"""indicators/volume.py uchun testlar (sintetik seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd
import pytest

from indicators.volume import compute_volume_ma, is_volume_confirmed, volume_ratio

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _df_with_volume(volumes: list[float]) -> pd.DataFrame:
    """Berilgan volume qatoridan OHLCV DataFrame (narxlar ahamiyatsiz — 100 doim)."""
    index = pd.date_range("2024-01-01", periods=len(volumes), freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": 100, "high": 100, "low": 100, "close": 100, "volume": volumes},
        index=index,
    )
    return df[_COLUMNS]


def test_compute_volume_ma_hand_verified() -> None:
    df = _df_with_volume([100, 200, 300, 400, 500])
    ma = compute_volume_ma(df, period=3)

    assert ma.name == "volume_ma"
    assert ma.iloc[0:2].isna().all()
    assert ma.iloc[2] == pytest.approx(200.0)  # (100+200+300)/3
    assert ma.iloc[3] == pytest.approx(300.0)  # (200+300+400)/3
    assert ma.iloc[4] == pytest.approx(400.0)


def test_volume_ratio_hand_verified() -> None:
    df = _df_with_volume([100, 100, 100, 400])
    ratio = volume_ratio(df, period=3)

    assert ratio.name == "volume_ratio"
    assert ratio.iloc[0:2].isna().all()
    assert ratio.iloc[2] == pytest.approx(1.0)  # 100 / mean(100,100,100)
    # rolling MA joriy barni ham qamrab oladi (compute_atr konvensiyasi):
    # window = (100, 100, 400) -> mean 200 -> ratio 400/200 = 2.0
    assert ratio.iloc[3] == pytest.approx(2.0)


def test_warmup_is_nan() -> None:
    df = _df_with_volume([10, 20, 30, 40, 50, 60])
    assert compute_volume_ma(df, period=4).iloc[0:3].isna().all()
    assert volume_ratio(df, period=4).iloc[0:3].isna().all()


def test_is_volume_confirmed_threshold_boundary() -> None:
    # rolling MA joriy barni ham qamrab oladi: ratio = v / ((100+100+v)/3).
    # v == 200 -> ratio AYNAN 1.5 (window mean = 400/3).
    below = _df_with_volume([100, 100, 100, 199])
    equal = _df_with_volume([100, 100, 100, 200])
    above = _df_with_volume([100, 100, 100, 201])

    assert is_volume_confirmed(below, 3, period=3, threshold=1.5) is False
    assert is_volume_confirmed(equal, 3, period=3, threshold=1.5) is True
    assert is_volume_confirmed(above, 3, period=3, threshold=1.5) is True


def test_is_volume_confirmed_out_of_range_or_nan_returns_false() -> None:
    df = _df_with_volume([100, 100, 100, 400])

    assert is_volume_confirmed(df, -1, period=3) is False
    assert is_volume_confirmed(df, 99, period=3) is False
    assert is_volume_confirmed(df, 1, period=3) is False  # warmup -> NaN ratio


def test_is_volume_confirmed_nan_ratio_returns_false() -> None:
    df = _df_with_volume([0, 0, 0, 0])
    # butun window 0 -> volume_ma = 0 -> ratio = NaN -> tasdiqlanmagan
    assert is_volume_confirmed(df, 3, period=3, threshold=1.5) is False


def test_empty_df_no_crash() -> None:
    index = pd.date_range("2024-01-01", periods=0, freq="D", tz="UTC")
    df_empty = pd.DataFrame(columns=_COLUMNS, index=index)

    assert compute_volume_ma(df_empty, period=3).empty
    assert volume_ratio(df_empty, period=3).empty
    assert is_volume_confirmed(df_empty, 0, period=3) is False
