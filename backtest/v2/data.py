"""backtest/v2/data.py: Stage R market data on the XNYS session index and the PIT total-return index (§3.3, §3.4).

- Series A: raw open/close per symbol, indexed by XNYS session (NaN = missing; no nearest-row fallback, §3.3).
- Events: the approved v2.0.4 event set (events_normalised of the signed-off re-evaluation), minus
  FIRST_SESSION_UNTESTABLE events (v2.0.2 item 2) and events excluded by review (v2.0.3 EVENT_REJECTED; none).
- Series B: TR(k0) = 1; TR(k) = TR(p) * (C(k) * Q(p,k) + D(p,k)) / C(p) (frozen §3.4 formula).
Series C (adjustment=all) is never loaded here. Only the Stage R snapshot (sessions <= 2022-12-30) is read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acquisition.v2.contract import STAGE_R_ROOT
from acquisition.v2.reevaluate import verify_snapshot
from acquisition.v2.sessions import session_of_label, stage_r_sessions
from config.day_universe import FROZEN_DAY_UNIVERSE

SNAPSHOT_ID = "stage_r_20261007T093410Z"
SNAPSHOT_MANIFEST_SHA256 = "aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd"
REVIEW_OUTPUT = f"reviews/v2_0_4__{SNAPSHOT_ID}"
REVIEW_OUTPUT_MANIFEST_SHA256 = "755c905e0adae6c7cac924aa8146384defe7053784b526675e7b51d714f6d698"
BENCHMARK_SYMBOL = "SPY"
LAST_ALLOWED_SESSION = date(2022, 12, 30)          # Stage R boundary; nothing later is ever loaded


class DataError(RuntimeError):
    """Required data missing, inconsistent, or outside the approved Stage R state."""


@dataclass(frozen=True)
class MarketData:
    sessions: tuple[date, ...]                     # XNYS sessions 2016-01-04 .. last loaded session
    tickers: tuple[str, ...]                       # sorted universe (25) followed by SPY
    open: np.ndarray                               # (n_sessions, n_tickers) raw open, NaN = no bar
    close: np.ndarray                              # raw close
    q: np.ndarray                                  # split ratio with ex-date at session k (1.0 = none)
    d: np.ndarray                                  # cash dividend per share with ex-date at session k (0.0 = none)

    @property
    def universe(self) -> tuple[str, ...]:
        return tuple(t for t in self.tickers if t != BENCHMARK_SYMBOL)

    def col(self, ticker: str) -> int:
        return self.tickers.index(ticker)

    def index_of(self, s: date) -> int:
        return self.sessions.index(s)

    def truncate(self, last: int) -> "MarketData":
        """Data as known after the close of session index `last` (bars and events dated > last removed)."""
        sl = slice(0, last + 1)
        return replace(self, sessions=self.sessions[sl], open=self.open[sl].copy(), close=self.close[sl].copy(),
                       q=self.q[sl].copy(), d=self.d[sl].copy())


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_events(stage_r_root: Path = STAGE_R_ROOT) -> tuple[list[dict], dict]:
    """Approved v2.0.4 event set. Verifies the signed-off review output before use."""
    out = Path(stage_r_root) / REVIEW_OUTPUT
    if _sha(out / "manifest.json") != REVIEW_OUTPUT_MANIFEST_SHA256:
        raise DataError("approved v2.0.4 review output manifest does not match the signed-off hash")
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for name, h in man["files_sha256"].items():
        if _sha(out / name) != h:
            raise DataError(f"review output file {name} does not match its manifest")
    if man.get("final_status") != "USABLE_FOR_RESEARCH":
        raise DataError("Stage R review output is not USABLE_FOR_RESEARCH")
    events = json.loads((out / "events_normalised.json").read_text(encoding="utf-8"))["events"]
    cross = json.loads((out / "crosscheck.json").read_text(encoding="utf-8"))["per_symbol"]
    reviews = json.loads((out / "reviews.json").read_text(encoding="utf-8"))
    first_session = {e["id"] for v in cross.values() for e in v.get("first_session_untestable", [])}
    rejected = set(reviews.get("events_excluded_by_review", []))
    kept = [e for e in events if e["id"] not in first_session and e["id"] not in rejected]
    info = {"review_output": f"data/oos_cache/protocol_v2/stage_r/{REVIEW_OUTPUT}",
            "review_output_manifest_sha256": REVIEW_OUTPUT_MANIFEST_SHA256, "events_total": len(events),
            "excluded_first_session": sorted(first_session), "excluded_by_review": sorted(rejected),
            "events_used": len(kept)}
    return kept, info


def load_stage_r(stage_r_root: Path = STAGE_R_ROOT) -> tuple[MarketData, dict]:
    snap = Path(stage_r_root) / SNAPSHOT_ID
    pre = verify_snapshot(snap, SNAPSHOT_MANIFEST_SHA256)
    sessions = tuple(stage_r_sessions())
    if sessions[-1] > LAST_ALLOWED_SESSION:
        raise DataError("session index extends beyond the Stage R boundary")
    tickers = tuple(sorted(FROZEN_DAY_UNIVERSE)) + (BENCHMARK_SYMBOL,)
    pos = {s: i for i, s in enumerate(sessions)}
    n, m = len(sessions), len(tickers)
    op, cl = np.full((n, m), np.nan), np.full((n, m), np.nan)
    for j, t in enumerate(tickers):
        df = pd.read_parquet(snap / "bars_raw" / f"{t}.parquet", columns=["open", "close"])
        for ts, o, c in zip(df.index, df["open"].to_numpy(np.float64), df["close"].to_numpy(np.float64)):
            day, exact = session_of_label(ts)
            if not exact or day not in pos:
                raise DataError(f"{t}: bar label {ts} is not an XNYS Stage R session label")
            op[pos[day], j], cl[pos[day], j] = o, c
    q, d = np.ones((n, m)), np.zeros((n, m))
    events, ev_info = load_events(stage_r_root)
    seen: set[tuple[str, str]] = set()
    for e in events:
        if e["entity"] not in tickers:
            raise DataError(f"event for non-universe entity {e['entity']}")
        ex = date.fromisoformat(e["ex_date"])
        if ex not in pos:
            raise DataError(f"event {e['id']} ex-date {ex} is not a Stage R session")
        key = (e["entity"], e["ex_date"])
        if key in seen:
            raise DataError(f"several events for {key} (same-ex-date case is a BLOCKING review, v2.0.1 C3)")
        seen.add(key)
        k, j = pos[ex], tickers.index(e["entity"])
        if e["event"] == "cash_dividend":
            d[k, j] = float(e["d"])
        elif "split" in e["event"]:
            q[k, j] = float(e["q"])
        else:
            raise DataError(f"unsupported event type {e['event']}")
    info = {"snapshot_id": SNAPSHOT_ID, "manifest_sha256": pre["manifest_sha256"], "file_count": pre["file_count"],
            "tree_sha256": pre["tree_sha256"],
            "bars_raw_sha256": {f"bars_raw/{t}.parquet": pre["files"][f"bars_raw/{t}.parquet"] for t in tickers},
            "events": ev_info, "sessions": n, "first_session": sessions[0].isoformat(),
            "last_session": sessions[-1].isoformat(),
            "missing_bars": int(np.isnan(cl).sum()), "series_A_only": True, "series_C_loaded": False}
    return MarketData(sessions, tickers, op, cl, q, d), info


def tr_index(data: MarketData) -> np.ndarray:
    """Series B, frozen §3.4: chain-linked forward from each symbol's first close; NaN where the close is missing."""
    n, m = data.close.shape
    tr = np.full((n, m), np.nan)
    for j in range(m):
        c = data.close[:, j]
        have = np.nonzero(~np.isnan(c))[0]
        if not len(have):
            continue
        tr[have[0], j] = 1.0
        for p, k in zip(have[:-1], have[1:]):
            Q, D = 1.0, 0.0
            for e in range(p + 1, k + 1):               # events with ex-date in (p, k]
                if data.d[e, j]:
                    D += data.d[e, j] * float(np.prod(data.q[e + 1:k + 1, j]))   # carry into post-split units
                Q *= data.q[e, j]
            tr[k, j] = tr[p, j] * (c[k] * Q + D) / c[p]
    return tr
