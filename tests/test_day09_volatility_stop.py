"""tests/test_day09_volatility_stop.py: DAY-09 H4 Volatility-Scaled (ATR) Stop Distance tests.

1. ATR stop distance depends only on point-in-time ATR and the multiplier.
2. Future OHLCV mutation does not change ATR/stop/target of an earlier signal.
3. The forming (entry) candle is not part of the ATR.
4. stop < entry < target and target distance == 2 x stop risk, for every multiplier.
5. Same-bar STOP/TARGET ambiguity stays STOP_FIRST.
6. Baseline (SIGNAL_LOW) execution is unchanged by the H4 code path.
7. H4 does not change entry timestamps or the signal population; ATR gaps are reported.
8. Invalid ATR is never silently accepted.
Cache immutability is enforced for all tests by tests/conftest.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.day_types import DaySetupStatus, ExecutionConfig
from backtest.execution import simulate_trade_execution
from backtest.volatility_stop import (
    BASELINE_EXPECTED,
    H4_MULTIPLIERS,
    REASON_ATR_WARMUP_NAN,
    atr_at_signal,
    h4_execution_config,
    run_day09_volatility_stop_experiment,
    variant_name,
)
from data.factory import get_provider
from indicators.atr import compute_atr
from strategy.day.types import DaySetup


def _synthetic_5m(n: int = 40, seed: int = 7, day: str = "2026-07-09") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{day} 09:30", periods=n, freq="5min", tz="America/New_York").tz_convert("UTC")
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.3, n))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.4, n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.4, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.uniform(1e5, 5e5, n)},
        index=idx,
    )


def _setup(df: pd.DataFrame, idx: int) -> DaySetup:
    return DaySetup(
        symbol="TEST",
        timestamp=df.index[idx],
        status=DaySetupStatus.CONFIRMED,
        price=float(df["close"].iloc[idx]),
        vwap=float(df["close"].iloc[idx]) - 0.5,
        rsi=55.0,
        rvol=2.5,
    )


def _hand_atr(df: pd.DataFrame, idx: int, period: int = 14) -> float:
    trs = []
    for j in range(idx - period + 1, idx + 1):
        h, l = df["high"].iloc[j], df["low"].iloc[j]
        pc = df["close"].iloc[j - 1] if j > 0 else np.nan
        cand = [h - l] + ([] if np.isnan(pc) else [abs(h - pc), abs(l - pc)])
        trs.append(max(cand))
    return float(np.mean(trs))


SETUP_IDX = 20


# ---- 1. stop distance = point-in-time ATR x multiplier ----

@pytest.mark.parametrize("mult", H4_MULTIPLIERS)
def test_atr_stop_distance_is_atr_times_multiplier(mult):
    df = _synthetic_5m()
    atr = atr_at_signal(df, SETUP_IDX)
    assert atr == pytest.approx(_hand_atr(df, SETUP_IDX), rel=1e-12)

    sim = simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), h4_execution_config(mult), atr_value=atr)
    entry = float(df["open"].iloc[SETUP_IDX + 1])
    assert sim is not None
    assert sim.trade.risk_per_share == pytest.approx(atr * mult, rel=1e-12)
    assert sim.trade.stop_price == pytest.approx(entry - atr * mult, rel=1e-12)
    assert sim.trade.target_price == pytest.approx(entry + 2.0 * atr * mult, rel=1e-12)
    assert sim.trade.entry_time == df.index[SETUP_IDX + 1]


def test_atr_at_signal_matches_full_series_rolling_value():
    """Runner uses the causal full-series ATR as a speed-up; it must equal the truncated computation."""
    df = _synthetic_5m()
    full = compute_atr(df)
    for i in range(13, len(df)):
        assert atr_at_signal(df, i) == pytest.approx(float(full.iloc[i]), rel=1e-12)
    for i in range(13):
        assert np.isnan(atr_at_signal(df, i))


# ---- 2. future mutation ----

@pytest.mark.parametrize("factor", [5.0, 0.2])
def test_future_ohlcv_mutation_does_not_change_atr_or_stop(factor):
    df = _synthetic_5m()
    mutated = df.copy()
    future = mutated.index > df.index[SETUP_IDX]
    mutated.loc[future, ["open", "high", "low", "close"]] *= factor
    mutated.loc[future, "volume"] *= 1000.0
    # keep the entry OPEN identical so stop/target can be compared exactly
    mutated.iloc[SETUP_IDX + 1, mutated.columns.get_loc("open")] = df["open"].iloc[SETUP_IDX + 1]

    atr_clean = atr_at_signal(df, SETUP_IDX)
    atr_mut = atr_at_signal(mutated, SETUP_IDX)
    assert atr_clean == atr_mut

    for mult in H4_MULTIPLIERS:
        a = simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), h4_execution_config(mult), atr_value=atr_clean)
        b = simulate_trade_execution(mutated, SETUP_IDX, _setup(df, SETUP_IDX), h4_execution_config(mult), atr_value=atr_mut)
        assert a.trade.stop_price == b.trade.stop_price
        assert a.trade.target_price == b.trade.target_price
        assert a.trade.risk_per_share == b.trade.risk_per_share


# ---- 3. forming candle excluded ----

def test_forming_entry_candle_not_in_atr_but_closed_signal_bar_is():
    df = _synthetic_5m()
    base = atr_at_signal(df, SETUP_IDX)

    forming = df.copy()  # T+1 bar is still forming at signal_time
    forming.iloc[SETUP_IDX + 1, forming.columns.get_loc("high")] *= 3.0
    forming.iloc[SETUP_IDX + 1, forming.columns.get_loc("low")] *= 0.3
    assert atr_at_signal(forming, SETUP_IDX) == base

    closed = df.copy()  # the signal bar itself is closed at signal_time -> must be included
    closed.iloc[SETUP_IDX, closed.columns.get_loc("high")] += 10.0
    assert atr_at_signal(closed, SETUP_IDX) != base


# ---- 4. geometry ----

@pytest.mark.parametrize("mult", H4_MULTIPLIERS)
@pytest.mark.parametrize("setup_idx", [13, 20, 30])
def test_geometry_stop_below_target_above_exact_2r(mult, setup_idx):
    df = _synthetic_5m()
    atr = atr_at_signal(df, setup_idx)
    t = simulate_trade_execution(df, setup_idx, _setup(df, setup_idx), h4_execution_config(mult), atr_value=atr).trade
    entry = float(df["open"].iloc[setup_idx + 1])
    assert t.stop_price < entry < t.target_price
    assert (t.target_price - entry) == pytest.approx(2.0 * (entry - t.stop_price), abs=1e-9)
    assert t.initial_stop_price == t.stop_price


# ---- 5. same-bar ambiguity ----

def test_same_bar_stop_and_target_is_stop_first():
    df = _synthetic_5m()
    atr = atr_at_signal(df, SETUP_IDX)
    cfg = h4_execution_config(1.0)
    entry = float(df["open"].iloc[SETUP_IDX + 1])
    j = SETUP_IDX + 1
    df.iloc[j, df.columns.get_loc("high")] = entry + 3.0 * atr  # >= target
    df.iloc[j, df.columns.get_loc("low")] = entry - 3.0 * atr   # <= stop
    sim = simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), cfg, atr_value=atr)
    assert sim.was_ambiguous is True
    assert sim.trade.exit_reason == "stop"
    assert sim.trade.exit_price == pytest.approx(entry - atr)
    assert sim.trade.r_multiple == pytest.approx(-1.0)


# ---- 6. baseline execution unchanged ----

def test_signal_low_path_ignores_atr_value():
    df = _synthetic_5m()
    cfg = ExecutionConfig()
    a = simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), cfg)
    b = simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), cfg, atr_value=123.0)
    assert a == b
    assert cfg.stop_mode == "SIGNAL_LOW" and cfg.atr_stop_multiplier is None


# ---- 8. invalid ATR is never silent ----

@pytest.mark.parametrize("bad", [None, float("nan"), 0.0, -1.0, float("inf")])
def test_invalid_atr_raises(bad):
    df = _synthetic_5m()
    with pytest.raises(ValueError):
        simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), h4_execution_config(1.0), atr_value=bad)


def test_invalid_multiplier_raises():
    df = _synthetic_5m()
    cfg = ExecutionConfig(stop_mode="ATR", atr_stop_multiplier=None)
    with pytest.raises(ValueError):
        simulate_trade_execution(df, SETUP_IDX, _setup(df, SETUP_IDX), cfg, atr_value=1.0)


# ---- 6/7. frozen experiment: baseline regression + population ----

@pytest.fixture(scope="module")
def day09_result():
    return run_day09_volatility_stop_experiment(provider=get_provider())


def test_baseline_regression_unchanged(day09_result):
    b = day09_result.metrics["BASELINE"]
    assert b.total_trades == BASELINE_EXPECTED["total_trades"]
    assert abs(b.win_rate - 0.3042) <= 0.0001
    assert abs(b.profit_factor - 0.9388) <= 0.0005
    assert abs(b.total_R - (-738.98)) <= 0.01
    assert abs(b.gross_return_compounded - (-41.19)) <= 0.01
    assert day09_result.baseline_regression["regression_verified"] is True


def test_population_and_entries_unchanged(day09_result):
    cov = day09_result.coverage
    assert cov["h4_evaluable_trades"] + cov["h4_insufficient_trades"] == BASELINE_EXPECTED["total_trades"]
    assert sum(cov["insufficient_by_reason"].values()) == cov["h4_insufficient_trades"]
    assert day09_result.metrics["BASELINE_EVALUABLE"].total_trades == cov["h4_evaluable_trades"]
    for m in H4_MULTIPLIERS:
        d = day09_result.diagnostics[variant_name(m)]
        assert day09_result.metrics[variant_name(m)].total_trades == cov["h4_evaluable_trades"]
        assert d.population == cov["h4_evaluable_trades"]
        assert d.entry_time_matches_baseline == d.population
        assert d.entry_price_matches_baseline == d.population
        assert sum(sum(r.values()) for r in d.transition_vs_baseline.values()) == d.population


def test_insufficient_atr_is_only_warmup(day09_result):
    """ATR(14) needs 14 bars: only 2026-07-02 signals before ATR exists may be insufficient."""
    for t in day09_result.insufficient_trades:
        assert t.reason == REASON_ATR_WARMUP_NAN
        assert t.session == "2026-07-02"
        ts = pd.Timestamp(t.setup_time).tz_convert("America/New_York")
        assert ts.time() < pd.Timestamp("10:35").time()


@pytest.mark.parametrize("mult", H4_MULTIPLIERS)
def test_h4_risk_equals_atr_multiple(day09_result, mult):
    d = day09_result.diagnostics[variant_name(mult)]
    for k in ("p10", "median", "p90"):
        assert d.risk_atr_multiple[k] == pytest.approx(mult, abs=1e-4)
