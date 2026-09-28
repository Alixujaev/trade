"""data/validation.py va data/bars.py uchun testlar to'plami.

OHLCV strukturaviy validatsiyasi, buzilgan (malformed) qatorlarni tozalash,
va closed-only (shakllanayotgan barni chiqarish) testlari.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from data.bars import filter_closed_bars, get_interval_timedelta
from data.validation import validate_ohlcv


def test_validate_ohlcv_success() -> None:
    idx = pd.date_range("2024-06-03 13:30:00", periods=3, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0, 101.0],
            "high": [105.0, 104.0, 103.0],
            "low": [99.0, 100.0, 100.0],
            "close": [102.0, 101.0, 102.0],
            "volume": [1000.0, 2000.0, 1500.0],
        },
        index=idx,
    )
    clean = validate_ohlcv(df, symbol="AAPL")

    assert len(clean) == 3
    assert list(clean.columns) == ["open", "high", "low", "close", "volume"]
    assert clean.index.name == "datetime"


def test_validate_ohlcv_missing_columns_raises() -> None:
    df = pd.DataFrame({"open": [100], "close": [105]})
    with pytest.raises(ValueError, match="kerakli ustunlar yo'q"):
        validate_ohlcv(df, symbol="AAPL")


def test_validate_ohlcv_empty_raises() -> None:
    df = pd.DataFrame()
    with pytest.raises(ValueError, match="bo'sh"):
        validate_ohlcv(df, symbol="AAPL")


def test_validate_ohlcv_filters_malformed_ohlc() -> None:
    idx = pd.date_range("2024-06-03 13:30:00", periods=5, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            # Qator 0: To'g'ri bar
            # Qator 1: Buzilgan (high < low: high=90, low=100)
            # Qator 2: Buzilgan (high < open: high=100, open=105)
            # Qator 3: Buzilgan (low > close: low=102, close=100)
            # Qator 4: Buzilgan (manfiy hajm: volume=-50)
            "open": [100.0, 100.0, 105.0, 101.0, 100.0],
            "high": [105.0, 90.0, 100.0, 105.0, 105.0],
            "low": [99.0, 100.0, 99.0, 102.0, 99.0],
            "close": [102.0, 102.0, 100.0, 100.0, 102.0],
            "volume": [1000.0, 1000.0, 1000.0, 1000.0, -50.0],
        },
        index=idx,
    )
    clean = validate_ohlcv(df, symbol="TEST")

    # Faqat 0-qator o'tishi kerak
    assert len(clean) == 1
    assert clean.iloc[0]["open"] == 100.0


def test_validate_ohlcv_deduplicates_and_sorts() -> None:
    t0 = pd.Timestamp("2024-06-03 13:35:00", tz="UTC")
    t1 = pd.Timestamp("2024-06-03 13:30:00", tz="UTC")
    # Tartibsiz va dublikatli
    idx = [t0, t1, t0]
    df = pd.DataFrame(
        {
            "open": [100.0, 90.0, 105.0],
            "high": [110.0, 95.0, 110.0],
            "low": [95.0, 85.0, 95.0],
            "close": [105.0, 92.0, 108.0],
            "volume": [100.0, 200.0, 300.0],
        },
        index=idx,
    )
    clean = validate_ohlcv(df)

    assert len(clean) == 2
    assert clean.index.is_monotonic_increasing
    # Dublikat t0 uchun oxirgi qiymat (volume=300) saqlangan
    assert clean.loc[t0, "volume"] == 300.0


def test_filter_closed_bars_excludes_forming_bar() -> None:
    # 5m barlar:
    # Bar 0: 13:30 UTC -> yopilish vaqti 13:35 UTC
    # Bar 1: 13:35 UTC -> yopilish vaqti 13:40 UTC
    # Bar 2: 13:40 UTC -> yopilish vaqti 13:45 UTC (forming!)
    idx = pd.to_datetime(["2024-06-03 13:30:00", "2024-06-03 13:35:00", "2024-06-03 13:40:00"]).tz_localize("UTC")
    df = pd.DataFrame({"close": [100, 101, 102]}, index=idx)

    # as_of = 13:42 UTC (Bar 2 hali yopilmagan: 13:45 > 13:42)
    as_of = datetime(2024, 6, 3, 13, 42, 0, tzinfo=timezone.utc)
    closed = filter_closed_bars(df, interval="5m", as_of=as_of)

    assert len(closed) == 2
    assert closed.index[-1] == pd.Timestamp("2024-06-03 13:35:00", tz="UTC")

    # as_of = 13:45 UTC ga yetganda Bar 2 ham yopilgan deb hisoblanadi
    as_of_done = datetime(2024, 6, 3, 13, 45, 0, tzinfo=timezone.utc)
    all_closed = filter_closed_bars(df, interval="5m", as_of=as_of_done)
    assert len(all_closed) == 3


def test_filter_closed_bars_preserves_historical_data() -> None:
    # Tarixiy ma'lumotlar o'tmishga tegishli bo'lganda (as_of=None) hech bir bar o'chirilmaydi
    idx = pd.date_range("2020-01-02 14:30:00", periods=10, freq="5min", tz="UTC")
    df = pd.DataFrame({"close": range(10)}, index=idx)
    closed = filter_closed_bars(df, interval="5m", as_of=None)
    assert len(closed) == 10


def test_get_interval_timedelta_mapping() -> None:
    assert get_interval_timedelta("5m") == pd.Timedelta(minutes=5)
    assert get_interval_timedelta("15m") == pd.Timedelta(minutes=15)
    assert get_interval_timedelta("1h") == pd.Timedelta(hours=1)
    assert get_interval_timedelta("1d") == pd.Timedelta(days=1)
    with pytest.raises(ValueError):
        get_interval_timedelta("2m")
