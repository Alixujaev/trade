"""data/factory.py uchun testlar va ikkala provider o'rtasidagi sxema mosligini tekshirish."""

from __future__ import annotations

import pandas as pd
import pytest

import data.factory as factory_module
from data.alpaca_provider import AlpacaProvider
from data.factory import get_provider
from data.yfinance_provider import YFinanceProvider
from smc.structure import detect_swings


def test_factory_returns_yfinance_provider_by_default(monkeypatch) -> None:
    monkeypatch.setattr(factory_module, "DATA_PROVIDER", "yfinance")
    assert isinstance(get_provider(), YFinanceProvider)


def test_factory_respects_settings_default_when_changed(monkeypatch) -> None:
    monkeypatch.setattr(factory_module, "DATA_PROVIDER", "alpaca")
    assert isinstance(get_provider(), AlpacaProvider)


def test_factory_returns_explicit_provider_by_name() -> None:
    assert isinstance(get_provider("yfinance"), YFinanceProvider)
    assert isinstance(get_provider("alpaca"), AlpacaProvider)
    assert isinstance(get_provider("ALPACA"), AlpacaProvider)  # case-insensitive


def test_factory_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        get_provider("ibkr")


def test_both_providers_produce_identical_schema_and_feed_detect_swings() -> None:
    """Provider almashtirilganda downstream kod (detect_swings) bir xil ishlashi kerak.

    Bu — Phase 3.5'ning asosiy maqsadi: DataProvider abstraksiyasi to'g'ri
    qurilganini isbotlash. Ikkala provider ham AYNAN bir xil sxemali DataFrame
    berishi, va downstream kod buni farqlamasligi kerak.
    """
    dates = pd.date_range("2024-01-01", periods=21, freq="D", tz="UTC")
    prices = [10, 11, 12, 13, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13, 14, 13, 12, 11, 10, 11, 12]

    yfinance_style = pd.DataFrame(
        {
            "Open": prices,
            "High": prices,
            "Low": prices,
            "Close": prices,
            "Volume": [1000] * 21,
        },
        index=dates.tz_localize(None),  # yfinance odatda tz-naive beradi
    )
    yfinance_clean = YFinanceProvider._clean(yfinance_style)

    alpaca_rows = [
        {
            "symbol": "SPUS",
            "timestamp": ts,
            "open": p,
            "high": p,
            "low": p,
            "close": p,
            "volume": 1000,
            "trade_count": 10,
            "vwap": p,
        }
        for ts, p in zip(dates, prices)
    ]
    alpaca_style = pd.DataFrame(alpaca_rows).set_index(["symbol", "timestamp"])
    alpaca_clean = AlpacaProvider._clean(alpaca_style, "SPUS")

    # Ikkala provider ham bir xil sxema: ustunlar, index nomi, tz
    assert list(yfinance_clean.columns) == list(alpaca_clean.columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert yfinance_clean.index.name == alpaca_clean.index.name == "datetime"
    assert str(yfinance_clean.index.tz) == str(alpaca_clean.index.tz) == "UTC"

    # Downstream kod (detect_swings) ikkalasida ham bir xil natija berishi kerak —
    # provider farqi structure/market_structure qatlamiga umuman ta'sir qilmasligi kerak
    swings_from_yfinance = detect_swings(yfinance_clean, lookback=2)
    swings_from_alpaca = detect_swings(alpaca_clean, lookback=2)

    assert [s.index_pos for s in swings_from_yfinance] == [s.index_pos for s in swings_from_alpaca]
    assert [s.price for s in swings_from_yfinance] == [s.price for s in swings_from_alpaca]
    assert [s.label for s in swings_from_yfinance] == [s.label for s in swings_from_alpaca]
