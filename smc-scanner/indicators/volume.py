"""Volume MA va breakout volume tasdig'i (TZ 10).

Breakout barida hajm (volume) o'rtachadan sezilarli yuqori bo'lishi kerak —
"haqiqiy" breakout institutsional ishtirok bilan keladi. Bu yerda oddiy
current_volume / volume_MA nisbati hisoblanadi va config chegarasi bilan
solishtiriladi.

Lookahead bias YO'Q: rolling mean orqaga qaragan (compute_atr bilan bir xil
shakl), birinchi `period-1` bar NaN.
"""

from __future__ import annotations

import pandas as pd

from config.settings import VOLUME_BREAKOUT_RATIO, VOLUME_MA_PERIOD


def compute_volume_ma(df: pd.DataFrame, *, period: int = VOLUME_MA_PERIOD) -> pd.Series:
    """'volume' ustunining `period`-davrli sodda rolling mean'i (nomi 'volume_ma').

    `min_periods=period` — birinchi `period-1` bar NaN (yetarli tarix yo'q).
    """
    return (
        df["volume"]
        .rolling(window=period, min_periods=period)
        .mean()
        .rename("volume_ma")
    )


def volume_ratio(df: pd.DataFrame, *, period: int = VOLUME_MA_PERIOD) -> pd.Series:
    """current_volume / volume_ma (nomi 'volume_ratio'). Warmup barlarda NaN.

    volume_ma == 0 bo'lgan chekka holatda natija inf/NaN bo'ladi — chaqiruvchi
    (is_volume_confirmed) NaN va cheksizlikni "tasdiqlanmagan" deb qabul qiladi.
    """
    ma = compute_volume_ma(df, period=period)
    return (df["volume"] / ma).rename("volume_ratio")


def is_volume_confirmed(
    df: pd.DataFrame,
    index_pos: int,
    *,
    period: int = VOLUME_MA_PERIOD,
    threshold: float = VOLUME_BREAKOUT_RATIO,
) -> bool:
    """`index_pos` barida volume_ratio >= threshold bo'lsa True.

    Chegaradan tashqari indeks yoki NaN/inf nisbat -> False (yetarli data yo'q =
    tasdiq yo'q, TZ 23).
    """
    if index_pos < 0 or index_pos >= len(df):
        return False
    ratio = volume_ratio(df, period=period).iloc[index_pos]
    if pd.isna(ratio) or ratio == float("inf"):
        return False
    return bool(ratio >= threshold)
