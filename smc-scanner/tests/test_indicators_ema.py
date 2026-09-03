"""indicators/ema.py uchun testlar (sintetik seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd
import pytest

from indicators.ema import compute_ema, compute_ema_frame

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _flat_df(prices: list[float], *, volume: float = 1000) -> pd.DataFrame:
    """open=high=low=close bo'lgan sodda OHLCV DataFrame (tz-aware UTC index)."""
    index = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": volume},
        index=index,
    )
    return df[_COLUMNS]


def test_compute_ema_hand_verified() -> None:
    """period=3 -> alpha=0.5. EMA[2] birinchi tasdiqlangan qiymat = o'sha 3 barning
    rekursiv o'rtachasi: seed EMA[0]=10, EMA[1]=0.5*20+0.5*10=15, EMA[2]=0.5*30+0.5*15=22.5.
    (min_periods=3 sababli EMA[0], EMA[1] NaN bilan maskalanadi, lekin rekursiya baribir
    bar 0 dan seed bo'ladi.)"""
    df = _flat_df([10, 20, 30, 40])
    ema = compute_ema(df, period=3)

    assert ema.name == "ema3"
    assert ema.iloc[0:2].isna().all()
    assert ema.iloc[2] == pytest.approx(22.5)
    # EMA[3] = 0.5*40 + 0.5*22.5 = 31.25
    assert ema.iloc[3] == pytest.approx(31.25)


def test_compute_ema_warmup_is_nan() -> None:
    df = _flat_df([1, 2, 3, 4, 5, 6, 7])
    ema = compute_ema(df, period=5)

    assert ema.iloc[0:4].isna().all()
    assert ema.iloc[4:].notna().all()


def test_compute_ema_no_lookahead_bias() -> None:
    """Kelajak barlarni kesish har saqlangan bar uchun EMA qiymatini o'zgartirmasligi kerak."""
    prices = [10, 12, 11, 14, 13, 16, 18, 17, 20, 22, 21, 24, 25, 23, 26]
    df_full = _flat_df(prices)
    ema_full = compute_ema(df_full, period=4)

    for k in (5, 8, 11, 14):
        ema_trunc = compute_ema(df_full.iloc[: k + 1], period=4)
        assert ema_trunc.iloc[k] == pytest.approx(ema_full.iloc[k])


def test_compute_ema_frame_columns_and_index() -> None:
    df = _flat_df(list(range(1, 60)))
    frame = compute_ema_frame(df, fast=5, mid=10, slow=20)

    assert list(frame.columns) == ["ema_fast", "ema_mid", "ema_slow"]
    assert frame.index.equals(df.index)
    # Har ustun o'z period'iga qarab warmup NaN bo'ladi.
    assert frame["ema_fast"].iloc[0:4].isna().all()
    assert frame["ema_slow"].iloc[0:19].isna().all()
    assert frame["ema_fast"].iloc[4] == pytest.approx(compute_ema(df, 5).iloc[4])


def test_compute_ema_short_series_all_nan() -> None:
    df = _flat_df([10, 11, 12])
    ema = compute_ema(df, period=10)

    assert ema.isna().all()
