"""scripts/exit_research.py uchun testlar (real tarmoqsiz — provider monkeypatch)."""

from __future__ import annotations

import argparse
import json

import pandas as pd
import pytest

import scripts.exit_research as er_module
from backtest.portfolio import BenchmarkResult, PortfolioResult
from backtest.types import TradeResult
from scripts.exit_research import (
    best_exit,
    build_csv_rows,
    build_result_table,
    compute_level1_verdict,
    compute_level2_verdicts,
    load_universe_frozen,
    run_all_models,
    run_windows_all_models,
    verdict_for_model,
    verdict_for_selection,
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
        symbols, model_keys=["A", "B", "C", "D", "E", "F", "NOEXIT"],
        cfg_base=er_module.PortfolioConfig(max_portfolio_risk_pct=1.0),
        benchmark_df=None, benchmark_ticker="SPUS",
    )

    assert len(all_results) == 7
    # 2 symbol -> load_universe_frozen 2 marta chaqiradi (har symbol uchun 1) -- 7 model UCHUN QAYTA EMAS.
    assert calls["n"] == 2


# ======================================================================
# Barcha exit modellari bir xil entry setni oladi
# ======================================================================


def test_all_exit_models_receive_identical_entry_set(monkeypatch) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df))

    symbols, _errors = load_universe_frozen(_args(), start="2020-01-01", end=None)
    all_results = run_all_models(
        symbols, model_keys=["A", "B", "C", "D", "E", "F", "NOEXIT"],
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


# ======================================================================
# LEVEL 2 (Exit): verdict_for_model / compute_level2_verdicts
# ======================================================================


def test_verdict_for_model_inconclusive_low_sample() -> None:
    v = verdict_for_model(
        oos_trade_count=5, oos_sharpe=2.0, baseline_oos_sharpe=0.5,
        min_oos_trades=30, meaningful_margin=0.15,
    )
    assert v == "INCONCLUSIVE (low sample)"


def test_verdict_for_model_requires_margin() -> None:
    kw = dict(oos_trade_count=50, baseline_oos_sharpe=1.0, min_oos_trades=30, meaningful_margin=0.15)
    assert verdict_for_model(oos_sharpe=1.2, **kw) == "EXIT IMPROVEMENT"  # delta=0.2>=0.15
    assert verdict_for_model(oos_sharpe=1.1, **kw) == "INCONCLUSIVE"  # delta=0.1<0.15
    assert verdict_for_model(oos_sharpe=1.0, **kw) == "NO EDGE"  # delta=0
    assert verdict_for_model(oos_sharpe=0.9, **kw) == "NO EDGE"  # delta<0


def test_verdict_for_model_higher_return_lower_sharpe_is_no_edge() -> None:
    # Spec's own example: return yuqori bo'lsa ham, Sharpe past -> NO EDGE.
    v = verdict_for_model(
        oos_trade_count=50, oos_sharpe=0.80, baseline_oos_sharpe=0.95,
        min_oos_trades=30, meaningful_margin=0.15,
    )
    assert v == "NO EDGE"


def test_compute_level2_verdicts_uses_no_exit_capped_baseline_not_constrained_bh() -> None:
    # Constrained BH Sharpe=0.5 (past); NoExit-capped Sharpe=1.0 (yuqori). Candidate "A" Sharpe=1.1.
    # Constrained BH'ga nisbatan delta=0.6 -> EXIT IMPROVEMENT bo'lardi; NoExit-capped'ga
    # nisbatan delta=0.1 -> INCONCLUSIVE. compute_level2_verdicts NoExit-capped'ni ishlatishi
    # kerak -- natija INCONCLUSIVE bo'lishi shart.
    constrained_bh = _fake_benchmark("capital_constrained_buy_hold", sharpe=0.5)
    oos_results = {
        "NOEXIT": _fake_portfolio_result(sharpe=1.0, num_trades=50, benchmarks=[constrained_bh]),
        "A": _fake_portfolio_result(sharpe=1.1, num_trades=50, benchmarks=[constrained_bh]),
    }
    verdicts = compute_level2_verdicts(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert verdicts["A"] == "INCONCLUSIVE"


def test_compute_level2_verdicts_no_verdict_for_no_exit_itself() -> None:
    oos_results = {
        "NOEXIT": _fake_portfolio_result(sharpe=1.0, num_trades=50),
        "A": _fake_portfolio_result(sharpe=0.5, num_trades=50),
    }
    verdicts = compute_level2_verdicts(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert "NOEXIT" not in verdicts
    assert "A" in verdicts


def test_compute_level2_verdicts_empty_when_no_exit_missing() -> None:
    oos_results = {"A": _fake_portfolio_result(sharpe=0.5, num_trades=50)}
    assert compute_level2_verdicts(oos_results, min_oos_trades=30, meaningful_margin=0.15) == {}


def test_compute_level2_verdicts_baseline_low_sample_overrides_individual() -> None:
    # NoExit-capped trade_count=6 (< min_oos_trades=30) -- doim band bo'lgan slot(lar) tufayli
    # kutilgan holat. "A" o'zining 50 savdosi va katta Sharpe delta'siga qaramay, verdict
    # BASELINE'ning O'ZI shovqinli bo'lgani uchun "INCONCLUSIVE (baseline low sample)" bo'lishi
    # kerak -- bu shu vazifaning asosiy regressiya testi (avvalgi xatoni tuzatadi).
    oos_results = {
        "NOEXIT": _fake_portfolio_result(sharpe=1.044, num_trades=6),
        "A": _fake_portfolio_result(sharpe=2.0, num_trades=50),  # delta=0.956 -- odatda EXIT IMPROVEMENT
    }
    verdicts = compute_level2_verdicts(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert verdicts["A"] == "INCONCLUSIVE (baseline low sample)"


def test_compute_level2_verdicts_normal_when_baseline_has_enough_trades() -> None:
    oos_results = {
        "NOEXIT": _fake_portfolio_result(sharpe=1.0, num_trades=40),
        "A": _fake_portfolio_result(sharpe=1.2, num_trades=40),  # delta=0.2 >= 0.15
        "B": _fake_portfolio_result(sharpe=1.0, num_trades=40),  # delta=0.0 -> NO EDGE
    }
    verdicts = compute_level2_verdicts(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert verdicts["A"] == "EXIT IMPROVEMENT"
    assert verdicts["B"] == "NO EDGE"


def test_best_exit_none_when_no_alpha() -> None:
    verdicts = {"A": "NO EDGE", "B": "INCONCLUSIVE", "C": "NO EDGE"}
    sharpes = {"A": 0.5, "B": 0.6, "C": 0.4}
    key, msg = best_exit(verdicts, sharpes)
    assert key is None
    assert msg == "NO EXIT EDGE FOUND"


def test_best_exit_picks_max_sharpe_among_exit_improvement() -> None:
    verdicts = {"A": "EXIT IMPROVEMENT", "B": "NO EDGE", "C": "EXIT IMPROVEMENT"}
    sharpes = {"A": 0.9, "B": 2.0, "C": 1.2}
    key, msg = best_exit(verdicts, sharpes)
    assert key == "C"
    assert msg.startswith("EXIT IMPROVEMENT")


# ======================================================================
# LEVEL 1 (Selection): verdict_for_selection / compute_level1_verdict
# ======================================================================


def test_verdict_for_selection_requires_margin() -> None:
    kw = dict(oos_trade_count=100, equal_weight_oos_sharpe=1.0, min_oos_trades=30, meaningful_margin=0.15)
    assert verdict_for_selection(selection_oos_sharpe=1.2, **kw) == "SELECTION EDGE"  # delta=0.2>=0.15
    assert verdict_for_selection(selection_oos_sharpe=1.1, **kw) == "INCONCLUSIVE"  # delta=0.1<0.15
    assert verdict_for_selection(selection_oos_sharpe=1.0, **kw) == "NO SELECTION EDGE"  # delta=0
    assert verdict_for_selection(selection_oos_sharpe=0.5, **kw) == "NO SELECTION EDGE"  # delta<0


def test_verdict_for_selection_low_sample() -> None:
    v = verdict_for_selection(
        oos_trade_count=5, selection_oos_sharpe=2.0, equal_weight_oos_sharpe=0.5,
        min_oos_trades=30, meaningful_margin=0.15,
    )
    assert v == "INCONCLUSIVE (low sample)"


def test_compute_level1_verdict_selection_edge() -> None:
    benches = [
        _fake_benchmark("equal_weight_buy_hold", sharpe=0.5),
        _fake_benchmark_with_trade_count("selection_bh", sharpe=0.8, trade_count=100),
    ]
    oos_results = {"NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=6, benchmarks=benches)}
    v = compute_level1_verdict(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert v == "SELECTION EDGE"


def test_compute_level1_verdict_no_selection_edge() -> None:
    benches = [
        _fake_benchmark("equal_weight_buy_hold", sharpe=0.8),
        _fake_benchmark_with_trade_count("selection_bh", sharpe=0.5, trade_count=100),
    ]
    oos_results = {"NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=6, benchmarks=benches)}
    v = compute_level1_verdict(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert v == "NO SELECTION EDGE"


def test_compute_level1_verdict_inconclusive_margin() -> None:
    benches = [
        _fake_benchmark("equal_weight_buy_hold", sharpe=0.5),
        _fake_benchmark_with_trade_count("selection_bh", sharpe=0.6, trade_count=100),
    ]
    oos_results = {"NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=6, benchmarks=benches)}
    v = compute_level1_verdict(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert v == "INCONCLUSIVE"


def test_compute_level1_verdict_inconclusive_low_sample() -> None:
    # Selection-BH o'zi 5 candidate'dan iborat -- juda kam, hatto katta delta bilan ham low-sample.
    benches = [
        _fake_benchmark("equal_weight_buy_hold", sharpe=0.5),
        _fake_benchmark_with_trade_count("selection_bh", sharpe=2.0, trade_count=5),
    ]
    oos_results = {"NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=6, benchmarks=benches)}
    v = compute_level1_verdict(oos_results, min_oos_trades=30, meaningful_margin=0.15)
    assert v == "INCONCLUSIVE (low sample)"


def test_compute_level1_verdict_empty_when_no_results() -> None:
    assert compute_level1_verdict({}, min_oos_trades=30, meaningful_margin=0.15) == "INCONCLUSIVE (low sample)"


# ======================================================================
# JSON experiment logging
# ======================================================================


def test_json_experiment_includes_noexit_capped_and_selection_bh_metrics(tmp_path) -> None:
    path = write_experiment(
        model_key="A", universe=["AAPL"], start="2020-01-01", end="2026-01-01",
        oos_start="2023-01-01", interval="1d", commission_pct=0.0, slippage_pct=0.0005,
        train_metrics={"sharpe": 1.0}, oos_metrics={"sharpe": 0.5},
        benchmarks={
            "equal_weight_buy_hold": {"sharpe": 0.3},
            "selection_bh": {"sharpe": 0.6, "trade_count": 120},
            "capital_constrained_buy_hold": {"sharpe": 0.4},
            "no_exit_capped": {"sharpe": 0.45, "total_return_pct": 12.0, "trade_count": 40},
        },
        skip_breakdown={"max_concurrent": 2}, verdict="NO EDGE",
        selection_verdict="SELECTION EDGE", experiments_dir=tmp_path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["verdict_baseline"] == {"selection": "equal_weight_bh", "exit": "no_exit_capped"}
    assert payload["selection_verdict"] == "SELECTION EDGE"
    assert "no_exit_capped" in payload["benchmarks"]
    assert payload["benchmarks"]["no_exit_capped"]["sharpe"] == pytest.approx(0.45)
    assert payload["benchmarks"]["no_exit_capped"]["trade_count"] == 40
    assert payload["benchmarks"]["selection_bh"]["trade_count"] == 120


def test_json_experiment_schema_fields(tmp_path) -> None:
    path = write_experiment(
        model_key="A", universe=["AAPL", "MSFT"], start="2020-01-01", end="2026-01-01",
        oos_start="2023-01-01", interval="1d", commission_pct=0.0, slippage_pct=0.0005,
        train_metrics={"sharpe": 1.0}, oos_metrics={"sharpe": 0.5},
        benchmarks={"equal_weight_buy_hold": {"sharpe": 0.3}}, skip_breakdown={"max_concurrent": 2},
        verdict="NO EDGE", selection_verdict="NO SELECTION EDGE", experiments_dir=tmp_path,
    )
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "exit_model", "params", "universe", "period", "oos_start", "interval", "costs",
        "train_metrics", "oos_metrics", "benchmarks", "skip_breakdown", "verdict",
        "selection_verdict", "verdict_baseline", "git_commit", "timestamp",
    ):
        assert key in payload
    assert payload["verdict_baseline"] == {"selection": "equal_weight_bh", "exit": "no_exit_capped"}
    assert payload["selection_verdict"] == "NO SELECTION EDGE"
    assert payload["exit_model"] == "fixed_sl_tp"
    assert payload["universe"] == ["AAPL", "MSFT"]
    assert payload["period"] == {"start": "2020-01-01", "end": "2026-01-01"}
    assert payload["verdict"] == "NO EDGE"


def test_json_experiment_never_overwrites(tmp_path) -> None:
    kwargs = dict(
        model_key="B", universe=["AAPL"], start="2020-01-01", end=None, oos_start="2023-01-01",
        interval="1d", commission_pct=0.0, slippage_pct=0.0005, train_metrics={}, oos_metrics={},
        benchmarks={}, skip_breakdown={}, verdict="NO EDGE", selection_verdict="INCONCLUSIVE",
        experiments_dir=tmp_path,
    )
    p1 = write_experiment(**kwargs)
    p2 = write_experiment(**kwargs)
    assert p1 != p2
    assert p1.exists() and p2.exists()


# ======================================================================
# Result table
# ======================================================================


def test_build_result_table_row_order_and_control_label() -> None:
    benches = [
        _fake_benchmark("equal_weight_buy_hold", sharpe=0.8),
        _fake_benchmark_with_trade_count("selection_bh", sharpe=0.6, trade_count=120),
        _fake_benchmark("capital_constrained_buy_hold", sharpe=0.5),
    ]
    model_results = {
        "A": _fake_portfolio_result(sharpe=1.0, num_trades=10, benchmarks=benches),
        "NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=10, benchmarks=benches),
        "B": _fake_portfolio_result(sharpe=0.7, num_trades=10, benchmarks=benches),
    }
    verdicts = {"A": "EXIT IMPROVEMENT", "B": "NO EDGE"}

    table = build_result_table(model_results, verdicts=verdicts)

    labels = list(table["Model"])
    assert labels[0] == "Equal-weight BH"
    assert labels[1] == "Selection-BH"
    assert labels[2] == "Constrained BH"
    assert labels[3] == "NoExit-capped (control)"
    assert labels[4:] == [
        f"A ({er_module._EXIT_MODEL_NAMES['A']})", f"B ({er_module._EXIT_MODEL_NAMES['B']})",
    ]

    noexit_row = table[table["Model"] == "NoExit-capped (control)"].iloc[0]
    assert noexit_row["Verdict"] == "CONTROL"

    a_row = table[table["Model"].str.startswith("A (")].iloc[0]
    assert a_row["Verdict"] == "EXIT IMPROVEMENT"

    constrained_row = table[table["Model"] == "Constrained BH"].iloc[0]
    assert constrained_row["Verdict"] == "-"

    selection_row = table[table["Model"] == "Selection-BH"].iloc[0]
    assert selection_row["Verdict"] == "-"
    assert selection_row["Trades"] == 120


def test_build_result_table_no_exit_control_regardless_of_verdicts_dict() -> None:
    # Hatto agar `verdicts` dict'ida "NOEXIT" kaliti bo'lsa ham (bo'lmasligi kerak, lekin
    # himoya sifatida), jadval qatori har doim "CONTROL" ko'rsatishi kerak.
    model_results = {"NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=10)}
    table = build_result_table(model_results, verdicts={"NOEXIT": "EXIT IMPROVEMENT"})
    assert table[table["Model"] == "NoExit-capped (control)"].iloc[0]["Verdict"] == "CONTROL"


# ======================================================================
# CSV export
# ======================================================================


def _fake_portfolio_result(
    *, sharpe: float, num_trades: int, benchmarks: list[BenchmarkResult] | None = None
) -> PortfolioResult:
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
        benchmarks=benchmarks if benchmarks is not None else [],
    )


def _fake_benchmark(name: str, *, sharpe: float) -> BenchmarkResult:
    return BenchmarkResult(
        name=name, equity_curve=[], metrics={
            "return_pct": 5.0, "cagr_pct": 10.0, "max_drawdown_pct": -2.0, "sharpe": sharpe, "sortino": sharpe,
        },
    )


def _fake_benchmark_with_trade_count(name: str, *, sharpe: float, trade_count: int) -> BenchmarkResult:
    b = _fake_benchmark(name, sharpe=sharpe)
    return BenchmarkResult(name=b.name, equity_curve=b.equity_curve, metrics={**b.metrics, "trade_count": trade_count})


def test_csv_export_one_row_per_split_and_model() -> None:
    # benchmarks=[] -> Equal-weight/Selection-BH/Constrained BH qatorlari HAM chiqadi
    # (bo'sh/0 metrikalar bilan) -- har split uchun 3 benchmark + 2 model = 5 qator, jami 10.
    all_results = {
        "TRAIN": {"A": _fake_portfolio_result(sharpe=1.0, num_trades=3), "B": _fake_portfolio_result(sharpe=1.2, num_trades=4)},
        "OOS": {"A": _fake_portfolio_result(sharpe=0.5, num_trades=2), "B": _fake_portfolio_result(sharpe=0.8, num_trades=5)},
    }
    verdicts = {"A": "NO EDGE", "B": "EXIT IMPROVEMENT"}

    df = build_csv_rows(all_results, verdicts=verdicts)

    assert len(df) == 10
    model_rows = df[df["model"].isin(["fixed_sl_tp", "atr_sl_tp"])]
    assert set(zip(model_rows["split"], model_rows["model"])) == {
        ("TRAIN", "fixed_sl_tp"), ("TRAIN", "atr_sl_tp"), ("OOS", "fixed_sl_tp"), ("OOS", "atr_sl_tp"),
    }
    oos_b = df[(df["split"] == "OOS") & (df["model"] == "atr_sl_tp")].iloc[0]
    assert oos_b["verdict"] == "EXIT IMPROVEMENT"
    train_a = df[(df["split"] == "TRAIN") & (df["model"] == "fixed_sl_tp")].iloc[0]
    assert train_a["verdict"] == "-"  # TRAIN split'da verdict yo'q

    bench_rows = df[df["model"].isin(["Equal-weight BH", "Selection-BH", "Constrained BH"])]
    assert len(bench_rows) == 6  # 2 split x 3 benchmark
    assert (bench_rows["verdict"] == "-").all()


def test_build_csv_rows_includes_benchmarks_and_control_row() -> None:
    benches = [
        _fake_benchmark("equal_weight_buy_hold", sharpe=0.8),
        _fake_benchmark_with_trade_count("selection_bh", sharpe=0.6, trade_count=120),
        _fake_benchmark("capital_constrained_buy_hold", sharpe=0.5),
    ]
    all_results = {
        "TRAIN": {
            "A": _fake_portfolio_result(sharpe=1.0, num_trades=3, benchmarks=benches),
            "NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=3, benchmarks=benches),
        },
        "OOS": {
            "A": _fake_portfolio_result(sharpe=1.5, num_trades=3, benchmarks=benches),
            "NOEXIT": _fake_portfolio_result(sharpe=0.9, num_trades=3, benchmarks=benches),
        },
    }
    verdicts = {"A": "EXIT IMPROVEMENT"}

    df = build_csv_rows(all_results, verdicts=verdicts)

    assert set(df["model"]) == {
        "Equal-weight BH", "Selection-BH", "Constrained BH", "no_exit_capped", "fixed_sl_tp",
    }
    no_exit_rows = df[df["model"] == "no_exit_capped"]
    assert len(no_exit_rows) == 2  # TRAIN + OOS
    assert (no_exit_rows["verdict"] == "CONTROL").all()
    bench_rows = df[df["model"].isin(["Equal-weight BH", "Selection-BH", "Constrained BH"])]
    assert (bench_rows["verdict"] == "-").all()
    selection_row = df[df["model"] == "Selection-BH"].iloc[0]
    assert selection_row["trade_count"] == 120
    oos_a = df[(df["split"] == "OOS") & (df["model"] == "fixed_sl_tp")].iloc[0]
    assert oos_a["verdict"] == "EXIT IMPROVEMENT"


# ======================================================================
# main() -- NoExit ogohlantirish
# ======================================================================


def test_main_warns_when_no_exit_excluded_from_exits(monkeypatch, capsys, tmp_path) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df))
    monkeypatch.setattr(er_module, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog", "A", "B", "--start", "2020-01-01", "--lookback", "1", "--min-rr", "1.5",
            "--no-require-trend", "--exits", "A,B", "--max-concurrent", "10",
            "--max-portfolio-risk", "1.0",
        ],
    )

    er_module.main()

    err = capsys.readouterr().err
    assert "OGOHLANTIRISH" in err
    assert "NoExit" in err


def test_main_no_warning_when_no_exit_included(monkeypatch, capsys, tmp_path) -> None:
    df = _make_df(_breakout_rows())
    monkeypatch.setattr("scripts.backtest_portfolio.get_provider", lambda name: _FakeProvider(df=df))
    monkeypatch.setattr(er_module, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog", "A", "B", "--start", "2020-01-01", "--lookback", "1", "--min-rr", "1.5",
            "--no-require-trend", "--exits", "A,NoExit", "--max-concurrent", "10",
            "--max-portfolio-risk", "1.0",
        ],
    )

    er_module.main()

    err = capsys.readouterr().err
    assert "OGOHLANTIRISH" not in err
