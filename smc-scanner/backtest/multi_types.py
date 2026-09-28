"""backtest/multi_types.py: DAY-04 — Multi-symbol validation ma'lumot modellari.

QAT'IY METODOLOGIK QOIDALAR:
- Bu modellar bir nechta aksiyalar bo'yicha muzlatilgan strategiyaning xolis statistik
  taqsimotini o'lchash uchun xizmat qiladi.
- Aksiyalarga baho berilmaydi ("yaxshi", "yomon", "eng zo'r" deb etiketlanmaydi).
- Har bir metrika factual o'lchov sifatida saqlanadi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
import pandas as pd

from backtest.day_types import DayBacktestResult, ExecutionConfig


class DataCoverageStatus(str, Enum):
    """Ma'lumot mavjudligi va qamrovi holati."""

    AVAILABLE = "AVAILABLE"        # To'liq va tekshirilgan ma'lumot
    PARTIAL = "PARTIAL"            # Qisman ma'lumot (umumiy oynadan kamroq)
    UNAVAILABLE = "UNAVAILABLE"    # Ma'lumot mavjud emas / topilmadi
    INVALID = "INVALID"            # OHLCV validatsiya xatosi


@dataclass(frozen=True)
class SymbolCoverage:
    """Bitta aksiya uchun ma'lumot qamrovi metrikasi."""

    symbol: str
    status: DataCoverageStatus
    bars_5m: int = 0
    bars_15m: int = 0
    start_date: pd.Timestamp | None = None
    end_date: pd.Timestamp | None = None
    reason: str = ""


@dataclass(frozen=True)
class PerSymbolMetrics:
    """Bitta aksiya bo'yicha barcha hisoblangan natijalar (factual)."""

    symbol: str
    data_start: pd.Timestamp
    data_end: pd.Timestamp
    sessions: int
    bars_5m: int
    bars_15m: int
    data_status: str

    trades: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float

    strategy_total_return: float
    strategy_avg_trade_return: float
    strategy_median_trade_return: float

    profit_factor: float
    expectancy: float
    max_drawdown: float

    avg_R: float | None
    median_R: float | None
    total_R: float | None

    skipped_signals: int
    insufficient_data: int
    same_bar_ambiguity: int

    buy_hold_return: float
    return_difference_vs_buy_hold: float

    slippage_0bps: float
    slippage_5bps: float
    slippage_10bps: float


@dataclass(frozen=True)
class AggregateTradeStats:
    """Barcha aksiyalar bo'ylab jamlangan savdo-darajali statistika (trade-level aggregate)."""

    total_trades: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float
    profit_factor: float
    expectancy: float
    total_R: float
    avg_R: float
    median_R: float
    r_std: float


@dataclass(frozen=True)
class SymbolDistributionStats:
    """Aksiyalar kesimidagi taqsimot statistikasi (descriptive, not ranking)."""

    total_symbols_tested: int
    positive_strategy_symbols: int
    negative_strategy_symbols: int
    zero_strategy_symbols: int
    median_strategy_return: float
    mean_strategy_return: float
    median_buy_hold_return: float
    mean_buy_hold_return: float
    outperformed_buy_hold_count: int


@dataclass(frozen=True)
class MarketContextSummary:
    """Indeks ETF (SPY / QQQ) kunlik yo'nalishi bo'yicha diagnostik taqsimot (strategiya filtri EMAS)."""

    spy_positive_trades: int
    spy_positive_win_rate: float
    spy_positive_avg_return: float

    spy_negative_trades: int
    spy_negative_win_rate: float
    spy_negative_avg_return: float

    qqq_positive_trades: int
    qqq_positive_win_rate: float
    qqq_positive_avg_return: float

    qqq_negative_trades: int
    qqq_negative_win_rate: float
    qqq_negative_avg_return: float

    spy_bnh_return: float
    qqq_bnh_return: float


@dataclass
class MultiSymbolDayBacktestResult:
    """DAY-04 Multi-symbol backtest validation to'liq natijasi."""

    study_window_start: pd.Timestamp
    study_window_end: pd.Timestamp
    total_sessions: int
    universe: list[str]
    tested_symbols: list[str]
    coverage: dict[str, SymbolCoverage]
    per_symbol_metrics: list[PerSymbolMetrics]
    aggregate_trade_stats: AggregateTradeStats
    symbol_distribution: SymbolDistributionStats
    slippage_sensitivity: dict[str, dict[str, float]]
    market_context: MarketContextSummary | None = None
    symbol_results: dict[str, DayBacktestResult] = field(default_factory=dict)
    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON serializatsiya uchun toza lug'at (dict) ga o'giradi."""
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, (pd.Timestamp, pd.DatetimeIndex)):
                return str(obj)
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, (PerSymbolMetrics, SymbolCoverage, AggregateTradeStats,
                                SymbolDistributionStats, MarketContextSummary)):
                d = asdict(obj)
                for k, v in d.items():
                    d[k] = _serialize(v)
                return d
            if isinstance(obj, dict):
                return {str(k): _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(item) for item in obj]
            if isinstance(obj, float) and (pd.isna(obj) or pd.isna(obj)):
                return None
            return obj

        return {
            "study_window": {
                "start": str(self.study_window_start),
                "end": str(self.study_window_end),
                "sessions": self.total_sessions,
            },
            "universe": {
                "requested": self.universe,
                "tested": self.tested_symbols,
                "coverage": {k: _serialize(v) for k, v in self.coverage.items()},
            },
            "per_symbol_metrics": [_serialize(m) for m in self.per_symbol_metrics],
            "aggregate_trade_stats": _serialize(self.aggregate_trade_stats),
            "symbol_distribution": _serialize(self.symbol_distribution),
            "slippage_sensitivity": self.slippage_sensitivity,
            "market_context": _serialize(self.market_context) if self.market_context else None,
            "execution_config": {
                "slippage_bps": self.execution_config.slippage_bps,
                "commission_per_share": self.execution_config.commission_per_share,
                "stop_mode": self.execution_config.stop_mode,
                "target_multiple": self.execution_config.target_multiple,
                "force_exit_time": str(self.execution_config.force_exit_time),
                "same_bar_rule": self.execution_config.same_bar_rule,
            },
            "metadata": self.metadata,
        }
