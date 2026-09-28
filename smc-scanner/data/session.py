"""US bozor savdo sessiyalari va vaqt zonalari bo'yicha yordamchi modul.

Day trading uchun US/Eastern (America/New_York) vaqti standarti:
- RTH (Regular Trading Hours): 09:30 – 16:00 ET (09:30 kiradi, 16:00 kirmaydi).
- Premarket: 04:00 – 09:30 ET (04:00 kiradi, 09:30 kirmaydi).
- Qat'iy `zoneinfo.ZoneInfo("America/New_York")` ishlatiladi: EDT (UTC-4) va EST (UTC-5)
  mavsumiy o'zgarishlari avtomatik hisobga olinadi, statik UTC ofsetlar ishlatilmaydi.
- Barcha funksiyalar sof (pure), no-lookahead: faqat bar timestamp'iga tayanadi.
"""

from __future__ import annotations

from datetime import date, datetime, time, tzinfo
from zoneinfo import ZoneInfo

import pandas as pd

NY_TZ: ZoneInfo = ZoneInfo("America/New_York")

PREMARKET_START: time = time(4, 0)
RTH_START: time = time(9, 30)
RTH_END: time = time(16, 0)
POSTMARKET_END: time = time(20, 0)


def to_eastern(
    ts: datetime | pd.Timestamp | pd.DatetimeIndex,
    *,
    assume_tz: tzinfo | None = None,
) -> datetime | pd.Timestamp | pd.DatetimeIndex:
    """Timestamp yoki DatetimeIndex'ni US/Eastern (America/New_York) vaqt zonasiga o'tkazadi.

    Tz-aware timestamp'lar to'g'ridan-to'g'ri konvertatsiya qilinadi.
    Tz-naive timestamp'lar xavfli (silent reinterpretation xatolariga olib kelmasligi uchun) —
    agar `assume_tz` berilmagan bo'lsa ValueError chiqariladi.
    """
    if isinstance(ts, pd.DatetimeIndex):
        if ts.tz is None:
            if assume_tz is None:
                raise ValueError(
                    "DatetimeIndex timezone-aware bo'lishi shart (masalan UTC). "
                    "Naive index uchun assume_tz parametrini ko'rsating."
                )
            return ts.tz_localize(assume_tz).tz_convert(NY_TZ)
        return ts.tz_convert(NY_TZ)

    if isinstance(ts, pd.Timestamp):
        if ts.tzinfo is None:
            if assume_tz is None:
                raise ValueError(
                    f"Timestamp {ts!r} timezone-aware bo'lishi shart. "
                    "Naive timestamp uchun assume_tz parametrini ko'rsating."
                )
            return ts.tz_localize(assume_tz).tz_convert(NY_TZ)
        return ts.tz_convert(NY_TZ)

    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            if assume_tz is None:
                raise ValueError(
                    f"datetime {ts!r} timezone-aware bo'lishi shart. "
                    "Naive datetime uchun assume_tz parametrini ko'rsating."
                )
            ts = ts.replace(tzinfo=assume_tz)
        return ts.astimezone(NY_TZ)

    raise TypeError(f"Qo'llab-quvvatlanmaydigan timestamp turi: {type(ts)}")


def get_session_date(
    ts: datetime | pd.Timestamp,
    *,
    assume_tz: tzinfo | None = None,
) -> date:
    """Timestamp tegishli bo'lgan savdo/sessiya sanasini (US/Eastern taqvim sanasi) qaytaradi.

    US birja sessiyalari (premarket, RTH, postmarket) New York kalendar sanasi
    bo'yicha belgilanadi. UTC dagi 20:00+ timestamp New Yorkda o'sha kunning o'zida
    qoladi (masalan 21:00 UTC = 17:00 EDT/16:00 EST).
    """
    ts_et = to_eastern(ts, assume_tz=assume_tz)
    return ts_et.date()  # type: ignore[union-attr]


def get_session_dates(
    dt_index: pd.DatetimeIndex,
    *,
    assume_tz: tzinfo | None = None,
) -> pd.Series:
    """DatetimeIndex barlari uchun har bir satrning savdo sanasini pd.Series sifatida qaytaradi."""
    index_et = to_eastern(dt_index, assume_tz=assume_tz)
    return pd.Series(index_et.date, index=dt_index, name="session_date")  # type: ignore[union-attr]


def is_rth(
    ts: datetime | pd.Timestamp,
    *,
    assume_tz: tzinfo | None = None,
) -> bool:
    """Bar RTH (Regular Trading Hours: 09:30 <= t < 16:00 ET) ga tegishli bo'lsa True.

    Chegaralar:
    - 09:30:00 -> True (birinchi RTH bar)
    - 15:59:59 -> True (oxirgi RTH barlari)
    - 16:00:00 -> False (RTH tugagan)
    - 09:29:59 -> False
    """
    ts_et = to_eastern(ts, assume_tz=assume_tz)
    t = ts_et.time()  # type: ignore[union-attr]
    return RTH_START <= t < RTH_END


def is_rth_series(
    dt_index: pd.DatetimeIndex,
    *,
    assume_tz: tzinfo | None = None,
) -> pd.Series:
    """DatetimeIndex bo'yicha RTH barlarini belgilovchi boolean mask Series qaytaradi."""
    index_et = to_eastern(dt_index, assume_tz=assume_tz)
    times = pd.Series(index_et.time, index=dt_index)  # type: ignore[union-attr]
    return (times >= RTH_START) & (times < RTH_END)


def is_premarket(
    ts: datetime | pd.Timestamp,
    *,
    assume_tz: tzinfo | None = None,
) -> bool:
    """Bar Premarket (04:00 <= t < 09:30 ET) ga tegishli bo'lsa True.

    Chegaralar:
    - 04:00:00 -> True
    - 09:29:59 -> True
    - 09:30:00 -> False (RTH boshlanishi, premarketga kirmaydi)
    - 03:59:59 -> False
    """
    ts_et = to_eastern(ts, assume_tz=assume_tz)
    t = ts_et.time()  # type: ignore[union-attr]
    return PREMARKET_START <= t < RTH_START


def is_premarket_series(
    dt_index: pd.DatetimeIndex,
    *,
    assume_tz: tzinfo | None = None,
) -> pd.Series:
    """DatetimeIndex bo'yicha Premarket barlarini belgilovchi boolean mask Series qaytaradi."""
    index_et = to_eastern(dt_index, assume_tz=assume_tz)
    times = pd.Series(index_et.time, index=dt_index)  # type: ignore[union-attr]
    return (times >= PREMARKET_START) & (times < RTH_START)


def filter_rth(df: pd.DataFrame, *, assume_tz: tzinfo | None = None) -> pd.DataFrame:
    """Faqat RTH (09:30–16:00 ET) barlarini qoldirib, nusxasini qaytaradi."""
    mask = is_rth_series(df.index, assume_tz=assume_tz)
    return df.loc[mask].copy()


def filter_premarket(df: pd.DataFrame, *, assume_tz: tzinfo | None = None) -> pd.DataFrame:
    """Faqat Premarket (04:00–09:30 ET) barlarini qoldirib, nusxasini qaytaradi."""
    mask = is_premarket_series(df.index, assume_tz=assume_tz)
    return df.loc[mask].copy()
