"""tests/test_day08_backtest.py: Integration & Regression Tests for DAY-08 H6 Index Regime Confluence.

Corrected (DAY-08B) semantics:
- H6 index context is looked up at signal_time = setup_time + 5m (signal bar end).
- Only SPY/QQQ bars with bar_end <= signal_time are used.
- Frozen SPY/QQQ coverage: 2026-07-08 -> 2026-09-25. Sessions 2026-07-02, 07-06, 07-07 have no
  index data, and 2026-07-08 has context only from 10:45 ET (5 closed 15m bars).

Baseline is checked against frozen DAY-04/DAY-07 invariants. H6 variants are checked
structurally; exact H6 metrics are regressed against the frozen artifacts/day08b output.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from backtest.index_regime import run_day08_index_regime_experiment, signal_time_for
from backtest.multi_symbol import run_multi_symbol_day_backtest
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.session import get_session_date, to_eastern
from strategy.day.index_regime import build_index_regime_detector

FROZEN_DAY08B_RESULTS = (
    Path(__file__).resolve().parent.parent / "artifacts" / "day08b" / "index-regime-corrected-results.json"
)
MISSING_INDEX_SESSIONS = {
    datetime.date(2026, 7, 2),
    datetime.date(2026, 7, 6),
    datetime.date(2026, 7, 7),
}
FIRST_INDEX_SESSION = datetime.date(2026, 7, 8)
FIRST_INDEX_CONTEXT_TIME = datetime.time(10, 45)  # 5 closed 15m bars after 09:30 ET

BASELINE_TRADES = 5691


@pytest.fixture(scope="module")
def day08_run():
    """Run the full DAY-08 experiment once (frozen cache replay) and keep its inputs."""
    prov = get_provider()
    multi = run_multi_symbol_day_backtest(symbols=get_day_universe(), provider=prov)
    detector = build_index_regime_detector(provider=prov)
    result = run_day08_index_regime_experiment(provider=prov, multi_result=multi, detector=detector)
    trades = [t for sym in multi.tested_symbols for t in multi.symbol_results[sym].trades]
    contexts = [(t, detector.get_context_at(signal_time_for(t.setup_time))) for t in trades]
    return result, contexts


@pytest.fixture(scope="module")
def full_experiment_result(day08_run):
    return day08_run[0]


def test_baseline_regression(full_experiment_result):
    """Section 18: Frozen Baseline Regression Audit (DAY-04/DAY-07 baseline)."""
    res = full_experiment_result
    base = res.baseline_metrics

    assert base.trades == BASELINE_TRADES
    assert abs(base.win_rate * 100 - 30.42) <= 0.01
    assert abs(base.profit_factor - 0.9388) <= 0.0005
    assert abs(base.total_R - (-738.98)) <= 0.01
    assert abs(base.slippage_0bps - (-41.19)) <= 0.01

    assert res.baseline_regression["regression_verified"] is True


def test_variant_trade_counts_and_eligibility(full_experiment_result):
    """Variant populations follow H6 filter semantics (no hardcoded H6 counts)."""
    res = full_experiment_result
    base, h6a, h6b, h6c = res.baseline_metrics, res.h6_a_metrics, res.h6_b_metrics, res.h6_c_metrics
    sc = res.signal_counts
    insufficient = sc["signals_excluded_due_to_missing_context"]
    evaluable = BASELINE_TRADES - insufficient

    for v in [base, h6a, h6b, h6c]:
        assert v.total_day01_signals == BASELINE_TRADES
        assert v.eligible_signals + v.excluded_signals == BASELINE_TRADES
        assert v.trades == v.eligible_signals

    # Insufficient index context is counted separately and is never part of an H6 population
    assert insufficient > 0
    assert sc["total_day01_signals"] == BASELINE_TRADES
    assert sc["signals_with_sufficient_both_context"] == evaluable
    assert sc["signals_with_sufficient_spy_context"] == evaluable
    assert sc["signals_with_sufficient_qqq_context"] == evaluable

    for v in [h6a, h6b, h6c]:
        assert 0 < v.trades < base.trades
        assert v.trades <= evaluable

    # H6-C is the intersection of SPY bullish and QQQ bullish
    assert h6c.trades <= min(h6a.trades, h6b.trades)
    assert h6a.trades + h6b.trades - h6c.trades <= evaluable


def test_h6_trade_membership_matches_context(day08_run):
    """Each H6 subset contains exactly the trades whose context at signal_time is bullish."""
    res, contexts = day08_run
    assert len(contexts) == BASELINE_TRADES

    expected_a = sum(1 for _, c in contexts if c.spy_bullish is True)
    expected_b = sum(1 for _, c in contexts if c.qqq_bullish is True)
    expected_c = sum(1 for _, c in contexts if c.aligned_bullish is True)
    assert res.h6_a_metrics.trades == expected_a
    assert res.h6_b_metrics.trades == expected_b
    assert res.h6_c_metrics.trades == expected_c

    for _, c in contexts:
        if not c.data_sufficient:
            assert c.spy_bullish is None and c.qqq_bullish is None
            assert c.aligned_bullish is not True
        if c.aligned_bullish is True:
            assert c.spy_bullish is True and c.qqq_bullish is True

    insufficient = sum(1 for _, c in contexts if not c.data_sufficient)
    assert insufficient == res.signal_counts["signals_excluded_due_to_missing_context"]


def test_insufficient_index_context_only_where_index_data_is_missing(day08_run):
    """INSUFFICIENT_INDEX_CONTEXT = 07-02/07-06/07-07 (no SPY/QQQ) + 07-08 before 10:45 ET warm-up."""
    _, contexts = day08_run

    for t, c in contexts:
        session = get_session_date(t.setup_time)
        sig_et = to_eastern(signal_time_for(t.setup_time))
        if session in MISSING_INDEX_SESSIONS:
            assert not c.data_sufficient, f"{t.symbol} {t.setup_time}: index data does not exist"
        elif session == FIRST_INDEX_SESSION and sig_et.time() < FIRST_INDEX_CONTEXT_TIME:
            assert not c.data_sufficient, f"{t.symbol} {t.setup_time}: < 5 closed 15m bars"
        else:
            assert c.data_sufficient, f"{t.symbol} {t.setup_time}: index context expected"

    missing_sessions = {get_session_date(t.setup_time) for t, c in contexts if not c.data_sufficient}
    assert MISSING_INDEX_SESSIONS <= missing_sessions <= MISSING_INDEX_SESSIONS | {FIRST_INDEX_SESSION}


def test_regime_distribution_sum_and_partitions(full_experiment_result):
    """Section 12: Verify regime distribution partition integrity."""
    res = full_experiment_result
    regimes = res.regime_distribution

    # Mutual exclusive & exhaustive 4-way partition
    p4_sum = (
        regimes["SPY AND QQQ bullish"].trades
        + regimes["mixed"].trades
        + regimes["aligned bearish"].trades
        + regimes["unknown"].trades
    )
    assert p4_sum == BASELINE_TRADES

    assert regimes["SPY bullish"].trades + regimes["SPY non-bullish"].trades == BASELINE_TRADES
    assert regimes["QQQ bullish"].trades + regimes["QQQ non-bullish"].trades == BASELINE_TRADES

    assert regimes["SPY bullish"].trades == res.h6_a_metrics.trades
    assert regimes["QQQ bullish"].trades == res.h6_b_metrics.trades
    assert regimes["SPY AND QQQ bullish"].trades == res.h6_c_metrics.trades

    # Missing context signals
    assert regimes["unknown"].trades == res.signal_counts["signals_excluded_due_to_missing_context"]


def test_per_symbol_trade_sums(full_experiment_result):
    """Section 13: Per-symbol trades must sum to aggregate trade counts."""
    res = full_experiment_result

    for var_key, metrics in [
        ("Baseline", res.baseline_metrics),
        ("H6-A", res.h6_a_metrics),
        ("H6-B", res.h6_b_metrics),
        ("H6-C", res.h6_c_metrics),
    ]:
        sym_dict = res.per_symbol_metrics[var_key]
        assert len(sym_dict) == 25
        assert sum(m.trades for m in sym_dict.values()) == metrics.trades


def test_slippage_monotonicity(full_experiment_result):
    """Section 16: Friction analysis must show monotonically decreasing returns with slippage."""
    res = full_experiment_result
    for v in [res.baseline_metrics, res.h6_a_metrics, res.h6_b_metrics, res.h6_c_metrics]:
        assert v.slippage_0bps > v.slippage_5bps
        assert v.slippage_5bps > v.slippage_10bps


def test_time_of_day_trade_sums(full_experiment_result):
    """Section 14: Time-of-day trade counts must sum to variant trade totals."""
    res = full_experiment_result
    for var_key, metrics in [
        ("Baseline", res.baseline_metrics),
        ("H6-A", res.h6_a_metrics),
        ("H6-B", res.h6_b_metrics),
        ("H6-C", res.h6_c_metrics),
    ]:
        tod_list = res.time_of_day_diagnostics[var_key]
        assert sum(m.trades for m in tod_list) == metrics.trades


def test_json_serialization(full_experiment_result):
    """Section 22: Result dictionary must be JSON serializable."""
    res = full_experiment_result
    json_str = json.dumps(res.to_dict())
    assert len(json_str) > 1000

    loaded = json.loads(json_str)
    assert loaded["baseline_regression"]["actual_trades"] == BASELINE_TRADES
    assert loaded["h6_c_metrics"]["trades"] == res.h6_c_metrics.trades
    assert "signal_time = setup_time" in loaded["metadata"]["h6_context_timestamp"]


@pytest.mark.skipif(not FROZEN_DAY08B_RESULTS.exists(), reason="frozen artifacts/day08b output mavjud emas")
def test_matches_frozen_day08b_artifact(full_experiment_result):
    """Exact H6 metrics regress against the frozen corrected DAY-08B output."""
    frozen = json.loads(FROZEN_DAY08B_RESULTS.read_text(encoding="utf-8"))
    current = json.loads(json.dumps(full_experiment_result.to_dict()))

    assert current["signal_counts"] == frozen["signal_counts"]
    assert current["baseline_regression"] == frozen["baseline_regression"]

    fields = [
        "trades", "eligible_signals", "excluded_signals", "wins", "losses", "breakevens",
        "win_rate", "profit_factor", "total_R", "avg_R", "max_drawdown",
        "slippage_0bps", "slippage_5bps", "slippage_10bps",
    ]
    for key in ["baseline_metrics", "h6_a_metrics", "h6_b_metrics", "h6_c_metrics"]:
        for f in fields:
            assert current[key][f] == frozen[key][f], f"{key}.{f}"
