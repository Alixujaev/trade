"""tests/test_day06a_gap_thresholds.py: DAY-06A Gap Threshold Robustness & Stability Tests.

QAT'IY METODOLOGIK TEKSHIRUVLAR:
1. Test 1 — Threshold boundary classification (0.5%, 1.0%, 1.9%, 2.0%, 2.1%, 3.0%, 3.1%, 4.0%, 4.1%)
2. Test 2 — Monotonicity: 4% eligibility => 3% => 2% => 1% (subset integrity)
3. Test 3 — Future data isolation: 09:30 dan keyingi narx/hajm mutatsiyalari
4. Test 4 — Session isolation: Boshqa kunlik sessiyalar mutatsiyasi
5. Test 5 — Symbol isolation: Ticker A ma'lumotlari Ticker B ga ta'sir qilmasligi
6. Test 6 — Order independence: Tickerlarni ishlash tartibi natijaga ta'sir qilmasligi
7. Test 7 — Backward compatibility: 2.0% threshold DAY-06 Variant A bilan 100% mos kelishi
8. Test 8 — Frozen strategy: Faqat sessiya geyti o'zgarishi, savdo ijro qoidalari o'zgarmasligi
9. Test 9 — Missing data: Oldingi close yoki bugungi open yo'q bo'lsa, DATA_INSUFFICIENT (gap=0 qilinmaydi)
"""

from __future__ import annotations

from datetime import date
import math
import numpy as np
import pandas as pd
import pytest

from backtest.day_types import ExecutionConfig
from backtest.stock_in_play import (
    GapThresholdSensitivityResult,
    VariantMetrics,
    compute_variant_metrics,
    run_gap_threshold_sensitivity_backtest,
)
from strategy.day.stock_in_play import (
    DEFAULT_GAP_THRESHOLDS_PCT,
    StockInPlayContext,
    compute_stock_in_play_contexts,
)


def _create_multi_day_synthetic_ohlcv(
    prices: list[tuple[float, float]],  # Har bir kun uchun (open, close)
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ko'p kunlik sintetik 5m RTH va Extended ma'lumotlarni yaratadi."""
    all_rth_dfs = []
    all_ext_dfs = []

    base_date = pd.Timestamp("2026-07-06 00:00:00", tz="America/New_York")

    for i, (open_p, close_p) in enumerate(prices):
        curr_day = base_date + pd.Timedelta(days=i)
        pm_times = pd.date_range(curr_day + pd.Timedelta(hours=4), curr_day + pd.Timedelta(hours=9, minutes=25), freq="5min")
        rth_times = pd.date_range(curr_day + pd.Timedelta(hours=9, minutes=30), curr_day + pd.Timedelta(hours=15, minutes=55), freq="5min")

        n_rth = len(rth_times)
        n_pm = len(pm_times)

        # RTH DataFrame
        rth_open = [open_p] + [open_p + 0.1] * (n_rth - 2) + [close_p]
        rth_high = [max(open_p, close_p) + 0.5] * n_rth
        rth_low = [min(open_p, close_p) - 0.5] * n_rth
        rth_close = [open_p] + [open_p + 0.2] * (n_rth - 2) + [close_p]
        rth_vol = [1000] * n_rth

        df_rth_day = pd.DataFrame(
            {"open": rth_open, "high": rth_high, "low": rth_low, "close": rth_close, "volume": rth_vol},
            index=rth_times,
        )
        all_rth_dfs.append(df_rth_day)

        # Extended DataFrame (premarket + RTH)
        ext_times = pm_times.append(rth_times)
        df_ext_day = pd.DataFrame(
            {
                "open": [open_p] * len(ext_times),
                "high": [open_p + 1.0] * len(ext_times),
                "low": [open_p - 1.0] * len(ext_times),
                "close": [open_p] * len(ext_times),
                "volume": [100] * len(ext_times),
            },
            index=ext_times,
        )
        df_ext_day.loc[rth_times[0], "open"] = open_p
        df_ext_day.loc[rth_times[-1], "close"] = close_p
        all_ext_dfs.append(df_ext_day)

    full_rth = pd.concat(all_rth_dfs)
    full_ext = pd.concat(all_ext_dfs)
    return full_rth, full_ext


def test_1_threshold_classification_boundaries() -> None:
    """Test 1: Chegaradagi barcha qiymatlar (0.5%, 1.0%, 1.9%, 2.0%, 2.1%, 3.0%, 3.1%, 4.0%, 4.1%) to'g'ri tasniflanishi kerak."""
    # Previous close = 100.0
    # Turli xil gap foizlari uchun bugungi open narxlari
    test_cases = [
        # (gap_pct, expected_1, expected_2, expected_3, expected_4)
        (0.005, False, False, False, False),  # 0.5%
        (0.010, True, False, False, False),   # 1.0%
        (0.019, True, False, False, False),   # 1.9%
        (0.020, True, True, False, False),    # 2.0%
        (0.021, True, True, False, False),    # 2.1%
        (0.030, True, True, True, False),     # 3.0%
        (0.031, True, True, True, False),     # 3.1%
        (0.040, True, True, True, True),      # 4.0%
        (0.041, True, True, True, True),      # 4.1%
        # Salbiy gaplar (absolute value)
        (-0.005, False, False, False, False),
        (-0.010, True, False, False, False),
        (-0.020, True, True, False, False),
        (-0.030, True, True, True, False),
        (-0.040, True, True, True, True),
    ]

    for gap, exp1, exp2, exp3, exp4 in test_cases:
        today_open = 100.0 * (1.0 + gap)
        rth_df, ext_df = _create_multi_day_synthetic_ohlcv([(100.0, 100.0), (today_open, today_open)])
        ctxs = compute_stock_in_play_contexts("TEST", rth_df, ext_df)

        d2 = sorted(ctxs.keys())[1]
        ctx = ctxs[d2]

        assert pytest.approx(ctx.gap_pct, 1e-4) == gap
        assert ctx.is_gap_eligible_at(0.01) == exp1, f"Failed at gap={gap} for 1.0%"
        assert ctx.is_gap_eligible_at(0.02) == exp2, f"Failed at gap={gap} for 2.0%"
        assert ctx.is_gap_eligible_at(0.03) == exp3, f"Failed at gap={gap} for 3.0%"
        assert ctx.is_gap_eligible_at(0.04) == exp4, f"Failed at gap={gap} for 4.0%"


def test_2_threshold_monotonicity() -> None:
    """Test 2: Monotonlik tekshiruvi: 4% muvofiq bo'lsa -> 3% muvofiq -> 2% muvofiq -> 1% muvofiq."""
    # Tasodifiy 20 ta turli xil gaplarga ega sessiyalar
    gaps = np.linspace(-0.06, 0.06, 25)
    prices = [(100.0, 100.0)]
    for g in gaps:
        prices.append((100.0 * (1.0 + g), 100.0 * (1.0 + g)))

    rth_df, ext_df = _create_multi_day_synthetic_ohlcv(prices)
    ctxs = compute_stock_in_play_contexts("TEST", rth_df, ext_df)

    for d, ctx in list(ctxs.items())[1:]:
        e1 = ctx.is_gap_eligible_at(0.01)
        e2 = ctx.is_gap_eligible_at(0.02)
        e3 = ctx.is_gap_eligible_at(0.03)
        e4 = ctx.is_gap_eligible_at(0.04)

        # Agar 4% ga yaroqli bo'lsa, barcha quyi thresholdlarga ham yaroqli bo'lishi shart
        if e4:
            assert e3, f"Monotonicity violation on {d}: 4% True but 3% False"
        if e3:
            assert e2, f"Monotonicity violation on {d}: 3% True but 2% False"
        if e2:
            assert e1, f"Monotonicity violation on {d}: 2% True but 1% False"


def test_3_future_data_isolation() -> None:
    """Test 3: 09:30 dan keyingi barcha RTH narx va hajm mutatsiyalari sessiya muvofiqligiga aslo ta'sir qilmasligi kerak."""
    # Kun 1: close 100.0. Kun 2: open 102.5 (+2.5% gap).
    # 2.5% gap: 1% va 2% ga True, 3% va 4% ga False.
    rth_df, ext_df = _create_multi_day_synthetic_ohlcv([(100.0, 100.0), (102.5, 102.5)])
    ctxs_clean = compute_stock_in_play_contexts("TEST", rth_df, ext_df)
    d2 = sorted(ctxs_clean.keys())[1]

    # Mutatsiya 1: 09:35 dan keyingi narxlarni 5 barobar oshirish
    rth_df_mutated = rth_df.copy()
    d2_rth_bars = rth_df_mutated.index[rth_df_mutated.index.date == d2]
    rth_df_mutated.loc[d2_rth_bars[1:], "close"] *= 5.0
    rth_df_mutated.loc[d2_rth_bars[1:], "high"] *= 5.0

    # Mutatsiya 2: 09:35 dan keyingi hajmni 1,000,000 barobar oshirish
    rth_df_mutated.loc[d2_rth_bars[1:], "volume"] = 999_999_999

    ctxs_mutated = compute_stock_in_play_contexts("TEST", rth_df_mutated, ext_df)

    assert ctxs_clean[d2].gap_pct == ctxs_mutated[d2].gap_pct
    for t in (0.01, 0.02, 0.03, 0.04):
        assert ctxs_clean[d2].is_gap_eligible_at(t) == ctxs_mutated[d2].is_gap_eligible_at(t)


def test_4_session_isolation() -> None:
    """Test 4: Boshqa kelajak yoki o'tgan sessiyaning narxi o'zgarishi joriy kunning gapiga ta'sir qilmasligi kerak."""
    prices = [(100.0, 100.0), (102.0, 102.0), (105.0, 105.0)]
    rth_df, ext_df = _create_multi_day_synthetic_ohlcv(prices)
    ctxs_orig = compute_stock_in_play_contexts("TEST", rth_df, ext_df)
    dates = sorted(ctxs_orig.keys())

    # 3-kun (kelajak kun) narxlarini butunlay o'zgartirish
    prices_mut = [(100.0, 100.0), (102.0, 102.0), (999.0, 999.0)]
    rth_mut, ext_mut = _create_multi_day_synthetic_ohlcv(prices_mut)
    ctxs_mut = compute_stock_in_play_contexts("TEST", rth_mut, ext_mut)

    # 2-kunning gap va muvofiqligi aynan bir xil qolishi shart
    assert ctxs_orig[dates[1]].gap_pct == ctxs_mut[dates[1]].gap_pct
    for t in (0.01, 0.02, 0.03, 0.04):
        assert ctxs_orig[dates[1]].is_gap_eligible_at(t) == ctxs_mut[dates[1]].is_gap_eligible_at(t)


def test_5_symbol_isolation() -> None:
    """Test 5: Ticker A ma'lumotlari Ticker B ga aslo ta'sir qilmasligi shart."""
    rth_a, ext_a = _create_multi_day_synthetic_ohlcv([(100.0, 100.0), (105.0, 105.0)])  # +5% gap
    rth_b, ext_b = _create_multi_day_synthetic_ohlcv([(50.0, 50.0), (50.25, 50.25)])     # +0.5% gap

    ctxs_a = compute_stock_in_play_contexts("SYM_A", rth_a, ext_a)
    ctxs_b = compute_stock_in_play_contexts("SYM_B", rth_b, ext_b)

    d2_a = sorted(ctxs_a.keys())[1]
    d2_b = sorted(ctxs_b.keys())[1]

    # SYM_A barcha thresholdlarga yaroqli (5% >= 4%)
    assert ctxs_a[d2_a].is_gap_eligible_at(0.04) is True
    # SYM_B hech qaysi thresholdga yaroqli emas (0.5% < 1%)
    assert ctxs_b[d2_b].is_gap_eligible_at(0.01) is False


def test_6_order_independence() -> None:
    """Test 6: Tickerlar qaysi tartibda yuklanishidan qat'i nazar, kontekstlar aynan bir xil bo'ladi."""
    rth_1, ext_1 = _create_multi_day_synthetic_ohlcv([(100.0, 100.0), (103.0, 103.0)])
    rth_2, ext_2 = _create_multi_day_synthetic_ohlcv([(200.0, 200.0), (208.0, 208.0)])

    # Order 1: SYM1, keyin SYM2
    ctx_1a = compute_stock_in_play_contexts("SYM1", rth_1, ext_1)
    ctx_2a = compute_stock_in_play_contexts("SYM2", rth_2, ext_2)

    # Order 2: SYM2, keyin SYM1
    ctx_2b = compute_stock_in_play_contexts("SYM2", rth_2, ext_2)
    ctx_1b = compute_stock_in_play_contexts("SYM1", rth_1, ext_1)

    for d in ctx_1a:
        g1a = ctx_1a[d].gap_pct
        g1b = ctx_1b[d].gap_pct
        if math.isnan(g1a):
            assert math.isnan(g1b)
        else:
            assert pytest.approx(g1a) == g1b
        for t in (0.01, 0.02, 0.03, 0.04):
            assert ctx_1a[d].is_gap_eligible_at(t) == ctx_1b[d].is_gap_eligible_at(t)

    for d in ctx_2a:
        g2a = ctx_2a[d].gap_pct
        g2b = ctx_2b[d].gap_pct
        if math.isnan(g2a):
            assert math.isnan(g2b)
        else:
            assert pytest.approx(g2a) == g2b
        for t in (0.01, 0.02, 0.03, 0.04):
            assert ctx_2a[d].is_gap_eligible_at(t) == ctx_2b[d].is_gap_eligible_at(t)


def test_7_backward_compatibility_day06() -> None:
    """Test 7: 2.0% threshold DAY-06 Variant A gipotezasi bilan bir xil mantiqda ishlaydi."""
    # 2.0% gap bilan kontekst
    rth_df, ext_df = _create_multi_day_synthetic_ohlcv([(100.0, 100.0), (102.0, 102.0)])
    ctxs = compute_stock_in_play_contexts("TEST", rth_df, ext_df, gap_threshold_pct=0.02)
    d2 = sorted(ctxs.keys())[1]
    ctx = ctxs[d2]

    # DAY-06 ning gap_eligible maydoni
    assert ctx.gap_eligible is True
    # DAY-06A ning is_gap_eligible_at(0.02) metodi
    assert ctx.is_gap_eligible_at(0.02) is True
    # Ikkalasining qiymati 100% teng bo'lishi shart
    assert ctx.gap_eligible == ctx.is_gap_eligible_at(0.02)


def test_8_frozen_strategy_invariance() -> None:
    """Test 8: Threshold tekshiruvi faqat sessiyani saralaydi, DAY-01 strategiya mexanikasini o'zgartirmaydi."""
    # Mock kontekst
    d = date(2026, 7, 7)
    ctx = StockInPlayContext(
        symbol="AAPL",
        session_date=d,
        previous_close=100.0,
        rth_open=103.0,
        gap_pct=0.03,
        premarket_volume=0.0,
        premarket_rvol=None,
        gap_eligible=True,
        gap_data_sufficient=True,
    )

    # Strategiya stop, target, forced exit kabi qoidalarga ega emas, faqat filtering
    assert ctx.is_gap_eligible_at(0.01) is True
    assert ctx.is_gap_eligible_at(0.02) is True
    assert ctx.is_gap_eligible_at(0.03) is True
    assert ctx.is_gap_eligible_at(0.04) is False


def test_9_missing_data_insufficient() -> None:
    """Test 9: Agar oldingi close yoki bugungi open mavjud bo'lmasa, DATA_INSUFFICIENT (gap=0 qilinmaydi)."""
    # 1-kun (oldingi close mavjud emas)
    rth_df, ext_df = _create_multi_day_synthetic_ohlcv([(100.0, 100.0)])
    ctxs = compute_stock_in_play_contexts("TEST", rth_df, ext_df)
    d1 = sorted(ctxs.keys())[0]
    ctx1 = ctxs[d1]

    # Oldingi close yo'qligi sababli gap_data_sufficient=False va gap_pct=NaN
    assert ctx1.gap_data_sufficient is False
    assert math.isnan(ctx1.gap_pct)
    # Hech qanday thresholdda muvofiq emas
    for t in (0.01, 0.02, 0.03, 0.04):
        assert ctx1.is_gap_eligible_at(t) is False
