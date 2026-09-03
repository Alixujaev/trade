"""scripts/backtest_breakout_retest.py uchun testlar (real tarmoqsiz — provider monkeypatch)."""

from __future__ import annotations

import pandas as pd
import pytest

import scripts.backtest_breakout_retest as bt_module
from backtest.types import TradeResult
from scripts.backtest_breakout_retest import (
    build_results,
    equal_weight_benchmark_block,
    five_years_ago_iso,
    portfolio_equity_curve,
    run_one_symbol,
    summarize,
)

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _make_df(rows: list[dict], *, start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    if "volume" not in df.columns:
        df["volume"] = 1000
    return df[_COLUMNS]


class _FakeProvider:
    def __init__(self, df: pd.DataFrame | None = None, error: Exception | None = None) -> None:
        self._df = df
        self._error = error

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        if self._error is not None:
            raise self._error
        return self._df


def _flat_rows(n: int, price: float = 100.0) -> list[dict]:
    return [{"open": price, "high": price + 1, "low": price - 1, "close": price}] * n


def test_five_years_ago_iso() -> None:
    value = five_years_ago_iso()
    parsed = pd.Timestamp(value)
    delta_days = (pd.Timestamp.today().normalize() - parsed.normalize()).days
    assert 5 * 365 - 3 <= delta_days <= 5 * 365 + 3


def test_run_one_symbol_success(monkeypatch) -> None:
    df = _make_df(_flat_rows(30))
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))

    row = run_one_symbol("SPUS", lookback=1, require_trend=False)

    assert row["ERROR"] is None
    assert row["SYMBOL"] == "SPUS"
    assert row["NEW_TRADES"] == 0  # tekis narx -> signal yo'q
    assert row["NEW_EDGE"] == pytest.approx(row["NEW_RETURN%"] - row["BUY&HOLD%"])
    assert "OLD_TRADES" not in row  # compare_old berilmadi


def test_run_one_symbol_provider_error_row(monkeypatch) -> None:
    monkeypatch.setattr(
        bt_module, "get_provider", lambda name: _FakeProvider(error=ValueError("kredensial yo'q"))
    )

    row = run_one_symbol("SPUS", lookback=1)

    assert row["ERROR"] == "kredensial yo'q"
    assert row["BARS"] is None
    assert row["SYMBOL"] == "SPUS"


def test_compare_old_populates_old_columns(monkeypatch) -> None:
    df = _make_df(_flat_rows(30))
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))

    row = run_one_symbol("SPUS", lookback=1, require_trend=False, compare_old=True)

    for key in ("OLD_TRADES", "OLD_WIN%", "OLD_EXP", "OLD_RETURN%", "OLD_EDGE"):
        assert key in row


def test_window_applied_before_signal_generation(monkeypatch) -> None:
    """--start berilganda BUY&HOLD% to'liq oynadagidan farq qilishi kerak (oyna
    XOM datada, signal generatsiyadan OLDIN qo'llanadi)."""
    rising = [{"open": p, "high": p + 1, "low": p - 1, "close": p} for p in range(100, 140)]
    df = _make_df(rising)
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))

    full = run_one_symbol("X", lookback=1, require_trend=False, start=None)
    windowed = run_one_symbol("X", lookback=1, require_trend=False, start="2024-02-01")

    assert full["BARS"] > windowed["BARS"]
    assert full["BUY&HOLD%"] != windowed["BUY&HOLD%"]


def test_build_results_continues_after_one_symbol_fails(monkeypatch) -> None:
    def fake_get_provider(name: str) -> _FakeProvider:
        return _FakeProvider(df=_make_df(_flat_rows(30)))

    monkeypatch.setattr(bt_module, "get_provider", fake_get_provider)

    real_run_one = bt_module.run_one_symbol

    def flaky_run_one(symbol, **kw):
        if symbol == "BAD":
            raise RuntimeError("bu chaqiruv qatorga aylantirilishi kerak emas edi")
        return real_run_one(symbol, **kw)

    # build_results ichidagi har chaqiruv o'zi try/except bilan o'ralgan (run_one_symbol);
    # bu yerda esa provider xatosini simulyatsiya qilamiz.
    monkeypatch.setattr(
        bt_module,
        "get_provider",
        lambda name: _FakeProvider(df=_make_df(_flat_rows(30))),
    )

    results = build_results(["GOOD", "GOOD2"], lookback=1, require_trend=False)
    assert len(results) == 2
    assert results["ERROR"].isna().all()

    # endi bitta symbol provider darajasida yiqiladi
    calls = {"n": 0}

    def sometimes_broken(name: str) -> _FakeProvider:
        calls["n"] += 1
        if calls["n"] == 2:
            return _FakeProvider(error=RuntimeError("tarmoq"))
        return _FakeProvider(df=_make_df(_flat_rows(30)))

    monkeypatch.setattr(bt_module, "get_provider", sometimes_broken)
    results2 = build_results(["A", "B", "C"], lookback=1, require_trend=False)
    assert len(results2) == 3
    assert results2["ERROR"].notna().sum() == 1
    assert results2["ERROR"].isna().sum() == 2


def test_summarize_math() -> None:
    df = pd.DataFrame(
        [
            {"SYMBOL": "A", "NEW_TRADES": 4, "NEW_RETURN%": 10.0, "NEW_EXP": 0.2, "NEW_WIN%": 50.0,
             "NEW_MAXDD%": 5.0, "NEW_EDGE": 2.0, "BUY&HOLD%": 8.0, "OLD_TRADES": 3, "OLD_RETURN%": 6.0,
             "OLD_EXP": 0.1, "OLD_EDGE": -2.0, "ERROR": None},
            {"SYMBOL": "B", "NEW_TRADES": 2, "NEW_RETURN%": 20.0, "NEW_EXP": 0.4, "NEW_WIN%": 60.0,
             "NEW_MAXDD%": 7.0, "NEW_EDGE": 4.0, "BUY&HOLD%": 16.0, "OLD_TRADES": 1, "OLD_RETURN%": 2.0,
             "OLD_EXP": 0.0, "OLD_EDGE": -14.0, "ERROR": None},
            {"SYMBOL": "C", "ERROR": "boom"},
        ]
    )

    out = summarize(df)

    assert out["symbols"] == 2  # xato qator hisobga olinmaydi
    assert out["new_trades_total"] == 6
    assert out["new_edge_mean"] == pytest.approx(3.0)
    assert out["old_edge_mean"] == pytest.approx(-8.0)
    assert "buy&hold'ni yengdimi" in out["verdict"].lower()
    assert "eski smc" in out["verdict"].lower()


def test_summarize_no_valid_rows() -> None:
    df = pd.DataFrame([{"SYMBOL": "A", "ERROR": "x"}])
    out = summarize(df)
    assert out["symbols"] == 0
    assert "verdict" in out


def _trade(ts: str, r_multiple: float) -> TradeResult:
    stamp = pd.Timestamp(ts, tz="UTC")
    return TradeResult(
        entry_ts=stamp, exit_ts=stamp, entry_price=100.0, exit_price=100.0,
        entry_index_pos=0, exit_index_pos=1, shares=1.0, exit_reason="target",
        r_multiple=r_multiple, pnl=0.0, hold_duration_days=1.0, mae_r=0.0, mfe_r=0.0,
    )


def test_portfolio_equity_curve_math() -> None:
    trades = [_trade("2024-03-01", 2.0), _trade("2024-01-01", -1.0), _trade("2024-02-01", 1.0)]
    curve = portfolio_equity_curve(trades, risk_pct=0.01)

    # entry_ts bo'yicha saralanadi: -1.0, +1.0, +2.0
    # 1.0 -> *0.99 -> *1.01 -> *1.02
    assert curve[0] == pytest.approx(1.0)
    assert curve[1] == pytest.approx(0.99)
    assert curve[2] == pytest.approx(0.99 * 1.01)
    assert curve[3] == pytest.approx(0.99 * 1.01 * 1.02)


def test_portfolio_equity_curve_empty() -> None:
    assert portfolio_equity_curve([]) == [1.0]


def test_equal_weight_benchmark_block_math() -> None:
    a = _make_df([{"open": p, "high": p, "low": p, "close": p} for p in [100, 110, 120, 130]])
    b = _make_df([{"open": p, "high": p, "low": p, "close": p} for p in [50, 55, 60, 66]])
    spus = _make_df([{"open": p, "high": p, "low": p, "close": p} for p in [10, 11, 12, 13]])

    block = equal_weight_benchmark_block(
        [("A", a), ("B", b)], spus, interval="1d", commission_pct=0.0, slippage_pct=0.0,
    )
    assert list(block.columns) == ["benchmark", "total_return%", "cagr%", "max_dd%", "sharpe", "sortino"]
    assert list(block["benchmark"]) == ["equal_weight_buy_hold", "buy_hold:SPUS"]
    # teng-vazn: A +30%, B +32% -> o'rtacha ~ +31%
    ew = block.iloc[0]
    assert 30.0 <= ew["total_return%"] <= 32.0
    # SPUS: 10 -> 13 = +30%
    assert block.iloc[1]["total_return%"] == pytest.approx(30.0, abs=0.1)


def test_equal_weight_benchmark_block_empty() -> None:
    block = equal_weight_benchmark_block([], None, interval="1d", commission_pct=0.0, slippage_pct=0.0)
    assert block.empty
