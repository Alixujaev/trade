"""acquisition/v1_1/contract.py: frozen protocol v1.1 acquisition contract (protocol-v1.1.md §2, §3, §17)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from acquisition.contract import ROOT_DIR
from config.day_universe import get_day_universe

PROTOCOL_VERSION = "v1.1"
PROTOCOL_DOC = "artifacts/day15/protocol-v1.1.md"
SCHEMA_VERSION = "v1.1-research-snapshot/1.0"

# Calendar segments (protocol-v1.1.md §3). The rule is authoritative; these anchor dates feed it.
RESEARCH_FIRST_SESSION = date(2026, 7, 2)
RESEARCH_LAST_SESSION = date(2026, 9, 25)
WARMUP_SESSIONS = 20
EMBARGO_SESSIONS = 1
STAGE1_SESSIONS = 20
STAGE2_SESSIONS = 40
FIRST_OOS_SESSION = date(2026, 9, 29)
# DAY-15G acquires warmup + research + embargo only; nothing on or after FIRST_OOS_SESSION.
DAY15G_LAST_SESSION = date(2026, 9, 28)

# interval -> (Alpaca timeframe, bar minutes)
TIMEFRAMES: dict[str, tuple[str, int]] = {"5m": ("5Min", 5), "15m": ("15Min", 15)}
INTERVAL_ORDER: tuple[str, ...] = ("5m", "15m")

STRATEGY_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
# trade_count (Alpaca 'n') and provider_vwap (Alpaca 'vw') are provenance only; the strategy computes its
# own VWAP from OHLCV (indicators/vwap.py) and never reads provider_vwap. There is no adj_close in v1.1.
STORED_COLUMNS: tuple[str, ...] = STRATEGY_COLUMNS + ("trade_count", "provider_vwap")

V11_ROOT = ROOT_DIR / "data" / "oos_cache" / "protocol_v1.1"
RESEARCH_ROOT = V11_ROOT / "research"
FORBIDDEN_WRITE_ROOTS = (
    ROOT_DIR / "data" / "cache",
    ROOT_DIR / "artifacts",
    ROOT_DIR / "data" / "oos_cache" / "protocol_v1.0",
)


@dataclass(frozen=True)
class AlpacaBarsConfig:
    """Every request parameter that is fixed by the protocol. `end` is INCLUSIVE at Alpaca (DAY-15E/15G)."""

    provider: str = "alpaca-market-data-v2"
    base_url: str = "https://data.alpaca.markets/v2/stocks"
    feed: str = "sip"
    adjustment: str = "raw"
    limit: int = 10000
    sort: str = "asc"
    end_semantics: str = "inclusive"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def v11_universe() -> list[str]:
    """Frozen 25-symbol universe, sorted for deterministic acquisition order."""
    return sorted(get_day_universe())


def timeframe(interval: str) -> str:
    if interval not in TIMEFRAMES:
        raise ValueError(f"Unsupported interval {interval!r}; supported: {list(TIMEFRAMES)}")
    return TIMEFRAMES[interval][0]


def bar_minutes(interval: str) -> int:
    if interval not in TIMEFRAMES:
        raise ValueError(f"Unsupported interval {interval!r}; supported: {list(TIMEFRAMES)}")
    return TIMEFRAMES[interval][1]
