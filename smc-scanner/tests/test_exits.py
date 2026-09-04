"""backtest/exits.py uchun testlar (qo'lda qurilgan sintetik df + TradeSetup, real tarmoqsiz).

Har bir modelning ikki fundamental talabi tekshiriladi: (1) engine.py'dagi mavjud fixed/trailing
mantiq bilan mos kelishi (adapter, qayta yozilmagan), (2) lookahead bias yo'qligi — kesish-invariant:
to'liq dataset natijasi qaror nuqtasigacha kesilgan dataset natijasi bilan bir xil bo'lishi kerak.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engine import _simulate_fixed_exit, _simulate_trailing_exit
from backtest.exits import (
    AtrExitConfig,
    AtrSLTPExit,
    FixedSLTPExit,
    StructureBreakExit,
    TrailingExitConfig,
    TrailingStopExit,
)
from smc.structure import detect_swings
from smc.market_structure import detect_structure_events
from smc.types import StructureState, TradeSetup
from smc.zones import compute_atr


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Har bir bar uchun aniq open/high/low/close berilgan DataFrame yasaydi."""
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    if "volume" not in df.columns:
        df["volume"] = 1000
    return df[["open", "high", "low", "close", "volume"]]


def _setup(entry_index_pos: int, entry: float, stop: float, target: float, ts: pd.Timestamp) -> TradeSetup:
    return TradeSetup(
        entry_ts=ts,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        direction=StructureState.BULLISH,
        entry_index_pos=entry_index_pos,
        reason="FVG",
    )


def _arrays(df: pd.DataFrame):
    return df["close"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy()


# ======================================================================
# Model A — FixedSLTPExit
# ======================================================================


def test_fixed_sl_tp_matches_engine_simulate_fixed_exit() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry bar
        {"open": 100, "high": 105, "low": 95, "close": 102},  # idx1 no hit
        {"open": 102, "high": 125, "low": 98, "close": 118},  # idx2 target hit (125>=120)
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=90.0, target=120.0, ts=df.index[0])
    closes, highs, lows = _arrays(df)

    expected = _simulate_fixed_exit(df, setup, closes, highs, lows, len(df))
    atr = compute_atr(df, 14)

    result = FixedSLTPExit().find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert (result.exit_index_pos, result.exit_price, result.exit_reason, result.min_low, result.running_high) == expected
    assert result.partial is None


def test_fixed_sl_tp_no_lookahead_bias() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 105, "low": 95, "close": 102},  # idx1 no hit
        {"open": 102, "high": 125, "low": 98, "close": 118},  # idx2 target hit
    ]
    df_full = _make_df(rows)
    df_truncated = df_full.iloc[:2]  # idx2 (chiqish bari) yo'q
    setup = _setup(0, entry=100.0, stop=90.0, target=120.0, ts=df_full.index[0])
    atr_full = compute_atr(df_full, 14)
    atr_trunc = compute_atr(df_truncated, 14)

    closes_f, highs_f, lows_f = _arrays(df_full)
    full = FixedSLTPExit().find_exit(setup, df_full, closes=closes_f, highs=highs_f, lows=lows_f, atr=atr_full)
    assert full.exit_reason == "target"
    assert full.exit_index_pos == 2

    closes_t, highs_t, lows_t = _arrays(df_truncated)
    truncated = FixedSLTPExit().find_exit(
        setup, df_truncated, closes=closes_t, highs=highs_t, lows=lows_t, atr=atr_trunc
    )
    assert truncated.exit_reason == "end_of_data"
    assert truncated.exit_index_pos == 1
    assert truncated.exit_price == pytest.approx(102.0)  # close[1]


# ======================================================================
# Model B — AtrSLTPExit
# ======================================================================


_ATR_ROWS = [
    {"open": 100, "high": 101, "low": 99, "close": 100},  # idx0
    {"open": 100, "high": 101, "low": 99, "close": 100},  # idx1
    {"open": 100, "high": 101, "low": 99, "close": 100},  # idx2
    {"open": 100, "high": 101, "low": 99, "close": 100},  # idx3 entry (atr_period=3 -> ATR[3]=2.0)
    {"open": 105, "high": 108, "low": 104, "close": 106},  # idx4 target hit if tp_mult=1 (100+1*2=102<=108)
    {"open": 106, "high": 107, "low": 90, "close": 92},  # idx5 stop hit if not exited already
]


def test_atr_sl_tp_uses_multiplier_not_original_stop() -> None:
    df = _make_df(_ATR_ROWS)
    # Original stop/target far away — ATR-derived levels (entry=100, ATR[3]=2.0,
    # sl_mult=1 -> stop=98, tp_mult=1 -> target=102) must be what's actually used.
    setup = _setup(3, entry=100.0, stop=1.0, target=999.0, ts=df.index[3])
    atr = compute_atr(df, 3)
    closes, highs, lows = _arrays(df)

    model = AtrSLTPExit(atr_period=3, sl_atr_multiplier=1.0, tp_atr_multiplier=1.0)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.exit_reason == "target"
    assert result.exit_price == pytest.approx(102.0)  # 100 + 1*ATR(2.0), NOT original target=999
    assert result.exit_index_pos == 4


def test_atr_sl_tp_warmup_falls_back_to_original_stop_target() -> None:
    df = _make_df(_ATR_ROWS)
    # entry_index_pos=0 -> ATR[0] is NaN (atr_period=3, warmup) -> fallback to setup's own stop/target.
    setup = _setup(0, entry=100.0, stop=90.0, target=101.0, ts=df.index[0])
    atr = compute_atr(df, 3)
    closes, highs, lows = _arrays(df)

    model = AtrSLTPExit(atr_period=3, sl_atr_multiplier=1.0, tp_atr_multiplier=1.0)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    # target=101 hit at idx1 (high=101>=101) using the ORIGINAL (fallback) target.
    assert result.exit_reason == "target"
    assert result.exit_price == pytest.approx(101.0)
    assert result.exit_index_pos == 1


def test_atr_sl_tp_no_lookahead_bias() -> None:
    df_full = _make_df(_ATR_ROWS)
    df_truncated = df_full.iloc[:4]  # idx4 (chiqish bari) yo'q
    setup = _setup(3, entry=100.0, stop=1.0, target=999.0, ts=df_full.index[3])
    atr_full = compute_atr(df_full, 3)
    atr_trunc = compute_atr(df_truncated, 3)

    model = AtrSLTPExit(atr_period=3, sl_atr_multiplier=1.0, tp_atr_multiplier=1.0)

    closes_f, highs_f, lows_f = _arrays(df_full)
    full = model.find_exit(setup, df_full, closes=closes_f, highs=highs_f, lows=lows_f, atr=atr_full)
    assert full.exit_reason == "target"
    assert full.exit_index_pos == 4

    closes_t, highs_t, lows_t = _arrays(df_truncated)
    truncated = model.find_exit(
        setup, df_truncated, closes=closes_t, highs=highs_t, lows=lows_t, atr=atr_trunc
    )
    assert truncated.exit_reason == "end_of_data"
    assert truncated.exit_index_pos == 3
    assert truncated.exit_price == pytest.approx(100.0)  # close[3]


# ======================================================================
# Model C — TrailingStopExit
# ======================================================================

# Xuddi tests/test_backtest_engine.py::_TRAILING_ROWS bilan bir xil (parity uchun).
_TRAILING_ROWS = [
    {"open": 100, "high": 101, "low": 99, "close": 100},  # idx0 entry
    {"open": 100, "high": 101, "low": 99, "close": 101},  # idx1
    {"open": 101, "high": 102, "low": 100, "close": 102},  # idx2
    {"open": 102, "high": 103, "low": 101, "close": 103},  # idx3
    {"open": 103, "high": 104, "low": 102, "close": 103},  # idx4
    {"open": 103, "high": 103.5, "low": 99, "close": 100},  # idx5 stop buziladi
]


def test_trailing_stop_matches_engine_when_activation_zero() -> None:
    df = _make_df(_TRAILING_ROWS)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df.index[0])
    atr = compute_atr(df, 3)
    closes, highs, lows = _arrays(df)

    expected = _simulate_trailing_exit(df, setup, atr, closes, highs, lows, len(df), 1.0)
    model = TrailingStopExit(atr_period=3, trail_atr_multiplier=1.0, activation_r=0.0)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert (result.exit_index_pos, result.exit_price, result.exit_reason, result.min_low, result.running_high) == expected


def test_trailing_stop_activation_r_delays_ratchet() -> None:
    # Price pushes to +0.5R (high=105 -> (105-100)/10=0.5R) then pulls back through the
    # ORIGINAL stop (90). With activation_r=1.0 the trail must never have ratcheted.
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 105, "low": 99, "close": 104},  # idx1 +0.5R high, below activation
        {"open": 104, "high": 104, "low": 89, "close": 90},  # idx2 original stop (90) hit
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df.index[0])
    atr = compute_atr(df, 2)
    closes, highs, lows = _arrays(df)

    model = TrailingStopExit(atr_period=2, trail_atr_multiplier=1.0, activation_r=1.0)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.exit_price == pytest.approx(90.0)
    assert result.exit_reason == "trailing_stop"
    assert result.exit_index_pos == 2


def test_trailing_stop_no_lookahead_bias() -> None:
    df_full = _make_df(_TRAILING_ROWS)
    df_truncated = df_full.iloc[:5]  # idx5 (chiqish bari) yo'q
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df_full.index[0])
    atr_full = compute_atr(df_full, 3)
    atr_trunc = compute_atr(df_truncated, 3)

    model = TrailingStopExit(atr_period=3, trail_atr_multiplier=1.0, activation_r=0.0)

    closes_t, highs_t, lows_t = _arrays(df_truncated)
    truncated = model.find_exit(
        setup, df_truncated, closes=closes_t, highs=highs_t, lows=lows_t, atr=atr_trunc
    )
    assert truncated.exit_reason == "end_of_data"
    assert truncated.exit_index_pos == 4
    assert truncated.exit_price == pytest.approx(103.0)  # close[4]


# ======================================================================
# Model D — StructureBreakExit
# ======================================================================

# lookback=2. idx3 = swing HIGH (110), confirmed at idx5. idx6: close=115 breaks it ->
# bootstrap BULLISH (state None->BULLISH, NO event, active_high consumed). idx9 = swing
# LOW (90), confirmed at idx11 (=9+lookback). idx12: close=82 breaks it -> CHoCH BEARISH
# event, index_pos=12 (the CONFIRMING bar), broken_swing_index_pos=9 (the raw swing bar).
# This is exactly the lookahead trap the spec's test targets: exit must fire at 12, never
# at 9 (broken swing bar) and never before 12 (confirmation bar).
_STRUCTURE_ROWS = [
    {"open": 100, "high": 100.5, "low": 99.5, "close": 100},  # idx0 entry bar
    {"open": 100, "high": 101, "low": 99, "close": 101},  # idx1
    {"open": 101, "high": 102, "low": 100, "close": 102},  # idx2
    {"open": 102, "high": 110, "low": 101, "close": 103},  # idx3 swing HIGH pivot
    {"open": 103, "high": 103, "low": 100, "close": 101},  # idx4
    {"open": 101, "high": 104, "low": 99, "close": 100},  # idx5 -> high confirmed here
    {"open": 100, "high": 116, "low": 99, "close": 115},  # idx6 close breaks 110 -> bootstrap BULLISH
    {"open": 115, "high": 115.5, "low": 110, "close": 111},  # idx7
    {"open": 111, "high": 112, "low": 108, "close": 109},  # idx8
    {"open": 109, "high": 109.5, "low": 90, "close": 95},  # idx9 swing LOW pivot
    {"open": 95, "high": 100, "low": 95, "close": 98},  # idx10
    {"open": 98, "high": 100, "low": 96, "close": 97},  # idx11 -> low confirmed here
    {"open": 97, "high": 98, "low": 80, "close": 82},  # idx12 close breaks 90 -> CHoCH BEARISH
    {"open": 82, "high": 83, "low": 78, "close": 79},  # idx13 filler
    {"open": 79, "high": 80, "low": 76, "close": 77},  # idx14 filler
]


def test_structure_break_exits_on_confirming_bar_not_broken_swing_bar() -> None:
    df = _make_df(_STRUCTURE_ROWS)
    setup = _setup(0, entry=100.0, stop=50.0, target=9999.0, ts=df.index[0])
    atr = compute_atr(df, 14)
    closes, highs, lows = _arrays(df)

    # Sanity: confirm the fixture actually produces the intended bearish event before
    # trusting the model's behavior against it.
    swings = detect_swings(df, lookback=2)
    events = detect_structure_events(df, swings)
    bearish = [e for e in events if e.direction.name == "BEARISH"]
    assert len(bearish) == 1
    assert bearish[0].index_pos == 12
    assert bearish[0].broken_swing_index_pos == 9

    model = StructureBreakExit(lookback=2)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.exit_reason == "structure_break"
    assert result.exit_index_pos == 12  # the CONFIRMING bar
    assert result.exit_index_pos != 9  # NOT the broken swing's raw bar
    assert result.exit_price == pytest.approx(82.0)  # close[12]


def test_structure_break_no_lookahead_bias() -> None:
    df_full = _make_df(_STRUCTURE_ROWS)
    df_truncated = df_full.iloc[:12]  # idx12 (the confirming/break bar) excluded
    setup = _setup(0, entry=100.0, stop=50.0, target=9999.0, ts=df_full.index[0])
    atr_trunc = compute_atr(df_truncated, 14)
    closes_t, highs_t, lows_t = _arrays(df_truncated)

    model = StructureBreakExit(lookback=2)
    truncated = model.find_exit(
        setup, df_truncated, closes=closes_t, highs=highs_t, lows=lows_t, atr=atr_trunc
    )

    # Without bar 12, the break is not yet observable -- must NOT fire early.
    assert truncated.exit_reason == "end_of_data"
    assert truncated.exit_index_pos == 11
    assert truncated.exit_price == pytest.approx(97.0)  # close[11]


def test_structure_break_end_of_data_when_no_bearish_event() -> None:
    # Pure uptrend -- swing highs keep forming but no swing low is ever confirmed and
    # broken bearishly, so no BEARISH structure event can ever fire.
    rows = [
        {"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i} for i in range(12)
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=50.0, target=9999.0, ts=df.index[0])
    atr = compute_atr(df, 14)
    closes, highs, lows = _arrays(df)

    model = StructureBreakExit(lookback=2)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.exit_reason == "end_of_data"
    assert result.exit_index_pos == len(df) - 1


# ======================================================================
# Model F — TimeBasedExit
# ======================================================================

from backtest.exits import TimeBasedExit  # noqa: E402


def test_time_exit_exits_at_entry_plus_max_hold_bars_close() -> None:
    rows = [{"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i} for i in range(10)]
    df = _make_df(rows)
    setup = _setup(2, entry=102.0, stop=90.0, target=999.0, ts=df.index[2])
    atr = compute_atr(df, 14)
    closes, highs, lows = _arrays(df)

    model = TimeBasedExit(max_hold_bars=3)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.exit_reason == "time_exit"
    assert result.exit_index_pos == 5  # entry_index_pos(2) + max_hold_bars(3)
    assert result.exit_price == pytest.approx(closes[5])
    assert result.partial is None


def test_time_exit_end_of_data_when_max_hold_exceeds_available_bars() -> None:
    rows = [{"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i} for i in range(6)]
    df = _make_df(rows)
    setup = _setup(2, entry=102.0, stop=90.0, target=999.0, ts=df.index[2])
    atr = compute_atr(df, 14)
    closes, highs, lows = _arrays(df)

    model = TimeBasedExit(max_hold_bars=10)  # far exceeds remaining bars
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.exit_reason == "end_of_data"
    assert result.exit_index_pos == len(df) - 1
    assert result.exit_price == pytest.approx(closes[-1])


def test_time_exit_no_lookahead_bias() -> None:
    rows = [{"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i} for i in range(10)]
    df_full = _make_df(rows)
    df_truncated = df_full.iloc[:5]  # bar 5 (the would-be exit bar) excluded
    setup = _setup(2, entry=102.0, stop=90.0, target=999.0, ts=df_full.index[2])
    atr_full = compute_atr(df_full, 14)
    atr_trunc = compute_atr(df_truncated, 14)

    model = TimeBasedExit(max_hold_bars=3)

    closes_f, highs_f, lows_f = _arrays(df_full)
    full = model.find_exit(setup, df_full, closes=closes_f, highs=highs_f, lows=lows_f, atr=atr_full)
    assert full.exit_index_pos == 5

    closes_t, highs_t, lows_t = _arrays(df_truncated)
    truncated = model.find_exit(
        setup, df_truncated, closes=closes_t, highs=highs_t, lows=lows_t, atr=atr_trunc
    )
    assert truncated.exit_reason == "end_of_data"
    assert truncated.exit_index_pos == 4
    assert truncated.exit_price == pytest.approx(closes_t[-1])


# ======================================================================
# Model E — PartialTpTrailingExit
# ======================================================================

from backtest.exits import PartialTpTrailingExit, build_exit_model, EXIT_MODEL_KEYS  # noqa: E402


def test_partial_tp_triggers_at_configured_r_with_correct_fraction() -> None:
    # entry=100, stop=90 -> risk=10, partial_tp_r=1.0 -> partial_level=110.
    rows2 = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 112, "low": 99, "close": 111},  # idx1 hits +1R (110)
        {"open": 111, "high": 112, "low": 108, "close": 111},  # idx2
        {"open": 111, "high": 112, "low": 108, "close": 111},  # idx3
        {"open": 111, "high": 112, "low": 60, "close": 65},  # idx4 crash -- trailing stop hit
    ]
    df2 = _make_df(rows2)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df2.index[0])
    atr2 = compute_atr(df2, 2)
    closes2, highs2, lows2 = _arrays(df2)

    model = PartialTpTrailingExit(partial_tp_r=1.0, partial_size=0.5, trail_atr_multiplier=1.0, atr_period=2)
    result = model.find_exit(setup, df2, closes=closes2, highs=highs2, lows=lows2, atr=atr2)

    assert result.partial is not None
    assert result.partial.fraction == pytest.approx(0.5)
    assert result.partial.price == pytest.approx(110.0)
    assert result.partial.reason == "partial_tp"
    assert result.partial.index_pos == 1


def test_partial_tp_full_stop_before_partial_has_no_partial_leg() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 101, "low": 89, "close": 90},  # idx1 stop (90) hit BEFORE +1R (110)
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df.index[0])
    atr = compute_atr(df, 2)
    closes, highs, lows = _arrays(df)

    model = PartialTpTrailingExit(partial_tp_r=1.0, partial_size=0.5, trail_atr_multiplier=1.0, atr_period=2)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.partial is None
    assert result.exit_reason == "stop"
    assert result.exit_price == pytest.approx(90.0)


def test_partial_tp_trailing_exits_final_leg_correctly() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 112, "low": 99, "close": 111},  # idx1 hits +1R (110), running_high>=112
        {"open": 111, "high": 113, "low": 108, "close": 111},  # idx2 new high 113
        {"open": 111, "high": 113, "low": 108, "close": 111},  # idx3
        {"open": 111, "high": 112, "low": 60, "close": 65},  # idx4 trailing stop hit
    ]
    df = _make_df(rows)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df.index[0])
    atr = compute_atr(df, 2)
    closes, highs, lows = _arrays(df)

    model = PartialTpTrailingExit(partial_tp_r=1.0, partial_size=0.5, trail_atr_multiplier=1.0, atr_period=2)
    result = model.find_exit(setup, df, closes=closes, highs=highs, lows=lows, atr=atr)

    assert result.partial is not None
    assert result.partial.index_pos == 1
    assert result.exit_reason == "trailing_stop"
    assert result.exit_index_pos == 4


def test_partial_tp_trailing_no_lookahead_bias() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 112, "low": 99, "close": 111},  # idx1 hits +1R
        {"open": 111, "high": 113, "low": 108, "close": 111},  # idx2
        {"open": 111, "high": 113, "low": 108, "close": 111},  # idx3
        {"open": 111, "high": 112, "low": 60, "close": 65},  # idx4 trailing stop hit
    ]
    df_full = _make_df(rows)
    atr_full = compute_atr(df_full, 2)
    setup = _setup(0, entry=100.0, stop=90.0, target=999.0, ts=df_full.index[0])
    model = PartialTpTrailingExit(partial_tp_r=1.0, partial_size=0.5, trail_atr_multiplier=1.0, atr_period=2)

    # Truncate BEFORE the partial trigger bar (idx1) -- must not observe the partial yet.
    df_pre = df_full.iloc[:1]
    atr_pre = compute_atr(df_pre, 2)
    closes_p, highs_p, lows_p = _arrays(df_pre)
    pre = model.find_exit(setup, df_pre, closes=closes_p, highs=highs_p, lows=lows_p, atr=atr_pre)
    assert pre.exit_reason == "end_of_data"
    assert pre.partial is None

    # Truncate BEFORE the final trailing-stop bar (idx4) -- partial observable, final not yet.
    df_mid = df_full.iloc[:4]
    atr_mid = compute_atr(df_mid, 2)
    closes_m, highs_m, lows_m = _arrays(df_mid)
    mid = model.find_exit(setup, df_mid, closes=closes_m, highs=highs_m, lows=lows_m, atr=atr_mid)
    assert mid.exit_reason == "end_of_data"
    assert mid.partial is not None
    assert mid.partial.index_pos == 1

    closes_f, highs_f, lows_f = _arrays(df_full)
    full = model.find_exit(setup, df_full, closes=closes_f, highs=highs_f, lows=lows_f, atr=atr_full)
    assert full.exit_reason == "trailing_stop"
    assert full.exit_index_pos == 4
    assert full.partial.index_pos == 1  # partial leg identical between mid/full


# ======================================================================
# Registry
# ======================================================================


def test_exit_model_registry_builds_all_six_letters() -> None:
    for key in EXIT_MODEL_KEYS:
        model = build_exit_model(key)
        assert hasattr(model, "find_exit")
        assert hasattr(model, "name")
        assert isinstance(model.name, str) and model.name
