"""tests/test_day11_time_window.py: DAY-11 H5 Time-of-Day Execution Window tests.

- Boundary tests on EntryWindow (half-open ET [start, end) on the ENTRY bar open).
- Synthetic engine tests drive the REAL fast and reference loops with controlled signals.
- Fast/reference equivalence on synthetic data and on a frozen AAPL subset.
- Real frozen-data tests: FULL == baseline, candidate invariance, subset invariance, PIT mutation.
Cache immutability is enforced for all tests by tests/conftest.py.
"""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest

import backtest.day_engine as day_engine
from backtest.day_engine import run_day_backtest, run_day_backtest_reference
from backtest.day_types import ExecutionConfig
from backtest.frequency_cap import trade_fingerprint
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.session_gate import ENTRY_WINDOWS, EntryWindow
from backtest.time_window import (
    load_regression_anchors,
    run_day11_time_window_experiment,
)
from config.day_universe import get_day_universe
from data.factory import get_provider
from strategy.day.types import DaySetup, DaySetupStatus

ET = "America/New_York"
W = {w.name: w for w in ENTRY_WINDOWS}
DAY1, DAY2 = "2026-08-10", "2026-08-11"


# =====================================================================
# 1. Boundary tests
# =====================================================================

BOUNDARY_TIMES = ["09:29", "09:30", "09:35", "10:59", "11:00", "11:01", "11:55", "12:00", "12:01",
                  "12:55", "13:00", "13:01", "13:55", "14:00", "14:01", "15:50", "15:55", "16:00"]
WINDOW_END = {"FULL": "16:00", "MORNING": "11:00", "MORNING_EXT": "12:00", "EARLY_DAY": "13:00", "NO_LATE": "14:00"}


def test_predeclared_windows_are_exactly_the_five():
    assert [w.name for w in ENTRY_WINDOWS] == ["FULL", "MORNING", "MORNING_EXT", "EARLY_DAY", "NO_LATE"]
    for w in ENTRY_WINDOWS:
        assert w.start == datetime.time(9, 30)
        assert f"{w.end:%H:%M}" == WINDOW_END[w.name]


@pytest.mark.parametrize("name", list(WINDOW_END))
@pytest.mark.parametrize("hhmm", BOUNDARY_TIMES)
def test_window_boundaries_half_open(name, hhmm):
    ts = pd.Timestamp(f"{DAY1} {hhmm}", tz=ET)
    expected = "09:30" <= hhmm < WINDOW_END[name]
    assert W[name].allows(ts) is expected
    assert W[name].allows(ts.tz_convert("UTC")) is expected   # provider timestamps are UTC


def test_window_uses_eastern_time_across_dst():
    # 13:55 UTC is 09:55 ET in summer (EDT) but 08:55 ET in winter (EST)
    assert W["MORNING"].allows(pd.Timestamp("2026-08-10 13:55", tz="UTC")) is True
    assert W["MORNING"].allows(pd.Timestamp("2026-12-10 13:55", tz="UTC")) is False
    assert W["MORNING"].allows(pd.Timestamp("2026-12-10 14:35", tz="UTC")) is True


# =====================================================================
# 2. Synthetic engine harness (patches BOTH fast and reference signal paths)
# =====================================================================

def _session_bars(day: str) -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:55", freq="5min", tz=ET)
    n = len(idx)
    return pd.DataFrame(
        {"open": np.full(n, 100.0), "high": np.full(n, 100.2), "low": np.full(n, 99.8),
         "close": np.full(n, 100.0), "volume": np.full(n, 1e5)},
        index=idx.tz_convert("UTC"),
    )


def _bar(df, day, hhmm) -> int:
    return df.index.get_loc(pd.Timestamp(f"{day} {hhmm}", tz=ET).tz_convert("UTC"))


def _install(monkeypatch, signal_times):
    def mk(symbol, ts, price):
        st = DaySetupStatus.CONFIRMED if ts in signal_times else DaySetupStatus.NO_SETUP
        return DaySetup(symbol=symbol, timestamp=ts, status=st, price=price, vwap=99.0, rsi=55.0, rvol=2.5)

    monkeypatch.setattr(day_engine, "precompute_day_features", lambda *a, **k: None)
    monkeypatch.setattr(day_engine, "evaluate_vwap_momentum_at_index",
                        lambda symbol, df, idx, features=None: mk(symbol, df.index[idx], float(df["close"].iloc[idx])))
    monkeypatch.setattr(day_engine, "evaluate_vwap_momentum",
                        lambda symbol, df, **k: mk(symbol, df.index[-1], float(df["close"].iloc[-1])))


def _run(df, window, signals, monkeypatch, fast=True):
    _install(monkeypatch, {df.index[i] for i in signals})
    fn = run_day_backtest if fast else run_day_backtest_reference
    kwargs = {"use_fast_engine": True} if fast else {}
    return fn("TEST", df_5m=df, df_15m=None, provider=object(),
              config=ExecutionConfig(entry_window=window), **kwargs)


def _stop_on_entry_bar(df, sig):
    df.iloc[sig + 1, df.columns.get_loc("low")] = 99.5


def test_gate_uses_entry_bar_not_signal_bar(monkeypatch):
    df = _session_bars(DAY1)
    s_1050, s_1055 = _bar(df, DAY1, "10:50"), _bar(df, DAY1, "10:55")
    for s in (s_1050, s_1055):
        _stop_on_entry_bar(df, s)
    res = _run(df, W["MORNING"], [s_1050, s_1055], monkeypatch)
    # 10:50 signal -> entry 10:55 (accepted); 10:55 signal -> entry 11:00 (rejected)
    assert [t.entry_time for t in res.trades] == [df.index[s_1050 + 1]]
    assert res.window_rejected_signals == 1
    assert res.window_rejected_entry_times == [df.index[s_1055 + 1]]


def test_window_close_does_not_close_or_modify_open_position(monkeypatch):
    df = _session_bars(DAY1)
    s = _bar(df, DAY1, "10:50")                     # entry 10:55
    df.iloc[s, df.columns.get_loc("low")] = 99.0    # stop 99.0 / target 102.0
    df.iloc[_bar(df, DAY1, "11:15"), df.columns.get_loc("low")] = 98.9   # stop at 11:15
    later = _bar(df, DAY1, "11:30")
    base = _run(df, None, [s, later], monkeypatch)
    morning = _run(df, W["MORNING"], [s, later], monkeypatch)
    t = morning.trades[0]
    assert t.exit_reason == "stop"
    assert t.exit_time == pd.Timestamp(f"{DAY1} 11:15", tz=ET).tz_convert("UTC")
    assert trade_fingerprint(t) == trade_fingerprint(base.trades[0])
    assert len(morning.trades) == 1 and morning.window_rejected_signals == 1   # 11:30 signal -> entry 11:35


def test_position_open_signal_is_skip_not_window_rejection(monkeypatch):
    df = _session_bars(DAY1)
    s = _bar(df, DAY1, "10:45")                     # >= bar 14 (engine warm-up); entry 10:50
    df.iloc[s, df.columns.get_loc("low")] = 99.0
    df.iloc[_bar(df, DAY1, "11:30"), df.columns.get_loc("low")] = 98.9   # open until 11:30
    inside_open = _bar(df, DAY1, "11:05")          # entry 11:10 would be outside, but position is open
    res = _run(df, W["MORNING"], [s, inside_open], monkeypatch)
    assert len(res.trades) == 1
    assert res.skipped_signals == 1
    assert res.window_rejected_signals == 0


def test_1555_entry_and_last_bar_signal_semantics(monkeypatch):
    df = pd.concat([_session_bars(DAY1), _session_bars(DAY2)])
    s_1550, s_1555 = _bar(df, DAY1, "15:50"), _bar(df, DAY1, "15:55")
    full = _run(df, W["FULL"], [s_1550, s_1555], monkeypatch)
    base = _run(df, None, [s_1550, s_1555], monkeypatch)
    assert [trade_fingerprint(t) for t in full.trades] == [trade_fingerprint(t) for t in base.trades]
    assert full.trades[0].exit_reason == "forced_eod"
    assert full.trades[0].entry_time == full.trades[0].exit_time            # same 15:55 bar
    # 15:55 signal has no same-session entry bar -> simulation_none, never window-rejected
    assert full.simulation_none_count == 1 and full.window_rejected_signals == 0
    no_late = _run(df, W["NO_LATE"], [s_1550, s_1555], monkeypatch)
    assert no_late.window_rejected_signals == 1 and no_late.simulation_none_count == 1


def test_session_reset_and_candidate_invariance(monkeypatch):
    df = pd.concat([_session_bars(DAY1), _session_bars(DAY2)])
    sigs = [_bar(df, DAY1, "10:40"), _bar(df, DAY1, "13:30"), _bar(df, DAY2, "10:40"), _bar(df, DAY2, "14:30")]
    for s in sigs:
        _stop_on_entry_bar(df, s)
    cands = set()
    for name in W:
        res = _run(df, W[name], sigs, monkeypatch)
        cands.add(res.candidate_signals)
        assert res.candidate_signals == (len(res.trades) + res.skipped_signals + res.cap_rejected_signals
                                         + res.window_rejected_signals + res.simulation_none_count)
    assert cands == {4}
    morning = _run(df, W["MORNING"], sigs, monkeypatch)
    assert [t.setup_time for t in morning.trades] == [df.index[sigs[0]], df.index[sigs[2]]]   # day 2 re-opens


@pytest.mark.parametrize("name", list(WINDOW_END))
def test_fast_reference_equivalence_synthetic(monkeypatch, name):
    df = pd.concat([_session_bars(DAY1), _session_bars(DAY2)])
    sigs = [_bar(df, d, t) for d in (DAY1, DAY2) for t in ("10:40", "10:55", "11:55", "12:55", "13:55", "15:50")]
    for s in sigs[::2]:
        _stop_on_entry_bar(df, s)
    fast = _run(df, W[name], sigs, monkeypatch, fast=True)
    ref = _run(df, W[name], sigs, monkeypatch, fast=False)
    assert [trade_fingerprint(t) for t in fast.trades] == [trade_fingerprint(t) for t in ref.trades]
    for attr in ("candidate_signals", "skipped_signals", "window_rejected_signals", "simulation_none_count",
                 "same_bar_ambiguity_count"):
        assert getattr(fast, attr) == getattr(ref, attr), attr
    assert fast.window_rejected_entry_times == ref.window_rejected_entry_times


# =====================================================================
# 3. Real frozen data
# =====================================================================

@pytest.mark.parametrize("name", ["FULL", "MORNING", "NO_LATE"])
def test_fast_reference_equivalence_frozen_aapl_subset(name):
    prov = get_provider()
    df5 = prov.get_ohlcv("AAPL", "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True).iloc[:312]
    df15 = prov.get_ohlcv("AAPL", "15m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True).iloc[:104]
    cfg = ExecutionConfig(entry_window=W[name])
    fast = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=cfg, use_fast_engine=True)
    ref = run_day_backtest_reference("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=cfg)
    assert [trade_fingerprint(t) for t in fast.trades] == [trade_fingerprint(t) for t in ref.trades]
    assert fast.candidate_signals == ref.candidate_signals > 0
    assert fast.window_rejected_signals == ref.window_rejected_signals
    assert fast.skipped_signals == ref.skipped_signals
    assert fast.metrics == ref.metrics


@pytest.fixture(scope="module")
def day11_result():
    return run_day11_time_window_experiment(provider=get_provider())


def test_full_reproduces_baseline_and_anchors(day11_result):
    reg = day11_result["baseline_regression"]
    assert reg["full_trades_identical_to_no_gate"] is True
    assert all(reg["no_gate_matches_anchors"].values())
    assert all(reg["full_matches_anchors"].values())
    anchors = load_regression_anchors()
    assert day11_result["metrics"]["FULL"]["total_trades"] == anchors["total_trades"]
    assert day11_result["accounting"]["FULL"]["window_rejected"] == 0


def test_candidate_invariance_and_identity(day11_result):
    cands = {a["candidate_signals"] for a in day11_result["accounting"].values()}
    assert len(cands) == 1
    for a in day11_result["accounting"].values():
        assert a["identity_holds"]
        assert a["cap_rejected"] == 0


def test_restricted_trades_equal_baseline_filtered_by_window(day11_result):
    for name, chk in day11_result["integrity"].items():
        assert all(chk.values()), (name, chk)
    t = {n: day11_result["metrics"][n]["total_trades"] for n in WINDOW_END}
    assert t["MORNING"] <= t["MORNING_EXT"] <= t["EARLY_DAY"] <= t["NO_LATE"] <= t["FULL"]


def test_no_hypothesis_combination(day11_result):
    rules = day11_result["metadata"]["execution_rules"]
    assert rules["initial_stop"] == "SIGNAL_LOW" and rules["target"] == "2.0R"
    assert rules["frequency_cap"] == "none" and rules["forced_exit"] == "15:55 ET"


def test_future_session_mutation_does_not_change_earlier_window_decisions():
    prov = get_provider()
    df5 = prov.get_ohlcv("AAPL", "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
    df15 = prov.get_ohlcv("AAPL", "15m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
    cutoff = pd.Timestamp("2026-08-14 00:00", tz=ET)

    def mutate(df):
        out = df.copy()
        later = out.index >= cutoff
        out.loc[later, ["open", "high", "low", "close"]] *= 1.07
        out.loc[later, "volume"] *= 3.0
        return out

    for name in ("MORNING", "NO_LATE"):
        cfg = ExecutionConfig(entry_window=W[name])
        clean = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=cfg)
        mut = run_day_backtest("AAPL", df_5m=mutate(df5), df_15m=mutate(df15), provider=prov, config=cfg)
        a = [trade_fingerprint(t) for t in clean.trades if t.entry_time < cutoff]
        b = [trade_fingerprint(t) for t in mut.trades if t.entry_time < cutoff]
        assert a and a == b
        ra = [ts for ts in clean.window_rejected_entry_times if ts < cutoff]
        rb = [ts for ts in mut.window_rejected_entry_times if ts < cutoff]
        assert ra == rb


def test_symbol_isolation_window_results_per_symbol_independent():
    prov = get_provider()
    cfg = ExecutionConfig(entry_window=W["MORNING"])
    both = run_multi_symbol_day_backtest(symbols=["AAPL", "NVDA"], provider=prov, config=cfg)
    alone = run_multi_symbol_day_backtest(symbols=["AAPL"], provider=prov, config=cfg)
    assert [trade_fingerprint(t) for t in both.symbol_results["AAPL"].trades] == \
           [trade_fingerprint(t) for t in alone.symbol_results["AAPL"].trades]
