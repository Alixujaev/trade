"""data/v11_research_loader.py: read-only loader for the protocol v1.1 Alpaca SIP research snapshot (DAY-15H).

Data-loading adapter only. It never creates a market-data provider, never reads data/cache or the v1.0 OOS
tree, and never requests anything from the network.

Hard rules (protocol-v1.1.md §3–§6, §16):
- every data file is re-hashed against the snapshot's files.json before use;
- any bar whose ET session is on/after the first OOS session (2026-09-29) aborts the load;
- the embargo session (2026-09-28) is excluded: it is never handed to the engine;
- only OHLCV is returned (provider_vwap / trade_count are provenance fields and are dropped), so the strategy
  computes VWAP from OHLCV with indicators/vwap.py exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acquisition.v1_1.contract import FIRST_OOS_SESSION, RESEARCH_ROOT, v11_universe
from data.session import get_session_dates

STRATEGY_COLUMNS = ("open", "high", "low", "close", "volume")
INTERVALS = ("5m", "15m")
EXPECTED_SEGMENTS = {"warmup": 20, "research": 60, "embargo": 1}


class V11DataError(RuntimeError):
    """The v1.1 research snapshot failed an integrity or boundary check; nothing may be computed."""


@dataclass
class V11ResearchData:
    snapshot_id: str
    snapshot_dir: Path
    warmup_sessions: list[date]
    research_sessions: list[date]
    embargo_sessions: list[date]
    frames: dict[str, dict[str, pd.DataFrame]]          # symbol -> interval -> warmup+research OHLCV
    identity: dict[str, Any] = field(default_factory=dict)

    def frame(self, symbol: str, interval: str, segments: tuple[str, ...] = ("warmup", "research")) -> pd.DataFrame:
        df = self.frames[symbol][interval]
        keep: set[date] = set()
        if "warmup" in segments:
            keep |= set(self.warmup_sessions)
        if "research" in segments:
            keep |= set(self.research_sessions)
        sess = get_session_dates(df.index)
        return df.loc[sess.isin(keep).to_numpy()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_snapshot_dir(root: Path = RESEARCH_ROOT) -> Path:
    snaps = sorted(p for p in (Path(root) / "snapshots").iterdir() if p.is_dir())
    if len(snaps) != 1:
        raise V11DataError(f"expected exactly one research snapshot, found {[p.name for p in snaps]}")
    return snaps[0]


def load_v11_research(snapshot_dir: Path | None = None, symbols: list[str] | None = None) -> V11ResearchData:
    snap = Path(snapshot_dir) if snapshot_dir is not None else default_snapshot_dir()
    files = json.loads((snap / "files.json").read_text(encoding="utf-8"))
    units = json.loads((snap / "units.json").read_text(encoding="utf-8"))
    run = json.loads((snap / "run.json").read_text(encoding="utf-8"))

    bad = [u for u in units if u.get("status") != "COMPLETE"]
    if bad:
        raise V11DataError(f"{len(bad)} units are not COMPLETE")
    seg_of: dict[date, str] = {}
    for u in units:
        d = date.fromisoformat(u["session"])
        if d >= FIRST_OOS_SESSION:
            raise V11DataError(f"OOS session {d} present in research snapshot")
        if seg_of.setdefault(d, u["segment"]) != u["segment"]:
            raise V11DataError(f"inconsistent segment for {d}")
    counts = {s: sum(1 for v in seg_of.values() if v == s) for s in EXPECTED_SEGMENTS}
    if counts != EXPECTED_SEGMENTS or set(seg_of.values()) != set(EXPECTED_SEGMENTS):
        raise V11DataError(f"segment counts {counts} != {EXPECTED_SEGMENTS}")
    warmup = sorted(d for d, s in seg_of.items() if s == "warmup")
    research = sorted(d for d, s in seg_of.items() if s == "research")
    embargo = sorted(d for d, s in seg_of.items() if s == "embargo")
    if not (max(warmup) < min(research) and max(research) < min(embargo)):
        raise V11DataError("segments are not chronological")

    universe = v11_universe()
    symbols = sorted(symbols) if symbols is not None else universe
    if not set(symbols) <= set(universe):
        raise V11DataError(f"symbols outside the frozen universe: {sorted(set(symbols) - set(universe))}")
    keep = set(warmup) | set(research)
    frames: dict[str, dict[str, pd.DataFrame]] = {}
    hashes: dict[str, str] = {}
    for sym in symbols:
        frames[sym] = {}
        for iv in INTERVALS:
            name = f"{sym}_{iv}.parquet"
            path = snap / name
            rec = files.get(name)
            if rec is None or _sha(path) != rec["file_sha256"]:
                raise V11DataError(f"hash mismatch or missing record for {name}")
            hashes[name] = rec["file_sha256"]
            df = pd.read_parquet(path)
            if "adj_close" in df.columns:
                raise V11DataError(f"unexpected adj_close in {name}")
            if not isinstance(df.index, pd.DatetimeIndex) or str(df.index.tz) != "UTC":
                raise V11DataError(f"{name}: index is not tz-aware UTC")
            if not df.index.is_unique or not df.index.is_monotonic_increasing:
                raise V11DataError(f"{name}: index not unique/monotonic")
            sess = get_session_dates(df.index)
            if (sess >= FIRST_OOS_SESSION).any():
                raise V11DataError(f"{name}: bars on/after {FIRST_OOS_SESSION} present; stopping")
            df = df.loc[sess.isin(keep).to_numpy(), list(STRATEGY_COLUMNS)]
            frames[sym][iv] = df
    identity = {
        "snapshot_id": snap.name,
        "snapshot_dir": str(snap),
        "files_json_sha256": _sha(snap / "files.json"),
        "units_json_sha256": _sha(snap / "units.json"),
        "run_json_sha256": _sha(snap / "run.json"),
        "provider_config": run.get("provider_config"),
        "acquisition_commit": run.get("git_commit"),
        "data_file_sha256": hashes,
        "embargo_excluded_sessions": [d.isoformat() for d in embargo],
    }
    return V11ResearchData(snap.name, snap, warmup, research, embargo, frames, identity)
