"""tests/test_rsi.py: Wilder's RSI(14) indikatori uchun deterministik testlar."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from indicators.rsi import compute_rsi


def test_rsi_period_14() -> None:
    """14 davrli RSI dastlabki 14 ta barni NaN qiladi, 15-barda (index 14) birinchi qiymat chiqadi."""
    dates = pd.date_range("2026-01-01 09:30", periods=20, freq="5min")
    prices = [100.0 + i for i in range(20)]
    df = pd.DataFrame({"close": prices}, index=dates)

    rsi = compute_rsi(df, period=14)

    assert len(rsi) == 20
    assert rsi.iloc[:14].isna().all()
    assert not np.isnan(rsi.iloc[14])
    assert rsi.name == "rsi"


def test_rsi_above_50() -> None:
    """Doimiy ko'tarilayotgan (uptrend) ma'lumotlarda RSI > 50 bo'ladi."""
    dates = pd.date_range("2026-01-01 09:30", periods=30, freq="5min")
    # Ko'tarilish bilan ozgina tebranish
    prices = [100.0 + i * 0.5 + (0.1 if i % 2 == 0 else -0.05) for i in range(30)]
    df = pd.DataFrame({"close": prices}, index=dates)

    rsi = compute_rsi(df, period=14)

    # Oxirgi barlarda RSI 50 dan ancha katta bo'lishi kerak
    assert rsi.iloc[-1] > 50.0


def test_rsi_below_50() -> None:
    """Doimiy tushayotgan (downtrend) ma'lumotlarda RSI < 50 bo'ladi."""
    dates = pd.date_range("2026-01-01 09:30", periods=30, freq="5min")
    prices = [100.0 - i * 0.5 + (-0.1 if i % 2 == 0 else 0.05) for i in range(30)]
    df = pd.DataFrame({"close": prices}, index=dates)

    rsi = compute_rsi(df, period=14)

    assert rsi.iloc[-1] < 50.0


def test_rsi_pure_gains() -> None:
    """Faqat o'sish bo'lsa (yo'qotish nol), RSI = 100.0 bo'lishi kerak."""
    dates = pd.date_range("2026-01-01 09:30", periods=20, freq="5min")
    prices = [100.0 + i * 2.0 for i in range(20)]
    df = pd.DataFrame({"close": prices}, index=dates)

    rsi = compute_rsi(df, period=14)

    assert rsi.iloc[14] == 100.0
    assert rsi.iloc[-1] == 100.0


def test_rsi_pure_losses() -> None:
    """Faqat tushish bo'lsa (foyda nol), RSI = 0.0 bo'lishi kerak."""
    dates = pd.date_range("2026-01-01 09:30", periods=20, freq="5min")
    prices = [100.0 - i * 2.0 for i in range(20)]
    df = pd.DataFrame({"close": prices}, index=dates)

    rsi = compute_rsi(df, period=14)

    assert rsi.iloc[14] == 0.0
    assert rsi.iloc[-1] == 0.0


def test_rsi_flat_prices() -> None:
    """Narx umuman o'zgarmasa, RSI = 50.0 bo'ladi."""
    dates = pd.date_range("2026-01-01 09:30", periods=20, freq="5min")
    prices = [100.0] * 20
    df = pd.DataFrame({"close": prices}, index=dates)

    rsi = compute_rsi(df, period=14)

    assert rsi.iloc[14] == 50.0
    assert rsi.iloc[-1] == 50.0


def test_rsi_short_data() -> None:
    """Yetarlicha bar bo'lmasa (<= period), barcha qiymatlar NaN bo'ladi."""
    dates = pd.date_range("2026-01-01 09:30", periods=10, freq="5min")
    df = pd.DataFrame({"close": [100.0 + i for i in range(10)]}, index=dates)

    rsi = compute_rsi(df, period=14)
    assert rsi.isna().all()


def test_rsi_invalid_period() -> None:
    """period <= 0 bo'lsa ValueError berilishi kerak."""
    df = pd.DataFrame({"close": [100.0, 101.0]})
    with pytest.raises(ValueError, match="musbat bo'lishi kerak"):
        compute_rsi(df, period=0)
