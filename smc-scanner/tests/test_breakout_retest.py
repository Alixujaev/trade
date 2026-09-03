"""strategy/breakout_retest.py uchun testlar (qo'lda qurilgan OHLCV ssenariylari)."""

from __future__ import annotations

import pandas as pd
import pytest

from strategy.breakout_retest import generate_breakout_retest_signals

_COLUMNS = ["open", "high", "low", "close", "volume"]

# Test parametrlari — kichik oynalar, ATR erta mavjud bo'lishi uchun period=3.
_KW = dict(
    lookback=1,
    atr_period=3,
    volume_ma_period=3,
    volume_ratio_min=1.5,
    retest_tolerance_atr_mult=0.25,
    retest_max_bars=5,
    confirmation_max_bars=3,
    sl_atr_mult=1.0,
    stop_mode="structure",
    tp_r_multiple=2.0,
    min_rr=1.5,
    require_trend=False,
)

# idx 1,3,5: swing high @100 (confirmed 2,4,6) -> RESISTANCE zona, confirmed=6, band [100,100]
# idx 8: breakout (close 104 > 100, volume 3000 -> ratio 1.8 >= 1.5)
# idx 9: retest (low 100 zona top'iga tegadi, close 101 ushlab qoladi)
# idx 10: bullish tasdiq (close 107 > open 101, close 107 > 100) -> entry
_BASE_ROWS = [
    {"open": 95, "high": 98, "low": 94, "close": 96, "volume": 1000},
    {"open": 96, "high": 100, "low": 95, "close": 97, "volume": 1000},
    {"open": 97, "high": 96, "low": 93, "close": 94, "volume": 1000},
    {"open": 94, "high": 100, "low": 93, "close": 96, "volume": 1000},
    {"open": 96, "high": 96, "low": 92, "close": 93, "volume": 1000},
    {"open": 93, "high": 100, "low": 92, "close": 95, "volume": 1000},
    {"open": 95, "high": 95, "low": 90, "close": 92, "volume": 1000},
    {"open": 92, "high": 99, "low": 91, "close": 98, "volume": 1000},
    {"open": 98, "high": 105, "low": 97, "close": 104, "volume": 3000},
    {"open": 104, "high": 106, "low": 100, "close": 101, "volume": 1000},
    {"open": 101, "high": 108, "low": 100.5, "close": 107, "volume": 1000},
    {"open": 107, "high": 109, "low": 105, "close": 108, "volume": 1000},
]


def _make_df(rows: list[dict]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    if not rows:
        return pd.DataFrame(columns=_COLUMNS, index=index)
    return pd.DataFrame(rows, index=index)[_COLUMNS]


def test_end_to_end_emits_one_signal() -> None:
    signals = generate_breakout_retest_signals(_make_df(_BASE_ROWS), **_KW)

    assert len(signals) == 1
    s = signals[0]
    assert s.entry_index_pos == 10
    assert s.breakout_index_pos == 8
    assert s.retest_index_pos == 9
    assert s.reason.startswith("BREAKOUT_RETEST@")
    assert s.entry_price == pytest.approx(107.0)
    # structure stop = zona.bottom(100) - 1.0*ATR[10];  ATR[10]=mean(TR8,TR9,TR10)=mean(8,6,7.5)=7.16667
    assert s.stop_price == pytest.approx(92.833333, abs=1e-4)
    # resistance yuqorida yo'q -> 2R fallback: entry + 2*(entry-stop)
    risk = 107.0 - 92.833333
    assert s.target_price == pytest.approx(107.0 + 2 * risk, abs=1e-3)


def test_no_signal_without_volume_confirmation() -> None:
    rows = [dict(r) for r in _BASE_ROWS]
    rows[8]["volume"] = 1000  # breakout barida hajm spike yo'q
    assert generate_breakout_retest_signals(_make_df(rows), **_KW) == []


def test_trend_filter_blocks_when_regime_not_bullish() -> None:
    # require_trend=True + qisqa seriya -> EMA200 warmup -> regime NEUTRAL -> breakout yo'q
    kw = {**_KW, "require_trend": True}
    assert generate_breakout_retest_signals(_make_df(_BASE_ROWS), **kw) == []
    # require_trend=False bilan esa signal bor
    assert len(generate_breakout_retest_signals(_make_df(_BASE_ROWS), **_KW)) == 1


def test_no_signal_when_retest_never_occurs() -> None:
    rows = [dict(r) for r in _BASE_ROWS[:9]] + [
        {"open": 104, "high": 112, "low": 106, "close": 111, "volume": 1000},
        {"open": 111, "high": 118, "low": 110, "close": 117, "volume": 1000},
        {"open": 117, "high": 124, "low": 116, "close": 123, "volume": 1000},
        {"open": 123, "high": 130, "low": 122, "close": 129, "volume": 1000},
        {"open": 129, "high": 136, "low": 128, "close": 135, "volume": 1000},
        {"open": 135, "high": 142, "low": 134, "close": 141, "volume": 1000},
    ]
    # breakout'dan keyin narx hech qachon zona top'iga (~100) qaytmaydi
    assert generate_breakout_retest_signals(_make_df(rows), **_KW) == []


def test_breakout_invalidated_by_close_back_below_band() -> None:
    rows = [dict(r) for r in _BASE_ROWS[:9]] + [
        {"open": 104, "high": 105, "low": 90, "close": 92, "volume": 1000},  # close 92 << 100-tol
        {"open": 92, "high": 95, "low": 88, "close": 90, "volume": 1000},
        {"open": 90, "high": 93, "low": 87, "close": 89, "volume": 1000},
    ]
    assert generate_breakout_retest_signals(_make_df(rows), **_KW) == []


def test_no_signal_when_confirmation_candle_bearish() -> None:
    rows = [dict(r) for r in _BASE_ROWS[:10]] + [
        {"open": 107, "high": 108, "low": 101, "close": 102, "volume": 1000},  # bearish (close<open)
        {"open": 102, "high": 103, "low": 99, "close": 100, "volume": 1000},   # close == top, > emas
        {"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1000},    # close < top
    ]
    assert generate_breakout_retest_signals(_make_df(rows), **_KW) == []


def test_rr_gate_rejects_low_rr_setup() -> None:
    kw = {**_KW, "min_rr": 5.0}  # RR ~2.0 setup shu chegaradan past -> emit qilinmaydi
    assert generate_breakout_retest_signals(_make_df(_BASE_ROWS), **kw) == []


def test_multiple_zones_produce_chronological_signals() -> None:
    # 1-zona @100 (yuqoridagi bilan bir xil, entry ~idx10), keyin 2-zona @120.
    rows = [dict(r) for r in _BASE_ROWS[:11]] + [
        {"open": 107, "high": 118, "low": 106, "close": 110, "volume": 1000},   # 11
        {"open": 110, "high": 120, "low": 108, "close": 112, "volume": 1000},   # 12 swing high @120
        {"open": 112, "high": 116, "low": 110, "close": 114, "volume": 1000},   # 13
        {"open": 114, "high": 120, "low": 112, "close": 116, "volume": 1000},   # 14 swing high @120
        {"open": 116, "high": 117, "low": 112, "close": 114, "volume": 1000},   # 15
        {"open": 114, "high": 120, "low": 112, "close": 116, "volume": 1000},   # 16 swing high @120
        {"open": 116, "high": 118, "low": 111, "close": 113, "volume": 1000},   # 17 -> zona confirmed 18
        {"open": 113, "high": 125, "low": 112, "close": 124, "volume": 3000},   # 18 breakout @120
        {"open": 124, "high": 126, "low": 120, "close": 121, "volume": 1000},   # 19 retest
        {"open": 121, "high": 130, "low": 120.5, "close": 129, "volume": 1000},  # 20 bullish tasdiq -> entry
        {"open": 129, "high": 131, "low": 126, "close": 130, "volume": 1000},   # 21
    ]
    signals = generate_breakout_retest_signals(_make_df(rows), **_KW)

    assert len(signals) == 2
    assert [s.entry_index_pos for s in signals] == sorted(s.entry_index_pos for s in signals)
    assert signals[0].entry_index_pos == 10
    assert signals[1].entry_index_pos == 20


def test_no_lookahead_bias() -> None:
    df_full = _make_df(_BASE_ROWS)
    signals_full = generate_breakout_retest_signals(df_full, **_KW)
    assert len(signals_full) == 1
    entry_pos = signals_full[0].entry_index_pos

    # entry barini o'z ichiga olgan kesim -> to'liq bilan bir xil
    incl = generate_breakout_retest_signals(df_full.iloc[: entry_pos + 1], **_KW)
    assert len(incl) == 1
    assert incl[0].entry_index_pos == entry_pos
    assert incl[0].entry_price == pytest.approx(signals_full[0].entry_price)
    assert incl[0].stop_price == pytest.approx(signals_full[0].stop_price)

    # entry baridan oldingi kesim -> signal yo'q
    excl = generate_breakout_retest_signals(df_full.iloc[:entry_pos], **_KW)
    assert excl == []


def test_insufficient_data_returns_empty_no_crash() -> None:
    assert generate_breakout_retest_signals(_make_df(_BASE_ROWS[:2]), **_KW) == []
    assert generate_breakout_retest_signals(_make_df([]), **_KW) == []
