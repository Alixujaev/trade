"""tests/test_day07_point_in_time.py: Point-in-time safety and adversarial mutation tests for DAY-07."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.day_types import (
    DaySetupStatus,
    ExecutionConfig,
)
from backtest.dynamic_stop import run_day07_dynamic_stop_experiment
from backtest.execution import simulate_trade_execution
from data.factory import get_provider
from strategy.day.types import DaySetup


def _make_pit_setup(
    timestamp: pd.Timestamp,
    price: float = 100.0,
) -> DaySetup:
    return DaySetup(
        symbol="TEST",
        timestamp=timestamp,
        status=DaySetupStatus.CONFIRMED,
        price=price,
        vwap=99.5,
        rsi=55.0,
        rvol=2.5,
    )


def test_future_price_mutation_safety() -> None:
    """Changing future 5m prices after bar T must not change whether BE was armed at T."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=5, freq="5min", tz="America/New_York")
    base_df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.5, 100.8, 101.0],
            "high": [100.0, 101.2, 101.5, 101.8, 101.9],  # Bar 1 high = 101.2 (>= +1R)
            "low": [99.0, 100.1, 100.3, 100.6, 100.7],   # Setup bar low = 99.0
            "close": [99.8, 100.5, 100.8, 101.0, 101.2],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )

    setup = _make_pit_setup(idx[0])
    cfg = ExecutionConfig(breakeven_trigger_r=1.0)

    sim_orig = simulate_trade_execution(base_df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim_orig is not None
    assert sim_orig.trade.be_triggered is True
    assert sim_orig.trade.be_trigger_time == idx[1]

    # Mutate future bars (Bar 3 and Bar 4) wildly
    mutated_df = base_df.copy()
    mutated_df.loc[idx[3], "high"] = 500.0
    mutated_df.loc[idx[4], "low"] = 1.0

    sim_mut = simulate_trade_execution(mutated_df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim_mut is not None
    # Arming at bar 1 must remain 100% invariant
    assert sim_mut.trade.be_triggered is True
    assert sim_mut.trade.be_trigger_time == idx[1]


def test_future_volume_mutation_safety() -> None:
    """Changing future volume must not change BE activation."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=4, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.5, 100.2],
            "high": [100.0, 101.2, 101.4, 100.8],
            "low": [99.0, 100.1, 100.0, 99.5],
            "close": [99.8, 100.5, 100.2, 99.9],
            "volume": [1000.0, 1000.0, 50_000_000.0, 100_000_000.0],  # Wild volume in future
        },
        index=idx,
    )
    setup = _make_pit_setup(idx[0])
    cfg = ExecutionConfig(breakeven_trigger_r=1.0)

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim is not None
    assert sim.trade.be_triggered is True
    assert sim.trade.be_trigger_time == idx[1]


def test_same_bar_safety() -> None:
    """A candle with high >= +1R and low <= entry must NOT produce a same-bar BE exit.
    BE may only become active on the NEXT bar.
    """
    idx = pd.date_range("2026-07-02 09:30:00", periods=3, freq="5min", tz="America/New_York")
    # Entry 100, Stop 99, Target 102.
    # Bar 1: High 101.5 (>= 101), Low 99.8 (<= 100 entry).
    # Since original stop is 99.0, Low 99.8 does NOT hit stop.
    # But Low 99.8 IS <= 100.0. If BE were active on Bar 1, it would prematurely exit.
    # Rule requires BE to activate only on NEXT bar!
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.5],
            "high": [100.0, 101.5, 100.8],
            "low": [99.0, 99.8, 99.9],  # Bar 1 low is 99.8 (below entry 100, above stop 99)
            "close": [99.8, 100.6, 100.0],
            "volume": [1000.0] * 3,
        },
        index=idx,
    )

    setup = _make_pit_setup(idx[0])
    cfg = ExecutionConfig(breakeven_trigger_r=1.0)

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim is not None
    # Must NOT have exited on Bar 1
    assert sim.trade.exit_time == idx[2], "Must exit on Bar 2 (when BE became active), NOT on Bar 1"
    assert sim.trade.exit_reason == "breakeven"
    assert sim.trade.be_triggered is True
    assert sim.trade.be_trigger_time == idx[1]


def test_entry_safety_no_be_before_entry() -> None:
    """BE trigger must never occur before the trade entry."""
    idx = pd.date_range("2026-07-02 09:30:00", periods=3, freq="5min", tz="America/New_York")
    # Bar 0 (setup candle) had high 105.0. But trade hasn't entered yet!
    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 99.8],
            "high": [105.0, 100.4, 99.5],
            "low": [99.0, 99.2, 98.5],
            "close": [99.8, 99.5, 98.8],
            "volume": [1000.0] * 3,
        },
        index=idx,
    )
    setup = _make_pit_setup(idx[0])
    cfg = ExecutionConfig(breakeven_trigger_r=1.0)

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim is not None
    # Setup bar high cannot trigger BE for a trade not yet open!
    assert sim.trade.be_triggered is False
    assert sim.trade.exit_reason == "stop"


def test_session_safety_no_leak() -> None:
    """No BE state may leak into another trading session."""
    idx_day1 = pd.date_range("2026-07-02 15:45:00", periods=3, freq="5min", tz="America/New_York")
    idx_day2 = pd.date_range("2026-07-03 09:30:00", periods=3, freq="5min", tz="America/New_York")
    all_idx = idx_day1.append(idx_day2)

    df = pd.DataFrame(
        {
            "open": [99.5, 100.0, 100.8, 100.5, 100.2, 99.5],
            "high": [100.0, 101.5, 101.0, 101.0, 100.5, 100.0],  # 15:50 hits +1R
            "low": [99.0, 100.1, 100.4, 100.0, 99.8, 99.0],
            "close": [99.8, 100.8, 100.5, 100.2, 100.0, 99.2],
            "volume": [1000.0] * 6,
        },
        index=all_idx,
    )

    setup = _make_pit_setup(all_idx[0])
    cfg = ExecutionConfig(breakeven_trigger_r=1.0)

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)
    assert sim is not None
    # Trade MUST be forced closed at 15:55 on Day 1 (idx_day1[2])
    assert sim.trade.exit_time == idx_day1[2]
    assert sim.trade.exit_reason == "forced_eod"


def test_symbol_isolation_and_order_independence() -> None:
    """Running symbols in different order must yield identical per-symbol results."""
    prov = get_provider()
    syms_order1 = ["AAPL", "MSFT"]
    syms_order2 = ["MSFT", "AAPL"]

    exp1 = run_day07_dynamic_stop_experiment(
        symbols=syms_order1,
        start_date="2026-07-02",
        end_date="2026-07-08",
        provider=prov,
    )
    exp2 = run_day07_dynamic_stop_experiment(
        symbols=syms_order2,
        start_date="2026-07-02",
        end_date="2026-07-08",
        provider=prov,
    )

    for sym in ["AAPL", "MSFT"]:
        m1 = exp1.symbols_comparison[sym]
        m2 = exp2.symbols_comparison[sym]
        assert m1["trades"] == m2["trades"]
        assert m1["baseline_win_rate"] == pytest.approx(m2["baseline_win_rate"])
        assert m1["h2_win_rate"] == pytest.approx(m2["h2_win_rate"])
        assert m1["baseline_total_R"] == pytest.approx(m2["baseline_total_R"])
        assert m1["h2_total_R"] == pytest.approx(m2["h2_total_R"])
