"""scripts/core_monitor.py uchun testlar (sintetik OHLCV data, real tarmoqsiz)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

import scripts.core_monitor as monitor_module
from config.core_watchlist import CoreHolding
from scripts.core_monitor import (
    build_row,
    needs_review,
    pct_below_52w_high,
    pct_change,
    run_monitor,
    trend_context,
)


def _make_df(closes: list[float]) -> pd.DataFrame:
    """Sodda OHLCV (high=close, low=close, open=close), kunlik."""
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1000] * len(closes)},
        index=index,
    )


# --- needs_review ---


def test_needs_review_none_always_true() -> None:
    assert needs_review(None, 90, today=date(2026, 1, 1)) is True


def test_needs_review_below_threshold_is_false() -> None:
    today = date(2026, 1, 1)
    last_reviewed = today - timedelta(days=89)
    assert needs_review(last_reviewed, 90, today=today) is False


def test_needs_review_at_and_above_threshold_is_true() -> None:
    today = date(2026, 1, 1)
    assert needs_review(today - timedelta(days=90), 90, today=today) is True
    assert needs_review(today - timedelta(days=200), 90, today=today) is True


# --- pct_change / pct_below_52w_high ---


def test_pct_change_hand_computed() -> None:
    assert pct_change(110.0, 100.0) == pytest.approx(10.0)
    assert pct_change(90.0, 100.0) == pytest.approx(-10.0)


def test_pct_change_invalid_past_returns_none() -> None:
    assert pct_change(100.0, 0.0) is None
    assert pct_change(100.0, -5.0) is None
    assert pct_change(100.0, None) is None


def test_pct_below_52w_high_hand_computed() -> None:
    # (150-135)/150*100 = 10.0
    assert pct_below_52w_high(135.0, 150.0) == pytest.approx(10.0)
    assert pct_below_52w_high(150.0, 150.0) == pytest.approx(0.0)


# --- trend_context ---


def test_trend_context_bull_bear_na() -> None:
    assert trend_context(110.0, 100.0) == "bull"
    assert trend_context(90.0, 100.0) == "bear"
    assert trend_context(100.0, None) == "N/A"


# --- build_row ---


def test_build_row_hand_verified_short_history() -> None:
    # 30 bar, close = 100..129 (chiziqli), TREND_KONTEKST="N/A" (200 SMA uchun yetarli emas)
    closes = [100.0 + i for i in range(30)]
    df = _make_df(closes)
    holding = CoreHolding("TST", "Test Co", "stock", "TEKSHIRILISHI KERAK", None)

    row = build_row(holding, df, review_interval_days=90, today=date(2026, 1, 1))

    assert row["TICKER"] == "TST"
    assert row["NARX"] == pytest.approx(129.0)
    # (129-124)/124*100
    assert row["O'ZGARISH_1H%"] == pytest.approx(4.03, abs=0.01)
    # (129-108)/108*100
    assert row["O'ZGARISH_1O%"] == pytest.approx(19.44, abs=0.01)
    assert row["52W_HIGH_DAN%"] == pytest.approx(0.0)  # eng yuqori narx aynan hozirgisi
    assert row["TREND_KONTEKST"] == "N/A"
    assert row["OXIRGI_TEKSHIRUV"] == "Hech qachon"
    assert row["TEKSHIRUV_KERAKMI"] == "Ha"
    assert row["ERROR"] is None


def test_build_row_trend_context_with_full_sma_history() -> None:
    # 200 bar: birinchi 199 tasi flat=100, oxirgisi=150 -> SMA=(199*100+150)/200=100.25
    closes = [100.0] * 199 + [150.0]
    df = _make_df(closes)
    holding = CoreHolding(
        "TST2", "Test Co 2", "etf", "ETF holdings (prospectus)", date(2025, 12, 15)
    )

    row = build_row(holding, df, review_interval_days=90, today=date(2026, 1, 1))

    assert row["TREND_KONTEKST"] == "bull"  # 150 > 100.25
    assert row["OXIRGI_TEKSHIRUV"] == "2025-12-15"
    assert row["TEKSHIRUV_KERAKMI"] == "Yo'q"  # 2026-01-01 - 2025-12-15 = 17 kun < 90


def test_build_row_insufficient_data_no_crash() -> None:
    df = _make_df([100.0, 101.0, 102.0])  # 3 bar — hech qanday o'zgarish% hisoblab bo'lmaydi
    holding = CoreHolding("TST3", "Test Co 3", "stock", "TEKSHIRILISHI KERAK", None)

    row = build_row(holding, df, today=date(2026, 1, 1))

    assert row["O'ZGARISH_1H%"] is None
    assert row["O'ZGARISH_1O%"] is None
    assert row["TREND_KONTEKST"] == "N/A"
    assert row["ERROR"] is None


# --- run_monitor (provider monkeypatch, real tarmoqsiz) ---


class _FakeProvider:
    def __init__(self, df: pd.DataFrame | None = None, error: Exception | None = None) -> None:
        self._df = df
        self._error = error

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        if self._error is not None:
            raise self._error
        return self._df


def test_run_monitor_continues_after_one_ticker_fails(monkeypatch) -> None:
    good_df = _make_df([100.0 + i for i in range(30)])

    def fake_get_provider(name: str | None) -> _FakeProvider:
        return _FakeProvider(df=good_df)

    call_count = {"n": 0}

    def fake_get_provider_with_failure(name: str | None) -> _FakeProvider:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FakeProvider(error=RuntimeError("tarmoq xatosi"))
        return _FakeProvider(df=good_df)

    monkeypatch.setattr(monitor_module, "get_provider", fake_get_provider_with_failure)

    watchlist = [
        CoreHolding("BAD", "Bad Co", "stock", "TEKSHIRILISHI KERAK", None),
        CoreHolding("GOOD", "Good Co", "stock", "TEKSHIRILISHI KERAK", None),
    ]

    result = run_monitor(watchlist, None, "1d", 90, today=date(2026, 1, 1))

    assert len(result) == 2
    bad_row = result[result["TICKER"] == "BAD"].iloc[0]
    good_row = result[result["TICKER"] == "GOOD"].iloc[0]
    assert pd.notna(bad_row["ERROR"])
    assert pd.isna(good_row["ERROR"])
    assert good_row["NARX"] == pytest.approx(129.0)


def test_run_monitor_handles_empty_data(monkeypatch) -> None:
    monkeypatch.setattr(monitor_module, "get_provider", lambda name: _FakeProvider(df=pd.DataFrame()))

    watchlist = [CoreHolding("EMPTY", "Empty Co", "stock", "TEKSHIRILISHI KERAK", None)]
    result = run_monitor(watchlist, None, "1d", 90, today=date(2026, 1, 1))

    assert len(result) == 1
    assert pd.notna(result.iloc[0]["ERROR"])
