"""acquisition/v2/contract.py: frozen Stage R acquisition contract.

Sources: artifacts/day16/research-protocol-v2.md (v2.0 R1, frozen at ba3cefe) §2, §3.1-§3.9, §17 and
artifacts/day17a/protocol-v2.0.1-amendment.md (v2.0.1, committed at ed034b3) C1-C4.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from acquisition.contract import ROOT_DIR
from config.day_universe import get_day_universe

PROTOCOL_VERSION = "2.0 R1 + 2.0.1 + 2.0.2"
SCHEMA_VERSION = "v2-stage-r-snapshot/1.0"
REVIEW_SCHEMA_VERSION = "v2-stage-r-review/1.0"
FREEZE_COMMIT = "ba3cefe54ccf2fe14c62f1c609f143d8a0904221"
AMENDMENT_COMMIT = "ed034b3e9500cc4d9b33625de7e1883f572cd5a4"
AMENDMENT_002_COMMIT = "0ebb6065f6e981e324220bae2abd2222800b2228"
AMENDMENT_002_FILES = (
    "artifacts/day18a/protocol-v2.0.2-amendment.md",
    "artifacts/day18a/protocol-v2.0.2-amendment.json",
)
PROTOCOL_FILES = (
    "artifacts/day16/research-protocol-v2.md",
    "artifacts/day16/research-protocol-v2.json",
    "artifacts/day16/research-checklist.json",
)
AMENDMENT_FILES = (
    "artifacts/day17a/protocol-v2.0.1-amendment.md",
    "artifacts/day17a/protocol-v2.0.1-amendment.json",
)

# Stage R (protocol §3.5, §3.6, §3.9)
STAGE_R_FIRST_SESSION = date(2016, 1, 4)
STAGE_R_LAST_SESSION = date(2022, 12, 30)
STAGE_R_EXPECTED_SESSIONS = 1762          # local exchange_calendars 4.13.2 resolution (DAY-17 §4)
FIRST_BAR_MAX_LAG_SESSIONS = 5            # §3.8: first bar <= 2016-01-04 + 5 sessions

# Corporate-action windows on process_date (v2.0.1 C1); event_date boundary is authoritative
CA_Q1 = ("2016-01-01", "2022-12-30")
CA_Q2 = ("2022-12-31", "2023-03-31")
CA_WINDOWS = {"Q1": CA_Q1, "Q2": CA_Q2}
EVENT_DATE_MIN = STAGE_R_FIRST_SESSION.isoformat()
EVENT_DATE_MAX = STAGE_R_LAST_SESSION.isoformat()
CA_DATA_QUALITY = ("complete", "all")      # canonical, audit (v2.0.1 C4)
CA_TYPES = ("reverse_split", "forward_split", "unit_split", "cash_dividend", "stock_dividend", "spin_off",
            "cash_merger", "stock_merger", "stock_and_cash_merger", "redemption", "name_change",
            "worthless_removal", "rights_distribution", "partial_call", "reorganization",
            "capital_gains_distribution")

BENCHMARK_SYMBOL = "SPY"
CA_QUERY_ALIASES = ("FB",)                 # v2.0.1 C2 rule 2 (Stage R alias)

# Frozen tolerances (protocol §3.4, §3.8) - never changed here.
# FACTOR_CHANGE_REL_TOL is the retired v2.0 R1 value, kept as a historical record only: v2.0.2 item 1 replaced
# the fixed relative test with the precision-interval rule (acquisition/v2/crosscheck.py), which has no constant.
FACTOR_CHANGE_REL_TOL = 1e-6
SPLIT_RATIO_REL_TOL = 0.001
MISSING_SESSION_REVIEW_FRACTION = 0.02

V2_ROOT = ROOT_DIR / "data" / "oos_cache" / "protocol_v2"
STAGE_R_ROOT = V2_ROOT / "stage_r"
FORBIDDEN_WRITE_ROOTS = (
    ROOT_DIR / "data" / "cache",
    ROOT_DIR / "artifacts",
    ROOT_DIR / "data" / "oos_cache" / "protocol_v1.0",
    ROOT_DIR / "data" / "oos_cache" / "protocol_v1.1",
)

BAR_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume", "trade_count", "provider_vwap")


@dataclass(frozen=True)
class DailyBarsConfig:
    provider: str = "alpaca-market-data-v2"
    url: str = "https://data.alpaca.markets/v2/stocks/bars"
    timeframe: str = "1Day"
    feed: str = "sip"
    limit: int = 10000
    sort: str = "asc"
    currency: str = "USD"
    end_semantics: str = "inclusive"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorporateActionsConfig:
    provider: str = "alpaca-market-data-v1"
    url: str = "https://data.alpaca.markets/v1/corporate-actions"
    limit: int = 1000
    sort: str = "asc"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


ASSETS_URL = "https://paper-api.alpaca.markets/v2/assets"


def universe() -> list[str]:
    """Frozen 25-symbol research universe, sorted."""
    return sorted(get_day_universe())


def stage_r_symbols() -> list[str]:
    """25 universe symbols + SPY (benchmark B2 only), sorted."""
    return sorted(set(universe()) | {BENCHMARK_SYMBOL})


def ca_query_symbols() -> list[str]:
    return sorted(set(stage_r_symbols()) | set(CA_QUERY_ALIASES))
