"""acquisition/contract.py: frozen acquisition contract (DAY-14 protocol v1.0, DAY-15A design)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

from config.day_universe import get_day_universe

ROOT_DIR = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = "oos-snapshot/1.0"
PROTOCOL_VERSION = "v1.0"
PROTOCOL_DOC = "artifacts/day14/research-protocol.md"
PROTOCOL_COMMIT = "5d48c53"

# DAY-14 data-expansion-spec §3: OOS = first N NYSE sessions strictly after the research-window end.
RESEARCH_WINDOW_END = date(2026, 9, 25)
OOS_SESSION_COUNT = 60
OOS_RULE = f"first {OOS_SESSION_COUNT} NYSE sessions strictly after {RESEARCH_WINDOW_END.isoformat()}"

# interval -> bar length in minutes. 1m is not part of this project.
SUPPORTED_INTERVALS: dict[str, int] = {"5m": 5, "15m": 15}

# RTH in America/New_York (data/session.py convention); bars are indexed by their OPEN.
EXCHANGE_TZ = "America/New_York"
STORAGE_TZ = "UTC"
RTH_START = time(9, 30)
RTH_END = time(16, 0)
FULL_SESSION_BARS: dict[str, int] = {"5m": 78, "15m": 26}

# Write-once OOS tree, never inside the frozen research cache (data/cache).
OOS_ROOT = ROOT_DIR / "data" / "oos_cache" / "protocol_v1.0"
FORBIDDEN_WRITE_ROOTS = (ROOT_DIR / "data" / "cache", ROOT_DIR / "artifacts")

STORED_COLUMNS = ("open", "high", "low", "close", "adj_close", "volume")


@dataclass(frozen=True)
class ProviderConfig:
    """Every yfinance.download keyword passed explicitly (no reliance on provider defaults).

    auto_adjust=False: raw OHLC are stored together with Yahoo's 'Adj Close' (user decision, DAY-15A).
    """

    provider: str = "yfinance"
    auto_adjust: bool = False
    back_adjust: bool = False
    prepost: bool = False
    actions: bool = False
    repair: bool = False
    keepna: bool = False
    ignore_tz: bool = False
    rounding: bool = False
    threads: bool = False
    progress: bool = False
    group_by: str = "column"
    multi_level_index: bool = False

    def download_kwargs(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("provider")
        return d


def oos_universe() -> list[str]:
    """Frozen 25-symbol universe (no additions/removals in this cycle)."""
    return get_day_universe()


def validate_interval(interval: str) -> int:
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval {interval!r}; supported: {sorted(SUPPORTED_INTERVALS)}")
    return SUPPORTED_INTERVALS[interval]
