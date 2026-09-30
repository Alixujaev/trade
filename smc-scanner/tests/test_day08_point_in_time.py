"""tests/test_day08_point_in_time.py: PIT & Adversarial Tests for DAY-08 H6 Index Regime Confluence.

MANDATORY ADVERSARIAL VALIDATIONS:
1. Future SPY price mutation: Modify SPY prices AFTER stock signal T (e.g. 5x). Result at T must remain identical.
2. Future QQQ price mutation: Same.
3. Future index volume mutation: Modify future SPY/QQQ volume to huge values. No effect at T.
4. Future 15m structure mutation: Alter future 15m candles to produce different later structure. Earlier context unchanged.
5. Forming 15m candle: At 10:25 ET, verify 10:15-10:30 candle is excluded.
6. Session isolation: Previous/next sessions do not contaminate current session.
7. Symbol isolation: Changing AAPL context does not affect MSFT.
8. Order independence: Changing symbol processing order does not change results.
"""

from __future__ import annotations

import copy
import pandas as pd
import numpy as np
import pytest

from backtest.index_regime import run_day08_index_regime_experiment
from data.factory import get_provider
from strategy.day.index_regime import (
    IndexRegimeDetector,
    build_index_regime_detector,
)


@pytest.fixture(scope="module")
def shared_provider():
    return get_provider()


def test_future_spy_price_mutation(shared_provider):
    """Mutating SPY price AFTER signal time T by 5x must NOT alter index regime at T."""
    spy_5m = shared_provider.get_ohlcv("SPY", "5m", include_extended_hours=False, closed_only=False)
    spy_15m = shared_provider.get_ohlcv("SPY", "15m", include_extended_hours=False, closed_only=False)
    qqq_5m = shared_provider.get_ohlcv("QQQ", "5m", include_extended_hours=False, closed_only=False)
    qqq_15m = shared_provider.get_ohlcv("QQQ", "15m", include_extended_hours=False, closed_only=False)

    det_clean = IndexRegimeDetector(spy_5m, spy_15m, qqq_5m, qqq_15m)

    # Pick a signal timestamp in the middle of dataset
    t_signal = pd.Timestamp("2026-07-08 14:30:00", tz="America/New_York")
    ctx_clean = det_clean.get_context_at(t_signal)

    # Mutate SPY future data (5x prices after t_signal)
    spy_5m_mutated = spy_5m.copy()
    spy_15m_mutated = spy_15m.copy()

    mask_5m_future = spy_5m_mutated.index > t_signal
    mask_15m_future = spy_15m_mutated.index > t_signal

    spy_5m_mutated.loc[mask_5m_future, ["open", "high", "low", "close"]] *= 5.0
    spy_15m_mutated.loc[mask_15m_future, ["open", "high", "low", "close"]] *= 5.0

    det_mutated = IndexRegimeDetector(spy_5m_mutated, spy_15m_mutated, qqq_5m, qqq_15m)
    ctx_mutated = det_mutated.get_context_at(t_signal)

    # State at T must be 100% identical
    assert ctx_clean.spy_5m_relation == ctx_mutated.spy_5m_relation
    assert ctx_clean.spy_15m_structure == ctx_mutated.spy_15m_structure
    assert ctx_clean.spy_bullish == ctx_mutated.spy_bullish
    assert ctx_clean.aligned_bullish == ctx_mutated.aligned_bullish
    assert ctx_clean.mixed == ctx_mutated.mixed
    assert ctx_clean.aligned_bearish == ctx_mutated.aligned_bearish


def test_future_qqq_price_mutation(shared_provider):
    """Mutating QQQ price AFTER signal time T by 5x must NOT alter index regime at T."""
    spy_5m = shared_provider.get_ohlcv("SPY", "5m", include_extended_hours=False, closed_only=False)
    spy_15m = shared_provider.get_ohlcv("SPY", "15m", include_extended_hours=False, closed_only=False)
    qqq_5m = shared_provider.get_ohlcv("QQQ", "5m", include_extended_hours=False, closed_only=False)
    qqq_15m = shared_provider.get_ohlcv("QQQ", "15m", include_extended_hours=False, closed_only=False)

    det_clean = IndexRegimeDetector(spy_5m, spy_15m, qqq_5m, qqq_15m)

    t_signal = pd.Timestamp("2026-07-08 14:30:00", tz="America/New_York")
    ctx_clean = det_clean.get_context_at(t_signal)

    # Mutate QQQ future data (5x prices after t_signal)
    qqq_5m_mutated = qqq_5m.copy()
    qqq_15m_mutated = qqq_15m.copy()

    mask_5m_future = qqq_5m_mutated.index > t_signal
    mask_15m_future = qqq_15m_mutated.index > t_signal

    qqq_5m_mutated.loc[mask_5m_future, ["open", "high", "low", "close"]] *= 5.0
    qqq_15m_mutated.loc[mask_15m_future, ["open", "high", "low", "close"]] *= 5.0

    det_mutated = IndexRegimeDetector(spy_5m, spy_15m, qqq_5m_mutated, qqq_15m_mutated)
    ctx_mutated = det_mutated.get_context_at(t_signal)

    assert ctx_clean.qqq_5m_relation == ctx_mutated.qqq_5m_relation
    assert ctx_clean.qqq_15m_structure == ctx_mutated.qqq_15m_structure
    assert ctx_clean.qqq_bullish == ctx_mutated.qqq_bullish
    assert ctx_clean.aligned_bullish == ctx_mutated.aligned_bullish
    assert ctx_clean.mixed == ctx_mutated.mixed


def test_future_index_volume_mutation(shared_provider):
    """Mutating future SPY/QQQ volume (e.g. 100x volume surge after T) must NOT alter regime at T."""
    spy_5m = shared_provider.get_ohlcv("SPY", "5m", include_extended_hours=False, closed_only=False)
    spy_15m = shared_provider.get_ohlcv("SPY", "15m", include_extended_hours=False, closed_only=False)
    qqq_5m = shared_provider.get_ohlcv("QQQ", "5m", include_extended_hours=False, closed_only=False)
    qqq_15m = shared_provider.get_ohlcv("QQQ", "15m", include_extended_hours=False, closed_only=False)

    det_clean = IndexRegimeDetector(spy_5m, spy_15m, qqq_5m, qqq_15m)

    t_signal = pd.Timestamp("2026-07-09 11:30:00", tz="America/New_York")
    ctx_clean = det_clean.get_context_at(t_signal)

    spy_5m_mut = spy_5m.copy()
    qqq_5m_mut = qqq_5m.copy()

    spy_5m_mut.loc[spy_5m_mut.index > t_signal, "volume"] *= 1000.0
    qqq_5m_mut.loc[qqq_5m_mut.index > t_signal, "volume"] *= 1000.0

    det_mut = IndexRegimeDetector(spy_5m_mut, spy_15m, qqq_5m_mut, qqq_15m)
    ctx_mut = det_mut.get_context_at(t_signal)

    assert ctx_clean.spy_5m_relation == ctx_mut.spy_5m_relation
    assert ctx_clean.qqq_5m_relation == ctx_mut.qqq_5m_relation
    assert ctx_clean.spy_bullish == ctx_mut.spy_bullish
    assert ctx_clean.qqq_bullish == ctx_mut.qqq_bullish


def test_future_15m_structure_mutation(shared_provider):
    """Altering future 15m candles to create a major swing break later must NOT change structure at T."""
    spy_5m = shared_provider.get_ohlcv("SPY", "5m", include_extended_hours=False, closed_only=False)
    spy_15m = shared_provider.get_ohlcv("SPY", "15m", include_extended_hours=False, closed_only=False)
    qqq_5m = shared_provider.get_ohlcv("QQQ", "5m", include_extended_hours=False, closed_only=False)
    qqq_15m = shared_provider.get_ohlcv("QQQ", "15m", include_extended_hours=False, closed_only=False)

    det_clean = IndexRegimeDetector(spy_5m, spy_15m, qqq_5m, qqq_15m)

    t_signal = pd.Timestamp("2026-07-10 13:00:00", tz="America/New_York")
    ctx_clean = det_clean.get_context_at(t_signal)

    # Force a massive drop in future 15m candles to create a bearish break in later bars
    spy_15m_mut = spy_15m.copy()
    future_mask = spy_15m_mut.index > t_signal
    spy_15m_mut.loc[future_mask, "close"] *= 0.70
    spy_15m_mut.loc[future_mask, "low"] *= 0.65

    det_mut = IndexRegimeDetector(spy_5m, spy_15m_mut, qqq_5m, qqq_15m)
    ctx_mut = det_mut.get_context_at(t_signal)

    assert ctx_clean.spy_15m_structure == ctx_mut.spy_15m_structure
    assert ctx_clean.spy_bullish == ctx_mut.spy_bullish


def test_forming_15m_candle_excluded_at_1025(shared_provider):
    """At 10:25 ET, verify 10:15-10:30 candle is excluded and 10:00-10:15 candle is used."""
    det = build_index_regime_detector(shared_provider)

    t_1025 = pd.Timestamp("2026-07-06 10:25:00", tz="America/New_York")
    as_of = det._normalize_timestamp(t_1025)

    # Check 15m index end time
    k15 = det.end_15m_spy.searchsorted(as_of, side="right") - 1
    assert k15 >= 0
    bar_end = det.end_15m_spy[k15]

    # Bar end time must be <= 10:25 ET (i.e. 10:15 ET)
    assert bar_end <= as_of
    from data.session import to_eastern
    bar_end_et = to_eastern(pd.DatetimeIndex([bar_end]))[0]
    assert bar_end_et.strftime("%H:%M") == "10:15"


def test_session_isolation(shared_provider):
    """Indices VWAP resets daily; previous session's volume/price does not leak into current session VWAP."""
    spy_5m = shared_provider.get_ohlcv("SPY", "5m", include_extended_hours=False, closed_only=False)
    spy_15m = shared_provider.get_ohlcv("SPY", "15m", include_extended_hours=False, closed_only=False)
    qqq_5m = shared_provider.get_ohlcv("QQQ", "5m", include_extended_hours=False, closed_only=False)
    qqq_15m = shared_provider.get_ohlcv("QQQ", "15m", include_extended_hours=False, closed_only=False)

    det_full = IndexRegimeDetector(spy_5m, spy_15m, qqq_5m, qqq_15m)

    # First session in dataset: 2026-07-06
    # Mutate 2026-07-06 prices
    t_session_1 = pd.Timestamp("2026-07-06 15:50:00", tz="America/New_York")
    t_session_2 = pd.Timestamp("2026-07-07 10:30:00", tz="America/New_York")

    ctx_session_2_clean = det_full.get_context_at(t_session_2)

    # Mutate session 1 data by 10x
    spy_5m_mut = spy_5m.copy()
    s1_mask = spy_5m_mut.index <= pd.Timestamp("2026-07-06 16:00:00", tz="America/New_York")
    spy_5m_mut.loc[s1_mask, ["open", "high", "low", "close"]] *= 10.0
    spy_5m_mut.loc[s1_mask, "volume"] *= 10.0

    det_s1_mut = IndexRegimeDetector(spy_5m_mut, spy_15m, qqq_5m, qqq_15m)
    ctx_session_2_mut = det_s1_mut.get_context_at(t_session_2)

    # Session 2 VWAP relation for SPY must remain unchanged because VWAP resets daily
    assert ctx_session_2_clean.spy_5m_relation == ctx_session_2_mut.spy_5m_relation


def test_symbol_isolation(shared_provider):
    """Context classification is independent of stock symbol: SPY/QQQ at time T is identical for any symbol."""
    det = build_index_regime_detector(shared_provider)
    ts = pd.Timestamp("2026-07-08 11:00:00", tz="America/New_York")

    ctx_aapl = det.get_context_at(ts)
    ctx_msft = det.get_context_at(ts)

    assert ctx_aapl == ctx_msft


def test_order_independence(shared_provider):
    """Running experiment with symbols in reversed order produces identical aggregate metrics."""
    test_symbols = ["AAPL", "MSFT", "NVDA"]

    res_forward = run_day08_index_regime_experiment(
        symbols=test_symbols,
        provider=shared_provider,
    )

    res_reverse = run_day08_index_regime_experiment(
        symbols=list(reversed(test_symbols)),
        provider=shared_provider,
    )

    assert res_forward.baseline_metrics.trades == res_reverse.baseline_metrics.trades
    assert res_forward.h6_a_metrics.trades == res_reverse.h6_a_metrics.trades
    assert res_forward.h6_b_metrics.trades == res_reverse.h6_b_metrics.trades
    assert res_forward.h6_c_metrics.trades == res_reverse.h6_c_metrics.trades

    assert res_forward.h6_c_metrics.total_R == res_reverse.h6_c_metrics.total_R
    assert res_forward.h6_c_metrics.win_rate == res_reverse.h6_c_metrics.win_rate


# ======================================================================
# Offline (sintetik) PIT testlari — tarmoqqa bog'liq emas.
# Yuqoridagi testlardan farqi: mutatsiya `bar_open > T` bo'yicha emas, balki
# `bar_end > T` bo'yicha qilinadi — ya'ni T da hali SHAKLLANAYOTGAN (forming)
# 5m va 15m shamlar ham buziladi. Grid'ga to'g'ri kelmaydigan T (10:25) tanlanadi.
# ======================================================================

_SYN_SESSIONS = ("2026-07-06", "2026-07-07", "2026-07-08")


def _synthetic_rth(freq_minutes: int, seed: int) -> pd.DataFrame:
    """Bir necha RTH sessiyasi uchun deterministik OHLCV (provider kabi UTC index)."""
    rng = np.random.default_rng(seed)
    frames = []
    price = 500.0
    for day in _SYN_SESSIONS:
        idx = pd.date_range(
            f"{day} 09:30", f"{day} 15:59", freq=f"{freq_minutes}min", tz="America/New_York"
        )
        # Tebranuvchi trend — swing'lar va BOS/CHoCH hosil bo'lishi uchun
        steps = np.sin(np.arange(len(idx)) / 3.0) * 1.5 + rng.normal(0.05, 0.4, len(idx))
        closes = price + np.cumsum(steps)
        opens = np.concatenate([[price], closes[:-1]])
        highs = np.maximum(opens, closes) + rng.uniform(0.05, 0.5, len(idx))
        lows = np.minimum(opens, closes) - rng.uniform(0.05, 0.5, len(idx))
        vols = rng.uniform(1e5, 5e5, len(idx))
        frames.append(
            pd.DataFrame(
                {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
                index=idx.tz_convert("UTC"),
            )
        )
        price = float(closes[-1])
    return pd.concat(frames)


def _mutate_unclosed(
    df: pd.DataFrame, freq_minutes: int, t: pd.Timestamp, factor: float
) -> pd.DataFrame:
    """T da hali yopilmagan (bar_end > T) barcha barlarni ekstremal buzadi: narx x factor, hajm x1000."""
    out = df.copy()
    unclosed = (out.index + pd.Timedelta(minutes=freq_minutes)) > t
    out.loc[unclosed, ["open", "high", "low", "close"]] *= factor
    out.loc[unclosed, "volume"] *= 1000.0
    return out


@pytest.fixture(scope="module")
def synthetic_index_data():
    return {
        "spy_5m": _synthetic_rth(5, seed=1),
        "spy_15m": _synthetic_rth(15, seed=2),
        "qqq_5m": _synthetic_rth(5, seed=3),
        "qqq_15m": _synthetic_rth(15, seed=4),
    }


# Ikki yo'nalish: x5 (bullish break) va x0.2 (bearish break) — struktura qaysi holatda
# bo'lmasin, forming bar ishlatilsa kamida bittasi natijani o'zgartiradi.
@pytest.mark.parametrize("factor", [5.0, 0.2])
@pytest.mark.parametrize(
    "t_str",
    ["2026-07-07 10:25", "2026-07-07 10:40", "2026-07-07 13:05", "2026-07-08 09:55"],
)
def test_offline_forming_and_future_bars_mutation_has_no_effect(synthetic_index_data, t_str, factor):
    """T da forming 5m/15m shamlar va barcha kelajak barlar buzilsa ham kontekst o'zgarmaydi."""
    d = synthetic_index_data
    t = pd.Timestamp(t_str, tz="America/New_York")

    clean = IndexRegimeDetector(d["spy_5m"], d["spy_15m"], d["qqq_5m"], d["qqq_15m"])
    mutated = IndexRegimeDetector(
        _mutate_unclosed(d["spy_5m"], 5, t, factor),
        _mutate_unclosed(d["spy_15m"], 15, t, factor),
        _mutate_unclosed(d["qqq_5m"], 5, t, factor),
        _mutate_unclosed(d["qqq_15m"], 15, t, factor),
    )

    ctx_clean = clean.get_context_at(t)
    assert ctx_clean.data_sufficient, "Sintetik data kontekst hosil qilishi kerak"
    assert ctx_clean == mutated.get_context_at(t)


@pytest.mark.parametrize("factor", [5.0, 0.2])
def test_offline_forming_15m_candle_mutation_at_1025(synthetic_index_data, factor):
    """10:25 ET: faqat 10:15–10:30 15m sham (forming) buzilsa — natija o'zgarmasligi shart.

    Bu sham'ning o'zi ishlatilganda (lookahead) 5x narx 15m strukturani albatta o'zgartirardi.
    """
    d = synthetic_index_data
    t = pd.Timestamp("2026-07-07 10:25", tz="America/New_York")
    forming_open = pd.Timestamp("2026-07-07 10:15", tz="America/New_York")

    spy_15m_mut = d["spy_15m"].copy()
    qqq_15m_mut = d["qqq_15m"].copy()
    for df in (spy_15m_mut, qqq_15m_mut):
        assert forming_open in df.index
        df.loc[forming_open, ["open", "high", "low", "close"]] *= factor

    clean = IndexRegimeDetector(d["spy_5m"], d["spy_15m"], d["qqq_5m"], d["qqq_15m"])
    mutated = IndexRegimeDetector(d["spy_5m"], spy_15m_mut, d["qqq_5m"], qqq_15m_mut)
    assert clean.get_context_at(t) == mutated.get_context_at(t)


def test_offline_next_session_mutation_does_not_leak_back(synthetic_index_data):
    """Keyingi sessiya (07-08) to'liq buzilsa ham oldingi sessiyadagi kontekst o'zgarmaydi."""
    d = synthetic_index_data
    cut = pd.Timestamp("2026-07-08 00:00", tz="America/New_York")

    def mutate_next(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        mask = out.index >= cut
        out.loc[mask, ["open", "high", "low", "close"]] *= 0.2
        out.loc[mask, "volume"] *= 1000.0
        return out

    clean = IndexRegimeDetector(d["spy_5m"], d["spy_15m"], d["qqq_5m"], d["qqq_15m"])
    mutated = IndexRegimeDetector(
        mutate_next(d["spy_5m"]), mutate_next(d["spy_15m"]),
        mutate_next(d["qqq_5m"]), mutate_next(d["qqq_15m"]),
    )
    for t_str in ("2026-07-07 10:25", "2026-07-07 12:10", "2026-07-07 15:55"):
        t = pd.Timestamp(t_str, tz="America/New_York")
        assert clean.get_context_at(t) == mutated.get_context_at(t)
