"""tests/test_day08_backtest.py: Integration & Regression Tests for DAY-08 H6 Index Regime Confluence."""

from __future__ import annotations

import json
import pytest

from backtest.index_regime import run_day08_index_regime_experiment
from data.factory import get_provider


@pytest.fixture(scope="module")
def full_experiment_result():
    """Run full DAY-08 experiment once for all integration assertions."""
    prov = get_provider()
    return run_day08_index_regime_experiment(provider=prov)


def test_baseline_regression(full_experiment_result):
    """Section 18: Frozen Baseline Regression Audit.

    Must reproduce DAY-04/DAY-07 baseline:
    - 5,691 trades
    - 30.42% win rate
    - PF ≈ 0.94
    - total R ≈ -738.98R
    """
    res = full_experiment_result
    base = res.baseline_metrics

    assert base.trades == 5691
    assert abs(base.win_rate - 0.3042) < 0.001
    assert abs(base.profit_factor - 0.94) < 0.02
    assert abs(base.total_R - (-738.98)) < 1.0

    reg = res.baseline_regression
    assert reg["regression_verified"] is True


def test_variant_trade_counts_and_eligibility(full_experiment_result):
    """Verify variant trade counts and subset relationships."""
    res = full_experiment_result
    base = res.baseline_metrics
    h6a = res.h6_a_metrics
    h6b = res.h6_b_metrics
    h6c = res.h6_c_metrics

    # Total DAY-01 signals must equal 5691 across all variants
    for v in [base, h6a, h6b, h6c]:
        assert v.total_day01_signals == 5691
        assert v.eligible_signals + v.excluded_signals == 5691
        assert v.trades == v.eligible_signals

    # Specific trade counts
    assert h6a.trades == 2278
    assert h6b.trades == 2397
    assert h6c.trades == 1820

    # H6-C is intersection of SPY and QQQ bullish, so must be <= min(H6-A, H6-B)
    assert h6c.trades <= h6a.trades
    assert h6c.trades <= h6b.trades


def test_regime_distribution_sum_and_partitions(full_experiment_result):
    """Section 12: Verify regime distribution partition integrity."""
    res = full_experiment_result
    regimes = res.regime_distribution

    # Mutual exclusive & exhaustive 4-way partition:
    # SPY AND QQQ bullish + mixed + aligned bearish + unknown == 5691
    p4_sum = (
        regimes["SPY AND QQQ bullish"].trades
        + regimes["mixed"].trades
        + regimes["aligned bearish"].trades
        + regimes["unknown"].trades
    )
    assert p4_sum == 5691

    # SPY partition
    assert regimes["SPY bullish"].trades + regimes["SPY non-bullish"].trades == 5691

    # QQQ partition
    assert regimes["QQQ bullish"].trades + regimes["QQQ non-bullish"].trades == 5691

    # Missing context signals
    assert regimes["unknown"].trades == res.signal_counts["signals_excluded_due_to_missing_context"]


def test_per_symbol_trade_sums(full_experiment_result):
    """Section 13: Per-symbol trades must sum to aggregate trade counts."""
    res = full_experiment_result

    for var_key, expected_trades in [
        ("Baseline", 5691),
        ("H6-A", 2278),
        ("H6-B", 2397),
        ("H6-C", 1820),
    ]:
        sym_dict = res.per_symbol_metrics[var_key]
        assert len(sym_dict) == 25
        total_sym_trades = sum(m.trades for m in sym_dict.values())
        assert total_sym_trades == expected_trades


def test_slippage_monotonicity(full_experiment_result):
    """Section 16: Friction analysis must show monotonically decreasing returns with slippage."""
    res = full_experiment_result
    for v in [res.baseline_metrics, res.h6_a_metrics, res.h6_b_metrics, res.h6_c_metrics]:
        assert v.slippage_0bps > v.slippage_5bps
        assert v.slippage_5bps > v.slippage_10bps


def test_time_of_day_trade_sums(full_experiment_result):
    """Section 14: Time-of-day trade counts must sum to variant trade totals."""
    res = full_experiment_result
    for var_key, expected_trades in [
        ("Baseline", 5691),
        ("H6-A", 2278),
        ("H6-B", 2397),
        ("H6-C", 1820),
    ]:
        tod_list = res.time_of_day_diagnostics[var_key]
        tod_sum = sum(m.trades for m in tod_list)
        assert tod_sum == expected_trades


def test_json_serialization(full_experiment_result):
    """Section 22: Result dictionary must be JSON serializable."""
    res_dict = full_experiment_result.to_dict()
    json_str = json.dumps(res_dict)
    assert len(json_str) > 1000

    loaded = json.loads(json_str)
    assert loaded["baseline_regression"]["actual_trades"] == 5691
    assert loaded["h6_c_metrics"]["trades"] == 1820
