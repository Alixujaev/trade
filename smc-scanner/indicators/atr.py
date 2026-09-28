"""Average True Range (ATR) indikatori.

Sodda ATR — True Range'ning rolling mean'i (Wilder smoothing EMAS).
Timeframe-agnostic: kunlik, haftalik, 1h, 15m, 5m va boshqa barcha barlarda bir xil ishlaydi.
Lookahead bias YO'Q: har bar faqat o'ziga va o'tmish barlarga tayanadi (birinchi period-1 bar NaN).
"""

from __future__ import annotations

import pandas as pd

from config.settings import ATR_PERIOD


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Sodda ATR — True Range'ning rolling mean'i.

    Birinchi `period-1` bar uchun NaN (yetarli tarix yo'q — sun'iy to'ldirilmaydi).
    """
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean().rename("atr")
