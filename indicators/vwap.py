"""Session-based Volume Weighted Average Price (VWAP) indikatori.

Kurs formulasi:
Typical Price:
    TP = (High + Low + Close) / 3
VWAP:
    VWAP = cumulative(TP * Volume) / cumulative(Volume)

Qoidalar:
1. RTH sessiyasi boshlanishida (09:30 ET) har bir kun uchun nolga (reset) tushadi.
2. Premarket ma'lumotlari RTH VWAP hisobiga aralashmaydi (rth_only=True bo'lganda).
3. Har bir savdo kuni mustaqil kumulyativ hisobga ega (o'tmish kunlar bugungisiga ta'sir qilmaydi).
4. No-lookahead: kelajak barlar joriy VWAP ga mutlaqo ta'sir qilmaydi (faqat o'tmish va joriy barlar).
5. Zero-volume: kumulyativ hajm 0 bo'lganda ZeroDivisionError oldi olinadi (NaN qaytadi),
   birinchi savdodan keyin 0-hajmli bar kelsa avvalgi VWAP qiymati saqlanadi.
6. Input DataFrame o'zgartirilmaydi (pure function).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.session import get_session_dates, is_rth_series


def compute_vwap(
    df: pd.DataFrame,
    *,
    rth_only: bool = True,
) -> pd.Series:
    """Session-based VWAP seriyasini qaytaradi (indeks df.index bilan bir xil, nomi 'vwap').

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV ma'lumotlari: 'high', 'low', 'close', 'volume' ustunlari va
        tz-aware DatetimeIndex.
    rth_only : bool, optional
        True bo'lsa (standart), faqat RTH (09:30–16:00 ET) barlari hisobga olinadi
        va premarket barlari uchun VWAP NaN bo'ladi. False bo'lsa, butun sessiya
        (premarket bilan birga) jamlanadi.

    Returns
    -------
    pd.Series
        VWAP qiymatlari seriyasi.
    """
    if df.empty:
        return pd.Series(dtype=float, index=df.index, name="vwap")

    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].astype(float)
    tp_vol = tp * vol

    session_dates = get_session_dates(df.index)
    result = pd.Series(np.nan, index=df.index, dtype=float, name="vwap")

    if rth_only:
        rth_mask = is_rth_series(df.index)
        valid_mask = rth_mask
    else:
        valid_mask = pd.Series(True, index=df.index)

    # Har bir savdo kuni (session_date) bo'yicha alohida, mustaqil kumulyativ hisoblash
    for session_date in session_dates.unique():
        day_filter = (session_dates == session_date) & valid_mask
        if not day_filter.any():
            continue

        day_vol = vol.loc[day_filter]
        day_tp_vol = tp_vol.loc[day_filter]

        cum_vol = day_vol.cumsum()
        cum_tp_vol = day_tp_vol.cumsum()

        # ZeroDivisionError oldini olish:
        # cum_vol == 0 bo'lganda (savdo bo'lmagan) NaN, aks holda cum_tp_vol / cum_vol
        day_vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, np.nan)
        result.loc[day_filter] = day_vwap

    return result


def compute_vwap_distance(
    df: pd.DataFrame,
    vwap: pd.Series | None = None,
    *,
    rth_only: bool = True,
) -> pd.Series:
    """Close narxining VWAP'dan foiz/ulush masofasi: (Close - VWAP) / VWAP.

    Musbat qiymat -> narx VWAP ustida.
    Manfiy qiymat -> narx VWAP ostida.
    VWAP NaN yoki 0 bo'lsa -> NaN.
    """
    if vwap is None:
        vwap = compute_vwap(df, rth_only=rth_only)

    valid = vwap.notna() & (vwap > 0)
    distance = pd.Series(np.nan, index=df.index, dtype=float, name="vwap_distance")
    distance.loc[valid] = (df.loc[valid, "close"] - vwap.loc[valid]) / vwap.loc[valid]
    return distance


def compute_vwap_distance_atr(
    df: pd.DataFrame,
    atr: pd.Series,
    vwap: pd.Series | None = None,
    *,
    rth_only: bool = True,
) -> pd.Series:
    """Close narxining VWAP'dan ATR birligidagi masofasi: (Close - VWAP) / ATR.

    Albatta alohida hisoblanadi (aralashtirilmagan).
    ATR NaN yoki <=0 bo'lsa -> NaN.
    """
    if vwap is None:
        vwap = compute_vwap(df, rth_only=rth_only)

    valid = vwap.notna() & atr.notna() & (atr > 0)
    distance_atr = pd.Series(np.nan, index=df.index, dtype=float, name="vwap_distance_atr")
    distance_atr.loc[valid] = (df.loc[valid, "close"] - vwap.loc[valid]) / atr.loc[valid]
    return distance_atr


def compute_vwap_slope(
    vwap: pd.Series,
    period: int = 5,
    *,
    dt_index: pd.DatetimeIndex | None = None,
) -> pd.Series:
    """VWAP nishabligi / delta o'zgarishi: (VWAP[t] - VWAP[t-period]) / period.

    Deterministik: faqat o'tmish va joriy barlar bilan hisoblanadi.
    MUHIM (no-cross-session): agar dt_index yoki vwap.index DatetimeIndex bo'lsa,
    sessiya chegarasidan o'tilganda kechagi kunning oxirgi VWAP'i bilan bugungi
    boshlang'ich VWAP solishtirilmaydi (har kun boshida birinchi period bar NaN bo'ladi).
    """
    name = f"vwap_slope_{period}"
    idx = dt_index if dt_index is not None else vwap.index

    if not isinstance(idx, pd.DatetimeIndex) or len(vwap) == 0:
        # Oddiy rolling diff
        slope = (vwap - vwap.shift(period)) / period
        return slope.rename(name)

    session_dates = get_session_dates(idx)
    result = pd.Series(np.nan, index=vwap.index, dtype=float, name=name)

    for session_date in session_dates.unique():
        mask = session_dates == session_date
        day_vwap = vwap.loc[mask]
        day_slope = (day_vwap - day_vwap.shift(period)) / period
        result.loc[mask] = day_slope

    return result
