"""backtest/day_types.py: DAY-02 — VWAP Momentum Backtest ma'lumot modellari.

QAT'IY METODOLOGIK QOIDA:
- Bu modellar natijalarni xolisona o'lchash uchun xizmat qiladi.
- Hech qanday "BUY SCORE", "OPTIMAL", "PROFITABLE" kabi subyektiv xulosalar yo'q.
- Har bir savdo rekordi point-in-time holat va kontekstni to'liq saqlaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Any
import pandas as pd

from strategy.day.types import DaySetupStatus


@dataclass(frozen=True)
class ExecutionConfig:
    """Intraday simulyatsiya uchun execution konfiguratsiyasi.

    Default qiymatlar BACKTEST ASSUMPTION hisoblanadi.
    """

    slippage_bps: float = 0.0              # Har bir kirish va chiqishda slippage (basis points: 1 bps = 0.01%)
    commission_per_share: float = 0.0      # Har bir aksiyaga to'lov ($)
    max_holding_minutes: int = 390         # Maksimal ushlab turish vaqti (daqiqa)
    force_exit_time: time = time(15, 55)   # RTH sessiyasi tugashidan oldin majburiy yopilish (15:55 ET)
    same_bar_rule: str = "STOP_FIRST"      # Agar bitta barda High>=TP va Low<=SL bo'lsa: "STOP_FIRST"

    # Stop va Target parametrlari (BACKTEST ASSUMPTION):
    # DAY-01 strategiyasida stop/target qoidalari aniqlanmagan.
    # Shuning uchun bu parametrlar faqat o'lchov gipotezasi hisoblanadi.
    stop_mode: str = "SIGNAL_LOW"          # "SIGNAL_LOW" | "VWAP" | "NONE"
    target_multiple: float | None = 2.0    # 2.0R yoki None (agar None bo'lsa faqat time/vwap/eod exit)
    exit_on_vwap_cross: bool = False       # Narx VWAP ostida yopilganda chiqish (ixtiyoriy)
    valid_statuses: tuple[DaySetupStatus, ...] = (
        DaySetupStatus.DETECTED,
        DaySetupStatus.CONFIRMED,
    )


@dataclass(frozen=True)
class DayBacktestTrade:
    """Bitta intraday simulyatsiya qilingan savdo yozuvi (immutable)."""

    symbol: str
    setup_time: pd.Timestamp               # Signal aniqlangan bar vaqti (T)
    entry_time: pd.Timestamp               # Kirish vaqti (T+1 bar open)
    entry_price: float                     # Kirish narxi (next bar open + slippage/comm)

    exit_time: pd.Timestamp                # Chiqish vaqti
    exit_price: float                      # Chiqish narxi
    exit_reason: str                       # "target" | "stop" | "vwap_loss" | "forced_eod" | "end_of_data"

    stop_price: float | None = None        # Belgilangan stop narxi (mavjud bo'lsa)
    target_price: float | None = None      # Belgilangan target narxi (mavjud bo'lsa)

    gross_return: float = 0.0              # (exit_price_raw - entry_price_raw) / entry_price_raw
    net_return: float = 0.0                # Xarajatlardan (slippage & comm) keyingi sof foiz

    risk_per_share: float | None = None    # |entry - stop|
    r_multiple: float | None = None        # (exit - entry) / risk_per_share

    rsi_at_setup: float = float("nan")
    rvol_at_setup: float = float("nan")
    vwap_at_setup: float = float("nan")

    structure_5m: str = "UNKNOWN"
    structure_15m: str = "UNKNOWN"

    evidence: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    hold_duration_minutes: int = 0
    trigger_type: str = "none"
    vwap_relation: str = "NO_RECLAIM"
    setup_status: str = "CONFIRMED"
    observed_price_at_setup: float = float("nan")


@dataclass(frozen=True)
class DayBacktestResult:
    """Butun intraday backtest simulyatsiyasi natijasi."""

    symbol: str
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    total_sessions: int
    total_bars: int

    trades: list[DayBacktestTrade]
    metrics: dict[str, Any]

    buy_and_hold_return: float             # Birinchi RTH narxidan oxirgi RTH narxigacha
    time_of_day_breakdown: dict[str, Any]
    component_breakdown: dict[str, Any]
    sensitivity_results: dict[str, Any]

    skipped_signals: int = 0               # Pozitsiya ochiqligi sabab tashlab ketilgan signallar
    insufficient_data_count: int = 0       # DATA_INSUFFICIENT sabab o'tkazib yuborilgan barlar
    same_bar_ambiguity_count: int = 0      # Bir barda SL va TP to'qnash kelgan holatlar soni

    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
