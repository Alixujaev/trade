"""smc/signal.py uchun testlar (sintetik OHLC seriya, real tarmoqsiz).

Test ma'lumotlari Phase 3'ning tekshirilgan "mirrored" bearish->bullish CHoCH
seriyasiga asoslangan (`_TREND_REVERSAL`ning 22-v ko'zgusi — bearish BOS'lar,
keyin bullish CHoCH idx=11'da), so'ngra unga real OHLC bar'lar bilan
displacement+FVG/OB+retest davomi qo'shilgan. Barcha aniq raqamlar generate_signals
va uning ichidagi (allaqachon alohida sinalgan: detect_swings, detect_structure_events,
detect_fvgs/detect_order_blocks, compute_atr) funksiyalari orqali hisoblanib,
haqiqiy natijalar bilan tasdiqlangan — bu integratsiya testi ularning TO'G'RI
BOG'LANGANINI tekshiradi.

MUHIM: generate_signals doim ATR_PERIOD=14 (default)ni ishlatadi (atr_period
parametri yo'q, faqat mult bor) — shuning uchun HECH QANDAY zona bar 13'dan
oldin hosil bo'la olmaydi (ATR shu bargacha NaN). Bu sabab zona-recency
chegarasini (`created_index_pos >= last_choch_index_pos`) CHoCH bar13'dan oldin
sodir bo'lgan holatda alohida tekshirib bo'lmaydi — chegara mantig'i
smc/signal.py'ning docstring'ida va kod review'da asoslangan.
"""

from __future__ import annotations

import pandas as pd
import pytest

from smc.signal import generate_signals

# Bearish BOS'lar, keyin bullish CHoCH idx=11'da (level=5) — Phase 3'da tekshirilgan.
_TREND_REVERSAL = [10, 12, 11, 14, 13, 16, 15, 18, 17, 20, 18, 15, 12]
_MIRRORED_BEARISH_TO_BULLISH = [22 - v for v in _TREND_REVERSAL]

# idx13: bullish displacement; idx14: gap tasdiqlaydi -> FVG (top=15.6,bottom=10.0,
# created=14); idx15: hali retest yo'q; idx16: retest -> signal.
_RETEST_ROWS = [
    {"open": 10, "high": 15.5, "low": 9.8, "close": 15},
    {"open": 16, "high": 17, "low": 15.6, "close": 16.5},
    {"open": 16.5, "high": 18, "low": 16, "close": 17.5},
    {"open": 17.5, "high": 18, "low": 14, "close": 16},
]


def _make_df(values: list[float] | None = None, extra_rows: list[dict] | None = None) -> pd.DataFrame:
    values = values if values is not None else _MIRRORED_BEARISH_TO_BULLISH
    extra_rows = extra_rows if extra_rows is not None else []
    rows = [{"open": v, "high": v, "low": v, "close": v} for v in values] + extra_rows
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[["open", "high", "low", "close", "volume"]]


def test_end_to_end_bullish_choch_then_fvg_retest() -> None:
    """To'liq ssenariy: bearish struktura -> bullish CHoCH -> displacement -> FVG -> retest -> signal."""
    df = _make_df(extra_rows=_RETEST_ROWS)

    signals = generate_signals(df, lookback=1, mult=1.0)

    assert len(signals) == 1
    s = signals[0]
    assert s.entry_index_pos == 16
    assert s.reason == "FVG"
    # entry = min(zona.top=15.6, shu bar high=18) = 15.6
    assert s.entry_price == pytest.approx(15.6)
    # stop = zona.bottom(10.0) - STOP_BUFFER_ATR_MULT(0.1) * ATR[16](default period=14)
    assert s.stop_price == pytest.approx(9.737857142857143)
    # mos swing high (>15.6) topilmadi -> 2R fallback: entry + 2.0*(entry-stop)
    assert s.target_price == pytest.approx(27.324285714285715)


def test_entry_price_capped_at_bar_high_when_below_zone_top() -> None:
    """Retest bar high'i zona top'iga yetmasa, entry narxi top'ga EMAS, shu bar high'iga cheklanadi."""
    rows = _RETEST_ROWS[:3] + [
        {"open": 14.5, "high": 15.0, "low": 13, "close": 14.8},  # high(15.0) < zona top(15.6)
    ]
    df = _make_df(extra_rows=rows)

    signals = generate_signals(df, lookback=1, mult=1.0)

    assert len(signals) == 1
    assert signals[0].entry_price == pytest.approx(15.0)  # zona.top(15.6) EMAS
    assert signals[0].entry_price < 15.6


def test_multiple_signals_can_occur_while_structure_stays_bullish() -> None:
    """generate_signals pozitsiya-eksklyuzivligini qo'llamaydi — bir nechta signal
    xronologik tartibda qaytishi mumkin (cheklov faqat backtest.engine'da)."""
    rows = _RETEST_ROWS + [
        {"open": 16, "high": 20, "low": 15.9, "close": 19.5},  # rally davom etadi
        {"open": 19.5, "high": 20, "low": 17, "close": 17.5},  # pastga tortiladi -> 2-OB retest
    ]
    df = _make_df(extra_rows=rows)

    signals = generate_signals(df, lookback=1, mult=1.0)

    assert len(signals) == 2
    assert [s.entry_index_pos for s in signals] == [16, 18]
    assert signals[0].reason == "FVG"
    assert signals[1].reason == "ORDER_BLOCK"


def test_no_lookahead_bias() -> None:
    """Kesilgan (truncated) data — retest bar hali yo'q bo'lsa — signal ham yo'q bo'lishi kerak."""
    df_full = _make_df(extra_rows=_RETEST_ROWS)

    signals_full = generate_signals(df_full, lookback=1, mult=1.0)
    assert len(signals_full) == 1

    df_including_retest = df_full.iloc[:17]  # idx16 (retest bar) kiritilgan — to'liq bilan bir xil
    signals_included = generate_signals(df_including_retest, lookback=1, mult=1.0)
    assert len(signals_included) == 1
    assert signals_included[0].entry_index_pos == signals_full[0].entry_index_pos
    assert signals_included[0].entry_price == pytest.approx(signals_full[0].entry_price)

    df_excluding_retest = df_full.iloc[:16]  # idx16 chiqarib tashlangan
    signals_excluded = generate_signals(df_excluding_retest, lookback=1, mult=1.0)
    assert signals_excluded == []


def test_empty_or_insufficient_data_returns_empty_no_crash() -> None:
    df_short = _make_df(values=[10, 11, 12])
    assert generate_signals(df_short) == []

    index = pd.date_range("2024-01-01", periods=0, freq="D", tz="UTC")
    df_empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=index)
    assert generate_signals(df_empty) == []
