from __future__ import annotations

import pandas as pd


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
