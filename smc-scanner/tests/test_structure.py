"""smc/structure.py uchun testlar (qo'lda hisoblangan sintetik price seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd

from smc.structure import detect_swings
from smc.types import SwingKind, SwingLabel


def _make_df(prices: list[float]) -> pd.DataFrame:
    """Berilgan narxlar ro'yxatidan sodda OHLCV DataFrame yasaydi (open=high=low=close)."""
    index = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000] * len(prices),
        },
        index=index,
    )


# Uptrend zigzag — qo'lda tekshirilgan: swing high'lar i=3(13), i=14(14);
# swing low'lar i=8(8), i=18(10). Boshqa barcha nuqtalar strict >/< shartini
# qanoatlantirmaydi yoki yetarli kontekstga ega emas.
_ZIGZAG = [10, 11, 12, 13, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13, 14, 13, 12, 11, 10, 11, 12]


def test_detect_swings_finds_expected_points() -> None:
    df = _make_df(_ZIGZAG)
    swings = detect_swings(df, lookback=2)

    assert [s.index_pos for s in swings] == [3, 8, 14, 18]
    assert [s.kind for s in swings] == [
        SwingKind.HIGH,
        SwingKind.LOW,
        SwingKind.HIGH,
        SwingKind.LOW,
    ]
    assert [s.price for s in swings] == [13, 8, 14, 10]


def test_detect_swings_labels_hh_hl_sequence() -> None:
    df = _make_df(_ZIGZAG)
    swings = detect_swings(df, lookback=2)

    assert swings[0].label is None  # o'sha turdagi (HIGH) birinchi swing
    assert swings[1].label is None  # o'sha turdagi (LOW) birinchi swing
    assert swings[2].label is SwingLabel.HH  # 14 > 13
    assert swings[3].label is SwingLabel.HL  # 10 > 8


def test_detect_swings_no_lookahead_bias() -> None:
    """Yetarli o'ng kontekst bo'lmagan swing (masalan oxirgi barlar) qaytmasligi kerak."""
    df_full = _make_df(_ZIGZAG)
    df_truncated = df_full.iloc[:15]  # i=14 uchun o'ng tomonda 2 ta bar qolmaydi

    swings_full = detect_swings(df_full, lookback=2)
    swings_truncated = detect_swings(df_truncated, lookback=2)

    assert any(s.index_pos == 14 for s in swings_full)
    assert all(s.index_pos <= 12 for s in swings_truncated)
    assert len(swings_truncated) == 2


def test_detect_swings_ignores_equal_highs() -> None:
    """Qo'shni teng high'lar qat'iy `>` shartini qanoatlantirmagani uchun swing bo'lmaydi."""
    prices = [1, 2, 4, 4, 2, 1]
    df = _make_df(prices)

    swings = detect_swings(df, lookback=1)

    assert swings == []


def test_detect_swings_lookback_affects_sensitivity() -> None:
    """Kattaroq lookback -> kamroq va kattaroq (muhimroq) swing'lar."""
    prices = [5, 8, 6, 9, 5, 3, 6, 4, 7, 3]
    df = _make_df(prices)

    swings_small = detect_swings(df, lookback=1)
    swings_large = detect_swings(df, lookback=2)

    assert len(swings_small) > len(swings_large)
    assert [s.price for s in swings_large] == [9, 3]


def test_detect_swings_insufficient_data_returns_empty() -> None:
    """Bar soni 2*lookback+1 dan kam bo'lsa, crash bo'lmasdan bo'sh ro'yxat qaytishi kerak."""
    df = _make_df([1, 2, 3])  # lookback=2 uchun kamida 5 bar kerak

    assert detect_swings(df, lookback=2) == []
