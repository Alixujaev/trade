"""tests/test_day_scanner.py: Day Scanner va non-directive signal formatter uchun testlar."""

from __future__ import annotations

from datetime import datetime
import pandas as pd
import pytest

from data.bars import filter_closed_bars
from data.provider import DataProvider
from signals.day_scanner import format_day_setup, scan_day
from strategy.day.types import DaySetupStatus, VwapRelation


class MockIntradayProvider(DataProvider):
    """Deterministik testlar uchun mock DataProvider."""

    def __init__(
        self,
        df_5m: pd.DataFrame | None = None,
        df_15m: pd.DataFrame | None = None,
        df_ext: pd.DataFrame | None = None,
    ) -> None:
        self.df_5m = df_5m if df_5m is not None else pd.DataFrame()
        self.df_15m = df_15m if df_15m is not None else pd.DataFrame()
        self.df_ext = df_ext if df_ext is not None else pd.DataFrame()

    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        *,
        include_extended_hours: bool = False,
        closed_only: bool = True,
        as_of: datetime | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        if include_extended_hours:
            df = self.df_ext
        elif interval == "5m":
            df = self.df_5m
        elif interval == "15m":
            df = self.df_15m
        else:
            df = pd.DataFrame()

        if closed_only and not df.empty:
            df = filter_closed_bars(df, interval, as_of=as_of)
        return df


def _create_5m_reclaim_df() -> pd.DataFrame:
    """VWAP reclaim holatini ifodalovchi 20 ta 5m bar DataFrame'i."""
    idx = pd.date_range("2026-01-05 09:30", periods=20, freq="5min", tz="America/New_York")
    closes = [100.0] * 17 + [99.0, 99.2, 101.0]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = [c - 0.1 for c in closes]
    vols = [1000.0] * 20
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=idx,
    )


def test_day_scanner_detects_vwap_reclaim() -> None:
    """Mock provayder bilan scan_day VWAP reclaim holatini to'g'ri aniqlaydi."""
    df_5m = _create_5m_reclaim_df()
    prov = MockIntradayProvider(df_5m=df_5m)

    setup = scan_day("AAPL", provider=prov)

    assert setup.symbol == "AAPL"
    assert setup.timeframe == "5m"
    assert setup.vwap_relation is VwapRelation.VWAP_RECLAIM
    assert setup.status in (DaySetupStatus.DETECTED, DaySetupStatus.CONFIRMED)


def test_day_scanner_returns_no_setup() -> None:
    """Narx VWAP ostida bo'lsa scan_day NO_SETUP qaytaradi."""
    idx = pd.date_range("2026-01-05 09:30", periods=20, freq="5min", tz="America/New_York")
    closes = [100.0] * 10 + [95.0] * 10  # VWAP ostida
    df_5m = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000.0] * 20,
        },
        index=idx,
    )
    prov = MockIntradayProvider(df_5m=df_5m)

    setup = scan_day("AAPL", provider=prov)

    assert setup.status is DaySetupStatus.NO_SETUP
    assert setup.vwap_relation is VwapRelation.BELOW_VWAP


def test_day_scanner_returns_data_insufficient() -> None:
    """Ma'lumot bo'sh yoki 15 bardan kam bo'lsa DATA_INSUFFICIENT qaytariladi."""
    idx = pd.date_range("2026-01-05 09:30", periods=5, freq="5min", tz="America/New_York")
    df_5m = pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [1000.0] * 5,
        },
        index=idx,
    )
    prov = MockIntradayProvider(df_5m=df_5m)

    setup = scan_day("AAPL", provider=prov)

    assert setup.status is DaySetupStatus.DATA_INSUFFICIENT
    assert any("fewer than 15 bars" in w for w in setup.warnings)


def test_day_scanner_never_uses_forming_bar() -> None:
    """as_of vaqtida hali yopilmagan forming bar hech qachon skanerga o'tmaydi."""
    # 09:30 dan 10:20 gacha 11 ta bar yaratamiz
    # 10:20 dagi bar 10:25 da yopiladi.
    # as_of = 10:22 (bar hali tugallanmagan)
    idx = pd.date_range("2026-01-05 09:30", periods=11, freq="5min", tz="America/New_York")
    df_5m = pd.DataFrame(
        {
            "open": [100.0] * 11,
            "high": [101.0] * 11,
            "low": [99.0] * 11,
            "close": [100.0] * 11,
            "volume": [1000.0] * 11,
        },
        index=idx,
    )
    prov = MockIntradayProvider(df_5m=df_5m)

    as_of_time = pd.Timestamp("2026-01-05 10:22", tz="America/New_York")
    # prov.get_ohlcv closed_only=True va as_of bilan chaqirilganda 10:20 bari filtrlanishi shart
    df_closed = prov.get_ohlcv("AAPL", "5m", closed_only=True, as_of=as_of_time)

    assert pd.Timestamp("2026-01-05 10:20", tz="America/New_York") not in df_closed.index
    assert df_closed.index[-1] == pd.Timestamp("2026-01-05 10:15", tz="America/New_York")


def test_day_scanner_respects_rth() -> None:
    """RTH sessiyasidan (09:30-16:00 ET) tashqaridagi barlarda NO_SETUP qaytariladi."""
    # Premarket barlari: 08:00 dan 09:15 gacha
    idx = pd.date_range("2026-01-05 08:00", periods=16, freq="5min", tz="America/New_York")
    df_5m = pd.DataFrame(
        {
            "open": [100.0] * 16,
            "high": [101.0] * 16,
            "low": [99.0] * 16,
            "close": [100.0] * 16,
            "volume": [1000.0] * 16,
        },
        index=idx,
    )
    prov = MockIntradayProvider(df_5m=df_5m)

    setup = scan_day("AAPL", provider=prov)

    assert setup.status is DaySetupStatus.NO_SETUP
    assert any("Outside RTH session" in w for w in setup.warnings)


def test_non_directive_output() -> None:
    """Signal matnida hech qachon BUY NOW, ENTER LONG, SELL NOW kabi buyruqlar bo'lmasligi shart."""
    df_5m = _create_5m_reclaim_df()
    prov = MockIntradayProvider(df_5m=df_5m)
    setup = scan_day("AAPL", provider=prov)

    output = format_day_setup(setup)

    assert "BUY NOW" not in output
    assert "ENTER LONG" not in output
    assert "SELL NOW" not in output
    assert "STRONG BUY" not in output
    assert "BUY SIGNAL" not in output
    assert "BUY" not in output or "Status: BUY" not in output

    # Non-directive elementlar mavjudligini tekshirish
    assert "DAY SETUP" in output
    assert "Symbol: AAPL" in output
    assert "Status: DETECTED" in output or "Status: CONFIRMED" in output
    assert "Evidence:" in output
