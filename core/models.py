from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class Action(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Signal:
    symbol: str
    timestamp: object
    target_position: int
    action: Action
    reason: str
    price: float | None
    formatted_text: str | None = None
    reply_markup: dict | None = None


@dataclass
class Trade:
    symbol: str
    entry_time: object
    exit_time: object
    entry_price: float
    exit_price: float
    shares: float
    commission: float

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commission

    @property
    def return_pct(self) -> float:
        return (self.exit_price - self.entry_price) / self.entry_price * 100


@dataclass
class BacktestResult:
    symbol: str
    equity_curve: pd.Series
    trades: list[Trade]
    initial_capital: float
