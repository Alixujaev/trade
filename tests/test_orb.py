"""tests/test_orb.py: ORB strategy - offline synthetic 5m bars (no network, no provider, no real data).

Covers: opening range, point-in-time signal (no lookahead), window/VWAP/volume/first-breakout rules, penny and
earnings filters (fail closed), sizing/costs/exits, daily risk gate, and backtest <-> paper parity.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import math

import pandas as pd
import pytest

from backtest.orb_engine import run_orb_backtest
from data.earnings import EarningsCoverageError, load_earnings_calendar
from data.session import NY_TZ
from indicators.volume import is_volume_confirmed
from paper_orb import runner as po
from strategy.day import orb
from strategy.day.orb_rules import OrbCarry, OrbRules, plan_entry, simulate_session

D0, D1, D2, D3 = date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5)
RULES = OrbRules(initial_capital=100_000.0)
BREAKOUT = {                                    # base 100: OR 99.5..100.5, signal 09:50, entry 09:55 open 101.0
    time(9, 30): dict(open=100.0, high=100.5, low=99.5, close=100.1),
    time(9, 45): dict(open=100.1, high=100.4, low=100.0, close=100.3),
    time(9, 50): dict(open=100.4, high=101.1, low=100.35, close=101.0, volume=5000.0),
    time(9, 55): dict(open=101.0, high=101.2, low=100.8, close=101.1),
}


def day_df(day: date, overrides: dict | None = None, *, base: float = 100.0, vol: float = 1000.0,
           last: time = time(15, 55), scale: float = 1.0) -> pd.DataFrame:
    t = datetime.combine(day, time(9, 30), NY_TZ)
    end = datetime.combine(day, last, NY_TZ)
    rows, idx = [], []
    while t <= end:
        r = dict(open=base, high=base + 0.05, low=base - 0.05, close=base, volume=vol)
        r.update((overrides or {}).get(t.time(), {}))
        rows.append({k: (v * scale if k != "volume" else v) for k, v in r.items()})
        idx.append(t)
        t += timedelta(minutes=5)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx).tz_convert("UTC")).rename_axis("datetime")


def hist(*parts: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(parts).sort_index()


def ov(*extra: tuple[time, dict]) -> dict:
    o = {k: dict(v) for k, v in BREAKOUT.items()}
    for t, d in extra:
        o.setdefault(t, {}).update(d)
    return o


@pytest.fixture
def earnings(tmp_path):
    def make(symbols=("AAA", "BBB", "CCC"), start=D0, end=D3, days: dict | None = None):
        p = tmp_path / "earn.csv"
        lines = ["symbol,coverage_start,coverage_end,earnings_date"]
        for s in symbols:
            ds = (days or {}).get(s, [])
            lines += [f"{s},{start},{end},{d}" for d in ds] or [f"{s},{start},{end},"]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return load_earnings_calendar(p)
    return make


def run1(bars, earnings_cal, session=D1, rules=RULES):
    return simulate_session(bars, session, rules, earnings_cal, OrbCarry())


# ------------------------------------------------------------------ signal

def test_opening_range_uses_exactly_the_three_or_bars():
    sdf = day_df(D1, BREAKOUT)
    assert orb.opening_range(sdf) == (100.5, 99.5)
    missing = sdf.drop(sdf.index[1])                                          # 09:35 bar missing
    assert orb.opening_range(missing) is None


def test_signal_entry_is_next_bar_and_point_in_time():
    df = hist(day_df(D0), day_df(D1, BREAKOUT))
    sig = orb.find_signal("AAA", df, orb.precompute(df), D1)
    assert sig is not None
    assert sig.signal_time.tz_convert(NY_TZ).time() == time(9, 50)
    assert sig.entry_time.tz_convert(NY_TZ).time() == time(9, 55)
    assert (sig.or_high, sig.or_low) == (100.5, 99.5)
    # truncate everything after the signal bar's successor, or perturb the future: same signal
    cut = df.loc[: sig.entry_time]
    assert orb.find_signal("AAA", cut, orb.precompute(cut), D1) == sig
    wild = df.copy()
    wild.loc[wild.index > sig.entry_time, ["open", "high", "low", "close", "volume"]] = [5.0, 500.0, 1.0, 400.0, 1e9]
    assert orb.find_signal("AAA", wild, orb.precompute(wild), D1) == sig
    # without the entry bar the signal cannot be acted on
    sig_only = df.loc[: sig.signal_time]
    assert orb.find_signal("AAA", sig_only, orb.precompute(sig_only), D1) is None


def test_precompute_matches_existing_volume_rule_and_vwap_is_causal():
    df = hist(day_df(D0), day_df(D1, BREAKOUT))
    f = orb.precompute(df)
    assert [bool(f.volume_ok.iloc[i]) for i in range(len(df))] == [is_volume_confirmed(df, i) for i in range(len(df))]
    k = 100
    assert orb.precompute(df.iloc[:k]).vwap.equals(f.vwap.iloc[:k])


def test_window_bounds():
    late = {t: v for t, v in BREAKOUT.items() if t < time(9, 45)}
    late[time(11, 0)] = dict(open=100.4, high=101.1, low=100.35, close=101.0, volume=5000.0)     # bar 11:00 -> no
    df = hist(day_df(D0), day_df(D1, late))
    assert orb.find_signal("AAA", df, orb.precompute(df), D1) is None
    ok = dict(late)
    ok[time(10, 55)] = ok.pop(time(11, 0))                                                       # bar 10:55 -> yes
    df = hist(day_df(D0), day_df(D1, ok))
    assert orb.find_signal("AAA", df, orb.precompute(df), D1).signal_time.tz_convert(NY_TZ).time() == time(10, 55)
    early = {time(9, 30): dict(open=100.0, high=100.5, low=99.5, close=100.1),
             time(9, 40): dict(open=100.1, high=100.4, low=100.0, close=100.45, volume=5000.0)}  # OR bar itself
    df = hist(day_df(D0), day_df(D1, early))
    assert orb.find_signal("AAA", df, orb.precompute(df), D1) is None


def test_vwap_and_volume_each_reject_and_first_valid_bar_wins():
    df = hist(day_df(D0), day_df(D1, BREAKOUT))
    f = orb.precompute(df)
    sig_ts = orb.find_signal("AAA", df, f, D1).signal_time
    hi_vwap = orb.OrbFeatures(vwap=f.vwap.where(f.vwap.index != sig_ts, 101.5), volume_ok=f.volume_ok)
    assert orb.find_signal("AAA", df, hi_vwap, D1) is None
    no_vol = orb.OrbFeatures(vwap=f.vwap, volume_ok=f.volume_ok.where(f.volume_ok.index != sig_ts, False))
    assert orb.find_signal("AAA", df, no_vol, D1) is None
    # 09:50 fails volume, 10:05 qualifies -> the 10:05 bar is the (first valid) signal
    two = ov((time(9, 50), dict(volume=1000.0)),
             (time(10, 5), dict(open=100.6, high=101.3, low=100.55, close=101.2, volume=6000.0)))
    df = hist(day_df(D0), day_df(D1, two))
    assert orb.find_signal("AAA", df, orb.precompute(df), D1).signal_time.tz_convert(NY_TZ).time() == time(10, 5)


# ------------------------------------------------------------------ filters

def test_penny_and_missing_prior_close_and_earnings_are_skipped(earnings):
    bars = {"AAA": hist(day_df(D0, scale=0.04), day_df(D1, BREAKOUT, scale=0.04)),     # prior close $4
            "BBB": day_df(D1, BREAKOUT),                                              # no prior session
            "CCC": hist(day_df(D0), day_df(D1, BREAKOUT))}
    trades, skips, _ = run1(bars, earnings(days={"CCC": [D1]}))
    assert trades == []
    assert {(s["symbol"], s["reason"]) for s in skips} == {
        ("AAA", "penny_stock"), ("BBB", "no_prior_close"), ("CCC", "earnings_day")}


def test_earnings_calendar_fails_closed(tmp_path, earnings):
    with pytest.raises(EarningsCoverageError, match="not found"):
        load_earnings_calendar(tmp_path / "nope.csv")
    cal = earnings(symbols=("AAA",), start=D0, end=D1)
    with pytest.raises(EarningsCoverageError, match="no coverage for BBB"):
        cal.check_coverage(["AAA", "BBB"], D0, D1)
    with pytest.raises(EarningsCoverageError, match="required"):
        cal.check_coverage(["AAA"], D0, D2)
    bad = tmp_path / "bad.csv"
    bad.write_text("symbol,coverage_start,coverage_end,earnings_date\nAAA,2026-03-02,2026-03-05,\n"
                   "AAA,2026-03-02,2026-03-06,\n", encoding="utf-8")
    with pytest.raises(EarningsCoverageError, match="inconsistent coverage"):
        load_earnings_calendar(bad)
    bars = {"AAA": hist(day_df(D0), day_df(D1, BREAKOUT), day_df(D2))}
    with pytest.raises(EarningsCoverageError):
        run_orb_backtest(bars, RULES, cal, D1, D2)                              # D2 not covered -> nothing runs


# ------------------------------------------------------------------ sizing, costs, exits

def _expected(entry_open, exit_raw, shares, risk, rules=RULES):
    ef, xf = entry_open * 1.0005, exit_raw * 0.9995
    pnl = (xf - ef) * shares - 2 * 0.005 * shares
    return pnl, pnl / (shares * risk)


def test_target_2r_sizing_and_exact_costs(earnings):
    bars = {"AAA": hist(day_df(D0), day_df(D1, ov((time(10, 30), dict(high=104.2, close=103.0)))))}
    (t,), _, carry = run1(bars, earnings())
    assert t["shares"] == math.floor(0.0025 * 100_000 / 1.5) == 166
    assert (t["entry_open"], t["stop"], t["target"], t["risk_per_share"]) == (101.0, 99.5, 104.0, 1.5)
    assert t["entry_fill"] == pytest.approx(101.0 * 1.0005)
    assert t["exit_reason"] == "TARGET" and t["exit_raw"] == 104.0
    pnl, r = _expected(101.0, 104.0, 166, 1.5)
    assert t["pnl"] == pytest.approx(pnl) and t["r_multiple"] == pytest.approx(r)
    assert carry.realised_pnl_total == pytest.approx(pnl) and carry.last_session == D1


def test_stop_first_gap_through_stop_and_force_exit(earnings):
    both = ov((time(10, 0), dict(high=104.5, low=99.0)))
    (t,), _, _ = run1({"AAA": hist(day_df(D0), day_df(D1, both))}, earnings())
    assert (t["exit_reason"], t["exit_raw"]) == ("STOP", 99.5)                    # same bar -> STOP_FIRST
    gap = ov((time(10, 0), dict(open=98.0, high=98.2, low=97.5, close=98.0)))
    (t,), _, _ = run1({"AAA": hist(day_df(D0), day_df(D1, gap))}, earnings())
    assert (t["exit_reason"], t["exit_raw"]) == ("STOP", 98.0)                    # gap below stop -> open
    flat = ov((time(15, 55), dict(open=100.7)))
    (t,), _, _ = run1({"AAA": hist(day_df(D0), day_df(D1, flat))}, earnings())
    assert t["exit_reason"] == "FORCE_EXIT_1555" and t["exit_raw"] == 100.7
    assert pd.Timestamp(t["exit_time"]).tz_convert(NY_TZ).time() == time(15, 55)
    short = {"AAA": hist(day_df(D0), day_df(D1, ov((time(12, 55), dict(close=100.9))), last=time(12, 55)))}
    (t,), _, _ = run1(short, earnings())
    assert t["exit_reason"] == "SESSION_END" and t["exit_raw"] == 100.9          # early close


def test_entry_open_not_above_stop_and_capital_cap():
    assert plan_entry(99.5, 99.5, 1e9, RULES) == (None, "entry_not_above_stop")
    p, why = plan_entry(101.0, 100.9, 100_000.0, RULES)                        # risk 0.1 -> 2500 shares wanted
    assert why == "ok" and p.capped and p.shares == math.floor(100_000.0 / (101.0 * 1.0005 + 0.005))
    assert plan_entry(101.0, 100.9, 50.0, RULES) == (None, "insufficient_capital")


# ------------------------------------------------------------------ daily risk gate

def _sym(day_over):
    return hist(day_df(D0), day_df(D1, day_over))


def test_max_two_trades_and_max_two_open_positions(earnings):
    same = {s: _sym(BREAKOUT) for s in ("AAA", "BBB", "CCC")}
    trades, skips, _ = run1(same, earnings())
    assert [t["symbol"] for t in trades] == ["AAA", "BBB"]
    assert {"symbol": "CCC", "reason": "max_trades_per_day"} == {k: skips[-1][k] for k in ("symbol", "reason")}
    loose = OrbRules(initial_capital=100_000.0, max_trades_per_day=3)
    trades, skips, _ = run1(same, earnings(), rules=loose)
    assert len(trades) == 2 and skips[-1]["reason"] == "max_open_positions"


def test_daily_loss_limit_stops_new_entries(earnings):
    stop = ov((time(10, 0), dict(low=99.0, close=99.2)))
    late = {t: v for t, v in BREAKOUT.items() if t < time(9, 50)}
    late[time(10, 30)] = dict(open=100.4, high=101.1, low=100.35, close=101.0, volume=5000.0)
    bars = {"AAA": _sym(stop), "BBB": _sym(stop), "CCC": _sym(late)}
    loose = OrbRules(initial_capital=100_000.0, max_trades_per_day=3)
    trades, skips, _ = run1(bars, earnings(), rules=loose)
    assert [t["symbol"] for t in trades] == ["AAA", "BBB"] and sum(t["r_multiple"] for t in trades) <= -2.0
    assert (skips[-1]["symbol"], skips[-1]["reason"]) == ("CCC", "daily_loss_limit")


def test_combined_notional_never_exceeds_available_capital(earnings):
    tight = {t: dict(v) for t, v in BREAKOUT.items()}
    for t in (time(9, 30), time(9, 35), time(9, 40)):                          # OR 100.45..100.5
        tight[t] = dict(open=100.48, high=100.5, low=100.45, close=100.48)
    tight[time(9, 55)] = dict(open=100.6, high=100.7, low=100.5, close=100.6)   # risk 0.15 -> 166 shares wanted
    small = OrbRules(initial_capital=10_000.0)
    trades, skips, _ = run1({"AAA": _sym(tight), "BBB": _sym(tight)}, earnings(), rules=small)
    assert [t["symbol"] for t in trades] == ["AAA"] and trades[0]["capped"]
    assert trades[0]["shares"] * (trades[0]["entry_fill"] + 0.005) <= 10_000.0
    assert (skips[-1]["symbol"], skips[-1]["reason"]) == ("BBB", "insufficient_capital")


# ------------------------------------------------------------------ backtest <-> paper parity

def _three_days():
    tp = ov((time(10, 30), dict(high=104.2)))
    st = ov((time(10, 0), dict(low=99.0)))
    return {"AAA": hist(day_df(D0), day_df(D1, tp), day_df(D2, st), day_df(D3, BREAKOUT)),
            "BBB": hist(day_df(D0), day_df(D1, st), day_df(D2), day_df(D3, tp))}


def test_backtest_and_paper_produce_identical_ledgers(tmp_path, earnings):
    bars, cal = _three_days(), earnings(symbols=("AAA", "BBB"))
    bt = run_orb_backtest(bars, RULES, cal, D1, D3)
    paper_trades = []
    for d in (D1, D2, D3):
        visible = {s: df.loc[df.index < pd.Timestamp(datetime.combine(d + timedelta(days=1), time(0), NY_TZ))]
                   for s, df in bars.items()}                                    # paper sees data up to d only
        assert po.process_session(d, visible, RULES, cal, tmp_path)["status"] == "OK"
        paper_trades += json.loads((tmp_path / "sessions" / f"{d}.json").read_text(encoding="utf-8"))["trades"]
    assert len(bt.trades) == 5
    assert json.dumps(paper_trades, sort_keys=True) == json.dumps(bt.trades, sort_keys=True)
    assert po.load_carry(tmp_path).to_dict() == bt.carry.to_dict()


def test_paper_is_idempotent_ordered_and_rule_locked(tmp_path, earnings):
    bars, cal = _three_days(), earnings(symbols=("AAA", "BBB"))
    assert po.process_session(D2, bars, RULES, cal, tmp_path)["status"] == "OK"
    before = (tmp_path / "sessions" / f"{D2}.json").read_bytes()
    assert po.process_session(D2, bars, RULES, cal, tmp_path)["status"] == "NOOP"
    assert (tmp_path / "sessions" / f"{D2}.json").read_bytes() == before
    with pytest.raises(ValueError, match="not after"):
        po.process_session(D1, bars, RULES, cal, tmp_path)
    with pytest.raises(po.PaperOrbError, match="rules"):
        po.process_session(D3, bars, OrbRules(initial_capital=50_000.0), cal, tmp_path)


def test_paper_orb_has_no_order_or_broker_code():
    import inspect
    src = inspect.getsource(po) + inspect.getsource(__import__("strategy.day.orb_rules", fromlist=["x"]))
    for banned in ("submit_order", "TradingClient", "place_order", "paper-api.alpaca", "api.alpaca.markets/v2/orders"):
        assert banned not in src
