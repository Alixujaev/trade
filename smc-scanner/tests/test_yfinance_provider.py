"""data/yfinance_provider.py uchun testlar (real tarmoqsiz, sun'iy data bilan)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import data.yfinance_provider as yfp_module
from data.yfinance_provider import YFinanceProvider


def _base_ohlcv(
    periods: int = 10, freq: str = "D", tz: str | None = None, *, end: object | None = None
) -> pd.DataFrame:
    if end is not None:
        dates = pd.date_range(end=end, periods=periods, freq=freq, tz=tz)
    else:
        dates = pd.date_range("2024-01-01", periods=periods, freq=freq, tz=tz)
    return pd.DataFrame(
        {
            "Open": np.arange(periods, dtype=float) + 100,
            "High": np.arange(periods, dtype=float) + 101,
            "Low": np.arange(periods, dtype=float) + 99,
            "Close": np.arange(periods, dtype=float) + 100.5,
            "Volume": np.arange(periods, dtype=float) + 1000,
        },
        index=dates,
    )


def _build_multiindex_raw() -> pd.DataFrame:
    """MultiIndex ustunli, tz-naive, NaN qatorli, dublikat va tartibsiz sun'iy raw data."""
    df = _base_ohlcv()
    df.columns = pd.MultiIndex.from_product([df.columns, ["SPUS"]])
    df.iloc[3] = np.nan  # NaN qator (2024-01-04)
    dup_row = df.iloc[[5]]  # dublikat uchun 2024-01-06 qatorini olish
    df = pd.concat([df, dup_row])
    df = df.sample(frac=1.0, random_state=42)  # tartibni buzish
    return df


def _build_flat_raw() -> pd.DataFrame:
    """MultiIndex'siz (flat) tz-naive sun'iy raw data, bitta NaN qatorli."""
    df = _base_ohlcv()
    df.iloc[2] = np.nan  # NaN qator (2024-01-03)
    return df


def _build_tz_aware_raw() -> pd.DataFrame:
    """Allaqachon tz-aware (America/New_York) sun'iy raw data."""
    return _base_ohlcv(periods=5, freq="h", tz="America/New_York")


# --- _clean() testlari ---


def test_clean_normalizes_multiindex_columns() -> None:
    result = YFinanceProvider._clean(_build_multiindex_raw())
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]


def test_clean_converts_naive_tz_to_utc() -> None:
    result = YFinanceProvider._clean(_build_multiindex_raw())
    assert result.index.tz is not None
    assert str(result.index.tz) == "UTC"
    assert result.index.name == "datetime"


def test_clean_drops_nan_rows() -> None:
    result = YFinanceProvider._clean(_build_multiindex_raw())
    assert result.isna().sum().sum() == 0
    # 10 asl qator + 1 dublikat - 1 NaN qator - 1 birlashtirilgan dublikat = 9
    assert len(result) == 9


def test_clean_sorts_and_dedups_index() -> None:
    result = YFinanceProvider._clean(_build_multiindex_raw())
    assert result.index.is_monotonic_increasing
    assert result.index.is_unique


def test_clean_flat_columns_single_symbol() -> None:
    result = YFinanceProvider._clean(_build_flat_raw())
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert result.isna().sum().sum() == 0
    assert len(result) == 9


def test_clean_converts_existing_tz_to_utc() -> None:
    result = YFinanceProvider._clean(_build_tz_aware_raw())
    assert str(result.index.tz) == "UTC"
    assert result.index.is_monotonic_increasing


def test_clean_missing_column_raises() -> None:
    raw = _build_flat_raw().drop(columns=["Volume"])
    with pytest.raises(ValueError):
        YFinanceProvider._clean(raw)


# --- get_ohlcv() testlari ---


def test_get_ohlcv_invalid_interval_raises() -> None:
    provider = YFinanceProvider()
    with pytest.raises(ValueError):
        provider.get_ohlcv("SPUS", "4h")


def test_get_ohlcv_uppercases_symbol_and_cleans(monkeypatch, tmp_path) -> None:
    captured: dict[str, str] = {}

    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        captured["symbol"] = symbol
        return _build_flat_raw()

    monkeypatch.setattr(yfp_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(yfp_module.yf, "download", fake_download)

    provider = YFinanceProvider()
    result = provider.get_ohlcv("spus", "1d", use_cache=False)

    assert captured["symbol"] == "SPUS"
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]


def test_get_ohlcv_empty_download_raises(monkeypatch, tmp_path) -> None:
    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr(yfp_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(yfp_module.yf, "download", fake_download)

    provider = YFinanceProvider()
    with pytest.raises(ValueError):
        provider.get_ohlcv("SPUS", "1d", use_cache=False)


def test_cache_roundtrip_avoids_second_network_call(monkeypatch, tmp_path) -> None:
    call_count = {"n": 0}

    # Oxirgi bar BUGUNGI sanada -> bar-sana tekshiruvi keshni "eski" demaydi
    # (bu test faqat TTL/roundtrip xatti-harakatini tekshiradi).
    recent = _base_ohlcv(end=pd.Timestamp.now(tz="UTC").normalize())

    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        call_count["n"] += 1
        return recent.copy()

    monkeypatch.setattr(yfp_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(yfp_module.yf, "download", fake_download)

    provider = YFinanceProvider()
    first = provider.get_ohlcv("SPUS", "1d", use_cache=True)
    assert call_count["n"] == 1

    def failing_download(symbol: str, **kwargs) -> pd.DataFrame:
        raise AssertionError("Tarmoqqa chiqmasligi kerak edi — kesh ishlatilishi kerak")

    monkeypatch.setattr(yfp_module.yf, "download", failing_download)

    second = provider.get_ohlcv("SPUS", "1d", use_cache=True)
    assert call_count["n"] == 1
    pd.testing.assert_frame_equal(first, second)


# --- bar-sana asosli "eskirish" (kunlik lag muammosi) ---

from datetime import datetime, timezone  # noqa: E402

from data.yfinance_provider import _latest_expected_session_date  # noqa: E402


def test_latest_expected_session_date_before_close_is_previous_day() -> None:
    # Chorshanba 10:00 UTC (sessiya hali yopilmagan) -> seshanba
    d = _latest_expected_session_date(datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc))
    assert d.isoformat() == "2026-08-25"


def test_latest_expected_session_date_after_close_is_same_day() -> None:
    # Chorshanba 22:00 UTC (sessiya yopilgan) -> chorshanba
    d = _latest_expected_session_date(datetime(2026, 8, 26, 22, 0, tzinfo=timezone.utc))
    assert d.isoformat() == "2026-08-26"


def test_latest_expected_session_date_weekend_rolls_back_to_friday() -> None:
    # Yakshanba -> juma
    d = _latest_expected_session_date(datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc))
    assert d.isoformat() == "2026-08-28"


def test_daily_cache_stale_when_last_bar_behind_session(monkeypatch, tmp_path) -> None:
    """Kesh fayli yangi yozilgan bo'lsa ham (TTL ichida), oxirgi bari o'tgan savdo
    kunidan eski bo'lsa -> qayta tortiladi (aynan CSGP holati: skan ertalab ishlagan,
    kunlik bar keyin yopilgan)."""
    call_count = {"n": 0}
    stale = _base_ohlcv(periods=10)  # 2024-01-.. — bugundan ancha eski

    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        call_count["n"] += 1
        return stale.copy()

    monkeypatch.setattr(yfp_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(yfp_module.yf, "download", fake_download)

    provider = YFinanceProvider()
    provider.get_ohlcv("SPUS", "1d", use_cache=True)
    assert call_count["n"] == 1

    # fayl endigina yozildi (mtime = hozir, TTL ichida), lekin bar-sana eski:
    provider.get_ohlcv("SPUS", "1d", use_cache=True)
    assert call_count["n"] == 2  # bar-sana eskiligi sabab qayta tortildi
