"""Intraday barlarning yopilganligini (completion) tekshirish va filtrlash moduli.

No-lookahead qoidasi:
Daqiqa davomida shakllanayotgan (incomplete / forming) shamcha signallarni buzmasligi
uchun, strategiya qatlami `closed_only=True` bilan faqat yopilgan barlarni talab qiladi.

Barning yopilish vaqti:
Bar timestamp'i barning OCHILISH vaqti (open time) deb hisoblanadi.
Bar davomiyligi: interval_delta (masalan 5m uchun 5 daqiqa).
Bar to'liq yopiladigan vaqt = bar_timestamp + interval_delta.
Agar as_of vaqti (yoki joriy vaqt) < bar_timestamp + interval_delta bo'lsa,
bu bar hali tugallanmagan (forming) deb hisoblanadi va filtrlanadi.

Tarixiy backtest'lar uchun:
Agar ma'lumotlar o'tmishga tegishli bo'lsa (bar_end <= as_of), hech qanday bar
tasodifan o'chirib yuborilmaydi.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

_INTERVAL_DELTAS: dict[str, pd.Timedelta] = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
    "1wk": pd.Timedelta(weeks=1),
}


def get_interval_timedelta(interval: str) -> pd.Timedelta:
    """Interval stringidan pd.Timedelta qaytaradi."""
    if interval not in _INTERVAL_DELTAS:
        raise ValueError(f"Noma'lum interval: {interval!r}. Mavjudlar: {sorted(_INTERVAL_DELTAS)}")
    return _INTERVAL_DELTAS[interval]


def filter_closed_bars(
    df: pd.DataFrame,
    interval: str,
    *,
    as_of: datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Faqat as_of vaqtida to'liq yopilgan (completed) barlarni qoldiradi.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV ma'lumotlari (tz-aware DatetimeIndex bilan).
    interval : str
        Bar intervali (masalan '5m', '15m', '1h', '1d').
    as_of : datetime | pd.Timestamp | None, optional
        Ma'lumot tekshirilayotgan vaqt nuqtasi. None bo'lsa, joriy UTC vaqti olinadi.

    Returns
    -------
    pd.DataFrame
        Faqat to'liq yopilgan barlardan iborat DataFrame nusxasi.
    """
    if df.empty:
        return df.copy()

    delta = get_interval_timedelta(interval)

    # as_of vaqtini UTC ga normallashtirish
    if as_of is None:
        ref_time = datetime.now(timezone.utc)
    else:
        if isinstance(as_of, pd.Timestamp):
            ref_time = (
                as_of.tz_convert("UTC")
                if as_of.tz is not None
                else as_of.tz_localize("UTC")
            )
        else:
            ref_time = (
                as_of.astimezone(timezone.utc)
                if as_of.tzinfo is not None
                else as_of.replace(tzinfo=timezone.utc)
            )

    idx_utc = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    bar_end_times = idx_utc + delta

    is_closed = bar_end_times <= pd.Timestamp(ref_time)
    return df.loc[is_closed].copy()
