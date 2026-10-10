"""paper/data.py: market data for the sealed paper runner (reuses the v2 Alpaca clients and Stage H derivations).

fetch_inputs()      raw + adjustment=all 1Day bars (HISTORY_START -> session) and corporate actions, through the
                    existing DailyBarsClient / CorporateActionsClient, over an HTTP client restricted to
                    https://data.alpaca.markets/ (no trading endpoint is reachable from this package).
build_market_data() identity / normalisation / structural checks via acquisition.v2.stage_h.derive, then the frozen
                    MarketData (Series A open/close, split q, dividend d) exactly as backtest.v2.data.load_stage_f.
snapshot()          write-once input snapshot (raw bars + events + manifest with SHA-256) = the input-data reference.
Fail closed (DataFailClosed) on missing/stale/incomplete bars, bars after the session, off-calendar labels, structural
HARD_FAIL or BLOCKING, identity conflicts and normalisation blocking. Crosscheck/review items are reported as
review_pending (health), not silently resolved.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from acquisition.v2.contract import CA_DATA_QUALITY, ca_query_symbols, stage_r_symbols
from acquisition.v2.sessions import session_of_label
from backtest.v2.data import BENCHMARK_SYMBOL, MarketData
from config.day_universe import FROZEN_DAY_UNIVERSE
from paper.config import ALLOWED_URL_PREFIX, DATA_URLS, HISTORY_START


class DataFailClosed(RuntimeError):
    """Input data missing, stale, incomplete or inconsistent: nothing is processed."""


class EndpointGuardError(RuntimeError):
    """A request to anything other than the Alpaca market-data API was attempted."""


class GuardedHttp:
    """Wraps acquisition.v2.http.HttpClient; refuses every URL outside the market-data API."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def get_json(self, url: str, params: dict[str, Any]):
        if not url.startswith(ALLOWED_URL_PREFIX):
            raise EndpointGuardError("refused non-market-data URL (paper runner is data-only)")
        return self._inner.get_json(url, params)


def check_endpoints() -> None:
    bad = [u for u in DATA_URLS if not u.startswith(ALLOWED_URL_PREFIX)]
    if bad:
        raise EndpointGuardError("configured data URL outside the market-data API")


def sessions_between(first: date, last: date) -> list[date]:
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS", start=(pd.Timestamp(first) - pd.Timedelta(days=40)).date().isoformat(),
                             end=(pd.Timestamp(last) + pd.Timedelta(days=40)).date().isoformat())
    return [d.date() for d in cal.sessions_in_range(pd.Timestamp(first), pd.Timestamp(last))]


def fetch_inputs(session: date, http) -> dict[str, Any]:
    """Network step (only in `run`): bars and corporate actions up to `session`; nothing after it is requested."""
    from acquisition.v2.bars_client import DailyBarsClient
    from acquisition.v2.ca_client import CorporateActionsClient
    check_endpoints()
    http = GuardedHttp(http)
    syms = stage_r_symbols()
    bars = DailyBarsClient(http, asof=session.isoformat(), first_session=HISTORY_START, last_session=session)
    frames: dict[str, dict[str, pd.DataFrame]] = {"raw": {}, "all": {}}
    for adj in ("raw", "all"):
        for s in syms:
            frames[adj][s] = bars.fetch(s, adj)[0]
    windows = {"Q1": ("2025-01-01", session.isoformat())}
    q_syms = ca_query_symbols()
    client = CorporateActionsClient(http)
    ca: dict[str, list] = {q: [] for q in CA_DATA_QUALITY}
    counts: dict[str, Any] = {}
    for q in CA_DATA_QUALITY:
        kept, rec = client.fetch_window("Q1", q, q_syms, windows=windows, event_min=HISTORY_START.isoformat(),
                                        event_max=session.isoformat(), stage="paper")
        uniq = {}
        for r in kept:
            rid = str(r.get("id"))
            if rid in uniq and uniq[rid] != r:
                raise DataFailClosed("corporate action returned with different content across pages")
            uniq[rid] = r
        ca[q] = [uniq[k] for k in sorted(uniq)]
        counts[f"Q1_{q}"] = rec["counts"]
    return {"session": session, "frames": frames, "ca": ca, "ca_counts": counts, "q_syms": q_syms}


def build_market_data(inputs: dict[str, Any], first_session: date) -> tuple[MarketData, dict[str, Any]]:
    from acquisition.v2 import stage_h as sh
    session: date = inputs["session"]
    sessions = sessions_between(HISTORY_START, session)
    if not sessions or sessions[-1] != session:
        raise DataFailClosed(f"{session} is not an XNYS session")
    d = sh.derive(inputs["frames"], inputs["ca"], inputs["q_syms"], inputs["ca_counts"], sessions=sessions,
                  segment_first=first_session)
    counts = d["validation"]["status_counts"]
    if counts["HARD_FAIL"] or counts["BLOCKING"]:
        raise DataFailClosed(f"structural data check failed: {counts}")
    if d["identity"]["conflicts"] or d["identity"]["unassigned_records"]:
        raise DataFailClosed("corporate-action identity conflicts")
    if d["normalised"]["blocking"]:
        raise DataFailClosed("corporate-action normalisation blocking")
    tickers = tuple(sorted(FROZEN_DAY_UNIVERSE)) + (BENCHMARK_SYMBOL,)
    pos = {s: i for i, s in enumerate(sessions)}
    n, m = len(sessions), len(tickers)
    op, cl = np.full((n, m), np.nan), np.full((n, m), np.nan)
    for j, t in enumerate(tickers):
        df = inputs["frames"]["raw"].get(t)
        if df is None:
            raise DataFailClosed(f"no bars for {t}")
        for ts, o, c in zip(df.index, df["open"].to_numpy(np.float64), df["close"].to_numpy(np.float64)):
            day, exact = session_of_label(ts)
            if not exact or day not in pos:
                raise DataFailClosed(f"{t}: bar label is not an XNYS session up to {session}")
            op[pos[day], j], cl[pos[day], j] = o, c
    last_ok = ~np.isnan(op[-1]) & ~np.isnan(cl[-1])
    if not last_ok.all():
        missing = [tickers[j] for j in np.nonzero(~last_ok)[0]]
        raise DataFailClosed(f"incomplete or stale data: no {session} bar for {missing}")
    cross = d["crosscheck"]["per_symbol"]
    first_untestable = {e["id"] for v in cross.values() for e in v.get("first_session_untestable", [])}
    events = [e for e in d["normalised"]["events"] if e["id"] not in first_untestable]
    q, dv = np.ones((n, m)), np.zeros((n, m))
    seen = set()
    for e in events:
        if e["entity"] not in tickers:
            raise DataFailClosed("event for a non-universe entity")
        ex = date.fromisoformat(e["ex_date"])
        if ex not in pos:
            raise DataFailClosed("event ex-date is not a session up to the target session")
        key = (e["entity"], e["ex_date"])
        if key in seen:
            raise DataFailClosed("several events on one ex-date (v2.0.1 C3 blocking case)")
        seen.add(key)
        k, j = pos[ex], tickers.index(e["entity"])
        if e["event"] == "cash_dividend":
            dv[k, j] = float(e["d"])
        elif "split" in e["event"]:
            q[k, j] = float(e["q"])
        else:
            raise DataFailClosed(f"unsupported event type {e['event']}")
    review = [i for i in d["reviews"]["items"] if i["status"] in ("BLOCKING", "HARD_FAIL")]
    info = {"session": session.isoformat(), "sessions": n, "first_session": sessions[0].isoformat(),
            "missing_bars": int(np.isnan(cl).sum()), "events_used": len(events),
            "review_pending": [{k: i.get(k) for k in ("entity", "event_date", "category")} for i in review]}
    return MarketData(tuple(sessions), tickers, op, cl, q, dv), {"info": info, "events": events}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def snapshot(root: Path, inputs: dict[str, Any], events: list[dict]) -> str:
    """Content-addressed, write-once input snapshot data/<session>-<manifest sha[:12]>/; returns the manifest SHA-256.

    A retry that refetches different (e.g. vendor-corrected) data gets its own directory and reference, so the
    reference stored with a ledger always describes the data that ledger was computed from.
    """
    session: date = inputs["session"]
    tmp = Path(root) / "data" / f"{session.isoformat()}.tmp"
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    (tmp / "bars_raw").mkdir(parents=True)
    files = {}
    for s, df in sorted(inputs["frames"]["raw"].items()):
        p = tmp / "bars_raw" / f"{s}.parquet"
        df.to_parquet(p)
        files[f"bars_raw/{s}.parquet"] = _sha(p.read_bytes())
    ev = json.dumps({"events": events, "ca_counts": inputs["ca_counts"]}, sort_keys=True, default=str).encode()
    (tmp / "events.json").write_bytes(ev)
    files["events.json"] = _sha(ev)
    man = json.dumps({"session": session.isoformat(), "history_start": HISTORY_START.isoformat(), "files_sha256": files},
                     sort_keys=True, indent=1).encode()
    (tmp / "manifest.json").write_bytes(man)
    ref = _sha(man)
    d = Path(root) / "data" / f"{session.isoformat()}-{ref[:12]}"
    if (d / "manifest.json").is_file() and _sha((d / "manifest.json").read_bytes()) == ref:
        import shutil
        shutil.rmtree(tmp)                                              # identical snapshot already stored
    else:
        tmp.replace(d)
    return ref


Fetcher = Callable[[date], tuple[MarketData, dict[str, Any]]]
