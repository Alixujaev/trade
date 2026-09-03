"""Trend rejimi engine — EMA 20/50/200 bozor filtri (TZ 5).

Bullish regime: Price > EMA200 AND EMA20 > EMA50 AND EMA50 > EMA200.
Bearish regime: teskarisi (Price < EMA200 AND EMA20 < EMA50 AND EMA50 < EMA200).
Boshqa hamma holat (jumladan warmup) -> NEUTRAL.

Trend — market FILTR, yakuniy signal emas: breakout+retest setup faqat bullish
(yoki `require_trend=False` bo'lsa har qanday) rejimda qabul qilinadi.

Lookahead bias YO'Q: har EMA orqaga qaragan (indicators/ema.py), NaN bilan
solishtiruv doim False -> warmup barlar avtomatik NEUTRAL.
"""

from __future__ import annotations

import pandas as pd

from config.settings import EMA_FAST_PERIOD, EMA_MID_PERIOD, EMA_SLOW_PERIOD
from indicators.ema import compute_ema_frame
from strategy.types import TrendRegime


def compute_trend_regime(
    df: pd.DataFrame,
    *,
    fast: int = EMA_FAST_PERIOD,
    mid: int = EMA_MID_PERIOD,
    slow: int = EMA_SLOW_PERIOD,
) -> pd.Series:
    """Har bar uchun TrendRegime qiymatli Series (indeks `df` bilan bir xil, nomi 'trend_regime')."""
    frame = compute_ema_frame(df, fast=fast, mid=mid, slow=slow)
    close = df["close"]

    bull = (
        (close > frame["ema_slow"])
        & (frame["ema_fast"] > frame["ema_mid"])
        & (frame["ema_mid"] > frame["ema_slow"])
    )
    bear = (
        (close < frame["ema_slow"])
        & (frame["ema_fast"] < frame["ema_mid"])
        & (frame["ema_mid"] < frame["ema_slow"])
    )

    regime = pd.Series(TrendRegime.NEUTRAL, index=df.index, dtype=object, name="trend_regime")
    regime[bull] = TrendRegime.BULLISH
    regime[bear] = TrendRegime.BEARISH
    return regime


def trend_regime_at(regime: pd.Series, index_pos: int) -> TrendRegime:
    """`regime` Series'idan `index_pos` qiymati; chegaradan tashqari -> NEUTRAL."""
    if index_pos < 0 or index_pos >= len(regime):
        return TrendRegime.NEUTRAL
    return regime.iloc[index_pos]
