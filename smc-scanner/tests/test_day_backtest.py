"""tests/test_day_backtest.py: DAY-02 — VWAP Momentum Backtest Engine uchun deterministik testlar."""

from __future__ import annotations

from datetime import time
import pandas as pd
import pytest

from backtest.day_engine import format_day_backtest_report, run_day_backtest
from backtest.day_types import ExecutionConfig
from backtest.execution import simulate_trade_execution
from backtest.metrics import compute_day_metrics
from strategy.day.types import DaySetup, DaySetupStatus, VwapRelation


def _make_intraday_series(
    start_str: str,
    n_bars: int,
    base_price: float = 100.0,
    price_deltas: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    """5m barlar DataFrame'ini yaratadi."""
    idx = pd.date_range(start_str, periods=n_bars, freq="5min", tz="America/New_York")
    closes = []
    curr = base_price
    for i in range(n_bars):
        delta = price_deltas[i] if price_deltas and i < len(price_deltas) else 0.0
        curr += delta
        closes.append(curr)

    vols = volumes if volumes else [1000.0] * n_bars
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = [c - 0.1 for c in closes]

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=idx,
    )


def test_entry_is_next_bar_open() -> None:
    """Signal T barida bo'lsa, kirish aniq T+1 barining OPEN narxida bo'ladi."""
    idx = pd.date_range("2026-01-05 09:30", periods=5, freq="5min", tz="America/New_York")
    # Bar 0 (T): setup bar
    # Bar 1 (T+1): open = 105.0
    opens = [100.0, 105.0, 106.0, 107.0, 108.0]
    closes = [100.5, 106.0, 107.0, 108.0, 109.0]
    highs = [101.0, 106.5, 107.5, 108.5, 109.5]
    lows = [99.5, 104.5, 105.5, 106.5, 107.5]
    df = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0]*5}, index=idx)

    setup = DaySetup(
        symbol="AAPL",
        timestamp=df.index[0],
        status=DaySetupStatus.DETECTED,
        price=100.5,
        vwap=100.0,
    )

    config = ExecutionConfig(slippage_bps=0.0, commission_per_share=0.0)
    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=config)

    assert sim is not None
    assert sim.trade.entry_price == 105.0
    assert sim.trade.entry_time == df.index[1]


def test_no_entry_without_next_bar() -> None:
    """Agar signal oxirgi barda bo'lsa (keyingi bar mavjud emas), trade ochilmaydi."""
    idx = pd.date_range("2026-01-05 09:30", periods=2, freq="5min", tz="America/New_York")
    df = pd.DataFrame({"open": [100.0, 101.0], "high": [101.0, 102.0], "low": [99.0, 100.0], "close": [100.5, 101.5], "volume": [1000.0, 1000.0]}, index=idx)

    setup = DaySetup(symbol="AAPL", timestamp=df.index[1], status=DaySetupStatus.DETECTED)
    config = ExecutionConfig()

    sim = simulate_trade_execution(df, setup_bar_idx=1, setup=setup, config=config)
    assert sim is None


def test_force_exit_at_1555() -> None:
    """15:55 ET ga yetganda ochiq pozitsiya majburiy (forced_eod) ravishda yopiladi."""
    # 09:30 dan 16:00 gacha 78 ta bar
    idx = pd.date_range("2026-01-05 09:30", periods=78, freq="5min", tz="America/New_York")
    # Narx bir xil 100 da ushlab turiladi (stop=98.0 va target=110.0 ga yetmaydi)
    lows = [99.5]*78
    lows[10] = 98.0  # signal bar low = 98.0 -> stop_price = 98.0
    df = pd.DataFrame(
        {"open": [100.0]*78, "high": [100.5]*78, "low": lows, "close": [100.0]*78, "volume": [1000.0]*78},
        index=idx,
    )

    setup = DaySetup(symbol="AAPL", timestamp=df.index[10], status=DaySetupStatus.DETECTED, vwap=99.0)
    config = ExecutionConfig(
        stop_mode="SIGNAL_LOW",
        target_multiple=5.0,  # yiroq target (100 + 5*2 = 110)
        force_exit_time=time(15, 55),
    )

    sim = simulate_trade_execution(df, setup_bar_idx=10, setup=setup, config=config)

    assert sim is not None
    assert sim.trade.exit_reason == "forced_eod"
    # 15:55 bari (index 77)
    assert sim.trade.exit_time == pd.Timestamp("2026-01-05 15:55", tz="America/New_York")


def test_same_bar_stop_target_uses_deterministic_rule() -> None:
    """Bitta barda High>=TP va Low<=SL bo'lsa, 'STOP_FIRST' qoidasi qo'llanadi va ambiguitiy hisoblanadi."""
    idx = pd.date_range("2026-01-05 09:30", periods=5, freq="5min", tz="America/New_York")
    # Bar 0: setup (low=98.0, open=100, close=100) -> SL = 98.0 (risk = 2.0), TP = 100 + 2*2 = 104.0
    # Bar 1: entry at open=100.0
    # Bar 2: high = 105.0 (>=TP), low = 95.0 (<=SL) -> ikkalasi ham bir barda!
    opens = [100.0, 100.0, 100.0, 100.0, 100.0]
    highs = [101.0, 101.0, 105.0, 101.0, 101.0]
    lows = [98.0, 99.0, 95.0, 99.0, 99.0]
    closes = [100.0, 100.0, 100.0, 100.0, 100.0]
    df = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0]*5}, index=idx)

    setup = DaySetup(symbol="AAPL", timestamp=df.index[0], status=DaySetupStatus.DETECTED, vwap=99.0)
    config = ExecutionConfig(
        stop_mode="SIGNAL_LOW",
        target_multiple=2.0,
        same_bar_rule="STOP_FIRST",
    )

    sim = simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=config)

    assert sim is not None
    assert sim.was_ambiguous is True
    assert sim.trade.exit_reason == "stop"
    assert sim.trade.exit_price == pytest.approx(98.0)


def test_no_overlapping_positions() -> None:
    """Pozitsiya ochiq turganda paydo bo'lgan yangi signallar o'tkazib yuboriladi."""
    # 30 ta bar: bir nechta reclaim signallari ketma-ket
    n = 30
    deltas = [0.0] * 17 + [-1.0, 0.2, 1.6] + [0.1] * 10
    df_5m = _make_intraday_series("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas)

    config = ExecutionConfig(
        stop_mode="SIGNAL_LOW",
        target_multiple=10.0,  # pozitsiya uzoq ushlab turiladi
    )

    result = run_day_backtest("AAPL", df_5m=df_5m, config=config)

    # Bir vaqtning o'zida faqat 1 ta pozitsiya bo'lishi shart
    for i in range(len(result.trades) - 1):
        t1 = result.trades[i]
        t2 = result.trades[i + 1]
        assert t2.entry_time >= t1.exit_time


def test_future_bars_do_not_change_historical_trade() -> None:
    """Kelajak barlari (tarixiy oynadan keyin) o'tmishdagi savdolarning natijasini o'zgartirmaydi."""
    # Dataset A: 30 ta bar
    df_a = _make_intraday_series("2026-01-05 09:30", 30, base_price=100.0, price_deltas=[0.0]*17 + [-1.0, 0.2, 1.6] + [0.0]*10)

    # Dataset B: df_a + 20 ta kelajak bar keskin o'zgarishlar bilan
    df_b = _make_intraday_series("2026-01-05 09:30", 50, base_price=100.0, price_deltas=[0.0]*17 + [-1.0, 0.2, 1.6] + [0.0]*10 + [5.0]*20)

    config = ExecutionConfig()

    result_a = run_day_backtest("AAPL", df_5m=df_a, config=config)
    result_b = run_day_backtest("AAPL", df_5m=df_b, end_date=df_a.index[-1], config=config)

    assert len(result_a.trades) == len(result_b.trades)
    if result_a.trades:
        assert result_a.trades[0].entry_price == result_b.trades[0].entry_price
        assert result_a.trades[0].exit_price == result_b.trades[0].exit_price
        assert result_a.trades[0].net_return == result_b.trades[0].net_return


def test_metrics_calculation_deterministic() -> None:
    """Metrikalar hisoblash deterministik va to'g'ri."""
    from backtest.day_types import DayBacktestTrade

    now = pd.Timestamp("2026-01-05 10:00", tz="America/New_York")
    trades = [
        DayBacktestTrade(
            symbol="AAPL", setup_time=now, entry_time=now, entry_price=100.0,
            exit_time=now, exit_price=102.0, exit_reason="target",
            gross_return=0.02, net_return=0.02, risk_per_share=1.0, r_multiple=2.0,
        ),
        DayBacktestTrade(
            symbol="AAPL", setup_time=now, entry_time=now, entry_price=100.0,
            exit_time=now, exit_price=99.0, exit_reason="stop",
            gross_return=-0.01, net_return=-0.01, risk_per_share=1.0, r_multiple=-1.0,
        ),
    ]

    metrics = compute_day_metrics(trades, buy_and_hold_return=1.5)

    assert metrics["total_trades"] == 2
    assert metrics["winning_trades"] == 1
    assert metrics["losing_trades"] == 1
    assert metrics["win_rate"] == 0.5
    assert metrics["average_R"] == pytest.approx(0.5)
    assert metrics["buy_and_hold_return_pct"] == 1.5


def test_non_directive_backtest_report() -> None:
    """Backtest hisoboti non-directive bo'lib, 'STRONG BUY', 'PROFITABLE STRATEGY' so'zlari yo'q."""
    df_5m = _make_intraday_series("2026-01-05 09:30", 30, base_price=100.0, price_deltas=[0.0]*17 + [-1.0, 0.2, 1.6] + [0.0]*10)
    result = run_day_backtest("AAPL", df_5m=df_5m)

    report = format_day_backtest_report(result)

    assert "DAY-02 VWAP MOMENTUM BACKTEST" in report
    assert "BEST" not in report
    assert "WORST" not in report
    assert "STRONG BUY" not in report
    assert "PROFITABLE STRATEGY" not in report
    assert "EDGE CONFIRMED" not in report
    assert "These are historical observations, not a validated trading edge." in report
