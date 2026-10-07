"""indicators/vwap.py uchun testlar to'plami.

Sessiya reset, no-lookahead, premarket aralashmasligi, zero-volume va masofa/slope testlari.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from indicators.atr import compute_atr
from indicators.vwap import (
    compute_vwap,
    compute_vwap_distance,
    compute_vwap_distance_atr,
    compute_vwap_slope,
)


def _make_sample_intraday(
    data: list[tuple[str, float, float, float, float]],
) -> pd.DataFrame:
    """(iso_timestamp_utc, high, low, close, volume) qatorlaridan DataFrame yasaydi."""
    timestamps, highs, lows, closes, volumes = zip(*data)
    idx = pd.to_datetime(timestamps).tz_localize("UTC")
    df = pd.DataFrame(
        {
            "open": closes,  # soddalik uchun open=close
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )
    return df[["open", "high", "low", "close", "volume"]]


def test_vwap_formula_hand_verified() -> None:
    # 2024-06-03 (EDT: 13:30 UTC = 09:30 EDT)
    # Bar 1: H=110, L=90, C=100, V=100 -> TP = 100, cum_tp_vol = 10,000, cum_vol = 100 -> VWAP = 100
    # Bar 2: H=120, L=100, C=110, V=200 -> TP = 110, cum_tp_vol = 10000 + 22000 = 32000, cum_vol = 300 -> VWAP = 106.66667
    bars = [
        ("2024-06-03 13:30:00", 110.0, 90.0, 100.0, 100.0),
        ("2024-06-03 13:35:00", 120.0, 100.0, 110.0, 200.0),
    ]
    df = _make_sample_intraday(bars)
    vwap = compute_vwap(df)

    assert vwap.name == "vwap"
    assert len(vwap) == 2
    assert vwap.iloc[0] == pytest.approx(100.0)
    assert vwap.iloc[1] == pytest.approx(32000.0 / 300.0)


def test_vwap_session_reset_and_day_isolation() -> None:
    """Kun o'zgarganda (09:30 ET birinchi barida) VWAP to'liq reset bo'ladi."""
    # Day 1: 2 ta bar, yuqori narxda (~500)
    # Day 2: 1 ta bar, past narxda: H=110, L=100, C=105, V=100 -> TP = 105, VWAP = 105.0 bo'lishi SHART!
    bars = [
        # Day 1 (2024-06-03)
        ("2024-06-03 13:30:00", 510.0, 490.0, 500.0, 1000.0),
        ("2024-06-03 13:35:00", 520.0, 500.0, 510.0, 1000.0),
        # Day 2 (2024-06-04)
        ("2024-06-04 13:30:00", 110.0, 100.0, 105.0, 100.0),
    ]
    df = _make_sample_intraday(bars)
    vwap = compute_vwap(df)

    # Day 2 ning birinchi barida kechagi 500 narxining ta'siri 0 bo'lishi kerak
    assert vwap.iloc[2] == pytest.approx(105.0)


def test_premarket_does_not_contaminate_rth_vwap() -> None:
    """Premarket barlari RTH VWAP qiymatini bulg'amasligi (contaminate qilmasligi) kerak."""
    bars = [
        # Premarket (08:00 UTC = 04:00 EDT)
        ("2024-06-03 08:00:00", 999.0, 999.0, 999.0, 50000.0),
        ("2024-06-03 13:00:00", 888.0, 888.0, 888.0, 50000.0),
        # RTH birinchi bar (13:30 UTC = 09:30 EDT)
        ("2024-06-03 13:30:00", 110.0, 100.0, 105.0, 100.0),
    ]
    df = _make_sample_intraday(bars)
    vwap = compute_vwap(df, rth_only=True)

    # Premarket barlarida RTH VWAP NaN bo'ladi
    assert np.isnan(vwap.iloc[0])
    assert np.isnan(vwap.iloc[1])

    # 09:30 dagi birinchi RTH barida VWAP aynan shu barning o'zidan (105.0) boshlanadi
    assert vwap.iloc[2] == pytest.approx(105.0)


def test_no_future_bar_influence() -> None:
    """Kelajak barlari qirqib tashlanganda ham o'tmish barlaridagi VWAP o'zgarmaydi."""
    bars = [
        ("2024-06-03 13:30:00", 100.0, 100.0, 100.0, 100.0),
        ("2024-06-03 13:35:00", 110.0, 110.0, 110.0, 100.0),
        ("2024-06-03 13:40:00", 200.0, 200.0, 200.0, 1000.0),
    ]
    df_full = _make_sample_intraday(bars)
    df_trunc = df_full.iloc[:2].copy()

    vwap_full = compute_vwap(df_full)
    vwap_trunc = compute_vwap(df_trunc)

    assert vwap_full.iloc[0] == pytest.approx(vwap_trunc.iloc[0])
    assert vwap_full.iloc[1] == pytest.approx(vwap_trunc.iloc[1])


def test_zero_volume_handling() -> None:
    """Sessiya boshida hajm 0 bo'lsa NaN, keyin savdo boshlangach kelgan 0-hajm avvalgi qiymatni saqlaydi."""
    bars = [
        # Sessiya boshida savdo yo'q
        ("2024-06-03 13:30:00", 100.0, 100.0, 100.0, 0.0),
        # Savdo bo'ldi
        ("2024-06-03 13:35:00", 110.0, 90.0, 100.0, 100.0),
        # Yana hajm 0 bo'lgan bar keldi
        ("2024-06-03 13:40:00", 105.0, 95.0, 100.0, 0.0),
    ]
    df = _make_sample_intraday(bars)
    vwap = compute_vwap(df)

    assert np.isnan(vwap.iloc[0])
    assert vwap.iloc[1] == pytest.approx(100.0)
    # 0 hajm qo'shilgach, cum_vol ham cum_tp_vol ham o'zgarmaydi -> VWAP 100.0 saqlanadi
    assert vwap.iloc[2] == pytest.approx(100.0)


def test_vwap_does_not_mutate_dataframe() -> None:
    bars = [
        ("2024-06-03 13:30:00", 100.0, 100.0, 100.0, 100.0),
    ]
    df = _make_sample_intraday(bars)
    cols_before = df.columns.tolist()
    _ = compute_vwap(df)
    assert df.columns.tolist() == cols_before


def test_vwap_distance_helpers() -> None:
    bars = [
        ("2024-06-03 13:30:00", 100.0, 100.0, 100.0, 100.0),
        ("2024-06-03 13:35:00", 110.0, 110.0, 110.0, 100.0),
    ]
    df = _make_sample_intraday(bars)
    vwap = compute_vwap(df)
    # vwap[0] = 100, close[0] = 100 -> dist = 0.0
    # vwap[1] = 105, close[1] = 110 -> dist = (110 - 105) / 105 = 5/105
    dist = compute_vwap_distance(df, vwap)
    assert dist.iloc[0] == pytest.approx(0.0)
    assert dist.iloc[1] == pytest.approx(5.0 / 105.0)

    # ATR masofasi
    atr = compute_atr(df, period=1)  # har barda TR olinadi
    dist_atr = compute_vwap_distance_atr(df, atr, vwap)
    assert dist_atr.name == "vwap_distance_atr"


def test_vwap_slope_resets_across_sessions() -> None:
    """Kun o'zgarganda nishablik (slope) kechagi kunning yopilish VWAP'i bilan hisoblanmaydi."""
    bars = [
        ("2024-06-03 13:30:00", 100.0, 100.0, 100.0, 100.0),
        ("2024-06-03 13:35:00", 110.0, 110.0, 110.0, 100.0),
        # Day 2
        ("2024-06-04 13:30:00", 50.0, 50.0, 50.0, 100.0),
        ("2024-06-04 13:35:00", 60.0, 60.0, 60.0, 100.0),
    ]
    df = _make_sample_intraday(bars)
    vwap = compute_vwap(df)
    slope = compute_vwap_slope(vwap, period=1, dt_index=df.index)

    # Day 1 bar 0 da shift(1) yo'q -> NaN
    assert np.isnan(slope.iloc[0])
    # Day 1 bar 1 da (105 - 100) / 1 = 5.0
    assert slope.iloc[1] == pytest.approx(5.0)
    # Day 2 bar 0 da kechagi Day 1 olinmasligi kerak -> NaN bo'lishi SHART!
    assert np.isnan(slope.iloc[2])
    # Day 2 bar 1 da (55 - 50) / 1 = 5.0
    assert slope.iloc[3] == pytest.approx(5.0)
