"""smc/structure.py va smc/market_structure.py uchun testlar (sintetik price seriya, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd

from smc.market_structure import current_structure_state, detect_structure_events
from smc.structure import detect_swings
from smc.types import (
    StructureEventType,
    StructureState,
    SwingKind,
    SwingLabel,
    SwingPoint,
)


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


def _make_full_df(rows: list[dict]) -> pd.DataFrame:
    """Har bir bar uchun aniq open/high/low/close/volume berilgan DataFrame yasaydi."""
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    return pd.DataFrame(rows, index=index)[["open", "high", "low", "close", "volume"]]


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


# --- BOS/CHoCH (smc/market_structure.py) testlari ---

# Toza bullish seriya (lookback=1): swing'lar i=1(H12),i=2(L11),i=3(H14,HH),
# i=4(L13,HL),i=5(H16,HH),i=6(L15,HL),i=7(H18,HH),i=8(L17,HL). Bootstrap i=3'da
# 12 darajasining break'i orqali (silent), keyin 14/16/18 navbat bilan close bilan
# buziladi -> 3 ta bullish BOS, CHoCH yo'q.
_BULLISH_SERIES = [10, 12, 11, 14, 13, 16, 15, 18, 17, 20]

# Uptrend -> reversal (lookback=1): yuqoridagi bilan bir xil, davomida yana
# pasayib, oxirgi HL(17)ni buzadi -> bearish CHoCH.
_TREND_REVERSAL = [10, 12, 11, 14, 13, 16, 15, 18, 17, 20, 18, 15, 12]


def test_detect_structure_events_pure_bullish_only_bos() -> None:
    df = _make_df(_BULLISH_SERIES)
    swings = detect_swings(df, lookback=1)

    events = detect_structure_events(df, swings)

    assert [e.event_type for e in events] == [StructureEventType.BOS] * 3
    assert [e.direction for e in events] == [StructureState.BULLISH] * 3
    assert [e.broken_level for e in events] == [14, 16, 18]
    assert [e.index_pos for e in events] == [5, 7, 9]


def test_detect_structure_events_uptrend_then_bearish_choch() -> None:
    df = _make_df(_TREND_REVERSAL)
    swings = detect_swings(df, lookback=1)

    events = detect_structure_events(df, swings)

    assert [e.event_type for e in events] == [
        StructureEventType.BOS,
        StructureEventType.BOS,
        StructureEventType.BOS,
        StructureEventType.CHOCH,
    ]
    assert [e.direction for e in events] == [
        StructureState.BULLISH,
        StructureState.BULLISH,
        StructureState.BULLISH,
        StructureState.BEARISH,
    ]
    assert [e.broken_level for e in events] == [14, 16, 18, 17]
    assert [e.index_pos for e in events] == [5, 7, 9, 11]


def test_detect_structure_events_downtrend_then_bullish_choch() -> None:
    """Yuqoridagi seriyaning oynadagi aksi — bearish BOS'lar, keyin bullish CHoCH."""
    mirrored = [22 - v for v in _TREND_REVERSAL]
    df = _make_df(mirrored)
    swings = detect_swings(df, lookback=1)

    events = detect_structure_events(df, swings)

    assert [e.event_type for e in events] == [
        StructureEventType.BOS,
        StructureEventType.BOS,
        StructureEventType.BOS,
        StructureEventType.CHOCH,
    ]
    assert [e.direction for e in events] == [
        StructureState.BEARISH,
        StructureState.BEARISH,
        StructureState.BEARISH,
        StructureState.BULLISH,
    ]
    assert [e.broken_level for e in events] == [8, 6, 4, 5]
    assert [e.index_pos for e in events] == [5, 7, 9, 11]


def test_break_requires_close_not_wick() -> None:
    """Wick level'dan yuqoriga chiqishi break EMAS — faqat close hisoblanadi.

    Faqat HIGH swing'lar ishlatiladi (LOW qatnashmaydi), shunda faqat close-vs-wick
    xatti-harakati sinaladi — boshqa hech qanday level bilan aralashmaydi.
    """
    rows = [
        {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 100},  # idx0 swing HIGH
        {"open": 15, "high": 15, "low": 15, "close": 15, "volume": 100},  # idx1 swing HIGH (bootstrap break + HH)
        {"open": 14, "high": 16, "low": 13, "close": 14, "volume": 100},  # idx2 wick, close'siz break
        {"open": 15, "high": 17, "low": 15, "close": 17, "volume": 100},  # idx3 haqiqiy close break
    ]
    df = _make_full_df(rows)
    # Bu qo'lda yasalgan swing'lar uchun confirmation lag muhim emas — soddalik
    # uchun confirmed_index_pos == index_pos deb olindi (o'z barida "ma'lum").
    swings = [
        SwingPoint(df.index[0], 10.0, SwingKind.HIGH, None, 0, 0),
        SwingPoint(df.index[1], 15.0, SwingKind.HIGH, SwingLabel.HH, 1, 1),
    ]

    events = detect_structure_events(df, swings)

    assert len(events) == 1
    assert events[0].index_pos == 3
    assert events[0].broken_level == 15.0
    assert events[0].event_type is StructureEventType.BOS


def test_broken_level_is_consumed_only_once() -> None:
    """Buzilgan level qayta trigger bermasligi kerak — yangi swing kelmaguncha."""
    rows = [
        {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 100},  # idx0 swing HIGH
        {"open": 12, "high": 12, "low": 12, "close": 12, "volume": 100},  # idx1 bootstrap break (silent)
        {"open": 14, "high": 14, "low": 14, "close": 14, "volume": 100},  # idx2 swing HIGH (HH)
        {"open": 16, "high": 16, "low": 16, "close": 16, "volume": 100},  # idx3 haqiqiy break -> BOS
        {"open": 20, "high": 20, "low": 20, "close": 20, "volume": 100},  # idx4 active_high yo'q -> event yo'q
        {"open": 25, "high": 25, "low": 25, "close": 25, "volume": 100},  # idx5 hamon event yo'q
    ]
    df = _make_full_df(rows)
    swings = [
        SwingPoint(df.index[0], 10.0, SwingKind.HIGH, None, 0, 0),
        SwingPoint(df.index[2], 14.0, SwingKind.HIGH, SwingLabel.HH, 2, 2),
    ]

    events = detect_structure_events(df, swings)

    assert len(events) == 1
    assert events[0].index_pos == 3
    assert events[0].broken_level == 14.0


def test_simultaneous_high_and_low_break_both_recorded() -> None:
    """Bir candle'da HIGH va LOW level ikkalasi ham buzilsa, ikkalasi ham qayd etilishi kerak.

    Sun'iy holat: LOW(103) narxi HIGH(100)dan yuqorida — real OHLC uchun g'ayrioddiy,
    lekin detect_structure_events faqat 'close'ni o'qiydi, shuning uchun bu yerda muammo yo'q.
    """
    rows = [
        {"open": 50, "high": 50, "low": 50, "close": 50, "volume": 100},  # idx0 swing HIGH
        {"open": 55, "high": 55, "low": 55, "close": 55, "volume": 100},  # idx1 bootstrap break (silent)
        {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 100},  # idx2 swing HIGH (HH)
        {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 100},  # idx3 swing LOW (HL)
        {"open": 101, "high": 101, "low": 101, "close": 101, "volume": 100},  # idx4 ikkala level ham buziladi
    ]
    df = _make_full_df(rows)
    swings = [
        SwingPoint(df.index[0], 50.0, SwingKind.HIGH, None, 0, 0),
        SwingPoint(df.index[1], 40.0, SwingKind.LOW, None, 1, 1),
        SwingPoint(df.index[2], 100.0, SwingKind.HIGH, SwingLabel.HH, 2, 2),
        SwingPoint(df.index[3], 103.0, SwingKind.LOW, SwingLabel.HL, 3, 3),
    ]

    events = detect_structure_events(df, swings)

    assert len(events) == 2
    assert events[0].event_type is StructureEventType.BOS
    assert events[0].direction is StructureState.BULLISH
    assert events[0].broken_level == 100.0
    assert events[1].event_type is StructureEventType.CHOCH
    assert events[1].direction is StructureState.BEARISH
    assert events[1].broken_level == 103.0
    assert events[0].index_pos == events[1].index_pos == 4


def test_detect_structure_events_no_lookahead_bias() -> None:
    """Kesilgan (truncated) data'dagi natija to'liq data natijasining prefiksi bo'lishi kerak."""
    df_full = _make_df(_TREND_REVERSAL)
    swings_full = detect_swings(df_full, lookback=1)
    full_events = detect_structure_events(df_full, swings_full)

    df_truncated = df_full.iloc[:11]  # CHoCH break candle'i (i=11) bu yerda yo'q
    swings_truncated = detect_swings(df_truncated, lookback=1)
    truncated_events = detect_structure_events(df_truncated, swings_truncated)

    assert len(full_events) == 4
    assert truncated_events == full_events[:3]


def test_detect_structure_events_empty_or_insufficient_swings() -> None:
    df = _make_df([10, 11, 12])
    assert detect_structure_events(df, []) == []

    df2 = _make_df([10, 11, 12, 13, 14])
    single_swing = [SwingPoint(df2.index[2], 12.0, SwingKind.HIGH, None, 2, 2)]
    assert detect_structure_events(df2, single_swing) == []


def test_current_structure_state_tracks_bootstrap_without_events() -> None:
    """Bootstrap event chiqarmasa ham, joriy state to'g'ri kuzatilishi kerak."""
    df_partial = _make_df(_TREND_REVERSAL).iloc[:5]
    swings_partial = detect_swings(df_partial, lookback=1)

    assert detect_structure_events(df_partial, swings_partial) == []
    assert current_structure_state(df_partial, swings_partial) is StructureState.BULLISH
