"""backtest/portfolio.py uchun testlar (sintetik OHLCV + qo'lda qurilgan setup'lar, tarmoqsiz)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_backtest
from backtest.metrics import max_drawdown_pct
from backtest.portfolio import (
    PortfolioConfig,
    SymbolData,
    avg_concurrent_positions,
    build_candidates,
    cagr_pct,
    curve_metrics,
    curve_return_pct,
    equal_weight_buy_hold_curve,
    max_concurrent_positions,
    naive_all_signals_curve,
    periodic_returns,
    run_portfolio,
    sharpe_ratio,
    simulate_portfolio,
    single_ticker_buy_hold_curve,
    sortino_ratio,
    _periods_per_year_for,
)
from scripts.backtest_breakout_retest import portfolio_equity_curve
from smc.types import StructureState, TradeSetup

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _make_df(rows: list[dict], *, start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    if "volume" not in df.columns:
        df["volume"] = 1000
    return df[_COLUMNS]


def _flat_rows(prices: list[float]) -> list[dict]:
    return [{"open": p, "high": p, "low": p, "close": p} for p in prices]


def _setup(entry_index_pos: int, *, entry: float, stop: float, target: float,
           ts: pd.Timestamp) -> TradeSetup:
    return TradeSetup(
        entry_ts=ts, entry_price=entry, stop_price=stop, target_price=target,
        direction=StructureState.BULLISH, entry_index_pos=entry_index_pos,
        reason=f"BREAKOUT_RETEST@{stop:.2f}-{entry:.2f}",
    )


def _sym(symbol: str, df: pd.DataFrame, setups: list[TradeSetup]) -> SymbolData:
    return SymbolData(symbol=symbol, df=df, signals=sorted(setups, key=lambda s: s.entry_index_pos))


# ======================================================================
# Sof metrika helper'lari
# ======================================================================


def test_periodic_returns_hand() -> None:
    assert periodic_returns([100, 110, 99]) == pytest.approx([0.1, -0.1])
    assert periodic_returns([100]) == []
    assert periodic_returns([0, 5]) == [0.0]  # E[k-1]==0 -> 0.0


def test_curve_return_pct() -> None:
    assert curve_return_pct([100, 150]) == pytest.approx(50.0)
    assert curve_return_pct([100]) == 0.0
    assert curve_return_pct([0, 5]) == 0.0


def test_cagr_pct_hand_verified() -> None:
    t = [pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")]
    # 731 kun / 365.25 = 2.00137 yil ; 2**(1/2.00137) - 1 ≈ 0.4139
    assert cagr_pct([100.0, 200.0], t) == pytest.approx(41.39, abs=0.05)
    assert cagr_pct([100.0], t) == 0.0
    assert cagr_pct([100.0, 0.0], t) == 0.0
    assert cagr_pct([0.0, 100.0], t) == 0.0


def test_sharpe_hand_verified() -> None:
    e = [100.0, 101.0, 102.0, 101.5]
    r = np.diff(e) / np.array(e[:-1])
    expected = r.mean() / r.std(ddof=1) * np.sqrt(252)
    assert sharpe_ratio(e, periods_per_year=252) == pytest.approx(expected)


def test_sharpe_zero_when_constant_or_short() -> None:
    assert sharpe_ratio([100, 100, 100], periods_per_year=252) == 0.0
    assert sharpe_ratio([100], periods_per_year=252) == 0.0


def test_sortino_hand_verified() -> None:
    e = [100.0, 101.0, 102.0, 101.5]
    r = np.diff(e) / np.array(e[:-1])
    downside = np.minimum(r, 0.0)
    dd = np.sqrt((downside**2).sum() / len(r))
    expected = r.mean() / dd * np.sqrt(252)
    assert sortino_ratio(e, periods_per_year=252) == pytest.approx(expected)


def test_sortino_zero_when_no_downside() -> None:
    assert sortino_ratio([100, 101, 102, 103], periods_per_year=252) == 0.0


def test_avg_concurrent_positions_active_span() -> None:
    samples = [0, 0, 1, 2, 2, 1, 0, 0]
    assert avg_concurrent_positions(samples, active_span_only=True) == pytest.approx(1.5)
    assert avg_concurrent_positions(samples, active_span_only=False) == pytest.approx(0.75)
    assert avg_concurrent_positions([], active_span_only=True) == 0.0
    assert avg_concurrent_positions([0, 0, 0], active_span_only=True) == 0.0


def test_max_concurrent_positions() -> None:
    assert max_concurrent_positions([0, 3, 1, 2]) == 3
    assert max_concurrent_positions([]) == 0


def test_periods_per_year_for() -> None:
    assert _periods_per_year_for("1d") == 252.0
    assert _periods_per_year_for("1wk") == 52.0
    assert _periods_per_year_for("4h") == 1512.0
    assert _periods_per_year_for("1h") == 1638.0
    assert _periods_per_year_for("noma'lum") == 252.0


def test_curve_metrics_keys() -> None:
    e = [100.0, 90.0, 110.0, 105.0]
    t = list(pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC"))
    m = curve_metrics(e, t, periods_per_year=252)
    assert set(m) == {"return_pct", "cagr_pct", "max_drawdown_pct", "sharpe", "sortino"}
    assert m["max_drawdown_pct"] == max_drawdown_pct(e)


# ======================================================================
# Benchmark egri chiziqlari
# ======================================================================


def test_single_ticker_buy_hold_curve_math() -> None:
    df = _make_df(_flat_rows([100, 110, 120]))
    tl = list(df.index)
    curve = single_ticker_buy_hold_curve(df, tl, initial_capital=1000, commission_pct=0.0, slippage_pct=0.0)
    assert curve == pytest.approx([1000.0, 1100.0, 1200.0])


def test_equal_weight_buy_hold_curve_late_starter() -> None:
    # A: 01-01..01-04 tekis 100 ; B: 01-03..01-04, close [50, 60]
    a = _sym("A", _make_df(_flat_rows([100, 100, 100, 100])), [])
    b = _sym("B", _make_df(_flat_rows([50, 60]), start="2024-01-03"), [])
    tl = list(pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC"))
    curve = equal_weight_buy_hold_curve([a, b], tl, initial_capital=1000, commission_pct=0.0, slippage_pct=0.0)
    # alloc=500. A: shares=5. B ikki kun kech: k0,k1 -> B ulushi 500 naqd; k2: 500+10*50=1000; k3: 500+10*60=1100
    assert curve == pytest.approx([1000.0, 1000.0, 1000.0, 1100.0])


def test_equal_weight_delisted_symbol_freezes() -> None:
    a = _sym("A", _make_df(_flat_rows([100, 100, 100, 100])), [])
    b = _sym("B", _make_df(_flat_rows([50, 80]), start="2024-01-01"), [])  # B 2 kundan keyin "delisted"
    tl = list(pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC"))
    curve = equal_weight_buy_hold_curve([a, b], tl, initial_capital=1000, commission_pct=0.0, slippage_pct=0.0)
    # alloc=500. A shares=5 (doim 100). B shares=10, close ffill: [50,80,80,80]
    # k0: 500+500=1000 ; k1: 500+800=1300 ; k2,k3: muzlaydi 1300
    assert curve == pytest.approx([1000.0, 1300.0, 1300.0, 1300.0])


# ======================================================================
# Oldindan hisoblash — engine parity
# ======================================================================


def test_precompute_candidate_matches_engine_fixed() -> None:
    df = _make_df([
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 100, "high": 108, "low": 95, "close": 105},
        {"open": 105, "high": 125, "low": 104, "close": 120},
    ])
    setup = _setup(0, entry=100.0, stop=90.0, target=120.0, ts=df.index[0])
    cfg = PortfolioConfig(exit_mode="fixed")
    cands, degen = build_candidates([_sym("X", df, [setup])], cfg=cfg)

    assert degen == []
    c = cands[0]
    from backtest.engine import _simulate_fixed_exit
    exp = _simulate_fixed_exit(df, setup, df["close"].to_numpy(), df["high"].to_numpy(),
                               df["low"].to_numpy(), len(df))
    assert (c.exit_index_pos, c.exit_price, c.exit_reason, c.min_low, c.running_high) == pytest.approx(exp)


def test_precompute_candidate_matches_engine_trailing() -> None:
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 100, "high": 101, "low": 99, "close": 101},
        {"open": 101, "high": 102, "low": 100, "close": 102},
        {"open": 102, "high": 103, "low": 101, "close": 103},
        {"open": 103, "high": 104, "low": 102, "close": 103},
        {"open": 103, "high": 103.5, "low": 99, "close": 100},
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df.index[0])
    cfg = PortfolioConfig(exit_mode="trailing", trail_atr_mult=1.0, atr_period=3)
    cands, _ = build_candidates([_sym("X", df, [setup])], cfg=cfg)

    c = cands[0]
    assert c.exit_reason == "trailing_stop"
    assert c.exit_price == pytest.approx(102.0)
    assert c.exit_index_pos == 5


def test_precompute_degenerate_setup_returns_none() -> None:
    df = _make_df(_flat_rows([100, 101, 102]))
    bad = _setup(0, entry=100.0, stop=100.0, target=110.0, ts=df.index[0])  # entry-stop == 0
    cfg = PortfolioConfig()
    cands, degen = build_candidates([_sym("X", df, [bad])], cfg=cfg)

    assert cands == []
    assert len(degen) == 1 and degen[0].reason == "degenerate_setup"

    res = simulate_portfolio([_sym("X", df, [bad])], cfg=cfg)
    assert res.metrics["skipped_by_reason"] == {"degenerate_setup": 1}
    assert res.metrics["num_trades"] == 0


# ======================================================================
# Yadro simulyator
# ======================================================================


def _target_df(entry: float, target: float, hit_bar: int, n: int) -> pd.DataFrame:
    """entry narxidan boshlanadigan, hit_bar'da target'ga tegadigan sodda df."""
    rows = []
    for i in range(n):
        if i == hit_bar:
            rows.append({"open": entry, "high": target + 1, "low": entry - 0.5, "close": target})
        else:
            rows.append({"open": entry, "high": entry + 0.5, "low": entry - 0.5, "close": entry})
    return _make_df(rows)


def test_single_position_matches_engine() -> None:
    df = _target_df(100.0, 110.0, hit_bar=2, n=4)
    setup = _setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0])
    cfg = PortfolioConfig(initial_capital=10_000.0, risk_pct=0.01, max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([_sym("X", df, [setup])], cfg=cfg)
    eng = run_backtest(df, [setup], initial_capital=10_000.0, risk_pct=0.01)

    assert len(res.trades) == 1 and len(eng.trades) == 1
    p, e = res.trades[0], eng.trades[0]
    assert p.shares == pytest.approx(e.shares)
    assert p.exit_price == pytest.approx(e.exit_price)
    assert p.exit_reason == e.exit_reason
    assert p.pnl == pytest.approx(e.pnl)
    assert p.r_multiple == pytest.approx(e.r_multiple)
    assert p.mae_r == pytest.approx(e.mae_r)
    assert p.mfe_r == pytest.approx(e.mfe_r)
    assert p.hold_duration_days == pytest.approx(e.hold_duration_days)
    assert res.final_capital == pytest.approx(eng.final_capital)


def test_two_concurrent_positions_both_realized() -> None:
    a_df = _target_df(100.0, 110.0, hit_bar=2, n=5)
    b_df = _target_df(50.0, 60.0, hit_bar=3, n=5)
    a = _sym("A", a_df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=a_df.index[0])])
    b = _sym("B", b_df, [_setup(1, entry=50.0, stop=45.0, target=60.0, ts=b_df.index[1])])
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.01, max_portfolio_risk_pct=0.5)

    res = simulate_portfolio([a, b], cfg=cfg)

    assert len(res.trades) == 2
    assert 2 in res.concurrency_samples
    assert res.metrics["max_concurrent_positions"] == 2
    total_pnl = sum(t.pnl for t in res.trades)
    assert res.final_capital == pytest.approx(100_000.0 + total_pnl)
    assert res.equity_curve[-1] == pytest.approx(res.final_capital)


def test_equity_curve_last_equals_final_capital() -> None:
    df = _target_df(100.0, 110.0, hit_bar=2, n=4)
    a = _sym("A", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0])])
    res = simulate_portfolio([a], cfg=PortfolioConfig(max_portfolio_risk_pct=1.0))
    assert res.equity_curve[-1] == pytest.approx(res.final_capital)


def test_max_concurrent_cap_enforced() -> None:
    df = _target_df(100.0, 110.0, hit_bar=2, n=6)
    tl0 = df.index[0]
    a = _sym("A", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=tl0)])
    b = _sym("B", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=tl0)])
    c = _sym("C", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=tl0)])
    d = _sym("D", df, [_setup(3, entry=100.0, stop=90.0, target=110.0, ts=df.index[3])])
    cfg = PortfolioConfig(initial_capital=100_000.0, max_concurrent_positions=1, max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([a, b, c, d], cfg=cfg)

    assert len(res.trades) == 2  # A (idx0) va D (idx3, A yopilgach)
    assert res.metrics["skipped_by_reason"].get("max_concurrent") == 2  # B, C


def test_portfolio_risk_cap_enforced() -> None:
    df = _target_df(100.0, 110.0, hit_bar=2, n=6)
    tl0 = df.index[0]
    a = _sym("A", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=tl0)])
    b = _sym("B", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=tl0)])
    d = _sym("D", df, [_setup(3, entry=100.0, stop=90.0, target=110.0, ts=df.index[3])])
    # risk_pct=0.01 -> har savdo planned_risk = 1% equity ; cap 1.5% -> ikkinchisi sig'maydi
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.01, max_portfolio_risk_pct=0.015,
                          max_concurrent_positions=10)

    res = simulate_portfolio([a, b, d], cfg=cfg)

    assert res.metrics["skipped_by_reason"].get("portfolio_risk_cap") == 1  # B
    assert len(res.trades) == 2  # A va D (A yopilgach open_risk bo'shaydi)


def test_no_leverage_free_cash_shrink() -> None:
    a_df = _target_df(100.0, 105.0, hit_bar=4, n=6)
    b_df = _target_df(200.0, 210.0, hit_bar=4, n=6)
    a = _sym("A", a_df, [_setup(0, entry=100.0, stop=90.0, target=105.0, ts=a_df.index[0])])
    b = _sym("B", b_df, [_setup(1, entry=200.0, stop=195.0, target=210.0, ts=b_df.index[1])])
    # initial 15000, risk_pct 0.05: A notional=7500 -> cash 7500 qoladi.
    # B: equity-cap -> 75 aksiya (15000); free-cash cap -> 7500/200 = 37.5 aksiya.
    cfg = PortfolioConfig(initial_capital=15_000.0, risk_pct=0.05, max_portfolio_risk_pct=0.9,
                          max_concurrent_positions=10)

    res = simulate_portfolio([a, b], cfg=cfg)

    assert len(res.trades) == 2  # ikkalasi ham ochildi
    b_trade = next(t for t in res.trades if t.entry_price == 200.0)
    assert b_trade.shares == pytest.approx(37.5)  # = free_cash(7500) / entry(200)


def test_no_leverage_insufficient_capital_skip() -> None:
    a_df = _target_df(100.0, 105.0, hit_bar=4, n=6)
    b_df = _target_df(100.0, 105.0, hit_bar=4, n=6)
    a = _sym("A", a_df, [_setup(0, entry=100.0, stop=90.0, target=105.0, ts=a_df.index[0])])
    b = _sym("B", b_df, [_setup(1, entry=100.0, stop=90.0, target=105.0, ts=b_df.index[1])])
    # risk_pct 0.5 -> A equity-cap bilan butun kapitalni band qiladi (cash -> ~0)
    cfg = PortfolioConfig(initial_capital=10_000.0, risk_pct=0.5, max_portfolio_risk_pct=1.0,
                          max_concurrent_positions=10)

    res = simulate_portfolio([a, b], cfg=cfg)

    assert len(res.trades) == 1  # faqat A
    assert res.metrics["skipped_by_reason"].get("insufficient_capital") == 1


def test_equity_compounds_across_concurrent_closes() -> None:
    a_df = _target_df(100.0, 110.0, hit_bar=1, n=5)   # A idx1'da yopiladi (foyda)
    b_df = _target_df(100.0, 110.0, hit_bar=4, n=5)
    a = _sym("A", a_df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=a_df.index[0])])
    b = _sym("B", b_df, [_setup(2, entry=100.0, stop=90.0, target=110.0, ts=b_df.index[2])])
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.01, max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([a, b], cfg=cfg)

    a_trade = next(t for t in res.trades if t.exit_index_pos == 1)
    b_trade = next(t for t in res.trades if t.entry_price == 100.0 and t is not a_trade)
    # A: shares = 1%*100000 / 10 = 100. B A yopilgach OSHGAN equity'dan o'lchanadi -> > 100
    assert a_trade.shares == pytest.approx(100.0)
    assert b_trade.shares > 100.0
    assert b_trade.shares == pytest.approx((0.01 * (100_000.0 + a_trade.pnl)) / 10.0)


def test_real_max_dd_exceeds_trade_close_only_dd() -> None:
    df = _make_df([
        {"open": 100, "high": 100.5, "low": 99.5, "close": 100},   # idx0 entry
        {"open": 100, "high": 100, "low": 60, "close": 61},         # idx1 chuqur cho'kish (stop 50 tegmaydi)
        {"open": 61, "high": 101.5, "low": 60, "close": 101},       # idx2 target 101
    ])
    setup = _setup(0, entry=100.0, stop=50.0, target=101.0, ts=df.index[0])
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.10, max_portfolio_risk_pct=0.10)

    res = simulate_portfolio([_sym("X", df, [setup])], cfg=cfg)

    trade_close_only_dd = max_drawdown_pct([res.initial_capital, res.final_capital])
    assert res.metrics["max_drawdown_pct"] > trade_close_only_dd
    assert res.metrics["max_drawdown_pct"] > 5.0  # ~7.8% kutiladi


def test_capital_exhaustion_halts_entries() -> None:
    df = _make_df([
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 100, "high": 100, "low": 0, "close": 1},   # idx1 stop 0 tegadi -> -100%/aksiya
        {"open": 1, "high": 2, "low": 1, "close": 1.5},
        {"open": 1.5, "high": 3, "low": 1, "close": 2},
    ])
    a = _sym("A", df, [_setup(0, entry=100.0, stop=0.0, target=999.0, ts=df.index[0])])
    b = _sym("B", df, [_setup(2, entry=1.0, stop=0.5, target=5.0, ts=df.index[2])])
    cfg = PortfolioConfig(initial_capital=10_000.0, risk_pct=1.0, max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([a, b], cfg=cfg)

    assert len(res.trades) == 1
    assert res.final_capital == pytest.approx(0.0)
    assert res.metrics["skipped_by_reason"].get("equity<=0") == 1


def test_one_position_per_symbol() -> None:
    df = _target_df(100.0, 110.0, hit_bar=4, n=6)
    setups = [
        _setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0]),
        _setup(2, entry=100.0, stop=90.0, target=110.0, ts=df.index[2]),  # 1-si hali ochiq
    ]
    cfg_on = PortfolioConfig(initial_capital=100_000.0, max_portfolio_risk_pct=1.0,
                             one_position_per_symbol=True)
    cfg_off = PortfolioConfig(initial_capital=100_000.0, max_portfolio_risk_pct=1.0,
                              one_position_per_symbol=False)

    res_on = simulate_portfolio([_sym("X", df, setups)], cfg=cfg_on)
    res_off = simulate_portfolio([_sym("X", df, setups)], cfg=cfg_off)

    assert len(res_on.trades) == 1
    assert res_on.metrics["skipped_by_reason"].get("symbol_already_open") == 1
    assert len(res_off.trades) == 2


def test_same_bar_exit_then_entry_ordering() -> None:
    df = _target_df(100.0, 110.0, hit_bar=2, n=6)
    a = _sym("A", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0])])  # exit idx2
    b = _sym("B", df, [_setup(2, entry=100.0, stop=90.0, target=110.0, ts=df.index[2])])  # entry idx2
    c = _sym("C", df, [_setup(3, entry=100.0, stop=90.0, target=110.0, ts=df.index[3])])
    cfg = PortfolioConfig(initial_capital=100_000.0, max_concurrent_positions=1, max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([a, b, c], cfg=cfg)

    # ENTRY oldin EXIT keyin -> idx2'da B kirolmaydi (A hali ochiq), keyin A yopiladi, idx3'da C kiradi
    assert res.metrics["skipped_by_reason"].get("max_concurrent") == 1  # B
    assert sorted(t.entry_index_pos for t in res.trades) == [0, 3]


def test_atr_risk_model_sizing() -> None:
    rows = [
        {"open": 100, "high": 102, "low": 98, "close": 100},
        {"open": 100, "high": 103, "low": 97, "close": 101},
        {"open": 101, "high": 104, "low": 99, "close": 102},
        {"open": 102, "high": 112, "low": 101, "close": 111},  # idx3 entry + target 110 tegadi
    ]
    df = _make_df(rows)
    setup = _setup(3, entry=102.0, stop=92.0, target=110.0, ts=df.index[3])
    fixed = simulate_portfolio([_sym("X", df, [setup])],
                               cfg=PortfolioConfig(risk_model="fixed_pct", atr_period=3,
                                                   max_portfolio_risk_pct=1.0))
    atr = simulate_portfolio([_sym("X", df, [setup])],
                             cfg=PortfolioConfig(risk_model="atr", atr_period=3,
                                                 max_portfolio_risk_pct=1.0))

    assert len(fixed.trades) == 1 and len(atr.trades) == 1
    assert fixed.trades[0].shares != pytest.approx(atr.trades[0].shares)
    # r_multiple narx-asosli -> ikkalasida bir xil
    assert fixed.trades[0].r_multiple == pytest.approx(atr.trades[0].r_multiple)


def test_trailing_exit_mode() -> None:
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 100, "high": 101, "low": 99, "close": 101},
        {"open": 101, "high": 102, "low": 100, "close": 102},
        {"open": 102, "high": 103, "low": 101, "close": 103},
        {"open": 103, "high": 104, "low": 102, "close": 103},
        {"open": 103, "high": 103.5, "low": 99, "close": 100},
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df.index[0])
    cfg = PortfolioConfig(exit_mode="trailing", trail_atr_mult=1.0, atr_period=3,
                          max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([_sym("X", df, [setup])], cfg=cfg)

    assert res.trades[0].exit_reason == "trailing_stop"
    assert res.trades[0].exit_price == pytest.approx(102.0)


def test_skipped_by_reason_counter() -> None:
    df = _target_df(100.0, 110.0, hit_bar=4, n=6)
    setups = [
        _setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0]),
        _setup(0, entry=100.0, stop=100.0, target=110.0, ts=df.index[0]),  # degenerate
    ]
    other = _sym("Y", df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0])])
    cfg = PortfolioConfig(max_concurrent_positions=1, max_portfolio_risk_pct=1.0)

    res = simulate_portfolio([_sym("X", df, setups), other], cfg=cfg)

    by = res.metrics["skipped_by_reason"]
    assert by.get("degenerate_setup") == 1
    assert by.get("max_concurrent") == 1  # Y (X band qildi)
    assert sum(by.values()) == res.metrics["num_skipped"]


def test_empty_universe_no_crash() -> None:
    res = simulate_portfolio([], cfg=PortfolioConfig(initial_capital=50_000.0))
    assert res.trades == []
    assert res.final_capital == 50_000.0
    assert res.equity_curve == []
    assert res.metrics["num_trades"] == 0


def test_no_signals_flat_curve() -> None:
    df = _make_df(_flat_rows([100, 101, 102, 103, 104]))
    res = simulate_portfolio([_sym("X", df, [])], cfg=PortfolioConfig(initial_capital=100_000.0))
    assert res.metrics["num_trades"] == 0
    assert res.equity_curve == pytest.approx([100_000.0] * 5)
    assert res.metrics["max_drawdown_pct"] == 0.0


def test_old_vs_new_diverge_on_overlapping_trades() -> None:
    """Ustma-ust g'olib savdolar: ESKI ketma-ket kompaund YANGI portfeldan ko'proq oshadi."""
    syms = []
    for i in range(6):
        d = _target_df(100.0, 110.0, hit_bar=3, n=6)
        syms.append(_sym(f"S{i}", d, [_setup(1, entry=100.0, stop=90.0, target=110.0, ts=d.index[1])]))
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.01, max_portfolio_risk_pct=1.0,
                          max_concurrent_positions=10)

    res = simulate_portfolio(syms, cfg=cfg)
    old_curve = portfolio_equity_curve(res.trades, risk_pct=0.01)
    new_multiple = 1.0 + res.metrics["total_return_pct"] / 100.0

    assert len(res.trades) == 6
    # 6 ta bir vaqtda ochilgan savdo: ESKI 6 marta ketma-ket kompaund, YANGI bir marta.
    assert old_curve[-1] > new_multiple


def test_naive_all_signals_curve_ignores_caps() -> None:
    """naive egri chizig'i cap'siz BARCHA signalni kompaundlaydi — cap'li portfeldan yuqori."""
    syms = []
    for i in range(8):
        d = _target_df(100.0, 110.0, hit_bar=3, n=6)
        syms.append(_sym(f"S{i}", d, [_setup(1, entry=100.0, stop=90.0, target=110.0, ts=d.index[1])]))
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.01, max_concurrent_positions=2,
                          max_portfolio_risk_pct=1.0)

    naive = naive_all_signals_curve(syms, cfg=cfg)
    res = run_portfolio(syms, cfg=cfg, benchmark_df=None, benchmark_ticker="X")

    assert len(naive) == 9  # 1.0 + 8 signal
    assert naive[-1] > 1.0
    # cap 2 -> ba'zi signallar o'tkazib yuboriladi -> portfel returni past
    assert res.naive_all_signals_curve == naive
    assert res.metrics["num_skipped"] >= 1
    assert naive[-1] > 1.0 + res.metrics["total_return_pct"] / 100.0


# ======================================================================
# Lookahead — truncation invariance
# ======================================================================


def test_portfolio_no_lookahead_bias() -> None:
    a_df = _target_df(100.0, 110.0, hit_bar=2, n=8)
    b_df = _target_df(50.0, 55.0, hit_bar=4, n=8)
    c_df = _target_df(200.0, 220.0, hit_bar=6, n=8)
    a = _sym("A", a_df, [_setup(0, entry=100.0, stop=90.0, target=110.0, ts=a_df.index[0])])
    b = _sym("B", b_df, [_setup(1, entry=50.0, stop=45.0, target=55.0, ts=b_df.index[1])])
    c = _sym("C", c_df, [_setup(3, entry=200.0, stop=180.0, target=220.0, ts=c_df.index[3])])
    cfg = PortfolioConfig(initial_capital=100_000.0, risk_pct=0.01, max_portfolio_risk_pct=1.0)

    full = simulate_portfolio([a, b, c], cfg=cfg)
    T = a_df.index[4]  # A (exit idx2) va B (exit idx4) T gacha yopiladi; C (exit idx6) yo'q

    def _trunc(sym: SymbolData) -> SymbolData:
        tdf = sym.df[sym.df.index <= T]
        tsig = [s for s in sym.signals if s.entry_ts <= T]
        return SymbolData(symbol=sym.symbol, df=tdf, signals=tsig)

    trunc = simulate_portfolio([_trunc(a), _trunc(b), _trunc(c)], cfg=cfg)

    # To'liq run'da T gacha YOPILGAN har savdo kesilgan run'da AYNAN takrorlanishi kerak.
    # (Teskarisi shart emas: kesish C ni majburan end_of_data bilan erta yopadi.)
    early_full = {t.entry_ts: t for t in full.trades if t.exit_ts <= T}
    trunc_by_entry = {t.entry_ts: t for t in trunc.trades}
    assert len(early_full) == 2  # A (exit idx2), B (exit idx4 == T)
    for k, ft in early_full.items():
        assert k in trunc_by_entry
        tt = trunc_by_entry[k]
        assert ft.exit_ts == tt.exit_ts
        assert ft.entry_price == pytest.approx(tt.entry_price)
        assert ft.exit_price == pytest.approx(tt.exit_price)
        assert ft.shares == pytest.approx(tt.shares)
        assert ft.pnl == pytest.approx(tt.pnl)
        assert ft.r_multiple == pytest.approx(tt.r_multiple)
