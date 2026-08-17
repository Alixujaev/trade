"""Offline correctness checks for the price-action Scanner (no network).

Run as: python -m tests.scanner_test
"""
from __future__ import annotations

import sys

import pandas as pd


def _mk_bars(rows: list[list[float]]) -> pd.DataFrame:
    """rows: list of [open, high, low, close]. Returns an OHLCV df."""
    idx = pd.date_range("2024-01-02", periods=len(rows), freq="B")
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])
    df["volume"] = 1_000_000
    return df


def test_atr() -> None:
    from indicators.indicators import atr

    n = 20
    period = 14
    df = _mk_bars([[100.0, 102.0, 98.0, 100.0]] * n)

    result = atr(df, period=period)
    assert result.isna().sum() == period - 1
    # constant high-low range with no prior-close jump -> TR is constant 4.0
    # for every bar, so the EMA of TR converges to 4.0 by the last bar.
    assert abs(result.iloc[-1] - 4.0) < 1e-9

    print("[ok] atr")


def main() -> int:
    tests = [
        test_atr,
    ]
    for t in tests:
        t()
    return 0


if __name__ == "__main__":
    sys.exit(main())
