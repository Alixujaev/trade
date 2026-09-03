"""EMA (Exponential Moving Average) — trend rejimi filtri uchun (TZ 5).

Lookahead bias YO'Q: `adjust=False` rekursiv EMA — har bar qiymati faqat o'sha
bardagi va undan OLDINGI yopilish narxlariga bog'liq (kelajak barlar ta'sir
qilmaydi). Birinchi `period-1` bar uchun NaN (yetarli tarix yo'q — sun'iy
to'ldirilmaydi, compute_atr konvensiyasi bilan bir xil).
"""

from __future__ import annotations

import pandas as pd

from config.settings import EMA_FAST_PERIOD, EMA_MID_PERIOD, EMA_SLOW_PERIOD


def compute_ema(df: pd.DataFrame, period: int, *, column: str = "close") -> pd.Series:
    """`column` ustunidan `period`-davrli rekursiv EMA (Series nomi f"ema{period}").

    `span=period`, `adjust=False` — standart TradingView-uslubidagi EMA:
    EMA[i] = alpha*x[i] + (1-alpha)*EMA[i-1],  alpha = 2/(period+1).
    `min_periods=period` — birinchi `period-1` bar NaN bo'ladi (bu keyingi
    barlardagi qiymatni O'ZGARTIRMAYDI — faqat maskalanadi), shuning uchun
    kelajak barlarni kesish har saqlangan bar uchun qiymatni saqlaydi.
    """
    return (
        df[column]
        .ewm(span=period, adjust=False, min_periods=period)
        .mean()
        .rename(f"ema{period}")
    )


def compute_ema_frame(
    df: pd.DataFrame,
    *,
    fast: int = EMA_FAST_PERIOD,
    mid: int = EMA_MID_PERIOD,
    slow: int = EMA_SLOW_PERIOD,
    column: str = "close",
) -> pd.DataFrame:
    """Uchta EMA'ni bitta DataFrame'da qaytaradi (ustunlar: ema_fast, ema_mid, ema_slow).

    Indeks `df` bilan bir xil. Har ustun mustaqil compute_ema natijasi —
    warmup NaN'lar har ustunda o'z period'iga qarab turlicha bo'ladi.
    """
    return pd.DataFrame(
        {
            "ema_fast": compute_ema(df, fast, column=column),
            "ema_mid": compute_ema(df, mid, column=column),
            "ema_slow": compute_ema(df, slow, column=column),
        },
        index=df.index,
    )
