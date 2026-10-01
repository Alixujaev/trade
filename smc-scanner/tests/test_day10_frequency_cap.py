"""tests/test_day10_frequency_cap.py: DAY-10 H3 Session Trade Frequency Cap tests.

Synthetic engine tests drive the REAL run_day_backtest loop with controlled signals
(the signal evaluator is monkeypatched), so the cap is tested exactly where it lives.
Real-data tests run on the frozen cache (network/cache guarded by tests/conftest.py).
"""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest

import backtest.day_engine as day_engine
from backtest.day_engine import run_day_backtest
from backtest.day_types import ExecutionConfig
from backtest.frequency_cap import (
    BASELINE_EXPECTED,
    H3_CAPS,
    group_by_symbol_session,
    run_day10_frequency_cap_experiment,
    trade_fingerprint,
    variant_name,
)
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.session_gate import SessionEntryGate
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.session import get_session_date
from strategy.day.types import DaySetup, DaySetupStatus

ET = "America/New_York"


# =====================================================================
# Synthetic harness
# =====================================================================

def _session_bars(day: str, extra_pre: bool = False, extra_post: bool = False) -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:55", freq="5min", tz=ET)
    if extra_pre:
        idx = idx.insert(0, pd.Timestamp(f"{day} 09:25", tz=ET))
    if extra_post:
        idx = idx.append(pd.DatetimeIndex([pd.Timestamp(f"{day} 16:00", tz=ET)]))
    n = len(idx)
    return pd.DataFrame(
        {"open": np.full(n, 100.0), "high": np.full(n, 100.2), "low": np.full(n, 99.8),
         "close": np.full(n, 100.0), "volume": np.full(n, 1e5)},
        index=idx.tz_convert("UTC"),
    )


def _bar(df: pd.DataFrame, day: str, hhmm: str) -> int:
    return df.index.get_loc(pd.Timestamp(f"{day} {hhmm}", tz=ET).tz_convert("UTC"))


def _install_signals(monkeypatch, signal_times: set[pd.Timestamp]) -> None:
    """Replace DAY-01 signal evaluation with a fixed set of CONFIRMED signal bars."""
    monkeypatch.setattr(day_engine, "precompute_day_features", lambda *a, **k: None)

    def fake_eval(symbol, df, idx, features=None):
        ts = df.index[idx]
        status = DaySetupStatus.CONFIRMED if ts in signal_times else DaySetupStatus.NO_SETUP
        return DaySetup(symbol=symbol, timestamp=ts, status=status, price=float(df["close"].iloc[idx]),
                        vwap=99.0, rsi=55.0, rvol=2.5)

    monkeypatch.setattr(day_engine, "evaluate_vwap_momentum_at_index", fake_eval)


def _quick_stop_after(df: pd.DataFrame, signal_idx: int) -> None:
    """Entry bar (signal+1) trades through the SIGNAL_LOW stop -> exits on entry bar."""
    df.iloc[signal_idx + 1, df.columns.get_loc("low")] = 99.5


def _run(df, cap, signals, monkeypatch):
    _install_signals(monkeypatch, {df.index[i] for i in signals})
    return run_day_backtest("TEST", df_5m=df, df_15m=None, provider=object(),
                            config=ExecutionConfig(max_trades_per_session=cap))


DAY1, DAY2 = "2026-08-10", "2026-08-11"


# =====================================================================
# Test 4 — re-entry cap (entry, stop, entry, stop, entry)
# =====================================================================

def test_reentry_cap_executes_only_first_two(monkeypatch):
    df = _session_bars(DAY1)
    sig = [_bar(df, DAY1, t) for t in ("11:00", "11:30", "12:00")]  # all >= bar 14 (engine warm-up)
    for i in sig:
        _quick_stop_after(df, i)

    base = _run(df, None, sig, monkeypatch)
    capped = _run(df, 2, sig, monkeypatch)

    assert len(base.trades) == 3
    assert all(t.exit_reason == "stop" for t in base.trades)
    assert len(capped.trades) == 2
    assert capped.cap_rejected_signals == 1
    assert [t.setup_time for t in capped.trades] == [df.index[sig[0]], df.index[sig[1]]]
    # Test 8 — no execution mutation of allowed trades
    assert [trade_fingerprint(t) for t in capped.trades] == [trade_fingerprint(t) for t in base.trades[:2]]
    assert capped.candidate_signals == base.candidate_signals == 3


# =====================================================================
# Test 5 — open-position signals are not counted
# =====================================================================

def test_open_position_signals_do_not_count_toward_cap(monkeypatch):
    df = _session_bars(DAY1)
    s1 = _bar(df, DAY1, "11:00")
    df.iloc[s1, df.columns.get_loc("low")] = 99.0          # stop 99.0, target 102.0 -> stays open
    exit_bar = _bar(df, DAY1, "12:00")
    df.iloc[exit_bar, df.columns.get_loc("low")] = 98.9     # stop hit at 12:00
    open_sigs = [_bar(df, DAY1, "11:20"), _bar(df, DAY1, "11:40")]   # while position open
    s2, s3 = _bar(df, DAY1, "13:00"), _bar(df, DAY1, "13:30")
    _quick_stop_after(df, s2)
    _quick_stop_after(df, s3)

    res = _run(df, 2, [s1, *open_sigs, s2, s3], monkeypatch)

    assert [t.setup_time for t in res.trades] == [df.index[s1], df.index[s2]]
    assert res.skipped_signals == 2            # existing engine semantics unchanged
    assert res.cap_rejected_signals == 1       # only s3
    assert res.candidate_signals == 5
    assert res.candidate_signals == len(res.trades) + res.skipped_signals + res.cap_rejected_signals + res.simulation_none_count


# =====================================================================
# Test 2 / Test 11 — session reset and forced exit
# =====================================================================

def test_session_reset_and_forced_exit_do_not_carry_count(monkeypatch):
    df = pd.concat([_session_bars(DAY1), _session_bars(DAY2)])
    a1, a2, a3 = (_bar(df, DAY1, t) for t in ("11:00", "11:30", "12:00"))
    for i in (a1, a2):
        _quick_stop_after(df, i)
    # a3: stop 99.0 / target 102.0 are never touched -> FORCED_EXIT at 15:55
    df.iloc[a3, df.columns.get_loc("low")] = 99.0
    last_sig = _bar(df, DAY1, "15:55")       # entry would be next session -> simulation None
    b1 = _bar(df, DAY2, "10:40")
    _quick_stop_after(df, b1)

    # cap=4: day 1 has 3 actual entries (incl. the forced-exit trade). If the forced exit had been
    # counted as an extra entry, the 15:55 signal would be cap-rejected instead of reaching simulation.
    res = _run(df, 4, [a1, a2, a3, last_sig, b1], monkeypatch)

    reasons = [t.exit_reason for t in res.trades]
    assert reasons == ["stop", "stop", "forced_eod", "stop"]
    assert res.cap_rejected_signals == 0                  # forced exit did not inflate the count
    assert res.simulation_none_count == 1                 # 15:55 signal: no same-session entry bar

    # cap=3: the 15:55 signal is the 4th candidate after 3 actual entries -> cap gate (before simulation)
    res3 = _run(df, 3, [a1, a2, a3, last_sig, b1], monkeypatch)
    assert res3.cap_rejected_signals == 1 and res3.simulation_none_count == 0
    assert len(res3.trades) == 4
    assert get_session_date(res.trades[-1].entry_time) == datetime.date(2026, 8, 11)

    capped1 = _run(df, 1, [a1, a2, a3, last_sig, b1], monkeypatch)
    assert [t.setup_time for t in capped1.trades] == [df.index[a1], df.index[b1]]   # new session starts at 0


# =====================================================================
# Test 10 — session boundary (09:29/09:30, 15:59/16:00)
# =====================================================================

def test_session_boundary_non_rth_bars_are_never_candidates(monkeypatch):
    df = pd.concat([_session_bars(DAY1, extra_post=True), _session_bars(DAY2, extra_pre=True)])
    post = _bar(df, DAY1, "16:00")
    pre = _bar(df, DAY2, "09:25")
    open_930 = _bar(df, DAY2, "09:30")
    first_rth = _bar(df, DAY2, "10:40")
    _quick_stop_after(df, first_rth)

    res = _run(df, 1, [post, pre, first_rth], monkeypatch)
    assert res.candidate_signals == 1
    assert [t.setup_time for t in res.trades] == [df.index[first_rth]]

    # 09:30 belongs to the new session; 15:55 bar of day 1 belongs to day 1
    assert get_session_date(df.index[open_930]) == datetime.date(2026, 8, 11)
    assert get_session_date(df.index[_bar(df, DAY1, "15:55")]) == datetime.date(2026, 8, 10)


# =====================================================================
# Gate unit tests — Test 2, 3, 9
# =====================================================================

def test_gate_session_isolation():
    g = SessionEntryGate(3)
    d1, d2 = datetime.date(2026, 8, 10), datetime.date(2026, 8, 11)
    for _ in range(3):
        assert g.allows(d1)
        g.record_entry(d1)
    assert not g.allows(d1)
    assert g.entries(d2) == 0 and g.allows(d2)


def test_gate_symbol_isolation():
    d = datetime.date(2026, 8, 10)
    aapl, nvda = SessionEntryGate(1), SessionEntryGate(1)
    aapl.record_entry(d)
    assert not aapl.allows(d)
    assert nvda.allows(d)


def test_gate_point_in_time_future_entries_do_not_change_past_decision():
    d1, d2 = datetime.date(2026, 8, 10), datetime.date(2026, 8, 11)
    g = SessionEntryGate(2)
    g.record_entry(d1)
    decision_before = g.allows(d1)
    for _ in range(10):                      # "future session" entries
        g.record_entry(d2)
    assert g.allows(d1) == decision_before is True


def test_gate_none_never_caps_and_invalid_cap_rejected():
    g = SessionEntryGate(None)
    d = datetime.date(2026, 8, 10)
    for _ in range(100):
        g.record_entry(d)
    assert g.allows(d)
    with pytest.raises(ValueError):
        SessionEntryGate(0)


# =====================================================================
# Real frozen-data tests — Test 1, 6, 7, 8, 9
# =====================================================================

@pytest.fixture(scope="module")
def day10_result():
    return run_day10_frequency_cap_experiment(provider=get_provider())


def test_no_cap_equivalent_to_default_baseline():
    prov = get_provider()
    default = run_multi_symbol_day_backtest(symbols=get_day_universe(), provider=prov)
    nocap = run_multi_symbol_day_backtest(
        symbols=get_day_universe(), provider=prov, config=ExecutionConfig(max_trades_per_session=None)
    )
    a = [trade_fingerprint(t) for s in default.tested_symbols for t in default.symbol_results[s].trades]
    b = [trade_fingerprint(t) for s in nocap.tested_symbols for t in nocap.symbol_results[s].trades]
    assert a == b
    assert len(a) == BASELINE_EXPECTED["total_trades"]
    assert default.aggregate_trade_stats == nocap.aggregate_trade_stats


def test_baseline_regression(day10_result):
    reg = day10_result["baseline_regression"]
    assert reg["regression_verified"] is True
    m = day10_result["metrics"][variant_name(None)]
    assert m["total_trades"] == 5691
    assert abs(m["win_rate"] - 0.3042) <= 0.0001
    assert abs(m["profit_factor"] - 0.9388) <= 0.0005
    assert abs(m["total_R"] - (-738.98)) <= 0.01
    assert abs(m["gross_return_compounded"] - (-41.19)) <= 0.01


def test_candidate_signal_population_invariant(day10_result):
    acc = day10_result["accounting"]
    base = acc[variant_name(None)]["candidate_signals"]
    for cap in H3_CAPS:
        a = acc[variant_name(cap)]
        assert a["candidate_signals"] == base
        assert a["identity_holds"]
        if cap is None:
            assert a["cap_rejected_entries"] == 0


def test_capped_entries_are_subset_prefix_of_baseline(day10_result):
    for cap in H3_CAPS:
        chk = day10_result["integrity"][variant_name(cap)]
        assert all(chk.values()), (cap, chk)
        freq = day10_result["frequency_distribution"][variant_name(cap)]
        if cap is not None:
            assert freq["max_per_session"] <= cap
    counts = [day10_result["metrics"][variant_name(c)]["total_trades"] for c in H3_CAPS[1:]]
    assert counts == sorted(counts)                      # monotone in cap
    assert counts[-1] <= day10_result["metrics"][variant_name(None)]["total_trades"]


def test_future_session_mutation_does_not_change_earlier_cap_decisions():
    """Adversarial PIT: perturbing later sessions changes their trades, not earlier capped trades."""
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

    for cap in (1, 2, 3):
        cfg = ExecutionConfig(max_trades_per_session=cap)
        clean = run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov, config=cfg)
        mut = run_day_backtest("AAPL", df_5m=mutate(df5), df_15m=mutate(df15), provider=prov, config=cfg)
        before_clean = [trade_fingerprint(t) for t in clean.trades if t.entry_time < cutoff]
        before_mut = [trade_fingerprint(t) for t in mut.trades if t.entry_time < cutoff]
        assert before_clean and before_clean == before_mut


def test_capped_aapl_matches_baseline_prefix_per_session():
    prov = get_provider()
    df5 = prov.get_ohlcv("AAPL", "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
    df15 = prov.get_ohlcv("AAPL", "15m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
    base = group_by_symbol_session(run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov).trades)
    for cap in (1, 2, 3, 4, 5):
        capped = group_by_symbol_session(
            run_day_backtest("AAPL", df_5m=df5, df_15m=df15, provider=prov,
                             config=ExecutionConfig(max_trades_per_session=cap)).trades
        )
        assert set(capped) == set(base)
        for key, trades in capped.items():
            assert [trade_fingerprint(t) for t in trades] == [trade_fingerprint(t) for t in base[key][:cap]]
