"""Time-of-day Relative Volume (RVOL) indikatori.

Kurs konseptsiyasi:
RVOL(T) = bugungi T vaqtidagi hajm / o'tgan tugallangan sessiyalarning aynan shu T vaqtidagi o'rtacha hajmi.

Qoidalar:
1. Vaqt bo'yicha moslik (same time-of-day alignment):
   Bugungi 09:35 hajmi o'tgan kunlarning aynan 09:35 dagi hajmlari bilan solishtiriladi
   (oddiy rolling MA emas).
2. Faqat o'tgan, to'liq yopilgan sessiyalar:
   Joriy sessiyaning hech bir bari (hatto 09:30 bari ham) o'zining baseline'iga kirmaydi.
   Shift(1) sessiya darajasida qo'llanadi.
3. Kelajak barlardan xoli (no-lookahead):
   Kelajak sessiyalar va joriy kunning kelajak barlari mutlaqo ko'rinmaydi.
4. Dam olish va bayram kunlari:
   Bozor yopiq kunlar sessiya hisoblanmaydi — faqat real ma'lumotga ega savdo kunlari
   (trading sessions) ketma-ketligi olinadi.
5. Deterministik minimum chegara:
   Agar o'tmishda yetarli sessiya (min_sessions) bo'lmasa -> NaN.
   Sun'iy hajm to'qib chiqarilmaydi.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.session import get_session_dates, to_eastern

DEFAULT_RVOL_LOOKBACK_SESSIONS: int = 20


def compute_rvol(
    df: pd.DataFrame,
    *,
    lookback_sessions: int = DEFAULT_RVOL_LOOKBACK_SESSIONS,
    min_sessions: int | None = None,
) -> pd.Series:
    """Intraday barlar uchun Time-of-day Relative Volume (RVOL) seriyasini hisoblaydi.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV ma'lumotlari: kamida 'volume' ustuni va tz-aware DatetimeIndex.
    lookback_sessions : int, optional
        Baseline uchun olinadigan o'tgan savdo sessiyalari soni (standart: 20).
    min_sessions : int | None, optional
        Hisoblash uchun minimal talab qilinadigan o'tgan sessiyalar soni.
        None bo'lsa, lookback_sessions bilan bir xil bo'ladi.

    Returns
    -------
    pd.Series
        RVOL qiymatlari seriyasi (indeks df.index bilan bir xil, nomi 'rvol').
    """
    if df.empty or "volume" not in df.columns:
        return pd.Series(dtype=float, index=df.index, name="rvol")

    if min_sessions is None:
        min_sessions = lookback_sessions

    session_dates = get_session_dates(df.index)
    index_et = to_eastern(df.index)
    times_of_day = pd.Series(index_et.time, index=df.index)  # type: ignore[union-attr]

    # Vaqtinchalik frame: har bir bar uchun sessiya sanasi, kun vaqti va hajm
    temp = pd.DataFrame(
        {
            "session": session_dates.values,
            "time": times_of_day.values,
            "volume": df["volume"].astype(float).values,
        },
        index=df.index,
    )

    # Dublikat (session, time) bo'lsa oxirgisini saqlaymiz
    temp_dedup = temp.drop_duplicates(subset=["session", "time"], keep="last")

    # Pivot: index = savdo sessiyalari (xronologik), columns = kun vaqti (09:30, 09:35, ...)
    vol_pivot = temp_dedup.pivot(index="session", columns="time", values="volume")

    # Qat'iy No-lookahead:
    # 1. shift(1) — joriy sessiya D o'z baseline'idan butunlay chiqarib tashlanadi;
    # 2. rolling(window, min_periods) — faqat o'tgan tugallangan sessiyalarning o'rtachasi.
    hist_baseline = (
        vol_pivot.shift(1)
        .rolling(window=lookback_sessions, min_periods=min_sessions)
        .mean()
    )

    # 0 ga bo'linishdan himoya
    valid_baseline = hist_baseline.where(hist_baseline > 0, np.nan)
    rvol_pivot = vol_pivot / valid_baseline

    # Pivot'dan df.index tartibidagi asl qatorlarga qaytarish
    # Index bo'yicha tez qidirish uchun unstack
    rvol_lookup = rvol_pivot.unstack()  # Series with MultiIndex (time, session)

    # df satrlariga mos qiymatlarni vektorlashtirilgan tarzda olish
    multi_idx = pd.MultiIndex.from_arrays(
        [temp["time"].values, temp["session"].values], names=["time", "session"]
    )
    rvol_values = rvol_lookup.reindex(multi_idx).values

    return pd.Series(rvol_values, index=df.index, dtype=float, name="rvol")
