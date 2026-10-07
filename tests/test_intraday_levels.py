"""levels/intraday_levels.py uchun to'liq testlar to'plami.

PDH, PDL, PDC, PMH, PML, ORH, ORL va HOD/LOD expanding darajalari bo'yicha
qat'iy no-lookahead va chegaraviy holatlar sinovi.
"""

from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd
import pytest

from levels.intraday_levels import (
    compute_expanding_hod_lod,
    compute_intraday_levels,
    compute_opening_range,
    compute_premarket_levels,
    compute_previous_day_levels,
)


def _make_sample_df(
    data: list[tuple[str, float, float, float, float]],
) -> pd.DataFrame:
    timestamps, highs, lows, closes, volumes = zip(*data)
    idx = pd.to_datetime(timestamps).tz_localize("UTC")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )
    return df[["open", "high", "low", "close", "volume"]]


def test_previous_day_levels_uses_d_minus_1_only() -> None:
    # 2 kunlik ma'lumot (EDT: 13:30 UTC = 09:30 EDT)
    # Day 1: High=150, Low=120, Close=130
    # Day 2: High=200, Low=90, Close=180
    bars = [
        # Day 1 (2024-06-03)
        ("2024-06-03 13:30:00", 140.0, 120.0, 125.0, 100.0),
        ("2024-06-03 15:00:00", 150.0, 122.0, 130.0, 100.0),  # D-1 high=150, low=120, close=130
        # Day 2 (2024-06-04)
        ("2024-06-04 13:30:00", 190.0, 100.0, 110.0, 100.0),
        ("2024-06-04 15:00:00", 200.0, 90.0, 180.0, 100.0),  # Bugun 200 gacha chiqdi va 90 gacha tushdi
    ]
    df = _make_sample_df(bars)
    pdh, pdl, pdc = compute_previous_day_levels(df)

    # Day 1 da D-1 yo'q -> barchasi NaN
    assert np.isnan(pdh.iloc[0])
    assert np.isnan(pdl.iloc[0])
    assert np.isnan(pdc.iloc[0])

    # Day 2 dagi barcha barlar uchun PDH=150, PDL=120, PDC=130 bo'lishi SHART
    assert pdh.iloc[2] == pytest.approx(150.0)
    assert pdl.iloc[2] == pytest.approx(120.0)
    assert pdc.iloc[2] == pytest.approx(130.0)

    # Bugungi kunning yangi rekordlari (200 va 90) bugungi PDH va PDL ni O'ZGARTIRMASLIGI SHART!
    assert pdh.iloc[3] == pytest.approx(150.0)
    assert pdl.iloc[3] == pytest.approx(120.0)
    assert pdc.iloc[3] == pytest.approx(130.0)


def test_premarket_levels_isolated_from_rth() -> None:
    # 2024-06-03
    bars = [
        # Premarket (08:00 UTC = 04:00 EDT)
        ("2024-06-03 08:00:00", 105.0, 95.0, 100.0, 10.0),
        ("2024-06-03 10:00:00", 115.0, 90.0, 110.0, 20.0),  # PMH=115, PML=90
        # RTH boshlanishi (13:30 UTC = 09:30 EDT)
        ("2024-06-03 13:30:00", 150.0, 80.0, 140.0, 500.0),  # RTH barlari
        ("2024-06-03 15:00:00", 250.0, 70.0, 240.0, 500.0),
    ]
    df = _make_sample_df(bars)
    pmh, pml = compute_premarket_levels(df)

    # Premarket ichida expanding
    assert pmh.iloc[0] == pytest.approx(105.0)
    assert pml.iloc[0] == pytest.approx(95.0)
    assert pmh.iloc[1] == pytest.approx(115.0)
    assert pml.iloc[1] == pytest.approx(90.0)

    # 09:30 va undan keyingi RTH barlarida PMH=115, PML=90 qat'iy muzlatilgan bo'lishi kerak
    # RTH dagi 150, 250 va 80, 70 premarket qiymatlarini o'zgartira olmaydi!
    assert pmh.iloc[2] == pytest.approx(115.0)
    assert pml.iloc[2] == pytest.approx(90.0)
    assert pmh.iloc[3] == pytest.approx(115.0)
    assert pml.iloc[3] == pytest.approx(90.0)


def test_premarket_empty_when_no_premarket_data() -> None:
    # Faqat RTH barlari berilgan kun
    bars = [
        ("2024-06-03 13:30:00", 105.0, 95.0, 100.0, 10.0),
        ("2024-06-03 13:35:00", 115.0, 90.0, 110.0, 20.0),
    ]
    df = _make_sample_df(bars)
    pmh, pml = compute_premarket_levels(df)
    assert pmh.isna().all()
    assert pml.isna().all()


def test_opening_range_unavailable_before_completion() -> None:
    # 09:30–09:45 oralig'idagi barlar (13:30, 13:35, 13:40 UTC)
    # 09:45 dagi bar (13:45 UTC) va undan keyingi barlar (13:50 UTC)
    bars = [
        ("2024-06-03 13:30:00", 102.0, 98.0, 100.0, 100.0),  # 09:30 EDT
        ("2024-06-03 13:35:00", 105.0, 99.0, 104.0, 100.0),  # 09:35 EDT
        ("2024-06-03 13:40:00", 104.0, 96.0, 101.0, 100.0),  # 09:40 EDT -> ORH=105, ORL=96
        ("2024-06-03 13:45:00", 108.0, 100.0, 107.0, 100.0),  # 09:45 EDT -> OR finalized!
        ("2024-06-03 13:50:00", 150.0, 80.0, 140.0, 100.0),  # 09:50 EDT
    ]
    df = _make_sample_df(bars)
    orh, orl = compute_opening_range(df, start_time=time(9, 30), end_time=time(9, 45))

    # 09:45 dan oldin ORH va ORL mavjud EMAS (NaN)
    assert np.isnan(orh.iloc[0])
    assert np.isnan(orh.iloc[1])
    assert np.isnan(orh.iloc[2])

    # 09:45 va undan keyin ORH=105.0, ORL=96.0
    assert orh.iloc[3] == pytest.approx(105.0)
    assert orl.iloc[3] == pytest.approx(96.0)

    # Keyingi 150 va 80 narxlari ORH/ORL ga ta'sir qilmaydi!
    assert orh.iloc[4] == pytest.approx(105.0)
    assert orl.iloc[4] == pytest.approx(96.0)


def test_hod_lod_strictly_expanding_anti_lookahead() -> None:
    """Anti-lookahead sinovi: oxirgi barda ulkan yangi high bo'lsa, avvalgi barlarning HOD'i o'zgarmasligi shart."""
    bars = [
        ("2024-06-03 13:30:00", 100.0, 90.0, 95.0, 100.0),
        ("2024-06-03 13:35:00", 105.0, 92.0, 102.0, 100.0),
        ("2024-06-03 13:40:00", 102.0, 85.0, 90.0, 100.0),
        ("2024-06-03 15:55:00", 999.0, 10.0, 500.0, 1000.0),  # Ulkan HOD=999 va LOD=10
    ]
    df = _make_sample_df(bars)
    hod, lod = compute_expanding_hod_lod(df)

    # Bar 0
    assert hod.iloc[0] == pytest.approx(100.0)
    assert lod.iloc[0] == pytest.approx(90.0)

    # Bar 1 (H=105, L=92) -> HOD=105, LOD=90
    assert hod.iloc[1] == pytest.approx(105.0)
    assert lod.iloc[1] == pytest.approx(90.0)

    # Bar 2 (H=102, L=85) -> HOD=105, LOD=85 (kelajakdagi 999 va 10 KO'RINMAYDI!)
    assert hod.iloc[2] == pytest.approx(105.0)
    assert lod.iloc[2] == pytest.approx(85.0)

    # Faqat oxirgi barda 999 va 10 chiqadi
    assert hod.iloc[3] == pytest.approx(999.0)
    assert lod.iloc[3] == pytest.approx(10.0)


def test_compute_intraday_levels_complete_frame() -> None:
    bars = [
        # Day 1
        ("2024-06-03 13:30:00", 100.0, 90.0, 95.0, 100.0),
        ("2024-06-03 13:45:00", 110.0, 85.0, 105.0, 100.0),
        # Day 2
        ("2024-06-04 13:30:00", 120.0, 110.0, 115.0, 100.0),
    ]
    df = _make_sample_df(bars)
    levels = compute_intraday_levels(df)

    expected_cols = ["pdh", "pdl", "pdc", "pmh", "pml", "orh", "orl", "hod", "lod"]
    assert list(levels.columns) == expected_cols
    assert len(levels) == 3
    # Day 2 dagi PDH Day 1 ning high'i (110.0) bo'lishi kerak
    assert levels["pdh"].iloc[2] == pytest.approx(110.0)
