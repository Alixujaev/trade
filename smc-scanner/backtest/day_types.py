"""backtest/day_types.py: DAY-02 — VWAP Momentum Backtest ma'lumot modellari.

QAT'IY METODOLOGIK QOIDA:
- Bu modellar natijalarni xolisona o'lchash uchun xizmat qiladi.
- Hech qanday "BUY SCORE", "OPTIMAL", "PROFITABLE" kabi subyektiv xulosalar yo'q.
- Har bir savdo rekordi point-in-time holat va kontekstni to'liq saqlaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import TYPE_CHECKING, Any
import pandas as pd

from strategy.day.types import DaySetupStatus

if TYPE_CHECKING:
    from backtest.session_gate import EntryWindow


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
    stop_mode: str = "SIGNAL_LOW"          # "SIGNAL_LOW" | "VWAP" | "ATR" | "NONE"
    target_multiple: float | None = 2.0    # 2.0R yoki None (agar None bo'lsa faqat time/vwap/eod exit)
    exit_on_vwap_cross: bool = False       # Narx VWAP ostida yopilganda chiqish (ixtiyoriy)
    valid_statuses: tuple[DaySetupStatus, ...] = (
        DaySetupStatus.DETECTED,
        DaySetupStatus.CONFIRMED,
    )
    breakeven_trigger_r: float | None = None  # DAY-07 H2: +1R ga yetganda breakeven stopga ko'chirish (masalan 1.0)
    atr_stop_multiplier: float | None = None  # DAY-09 H4: stop_mode="ATR" da risk = ATR_5m(signal) * multiplier
    max_trades_per_session: int | None = None  # DAY-10 H3: symbol+RTH session bo'yicha haqiqiy entry'lar chegarasi (None = cap yo'q)
    entry_window: EntryWindow | None = None    # DAY-11 H5: yangi entry faqat [start, end) ET oynasida (None = gate yo'q)


@dataclass(frozen=True)
class DayBacktestTrade:
    """Bitta intraday simulyatsiya qilingan savdo yozuvi (immutable)."""

    symbol: str
    setup_time: pd.Timestamp               # Signal aniqlangan bar vaqti (T)
    entry_time: pd.Timestamp               # Kirish vaqti (T+1 bar open)
    entry_price: float                     # Kirish narxi (next bar open + slippage/comm)

    exit_time: pd.Timestamp                # Chiqish vaqti
    exit_price: float                      # Chiqish narxi
    exit_reason: str                       # "target" | "stop" | "breakeven" | "vwap_loss" | "forced_eod" | "end_of_data"

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

    # DAY-07 H2 Dynamic Stop (1R -> Breakeven) maydonlari
    initial_stop_price: float | None = None
    initial_risk_per_share: float | None = None
    breakeven_price: float | None = None
    be_triggered: bool = False
    be_trigger_time: pd.Timestamp | None = None
    effective_exit_stop_price: float | None = None


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

    # DAY-10 H3: signal populyatsiyasi hisobi
    # candidate_signals = len(trades) + skipped_signals + cap_rejected_signals
    #                     + window_rejected_signals + simulation_none_count
    candidate_signals: int = 0             # valid_statuses ichidagi barcha setup'lar
    cap_rejected_signals: int = 0          # session frequency cap sabab ochilmagan entry'lar
    simulation_none_count: int = 0         # simulate_trade_execution None qaytargan (kun oxiri / data tugadi)
    window_rejected_signals: int = 0       # DAY-11 H5: entry vaqti oynadan tashqarida bo'lgani sabab ochilmagan
    window_rejected_entry_times: list[pd.Timestamp] = field(default_factory=list)  # rad etilgan entry bar vaqtlari
