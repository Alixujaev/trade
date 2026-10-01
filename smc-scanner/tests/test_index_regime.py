"""tests/test_index_regime.py: Unit tests for DAY-08 Index Regime Confluence module."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import datetime
import pytest
import pandas as pd
import numpy as np

from strategy.day.index_regime import (
    IndexRegimeContext,
    IndexRegimeDetector,
    IndexStructureContext,
    IndexVwapRelation,
    build_index_regime_detector,
)


def _create_sample_ohlcv(
    start: str,
    periods: int,
    freq: str,
    base_price: float = 500.0,
    trend: float = 0.5,
) -> pd.DataFrame:
    """Helper to create synthetic OHLCV data with DatetimeIndex."""
    idx = pd.date_range(start, periods=periods, freq=freq, tz="America/New_York")
    rows = []
    price = base_price
    for i, ts in enumerate(idx):
        o = price
        h = o + 1.0 + (i % 3) * 0.2
        l = o - 0.8
        c = o + trend + (0.2 if i % 2 == 0 else -0.2)
        v = 10000.0 + (i % 5) * 1000.0
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
        price = c
    return pd.DataFrame(rows, index=idx)


def test_index_regime_context_immutability():
    """Verify IndexRegimeContext is an immutable frozen dataclass."""
    ts = pd.Timestamp("2026-07-06 10:25:00", tz="America/New_York")
    ctx = IndexRegimeContext(
        timestamp=ts,
        spy_5m_relation="ABOVE_VWAP",
        spy_15m_structure="BULLISH",
        spy_vwap_relation="ABOVE_VWAP",
        qqq_5m_relation="ABOVE_VWAP",
        qqq_15m_structure="BULLISH",
        qqq_vwap_relation="ABOVE_VWAP",
        spy_bullish=True,
        qqq_bullish=True,
        aligned_bullish=True,
        mixed=False,
        aligned_bearish=False,
        data_sufficient=True,
    )

    with pytest.raises(FrozenInstanceError):
        ctx.aligned_bullish = False  # type: ignore[misc]

    assert ctx.timestamp == ts
    assert ctx.aligned_bullish is True
    assert ctx.mixed is False
    assert ctx.data_sufficient is True


def test_section_9_1025_et_boundary_regression():
    """Section 9 Explicit Regression Test:

    If the stock signal occurs at 10:25 ET, the 10:15-10:30 15m index candle is
    still forming and MUST NOT be used.
    The latest usable candle is 10:00-10:15.
    Likewise, the 10:25-10:30 5m candle is forming and the latest closed 5m
    candle is 10:20-10:25.
    """
    # Create 5m bars starting at 09:30:
    # 09:30, 09:35, 09:40, 09:45, 09:50, 09:55, 10:00, 10:05, 10:10, 10:15, 10:20, 10:25, 10:30...
    df_5m = _create_sample_ohlcv("2026-07-06 09:30:00", periods=20, freq="5min", base_price=500.0)
    # Create 15m bars starting at 09:30:
    # 09:30 (ends 09:45), 09:45 (ends 10:00), 10:00 (ends 10:15), 10:15 (ends 10:30), 10:30 (ends 10:45)
    df_15m = _create_sample_ohlcv("2026-07-06 09:30:00", periods=8, freq="15min", base_price=500.0)

    detector = IndexRegimeDetector(
        spy_5m=df_5m,
        spy_15m=df_15m,
        qqq_5m=df_5m,
        qqq_15m=df_15m,
    )

    t_1025 = pd.Timestamp("2026-07-06 10:25:00", tz="America/New_York")
    as_of = detector._normalize_timestamp(t_1025)

    # 1. Check 15m end times searchsorted
    # 10:00 bar has end time 10:15 <= 10:25
    # 10:15 bar has end time 10:30 > 10:25
    k15 = detector.end_15m_spy.searchsorted(as_of, side="right") - 1
    assert k15 >= 0
    latest_15m_bar_open = df_15m.index[k15]
    latest_15m_bar_end = detector.end_15m_spy[k15]

    # Verify latest usable 15m candle is 10:00 (which closed at 10:15)
    assert latest_15m_bar_open.strftime("%H:%M") == "10:00"
    assert latest_15m_bar_end.strftime("%H:%M") == "10:15"
    assert latest_15m_bar_end <= as_of

    # Verify 10:15-10:30 candle is EXCLUDED (not selected)
    assert latest_15m_bar_open.strftime("%H:%M") != "10:15"

    # 2. Check 5m end times searchsorted
    # 10:20 bar has end time 10:25 <= 10:25
    # 10:25 bar has end time 10:30 > 10:25
    k5 = detector.end_5m_spy.searchsorted(as_of, side="right") - 1
    assert k5 >= 0
    latest_5m_bar_open = df_5m.index[k5]
    latest_5m_bar_end = detector.end_5m_spy[k5]

    # Verify latest closed 5m candle is 10:20 (which closed at 10:25)
    assert latest_5m_bar_open.strftime("%H:%M") == "10:20"
    assert latest_5m_bar_end.strftime("%H:%M") == "10:25"
    assert latest_5m_bar_end <= as_of

    # Verify forming 10:25 candle is EXCLUDED
    assert latest_5m_bar_open.strftime("%H:%M") != "10:25"


def test_missing_data_behavior():
    """Section 7: If index data is insufficient or unavailable,

    must explicitly return UNKNOWN / DATA_INSUFFICIENT (is_bullish=None).
    """
    empty_df = pd.DataFrame()
    detector = IndexRegimeDetector(
        spy_5m=empty_df,
        spy_15m=empty_df,
        qqq_5m=empty_df,
        qqq_15m=empty_df,
    )

    t = pd.Timestamp("2026-07-06 10:25:00", tz="America/New_York")
    ctx = detector.get_context_at(t)

    assert ctx.data_sufficient is False
    assert ctx.spy_bullish is None
    assert ctx.qqq_bullish is None
    assert ctx.aligned_bullish is False
    assert ctx.aligned_bearish is False
    assert ctx.mixed is False
    assert ctx.spy_5m_relation == IndexVwapRelation.UNKNOWN.value
    assert ctx.spy_15m_structure == IndexStructureContext.UNKNOWN.value


def test_early_morning_insufficient_15m_data():
    """At 09:35 ET, fewer than 5 15m bars are available, so 15m structure is UNKNOWN."""
    df_5m = _create_sample_ohlcv("2026-07-06 09:30:00", periods=10, freq="5min")
    df_15m = _create_sample_ohlcv("2026-07-06 09:30:00", periods=2, freq="15min")

    detector = IndexRegimeDetector(
        spy_5m=df_5m,
        spy_15m=df_15m,
        qqq_5m=df_5m,
        qqq_15m=df_15m,
    )

    t_0935 = pd.Timestamp("2026-07-06 09:35:00", tz="America/New_York")
    ctx = detector.get_context_at(t_0935)

    # 15m structure cannot be confirmed with < 5 bars
    assert ctx.spy_15m_structure == IndexStructureContext.UNKNOWN.value
    assert ctx.data_sufficient is False
    assert ctx.spy_bullish is None
    assert ctx.aligned_bullish is False


def test_regime_mutual_exclusivity():
    """Verify that for sufficient data, exactly one of (aligned_bullish, mixed, aligned_bearish) is True."""
    from data.factory import get_provider
    prov = get_provider()

    detector = build_index_regime_detector(provider=prov)

    # Sample a set of trading session times
    # Frozen SPY/QQQ coverage: 2026-07-08 -> 2026-09-25 (context from 07-08 10:45 ET)
    test_times = [
        pd.Timestamp("2026-07-08 15:00:00", tz="America/New_York"),
        pd.Timestamp("2026-07-09 11:30:00", tz="America/New_York"),
        pd.Timestamp("2026-07-10 14:00:00", tz="America/New_York"),
        pd.Timestamp("2026-07-13 10:30:00", tz="America/New_York"),
    ]

    for ts in test_times:
        ctx = detector.get_context_at(ts)
        assert ctx.data_sufficient, f"Index context expected at {ts}"
        true_count = sum([ctx.aligned_bullish, ctx.mixed, ctx.aligned_bearish])
        assert true_count == 1, f"Expected exactly one active category at {ts}, got {true_count}"
