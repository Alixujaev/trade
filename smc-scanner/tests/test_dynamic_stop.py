"""tests/test_dynamic_stop.py: Unit tests and reference fixtures for DAY-07 H2 dynamic stop management."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.day_types import (
    DaySetupStatus,
    ExecutionConfig,
)
from backtest.execution import simulate_trade_execution
from strategy.day.types import DaySetup


def _make_dummy_setup(
    symbol: str = "TEST",
    setup_time: pd.Timestamp = pd.Timestamp("2026-07-02 09:40:00", tz="America/New_York"),
    price: float = 100.0,
) -> DaySetup:
    """Create a standardized dummy DaySetup fixture."""
    return DaySetup(
        symbol=symbol,
        timestamp=setup_time,
        status=DaySetupStatus.CONFIRMED,
        price=price,
        vwap=99.5,
        rsi=55.0,
        rvol=2.5,
        structure_5m="BULLISH",
        structure_15m="BULLISH",
        evidence=("VWAP reclaim", "RSI momentum"),
        warnings=(),
    )


def test_case_1_ordinary_stop() -> None:
    """Case 1 — ordinary stop:
    Entry 100, Stop 99, Target 102 (R = 1)
    Next bar: High 100.5, Low 98.8
    Expected: STOP, -1R, BE not triggered.
    """
    idx = pd.date_range("2026-07-02 09:40:00", periods=3, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.8, 100.0, 99.5],
            "high": [100.0, 100.5, 100.0],
            "low": [99.0, 98.8, 98.5],  # Setup bar low = 99.0 -> Stop = 99.0
            "close": [100.0, 99.0, 99.0],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=idx,
    )

    setup = _make_dummy_setup(setup_time=idx[0], price=100.0)
    config = ExecutionConfig(
        slippage_bps=0.0,
        commission_per_share=0.0,
        target_multiple=2.0,
        breakeven_trigger_r=1.0,
    )

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=config)
    assert sim is not None
    t = sim.trade
    assert t.exit_reason == "stop"
    assert t.exit_price == pytest.approx(99.0)
    assert t.r_multiple == pytest.approx(-1.0)
    assert t.be_triggered is False
    assert t.be_trigger_time is None
    assert t.effective_exit_stop_price == pytest.approx(99.0)


def test_case_2_plus_1r_then_next_bar_be() -> None:
    """Case 2 — +1R then next-bar BE:
    Entry 100, Stop 99, Target 102
    Bar 1: High 101.2, Low 100.2
    Bar 2: High 100.8, Low 99.8
    Expected:
      Bar 1 -> BE armed
      Bar 2 -> BREAKEVEN
    """
    idx = pd.date_range("2026-07-02 09:40:00", periods=3, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.8, 100.0, 100.5],
            "high": [100.0, 101.2, 100.8],
            "low": [99.0, 100.2, 99.8],  # Setup bar low = 99.0
            "close": [100.0, 100.5, 99.9],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=idx,
    )

    setup = _make_dummy_setup(setup_time=idx[0], price=100.0)
    config = ExecutionConfig(
        slippage_bps=0.0,
        commission_per_share=0.0,
        target_multiple=2.0,
        breakeven_trigger_r=1.0,
    )

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=config)
    assert sim is not None
    t = sim.trade
    assert t.exit_reason == "breakeven"
    assert t.exit_price == pytest.approx(100.0)
    assert t.r_multiple == pytest.approx(0.0)
    assert t.gross_return == pytest.approx(0.0)
    assert t.be_triggered is True
    assert t.be_trigger_time == idx[1]
    assert t.effective_exit_stop_price == pytest.approx(100.0)
    assert t.exit_time == idx[2]


def test_case_3_plus_1r_and_target_on_same_trigger_bar() -> None:
    """Case 3 — +1R and target on same trigger bar:
    Entry 100, Stop 99, Target 102
    Bar 1: High 102.2, Low 100.2
    Expected:
      TARGET (+2R)
    """
    idx = pd.date_range("2026-07-02 09:40:00", periods=2, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.8, 100.0],
            "high": [100.0, 102.2],
            "low": [99.0, 100.2],  # Setup bar low = 99.0
            "close": [100.0, 102.0],
            "volume": [1000.0, 1000.0],
        },
        index=idx,
    )

    setup = _make_dummy_setup(setup_time=idx[0], price=100.0)
    config = ExecutionConfig(
        slippage_bps=0.0,
        commission_per_share=0.0,
        target_multiple=2.0,
        breakeven_trigger_r=1.0,
    )

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=config)
    assert sim is not None
    t = sim.trade
    assert t.exit_reason == "target"
    assert t.exit_price == pytest.approx(102.0)
    assert t.r_multiple == pytest.approx(2.0)
    assert t.exit_time == idx[1]


def test_case_4_plus_1r_and_stop_range_ambiguity_on_same_bar() -> None:
    """Case 4 — +1R and stop-range ambiguity on same bar:
    Entry 100, Stop 99, Target 102
    Bar 1: High 101.2, Low 99.0
    Expected:
      Original stop semantics apply
      BE is NOT active during Bar 1
    """
    idx = pd.date_range("2026-07-02 09:40:00", periods=2, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [99.8, 100.0],
            "high": [100.0, 101.2],
            "low": [99.0, 99.0],  # Bar 1 low touches original stop (99.0)
            "close": [100.0, 99.2],
            "volume": [1000.0, 1000.0],
        },
        index=idx,
    )

    setup = _make_dummy_setup(setup_time=idx[0], price=100.0)
    config = ExecutionConfig(
        slippage_bps=0.0,
        commission_per_share=0.0,
        target_multiple=2.0,
        breakeven_trigger_r=1.0,
        same_bar_rule="STOP_FIRST",
    )

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=config)
    assert sim is not None
    t = sim.trade
    assert t.exit_reason == "stop"
    assert t.exit_price == pytest.approx(99.0)
    assert t.r_multiple == pytest.approx(-1.0)
    assert t.be_triggered is False


def test_case_5_multiple_bars_after_be() -> None:
    """Case 5 — multiple bars after BE:
    Verify BE remains active until TARGET, BREAKEVEN, or FORCED_EXIT.
    """
    idx = pd.date_range("2026-07-02 09:40:00", periods=5, freq="5min", tz="America/New_York")
    # Sub-case A: Survives Bar 2, hits BE on Bar 3
    df_a = pd.DataFrame(
        {
            "open": [99.8, 100.0, 100.8, 100.4, 99.5],
            "high": [100.0, 101.2, 101.5, 100.8, 100.0],
            "low": [99.0, 100.2, 100.2, 100.0, 99.0],  # Bar 3 touches 100.0 (BE)
            "close": [100.0, 100.8, 100.5, 100.1, 99.2],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )
    setup = _make_dummy_setup(setup_time=idx[0], price=100.0)
    config = ExecutionConfig(
        slippage_bps=0.0,
        commission_per_share=0.0,
        target_multiple=2.0,
        breakeven_trigger_r=1.0,
    )
    sim_a = simulate_trade_execution(df_a, setup_bar_idx=0, setup=setup, config=config)
    assert sim_a is not None
    assert sim_a.trade.exit_reason == "breakeven"
    assert sim_a.trade.exit_price == pytest.approx(100.0)
    assert sim_a.trade.exit_time == idx[3]
    assert sim_a.trade.be_triggered is True
    assert sim_a.trade.be_trigger_time == idx[1]

    # Sub-case B: Survives Bar 2, hits TARGET on Bar 3
    df_b = pd.DataFrame(
        {
            "open": [99.8, 100.0, 100.8, 101.0, 101.5],
            "high": [100.0, 101.2, 101.5, 102.5, 102.0],  # Bar 3 hits target (102.0)
            "low": [99.0, 100.2, 100.3, 100.8, 101.0],
            "close": [100.0, 100.8, 101.0, 102.1, 101.8],
            "volume": [1000.0] * 5,
        },
        index=idx,
    )
    sim_b = simulate_trade_execution(df_b, setup_bar_idx=0, setup=setup, config=config)
    assert sim_b is not None
    assert sim_b.trade.exit_reason == "target"
    assert sim_b.trade.exit_price == pytest.approx(102.0)
    assert sim_b.trade.r_multiple == pytest.approx(2.0)
    assert sim_b.trade.exit_time == idx[3]
    assert sim_b.trade.be_triggered is True
    assert sim_b.trade.effective_exit_stop_price == pytest.approx(100.0)
