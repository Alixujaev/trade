"""tests/test_day05_failure_analysis.py: DAY-05 Failure Analysis testlari.

Tekshiruvlar:
1. Time buckets xaritalanishi
2. Exit reason agregatsiyasi
3. RSI va RVOL chegaraviy intervallari
4. Repeated-entry hisob-kitoblari
5. Consecutive loss streaks aniqlanishi
6. Holding duration vaqtlari
7. MFE va MAE hisoblash aniqligi
8. Target excursion (0.5R, 1.0R, 1.5R, 2.0R) tekshiruvi
9. Signal -> Entry gap hisobi
10. Symbol concentration agregatsiyasi
11. Point-in-Time xavfsizligi: MFE/MAE strategiya signaliga aslo ta'sir qilmasligi (post-hoc izolyatsiya).
"""

from __future__ import annotations

from datetime import time
import numpy as np
import pandas as pd
import pytest

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.failure_analysis import (
    DiagnosticTradeRecord,
    compute_group_metrics,
    enrich_trade_record,
    get_duration_bucket,
    get_entry_gap_bucket,
    get_rsi_bucket,
    get_rvol_bucket,
    get_stop_distance_bucket,
    get_time_of_day_bucket,
    map_exit_reason,
    run_day_failure_analysis,
)
from backtest.multi_types import (
    AggregateTradeStats,
    DataCoverageStatus,
    MultiSymbolDayBacktestResult,
    PerSymbolMetrics,
    SymbolCoverage,
    SymbolDistributionStats,
)
from strategy.day.vwap_momentum import evaluate_vwap_momentum


def test_time_of_day_buckets() -> None:
    """Vaqt oralig'i to'g'ri predefined bucketlarga tushishi kerak."""
    assert get_time_of_day_bucket(time(9, 30)) == "09:30–10:00"
    assert get_time_of_day_bucket(time(9, 59)) == "09:30–10:00"
    assert get_time_of_day_bucket(time(10, 0)) == "10:00–11:00"
    assert get_time_of_day_bucket(time(10, 59)) == "10:00–11:00"
    assert get_time_of_day_bucket(time(11, 0)) == "11:00–12:00"
    assert get_time_of_day_bucket(time(12, 0)) == "12:00–14:00"
    assert get_time_of_day_bucket(time(13, 59)) == "12:00–14:00"
    assert get_time_of_day_bucket(time(14, 0)) == "14:00–15:00"
    assert get_time_of_day_bucket(time(15, 0)) == "15:00–15:55"
    assert get_time_of_day_bucket(time(15, 55)) == "15:00–15:55"
    assert get_time_of_day_bucket(time(16, 0)) == "OTHER"


def test_exit_reason_mapping() -> None:
    """Exit sabablari standart nomlarga xaritalanadi."""
    assert map_exit_reason("stop") == "STOP"
    assert map_exit_reason("STOP") == "STOP"
    assert map_exit_reason("target") == "TARGET"
    assert map_exit_reason("forced_eod") == "FORCED_EXIT"
    assert map_exit_reason("end_of_data") == "FORCED_EXIT"
    assert map_exit_reason("max_time") == "FORCED_EXIT"


def test_rsi_and_rvol_bins() -> None:
    """RSI va RVOL chegaraviy qiymatlari to'g'ri deterministik binlarga tushishi kerak."""
    assert get_rsi_bucket(45.0) == "<50"
    assert get_rsi_bucket(49.99) == "<50"
    assert get_rsi_bucket(50.0) == "50–55"
    assert get_rsi_bucket(54.99) == "50–55"
    assert get_rsi_bucket(55.0) == "55–60"
    assert get_rsi_bucket(60.0) == "60–70"
    assert get_rsi_bucket(70.0) == "70+"
    assert get_rsi_bucket(85.0) == "70+"

    assert get_rvol_bucket(0.8) == "<1.0"
    assert get_rvol_bucket(1.0) == "1.0–2.0"
    assert get_rvol_bucket(1.99) == "1.0–2.0"
    assert get_rvol_bucket(2.0) == "2.0–3.0"
    assert get_rvol_bucket(3.0) == "3.0–5.0"
    assert get_rvol_bucket(5.0) == "5.0+"
    assert get_rvol_bucket(8.5) == "5.0+"


def test_duration_and_stop_distance_buckets() -> None:
    """Davomiylik va stop masofasi to'g'ri guruhlanadi."""
    assert get_duration_bucket(3) == "0–5 min"
    assert get_duration_bucket(5) == "5–10 min"
    assert get_duration_bucket(15) == "10–20 min"
    assert get_duration_bucket(25) == "20–30 min"
    assert get_duration_bucket(45) == "30–60 min"
    assert get_duration_bucket(90) == "60–120 min"
    assert get_duration_bucket(150) == "120+ min"

    assert get_stop_distance_bucket(0.002) == "<0.25%"
    assert get_stop_distance_bucket(0.003) == "0.25–0.50%"
    assert get_stop_distance_bucket(0.007) == "0.50–1.00%"
    assert get_stop_distance_bucket(0.015) == "1.00–2.00%"
    assert get_stop_distance_bucket(0.025) == "2.00%+"


def test_mfe_mae_synthetic_calculation() -> None:
    """Sintetik 5m shamlar ustida MFE va MAE aniq hisoblanishi kerak."""
    times = pd.date_range("2026-07-02 09:30", periods=5, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [102.0, 105.0, 106.0, 104.0, 105.0],
            "low":  [99.0,  100.5, 98.0,  102.0, 103.0],
            "close": [101.0, 103.0, 99.0, 103.5, 104.5],
            "volume": [1000] * 5,
        },
        index=times,
    )

    # Trade: setup at times[0], entry at times[1] (open=101.0), exit at times[2] (close=99.0)
    # Stop: 99.0 -> risk = 101.0 - 99.0 = 2.0
    # Window (times[1]..times[2]):
    # max_high = max(105.0, 106.0) = 106.0
    # min_low = min(100.5, 98.0) = 98.0
    trade = DayBacktestTrade(
        symbol="TEST",
        setup_time=times[0],
        entry_time=times[1],
        entry_price=101.0,
        exit_time=times[2],
        exit_price=99.0,
        exit_reason="stop",
        stop_price=99.0,
        target_price=105.0,
        gross_return=(99.0 - 101.0) / 101.0,
        net_return=(99.0 - 101.0) / 101.0,
        risk_per_share=2.0,
        r_multiple=-1.0,
    )

    enriched = enrich_trade_record(trade, df)

    # Entry = 101.0
    # Max High = 106.0 -> MFE = 106.0 - 101.0 = 5.0 -> MFE % = 5.0 / 101.0
    # Min Low = 98.0 -> MAE = 98.0 - 101.0 = -3.0 -> MAE % = -3.0 / 101.0
    # Risk = 2.0 -> MFE R = 5.0 / 2.0 = 2.5R, MAE R = -3.0 / 2.0 = -1.5R
    assert pytest.approx(enriched.mfe_pct, 1e-4) == 5.0 / 101.0
    assert pytest.approx(enriched.mae_pct, 1e-4) == -3.0 / 101.0
    assert enriched.mfe_r is not None
    assert pytest.approx(enriched.mfe_r, 1e-4) == 2.5
    assert enriched.mae_r is not None
    assert pytest.approx(enriched.mae_r, 1e-4) == -1.5

    # Target excursions reached
    assert enriched.target_0_5r_reached is True
    assert enriched.target_1_0r_reached is True
    assert enriched.target_1_5r_reached is True
    assert enriched.target_2_0r_reached is True


def test_signal_entry_gap_calculation() -> None:
    """Signal bar close va entry bar open orasidagi gap to'g'ri o'lchanadi."""
    times = pd.date_range("2026-07-02 09:30", periods=2, freq="5min", tz="America/New_York")
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.5, 101.5],
            "close": [100.0, 102.5],
            "volume": [1000, 1000],
        },
        index=times,
    )

    # Signal close = 100.0, Entry open = 102.0 -> Gap = (102.0 - 100.0) / 100.0 = +2.0%
    trade = DayBacktestTrade(
        symbol="TEST",
        setup_time=times[0],
        entry_time=times[1],
        entry_price=102.0,
        exit_time=times[1],
        exit_price=102.5,
        exit_reason="target",
        gross_return=0.0049,
        net_return=0.0049,
        risk_per_share=1.0,
        r_multiple=0.5,
    )

    enriched = enrich_trade_record(trade, df)
    assert pytest.approx(enriched.signal_entry_gap_pct, 1e-4) == 0.02
    assert get_entry_gap_bucket(enriched.signal_entry_gap_pct) == "positive gap (>+0.05%)"


def test_consecutive_losses_and_repeated_entries() -> None:
    """Ketma-ket zararlar va takroriy kirishlar to'g'ri jamlanadi."""
    t0 = pd.Timestamp("2026-07-02 10:00", tz="America/New_York")
    t1 = pd.Timestamp("2026-07-02 10:30", tz="America/New_York")
    t2 = pd.Timestamp("2026-07-02 11:00", tz="America/New_York")
    t3 = pd.Timestamp("2026-07-03 10:00", tz="America/New_York")

    # 3 trades on day 1 (loss, loss, win), 1 trade on day 2 (loss)
    trades = [
        DayBacktestTrade("AAPL", t0, t0, 100.0, t0, 99.0, "stop", net_return=-0.01, r_multiple=-1.0),
        DayBacktestTrade("AAPL", t1, t1, 100.0, t1, 98.0, "stop", net_return=-0.02, r_multiple=-2.0),
        DayBacktestTrade("AAPL", t2, t2, 100.0, t2, 102.0, "target", net_return=0.02, r_multiple=2.0),
        DayBacktestTrade("AAPL", t3, t3, 100.0, t3, 99.5, "stop", net_return=-0.005, r_multiple=-0.5),
    ]

    from backtest.day_types import DayBacktestResult
    sym_res = DayBacktestResult(
        symbol="AAPL",
        window_start=t0,
        window_end=t3,
        total_sessions=2,
        total_bars=100,
        trades=trades,
        metrics={},
        buy_and_hold_return=0.0,
        time_of_day_breakdown={},
        component_breakdown={},
        sensitivity_results={},
    )

    multi_res = MultiSymbolDayBacktestResult(
        study_window_start=t0,
        study_window_end=t3,
        total_sessions=2,
        universe=["AAPL"],
        tested_symbols=["AAPL"],
        coverage={"AAPL": SymbolCoverage("AAPL", DataCoverageStatus.AVAILABLE)},
        per_symbol_metrics=[],
        aggregate_trade_stats=AggregateTradeStats(4, 1, 3, 0, 25.0, 0.5, -0.003, -1.5, -0.375, -1.0, 1.4),
        symbol_distribution=SymbolDistributionStats(1, 0, 1, 0, -1.5, -1.5, 0, 0, 0),
        slippage_sensitivity={},
        symbol_results={"AAPL": sym_res},
    )

    # Empty ohlcv mock
    analysis = run_day_failure_analysis(multi_res, df_5m_by_symbol={"AAPL": pd.DataFrame()})

    # Loss streak: loss, loss -> streak 2; win -> reset; loss -> streak 1
    # Max streak global = 2
    assert analysis.consecutive_loss_analysis["max_consecutive_losses_global"] == 2
    # Traded sessions: day 1 has 3 trades, day 2 has 1 trade
    rep = analysis.repeated_entry_analysis
    assert rep["total_traded_symbol_sessions"] == 2
    assert rep["frequency_distribution"]["3_trades"]["sessions"] == 1
    assert rep["frequency_distribution"]["1_trade"]["sessions"] == 1
    assert rep["threshold_summary"]["sessions_ge_3_trades"]["count"] == 1


def test_pit_safety_mfe_mae_isolation() -> None:
    """MFE/MAE faqat post-hoc tahlilda ishlatiladi va strategiya signaliga hech qachon ta'sir qilmaydi.

    Adversarial test: entry'dan keyingi kelajak shamlarining narxi keskin o'zgarsa ham,
    signal vaqtidagi qaror 100% bir xil qolishi shart.
    """
    dates = pd.date_range("2026-07-02 09:30", periods=25, freq="5min", tz="America/New_York")
    np.random.seed(42)
    base_price = 100.0 + np.cumsum(np.random.randn(25) * 0.1)

    df_base = pd.DataFrame(
        {
            "open": base_price,
            "high": base_price + 0.2,
            "low": base_price - 0.2,
            "close": base_price,
            "volume": [2000] * 25,
        },
        index=dates,
    )

    # Asl signalni tekshirish (masalan bar 18)
    as_of = dates[18] + pd.Timedelta(minutes=5)
    setup_clean = evaluate_vwap_momentum("AAPL", df_base.iloc[:19], as_of=as_of)

    # Kelajak narxlari (bar 19..24) ni 500 barobar o'zgartiramiz
    df_corrupted_future = df_base.copy()
    df_corrupted_future.iloc[19:, df_corrupted_future.columns.get_loc("high")] = 9999.0
    df_corrupted_future.iloc[19:, df_corrupted_future.columns.get_loc("low")] = 1.0

    # Kelajak o'zgarganda ham bar 18 dagi signal 100% bir xil qolishi shart (causal invariant)
    setup_post_mutation = evaluate_vwap_momentum("AAPL", df_corrupted_future.iloc[:19], as_of=as_of)

    assert setup_clean.status == setup_post_mutation.status
    assert setup_clean.trigger == setup_post_mutation.trigger
    assert pytest.approx(setup_clean.price) == setup_post_mutation.price
    assert pytest.approx(setup_clean.vwap) == setup_post_mutation.vwap
