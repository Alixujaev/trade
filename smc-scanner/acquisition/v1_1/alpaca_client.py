"""acquisition/v1_1/alpaca_client.py: Alpaca Market Data v2 historical stock bars (protocol v1.1 §2, §17).

- feed=sip, adjustment=raw, explicit start/end on every request, fixed limit and sort.
- **Alpaca `end` is INCLUSIVE** (VERIFIED, DAY-15E 5Min / DAY-15G 15Min): a bar whose start equals `end` is
  returned. This module never uses yfinance's exclusive "end = next day 00:00" convention; callers pass the
  last wanted bar OPEN as `end`.
- Pagination follows `next_page_token` until it is null. Pages are concatenated in order; an identical
  bar repeated across pages is collapsed and counted, a conflicting one raises (never silently chosen).
- Deterministic retry policy (RETRY_STATUSES / RETRY_SLEEPS_S). 401/403 are fatal and never retried.
- Credentials are sent as headers only and never appear in returned request records.
No filtering of sessions, no indicator or signal computation happens here.
"""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Callable

import pandas as pd

from acquisition.v1_1.contract import STORED_COLUMNS, AlpacaBarsConfig, timeframe

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_SLEEPS_S = (2.0, 5.0, 15.0)        # sleeps before attempts 2, 3, 4 -> at most 4 attempts per page
FATAL_STATUSES = frozenset({401, 403})
MAX_PAGES = 100
_FIELD_MAP = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "n": "trade_count",
              "vw": "provider_vwap"}


class AlpacaRequestError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, fatal: bool = False):
        super().__init__(message)
        self.status = status
        self.fatal = fatal


class EndBeyondLimitError(RuntimeError):
    """The requested inclusive end lies after the caller's hard limit (raised before any request)."""


class PageConflictError(RuntimeError):
    """The same bar timestamp appeared twice with different values."""


def _utc_str(ts: datetime | pd.Timestamp) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_frame() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], tz="UTC", name="datetime")
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in STORED_COLUMNS}, index=idx)


def normalize_bars(bars: list[dict[str, Any]]) -> tuple[pd.DataFrame, int]:
    """Alpaca bar dicts (in page order) -> canonical frame (UTC index = bar START), identical-duplicate count."""
    if not bars:
        return empty_frame(), 0
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    dupes = 0
    for b in bars:
        missing = [k for k in ("t", "o", "h", "l", "c", "v") if k not in b]
        if missing:
            raise ValueError(f"bar missing fields {missing}")
        key = b["t"]
        rec = {_FIELD_MAP[k]: b.get(k) for k in _FIELD_MAP}
        if key in seen:
            if seen[key] != rec:
                raise PageConflictError(f"conflicting duplicate bar at {key}")
            dupes += 1
            continue
        seen[key] = rec
        order.append(key)
    idx = pd.DatetimeIndex(pd.to_datetime(order, utc=True), name="datetime")
    df = pd.DataFrame([seen[k] for k in order], index=idx, columns=list(STORED_COLUMNS))
    for c in ("open", "high", "low", "close", "provider_vwap"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in ("volume", "trade_count"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df = df.sort_index(kind="mergesort")
    return df, dupes


class AlpacaBarsClient:
    def __init__(self, api_key: str, secret_key: str, *, config: AlpacaBarsConfig | None = None,
                 get: Callable[..., Any] | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, min_interval_s: float = 0.35,
                 timeout_s: float = 30.0) -> None:
        if not api_key or not secret_key:
            raise ValueError("Alpaca credentials are missing")
        self.config = config or AlpacaBarsConfig()
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key, "Accept": "application/json"}
        if get is None:
            import requests
            get = requests.get
        self._get = get
        self._sleep = sleep
        self._clock = clock
        self._min_interval = min_interval_s
        self._timeout = timeout_s
        self._last_call: float | None = None

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _get_page(self, url: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        for attempt in range(len(RETRY_SLEEPS_S) + 1):
            if attempt:
                self._sleep(RETRY_SLEEPS_S[attempt - 1])
            self._throttle()
            try:
                resp = self._get(url, params=dict(params), headers=self._headers, timeout=self._timeout)
            except OSError as exc:  # includes requests.ConnectionError / Timeout (RequestException is an IOError)
                attempts.append({"attempt": attempt + 1, "error": type(exc).__name__})
                continue
            status = int(resp.status_code)
            rid = resp.headers.get("X-Request-ID") if resp.headers else None
            attempts.append({"attempt": attempt + 1, "status": status, "request_id": rid})
            if status == 200:
                return resp.json(), {"status": status, "request_id": rid, "attempts": attempts}
            body = (resp.text or "")[:300]
            if status in FATAL_STATUSES:
                raise AlpacaRequestError(f"HTTP {status}: {body}", status=status, fatal=True)
            if status not in RETRY_STATUSES:
                raise AlpacaRequestError(f"HTTP {status}: {body}", status=status)
        raise AlpacaRequestError(f"retries exhausted: {attempts}", status=None)

    def fetch(self, symbol: str, interval: str, start: datetime, end: datetime, *,
              not_after: datetime) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Bars with start <= bar_start <= end (INCLUSIVE end). Rejects end > not_after before any request."""
        tf = timeframe(interval)
        s, e, lim = pd.Timestamp(start), pd.Timestamp(end), pd.Timestamp(not_after)
        if s.tzinfo is None or e.tzinfo is None or lim.tzinfo is None:
            raise ValueError("start/end/not_after must be timezone-aware")
        if e < s:
            raise ValueError("end before start")
        if e > lim:
            raise EndBeyondLimitError(f"requested end {e.isoformat()} is after the hard limit {lim.isoformat()}")
        url = f"{self.config.base_url}/{symbol}/bars"
        params: dict[str, Any] = {"timeframe": tf, "start": _utc_str(s), "end": _utc_str(e),
                                  "feed": self.config.feed, "adjustment": self.config.adjustment,
                                  "limit": self.config.limit, "sort": self.config.sort}
        bars: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(MAX_PAGES):
            p = dict(params, page_token=token) if token else params
            body, info = self._get_page(url, p)
            page_bars = body.get("bars") or []
            token = body.get("next_page_token")
            pages.append({**info, "bars": len(page_bars), "next_page_token_present": bool(token)})
            bars.extend(page_bars)
            if not token:
                break
        else:
            raise AlpacaRequestError(f"more than {MAX_PAGES} pages for {symbol} {interval}")
        df, dupes = normalize_bars(bars)
        record = {
            "symbol": symbol, "interval": interval, "url": url,
            "params": params, "end_semantics": self.config.end_semantics,
            "provider": self.config.provider, "provider_config": self.config.as_dict(),
            "page_count": len(pages), "pages": pages, "page_overlap_duplicates": dupes,
            "returned_rows": int(len(df)),
            "request_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        }
        return df, record
