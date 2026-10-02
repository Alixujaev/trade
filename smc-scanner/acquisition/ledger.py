"""acquisition/ledger.py: OOS completeness ledger from immutable snapshot metadata.

Reads only run/meta JSON and file bytes for SHA-256 (never parses parquet content). A unit
(session, symbol, interval) is complete only if an accepted snapshot file covers it with every expected
bar, passed structural validation, has the required metadata, and its bytes still match the recorded hash.
Discrepancy copies (conflicts/) never count; the earliest complete snapshot is the accepted original.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acquisition.capture_policy import capturable_sessions
from acquisition.contract import EXCHANGE_TZ, SUPPORTED_INTERVALS, oos_universe
from acquisition.provider_adapter import (
    INTRADAY_LOOKBACK_DAYS, LOOKBACK_SAFETY_MARGIN_DAYS, earliest_requestable_start,
)
from acquisition.sessions import OOSSession

REQUIRED_META = ("content_sha256", "file_sha256", "provider_config", "symbol", "interval", "row_count",
                 "structural_checks", "schema_version")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _data_path(snap_dir: Path, rec: dict[str, Any]) -> Path:
    # New runs record the data file; snapshot #1 (DAY-15B initial run) used {SYM}_{iv}.parquet.
    if rec.get("data_file"):
        return snap_dir / rec["data_file"]
    return snap_dir / f"{rec['symbol']}_{rec['interval']}.parquet"


def complete_units(root: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    """{(session_iso, symbol, interval): provenance} for every verified complete unit (earliest snapshot wins)."""
    units: dict[tuple[str, str, str], dict[str, Any]] = {}
    snaps = Path(root) / "snapshots"
    if not snaps.exists():
        return units
    for run_path in sorted(snaps.glob("*/run.json")):
        snap_dir = run_path.parent
        run = json.loads(run_path.read_text(encoding="utf-8"))
        for rec in run.get("results", []):
            if rec.get("status") == "MISSING" or not rec.get("structural_passed"):
                continue
            data = _data_path(snap_dir, rec)
            meta_path = data.with_suffix("").with_suffix(".meta.json")
            if not data.exists() or not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if any(k not in meta for k in REQUIRED_META) or meta["provider_config"].get("auto_adjust") is not False:
                continue
            if meta["content_sha256"] != rec.get("content_sha256") or _sha(data) != meta["file_sha256"]:
                continue
            for session, cov in (rec.get("coverage_per_session") or {}).items():
                if cov.get("expected_bars", 0) > 0 and cov.get("present_bars") == cov["expected_bars"] \
                        and not cov.get("missing_bar_opens"):
                    key = (session, rec["symbol"], rec["interval"])
                    units.setdefault(key, {"snapshot_id": run.get("snapshot_id", snap_dir.name),
                                           "data_file": str(data.relative_to(root)).replace("\\", "/"),
                                           "file_sha256": meta["file_sha256"]})
    return units


def _runs(indices: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for i in sorted(indices):
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def capture_state(root: Path, sessions: list[OOSSession], now: datetime,
                  symbols: list[str] | None = None,
                  intervals: tuple[str, ...] = tuple(sorted(SUPPORTED_INTERVALS))) -> dict[str, Any]:
    """Ledger-based lifecycle state. No network, no market-data content."""
    symbols = list(symbols) if symbols is not None else oos_universe()
    done = complete_units(root)
    combos = [(s, i) for s in symbols for i in intervals]
    per_session = {}
    for s in sessions:
        n = sum(1 for sym, iv in combos if (s.session.isoformat(), sym, iv) in done)
        per_session[s.index] = n
    complete = [s for s in sessions if per_session[s.index] == len(combos)]
    partial = [s for s in sessions if 0 < per_session[s.index] < len(combos)]
    missing = [s for s in sessions if per_session[s.index] == 0]
    cap = capturable_sessions(sessions, now)
    by_index = {s.index: s for s in sessions}
    plan = []
    for sym, iv in combos:
        need = [s.index for s in cap if (s.session.isoformat(), sym, iv) not in done]
        for a, b in _runs(need):
            plan.append({"symbol": sym, "interval": iv, "first_index": a, "last_index": b,
                         "first_session": by_index[a].session.isoformat(), "last_session": by_index[b].session.isoformat()})
    limit = earliest_requestable_start(now)
    remaining_cap = sorted({p["first_index"] for p in plan})
    earliest_missing = by_index[remaining_cap[0]] if remaining_cap else None
    if len(complete) == len(sessions):
        status = "COMPLETE"
    elif not plan:
        status = "UP_TO_DATE"
    elif pd.Timestamp(earliest_missing.session).tz_localize(EXCHANGE_TZ) < limit:
        status = "BLOCKED"
    else:
        status = "READY"
    return {
        "status": status,
        "total_sessions": len(sessions),
        "units_per_session": len(combos),
        "complete_sessions": [s.session.isoformat() for s in complete],
        "partial_sessions": [s.session.isoformat() for s in partial],
        "missing_sessions": [s.session.isoformat() for s in missing],
        "progress": f"{len(complete)}/{len(sessions)}",
        "capturable_sessions": [s.session.isoformat() for s in cap],
        "latest_capturable_session": cap[-1].session.isoformat() if cap else None,
        "earliest_missing_capturable_session": earliest_missing.session.isoformat() if earliest_missing else None,
        "provider_window": {"earliest_requestable_start_utc": limit.isoformat(),
                            "lookback_days": INTRADAY_LOOKBACK_DAYS, "safety_margin_days": LOOKBACK_SAFETY_MARGIN_DAYS,
                            "status": "INFERRED"},
        "planned_requests": plan,
        "planned_request_count": len(plan),
    }
