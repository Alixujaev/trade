"""backtest/window.py uchun testlar (sana bo'yicha kesish + lookahead yo'qligi)."""

from __future__ import annotations

import pandas as pd

from backtest.window import slice_date_range
from smc.signal import generate_signals


def _make_df(values: list[float]) -> pd.DataFrame:
    """Sodda OHLCV DataFrame (open=high=low=close), 2024-01-01'dan boshlab kunlik."""
    index = pd.date_range("2024-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": values, "high": values, "low": values, "close": values, "volume": [1000] * len(values)},
        index=index,
    )


def test_slice_date_range_both_bounds_inclusive() -> None:
    df = _make_df(list(range(10)))  # 2024-01-01 .. 2024-01-10

    sliced = slice_date_range(df, "2024-01-03", "2024-01-06")

    assert len(sliced) == 4
    assert sliced.index[0] == pd.Timestamp("2024-01-03", tz="UTC")  # start chegarasi kiritilgan
    assert sliced.index[-1] == pd.Timestamp("2024-01-06", tz="UTC")  # end chegarasi kiritilgan


def test_slice_date_range_only_start_or_only_end() -> None:
    df = _make_df(list(range(10)))

    only_start = slice_date_range(df, "2024-01-08", None)
    assert len(only_start) == 3  # 08,09,10

    only_end = slice_date_range(df, None, "2024-01-03")
    assert len(only_end) == 3  # 01,02,03


def test_slice_date_range_no_bounds_returns_unchanged() -> None:
    df = _make_df(list(range(5)))

    result = slice_date_range(df, None, None)

    pd.testing.assert_frame_equal(result, df)


def test_slice_date_range_window_outside_data_returns_empty() -> None:
    df = _make_df(list(range(5)))  # 2024-01-01..05

    result = slice_date_range(df, "2030-01-01", "2030-02-01")

    assert result.empty


# --- Lookahead: sana bo'yicha kesish pozitsion kesishga TENG bo'lishi kerak ---
# Phase 5'ning tekshirilgan ssenariysi: bearish struktura -> bullish CHoCH (idx=11) ->
# displacement -> FVG (created=14) -> retest (idx=16) -> bitta signal.
_TREND_REVERSAL = [10, 12, 11, 14, 13, 16, 15, 18, 17, 20, 18, 15, 12]
_MIRRORED_BEARISH_TO_BULLISH = [22 - v for v in _TREND_REVERSAL]
_RETEST_ROWS = [
    {"open": 10, "high": 15.5, "low": 9.8, "close": 15},
    {"open": 16, "high": 17, "low": 15.6, "close": 16.5},
    {"open": 16.5, "high": 18, "low": 16, "close": 17.5},
    {"open": 17.5, "high": 18, "low": 14, "close": 16},
]


def _make_signal_scenario_df() -> pd.DataFrame:
    rows = [{"open": v, "high": v, "low": v, "close": v} for v in _MIRRORED_BEARISH_TO_BULLISH] + _RETEST_ROWS
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[["open", "high", "low", "close", "volume"]]


def test_date_slice_equivalent_to_positional_slice_for_signals() -> None:
    """Sana bo'yicha kesish (end_date=retest bar) pozitsion kesish (iloc[:17]) bilan
    AYNAN bir xil signal berishi kerak — bu kesish lookahead yaratmasligini isbotlaydi."""
    df_full = _make_signal_scenario_df()
    retest_index_pos = 16
    retest_date = df_full.index[retest_index_pos]

    df_date_sliced = slice_date_range(df_full, start_date=None, end_date=str(retest_date.date()))
    df_positionally_sliced = df_full.iloc[: retest_index_pos + 1]

    signals_date = generate_signals(df_date_sliced, lookback=1, mult=1.0)
    signals_positional = generate_signals(df_positionally_sliced, lookback=1, mult=1.0)

    assert len(signals_date) == len(signals_positional) == 1
    assert signals_date[0].entry_price == signals_positional[0].entry_price
    assert signals_date[0].stop_price == signals_positional[0].stop_price
    assert signals_date[0].target_price == signals_positional[0].target_price
    assert signals_date[0].entry_index_pos == signals_positional[0].entry_index_pos == retest_index_pos


def test_date_slice_excluding_retest_bar_produces_no_signal() -> None:
    """end_date retest bar'dan OLDIN to'xtasa, signal umuman chiqmasligi kerak (kelajak ko'rinmaydi)."""
    df_full = _make_signal_scenario_df()
    retest_index_pos = 16
    day_before_retest = df_full.index[retest_index_pos - 1]

    df_sliced = slice_date_range(df_full, start_date=None, end_date=str(day_before_retest.date()))
    signals = generate_signals(df_sliced, lookback=1, mult=1.0)

    assert signals == []
