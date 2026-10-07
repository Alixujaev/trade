"""smc/zones.py uchun testlar (qo'lda hisoblangan sintetik OHLC seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd
import pytest

from config.settings import DISPLACEMENT_ATR_MULT
from smc.types import StructureState, ZoneType
from smc.zones import compute_atr, detect_displacement, detect_fvgs, detect_order_blocks


_COLUMNS = ["open", "high", "low", "close", "volume"]


def _make_ohlc_df(rows: list[dict]) -> pd.DataFrame:
    """Har bir bar uchun aniq open/high/low/close/volume berilgan DataFrame yasaydi."""
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    if not rows:
        return pd.DataFrame(columns=_COLUMNS, index=index)
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[_COLUMNS]


# Qo'lda hisoblangan 8-bar seriya (ATR_PERIOD=3, mult=1.0):
# i=0..2 — sokin warmup (ATR birinchi marta i=2'da tasdiqlanadi, =2.0)
# i=3    — sokin, kichik bearish tana (body=0.2 < 1.0*ATR=2.0) -> displacement YO'Q
# i=4    — kuchli bullish displacement (body=5 >= 1.0*ATR≈3.2333)
# i=5    — gap'ni tasdiqlaydi: low(105.6) > high[3](101) -> bullish FVG, top=105.6, bottom=101
# i=6    — zonaga qaytmaydi
# i=7    — low(104) <= 105.6 va high(108) >= 101 -> FVG shu yerda to'ladi
_BASE_ROWS = [
    {"open": 100, "high": 101, "low": 99, "close": 100},
    {"open": 100, "high": 101, "low": 99, "close": 100.2},
    {"open": 100.2, "high": 101.2, "low": 99.2, "close": 100},
    {"open": 100, "high": 101, "low": 99, "close": 99.8},
    {"open": 100, "high": 105.5, "low": 99.8, "close": 105},
    {"open": 106, "high": 107, "low": 105.6, "close": 106.5},
    {"open": 106.5, "high": 108, "low": 106, "close": 107.5},
    {"open": 107.5, "high": 108, "low": 104, "close": 106},
]


def test_compute_atr_hand_verified_values() -> None:
    df = _make_ohlc_df(_BASE_ROWS)
    atr = compute_atr(df, period=3)

    assert atr.iloc[0:2].isna().all()
    assert atr.iloc[2] == pytest.approx(2.0)
    assert atr.iloc[3] == pytest.approx(2.0)
    assert atr.iloc[4] == pytest.approx(3.2333, abs=1e-3)


def test_detect_displacement_threshold() -> None:
    df = _make_ohlc_df(_BASE_ROWS)
    displacement = detect_displacement(df, atr_period=3, mult=1.0)

    assert list(displacement.iloc[0:4]) == [0, 0, 0, 0]  # warmup + kuchsiz bar3
    assert displacement.iloc[4] == 1  # kuchli bullish


def test_detect_fvgs_creates_bullish_zone_and_marks_fill() -> None:
    df = _make_ohlc_df(_BASE_ROWS)
    zones = detect_fvgs(df, atr_period=3, mult=1.0)

    assert len(zones) == 1
    zone = zones[0]
    assert zone.zone_type is ZoneType.FVG
    assert zone.direction is StructureState.BULLISH
    assert zone.top == pytest.approx(105.6)
    assert zone.bottom == pytest.approx(101)
    assert zone.created_index_pos == 5
    assert zone.filled is True
    assert zone.filled_index_pos == 7


def test_no_displacement_means_no_fvg_despite_price_gap() -> None:
    """Xuddi shu gap, lekin bar4 tanasi kichik — displacement yo'q, FVG ham OB ham yo'q."""
    rows = [dict(r) for r in _BASE_ROWS]
    rows[4] = {"open": 100, "high": 105.5, "low": 99.8, "close": 100.3}  # kichik tana, gap saqlanadi
    df = _make_ohlc_df(rows)

    assert detect_displacement(df, atr_period=3, mult=1.0).iloc[4] == 0
    assert detect_fvgs(df, atr_period=3, mult=1.0) == []
    assert detect_order_blocks(df, atr_period=3, mult=1.0) == []


def test_detect_order_blocks_selects_nearest_bearish_candle_and_stays_unfilled() -> None:
    df = _make_ohlc_df(_BASE_ROWS)
    zones = detect_order_blocks(df, atr_period=3, mult=1.0)

    assert len(zones) == 1
    zone = zones[0]
    assert zone.zone_type is ZoneType.ORDER_BLOCK
    assert zone.direction is StructureState.BULLISH
    assert zone.top == pytest.approx(101)  # bar3'ning high'i
    assert zone.bottom == pytest.approx(99)  # bar3'ning low'i
    assert zone.created_index_pos == 4
    assert zone.filled is False
    assert zone.filled_ts is None


def test_order_block_backward_scan_skips_long_monotonic_run() -> None:
    """Displacement'dan oldin ko'p sonli bir xil (bullish) candle bo'lsa ham,
    orqaga qarab qidiruv to'g'ri, uzoqroqdagi yagona bearish candle'ni topishi kerak."""
    quiet_bullish = {"open": 100, "high": 100.6, "low": 99.6, "close": 100.3}
    quiet_bearish = {"open": 100.3, "high": 100.6, "low": 99.6, "close": 100}
    strong_bullish = {"open": 100, "high": 121, "low": 99.5, "close": 120}

    rows = [dict(quiet_bullish) for _ in range(10)]
    bearish_index = len(rows)
    rows.append(dict(quiet_bearish))
    rows += [dict(quiet_bullish) for _ in range(10)]
    displacement_index = len(rows)
    rows.append(dict(strong_bullish))

    df = _make_ohlc_df(rows)
    zones = detect_order_blocks(df)  # default ATR_PERIOD/DISPLACEMENT_ATR_MULT

    assert len(zones) == 1
    zone = zones[0]
    assert zone.created_index_pos == displacement_index
    assert zone.top == pytest.approx(quiet_bearish["high"])
    assert zone.bottom == pytest.approx(quiet_bearish["low"])
    assert zone.created_index_pos - bearish_index > 1  # ko'p bar orqada joylashgan


def test_detect_fvgs_no_lookahead_bias() -> None:
    """Kesilgan (truncated) data'da zona hali ochiq ko'rinishi kerak — kelajakdagi fill bilinmaydi."""
    df_full = _make_ohlc_df(_BASE_ROWS)
    full_zones = detect_fvgs(df_full, atr_period=3, mult=1.0)

    df_truncated = df_full.iloc[:7]  # fill candle (i=7) bu yerda yo'q
    truncated_zones = detect_fvgs(df_truncated, atr_period=3, mult=1.0)

    assert len(full_zones) == len(truncated_zones) == 1
    assert truncated_zones[0].top == full_zones[0].top
    assert truncated_zones[0].bottom == full_zones[0].bottom
    assert truncated_zones[0].created_index_pos == full_zones[0].created_index_pos
    assert truncated_zones[0].filled is False
    assert truncated_zones[0].filled_ts is None
    assert truncated_zones[0].filled_index_pos is None
    assert full_zones[0].filled is True  # to'liq data'da esa to'ldirilgan


def test_mult_omitted_falls_back_to_settings_default() -> None:
    """mult berilmasa, settings.DISPLACEMENT_ATR_MULT bilan bir xil natija berishi kerak."""
    df = _make_ohlc_df(_BASE_ROWS)

    default_fvgs = detect_fvgs(df, atr_period=3)
    explicit_fvgs = detect_fvgs(df, atr_period=3, mult=DISPLACEMENT_ATR_MULT)
    assert default_fvgs == explicit_fvgs

    default_obs = detect_order_blocks(df, atr_period=3)
    explicit_obs = detect_order_blocks(df, atr_period=3, mult=DISPLACEMENT_ATR_MULT)
    assert default_obs == explicit_obs


def test_mult_override_sweeps_without_touching_settings() -> None:
    """Turli mult qiymatlarini settings'ni monkeypatch qilmasdan solishtirish mumkin bo'lishi kerak."""
    df = _make_ohlc_df(_BASE_ROWS)
    mult_before = DISPLACEMENT_ATR_MULT

    strict = detect_fvgs(df, atr_period=3, mult=10.0)  # juda qattiq chegara — hech narsa topilmaydi
    loose = detect_fvgs(df, atr_period=3, mult=1.0)

    assert strict == []
    assert len(loose) == 1
    # settings qiymati o'zgarmagani (global holat ifloslanmagani)ni tasdiqlaymiz
    assert DISPLACEMENT_ATR_MULT == mult_before


def test_empty_or_insufficient_data_returns_empty_no_crash() -> None:
    df_empty = _make_ohlc_df([])
    df_short = _make_ohlc_df(_BASE_ROWS[:2])

    assert detect_fvgs(df_empty) == []
    assert detect_fvgs(df_short) == []
    assert detect_order_blocks(df_empty) == []
    assert detect_order_blocks(df_short) == []
    assert compute_atr(df_short).isna().all()
