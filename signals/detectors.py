from __future__ import annotations

import pandas as pd

from core.config import IndicatorConfig
from indicators.indicators import atr, ema


def bullish_sweep(df: pd.DataFrame, lookback: int = 20, reclaim_frac: float = 0.5) -> bool:
    if len(df) < lookback + 1:
        return False

    prior = df.iloc[-(lookback + 1):-1]
    last = df.iloc[-1]
    prior_low = float(prior["low"].min())
    last_low = float(last["low"])
    last_high = float(last["high"])
    last_close = float(last["close"])

    if not (last_low < prior_low):
        return False
    if not (last_close > prior_low):
        return False

    bar_range = last_high - last_low
    if bar_range <= 0:
        return False

    recovery = (last_close - last_low) / bar_range
    return bool(recovery >= reclaim_frac)


def bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False

    prior = df.iloc[-2]
    last = df.iloc[-1]

    prior_bearish = prior["close"] < prior["open"]
    last_bullish = last["close"] > last["open"]
    if not (prior_bearish and last_bullish):
        return False

    prior_body_low = min(prior["open"], prior["close"])
    prior_body_high = max(prior["open"], prior["close"])
    last_body_low = min(last["open"], last["close"])
    last_body_high = max(last["open"], last["close"])

    engulfs = last_body_low <= prior_body_low and last_body_high >= prior_body_high
    return bool(engulfs)


def bullish_pin(df: pd.DataFrame, wick_frac: float = 0.6) -> bool:
    if len(df) < 1:
        return False

    last = df.iloc[-1]
    bar_range = float(last["high"] - last["low"])
    if bar_range <= 0:
        return False

    body = abs(float(last["close"] - last["open"]))
    lower_wick = float(min(last["open"], last["close"]) - last["low"])

    wick_ok = (lower_wick / bar_range) >= wick_frac
    body_ok = (body / bar_range) <= 0.3
    return bool(wick_ok and body_ok)


def uptrend(df: pd.DataFrame, cfg: IndicatorConfig) -> bool:
    fast = ema(df["close"], cfg.ema_fast)
    slow = ema(df["close"], cfg.ema_slow)
    if pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]):
        return False
    return bool(fast.iloc[-1] > slow.iloc[-1])


def near_fvg(df: pd.DataFrame, atr_frac: float = 0.3, lookback: int = 10) -> bool:
    if len(df) < 3:
        return False

    atr_series = atr(df, period=14)
    current_price = float(df["close"].iloc[-1])
    start = max(2, len(df) - lookback)

    for i in range(start, len(df)):
        gap_low = float(df["high"].iloc[i - 2])
        gap_high = float(df["low"].iloc[i])
        gap_size = gap_high - gap_low
        if gap_size <= 0:
            continue

        atr_i = atr_series.iloc[i]
        if pd.isna(atr_i) or gap_size <= atr_frac * atr_i:
            continue

        if gap_low <= current_price <= gap_high:
            return True

    return False


_ROUND_NUMBER_UNIT = 5.0


def near_round_number(df: pd.DataFrame, tol_frac: float = 0.01) -> bool:
    if len(df) < 1:
        return False

    price = float(df["close"].iloc[-1])
    nearest = round(price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT
    tol = tol_frac * price
    return bool(abs(price - nearest) <= tol)
