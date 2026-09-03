"""scripts/backtest_portfolio.py uchun testlar (real tarmoqsiz — provider monkeypatch)."""

from __future__ import annotations

import argparse

import pandas as pd
import pytest

import scripts.backtest_portfolio as bt_module
from backtest.portfolio import PortfolioResult
from backtest.types import TradeResult
from scripts.backtest_portfolio import (
    build_trade_rows,
    load_benchmark_df,
    load_universe,
    parse_args,
    run,
    summarize,
)

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _make_df(rows: list[dict], *, start: str = "2020-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    if "volume" not in df.columns:
        df["volume"] = 1000
    else:
        df["volume"] = df["volume"].fillna(1000)  # ba'zi rowlarda volume berilgan, qolganiga default
    return df[_COLUMNS]


def _flat_rows(prices: list[float]) -> list[dict]:
    return [{"open": p, "high": p, "low": p, "close": p} for p in prices]


def _breakout_rows() -> list[dict]:
    """lookback=1, volume_ma_period=20 bilan haqiqiy breakout+retest signal beradigan seriya.

    idx 1,3,5: swing high @100 -> RESISTANCE zona (confirmed idx6). idx6..19: baza
    (volume MA to'lishi uchun). idx20: breakout (close 104 > 100, volume 3000).
    idx21: retest (low 100). idx22: bullish tasdiq -> entry.
    """
    rows = [
        {"open": 96, "high": 98, "low": 95, "close": 97},
        {"open": 97, "high": 100, "low": 96, "close": 98},   # 1 swing high
        {"open": 98, "high": 97, "low": 94, "close": 95},
        {"open": 95, "high": 100, "low": 94, "close": 96},   # 3 swing high
        {"open": 96, "high": 97, "low": 93, "close": 94},
        {"open": 94, "high": 100, "low": 93, "close": 95},   # 5 swing high
        {"open": 95, "high": 96, "low": 92, "close": 93},    # 6 zona confirmed
    ]
    rows += [{"open": 95, "high": 98, "low": 93, "close": 96} for _ in range(13)]  # 7..19 baza
    rows += [
        {"open": 96, "high": 105, "low": 95, "close": 104, "volume": 3000},  # 20 breakout
        {"open": 104, "high": 106, "low": 100, "close": 101},                # 21 retest
        {"open": 101, "high": 108, "low": 100.5, "close": 107},              # 22 tasdiq/entry
        {"open": 107, "high": 115, "low": 106, "close": 113},                # 23
        {"open": 113, "high": 125, "low": 112, "close": 122},                # 24
        {"open": 122, "high": 135, "low": 120, "close": 133},                # 25 target ~132 tegadi
        {"open": 133, "high": 138, "low": 130, "close": 135},                # 26
        {"open": 135, "high": 140, "low": 132, "close": 138},                # 27
        {"open": 138, "high": 142, "low": 135, "close": 140},                # 28
        {"open": 140, "high": 145, "low": 138, "close": 143},                # 29
    ]
    return rows


class _FakeProvider:
    def __init__(self, df: pd.DataFrame | None = None, error: Exception | None = None) -> None:
        self._df = df
        self._error = error

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        if self._error is not None:
            raise self._error
        return self._df


def _args(**overrides) -> argparse.Namespace:
    base = dict(
        symbols=["A", "B", "C"], start="2020-01-01", end=None, interval="1d", provider=None,
        commission_pct=0.0, slippage_pct=0.0, min_score=None, max_concurrent=10,
        max_portfolio_risk=1.0, risk_model="fixed_pct", exit_mode="fixed",
        initial_capital=100_000.0, lookback=1, min_rr=1.5, require_trend=False,
        benchmark_ticker="SPUS", output_csv="portfolio_backtest_results.csv",
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ======================================================================
# parse_args
# ======================================================================


def test_parse_args_defaults(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog"])
    args = parse_args()
    assert args.max_concurrent == 10
    assert args.max_portfolio_risk == pytest.approx(0.10)
    assert args.benchmark_ticker == "SPUS"
    assert args.initial_capital == pytest.approx(100_000.0)
    assert args.require_trend is True
    assert args.output_csv == "portfolio_backtest_results.csv"


def test_parse_args_no_require_trend(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--no-require-trend", "--max-concurrent", "3"])
    args = parse_args()
    assert args.require_trend is False
    assert args.max_concurrent == 3


# ======================================================================
# load_universe / load_benchmark_df
# ======================================================================


def test_load_universe_success(monkeypatch) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))

    data, errors = load_universe(
        ["A", "B"], interval="1d", provider_name=None, start="2020-01-01", end=None,
        lookback=1, min_rr=1.5, require_trend=False, min_score=None,
    )
    assert [s.symbol for s in data] == ["A", "B"]
    assert errors == []


def test_load_universe_provider_error_row(monkeypatch) -> None:
    good = _make_df(_breakout_rows())

    def provider(name: str) -> _FakeProvider:
        return _FakeProvider(df=good)

    calls = {"n": 0}

    def flaky(name: str) -> _FakeProvider:
        calls["n"] += 1
        if calls["n"] == 2:
            return _FakeProvider(error=ValueError("kredensial yo'q"))
        return _FakeProvider(df=good)

    monkeypatch.setattr(bt_module, "get_provider", flaky)
    data, errors = load_universe(
        ["A", "B", "C"], interval="1d", provider_name=None, start="2020-01-01", end=None,
        lookback=1, min_rr=1.5, require_trend=False, min_score=None,
    )
    assert len(data) == 2
    assert len(errors) == 1 and errors[0]["ERROR"] == "kredensial yo'q"


def test_load_universe_insufficient_data_row(monkeypatch) -> None:
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=_make_df(_flat_rows([1, 2]))))
    data, errors = load_universe(
        ["A"], interval="1d", provider_name=None, start=None, end=None,
        lookback=5, min_rr=1.5, require_trend=False, min_score=None,
    )
    assert data == []
    assert errors[0]["ERROR"] == "yetarsiz data"


def test_load_benchmark_df_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        bt_module, "get_provider", lambda name: _FakeProvider(error=RuntimeError("yo'q"))
    )
    df, err = load_benchmark_df("SPUS", interval="1d", provider_name=None, start=None, end=None)
    assert df is None and err == "yo'q"


# ======================================================================
# run (end-to-end, tarmoqsiz)
# ======================================================================


def test_run_end_to_end_small(monkeypatch) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))

    result, errors = run(_args())

    assert isinstance(result, PortfolioResult)
    assert errors == []
    for key in ("total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe", "sortino",
                "num_trades", "num_skipped", "skipped_by_reason", "avg_concurrent_positions"):
        assert key in result.metrics
    assert len(result.benchmarks) == 2
    assert result.metrics["num_trades"] >= 1  # breakout seriyasidan kamida bitta savdo


def test_benchmark_ticker_configurable(monkeypatch) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))

    result, _ = run(_args(benchmark_ticker="XYZ"))
    assert result.benchmarks[1].name == "buy_hold:XYZ"
    assert result.benchmarks[1].error is None


def test_benchmark_ticker_missing_no_crash(monkeypatch) -> None:
    good = _make_df(_breakout_rows())

    def provider(name: str):
        return _FakeProvider(df=good)

    call = {"n": 0}

    def flaky(name: str):
        call["n"] += 1
        # oxirgi chaqiruv = benchmark; uni yiqitamiz
        return _FakeProvider(df=good)

    monkeypatch.setattr(bt_module, "get_provider", provider)
    # benchmark ticker'ni universe'da bo'lmagan va yiqiladigan qilib beramiz
    def per_symbol(name: str):
        return _FakeProvider(df=good)

    # load_benchmark_df ni to'g'ridan-to'g'ri yiqitamiz
    monkeypatch.setattr(
        bt_module, "load_benchmark_df",
        lambda ticker, **kw: (None, f"{ticker}: mock xato"),
    )
    result, _ = run(_args(benchmark_ticker="ZZZ"))
    bh = result.benchmarks[1]
    assert bh.equity_curve == []
    assert bh.error is not None


# ======================================================================
# summarize / build_trade_rows
# ======================================================================


def _trade(pnl: float, r: float) -> TradeResult:
    stamp = pd.Timestamp("2020-01-01", tz="UTC")
    return TradeResult(
        entry_ts=stamp, exit_ts=stamp, entry_price=100.0, exit_price=100.0 + r * 10,
        entry_index_pos=0, exit_index_pos=1, shares=1.0, exit_reason="target",
        r_multiple=r, pnl=pnl, hold_duration_days=1.0, mae_r=0.0, mfe_r=r,
    )


def _fake_result() -> PortfolioResult:
    trades = [_trade(500.0, 2.0), _trade(-100.0, -1.0)]
    return PortfolioResult(
        trades=trades, trade_symbols=["A", "B"], skipped=[], timeline=[],
        equity_curve=[100_000.0, 100_400.0], concurrency_samples=[1, 1],
        initial_capital=100_000.0, final_capital=100_400.0,
        metrics={
            "num_trades": 2, "num_skipped": 3, "skipped_by_reason": {"max_concurrent": 3},
            "total_return_pct": 0.4, "cagr_pct": 0.2, "max_drawdown_pct": 1.1,
            "sharpe": 0.5, "sortino": 0.7, "avg_concurrent_positions": 1.0,
            "max_concurrent_positions": 2,
        },
        benchmarks=[],
    )


def test_summarize_side_by_side() -> None:
    result = _fake_result()
    old_curve = [1.0, 1.05, 1.1]  # ~1.1x
    out = summarize(result, old_curve=old_curve)

    assert out["old_final_multiple"] == pytest.approx(1.1)
    assert out["new_return_pct"] == pytest.approx(0.4)
    assert out["new_max_dd_pct"] == pytest.approx(1.1)
    assert out["new_sharpe"] == pytest.approx(0.5)
    assert out["new_sortino"] == pytest.approx(0.7)
    assert out["new_skipped_by_reason"] == {"max_concurrent": 3}
    assert "NEGA FARQ QILADI" in out["explanation"]
    assert "ketma-ket" in out["explanation"].lower()


def test_summarize_no_valid_rows() -> None:
    result = _fake_result()
    out = summarize(result, old_curve=[])
    assert out["old_final_multiple"] == 1.0


def test_build_trade_rows_columns() -> None:
    result = _fake_result()
    df = build_trade_rows(result)
    assert list(df.columns) == [
        "SYMBOL", "ENTRY_TS", "EXIT_TS", "ENTRY_PRICE", "EXIT_PRICE", "SHARES",
        "EXIT_REASON", "R_MULTIPLE", "PNL", "HOLD_DAYS", "MAE_R", "MFE_R",
    ]
    assert len(df) == 2
    assert list(df["SYMBOL"]) == ["A", "B"]


def test_main_writes_csv_no_network(monkeypatch, tmp_path) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=df))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "A", "B", "--start", "2020-01-01", "--lookback", "1", "--no-require-trend"],
    )

    bt_module.main()

    out = tmp_path / "portfolio_backtest_results.csv"
    assert out.exists()
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("SYMBOL,ENTRY_TS,EXIT_TS")


# ======================================================================
# Lookahead — skript darajasi
# ======================================================================


def test_backtest_portfolio_no_lookahead_bias(monkeypatch) -> None:
    full_df = _make_df(_breakout_rows())
    T = full_df.index[27]  # savdo idx25'da (target) yopiladi -> T dan oldin

    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=full_df))
    full_result, _ = run(_args(symbols=["A", "B"]))

    trunc_df = full_df[full_df.index <= T]
    monkeypatch.setattr(bt_module, "get_provider", lambda name: _FakeProvider(df=trunc_df))
    trunc_result, _ = run(_args(symbols=["A", "B"]))

    early_full = {
        (s, t.entry_ts): t
        for s, t in zip(full_result.trade_symbols, full_result.trades)
        if t.exit_ts <= T
    }
    trunc_by = {
        (s, t.entry_ts): t
        for s, t in zip(trunc_result.trade_symbols, trunc_result.trades)
    }
    assert early_full  # kamida bitta erta savdo
    for key, ft in early_full.items():
        assert key in trunc_by
        tt = trunc_by[key]
        assert ft.exit_ts == tt.exit_ts
        assert ft.exit_price == pytest.approx(tt.exit_price)
        assert ft.pnl == pytest.approx(tt.pnl)
        assert ft.r_multiple == pytest.approx(tt.r_multiple)
