"""tests/test_day07a_robustness.py: Comprehensive test suite for DAY-07A H2 stop management robustness."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.day_types import (
    DaySetupStatus,
    ExecutionConfig,
)
from backtest.dynamic_stop_robustness import (
    DAY07A_BE_THRESHOLDS_R,
    format_dynamic_stop_robustness_report,
    run_day07a_robustness_experiment,
)
from backtest.execution import simulate_trade_execution
from data.factory import get_provider
from strategy.day.types import DaySetup


def _make_dummy_setup(
    setup_time: pd.Timestamp,
    price: float = 100.0,
    symbol: str = "TEST",
) -> DaySetup:
    return DaySetup(
        symbol=symbol,
        timestamp=setup_time,
        status=DaySetupStatus.CONFIRMED,
        price=price,
        vwap=99.5,
        rsi=55.0,
        rvol=2.5,
    )


# ---------------------------------------------------------------------
# 1. Threshold Configuration & Invariants
# ---------------------------------------------------------------------

def test_predeclared_thresholds_exact() -> None:
    """Pre-declared threshold tuple must be exactly (0.75, 1.00, 1.25)."""
    assert DAY07A_BE_THRESHOLDS_R == (0.75, 1.00, 1.25)
    assert len(DAY07A_BE_THRESHOLDS_R) == 3


def test_monotonic_trigger_eligibility_synthetic() -> None:
    """If a trade triggers 1.25R, it must also trigger 1.00R and 0.75R.
    Therefore, count(0.75R) >= count(1.00R) >= count(1.25R).
    """
    idx = pd.date_range("2026-07-02 09:30:00", periods=5, freq="5min", tz="America/New_York")
    # Setup bar low = 99.0, entry = 100.0 -> R = 1.0
    # 0.75R trigger = 100.75
    # 1.00R trigger = 101.00
    # 1.25R trigger = 101.25
    df_075_only = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.6, 100.2, 99.8],
            "high": [100.0, 100.8, 100.7, 100.3, 100.0],  # Bar 1 high = 100.8 (reaches 0.75R, but not 1.00R)
            "low": [99.0, 100.0, 100.1, 99.9, 99.5],
            "close": [99.8, 100.5, 100.3, 100.0, 99.6],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )
    setup = _make_dummy_setup(idx[0])

    sim_075 = simulate_trade_execution(df_075_only, setup_bar_idx=0, setup=setup, config=ExecutionConfig(breakeven_trigger_r=0.75))
    sim_100 = simulate_trade_execution(df_075_only, setup_bar_idx=0, setup=setup, config=ExecutionConfig(breakeven_trigger_r=1.00))
    sim_125 = simulate_trade_execution(df_075_only, setup_bar_idx=0, setup=setup, config=ExecutionConfig(breakeven_trigger_r=1.25))

    assert sim_075 is not None and sim_100 is not None and sim_125 is not None
    assert sim_075.trade.be_triggered is True
    assert sim_100.trade.be_triggered is False
    assert sim_125.trade.be_triggered is False


def test_monotonic_activation_timing_synthetic() -> None:
    """0.75R trigger cannot occur after 1.00R trigger for any trade."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=5, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.8, 101.1, 100.5],
            "high": [100.0, 100.8, 101.1, 101.3, 100.9],  # Bar 1 hits 0.75R (100.8), Bar 2 hits 1.0R (101.1)
            "low": [99.0, 100.1, 100.4, 100.8, 100.2],
            "close": [99.8, 100.7, 101.0, 101.1, 100.6],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )
    setup = _make_dummy_setup(idx[0])

    sim_075 = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=ExecutionConfig(breakeven_trigger_r=0.75))
    sim_100 = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=ExecutionConfig(breakeven_trigger_r=1.00))

    assert sim_075 is not None and sim_100 is not None
    assert sim_075.trade.be_trigger_time is not None
    assert sim_100.trade.be_trigger_time is not None
    assert sim_075.trade.be_trigger_time <= sim_100.trade.be_trigger_time


# ---------------------------------------------------------------------
# 2. Execution Semantics & Point-in-Time Safety
# ---------------------------------------------------------------------

def test_next_bar_activation_rule_across_thresholds() -> None:
    """For any threshold, BE must become active on NEXT bar only."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=4, freq="5min", tz="America/New_York")
    # Entry 100, Stop 99 (R = 1)
    # Threshold 1.25R: Trigger = 101.25
    # Bar 1 reaches 101.30, but low is 99.8 (below entry 100, above stop 99)
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.5, 100.2],
            "high": [100.0, 101.3, 101.0, 100.8],
            "low": [99.0, 99.8, 99.9, 99.5],  # Bar 1 low 99.8 does not hit stop (99.0)
            "close": [99.8, 100.6, 100.2, 99.9],
            "volume": [1000.0] * 4,
        },
        index=idx,
    )
    setup = _make_dummy_setup(idx[0])
    cfg = ExecutionConfig(breakeven_trigger_r=1.25)

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim is not None
    # Must NOT have exited on Bar 1
    assert sim.trade.exit_time == idx[2]
    assert sim.trade.exit_reason == "breakeven"
    assert sim.trade.be_triggered is True
    assert sim.trade.be_trigger_time == idx[1]


def test_target_precedence_on_trigger_bar_across_thresholds() -> None:
    """Target reached on trigger candle executes normally at +2R for all thresholds."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=3, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 101.5],
            "high": [100.0, 102.2, 102.0],  # Bar 1 reaches 2R target (102.0)
            "low": [99.0, 100.2, 101.0],
            "close": [99.8, 102.0, 101.8],
            "volume": [1000.0] * 3,
        },
        index=idx,
    )
    setup = _make_dummy_setup(idx[0])

    for k in (0.75, 1.00, 1.25):
        cfg = ExecutionConfig(breakeven_trigger_r=k)
        sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)
        assert sim is not None
        assert sim.trade.exit_reason == "target"
        assert sim.trade.exit_price == pytest.approx(102.0)
        assert sim.trade.r_multiple == pytest.approx(2.0)


def test_pit_future_price_mutation_invariance() -> None:
    """Mutating future prices cannot change whether any threshold was armed at bar T."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=5, freq="5min", tz="America/New_York")
    base_df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.5, 100.8, 101.0],
            "high": [100.0, 101.3, 101.5, 101.8, 101.9],  # Bar 1 hits all 3 thresholds (101.3 >= 101.25)
            "low": [99.0, 100.1, 100.3, 100.6, 100.7],
            "close": [99.8, 100.8, 101.0, 101.2, 101.5],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )
    setup = _make_dummy_setup(idx[0])

    for k in (0.75, 1.00, 1.25):
        cfg = ExecutionConfig(breakeven_trigger_r=k)
        sim_orig = simulate_trade_execution(base_df, setup_bar_idx=0, setup=setup, config=cfg)
        assert sim_orig is not None
        assert sim_orig.trade.be_triggered is True
        assert sim_orig.trade.be_trigger_time == idx[1]

        # Mutate future bars wildly
        mutated_df = base_df.copy()
        mutated_df.loc[idx[3], "high"] = 999.0
        mutated_df.loc[idx[4], "low"] = 1.0

        sim_mut = simulate_trade_execution(mutated_df, setup_bar_idx=0, setup=setup, config=cfg)
        assert sim_mut is not None
        assert sim_mut.trade.be_triggered is True
        assert sim_mut.trade.be_trigger_time == idx[1]


# ---------------------------------------------------------------------
# 3. Integration & Regression Validation
# ---------------------------------------------------------------------

def test_day07a_regression_and_invariants() -> None:
    """DAY-07A sample run:
    1. Trade counts match baseline for all variants.
    2. Monotonicity holds.
    3. Report formatting contains all required sections.
    """
    prov = get_provider()
    symbols = ["AAPL", "MSFT"]

    exp = run_day07a_robustness_experiment(
        symbols=symbols,
        start_date="2026-07-02",
        end_date="2026-07-15",
        provider=prov,
    )

    base_cnt = exp.baseline.metrics.total_trades
    assert base_cnt > 0

    # Trade counts must be identical across all variants
    for k_str, res in exp.threshold_variants.items():
        assert res.metrics.total_trades == base_cnt, f"{k_str} trade count must match baseline"

    # Monotonic trigger eligibility check
    trig_075 = exp.threshold_variants["0.75R"].be_diagnostics.be_triggered_trades  # type: ignore[union-attr]
    trig_100 = exp.threshold_variants["1.00R"].be_diagnostics.be_triggered_trades  # type: ignore[union-attr]
    trig_125 = exp.threshold_variants["1.25R"].be_diagnostics.be_triggered_trades  # type: ignore[union-attr]
    assert trig_075 >= trig_100 >= trig_125

    # Report sections check
    report = format_dynamic_stop_robustness_report(exp)
    assert "DAY-07A — H2 Stop Management Robustness" in report
    assert "1. REQUIRED COMPARISON TABLE" in report
    assert "2. SYMBOL-LEVEL DISTRIBUTION SUMMARY" in report
    assert "3. EXIT REASON DISTRIBUTION ACROSS VARIANTS" in report
    assert "4. BREAKEVEN ACTIVATION & FOLLOW-THROUGH DIAGNOSTICS" in report
    assert "5. PAIRED COUNTERFACTUAL TRANSITION MATRICES" in report
    assert "6. GIVE-BACK DIAGNOSTICS" in report
    assert "7. STOP GEOMETRY & HOLDING DURATION DIAGNOSTICS" in report
    assert "8. CROSS-THRESHOLD STABILITY ANALYSIS" in report
    assert "9. MONOTONICITY & REGRESSION VALIDATION" in report
    assert "10. POINT-IN-TIME VERIFICATION" in report
    assert "11. LIMITATIONS & RESEARCH INTERPRETATION" in report
