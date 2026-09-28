"""Wilder's RSI (Relative Strength Index) indikatori.

Course DAY-01 konsepti uchun:
- Standart davr: 14 (RSI(14))
- Wilder smoothing (exponential moving average with alpha = 1 / period)
- RSI > 50: Bullish momentum confirmation context
- RSI < 50: Bearish / non-bullish momentum context

Lookahead bias yo'q: Har bir bar faqat o'sha paytgacha bo'lgan narxlar asosida
hisoblanadi.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_rsi(
    df: pd.DataFrame,
    period: int = 14,
    *,
    column: str = "close",
) -> pd.Series:
    """Wilder's smoothing usuli bilan RSI hisoblaydi.

    Args:
        df: Narxlar jadvali (kamida `column` ustuni bo'lishi kerak).
        period: RSI hisoblash davri (default 14).
        column: Narx ustuni nomi (default "close").

    Returns:
        pd.Series: float64 turidagi RSI qiymatlari, 0 dan 100 gacha.
        Dastlabki `period` ta qator NaN bo'ladi.
    """
    if period <= 0:
        raise ValueError(f"period musbat bo'lishi kerak, berildi: {period}")

    n = len(df)
    result = np.full(n, np.nan, dtype=np.float64)

    if n <= period or column not in df.columns:
        return pd.Series(result, index=df.index, name="rsi", dtype=np.float64)

    values = df[column].to_numpy(dtype=np.float64)
    deltas = np.diff(values)  # length n - 1

    gains = np.where(deltas > 0.0, deltas, 0.0)
    losses = np.where(deltas < 0.0, -deltas, 0.0)

    # Dastlabki `period` ta o'zgarishning oddiy o'rtachasi (SMA)
    # deltas[0:period] bular 0 dan period-1 gacha bo'lgan o'zgarishlar,
    # ular 1 dan period gacha bo'lgan barlarni o'z ichiga oladi (index: period).
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    # Birinchi RSI qiymati index = period da paydo bo'ladi
    if avg_loss == 0.0:
        result[period] = 100.0 if avg_gain > 0.0 else 50.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder smoothing keyingi barlar uchun:
    # avg = (avg_prev * (period - 1) + current) / period
    for i in range(period + 1, n):
        gain = gains[i - 1]
        loss = losses[i - 1]

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0.0:
            result[i] = 100.0 if avg_gain > 0.0 else 50.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return pd.Series(result, index=df.index, name="rsi", dtype=np.float64)
