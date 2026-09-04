"""scripts/exit_research.py uchun testlar (real tarmoqsiz — provider monkeypatch)."""

from __future__ import annotations

import argparse
import json

import pandas as pd
import pytest

import scripts.exit_research as er_module
from backtest.portfolio import PortfolioResult
from backtest.types import TradeResult
from scripts.exit_research import (
    best_exit,
    build_csv_rows,
    build_result_table,
    compute_verdicts,
    load_universe_frozen,
    run_all_models,
    run_windows_all_models,
    verdict_for_model,
    write_experiment,
)

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _make_df(rows: list[dict], *, start: str = "2020-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    if "volume" not in df.columns:
        df["volume"] = 1000
    else:
        df["volume"] = df["volume"].fillna(1000)
    return df[_COLUMNS]


def _breakout_rows() -> list[dict]:
    """lookback=1, volume_ma_period=20 bilan haqiqiy breakout+retest signal beradigan seriya
    (tests/test_backtest_portfolio.py::_breakout_rows bilan bir xil ssenariy)."""
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
        symbols=["A", "B"], start="2020-01-01", end=None, oos_start=None, interval="1d",
        provider=None, min_score=None, max_concurrent=10, max_portfolio_risk=1.0,
        commission_pct=0.0, slippage_pct=0.0, exits="A,B,C,D,E,F", output_csv=None,
        min_oos_trades=1, meaningful_margin=0.15, benchmark_ticker="SPUS",
        initial_capital=100_000.0, lookback=1, min_rr=1.5, require_trend=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ======================================================================
# Entry freeze
# ======================================================================


def test_entry_generation_runs_exactly_once(monkeypatch) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df))

    calls = {"n": 0}
    import strategy.breakout_retest as br_module

    original = br_module.generate_breakout_retest_signals

    def counted(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(br_module, "generate_breakout_retest_signals", counted)
    monkeypatch.setattr(
        "backtest.portfolio.generate_breakout_retest_signals", counted
    )

    symbols, _errors = load_universe_frozen(_args(), start="2020-01-01", end=None)
    all_results = run_all_models(
        symbols, model_keys=["A", "B", "C", "D", "E", "F"],
        cfg_base=er_module.PortfolioConfig(max_portfolio_risk_pct=1.0),
        benchmark_df=None, benchmark_ticker="SPUS",
    )

    assert len(all_results) == 6
    # 2 symbol -> load_universe_frozen 2 marta chaqiradi (har symbol uchun 1) -- 6 model UCHUN QAYTA EMAS.
    assert calls["n"] == 2


# ======================================================================
# Barcha exit modellari bir xil entry setni oladi
# ======================================================================


def test_all_exit_models_receive_identical_entry_set(monkeypatch) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df))

    symbols, _errors = load_universe_frozen(_args(), start="2020-01-01", end=None)
    all_results = run_all_models(
        symbols, model_keys=["A", "B", "C", "D", "E", "F"],
        cfg_base=er_module.PortfolioConfig(max_portfolio_risk_pct=1.0),
        benchmark_df=None, benchmark_ticker="SPUS",
    )

    entry_sets = {}
    for key, result in all_results.items():
        cands = set()
        for sym in symbols:
            for setup in sym.signals:
                cands.add((sym.symbol, setup.entry_ts, round(setup.entry_price, 6)))
        entry_sets[key] = cands

    first = next(iter(entry_sets.values()))
    for key, s in entry_sets.items():
        assert s == first, f"model {key} entry set differs"


# ======================================================================
# No-lookahead (end-to-end)
# ======================================================================


def test_exit_research_no_lookahead(monkeypatch) -> None:
    rows = _breakout_rows()
    df_full = _make_df(rows)
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df_full))

    cfg_base = er_module.PortfolioConfig(max_portfolio_risk_pct=1.0)
    symbols_full, _ = load_universe_frozen(_args(), start="2020-01-01", end=None)
    full_results = run_all_models(
        symbols_full, model_keys=["A", "B", "C", "D", "E", "F"], cfg_base=cfg_base,
        benchmark_df=None, benchmark_ticker="SPUS",
    )

    # Kesilgan run: oxirgi 3 bar olib tashlangan.
    df_trunc = df_full.iloc[:-3]
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df_trunc))
    symbols_trunc, _ = load_universe_frozen(_args(), start="2020-01-01", end=None)
    trunc_results = run_all_models(
        symbols_trunc, model_keys=["A", "B", "C", "D", "E", "F"], cfg_base=cfg_base,
        benchmark_df=None, benchmark_ticker="SPUS",
    )

    # Har ikkala run'da HAM yopilgan (kesish nuqtasidan oldin exit_ts bo'lgan) savdolar bir xil
    # bo'lishi kerak -- kelajak barlar ta'sir qilmasligi kerak.
    cutoff = df_trunc.index[-1]
    for key in full_results:
        full_trades = {
            (t.entry_ts, t.leg): t for t in full_results[key].trades if t.exit_ts <= cutoff
        }
        trunc_trades = {(t.entry_ts, t.leg): t for t in trunc_results[key].trades}
        for k, ft in full_trades.items():
            assert k in trunc_trades, f"model {key} missing trade {k} after truncation"
            tt = trunc_trades[k]
            assert ft.exit_price == pytest.approx(tt.exit_price)
            assert ft.exit_reason == tt.exit_reason


# ======================================================================
# Verdict engine
# ======================================================================


def test_verdict_inconclusive_low_sample() -> None:
    v = verdict_for_model(
        oos_trade_count=5, oos_sharpe=2.0, constrained_bh_oos_sharpe=0.5,
        min_oos_trades=30, meaningful_margin=0.15,
    )
    assert v == "INCONCLUSIVE (low sample)"


def test_verdict_alpha_requires_margin() -> None:
    kw = dict(oos_trade_count=50, constrained_bh_oos_sharpe=1.0, min_oos_trades=30, meaningful_margin=0.15)
    assert verdict_for_model(oos_sharpe=1.2, **kw) == "ALPHA: exit value qo'shdi"  # delta=0.2>=0.15
    assert verdict_for_model(oos_sharpe=1.1, **kw) == "INCONCLUSIVE"  # delta=0.1<0.15
    assert verdict_for_model(oos_sharpe=1.0, **kw) == "NO EDGE"  # delta=0
    assert verdict_for_model(oos_sharpe=0.9, **kw) == "NO EDGE"  # delta<0


def test_verdict_higher_return_lower_sharpe_is_no_edge() -> None:
    # Spec's own example: return yuqori bo'lsa ham, Sharpe past -> NO EDGE.
    v = verdict_for_model(
        oos_trade_count=50, oos_sharpe=0.80, constrained_bh_oos_sharpe=0.95,
        min_oos_trades=30, meaningful_margin=0.15,
    )
    assert v == "NO EDGE"


def test_best_exit_none_when_no_alpha() -> None:
    verdicts = {"A": "NO EDGE", "B": "INCONCLUSIVE", "C": "NO EDGE"}
    sharpes = {"A": 0.5, "B": 0.6, "C": 0.4}
    key, msg = best_exit(verdicts, sharpes)
    assert key is None
    assert msg == "NO EXIT EDGE FOUND"


def test_best_exit_picks_max_sharpe_among_alpha() -> None:
    verdicts = {"A": "ALPHA: exit value qo'shdi", "B": "NO EDGE", "C": "ALPHA: exit value qo'shdi"}
    sharpes = {"A": 0.9, "B": 2.0, "C": 1.2}
    key, msg = best_exit(verdicts, sharpes)
    assert key == "C"
    assert msg.startswith("ALPHA")


# ======================================================================
# JSON experiment logging
# ======================================================================


def test_json_experiment_schema_fields(tmp_path) -> None:
    path = write_experiment(
        model_key="A", universe=["AAPL", "MSFT"], start="2020-01-01", end="2026-01-01",
        oos_start="2023-01-01", interval="1d", commission_pct=0.0, slippage_pct=0.0005,
        train_metrics={"sharpe": 1.0}, oos_metrics={"sharpe": 0.5},
        benchmarks={"equal_weight_buy_hold": {"sharpe": 0.3}}, skip_breakdown={"max_concurrent": 2},
        verdict="NO EDGE", experiments_dir=tmp_path,
    )
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "exit_model", "params", "universe", "period", "oos_start", "interval", "costs",
        "train_metrics", "oos_metrics", "benchmarks", "skip_breakdown", "verdict",
        "git_commit", "timestamp",
    ):
        assert key in payload
    assert payload["exit_model"] == "fixed_sl_tp"
    assert payload["universe"] == ["AAPL", "MSFT"]
    assert payload["period"] == {"start": "2020-01-01", "end": "2026-01-01"}
    assert payload["verdict"] == "NO EDGE"


def test_json_experiment_never_overwrites(tmp_path) -> None:
    kwargs = dict(
        model_key="B", universe=["AAPL"], start="2020-01-01", end=None, oos_start="2023-01-01",
        interval="1d", commission_pct=0.0, slippage_pct=0.0005, train_metrics={}, oos_metrics={},
        benchmarks={}, skip_breakdown={}, verdict="NO EDGE", experiments_dir=tmp_path,
    )
    p1 = write_experiment(**kwargs)
    p2 = write_experiment(**kwargs)
    assert p1 != p2
    assert p1.exists() and p2.exists()


# ======================================================================
# CSV export
# ======================================================================


def _fake_portfolio_result(*, sharpe: float, num_trades: int) -> PortfolioResult:
    trades = [
        TradeResult(
            entry_ts=pd.Timestamp("2020-01-01", tz="UTC"), exit_ts=pd.Timestamp("2020-01-02", tz="UTC"),
            entry_price=100.0, exit_price=101.0, entry_index_pos=0, exit_index_pos=1, shares=1.0,
            exit_reason="target", r_multiple=1.0, pnl=1.0, hold_duration_days=1.0, mae_r=0.0, mfe_r=1.0,
        )
        for _ in range(num_trades)
    ]
    metrics = {
        "num_trades": num_trades, "win_rate": 1.0, "avg_r_multiple": 1.0, "expectancy_r": 1.0,
        "profit_factor": 2.0, "avg_hold_days": 1.0, "total_return_pct": 5.0, "cagr_pct": 10.0,
        "max_drawdown_pct": -2.0, "sharpe": sharpe, "sortino": sharpe, "num_skipped": 0,
        "skipped_by_reason": {}, "avg_concurrent_positions": 1.0, "max_concurrent_positions": 1,
    }
    return PortfolioResult(
        trades=trades, trade_symbols=["A"] * num_trades, skipped=[], timeline=[], equity_curve=[],
        concurrency_samples=[], initial_capital=100_000.0, final_capital=105_000.0, metrics=metrics,
        benchmarks=[],
    )


def test_csv_export_one_row_per_split_and_model() -> None:
    all_results = {
        "TRAIN": {"A": _fake_portfolio_result(sharpe=1.0, num_trades=3), "B": _fake_portfolio_result(sharpe=1.2, num_trades=4)},
        "OOS": {"A": _fake_portfolio_result(sharpe=0.5, num_trades=2), "B": _fake_portfolio_result(sharpe=0.8, num_trades=5)},
    }
    verdicts = {"A": "NO EDGE", "B": "ALPHA: exit value qo'shdi"}

    df = build_csv_rows(all_results, verdicts=verdicts)

    assert len(df) == 4
    assert set(zip(df["split"], df["model"])) == {
        ("TRAIN", "fixed_sl_tp"), ("TRAIN", "atr_sl_tp"), ("OOS", "fixed_sl_tp"), ("OOS", "atr_sl_tp"),
    }
    oos_b = df[(df["split"] == "OOS") & (df["model"] == "atr_sl_tp")].iloc[0]
    assert oos_b["verdict"] == "ALPHA: exit value qo'shdi"
    train_a = df[(df["split"] == "TRAIN") & (df["model"] == "fixed_sl_tp")].iloc[0]
    assert train_a["verdict"] == "-"  # TRAIN split'da verdict yo'q
