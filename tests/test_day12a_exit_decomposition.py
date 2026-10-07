"""tests/test_day12a_exit_decomposition.py: DAY-12A Exit Failure Decomposition tests (diagnostic only).

- Synthetic long trades: MFE/MAE values, R conversion, exit boundary, exit-bar (STOP_FIRST) semantics,
  forced-exit bar, invalid risk, PIT (post-exit mutation), faithful-reconstruction guards.
- Frozen data: plain baseline reproduced (DAY-10 anchors), every trade reconstructed and consistent.
Cache immutability and network blocking are enforced for all tests by tests/conftest.py.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.exit_decomposition import (
    analyze_rows,
    baseline_config_is_plain,
    build_trade_rows,
    compute_trade_excursion,
    loser_reach,
    run_day12a_exit_decomposition,
)
from backtest.frequency_cap import trade_fingerprint
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.time_window import load_regression_anchors
from data.factory import get_provider

# 2026-08-10 13:30 UTC = 09:30 ET
IDX = pd.date_range("2026-08-10 13:30", periods=8, freq="5min", tz="UTC")


def _bars(rows) -> pd.DataFrame:
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": [1000] * len(rows)}, index=IDX[: len(rows)])


def _trade(entry_i, exit_i, exit_price, reason, entry=100.0, stop=99.0, target=102.0, setup_i=None) -> DayBacktestTrade:
    risk = None if stop is None else entry - stop
    return DayBacktestTrade(
        symbol="TEST",
        setup_time=IDX[entry_i - 1 if setup_i is None else setup_i],
        entry_time=IDX[entry_i],
        entry_price=entry,
        exit_time=IDX[exit_i],
        exit_price=exit_price,
        exit_reason=reason,
        stop_price=stop,
        target_price=target,
        gross_return=(exit_price - entry) / entry,
        risk_per_share=risk,
        r_multiple=(exit_price - entry) / risk if risk else None,
        hold_duration_minutes=int((IDX[exit_i] - IDX[entry_i]).total_seconds() / 60),
    )


# signal bar 0; entry bar 1 open 100; bars 2-3 drift; bar 4 stop bar (high 101.8 would be MFE if included)
STOP_PATH = [
    (99.5, 100.2, 99.0, 100.0),   # 0 signal bar (low 99.0 = stop)
    (100.0, 100.6, 99.6, 100.4),  # 1 entry bar
    (100.4, 101.2, 100.1, 100.9), # 2  high 101.2 -> +1.2R
    (100.9, 101.0, 99.4, 99.5),   # 3  low 99.4 -> -0.6R
    (99.5, 101.8, 98.7, 99.0),    # 4  stop exit bar (ambiguous ordering)
    (99.0, 105.0, 90.0, 104.0),   # 5  AFTER exit — must be ignored
]


def test_mfe_mae_known_long_stop_trade():
    bars = _bars(STOP_PATH)
    ex = compute_trade_excursion(bars, _trade(1, 4, 99.0, "stop"))
    assert ex.mfe_price == pytest.approx(101.2)
    assert ex.mfe == pytest.approx(1.2)
    assert ex.mfe_time == IDX[2] and ex.time_to_mfe_minutes == 5
    # adverse: stop fill 99.0 on the exit bar (low 98.7 occurs after the stop fill)
    assert ex.mae_price == pytest.approx(99.0)
    assert ex.mae == pytest.approx(-1.0)
    assert ex.mae_time == IDX[4] and ex.time_to_mae_minutes == 15
    assert ex.bars_observed == 4


def test_r_conversion_uses_original_risk_distance():
    bars = _bars(STOP_PATH)
    t = _trade(1, 4, 99.0, "stop")
    ex = compute_trade_excursion(bars, t)
    assert ex.mfe_r == pytest.approx(ex.mfe / t.risk_per_share) == pytest.approx(1.2)
    assert ex.mae_r == pytest.approx(ex.mae / t.risk_per_share) == pytest.approx(-1.0)
    # different stop distance -> R scales with the trade's own risk only
    t2 = _trade(1, 4, 99.0, "stop", stop=98.5, target=103.0)
    assert compute_trade_excursion(bars, t2).mfe_r == pytest.approx(1.2 / 1.5)


def test_bars_after_exit_never_contribute():
    bars = _bars(STOP_PATH)
    ex = compute_trade_excursion(bars, _trade(1, 4, 99.0, "stop"))
    ub = compute_trade_excursion(bars, _trade(1, 4, 99.0, "stop"), "UPPER_BOUND")
    assert ex.mfe_price < 105.0 and ex.mae_price > 90.0
    assert ub.mfe_price == pytest.approx(101.8) and ub.mae_price == pytest.approx(98.7)


def test_pit_mutating_future_bars_does_not_change_excursion():
    t = _trade(1, 4, 99.0, "stop")
    base = _bars(STOP_PATH)
    mutated = base.copy()
    mutated.iloc[5] = [50.0, 500.0, 1.0, 400.0, 1000]
    extra = pd.concat([mutated, _bars(STOP_PATH + [(1.0, 999.0, 0.1, 5.0)] * 2).iloc[6:]])
    for mode in ("PRIMARY", "UPPER_BOUND"):
        a = compute_trade_excursion(base, t, mode)
        assert compute_trade_excursion(mutated, t, mode) == a
        assert compute_trade_excursion(extra, t, mode) == a
        assert compute_trade_excursion(base.iloc[:5], t, mode) == a  # truncated exactly at exit bar


def test_same_bar_ambiguity_respects_stop_first():
    # exit bar high reaches target AND low reaches stop -> engine records STOP (STOP_FIRST)
    path = [
        (99.5, 100.2, 99.0, 100.0),
        (100.0, 100.5, 99.8, 100.3),
        (100.3, 102.5, 98.9, 99.2),   # ambiguous exit bar: high >= 102 target, low <= 99 stop
    ]
    bars = _bars(path)
    t = _trade(1, 2, 99.0, "stop")
    p = compute_trade_excursion(bars, t, "PRIMARY")
    assert p.exit_bar_same_bar_ambiguous is True
    assert p.mfe_r == pytest.approx(0.5)            # entry bar high only; exit bar contributes its open (100.3)
    assert p.mfe_r < 2.0                            # never contradicts the recorded STOP
    u = compute_trade_excursion(bars, t, "UPPER_BOUND")
    assert u.mfe_r == pytest.approx(2.5)            # upper bound is explicitly the optimistic bound


def test_target_exit_bar_adverse_first():
    path = [
        (99.5, 100.2, 99.0, 100.0),
        (100.0, 100.4, 99.7, 100.2),
        (100.2, 102.9, 99.3, 102.5),  # target bar: low 99.3 counted (adverse-first), high capped at target fill
    ]
    bars = _bars(path)
    p = compute_trade_excursion(bars, _trade(1, 2, 102.0, "target"))
    assert p.mfe_price == pytest.approx(102.0) and p.mfe_r == pytest.approx(2.0)
    assert p.mae_price == pytest.approx(99.3) and p.mae_r == pytest.approx(-0.7)
    assert p.exit_bar_gap_through is False


def test_forced_exit_bar_full_range():
    path = [
        (99.5, 100.2, 99.0, 100.0),
        (100.0, 100.4, 99.7, 100.2),
        (100.2, 101.5, 98.5, 100.1),  # forced bar: engine holds to close without stop/target checks
    ]
    bars = _bars(path)
    p = compute_trade_excursion(bars, _trade(1, 2, 100.1, "forced_eod"))
    assert p.mfe_price == pytest.approx(101.5)
    assert p.mae_price == pytest.approx(98.5) and p.mae_r == pytest.approx(-1.5)


def test_stop_on_entry_bar_gives_zero_mfe_primary():
    path = [(99.5, 100.2, 99.0, 100.0), (100.0, 100.9, 98.8, 99.1)]
    p = compute_trade_excursion(_bars(path), _trade(1, 1, 99.0, "stop"))
    assert p.mfe == 0.0 and p.time_to_mfe_minutes == 0
    assert p.mae_r == pytest.approx(-1.0)
    assert p.mfe >= 0.0 and p.mae <= 0.0


@pytest.mark.parametrize("stop", [None, 100.0, 101.0])
def test_zero_or_invalid_risk_is_nan_not_corrupting(stop):
    bars = _bars(STOP_PATH)
    t = _trade(1, 5, 104.0, "forced_eod", stop=stop, target=None)
    ex = compute_trade_excursion(bars, t)
    assert ex.risk_valid is False and math.isnan(ex.mfe_r) and math.isnan(ex.mae_r)
    assert ex.mfe == pytest.approx(5.0)          # price excursion still defined
    good = _trade(1, 4, 99.0, "stop")
    rows, integ = build_trade_rows([good, t], {"TEST": bars})
    assert integ["invalid_risk_trades"] == 1
    lr = loser_reach(rows)
    assert lr["losers"] == 1                     # invalid-risk trade excluded from R stats
    res = analyze_rows(rows)
    assert res["outcome_decomposition"]["LOSERS"]["avg_MFE_R"] == pytest.approx(1.2)


def test_reconstruction_refuses_to_approximate():
    bars = _bars(STOP_PATH)
    with pytest.raises(ValueError):          # entry price != entry-bar open (would imply a different cost model)
        compute_trade_excursion(bars, _trade(1, 4, 99.0, "stop", entry=100.05, stop=99.05, target=102.05))
    with pytest.raises(ValueError):          # exit bar missing from data
        compute_trade_excursion(bars.drop(IDX[4]), _trade(1, 4, 99.0, "stop"))
    with pytest.raises(ValueError):
        compute_trade_excursion(bars, _trade(1, 4, 99.0, "stop"), "OPTIMISTIC")


def test_record_verification_on_synthetic_trade():
    rows, integ = build_trade_rows([_trade(1, 4, 99.0, "stop")], {"TEST": _bars(STOP_PATH)})
    assert integ["all_record_checks_pass"], integ["record_check_failures"]
    bad = _trade(1, 4, 99.0, "stop", stop=98.0, target=104.0)  # stop not = signal low
    _, integ2 = build_trade_rows([bad], {"TEST": _bars(STOP_PATH)})
    assert not integ2["all_record_checks_pass"]


def test_plain_baseline_config_checks():
    assert all(baseline_config_is_plain(ExecutionConfig()).values())
    assert not all(baseline_config_is_plain(ExecutionConfig(max_trades_per_session=1)).values())
    assert not all(baseline_config_is_plain(ExecutionConfig(breakeven_trigger_r=1.0)).values())


# =====================================================================
# Frozen-data tests
# =====================================================================

@pytest.fixture(scope="module")
def day12a():
    return run_day12a_exit_decomposition(provider=get_provider())


def test_baseline_reproduced_and_unchanged(day12a):
    res, rows = day12a
    anchors = load_regression_anchors()
    reg = res["baseline_regression"]
    assert reg["regression_verified"]
    assert all(reg["baseline_matches_anchors"].values())
    assert res["frozen_dataset"]["baseline_trades"] == anchors["total_trades"] == len(rows)
    base = run_multi_symbol_day_backtest(provider=get_provider())
    trades = [t for s in base.tested_symbols for t in base.symbol_results[s].trades]
    assert [(trade_fingerprint(t)[0], trade_fingerprint(t)[2]) for t in trades] == [
        (r["symbol"], r["entry_time"]) for r in rows]


def test_every_trade_reconstructed_and_consistent(day12a):
    res, rows = day12a
    integ = res["integrity"]
    assert integ["all_trades_reconstructed"]
    assert integ["all_record_checks_pass"], integ["record_check_failures"]
    assert integ["invalid_risk_trades"] == 0
    assert integ["primary_mfe_never_exceeds_upper_bound"] and integ["primary_mae_never_below_upper_bound"]
    for r in rows:
        assert r["MFE"] >= 0.0 and r["MAE"] <= 0.0
        assert r["entry_time"] <= r["MFE_time"] <= r["exit_time"]
        assert r["entry_time"] <= r["MAE_time"] <= r["exit_time"]
        if r["exit_reason"] == "TARGET":
            # exit-bar open above the target (gap-through) is an observed price before the target fill
            assert r["MFE_R"] >= 2.0 - 1e-9
            if not r["exit_bar_gap_through"]:
                assert r["MFE_R"] == pytest.approx(2.0)
        if r["exit_reason"] == "STOP":
            assert r["MFE_R"] < 2.0 and r["MAE_R"] <= -1.0 + 1e-9


def test_group_counts_are_consistent(day12a):
    res, rows = day12a
    ex = res["exit_reason_decomposition"]
    assert sum(ex[g]["count"] for g in ex) == len(rows)
    assert {k: ex[k]["count"] for k in ex} == {k: res["baseline_regression"]["baseline_exit_counts"][k] for k in ex}
    oc = res["outcome_decomposition"]
    assert oc["WINNERS"]["count"] + oc["LOSERS"]["count"] + oc["BREAKEVENS"]["count"] == len(rows)
    assert sum(b["count"] for b in res["holding_time"].values() if b.get("count")) == len(rows)
    assert res["mechanism"]["status"] in ("MECHANISM SUPPORTED", "MECHANISM NOT SUPPORTED", "MECHANISM INCONCLUSIVE")
