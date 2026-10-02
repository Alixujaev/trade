"""tests/test_day12b_breakeven.py: DAY-12B +0.5R -> Breakeven counterfactual tests.

- Synthetic bars through the REAL simulate_trade_execution with ExecutionConfig(breakeven_trigger_r=0.5).
- Fast/reference engine equivalence, candidate invariance, PIT on frozen AAPL data.
- Frozen-data paired experiment: baseline unchanged, identical population, accounting reconciles.
Cache immutability and network blocking are enforced for all tests by tests/conftest.py.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.breakeven_05 import DAY12B_BE_TRIGGER_R, be_config, resimulate_paired, run_day12b_experiment
from backtest.day_engine import run_day_backtest, run_day_backtest_reference
from backtest.day_types import ExecutionConfig
from backtest.execution import simulate_trade_execution
from backtest.frequency_cap import trade_fingerprint
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.time_window import load_regression_anchors
from data.factory import get_provider
from data.session import get_session_date, get_session_dates
from strategy.day.types import DaySetup, DaySetupStatus

BE = be_config()
BASE = ExecutionConfig()


def _df(rows, start="2026-08-10 13:30"):  # 13:30 UTC = 09:30 ET
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": [1000] * len(rows)}, index=idx)


def _sim(rows, cfg=BE, start="2026-08-10 13:30"):
    df = _df(rows, start)
    setup = DaySetup(symbol="T", timestamp=df.index[0], status=DaySetupStatus.CONFIRMED)
    return simulate_trade_execution(df, setup_bar_idx=0, setup=setup, config=cfg)


SIGNAL = (99.5, 100.2, 99.0, 100.0)  # signal low 99.0 -> stop 99, entry 100 -> R = 1, trigger 100.5, target 102
FLAT = (100.2, 100.3, 100.1, 100.2)


def test_only_one_threshold_and_config_is_opt_in():
    assert DAY12B_BE_TRIGGER_R == 0.5
    assert BE.breakeven_trigger_r == 0.5
    assert BASE.breakeven_trigger_r is None
    assert BE == ExecutionConfig(breakeven_trigger_r=0.5)  # nothing else changed vs the plain baseline


def test_be_not_activated_below_trigger():
    sim = _sim([SIGNAL, (100.0, 100.49, 99.6, 100.2), (100.2, 100.4, 99.9, 100.0), (100.0, 100.1, 98.9, 99.0)])
    t = sim.trade
    assert t.be_triggered is False and t.exit_reason == "stop" and t.r_multiple == pytest.approx(-1.0)


def test_be_needs_closed_bar_and_is_not_retroactive():
    # entry bar crosses +0.5R (high 100.6) AND trades below entry (low 99.8): BE must NOT apply on this bar
    sim = _sim([SIGNAL, (100.0, 100.6, 99.8, 100.3), (100.3, 100.4, 99.95, 100.0), FLAT])
    t = sim.trade
    assert t.be_triggered is True
    assert t.be_trigger_time == pd.Timestamp("2026-08-10 13:35", tz="UTC")   # the closed entry bar
    assert t.exit_reason == "breakeven" and t.exit_time == pd.Timestamp("2026-08-10 13:40", tz="UTC")
    assert t.exit_price == pytest.approx(100.0) and t.r_multiple == pytest.approx(0.0)


def test_be_stop_is_exactly_entry_and_original_r_and_target_unchanged():
    sim = _sim([SIGNAL, (100.0, 100.6, 99.8, 100.3), (100.3, 100.4, 99.95, 100.0)])
    t = sim.trade
    assert t.effective_exit_stop_price == t.entry_price == 100.0
    assert t.breakeven_price == 100.0
    assert t.initial_stop_price == t.stop_price == 99.0
    assert t.initial_risk_per_share == t.risk_per_share == pytest.approx(1.0)
    assert t.target_price == pytest.approx(100.0 + 2.0 * 1.0)


def test_stop_before_confirmation_remains_stop():
    # same bar crosses the trigger and the original stop: no BE (bar exits first), normal STOP
    sim = _sim([SIGNAL, (100.0, 100.7, 98.9, 99.2), FLAT])
    assert sim.trade.exit_reason == "stop" and sim.trade.be_triggered is False
    assert sim.trade.r_multiple == pytest.approx(-1.0)


def test_reach_half_r_then_return_gives_be():
    sim = _sim([SIGNAL, (100.0, 100.3, 99.7, 100.2), (100.2, 100.55, 100.1, 100.4), (100.4, 100.45, 99.5, 99.6)])
    t = sim.trade
    assert t.be_triggered and t.exit_reason == "breakeven" and t.r_multiple == pytest.approx(0.0)
    base = _sim([SIGNAL, (100.0, 100.3, 99.7, 100.2), (100.2, 100.55, 100.1, 100.4), (100.4, 100.45, 99.5, 99.6),
                 (99.6, 99.7, 98.9, 99.0)], cfg=BASE)
    assert base.trade.exit_reason == "stop"  # the same path without BE stops out at -1R


def test_same_bar_be_and_target_is_deterministic_stop_first():
    rows = [SIGNAL, (100.0, 100.6, 99.8, 100.3), (100.3, 102.5, 99.9, 101.0)]
    a, b = _sim(rows), _sim(rows)
    assert a.trade == b.trade and a.was_ambiguous is True
    assert a.trade.exit_reason == "breakeven" and a.trade.r_multiple == pytest.approx(0.0)


def test_target_on_trigger_bar_executes_normally():
    sim = _sim([SIGNAL, (100.0, 102.1, 99.5, 101.8), FLAT])
    assert sim.trade.exit_reason == "target" and sim.trade.r_multiple == pytest.approx(2.0)
    assert sim.trade.be_triggered is False


def test_forced_exit_unchanged():
    rows = [SIGNAL, (100.0, 100.6, 99.8, 100.3), (100.3, 100.4, 98.5, 98.7)]  # 15:45 signal, 15:50 entry, 15:55 forced
    be, base = _sim(rows, start="2026-08-10 19:45"), _sim(rows, cfg=BASE, start="2026-08-10 19:45")
    assert be.trade.exit_reason == base.trade.exit_reason == "forced_eod"
    assert be.trade.exit_price == base.trade.exit_price == 98.7


def test_long_only_and_default_never_triggers():
    rows = [SIGNAL, (100.0, 100.6, 99.8, 100.3), (100.3, 100.4, 99.95, 100.0), FLAT]
    base = _sim(rows, cfg=BASE).trade
    assert base.be_triggered is False and base.exit_reason != "breakeven"
    be = _sim(rows).trade
    assert be.exit_price >= be.stop_price and be.target_price > be.entry_price > be.stop_price  # long geometry


# =====================================================================
# Frozen AAPL: engine equivalence, candidate invariance, PIT
# =====================================================================

def _aapl(n5=312, n15=104):
    prov = get_provider()
    df5 = prov.get_ohlcv("AAPL", "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
    df15 = prov.get_ohlcv("AAPL", "15m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
    return prov, (df5 if n5 is None else df5.iloc[:n5]), (df15 if n15 is None else df15.iloc[:n15])


def test_fast_reference_equivalence_frozen_aapl_subset_be():
    prov, df5, df15 = _aapl()
    fast = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=BE, use_fast_engine=True)
    ref = run_day_backtest_reference("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=BE)
    assert [trade_fingerprint(t) for t in fast.trades] == [trade_fingerprint(t) for t in ref.trades]
    assert [t.be_trigger_time for t in fast.trades] == [t.be_trigger_time for t in ref.trades]
    assert fast.metrics == ref.metrics


def test_candidate_signal_population_unchanged():
    prov, df5, df15 = _aapl(n5=None, n15=None)
    base = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=BASE, use_fast_engine=True)
    be = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=BE, use_fast_engine=True)
    assert base.candidate_signals == be.candidate_signals > 0


def test_pit_future_mutation_does_not_change_earlier_be_trades():
    prov, df5, df15 = _aapl(n5=None, n15=None)
    base = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=BASE, use_fast_engine=True)
    sd = get_session_dates(df5.index)
    sessions = sorted(set(sd))
    cutoff = sessions[len(sessions) // 2]
    early = [t for t in base.trades if get_session_date(t.exit_time) < cutoff]
    assert early
    mutated = df5.copy()
    mask = (sd >= cutoff).to_numpy()
    mutated.loc[mask, ["open", "high", "low", "close"]] *= 1.07
    a, _, fa = resimulate_paired(early, {"AAPL": df5}, BE)
    b, _, fb = resimulate_paired(early, {"AAPL": mutated}, BE)
    assert not fa and not fb
    assert [trade_fingerprint(t) for t in a] == [trade_fingerprint(t) for t in b]
    assert [t.be_trigger_time for t in a] == [t.be_trigger_time for t in b]


# =====================================================================
# Frozen-data paired experiment
# =====================================================================

@pytest.fixture(scope="module")
def day12b():
    return run_day12b_experiment(provider=get_provider())


def test_baseline_exactly_identical(day12b):
    res, _ = day12b
    reg = res["baseline_regression"]
    assert reg["regression_verified"]
    assert all(reg["baseline_matches_anchors"].values())
    assert reg["paired_replay_with_baseline_config_identical"]
    assert res["metrics"]["BASELINE"]["total_trades"] == load_regression_anchors()["total_trades"]
    base = run_multi_symbol_day_backtest(provider=get_provider())
    assert sum(len(base.symbol_results[s].trades) for s in base.tested_symbols) == res["frozen_dataset"]["baseline_trades"]


def test_paired_population_and_reconciliation(day12b):
    res, rows = day12b
    a = res["accounting"]
    assert a["resimulation_failures"] == []
    assert a["same_population"] and a["be_trades"] == a["baseline_trades"] == len(rows)
    assert a["reconciles"]
    assert a["be_exit_r_all_zero"]
    assert res["metrics"]["BE_0.5R"]["total_trades"] == res["metrics"]["BASELINE"]["total_trades"]
    tm = a["exit_transition_matrix_baseline_to_be"]
    assert sum(sum(r.values()) for r in tm.values()) == len(rows)
    for r in rows:
        if not r["be_triggered"]:
            assert r["delta_R"] == 0.0 and r["be_exit_reason"] == r["baseline_exit_reason"]
        if r["be_exit_reason"] == "BREAKEVEN":
            assert r["be_triggered"] and r["be_R"] == 0.0
        assert r["target_price"] == pytest.approx(r["entry_price"] + 2 * r["risk_R_unit"])


def test_no_hypothesis_combination(day12b):
    res, _ = day12b
    cfg = res["baseline_regression"]["plain_baseline_config"]
    assert all(cfg.values())
    assert res["metadata"]["be_trigger_r"] == 0.5
    assert res["evaluation"]["status"] in (
        "MECHANISM SUPPORTED", "MECHANISM NOT SUPPORTED", "MECHANISM INCONCLUSIVE")
