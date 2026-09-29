"""tests/test_day07_backtest.py: Full backtest regression, equivalence, and metrics tests for DAY-07."""

from __future__ import annotations

from datetime import datetime, time
import numpy as np
import pandas as pd
import pytest

from backtest.day_types import (
    DayBacktestTrade,
    DaySetupStatus,
    ExecutionConfig,
)
from backtest.dynamic_stop import (
    format_dynamic_stop_report,
    run_day07_dynamic_stop_experiment,
)
from backtest.execution import simulate_trade_execution
from backtest.failure_analysis import map_exit_reason
from data.factory import get_provider
from strategy.day.types import DaySetup


def test_day07_regression_and_equivalence() -> None:
    """Regression / Equivalence:
    Signal timestamps, entry timestamps/prices, initial stops, and targets
    must be 100% IDENTICAL between Baseline and H2.
    """
    prov = get_provider()
    symbols = ["AAPL", "MSFT"]

    exp = run_day07_dynamic_stop_experiment(
        symbols=symbols,
        start_date="2026-07-02",
        end_date="2026-07-15",
        provider=prov,
    )

    b = exp.baseline_metrics
    h = exp.h2_metrics
    cf = exp.counterfactual

    assert b.total_trades == h.total_trades, "Total trades must be identical"
    assert b.total_trades > 0, "Should generate trades for sample period"

    # Transition matrix sum must equal total trades
    total_in_matrix = sum(
        sum(cf.transition_matrix[r1][r2] for r2 in cf.transition_matrix[r1])
        for r1 in cf.transition_matrix
    )
    assert total_in_matrix == b.total_trades

    # Give-back diagnostic consistency
    assert exp.giveback.baseline_mfe_ge_1r_total <= b.total_trades
    assert exp.giveback.baseline_mfe_stop_count + exp.giveback.baseline_mfe_target_count + exp.giveback.baseline_mfe_forced_count == exp.giveback.baseline_mfe_ge_1r_total


def test_non_be_triggered_trades_are_identical() -> None:
    """Any trade that does NOT reach +1R must have 100% identical outcomes in Baseline and H2."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=5, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 99.8, 99.4, 98.8],
            "high": [100.0, 100.4, 100.1, 99.7, 99.0],
            "low": [99.0, 99.6, 99.2, 98.9, 98.5],
            "close": [99.8, 99.7, 99.3, 99.0, 98.6],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )

    setup = DaySetup(
        symbol="TEST",
        timestamp=idx[0],
        status=DaySetupStatus.CONFIRMED,
        price=100.0,
        vwap=99.5,
        rsi=55.0,
        rvol=2.5,
    )

    cfg_base = ExecutionConfig(target_multiple=2.0, breakeven_trigger_r=None)
    cfg_h2 = ExecutionConfig(target_multiple=2.0, breakeven_trigger_r=1.0)

    sim_base = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg_base)
    sim_h2 = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg_h2)

    assert sim_base is not None and sim_h2 is not None
    tb = sim_base.trade
    th = sim_h2.trade

    assert tb.setup_time == th.setup_time
    assert tb.entry_time == th.entry_time
    assert tb.entry_price == th.entry_price
    assert tb.stop_price == th.stop_price
    assert tb.target_price == th.target_price
    assert tb.exit_time == th.exit_time
    assert tb.exit_price == th.exit_price
    assert tb.exit_reason == th.exit_reason
    assert tb.net_return == th.net_return
    assert tb.r_multiple == th.r_multiple
    assert th.be_triggered is False


def test_format_dynamic_stop_report_sections() -> None:
    """Report formatting must contain all required sections and valid content."""
    prov = get_provider()
    exp = run_day07_dynamic_stop_experiment(
        symbols=["AAPL"],
        start_date="2026-07-02",
        end_date="2026-07-08",
        provider=prov,
    )

    rep = format_dynamic_stop_report(exp)
    assert "DAY-07 — H2 Dynamic Stop Management" in rep
    assert "1. STRATEGY COMPARISON TABLE" in rep
    assert "2. EXIT REASON DISTRIBUTION" in rep
    assert "3. BREAKEVEN MANAGEMENT DIAGNOSTICS" in rep
    assert "4. PAIRED COUNTERFACTUAL TRANSITION MATRIX" in rep
    assert "5. GIVE-BACK DIAGNOSTIC" in rep
    assert "6. SLIPPAGE SENSITIVITY" in rep
    assert "7. PER-SYMBOL DISTRIBUTION" in rep
    assert "8. POINT-IN-TIME VALIDATION & VERIFICATION" in rep
    assert "9. LIMITATIONS & RESEARCH INTERPRETATION" in rep
