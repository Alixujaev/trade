"""tests/test_day19_v2_research.py: DAY-19 frozen v2 research engine (backtest/v2), synthetic data only.

No snapshot, no network (sockets blocked by tests/conftest.py). Checks the frozen formulas of protocol v2:
§3.4 TR index, §4-§6 signals and schedules, §8 execution order, §9 costs, §11 accounting, §12 metrics, §7 PIT.
"""

from __future__ import annotations

from datetime import date
import math

import numpy as np
import pytest

from acquisition.v2.sessions import stage_r_sessions
from backtest.v2 import engine as en
from backtest.v2 import metrics as mt
from backtest.v2 import signals as sg
from backtest.v2.data import MarketData, tr_index

SESS = tuple(stage_r_sessions())


def market(closes, opens=None, q=None, d=None, tickers=None):
    c = np.asarray(closes, dtype=float)
    if c.ndim == 1:
        c = c[:, None]
    n, m = c.shape
    tickers = tickers or tuple(f"T{j:02d}" for j in range(m))
    return MarketData(SESS[:n], tuple(tickers), c.copy() if opens is None else np.asarray(opens, float).reshape(n, m),
                      c, np.ones((n, m)) if q is None else np.asarray(q, float).reshape(n, m),
                      np.zeros((n, m)) if d is None else np.asarray(d, float).reshape(n, m))


# ================================================================ timeline / sessions

def test_research_and_warmup_session_counts():
    i0, i1 = SESS.index(date(2017, 2, 1)), SESS.index(date(2022, 12, 30))
    assert i0 == 272 and i1 - i0 + 1 == 1490 and SESS[0] == date(2016, 1, 4) and SESS[-1] == date(2022, 12, 30)
    assert SESS[i0 - 1] == date(2017, 1, 31)


def test_schedules_month_iso_week_initial_and_last_close_discarded():
    nxt = date(2023, 1, 3)
    me = sg.month_end_flags(SESS, nxt)
    we = sg.iso_week_end_flags(SESS, nxt)
    i0, i1 = SESS.index(date(2017, 2, 1)), SESS.index(date(2022, 12, 30))
    assert me[SESS.index(date(2017, 1, 31))] and me[i1] and not me[SESS.index(date(2017, 2, 27))]
    assert we[SESS.index(date(2017, 2, 3))] and not we[SESS.index(date(2017, 1, 31))]
    mom = sg.decision_sessions(me, i0, i1)
    strd = sg.decision_sessions(we, i0, i1)
    assert mom[0] == i0 - 1 and i1 not in mom and len(mom) == 71
    assert strd[0] == i0 - 1 and SESS[strd[1]] == date(2017, 2, 3) and i1 not in strd   # §8.14 off-schedule start


# ================================================================ §3.4 TR index

def test_tr_index_split_dividend_and_missing_bar_carry():
    c = [10.0, 11.0, 5.0, np.nan, 2.6, 2.8]
    q = [1, 1, 2, 1, 2, 1]                       # 2:1 at k=2; 2:1 at k=4 (during no gap)
    d = [0, 0, 0, 0.3, 0, 0]                     # dividend at k=3 while bar missing; carried into k=4 units
    tr = tr_index(market(c, q=q, d=d))[:, 0]
    assert tr[0] == 1.0 and tr[1] == pytest.approx(1.1)
    assert tr[2] == pytest.approx(1.1 * (5.0 * 2 + 0) / 11.0)
    assert math.isnan(tr[3])
    assert tr[4] == pytest.approx(tr[2] * (2.6 * 2 + 0.3 * 2) / 5.0)   # D = d(e) * q over (e, k]
    assert tr[5] == pytest.approx(tr[4] * 2.8 / 2.6)


def test_tr_index_is_point_in_time():
    rng = np.linspace(10, 30, 40)
    m = market(rng, d=np.where(np.arange(40) % 7 == 3, 0.1, 0.0))
    full = tr_index(m)
    for k in (0, 5, 17, 39):
        assert np.array_equal(tr_index(m.truncate(k)), full[:k + 1], equal_nan=True)


# ================================================================ signals

def test_mom_signal_skip_month_ranking_ties_and_eligibility():
    n = 260
    t = n - 1
    tr = np.ones((n, 7))
    gains = [0.5, 0.2, 0.2, -0.1, 0.9, 0.3, 0.0]
    for j, g in enumerate(gains):
        tr[t - 21, j] = 1 + g
        tr[t - 20:, j] = 100.0                   # closes t-20..t are NOT used
    tr[t - 252, 6] = np.nan                      # ineligible
    tick = tuple("ABCDEFG")
    tg = sg.mom_targets(tr, t, list(range(7)), tick)
    assert list(tg) == [4, 0, 5, 1, 2] and all(w == 0.2 for w in tg.values())   # B before C on the 0.2 tie


def test_str_z_score_matches_formula_and_selects_five_lowest():
    rs = np.random.default_rng(3)                # fixture generation only; the engine uses no randomness
    tr = np.cumprod(1 + rs.normal(0, 0.01, (70, 8)), axis=0)
    t = 69
    z = sg.str_scores(tr, t, list(range(8)))
    r5 = tr[t] / tr[t - 5] - 1
    sig = np.std(tr[t - 59:t + 1] / tr[t - 60:t] - 1, axis=0, ddof=1)
    exp = (r5 - r5.mean()) / (sig * math.sqrt(5))
    assert all(z[j] == pytest.approx(exp[j]) for j in range(8))
    tg = sg.str_targets(tr, t, list(range(8)), tuple("ABCDEFGH"))
    assert set(tg) == set(np.argsort(exp)[:5]) and len(tg) == 5


def test_str_eligibility_requires_61_closes_and_positive_sigma():
    tr = np.ones((70, 3))
    tr[:, 1] = np.linspace(1, 2, 70)
    tr[30, 2] = np.nan
    assert set(sg.str_scores(tr, 69, [0, 1, 2])) == {1}   # flat series sigma = 0; NaN inside the window


def test_lrv_formation_greedy_disjoint_sigma_trigger_lagging():
    base = np.linspace(1, 2, 252)
    tr = np.stack([base, base * 1.001, base * 1.5, base * 1.502, base ** 2, base ** 2.01], axis=1)
    pairs = sg.lrv_formation(tr, 251, list(range(6)), tuple("ABCDEF"))
    assert [(p.i, p.j) for p in pairs] == [(0, 1), (2, 3), (4, 5)]          # disjoint, ascending SSD
    D = tr[:, 4] / tr[0, 4] - tr[:, 5] / tr[0, 5]
    assert pairs[2].sigma == pytest.approx(np.std(D, ddof=1))
    p = sg.Pair(0, 1, 0.0, 0.1)
    assert not sg.lrv_trigger(0.2, p) and sg.lrv_trigger(0.2000001, p)      # strict
    assert sg.lrv_lagging(0.3, p) == 1 and sg.lrv_lagging(-0.3, p) == 0


# ================================================================ engine / accounting

def _flat_sim(s, opens, closes, decide, dec_idx, q=None, d=None):
    m = market(closes, opens=opens, q=q, d=d)
    return en.simulate_targets(m, decide, dec_idx, s, 1, len(m.sessions) - 1, "X"), m


def test_order_of_operations_lambda_costs_and_liquidation():
    s = 0.001
    closes = np.array([[10.0, 20.0]] * 4)
    res, _ = _flat_sim(s, closes, closes, lambda t: {0: 0.5, 1: 0.5}, [0])
    B = 100_000.0
    lam = min(1.0, B / (B * (1 + s)))
    assert res.fills[0]["lambda"] == pytest.approx(lam) and res.fills[0]["cost"] == pytest.approx(0.5 * B * lam * s)
    invested = lam * B
    assert res.pre_liq_last == pytest.approx(invested)                       # cash 0 after lambda-scaled buys
    assert res.equity[-1] == pytest.approx(invested * (1 - s))               # liquidation cost once, at the end
    assert res.costs == pytest.approx(invested * s + invested * s)


def test_resize_sell_before_buy_and_turnover():
    closes = np.array([[10.0, 10.0, 10.0]] * 3 + [[20.0, 10.0, 10.0]] * 3)
    dec = {0: {0: 0.5, 1: 0.5}, 3: {0: 0.5, 2: 0.5}}
    res, _ = _flat_sim(0.0, closes, closes, lambda t: dec[t], [0, 3])
    ex = [f for f in res.fills if f["session"] == SESS[4].isoformat()]
    assert [f["side"] for f in ex] == ["sell", "sell", "buy"]                # T00 resized down, T01 sold, T02 bought
    E = 50_000 * 2 + 50_000
    assert res.executions[1]["E_open"] == pytest.approx(E)
    assert res.executions[1]["turnover"] == pytest.approx(0.5 * (25_000 + 50_000 + 75_000) / E)


def test_dividend_uses_previous_close_shares_and_split_scales_shares():
    closes = np.array([[10.0]] * 3 + [[5.0]] * 3)
    q = np.ones((6, 1)); q[3, 0] = 2.0
    d = np.zeros((6, 1)); d[2, 0] = 0.5
    res, _ = _flat_sim(0.0, closes, closes, lambda t: {0: 1.0}, [0], q=q, d=d)
    assert res.dividends == pytest.approx(10_000 * 0.5)                      # 10,000 shares bought at 10
    assert res.equity[-1] == pytest.approx(20_000 * 5.0 + 5_000)             # split: shares x 2, dividend as cash


def test_missing_open_cancels_buy_and_makes_pending_sell():
    o = np.array([[10.0, 10.0], [10.0, np.nan], [10.0, 10.0], [np.nan, 10.0], [10.0, 10.0], [10.0, 10.0]])
    c = np.full((6, 2), 10.0)
    dec = {0: {0: 0.5, 1: 0.5}, 2: {1: 0.5}}
    res, _ = _flat_sim(0.0, o, c, lambda t: dec[t], [0, 2])
    assert [(f["session"], f["ticker"], f["side"]) for f in res.fills] == [
        (SESS[1].isoformat(), "T00", "buy"), (SESS[3].isoformat(), "T01", "buy"), (SESS[4].isoformat(), "T00", "sell")]


def test_lrv_per_slot_lambda_never_lends_across_slots():
    n, f = 400, 252                            # full 252-session formation window before the segment
    tr = np.ones((n, 4))
    tr[f + 2:, 1] = 0.5                        # pair (T00,T01) diverges at close f+2 -> buy lagging T01 at open f+3
    m = market(np.ones((n, 4)) * 10.0)
    st = en.simulate_lrv(m, tr, 0.001, f, n - 1, upto=f + 5)
    assert st.decisions[0]["close"] == SESS[f - 1].isoformat() and len(st.decisions[0]["formation"]) == 2
    buys = [x for x in st.fills if x["side"] == "buy"]
    assert len(buys) == 1 and buys[0]["ticker"] == "T01" and buys[0]["session"] == SESS[f + 3].isoformat()
    assert buys[0]["lambda"] == pytest.approx(1 / 1.001)
    slot_cap = 100_000 / 5
    assert buys[0]["notional"] * (1 + 0.001) == pytest.approx(slot_cap)     # spends exactly its own capital
    assert st.equity[-1] == pytest.approx(100_000 - slot_cap + buys[0]["notional"])   # other slots' cash untouched


def test_lrv_exit_same_close_rule_reentry_and_period_end():
    n, f = 520, 252
    tr = np.ones((n, 4))
    tr[f + 2:, 1] = 0.5                        # close f+2: S = +0.5 -> entry T01 (s0 = +1) at open f+3
    tr[f + 6:, 1] = 1.5                        # close f+6: S = -0.5 -> exit (s0*S < 0); NO entry on this close
    m = market(np.ones((n, 4)) * 10.0)
    st = en.simulate_lrv(m, tr, 0.0, f, n - 1)
    seq = [(x["session"], x["ticker"], x["side"]) for x in st.fills]
    assert seq[:3] == [(SESS[f + 3].isoformat(), "T01", "buy"), (SESS[f + 7].isoformat(), "T01", "sell"),
                       (SESS[f + 8].isoformat(), "T00", "buy")]                # re-entry at the close after flat
    # still diverged after p125 = f+125 -> sold at the open of p126 (next cycle start)
    assert (SESS[f + 126].isoformat(), "T00", "sell") in seq
    acts = [x for x in st.decisions if x.get("action")]
    assert not any(x["close"] == SESS[f + 6].isoformat() and x["action"] == "entry" for x in acts)
    assert all(x["close"] <= SESS[f + 124].isoformat() or x["close"] >= SESS[f + 126].isoformat() for x in acts)
    assert [x["close"] for x in st.decisions if "formation" in x][:2] == [SESS[f - 1].isoformat(),
                                                                          SESS[f + 125].isoformat()]


def test_benchmark_buy_and_hold_never_rebalances():
    closes = np.array([[10.0, 10.0], [10.0, 10.0], [20.0, 10.0], [40.0, 10.0]])
    res, _ = _flat_sim(0.0, closes, closes, lambda t: {0: 0.5, 1: 0.5}, [0])
    assert len(res.executions) == 1 and res.equity[-1] == pytest.approx(5_000 * 40 + 5_000 * 10)


# ================================================================ metrics

def test_metric_formulas():
    r = np.array([0.01, -0.02, 0.03, -0.01])
    assert mt._sortino(r) == pytest.approx(np.mean(r) / math.sqrt(np.mean(np.minimum(r, 0) ** 2)) * math.sqrt(252))
    assert mt._mdd(np.array([100, 120, 90, 130, 65])) == pytest.approx(0.5)
    assert mt.cagr(121_000, 504) == pytest.approx(0.1)
    adj = mt.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}
    t, p = mt.hac_t(np.array([0.001] * 50 + [-0.0005] * 50))
    assert math.isfinite(t) and 0 <= p <= 1


# ================================================================ §7 PIT on synthetic data

def test_decisions_identical_under_truncation_and_future_mutation():
    n = 300
    rs = np.random.default_rng(5)
    c = np.cumprod(1 + rs.normal(0, 0.01, (n, 8)), axis=0) * 50
    m = market(c)
    tr = tr_index(m)
    uni = list(range(8))
    for t in (260, 280, 299):
        full = sg.mom_targets(tr, t, uni, m.tickers)
        assert sg.mom_targets(tr_index(m.truncate(t)), t, uni, m.tickers) == full
        c2 = c.copy(); c2[t + 1:] *= 3.0
        assert sg.mom_targets(tr_index(market(c2)), t, uni, m.tickers) == full
        assert sg.str_targets(tr_index(m.truncate(t)), t, uni, m.tickers) == sg.str_targets(tr, t, uni, m.tickers)
