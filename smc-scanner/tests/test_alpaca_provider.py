"""data/alpaca_provider.py uchun testlar (real Alpaca tarmog'iga chiqmasdan, sun'iy data bilan)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from alpaca.data.timeframe import TimeFrameUnit

import data.alpaca_provider as alpaca_module
from data.alpaca_provider import _INTERVAL_TO_TIMEFRAME, AlpacaProvider


def _build_multi_symbol_raw() -> pd.DataFrame:
    """Alpaca'ning haqiqiy BarSet.df formatiga mos sun'iy raw data (2 symbol, MultiIndex)."""
    timestamps = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    rows = []
    for symbol in ("SPUS", "HLAL"):
        for i, ts in enumerate(timestamps):
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": ts,
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100.5 + i,
                    "volume": 1000 + i,
                    "trade_count": 50 + i,  # AlpacaProvider._clean bu ustunni tashlashi kerak
                    "vwap": 100.2 + i,  # bu ham
                }
            )
    df = pd.DataFrame(rows)
    return df.set_index(["symbol", "timestamp"])


def _build_single_symbol_tz_naive_raw() -> pd.DataFrame:
    """Bitta symbol, tz-naive timestamp level (himoya uchun — real Alpaca odatda tz-aware)."""
    timestamps = pd.date_range("2024-01-01", periods=5, freq="D")  # tz yo'q
    rows = [
        {
            "symbol": "SPUS",
            "timestamp": ts,
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100.5 + i,
            "volume": 1000 + i,
        }
        for i, ts in enumerate(timestamps)
    ]
    df = pd.DataFrame(rows)
    return df.set_index(["symbol", "timestamp"])


# --- _clean() testlari ---


def test_clean_selects_symbol_and_drops_extra_columns() -> None:
    raw = _build_multi_symbol_raw()
    result = AlpacaProvider._clean(raw, "SPUS")

    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert len(result) == 5  # faqat SPUS qatorlari, HLAL emas
    assert result["open"].iloc[0] == 100


def test_clean_result_has_utc_tz_and_datetime_name() -> None:
    raw = _build_multi_symbol_raw()
    result = AlpacaProvider._clean(raw, "HLAL")

    assert result.index.name == "datetime"
    assert str(result.index.tz) == "UTC"
    assert result.index.is_monotonic_increasing
    assert result.index.is_unique


def test_clean_localizes_naive_timestamps_to_utc() -> None:
    raw = _build_single_symbol_tz_naive_raw()
    result = AlpacaProvider._clean(raw, "SPUS")

    assert str(result.index.tz) == "UTC"
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]


# --- interval mapping / validatsiya testlari ---


def test_interval_to_timeframe_mapping_is_correct() -> None:
    assert _INTERVAL_TO_TIMEFRAME["1d"].amount == 1
    assert _INTERVAL_TO_TIMEFRAME["1d"].unit == TimeFrameUnit.Day

    assert _INTERVAL_TO_TIMEFRAME["4h"].amount == 4
    assert _INTERVAL_TO_TIMEFRAME["4h"].unit == TimeFrameUnit.Hour

    assert _INTERVAL_TO_TIMEFRAME["1h"].amount == 1
    assert _INTERVAL_TO_TIMEFRAME["1h"].unit == TimeFrameUnit.Hour

    assert _INTERVAL_TO_TIMEFRAME["1wk"].amount == 1
    assert _INTERVAL_TO_TIMEFRAME["1wk"].unit == TimeFrameUnit.Week


def test_get_ohlcv_invalid_interval_raises() -> None:
    # __init__ kredensial talab qilmaydi (lazy client) — .env bo'lmasa ham bu test ishlaydi
    provider = AlpacaProvider()
    with pytest.raises(ValueError):
        provider.get_ohlcv("SPUS", "5m")


def test_get_ohlcv_4h_now_supported() -> None:
    """Alpaca 4H'ni qo'llab-quvvatlaydi — bu yfinance'dan farqli (asosiy sabab)."""
    assert "4h" in alpaca_module.SUPPORTED_INTERVALS


# --- get_ohlcv() / cache testlari (tarmoq monkeypatch qilinadi) ---


def test_get_ohlcv_fetches_uppercases_symbol_and_cleans(monkeypatch, tmp_path) -> None:
    captured: dict[str, str] = {}

    def fake_fetch(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        captured["symbol"] = symbol
        captured["interval"] = interval
        return _build_multi_symbol_raw()

    monkeypatch.setattr(alpaca_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(AlpacaProvider, "_fetch_raw", fake_fetch)

    provider = AlpacaProvider()
    result = provider.get_ohlcv("spus", "4h", use_cache=False)

    assert captured["symbol"] == "SPUS"
    assert captured["interval"] == "4h"
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]


def test_cache_roundtrip_avoids_second_fetch(monkeypatch, tmp_path) -> None:
    call_count = {"n": 0}

    def fake_fetch(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        call_count["n"] += 1
        return _build_multi_symbol_raw()

    monkeypatch.setattr(alpaca_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(AlpacaProvider, "_fetch_raw", fake_fetch)

    provider = AlpacaProvider()
    first = provider.get_ohlcv("SPUS", "1d", use_cache=True)
    assert call_count["n"] == 1

    def failing_fetch(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        raise AssertionError("Tarmoqqa chiqmasligi kerak edi — kesh ishlatilishi kerak")

    monkeypatch.setattr(AlpacaProvider, "_fetch_raw", failing_fetch)

    second = provider.get_ohlcv("SPUS", "1d", use_cache=True)
    assert call_count["n"] == 1
    pd.testing.assert_frame_equal(first, second)


def test_cache_file_uses_alpaca_prefix(monkeypatch, tmp_path) -> None:
    """Alpaca kesh fayli yfinance kesh fayli bilan aralashmasligi kerak."""
    monkeypatch.setattr(alpaca_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        AlpacaProvider, "_fetch_raw", lambda self, symbol, interval, lookback_days: _build_multi_symbol_raw()
    )

    provider = AlpacaProvider()
    provider.get_ohlcv("SPUS", "1d", use_cache=False)
    provider.get_ohlcv("SPUS", "1d", use_cache=True)  # kesh yozilgan bo'lishi kerak

    cached_files = list(tmp_path.glob("alpaca_SPUS_1d.parquet"))
    assert len(cached_files) == 1
