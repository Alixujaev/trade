"""journal/benchmark.py (sof, I/O'siz qatlam) uchun testlar."""

from __future__ import annotations

from datetime import date

import pytest

from journal.benchmark import (
    BenchmarkResult,
    calculate_buy_hold_return,
    discretionary_price_return,
    outperformed_benchmark,
)


# ======================================================================
# calculate_buy_hold_return
# ======================================================================


def test_calculate_buy_hold_return_positive() -> None:
    assert calculate_buy_hold_return(100.0, 110.0) == pytest.approx(0.10)


def test_calculate_buy_hold_return_negative() -> None:
    assert calculate_buy_hold_return(100.0, 90.0) == pytest.approx(-0.10)


def test_calculate_buy_hold_return_flat() -> None:
    assert calculate_buy_hold_return(100.0, 100.0) == pytest.approx(0.0)


def test_calculate_buy_hold_return_zero_entry_price_is_safe() -> None:
    """Degenerativ holat (ma'lumot xato bo'lsa ham yuz berishi mumkin) -- ZeroDivisionError
    o'rniga xavfsiz 0.0."""
    assert calculate_buy_hold_return(0.0, 110.0) == 0.0


def test_calculate_buy_hold_return_negative_entry_price_is_safe() -> None:
    assert calculate_buy_hold_return(-5.0, 110.0) == 0.0


# ======================================================================
# discretionary_price_return -- R-multiple'dan MUSTAQIL, alohida birlik
# ======================================================================


def test_discretionary_price_return_matches_buy_hold_formula() -> None:
    """Bir xil formula, faqat exit narxi -- savdoning HAQIQIY chiqishi (benchmark emas)."""
    assert discretionary_price_return(100.0, 120.0) == pytest.approx(0.20)


def test_discretionary_price_return_zero_entry_price_is_safe() -> None:
    assert discretionary_price_return(0.0, 120.0) == 0.0


def test_discretionary_price_return_differs_from_r_multiple() -> None:
    """METODOLOGIK asos: tor stop bilan R=+2.0 bo'lgan savdo narxda atigi bir necha
    foiz ko'tarilgan bo'lishi mumkin -- price return R bilan bir xil EMAS."""
    entry_price, stop_price, exit_price = 100.0, 98.0, 104.0
    r_multiple = (exit_price - entry_price) / (entry_price - stop_price)  # = 2.0
    price_return = discretionary_price_return(entry_price, exit_price)  # = 0.04

    assert r_multiple == pytest.approx(2.0)
    assert price_return == pytest.approx(0.04)
    assert price_return != r_multiple


# ======================================================================
# BenchmarkResult -- same-window, alohida birlik
# ======================================================================


def test_benchmark_result_holds_same_window_dates() -> None:
    result = BenchmarkResult(
        symbol="AAPL",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
        entry_price=100.0,
        benchmark_exit_price=110.0,
        benchmark_return=calculate_buy_hold_return(100.0, 110.0),
    )

    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 1, 10)
    assert result.benchmark_return == pytest.approx(0.10)


def test_benchmark_result_is_frozen() -> None:
    result = BenchmarkResult(
        symbol="AAPL", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
        entry_price=100.0, benchmark_exit_price=110.0, benchmark_return=0.10,
    )

    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        result.entry_price = 999.0  # type: ignore[misc]


# ======================================================================
# outperformed_benchmark -- "outperform" ning ANIQ ta'rifi (metodologik yurak)
# ======================================================================


def test_outperformed_benchmark_true_when_price_return_exceeds_benchmark() -> None:
    benchmark = BenchmarkResult(
        symbol="AAPL", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
        entry_price=100.0, benchmark_exit_price=105.0, benchmark_return=0.05,
    )

    assert outperformed_benchmark(entry_price=100.0, exit_price=120.0, benchmark=benchmark) is True


def test_outperformed_benchmark_false_when_price_return_below_benchmark() -> None:
    benchmark = BenchmarkResult(
        symbol="AAPL", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
        entry_price=100.0, benchmark_exit_price=130.0, benchmark_return=0.30,
    )

    assert outperformed_benchmark(entry_price=100.0, exit_price=110.0, benchmark=benchmark) is False


def test_outperformed_benchmark_false_when_equal() -> None:
    """Teng bo'lsa outperform EMAS (qat'iy >)."""
    benchmark = BenchmarkResult(
        symbol="AAPL", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
        entry_price=100.0, benchmark_exit_price=110.0, benchmark_return=0.10,
    )

    assert outperformed_benchmark(entry_price=100.0, exit_price=110.0, benchmark=benchmark) is False


def test_outperformed_benchmark_ignores_r_multiple_uses_price_return_only() -> None:
    """METODOLOGIK asos: R baland bo'lsa ham (tor stop), price return past bo'lsa
    outperform EMAS -- R bu yerda HECH QACHON ishlatilmaydi."""
    # Savdo: entry=100, stop=99 (tor), exit=102 -> R=+2.0, price return=+2%
    # Benchmark: shu oynada +5% o'sgan -> price return bo'yicha benchmark yutadi
    benchmark = BenchmarkResult(
        symbol="AAPL", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
        entry_price=100.0, benchmark_exit_price=105.0, benchmark_return=0.05,
    )
    r_multiple = (102.0 - 100.0) / (100.0 - 99.0)
    assert r_multiple == pytest.approx(2.0)  # "yaxshi ko'rinadi" R bo'yicha

    assert outperformed_benchmark(entry_price=100.0, exit_price=102.0, benchmark=benchmark) is False
