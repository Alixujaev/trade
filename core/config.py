from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class IndicatorConfig:
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    ema_fast: int = 50
    ema_slow: int = 200


@dataclass
class BacktestConfig:
    initial_capital: float = 10000
    position_fraction: float = 0.95
    commission_bps: float = 5
    slippage_bps: float = 3


@dataclass
class AppConfig:
    interval: str = "1d"
    lookback_days: int = 400
    state_file: str = "state.json"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

    @classmethod
    def from_env(cls) -> AppConfig:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        return cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
        )
