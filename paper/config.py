"""paper/config.py: frozen parameters of the sealed paper-trading experiment V2-MOM-P001 (protocol 2.3, DAY-27).

Nothing here changes V2-MOM: ranking, sizing, timing and costs come from backtest/v2 (frozen config SHA
62827d70…); only the operational setting (dates, seal, state location, data endpoint) is declared.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from acquisition.contract import ROOT_DIR
from acquisition.v2.contract import CorporateActionsConfig, DailyBarsConfig

EXPERIMENT_ID = "V2-MOM-P001"
BENCHMARK_IDS = {"B1": "V2-B1-P001", "B2": "V2-B2-P001"}
MARKET_TZ = ZoneInfo("America/New_York")
FIRST_SESSION = date(2026, 10, 12)                 # first sample session; initial decision at the 2026-10-09 close
HISTORY_START = date(2025, 1, 2)                   # bar/event history start (>= 252 sessions of lookback)
SEAL_UNTIL = datetime(2026, 12, 9, 16, 15, tzinfo=MARKET_TZ)   # fwd-gate2 capture time; nothing revealed before
COST_PRIMARY = 0.0005                              # frozen primary 5 bps per side
LEDGERS = ("V2-MOM", "B1", "B2")
DATA_READY_DELAY_MIN = 15                          # minutes after the official close before the day's bar is used
STALE_LOCK_SECONDS = 2 * 3600
ALLOWED_URL_PREFIX = "https://data.alpaca.markets/"
DATA_URLS = (DailyBarsConfig().url, CorporateActionsConfig().url)
ADOPTION_JSON_23 = "artifacts/day27/protocol-v2.3-adoption.json"
AMENDMENT_FILES_23 = ("artifacts/day27/protocol-v2.3-amendment.md", "artifacts/day27/protocol-v2.3-amendment.json")
RISK = {"max_names": 5, "max_target_weight": 0.2, "max_target_sum": 1.0, "max_exposure": 1.0 + 1e-9,
        "min_cash": -1e-6}


def state_dir() -> Path:
    """Runner state root: $PAPER_STATE_DIR, else <repo>/paper_state (gitignored)."""
    return Path(os.environ.get("PAPER_STATE_DIR") or (ROOT_DIR / "paper_state"))


def ready_time(session_close: datetime) -> datetime:
    """When a session's daily bar may be used: official close (early closes included) + DATA_READY_DELAY_MIN."""
    return session_close + timedelta(minutes=DATA_READY_DELAY_MIN)
