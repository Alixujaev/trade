"""scripts/backtest_matrix.py uchun testlar (real tarmoqsiz — provider monkeypatch qilinadi)."""

from __future__ import annotations

import pandas as pd
import pytest

import scripts.backtest_matrix as matrix_module
from scripts.backtest_matrix import (
    _default_provider_for_interval,
    aggregate_by,
    build_matrix,
    run_one_combination,
    top_by_edge,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[["open", "high", "low", "close", "volume"]]


class _FakeProvider:
    """Sinov uchun sodda DataProvider — hech qanday tarmoqqa chiqmaydi."""

    def __init__(self, df: pd.DataFrame | None = None, error: Exception | None = None) -> None:
        self._df = df
        self._error = error

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        if self._error is not None:
            raise self._error
        return self._df


def test_default_provider_for_interval() -> None:
    assert _default_provider_for_interval("4h") == "alpaca"
    assert _default_provider_for_interval("1d") == "yfinance"
    assert _default_provider_for_interval("1wk") == "yfinance"


def test_run_one_combination_success(monkeypatch) -> None:
    # Kvant jihatdan sodda: bo'sh signal -> 0 savdo, lekin crash yo'q, natija to'g'ri shakllangan
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100}] * 5
    df = _make_df(rows)
    monkeypatch.setattr(matrix_module, "get_provider", lambda name: _FakeProvider(df=df))

    row = run_one_combination("SPUS", "1d", "yfinance", "fixed_pct", 1.5, lookback=1)

    assert row["ERROR"] is None
    assert row["SYMBOL"] == "SPUS"
    assert row["INTERVAL"] == "1d"
    assert row["PROVIDER"] == "yfinance"
    assert row["TRADES"] == 0
    assert row["LOW_SAMPLE"] is True  # 0 < LOW_SAMPLE_THRESHOLD
    assert row["EDGE"] == pytest.approx(row["RETURN%"] - row["BUY&HOLD%"])


def test_run_one_combination_handles_provider_error(monkeypatch) -> None:
    monkeypatch.setattr(
        matrix_module, "get_provider", lambda name: _FakeProvider(error=ValueError("kredensial yo'q"))
    )

    row = run_one_combination("SPUS", "4h", "alpaca", "fixed_pct", 1.5)

    assert row["ERROR"] == "kredensial yo'q"
    assert row["TRADES"] is None
    assert row["EDGE"] is None
    assert row["SYMBOL"] == "SPUS"
    assert row["INTERVAL"] == "4h"


def test_build_matrix_continues_after_one_combination_fails(monkeypatch) -> None:
    """Bitta combo yiqilsa (masalan simulyatsiya qilingan tarmoq xatosi), qolganlari davom etishi kerak."""
    good_df = _make_df([{"open": 100, "high": 101, "low": 99, "close": 100}] * 5)

    def fake_get_provider(name: str) -> _FakeProvider:
        if name == "alpaca":
            raise RuntimeError("alpaca .env topilmadi")
        return _FakeProvider(df=good_df)

    monkeypatch.setattr(matrix_module, "get_provider", fake_get_provider)

    matrix = build_matrix(
        symbols=["SPUS"],
        intervals=["1d", "4h"],
        providers=None,  # avtomatik: 1d->yfinance (muvaffaqiyatli), 4h->alpaca (xato)
        risk_models=["fixed_pct"],
        mults=[1.5],
        lookback=1,
    )

    assert len(matrix) == 2
    yfinance_row = matrix[matrix["INTERVAL"] == "1d"].iloc[0]
    alpaca_row = matrix[matrix["INTERVAL"] == "4h"].iloc[0]
    assert pd.isna(yfinance_row["ERROR"])
    assert not pd.isna(alpaca_row["ERROR"])


def test_build_matrix_empty_combination_set_returns_empty_df() -> None:
    matrix = build_matrix(symbols=[], intervals=["1d"], providers=None, risk_models=["fixed_pct"], mults=[1.5])
    assert matrix.empty


def test_top_by_edge_excludes_errors_and_sorts_descending(monkeypatch) -> None:
    good_df = _make_df([{"open": 100, "high": 101, "low": 99, "close": 100}] * 5)

    call_count = {"n": 0}

    def fake_get_provider(name: str) -> _FakeProvider:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("xato")
        return _FakeProvider(df=good_df)

    monkeypatch.setattr(matrix_module, "get_provider", fake_get_provider)

    matrix = build_matrix(
        symbols=["A", "B", "C"], intervals=["1d"], providers=["yfinance"],
        risk_models=["fixed_pct"], mults=[1.5], lookback=1,
    )

    top = top_by_edge(matrix, n=5)
    assert top["ERROR"].isna().all()
    assert len(top) == 2  # 3 dan 1 tasi xato
    assert list(top["EDGE"]) == sorted(top["EDGE"], reverse=True)


def test_aggregate_by_interval_ignores_error_rows(monkeypatch) -> None:
    good_df = _make_df([{"open": 100, "high": 101, "low": 99, "close": 100}] * 5)
    monkeypatch.setattr(matrix_module, "get_provider", lambda name: _FakeProvider(df=good_df))

    matrix = build_matrix(
        symbols=["SPUS"], intervals=["1d"], providers=["yfinance"],
        risk_models=["fixed_pct"], mults=[1.0, 1.5], lookback=1,
    )

    agg = aggregate_by(matrix, "INTERVAL")
    assert "1d" in agg.index
    assert "TRADES" in agg.columns
