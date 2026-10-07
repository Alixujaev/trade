"""Provayderlarning intraday (5m, 15m, extended-hours, cache) imkoniyatlari testlari.

Barcha tarmoq chaqiruvlari monkeypatch qilinadi (deterministik).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from data.alpaca_provider import AlpacaProvider
from data.yfinance_provider import YFinanceProvider


def _dummy_ohlcv_intraday() -> pd.DataFrame:
    # 08:00 UTC (Premarket 04:00 EDT), 13:30 UTC (RTH 09:30 EDT)
    times = ["2024-06-03 08:00:00", "2024-06-03 13:30:00", "2024-06-03 13:35:00"]
    idx = pd.to_datetime(times).tz_localize("UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 102.0, 103.0],
            "High": [105.0, 106.0, 107.0],
            "Low": [99.0, 101.0, 102.0],
            "Close": [102.0, 103.0, 105.0],
            "Volume": [1000.0, 2000.0, 3000.0],
        },
        index=idx,
    )


# --- YFinanceProvider Intraday Testlari ---


def test_yfinance_supports_5m_and_15m(monkeypatch, tmp_path) -> None:
    provider = YFinanceProvider()
    monkeypatch.setattr(provider, "_cache_path", lambda s, i, include_extended_hours=False: tmp_path / f"{s}_{i}.parquet")

    captured_kwargs: dict = {}

    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        captured_kwargs.update(kwargs)
        return _dummy_ohlcv_intraday()

    monkeypatch.setattr("data.yfinance_provider.yf.download", fake_download)

    # 5m
    res_5m = provider.get_ohlcv("AAPL", "5m", use_cache=False)
    assert len(res_5m) == 3
    assert captured_kwargs["interval"] == "5m"
    assert captured_kwargs["period"] == "60d"

    # 15m
    res_15m = provider.get_ohlcv("AAPL", "15m", use_cache=False)
    assert len(res_15m) == 3
    assert captured_kwargs["interval"] == "15m"
    assert captured_kwargs["period"] == "60d"


def test_yfinance_rejects_1m_and_4h() -> None:
    provider = YFinanceProvider()
    with pytest.raises(ValueError, match="qo'llab-quvvatlamaydi"):
        provider.get_ohlcv("AAPL", "1m")
    with pytest.raises(ValueError, match="qo'llab-quvvatlamaydi"):
        provider.get_ohlcv("AAPL", "4h")


def test_yfinance_extended_hours_prepost_flag_and_cache(monkeypatch, tmp_path) -> None:
    provider = YFinanceProvider()
    monkeypatch.setattr("data.yfinance_provider.CACHE_DIR", tmp_path)

    captured_prepost: list[bool] = []

    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        captured_prepost.append(kwargs.get("prepost", False))
        return _dummy_ohlcv_intraday()

    monkeypatch.setattr("data.yfinance_provider.yf.download", fake_download)

    # 1. include_extended_hours=False -> prepost=False, fayl: AAPL_5m.parquet
    provider.get_ohlcv("AAPL", "5m", include_extended_hours=False, use_cache=True)
    assert captured_prepost[-1] is False
    assert (tmp_path / "AAPL_5m.parquet").exists()
    assert not (tmp_path / "AAPL_5m_ext.parquet").exists()

    # 2. include_extended_hours=True -> prepost=True, fayl: AAPL_5m_ext.parquet (alohida kesh!)
    provider.get_ohlcv("AAPL", "5m", include_extended_hours=True, use_cache=True)
    assert captured_prepost[-1] is True
    assert (tmp_path / "AAPL_5m_ext.parquet").exists()


def test_yfinance_closed_only_filtering(monkeypatch, tmp_path) -> None:
    provider = YFinanceProvider()
    monkeypatch.setattr(provider, "_cache_path", lambda s, i, include_extended_hours=False: tmp_path / f"{s}_{i}.parquet")

    def fake_download(symbol: str, **kwargs) -> pd.DataFrame:
        return _dummy_ohlcv_intraday()

    monkeypatch.setattr("data.yfinance_provider.yf.download", fake_download)

    # 13:35 da ochilgan 5m bar 13:40 da yopiladi.
    # as_of = 13:37 UTC berilsa, oxirgi bar shakllanayotgan bo'lib filtrlanishi kerak
    as_of = datetime(2024, 6, 3, 13, 37, 0, tzinfo=timezone.utc)
    res = provider.get_ohlcv("AAPL", "5m", use_cache=False, closed_only=True, as_of=as_of)
    assert len(res) == 2


def test_yfinance_cache_ttl_intraday_vs_hourly(tmp_path) -> None:
    provider = YFinanceProvider()
    f_5m = tmp_path / "test_5m.parquet"
    f_5m.write_bytes(b"dummy")

    # 10 daqiqa oldingi fayl (intraday TTL 5 daqiqa bo'lgani uchun eski hisoblanadi)
    old_time = time.time() - 10 * 60
    import os
    os.utime(f_5m, (old_time, old_time))

    # 5m uchun kesh eskirgan (False)
    assert provider._is_cache_fresh(f_5m, interval="5m") is False

    # 1h uchun 10 daqiqalik fayl yangi (True, chunki 1h TTL = 4 soat)
    assert provider._is_cache_fresh(f_5m, interval="1h") is True


# --- AlpacaProvider Intraday Testlari ---


def test_alpaca_supports_5m_and_15m_with_rth_filtering(monkeypatch, tmp_path) -> None:
    provider = AlpacaProvider()
    monkeypatch.setattr(provider, "_cache_path", lambda s, i, include_extended_hours=False: tmp_path / f"alpaca_{s}_{i}.parquet")

    def fake_fetch_raw(symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        # Dummy ma'lumot: 1 ta premarket (08:00 UTC) va 2 ta RTH bar
        df = _dummy_ohlcv_intraday()
        df.columns = [c.lower() for c in df.columns]
        return df

    monkeypatch.setattr(provider, "_fetch_raw", fake_fetch_raw)

    # 1. include_extended_hours=False (standart): premarket bar tashlanib faqat RTH (2 ta) qoladi
    res_rth = provider.get_ohlcv("AAPL", "5m", use_cache=False, include_extended_hours=False)
    assert len(res_rth) == 2
    assert pd.Timestamp("2024-06-03 08:00:00", tz="UTC") not in res_rth.index

    # 2. include_extended_hours=True: premarket bar ham saqlanadi (3 ta)
    res_ext = provider.get_ohlcv("AAPL", "5m", use_cache=False, include_extended_hours=True)
    assert len(res_ext) == 3
    assert pd.Timestamp("2024-06-03 08:00:00", tz="UTC") in res_ext.index
