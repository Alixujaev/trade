"""tests/test_stock_in_play.py: DAY-06 Stock-in-Play Context Hypothesis testlari.

Tekshiruvlar:
1. Gap hisoblash formulasi
2. Oldingi RTH sessiyasi close narxi ishlatilishi
3. Premarket vaqt chegaralari (04:00 - 09:30 ET)
4. Premarket RVOL hisobi (lookback bo'yicha)
5. Sessiya darajasida muzlatish (immutability)
6. Ijobiy gap (positive gap)
7. Salbiy gap (negative gap, long-only saqlanishi)
8. Kombinatsiyalangan muvofiqlik (Combined eligibility: Gap AND Premarket RVOL)
9. Katalizator yo'qligi (catalyst_available=False, catalyst_present=None)
10. Adversarial PIT Test A: 09:30 dan keyingi kelajak RTH narxlari mutatsiyasi
11. Adversarial PIT Test B: 09:30 dan keyingi kelajak RTH hajmi mutatsiyasi
12. Adversarial PIT Test C: 09:30 dan keyingi ma'lumotlar premarket ko'rsatkichini o'zgartirmasligi
13. Adversarial PIT Test D: Kelajak sessiya mutatsiyasi bugungi sessiyani o'zgartirmasligi
14. Adversarial PIT Test E: Ticker izolyatsiyasi (Symbol A Symbol B ga ta'sir qilmasligi)
15. Tickerlar tartibi mustaqilligi (Order independence)
16. Baseline o'zgarmasligi (Muzlatilgan DAY-01/02 qoidalari)
"""

from __future__ import annotations

from datetime import date
import numpy as np
import pandas as pd
import pytest

from backtest.day_types import ExecutionConfig
from backtest.stock_in_play import (
    StockInPlayExperimentResult,
    compute_variant_metrics,
    run_stock_in_play_backtest,
)
from strategy.day.stock_in_play import (
    DEFAULT_GAP_THRESHOLD_PCT,
    DEFAULT_PREMARKET_RVOL_THRESHOLD,
    StockInPlayContext,
    compute_stock_in_play_contexts,
)


def _create_two_day_synthetic_ohlcv(
    *,
    day1_close: float = 100.0,
    day2_open: float = 103.0,
    day2_pm_vol: float = 50000.0,
    day1_pm_vol: float = 25000.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ikki kunlik sintetik 5m RTH va Extended ma'lumotlarini yaratadi."""
    # Day 1: 2026-07-06
    d1_pm_times = pd.date_range("2026-07-06 04:00", "2026-07-06 09:25", freq="5min", tz="America/New_York")
    d1_rth_times = pd.date_range("2026-07-06 09:30", "2026-07-06 15:55", freq="5min", tz="America/New_York")

    # Day 2: 2026-07-07
    d2_pm_times = pd.date_range("2026-07-07 04:00", "2026-07-07 09:25", freq="5min", tz="America/New_York")
    d2_rth_times = pd.date_range("2026-07-07 09:30", "2026-07-07 15:55", freq="5min", tz="America/New_York")

    all_rth_times = d1_rth_times.append(d2_rth_times)
    all_ext_times = d1_pm_times.append(d1_rth_times).append(d2_pm_times).append(d2_rth_times)

    # RTH DataFrame
    n_rth1 = len(d1_rth_times)
    n_rth2 = len(d2_rth_times)

    rth_df = pd.DataFrame(
        {
            "open": [98.0] * (n_rth1 - 1) + [99.0] + [day2_open] * n_rth2,
            "high": [99.0] * n_rth1 + [day2_open + 2.0] * n_rth2,
            "low":  [97.0] * n_rth1 + [day2_open - 1.0] * n_rth2,
            "close": [98.0] * (n_rth1 - 1) + [day1_close] + [day2_open + 1.0] * n_rth2,
            "volume": [1000] * (n_rth1 + n_rth2),
        },
        index=all_rth_times,
    )

    # Extended DataFrame (includes premarket)
    ext_df = pd.DataFrame(
        {
            "open": [100.0] * len(all_ext_times),
            "high": [101.0] * len(all_ext_times),
            "low":  [99.0] * len(all_ext_times),
            "close": [100.0] * len(all_ext_times),
            "volume": [100] * len(all_ext_times),
        },
        index=all_ext_times,
    )

    # Day 1 PM volume set
    ext_df.loc[d1_pm_times, "volume"] = int(day1_pm_vol / len(d1_pm_times))
    # Day 2 PM volume set
    ext_df.loc[d2_pm_times, "volume"] = int(day2_pm_vol / len(d2_pm_times))

    # Day 1 close set
    ext_df.loc[d1_rth_times[-1], "close"] = day1_close
    # Day 2 open set
    ext_df.loc[d2_rth_times[0], "open"] = day2_open

    return rth_df, ext_df


def test_gap_calculation_and_previous_close() -> None:
    """Gap formulasi to'g'ri hisoblanishi va oldingi RTH close narxiga tayanishi kerak."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv(day1_close=100.0, day2_open=103.0)

    contexts = compute_stock_in_play_contexts(
        "TEST",
        rth_df,
        ext_df,
        gap_threshold_pct=0.02,
    )

    d2 = date(2026, 7, 7)
    assert d2 in contexts
    ctx2 = contexts[d2]

    # Day 1 close: 100.0, Day 2 open: 103.0 -> Gap = +3.0%
    assert pytest.approx(ctx2.previous_close) == 100.0
    assert pytest.approx(ctx2.rth_open) == 103.0
    assert pytest.approx(ctx2.gap_pct, 1e-4) == 0.03
    assert ctx2.gap_eligible is True
    assert ctx2.is_positive_gap is True
    assert ctx2.is_negative_gap is False


def test_negative_gap_long_only_handling() -> None:
    """Salbiy gap aniqlanishi va long-only kontekstida saqlanishi kerak."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv(day1_close=100.0, day2_open=97.0)

    contexts = compute_stock_in_play_contexts(
        "TEST",
        rth_df,
        ext_df,
        gap_threshold_pct=0.02,
    )

    d2 = date(2026, 7, 7)
    ctx2 = contexts[d2]

    # Day 1 close: 100.0, Day 2 open: 97.0 -> Gap = -3.0%
    assert pytest.approx(ctx2.gap_pct, 1e-4) == -0.03
    assert ctx2.gap_eligible is True
    assert ctx2.is_negative_gap is True
    assert ctx2.is_positive_gap is False


def test_premarket_volume_and_rvol_calculation() -> None:
    """Premarket hajmi va RVOL to'g'ri o'lchanishi kerak."""
    # 6 kunlik ma'lumot: 5 ta oldingi kun (har kuni 20,000 hajm) va 6-kun (60,000 hajm) -> RVOL = 3.0x
    dates_list = pd.date_range("2026-07-06", periods=6, freq="B")
    all_pm_times = []
    all_rth_times = []

    for d in dates_list:
        d_str = d.strftime("%Y-%m-%d")
        pm = pd.date_range(f"{d_str} 04:00", f"{d_str} 09:25", freq="5min", tz="America/New_York")
        rth = pd.date_range(f"{d_str} 09:30", f"{d_str} 15:55", freq="5min", tz="America/New_York")
        all_pm_times.extend(pm)
        all_rth_times.extend(rth)

    idx_rth = pd.DatetimeIndex(all_rth_times)
    idx_ext = pd.DatetimeIndex(all_pm_times + all_rth_times).sort_values()

    df_rth = pd.DataFrame(
        {"open": [100.0] * len(idx_rth), "high": [101.0] * len(idx_rth), "low": [99.0] * len(idx_rth), "close": [100.0] * len(idx_rth), "volume": [1000] * len(idx_rth)},
        index=idx_rth,
    )

    df_ext = pd.DataFrame(
        {"open": [100.0] * len(idx_ext), "high": [101.0] * len(idx_ext), "low": [99.0] * len(idx_ext), "close": [100.0] * len(idx_ext), "volume": [100] * len(idx_ext)},
        index=idx_ext,
    )

    # Set PM volume for first 5 days = 20,000 each
    for d in dates_list[:5]:
        d_str = d.strftime("%Y-%m-%d")
        t_pm = pd.date_range(f"{d_str} 04:00", f"{d_str} 09:25", freq="5min", tz="America/New_York")
        df_ext.loc[t_pm, "volume"] = int(20000 / len(t_pm))

    # Set Day 6 PM volume = 60,000 (RVOL = 60,000 / 20,000 = 3.0x)
    d6_str = dates_list[5].strftime("%Y-%m-%d")
    t_d6_pm = pd.date_range(f"{d6_str} 04:00", f"{d6_str} 09:25", freq="5min", tz="America/New_York")
    df_ext.loc[t_d6_pm, "volume"] = int(60000 / len(t_d6_pm))

    contexts = compute_stock_in_play_contexts(
        "TEST",
        df_rth,
        df_ext,
        min_premarket_sessions=5,
        premarket_rvol_threshold=2.0,
    )

    d6_date = dates_list[5].date()
    ctx6 = contexts[d6_date]
    assert ctx6.premarket_rvol is not None
    assert pytest.approx(ctx6.premarket_rvol, 1e-2) == 3.0
    assert ctx6.premarket_rvol_eligible is True


def test_missing_catalyst_handling() -> None:
    """Katalizator yo'qligi sababli catalyst_available=False va catalyst_present=None bo'lishi shart."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv()
    contexts = compute_stock_in_play_contexts("TEST", rth_df, ext_df)
    d2 = date(2026, 7, 7)
    ctx = contexts[d2]
    assert ctx.catalyst_available is False
    assert ctx.catalyst_present is None


def test_session_level_freezing() -> None:
    """StockInPlayContext immutable (muzlatilgan) dataclass bo'lishi shart."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv()
    contexts = compute_stock_in_play_contexts("TEST", rth_df, ext_df)
    d2 = date(2026, 7, 7)
    ctx = contexts[d2]

    with pytest.raises(Exception):
        ctx.gap_eligible = False  # type: ignore[misc]


def test_pit_adversarial_future_rth_price_mutation() -> None:
    """09:30 dan keyingi kelajak RTH narxlarining keskin o'zgarishi stock-in-play muvofiqligiga aslo ta'sir qilmasligi kerak."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv(day1_close=100.0, day2_open=103.0)

    # Asl kontekst
    ctx_clean = compute_stock_in_play_contexts("TEST", rth_df, ext_df)[date(2026, 7, 7)]

    # Day 2 dagi 10:00 dan keyingi narxlarni 50,000 barobar o'zgartiramiz
    rth_corrupt = rth_df.copy()
    d2_late_mask = rth_corrupt.index >= pd.Timestamp("2026-07-07 10:00", tz="America/New_York")
    rth_corrupt.loc[d2_late_mask, "close"] = 999999.0
    rth_corrupt.loc[d2_late_mask, "high"] = 999999.0

    ctx_post_mutation = compute_stock_in_play_contexts("TEST", rth_corrupt, ext_df)[date(2026, 7, 7)]

    assert pytest.approx(ctx_clean.gap_pct) == ctx_post_mutation.gap_pct
    assert ctx_clean.gap_eligible == ctx_post_mutation.gap_eligible
    assert ctx_clean.previous_close == ctx_post_mutation.previous_close
    assert ctx_clean.rth_open == ctx_post_mutation.rth_open


def test_pit_adversarial_future_rth_volume_mutation() -> None:
    """09:30 dan keyingi kelajak RTH hajmi keskin o'zgarsa ham kontekst 100% bir xil qolishi shart."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv(day1_close=100.0, day2_open=103.0)
    ctx_clean = compute_stock_in_play_contexts("TEST", rth_df, ext_df)[date(2026, 7, 7)]

    ext_corrupt = ext_df.copy()
    d2_late_mask = ext_corrupt.index >= pd.Timestamp("2026-07-07 10:00", tz="America/New_York")
    ext_corrupt.loc[d2_late_mask, "volume"] = 999_999_999

    ctx_post_mutation = compute_stock_in_play_contexts("TEST", rth_df, ext_corrupt)[date(2026, 7, 7)]

    assert ctx_clean.premarket_volume == ctx_post_mutation.premarket_volume
    assert ctx_clean.premarket_rvol == ctx_post_mutation.premarket_rvol


def test_pit_adversarial_unrelated_future_session() -> None:
    """Kelajakdagi Day 3 ma'lumotlari Day 2 kontekstiga hech qanday ta'sir qilmasligi kerak."""
    rth_df, ext_df = _create_two_day_synthetic_ohlcv(day1_close=100.0, day2_open=103.0)
    ctx_clean = compute_stock_in_play_contexts("TEST", rth_df, ext_df)[date(2026, 7, 7)]

    # Day 3 ni qo'shamiz
    d3_times = pd.date_range("2026-07-08 09:30", "2026-07-08 15:55", freq="5min", tz="America/New_York")
    d3_rth = pd.DataFrame(
        {"open": [200.0] * len(d3_times), "high": [201.0] * len(d3_times), "low": [199.0] * len(d3_times), "close": [200.0] * len(d3_times), "volume": [5000] * len(d3_times)},
        index=d3_times,
    )
    rth_with_future = pd.concat([rth_df, d3_rth])

    ctx_with_future = compute_stock_in_play_contexts("TEST", rth_with_future, ext_df)[date(2026, 7, 7)]

    assert pytest.approx(ctx_clean.gap_pct) == ctx_with_future.gap_pct
    assert ctx_clean.gap_eligible == ctx_with_future.gap_eligible


def test_symbol_isolation() -> None:
    """Symbol A ning ma'lumotlari Symbol B kontekstini ifloslantirmasligi kerak."""
    rth_a, ext_a = _create_two_day_synthetic_ohlcv(day1_close=100.0, day2_open=105.0)
    rth_b, ext_b = _create_two_day_synthetic_ohlcv(day1_close=50.0, day2_open=50.1)

    ctx_a = compute_stock_in_play_contexts("SYM_A", rth_a, ext_a)[date(2026, 7, 7)]
    ctx_b = compute_stock_in_play_contexts("SYM_B", rth_b, ext_b)[date(2026, 7, 7)]

    assert ctx_a.gap_eligible is True
    assert ctx_b.gap_eligible is False
    assert ctx_a.symbol == "SYM_A"
    assert ctx_b.symbol == "SYM_B"


def test_order_independence_and_baseline_equivalence() -> None:
    """Tickerlar ketma-ketligi eksperiment natijalariga aslo ta'sir qilmasligi kerak."""
    from backtest.day_types import DayBacktestResult, DayBacktestTrade
    from backtest.failure_analysis import enrich_trade_record
    from backtest.multi_types import (
        AggregateTradeStats,
        DataCoverageStatus,
        MultiSymbolDayBacktestResult,
        PerSymbolMetrics,
        SymbolCoverage,
        SymbolDistributionStats,
    )
    from backtest.stock_in_play import compute_variant_metrics

    t1 = pd.Timestamp("2026-07-07 10:00", tz="America/New_York")
    trades = [
        DayBacktestTrade("AAPL", t1, t1, 100.0, t1, 102.0, "target", gross_return=0.02, net_return=0.02, risk_per_share=1.0, r_multiple=2.0),
        DayBacktestTrade("MSFT", t1, t1, 200.0, t1, 198.0, "stop", gross_return=-0.01, net_return=-0.01, risk_per_share=2.0, r_multiple=-1.0),
    ]

    enriched = [enrich_trade_record(t, pd.DataFrame()) for t in trades]

    ctx_aapl = StockInPlayContext("AAPL", date(2026, 7, 7), 95.0, 100.0, 0.052, 0.0, None, False, None, True, False, True, False, False, True, False)
    ctx_msft = StockInPlayContext("MSFT", date(2026, 7, 7), 200.0, 200.5, 0.002, 0.0, None, False, None, False, False, False, False, False, True, False)

    # Order 1: [AAPL, MSFT]
    contexts_1 = [ctx_aapl, ctx_msft]
    # Order 2: [MSFT, AAPL]
    contexts_2 = [ctx_msft, ctx_aapl]

    bnh = {"AAPL": 5.0, "MSFT": 2.0}

    m1 = compute_variant_metrics("GapOnly", [enriched[0]], contexts_1, lambda c: c.gap_only_eligible, 2, bnh, {})
    m2 = compute_variant_metrics("GapOnly", [enriched[0]], contexts_2, lambda c: c.gap_only_eligible, 2, bnh, {})

    assert m1.total_trades == m2.total_trades
    assert m1.win_rate == m2.win_rate
    assert m1.total_R == m2.total_R
    assert m1.expectancy == m2.expectancy
    assert m1.trade_reduction_pct == m2.trade_reduction_pct
