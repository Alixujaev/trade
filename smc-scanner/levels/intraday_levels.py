"""Day trading uchun intraday darajalar (intraday levels) moduli.

Qo'llab-quvvatlanadigan darajalar:
- PDH — Previous Day High (o'tgan kunning eng yuqori narxi)
- PDL — Previous Day Low (o'tgan kunning eng past narxi)
- PDC — Previous Day Close (o'tgan kunning yopilish narxi)
- PMH — Premarket High (04:00 <= t < 09:30 ET oralig'idagi eng yuqori narx)
- PML — Premarket Low (04:00 <= t < 09:30 ET oralig'idagi eng past narx)
- ORH — Opening Range High (standart: 09:30–09:45 ET oralig'idagi eng yuqori narx)
- ORL — Opening Range Low (standart: 09:30–09:45 ET oralig'idagi eng past narx)
- HOD — High of Day (sessiya boshidan joriy vaqtgacha kengayuvchi / expanding high)
- LOD — Low of Day (sessiya boshidan joriy vaqtgacha kengayuvchi / expanding low)

Qat'iy No-Lookahead qoidalari:
1. PDH / PDL / PDC FAQAT oxirgi yopilgan (D-1) savdo kunidan olinadi. Bugungi kunning
   rivojlanayotgan barlari hech qachon PDH/PDL ga ta'sir qilmaydi.
2. PMH / PML faqat 04:00 <= t < 09:30 ET barlaridan tuziladi. 09:30+ barlari
   premarket darajalarini o'zgartira olmaydi. Premarket data bo'lmasa -> None/NaN.
3. ORH / ORL ochilish diapazoni (09:45) tugaguncha NOANIQ (NaN bo'ladi). Faqat 09:45
   va undan keyin kuchga kiradi va kundan keyingi barlar tomonidan o'zgartirilmaydi.
4. HOD / LOD strictly expanding: HOD(t) = max(high[start:t]). Kelajak bar o'tmishdagi
   HOD/LOD qiymatini hech qachon o'zgartirmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from data.session import (
    RTH_START,
    get_session_dates,
    is_premarket_series,
    is_rth_series,
    to_eastern,
)

DEFAULT_OR_START: time = time(9, 30)
DEFAULT_OR_END: time = time(9, 45)


@dataclass(frozen=True)
class IntradayLevels:
    """Bitta vaqt nuqtasi yoki sessiya uchun intraday level qiymatlari (immutable)."""

    session_date: date
    pdh: float | None = None
    pdl: float | None = None
    pdc: float | None = None
    pmh: float | None = None
    pml: float | None = None
    orh: float | None = None
    orl: float | None = None
    hod: float | None = None
    lod: float | None = None


def compute_previous_day_levels(
    df: pd.DataFrame,
    *,
    rth_only: bool = True,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Har bir bar uchun o'tgan tugallangan savdo kuni (D-1) ning PDH, PDL, PDC seriyalarini qaytaradi.

    No-lookahead kafolati:
    - Savdo kuni D dagi barcha barlar uchun PDH/PDL/PDC qat'iy ravishda D-1 kuni barlaridan olinadi.
    - D kunidagi barcha barlarda PDH/PDL/PDC o'zgarmas (konstanta) bo'lib qoladi.
    - Agar D birinchi savdo kuni bo'lsa (D-1 yo'q) -> NaN.
    """
    pdh = pd.Series(np.nan, index=df.index, dtype=float, name="pdh")
    pdl = pd.Series(np.nan, index=df.index, dtype=float, name="pdl")
    pdc = pd.Series(np.nan, index=df.index, dtype=float, name="pdc")

    if df.empty:
        return pdh, pdl, pdc

    session_dates = get_session_dates(df.index)
    unique_dates = list(dict.fromkeys(session_dates))  # tartib saqlangan noyob sanalar

    if rth_only:
        rth_mask = is_rth_series(df.index)
    else:
        rth_mask = pd.Series(True, index=df.index)

    for i in range(1, len(unique_dates)):
        prev_date = unique_dates[i - 1]
        curr_date = unique_dates[i]

        prev_mask = (session_dates == prev_date) & rth_mask
        if not prev_mask.any():
            # Agar RTH barlari topilmasa, sessiyaning istalgan barini olishga fallback
            prev_mask = session_dates == prev_date

        if not prev_mask.any():
            continue

        prev_bars = df.loc[prev_mask]
        day_pdh = float(prev_bars["high"].max())
        day_pdl = float(prev_bars["low"].min())
        day_pdc = float(prev_bars["close"].iloc[-1])

        curr_mask = session_dates == curr_date
        pdh.loc[curr_mask] = day_pdh
        pdl.loc[curr_mask] = day_pdl
        pdc.loc[curr_mask] = day_pdc

    return pdh, pdl, pdc


def compute_premarket_levels(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Har bir bar uchun PMH (Premarket High) va PML (Premarket Low) seriyalarini qaytaradi.

    Qoidalar:
    - Faqat 04:00 <= t < 09:30 ET oralig'idagi barlar premarket hisoblanadi.
    - Premarket davomida (t < 09:30) PMH va PML joriy vaqtgacha kengayuvchi (expanding) bo'ladi.
    - 09:30 da premarket yopiladi: RTH (t >= 09:30) barlari uchun premarketning YAKUNIY
      (to'liq) High va Low qiymati muzlatiladi (freeze).
    - 09:30+ barlari premarket darajalarini HECH QACHON o'zgartira olmaydi.
    - Premarket ma'lumoti yo'q kunlar uchun -> NaN.
    """
    pmh = pd.Series(np.nan, index=df.index, dtype=float, name="pmh")
    pml = pd.Series(np.nan, index=df.index, dtype=float, name="pml")

    if df.empty:
        return pmh, pml

    session_dates = get_session_dates(df.index)
    prem_mask = is_premarket_series(df.index)
    index_et = to_eastern(df.index)
    times = pd.Series(index_et.time, index=df.index)  # type: ignore[union-attr]

    for session_date in session_dates.unique():
        day_mask = session_dates == session_date
        day_prem_mask = day_mask & prem_mask

        if not day_prem_mask.any():
            continue  # Premarket ma'lumoti yo'q

        prem_highs = df.loc[day_prem_mask, "high"]
        prem_lows = df.loc[day_prem_mask, "low"]

        # Premarket ichida expanding
        pmh.loc[day_prem_mask] = prem_highs.expanding().max().values
        pml.loc[day_prem_mask] = prem_lows.expanding().min().values

        # Yakuniy premarket darajalari
        final_pmh = float(prem_highs.max())
        final_pml = float(prem_lows.min())

        # 09:30 va undan keyingi barlarga muzlatilgan yakuniy darajani beramiz
        post_prem_mask = day_mask & (times >= RTH_START)
        pmh.loc[post_prem_mask] = final_pmh
        pml.loc[post_prem_mask] = final_pml

    return pmh, pml


def compute_opening_range(
    df: pd.DataFrame,
    *,
    start_time: time = DEFAULT_OR_START,
    end_time: time = DEFAULT_OR_END,
) -> tuple[pd.Series, pd.Series]:
    """Opening Range (ORH, ORL) seriyalarini qaytaradi (standart 09:30–09:45 ET).

    Qoidalar:
    - Ochilish diapazoni tugaguniga qadar (t < end_time) ORH va ORL NOANIQ (NaN).
    - Diapazon tugagach (t >= end_time), [start_time, end_time) oralig'idagi barlarning
      High va Low qiymatlari o'zgarmas daraja sifatida belgilanadi.
    - 09:45 dan keyingi barlar ORH/ORL ni o'zgartirmaydi.
    - Kelajak barlar ko'rinmaydi (no-lookahead).
    """
    orh = pd.Series(np.nan, index=df.index, dtype=float, name="orh")
    orl = pd.Series(np.nan, index=df.index, dtype=float, name="orl")

    if df.empty:
        return orh, orl

    session_dates = get_session_dates(df.index)
    index_et = to_eastern(df.index)
    times = pd.Series(index_et.time, index=df.index)  # type: ignore[union-attr]

    for session_date in session_dates.unique():
        day_mask = session_dates == session_date

        # Opening range darchasi: start_time <= t < end_time
        or_mask = day_mask & (times >= start_time) & (times < end_time)
        if not or_mask.any():
            continue

        final_orh = float(df.loc[or_mask, "high"].max())
        final_orl = float(df.loc[or_mask, "low"].min())

        # FAQAT end_time va undan keyingi barlarda mavjud
        available_mask = day_mask & (times >= end_time)
        orh.loc[available_mask] = final_orh
        orl.loc[available_mask] = final_orl

    return orh, orl


def compute_expanding_hod_lod(
    df: pd.DataFrame,
    *,
    rth_only: bool = True,
) -> tuple[pd.Series, pd.Series]:
    """Sessiya bo'ylab expanding HOD (High of Day) va LOD (Low of Day) seriyalarini qaytaradi.

    HOD(t) = max(high[start:t])
    LOD(t) = min(low[start:t])

    No-lookahead: kelajakdagi t+k barlari t vaqtidagi HOD/LOD ga mutlaqo ta'sir qilmaydi.
    """
    hod = pd.Series(np.nan, index=df.index, dtype=float, name="hod")
    lod = pd.Series(np.nan, index=df.index, dtype=float, name="lod")

    if df.empty:
        return hod, lod

    session_dates = get_session_dates(df.index)

    if rth_only:
        rth_mask = is_rth_series(df.index)
        valid_mask = rth_mask
    else:
        valid_mask = pd.Series(True, index=df.index)

    for session_date in session_dates.unique():
        day_filter = (session_dates == session_date) & valid_mask
        if not day_filter.any():
            continue

        day_highs = df.loc[day_filter, "high"]
        day_lows = df.loc[day_filter, "low"]

        hod.loc[day_filter] = day_highs.expanding().max().values
        lod.loc[day_filter] = day_lows.expanding().min().values

    return hod, lod


def compute_intraday_levels(
    df: pd.DataFrame,
    *,
    or_start: time = DEFAULT_OR_START,
    or_end: time = DEFAULT_OR_END,
    rth_only: bool = True,
) -> pd.DataFrame:
    """Barcha intraday darajalarni bitta to'liq DataFrame'ga jamlab qaytaradi.

    Ustunlar: ['pdh', 'pdl', 'pdc', 'pmh', 'pml', 'orh', 'orl', 'hod', 'lod']
    Barchasi df.index bilan moslashgan.
    """
    pdh, pdl, pdc = compute_previous_day_levels(df, rth_only=rth_only)
    pmh, pml = compute_premarket_levels(df)
    orh, orl = compute_opening_range(df, start_time=or_start, end_time=or_end)
    hod, lod = compute_expanding_hod_lod(df, rth_only=rth_only)

    return pd.DataFrame(
        {
            "pdh": pdh,
            "pdl": pdl,
            "pdc": pdc,
            "pmh": pmh,
            "pml": pml,
            "orh": orh,
            "orl": orl,
            "hod": hod,
            "lod": lod,
        },
        index=df.index,
    )
