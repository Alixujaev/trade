"""levels/support_resistance.py uchun testlar (sintetik zig-zag seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd

from levels.support_resistance import active_sr_zones_at, detect_sr_zones, nearest_resistance_above
from levels.types import SRZoneKind

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _flat_df(prices: list[float], *, volume: float = 1000) -> pd.DataFrame:
    """open=high=low=close bo'lgan sodda OHLCV DataFrame (tz-aware UTC index)."""
    index = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": volume},
        index=index,
    )
    return df[_COLUMNS]


# lookback=1 zig-zag: 4 ta low ~99.5 atrofida, 3 ta high ~112.3 atrofida.
# swing low index_pos: 1(100),3(101),5(99),7(98) -> confirmed 2,4,6,8
# swing high index_pos: 2(112),4(113),6(112)     -> confirmed 3,5,7
_ZIGZAG = [110, 100, 112, 101, 113, 99, 112, 98, 114]


def test_detects_support_and_resistance_zones() -> None:
    zones = detect_sr_zones(_flat_df(_ZIGZAG), lookback=1)

    assert len(zones) == 2
    support = next(z for z in zones if z.kind is SRZoneKind.SUPPORT)
    resistance = next(z for z in zones if z.kind is SRZoneKind.RESISTANCE)

    # Support: birinchi 3 ta low (100, 101, 99) -> band [99, 101]
    assert (support.bottom, support.top) == (99.0, 101.0)
    assert support.touch_count == 3
    # Resistance: birinchi 3 ta high (112, 113, 112) -> band [112, 113]
    assert (resistance.bottom, resistance.top) == (112.0, 113.0)
    assert resistance.touch_count == 3


def test_min_touches_gate() -> None:
    """Bir darajada faqat 2 teginish bo'lsa zona tug'ilmaydi."""
    df = _flat_df([110, 100, 112, 101, 113])  # lows: 100, 101 (2 ta) ; highs: 112 (1 ta)
    assert detect_sr_zones(df, lookback=1) == []


def test_confirmed_index_pos_is_max_member() -> None:
    zones = detect_sr_zones(_flat_df(_ZIGZAG), lookback=1)
    support = next(z for z in zones if z.kind is SRZoneKind.SUPPORT)
    resistance = next(z for z in zones if z.kind is SRZoneKind.RESISTANCE)

    # support a'zolari confirmed 2,4,6 -> max 6 ; resistance 3,5,7 -> max 7
    assert support.confirmed_index_pos == 6
    assert resistance.confirmed_index_pos == 7


def test_active_sr_zones_at_excludes_future_zones() -> None:
    zones = detect_sr_zones(_flat_df(_ZIGZAG), lookback=1)

    assert active_sr_zones_at(zones, 5) == []               # hali hech biri tasdiqlanmagan
    assert len(active_sr_zones_at(zones, 6)) == 1           # support (conf 6)
    assert len(active_sr_zones_at(zones, 7)) == 2           # support + resistance


def test_strength_touch_based_and_bounded() -> None:
    zones = detect_sr_zones(_flat_df(_ZIGZAG), lookback=1, touch_saturation=6)
    for z in zones:
        assert 0.0 <= z.strength <= 1.0
        # 3 teginish / 6 to'yinish = 0.5
        assert z.strength == 0.5


def test_insufficient_data_returns_empty() -> None:
    # n < 2*lookback+1
    assert detect_sr_zones(_flat_df([10, 11, 12]), lookback=2) == []
    # bo'sh df
    index = pd.date_range("2024-01-01", periods=0, freq="D", tz="UTC")
    df_empty = pd.DataFrame(columns=_COLUMNS, index=index)
    assert detect_sr_zones(df_empty, lookback=1) == []


def test_nearest_resistance_above() -> None:
    zones = detect_sr_zones(_flat_df(_ZIGZAG), lookback=1)

    # index_pos 7 da resistance faol (bottom=112)
    res = nearest_resistance_above(zones, price=105.0, index_pos=7)
    assert res is not None and res.kind is SRZoneKind.RESISTANCE

    # narx zona ostida emas (115 > 112) -> None
    assert nearest_resistance_above(zones, price=115.0, index_pos=7) is None
    # resistance hali faol emas (bar 6)
    assert nearest_resistance_above(zones, price=105.0, index_pos=6) is None


def test_detect_sr_zones_no_lookahead_bias() -> None:
    """Kesilgan df'da `bar k`gacha tasdiqlangan zonalar to'liq df bilan bir xil
    band/touch_count/confirmed_index_pos berishi kerak (klasterlash xronologik)."""
    df_full = _flat_df(_ZIGZAG)
    zones_full = detect_sr_zones(df_full, lookback=1)

    for k in range(3, len(df_full)):
        active_full = active_sr_zones_at(zones_full, k)
        zones_trunc = detect_sr_zones(df_full.iloc[: k + 1], lookback=1)

        key = lambda z: (z.kind.name, z.bottom, z.top, z.touch_count, z.confirmed_index_pos)
        assert sorted(map(key, active_full)) == sorted(map(key, zones_trunc))
