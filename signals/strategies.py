from __future__ import annotations

import pandas as pd

from core.config import IndicatorConfig
from indicators.indicators import crossover, crossunder, ema, macd, rsi
from signals.base import Strategy, _hold_between


class RsiStrategy(Strategy):
    def __init__(self, cfg: IndicatorConfig | None = None) -> None:
        self.cfg = cfg or IndicatorConfig()
        self.name = (
            f"RSI({self.cfg.rsi_period},{self.cfg.rsi_oversold},{self.cfg.rsi_overbought})"
        )

    def target_position(self, df: pd.DataFrame) -> pd.Series:
        r = rsi(df["close"], period=self.cfg.rsi_period)
        oversold = pd.Series(self.cfg.rsi_oversold, index=df.index)
        overbought = pd.Series(self.cfg.rsi_overbought, index=df.index)
        entries = crossover(r, oversold)
        exits = crossunder(r, overbought)
        return _hold_between(entries, exits)


class MacdStrategy(Strategy):
    def __init__(self, cfg: IndicatorConfig | None = None) -> None:
        self.cfg = cfg or IndicatorConfig()
        self.name = f"MACD({self.cfg.macd_fast},{self.cfg.macd_slow},{self.cfg.macd_signal})"

    def target_position(self, df: pd.DataFrame) -> pd.Series:
        macd_df = macd(
            df["close"],
            fast=self.cfg.macd_fast,
            slow=self.cfg.macd_slow,
            signal=self.cfg.macd_signal,
        )
        return (macd_df["macd"] > macd_df["signal"]).astype(int)


class EmaCrossStrategy(Strategy):
    def __init__(self, cfg: IndicatorConfig | None = None) -> None:
        self.cfg = cfg or IndicatorConfig()
        self.name = f"EMACross({self.cfg.ema_fast},{self.cfg.ema_slow})"

    def target_position(self, df: pd.DataFrame) -> pd.Series:
        fast = ema(df["close"], self.cfg.ema_fast)
        slow = ema(df["close"], self.cfg.ema_slow)
        return (fast > slow).astype(int)


class CombinedStrategy(Strategy):
    _MODES = ("all", "any", "majority")

    def __init__(self, strategies: list[Strategy], mode: str = "all") -> None:
        if mode not in self._MODES:
            raise ValueError(f"unknown mode: {mode!r}, expected one of {self._MODES}")
        self.strategies = strategies
        self.mode = mode
        members = "+".join(s.name for s in strategies)
        self.name = f"Combined[{mode}]({members})"

    def target_position(self, df: pd.DataFrame) -> pd.Series:
        positions = pd.concat([s.target_position(df) for s in self.strategies], axis=1)
        votes = positions.sum(axis=1)
        if self.mode == "all":
            result = votes == len(self.strategies)
        elif self.mode == "any":
            result = votes > 0
        else:  # majority
            result = votes > len(self.strategies) / 2
        return result.astype(int)
