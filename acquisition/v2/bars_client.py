"""acquisition/v2/bars_client.py: Alpaca SIP 1Day bars for Stage R (protocol §3.1, §3.3; DAY-17 Q1/Q2).

- GET /v2/stocks/bars, one symbol per request, timeframe=1Day, feed=sip, adjustment raw|all, explicit asof.
- start/end are the first/last Stage R bar LABELS (00:00 New York); Alpaca `end` is INCLUSIVE.
- Hard guard before any request: start >= label(2016-01-04) and end <= label(2022-12-30).
- Rows are returned exactly as received (no filtering); validation is a separate step.
No signal, return or index is computed.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from acquisition.v2.contract import BAR_COLUMNS, STAGE_R_FIRST_SESSION, STAGE_R_LAST_SESSION, DailyBarsConfig
from acquisition.v2.http import MAX_PAGES, AlpacaRequestError, HttpClient, RequestGuardError
from acquisition.v2.sessions import label_for

ADJUSTMENTS = ("raw", "all")
_FIELD_MAP = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "n": "trade_count",
              "vw": "provider_vwap"}


class PageConflictError(RuntimeError):
    """The same bar label appeared twice with different values."""


def _z(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_daily(bars: list[dict[str, Any]]) -> tuple[pd.DataFrame, int]:
    """Bar dicts -> frame indexed by UTC label (kept exactly as received, incl. duplicates of identical rows
    collapsed and counted). Conflicting duplicates raise."""
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    dupes = 0
    for b in bars:
        missing = [k for k in ("t", "o", "h", "l", "c", "v") if k not in b]
        if missing:
            raise ValueError(f"bar missing fields {missing}")
        rec = {_FIELD_MAP[k]: b.get(k) for k in _FIELD_MAP}
        if b["t"] in seen:
            if seen[b["t"]] != rec:
                raise PageConflictError(f"conflicting duplicate bar at {b['t']}")
            dupes += 1
            continue
        seen[b["t"]] = rec
        order.append(b["t"])
    idx = pd.DatetimeIndex(pd.to_datetime(order, utc=True), name="datetime")
    df = pd.DataFrame([seen[k] for k in order], index=idx, columns=list(BAR_COLUMNS))
    for c in BAR_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df, dupes


class DailyBarsClient:
    def __init__(self, http: HttpClient, *, asof: str, config: DailyBarsConfig | None = None) -> None:
        if not asof or len(asof) != 10:
            raise ValueError("asof must be an explicit YYYY-MM-DD date")
        self.http = http
        self.asof = asof
        self.config = config or DailyBarsConfig()
        self.min_label = label_for(STAGE_R_FIRST_SESSION)
        self.max_label = label_for(STAGE_R_LAST_SESSION)

    def fetch(self, symbol: str, adjustment: str, start: pd.Timestamp | None = None,
              end: pd.Timestamp | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
        if adjustment not in ADJUSTMENTS:
            raise RequestGuardError(f"adjustment {adjustment!r} not in {ADJUSTMENTS}")
        s = pd.Timestamp(start) if start is not None else self.min_label
        e = pd.Timestamp(end) if end is not None else self.max_label
        if s.tzinfo is None or e.tzinfo is None:
            raise RequestGuardError("start/end must be timezone-aware")
        if s < self.min_label or e > self.max_label or e < s:
            raise RequestGuardError(f"bar request {s}..{e} outside Stage R {self.min_label}..{self.max_label}")
        params: dict[str, Any] = {"symbols": symbol, "timeframe": self.config.timeframe, "start": _z(s),
                                  "end": _z(e), "feed": self.config.feed, "adjustment": adjustment,
                                  "asof": self.asof, "limit": self.config.limit, "sort": self.config.sort,
                                  "currency": self.config.currency}
        bars: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        other_symbols: set[str] = set()
        token: str | None = None
        for _ in range(MAX_PAGES):
            p = dict(params, page_token=token) if token else params
            body, info = self.http.get_json(self.config.url, p)
            by_sym = body.get("bars") or {}
            other_symbols |= {k for k in by_sym if k != symbol}
            page_bars = by_sym.get(symbol) or []
            token = body.get("next_page_token")
            pages.append({**info, "bars": len(page_bars), "next_page_token_present": bool(token)})
            bars.extend(page_bars)
            if not token:
                break
        else:
            raise AlpacaRequestError(f"more than {MAX_PAGES} pages for {symbol} {adjustment}")
        df, dupes = normalize_daily(bars)
        record = {"symbol": symbol, "adjustment": adjustment, "url": self.config.url, "params": params,
                  "provider_config": self.config.as_dict(), "page_count": len(pages), "pages": pages,
                  "page_overlap_duplicates": dupes, "returned_rows": int(len(df)),
                  "unexpected_symbols_in_response": sorted(other_symbols),
                  "request_utc": pd.Timestamp.now(tz="UTC").isoformat()}
        return df, record
