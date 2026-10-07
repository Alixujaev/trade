"""strategy/trend.py uchun testlar (sintetik seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd

from strategy.trend import compute_trend_regime, trend_regime_at
from strategy.types import TrendRegime

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _flat_df(prices: list[float], *, volume: float = 1000) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": volume},
        index=index,
    )
    return df[_COLUMNS]


def test_bullish_regime_when_emas_stacked_up() -> None:
    """Uzoq, barqaror o'suvchi trend -> oxirida EMA'lar bullish tartibda."""
    df = _flat_df([float(i) for i in range(1, 121)])  # 1..120 monoton o'sish
    regime = compute_trend_regime(df, fast=5, mid=10, slow=20)

    assert regime.name == "trend_regime"
    assert regime.iloc[-1] is TrendRegime.BULLISH
    assert regime.iloc[-5:].eq(TrendRegime.BULLISH).all()


def test_bearish_regime_mirror() -> None:
    df = _flat_df([float(i) for i in range(120, 0, -1)])  # 120..1 monoton pasayish
    regime = compute_trend_regime(df, fast=5, mid=10, slow=20)

    assert regime.iloc[-1] is TrendRegime.BEARISH
    assert regime.iloc[-5:].eq(TrendRegime.BEARISH).all()


def test_choppy_series_is_neutral() -> None:
    prices = [100, 101, 99, 100, 101, 99, 100, 101, 99, 100] * 6  # 60 bar arra tishi
    df = _flat_df(prices)
    regime = compute_trend_regime(df, fast=5, mid=10, slow=20)

    assert regime.iloc[-1] is TrendRegime.NEUTRAL


def test_warmup_bars_are_neutral() -> None:
    df = _flat_df([float(i) for i in range(1, 40)])
    regime = compute_trend_regime(df, fast=5, mid=10, slow=20)

    # slow=20 -> birinchi 19 bar EMA_slow NaN -> NEUTRAL
    assert regime.iloc[0:19].eq(TrendRegime.NEUTRAL).all()


def test_trend_regime_at_bounds() -> None:
    df = _flat_df([float(i) for i in range(1, 40)])
    regime = compute_trend_regime(df, fast=5, mid=10, slow=20)

    assert trend_regime_at(regime, -1) is TrendRegime.NEUTRAL
    assert trend_regime_at(regime, 999) is TrendRegime.NEUTRAL
    assert trend_regime_at(regime, len(df) - 1) is regime.iloc[-1]


def test_compute_trend_regime_no_lookahead_bias() -> None:
    prices = [float(i) for i in range(1, 90)] + [50.0, 55.0, 52.0, 58.0, 54.0]
    df_full = _flat_df(prices)
    regime_full = compute_trend_regime(df_full, fast=5, mid=10, slow=20)

    for k in (30, 50, 70, 88):
        regime_trunc = compute_trend_regime(df_full.iloc[: k + 1], fast=5, mid=10, slow=20)
        assert regime_trunc.iloc[k] is regime_full.iloc[k]
