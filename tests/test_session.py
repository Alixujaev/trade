"""data/session.py uchun to'liq testlar to'plami.

Sessiya chegaralari, EDT/EST mavsumiy vaqtlar va timezone konversiyasi sinovi.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from data.session import (
    NY_TZ,
    PREMARKET_START,
    RTH_END,
    RTH_START,
    filter_premarket,
    filter_rth,
    get_session_date,
    get_session_dates,
    is_premarket,
    is_premarket_series,
    is_rth,
    is_rth_series,
    to_eastern,
)


def test_session_boundary_constants() -> None:
    assert PREMARKET_START == time(4, 0)
    assert RTH_START == time(9, 30)
    assert RTH_END == time(16, 0)


def test_is_premarket_boundaries() -> None:
    # 04:00:00 ET -> Premarket boshlanishi
    t_0400 = datetime(2024, 6, 3, 4, 0, 0, tzinfo=NY_TZ)
    assert is_premarket(t_0400) is True

    # 09:29:59 ET -> Premarket
    t_092959 = datetime(2024, 6, 3, 9, 29, 59, tzinfo=NY_TZ)
    assert is_premarket(t_092959) is True

    # 09:30:00 ET -> RTH boshlanishi, premarket EMAS
    t_093000 = datetime(2024, 6, 3, 9, 30, 0, tzinfo=NY_TZ)
    assert is_premarket(t_093000) is False

    # 03:59:59 ET -> Premarketdan oldin
    t_035959 = datetime(2024, 6, 3, 3, 59, 59, tzinfo=NY_TZ)
    assert is_premarket(t_035959) is False


def test_is_rth_boundaries() -> None:
    # 09:29:59 ET -> RTH emas
    t_092959 = datetime(2024, 6, 3, 9, 29, 59, tzinfo=NY_TZ)
    assert is_rth(t_092959) is False

    # 09:30:00 ET -> RTH ga kiradi
    t_093000 = datetime(2024, 6, 3, 9, 30, 0, tzinfo=NY_TZ)
    assert is_rth(t_093000) is True

    # 15:59:59 ET -> RTH
    t_155959 = datetime(2024, 6, 3, 15, 59, 59, tzinfo=NY_TZ)
    assert is_rth(t_155959) is True

    # 16:00:00 ET -> RTH dan tashqarida
    t_160000 = datetime(2024, 6, 3, 16, 0, 0, tzinfo=NY_TZ)
    assert is_rth(t_160000) is False


def test_edt_summer_timezone() -> None:
    # Yoz oylarida (EDT = UTC-4): 13:30 UTC == 09:30 EDT
    utc_dt = datetime(2024, 7, 15, 13, 30, 0, tzinfo=ZoneInfo("UTC"))
    et_dt = to_eastern(utc_dt)
    assert et_dt.hour == 9
    assert et_dt.minute == 30
    assert is_rth(utc_dt) is True


def test_est_winter_timezone() -> None:
    # Qish oylarida (EST = UTC-5): 14:30 UTC == 09:30 EST
    utc_dt = datetime(2024, 1, 15, 14, 30, 0, tzinfo=ZoneInfo("UTC"))
    et_dt = to_eastern(utc_dt)
    assert et_dt.hour == 9
    assert et_dt.minute == 30
    assert is_rth(utc_dt) is True


def test_trading_date_identification() -> None:
    # UTC bo'yicha 2024-07-15 21:00 UTC -> Nyu-Yorkda 17:00 EDT (o'sha kun, 2024-07-15)
    utc_evening = datetime(2024, 7, 15, 21, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert get_session_date(utc_evening) == date(2024, 7, 15)

    # Qishda: 2024-01-16 01:30 UTC -> Nyu-Yorkda 2024-01-15 20:30 EST (oldingi kun sanasi!)
    utc_night = datetime(2024, 1, 16, 1, 30, 0, tzinfo=ZoneInfo("UTC"))
    assert get_session_date(utc_night) == date(2024, 1, 15)


def test_naive_timestamp_rejection() -> None:
    naive_dt = datetime(2024, 6, 3, 9, 30, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        to_eastern(naive_dt)

    # Explicit assume_tz ko'rsatilsa xato bo'lmaydi
    assumed = to_eastern(naive_dt, assume_tz=ZoneInfo("UTC"))
    assert assumed.tzinfo is not None


def test_datetime_index_support_and_series_masks() -> None:
    times = [
        "2024-06-03 08:00:00",  # 04:00 EDT (premarket)
        "2024-06-03 13:29:59",  # 09:29:59 EDT (premarket)
        "2024-06-03 13:30:00",  # 09:30:00 EDT (RTH)
        "2024-06-03 19:59:59",  # 15:59:59 EDT (RTH)
        "2024-06-03 20:00:00",  # 16:00:00 EDT (postmarket)
    ]
    idx = pd.to_datetime(times).tz_localize("UTC")
    df = pd.DataFrame({"close": [1, 2, 3, 4, 5]}, index=idx)

    prem_mask = is_premarket_series(df.index)
    rth_mask = is_rth_series(df.index)
    dates = get_session_dates(df.index)

    assert prem_mask.tolist() == [True, True, False, False, False]
    assert rth_mask.tolist() == [False, False, True, True, False]
    assert (dates == date(2024, 6, 3)).all()

    df_rth = filter_rth(df)
    assert len(df_rth) == 2
    assert df_rth["close"].tolist() == [3, 4]

    df_prem = filter_premarket(df)
    assert len(df_prem) == 2
    assert df_prem["close"].tolist() == [1, 2]
