"""backtest/orb_snapshot_input.py: research-only 5m SIP frames for the ORB engine (ORB-SIP-D1..D6).

Validation-and-pass-through layer around data/v11_research_loader.load_v11_research. It never changes bars, never
falls back to another snapshot or provider, and never touches the network. Decisions and pinned values:
artifacts/orb/sip_diagnostic_decision.md. Output feeds backtest.orb_engine.run_orb_backtest unchanged.

Every failure raises SnapshotInputError (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acquisition.v1_1.contract import AlpacaBarsConfig
from data.session import get_session_dates, is_rth_series
from data.v11_research_loader import V11DataError, load_v11_research

OHLCV = ["open", "high", "low", "close", "volume"]
INTERVAL = "5m"
SEGMENT = "research"
RESEARCH_FIRST = date(2026, 7, 2)
RESEARCH_LAST = date(2026, 9, 25)
RESEARCH_SESSIONS = 60


@dataclass(frozen=True)
class SnapshotPins:
    snapshot_id: str
    files_json_sha256: str
    units_json_sha256: str
    run_json_sha256: str


PINNED = SnapshotPins(
    snapshot_id="research_20261006T095201Z",
    files_json_sha256="b43b8996d1e45a58c61aba74bc8bc83b173809e554f4c0c125c0f4f5f6b95139",
    units_json_sha256="6a0466192a87ce53cb27d8b5e55a4fb510f8e790d8cc75548b6e9987a3b76b74",
    run_json_sha256="8b57b2dad2c22b69dee25845ef6d4d3520811088124c35b3b668e6fb510a4278",
)


class SnapshotInputError(RuntimeError):
    """The snapshot or a returned frame failed an ORB-SIP check; nothing may be computed."""


@dataclass(frozen=True)
class SnapshotInput:
    bars: dict[str, pd.DataFrame]
    provenance: dict[str, Any]


def _read_pinned_json(path: Path, expected_sha: str) -> Any:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise SnapshotInputError(f"cannot read {path.name}: {exc}") from exc
    got = hashlib.sha256(payload).hexdigest()
    if got != expected_sha:
        raise SnapshotInputError(f"{path.name} SHA-256 {got} != pinned {expected_sha}")
    try:
        return json.loads(payload.decode("utf-8"))
    except ValueError as exc:
        raise SnapshotInputError(f"{path.name} is not valid JSON: {exc}") from exc


def validate_frame(symbol: str, df: pd.DataFrame, research_sessions: set[date]) -> None:
    """Raise SnapshotInputError unless `df` is a clean research-only RTH 5m OHLCV frame. Never modifies `df`."""
    if df.empty:
        raise SnapshotInputError(f"{symbol}: empty frame")
    if list(df.columns) != OHLCV:
        raise SnapshotInputError(f"{symbol}: columns {list(df.columns)} != {OHLCV}")
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        raise SnapshotInputError(f"{symbol}: index is not a DatetimeIndex")
    if idx.tz is None or str(idx.tz) != "UTC":
        raise SnapshotInputError(f"{symbol}: index timezone is {idx.tz}, expected UTC")
    if idx.has_duplicates:
        raise SnapshotInputError(f"{symbol}: duplicate timestamps")
    if not idx.is_monotonic_increasing:
        raise SnapshotInputError(f"{symbol}: timestamps not monotonic increasing")
    non_rth = int((~is_rth_series(idx)).sum())
    if non_rth:
        raise SnapshotInputError(f"{symbol}: {non_rth} bars outside RTH")
    outside = sorted(set(get_session_dates(idx)) - research_sessions)
    if outside:
        raise SnapshotInputError(f"{symbol}: bars on non-research sessions {[d.isoformat() for d in outside[:5]]}")
    if df.isna().to_numpy().any():
        raise SnapshotInputError(f"{symbol}: NaN values present")


def load_research_frames(snapshot_dir: Path, symbols: list[str], *, pins: SnapshotPins = PINNED) -> SnapshotInput:
    """Pinned, research-only 5m frames {symbol: OHLCV} plus provenance. Raises SnapshotInputError on any failure."""
    snap = Path(snapshot_dir)
    if not snap.is_dir():
        raise SnapshotInputError(f"snapshot directory not found: {snap}")
    if snap.name != pins.snapshot_id:
        raise SnapshotInputError(f"snapshot {snap.name!r} != pinned {pins.snapshot_id!r}")
    symbols = list(symbols)
    if not symbols:
        raise SnapshotInputError("no symbols requested")
    if len(set(symbols)) != len(symbols):
        raise SnapshotInputError(f"duplicate symbols requested: {symbols}")

    try:
        data = load_v11_research(snap, symbols=symbols)
    except (V11DataError, OSError, KeyError, ValueError) as exc:
        raise SnapshotInputError(f"loader rejected snapshot: {type(exc).__name__}: {exc}") from exc

    ident = data.identity
    for key, pinned in (("files_json_sha256", pins.files_json_sha256), ("units_json_sha256", pins.units_json_sha256),
                        ("run_json_sha256", pins.run_json_sha256)):
        if ident.get(key) != pinned:
            raise SnapshotInputError(f"{key} {ident.get(key)} != pinned {pinned}")
    expected_cfg = AlpacaBarsConfig().as_dict()
    if ident.get("provider_config") != expected_cfg:
        raise SnapshotInputError(f"provider_config {ident.get('provider_config')} != {expected_cfg}")

    units = _read_pinned_json(snap / "units.json", pins.units_json_sha256)
    run = _read_pinned_json(snap / "run.json", pins.run_json_sha256)
    for u in units:
        where = f"unit {u.get('session')}/{u.get('symbol')}/{u.get('interval')}"
        if u.get("status") != "COMPLETE":
            raise SnapshotInputError(f"{where}: status {u.get('status')!r}")
        params = (u.get("request") or {}).get("params")
        if not isinstance(params, dict):
            raise SnapshotInputError(f"{where}: no recorded request params")
        if params.get("feed") != "sip" or params.get("adjustment") != "raw":
            raise SnapshotInputError(f"{where}: feed={params.get('feed')!r} adjustment={params.get('adjustment')!r}")
    missing = sorted(set(symbols) - set(run.get("symbols") or []))
    if missing:
        raise SnapshotInputError(f"symbols not in snapshot run.json: {missing}")

    research = list(data.research_sessions)
    if len(research) != RESEARCH_SESSIONS or research[0] != RESEARCH_FIRST or research[-1] != RESEARCH_LAST:
        raise SnapshotInputError(
            f"research segment {research[0] if research else None}..{research[-1] if research else None} "
            f"({len(research)} sessions) != {RESEARCH_FIRST}..{RESEARCH_LAST} ({RESEARCH_SESSIONS})")
    research_set = set(research)

    bars: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = data.frame(sym, INTERVAL, (SEGMENT,))
        validate_frame(sym, df, research_set)
        bars[sym] = df

    provenance = {
        "source": "Alpaca Market Data v2 SIP, adjustment=raw (v1.1 research snapshot)",
        "snapshot_id": pins.snapshot_id,
        "files_json_sha256": pins.files_json_sha256,
        "units_json_sha256": pins.units_json_sha256,
        "run_json_sha256": pins.run_json_sha256,
        "provider_config": expected_cfg,
        "acquisition_commit": ident.get("acquisition_commit"),
        "interval": INTERVAL,
        "segment": SEGMENT,
        "research_first": RESEARCH_FIRST.isoformat(),
        "research_last": RESEARCH_LAST.isoformat(),
        "research_sessions": RESEARCH_SESSIONS,
        "symbols": sorted(symbols),
        "rth_only": True,
        "warmup_supplied": False,
    }
    return SnapshotInput(bars=bars, provenance=provenance)
