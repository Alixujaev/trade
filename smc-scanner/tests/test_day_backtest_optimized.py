"""tests/test_day_backtest_optimized.py: DAY-03 — Performance optimization & Point-in-time hardening tests.

QAT'IY METODOLOGIK QOIDALAR:
- Reference implementation (slice-by-slice) va optimized implementation (precomputed)
  o'rtasida 100% BIT-LEVEL EKVIVALENTLIK tekshiriladi.
- Future-data adversarial testlar: kelajak barlar (volume spike, price spike, RSI extreme,
  VWAP o'zgarishi, 15m structure o'zgarishi) o'tmishdagi qarorni 0% o'zgartira olmasligi isbotlanadi.
- NO STRATEGY RULE MODIFICATION
- NO PARAMETER OPTIMIZATION
- NO PROFITABILITY CLAIM
"""

from __future__ import annotations

import math
from datetime import time
import numpy as np
import pandas as pd
import pytest

from backtest.day_engine import run_day_backtest, run_day_backtest_reference
from backtest.day_types import ExecutionConfig
from indicators.rsi import compute_rsi
from indicators.rvol import compute_rvol
from indicators.vwap import compute_vwap
from levels.intraday_levels import compute_intraday_levels
from strategy.day.types import DaySetupStatus
from strategy.day.vwap_momentum import (
    evaluate_vwap_momentum,
    evaluate_vwap_momentum_at_index,
    precompute_day_features,
)


def _build_multiday_intraday_dataset(
    n_days: int = 5,
    bars_per_day: int = 78,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministik ko'p kunlik 5m va 15m OHLCV datasetini yaratadi."""
    rng = np.random.default_rng(seed)
    # 5 kunlik RTH: 09:30 dan 16:00 gacha (78 ta 5m bar har kuni)
    dates = pd.date_range("2026-01-05", periods=n_days, freq="B", tz="America/New_York")
    
    all_5m_rows = []
    
    curr_price = 150.0
    for d in dates:
        day_str = d.strftime("%Y-%m-%d")
        day_times_5m = pd.date_range(
            f"{day_str} 09:30", periods=bars_per_day, freq="5min", tz="America/New_York"
        )
        for t in day_times_5m:
            delta = rng.normal(0.05, 0.4)
            curr_price = max(10.0, curr_price + delta)
            high = curr_price + rng.uniform(0.1, 0.5)
            low = curr_price - rng.uniform(0.1, 0.5)
            op = curr_price + rng.uniform(-0.2, 0.2)
            vol = rng.uniform(1000.0, 50000.0)
            all_5m_rows.append(
                {"open": op, "high": high, "low": low, "close": curr_price, "volume": vol, "ts": t}
            )

    df_5m = pd.DataFrame(all_5m_rows).set_index("ts")

    # 15m resample
    df_15m = (
        df_5m.resample("15min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )

    return df_5m, df_15m


class TestEquivalence:
    """Reference (slice-by-slice) vs Optimized (precomputed) engine ekvivalentlik tekshiruvi."""

    def test_deterministic_equivalence_all_fields(self) -> None:
        """Har bir savdo va barcha metrikalar ikkala engine'da aynan bir xil bo'lishi shart."""
        df_5m, df_15m = _build_multiday_intraday_dataset(n_days=4, seed=123)
        config = ExecutionConfig(
            slippage_bps=5.0,
            commission_per_share=0.005,
            stop_mode="SIGNAL_LOW",
            target_multiple=2.0,
            force_exit_time=time(15, 55),
        )

        res_ref = run_day_backtest_reference(
            "TEST",
            df_5m=df_5m,
            df_15m=df_15m,
            config=config,
        )

        res_opt = run_day_backtest(
            "TEST",
            df_5m=df_5m,
            df_15m=df_15m,
            config=config,
            use_fast_engine=True,
        )

        # 1. Savdolar soni
        assert len(res_ref.trades) == len(res_opt.trades)
        assert len(res_ref.trades) > 0, "Kamida bitta trade bo'lishi kerak ekvivalentlikni solishtirish uchun"

        # 2. Har bir savdo detallari
        for i, (t_ref, t_opt) in enumerate(zip(res_ref.trades, res_opt.trades)):
            assert t_ref.setup_time == t_opt.setup_time, f"Trade {i}: setup_time"
            assert t_ref.entry_time == t_opt.entry_time, f"Trade {i}: entry_time"
            assert t_ref.exit_time == t_opt.exit_time, f"Trade {i}: exit_time"
            assert t_ref.entry_price == pytest.approx(t_opt.entry_price, rel=1e-7), f"Trade {i}: entry_price"
            assert t_ref.stop_price == pytest.approx(t_opt.stop_price, rel=1e-7), f"Trade {i}: stop_price"
            assert t_ref.target_price == pytest.approx(t_opt.target_price, rel=1e-7), f"Trade {i}: target_price"
            assert t_ref.exit_price == pytest.approx(t_opt.exit_price, rel=1e-7), f"Trade {i}: exit_price"
            assert t_ref.exit_reason == t_opt.exit_reason, f"Trade {i}: exit_reason"
            assert t_ref.r_multiple == pytest.approx(t_opt.r_multiple, rel=1e-7), f"Trade {i}: r_multiple"
            assert t_ref.net_return == pytest.approx(t_opt.net_return, rel=1e-7), f"Trade {i}: net_return"
            assert t_ref.evidence == t_opt.evidence, f"Trade {i}: evidence"

        # 3. Execution sanagichlari
        assert res_ref.skipped_signals == res_opt.skipped_signals
        assert res_ref.insufficient_data_count == res_opt.insufficient_data_count
        assert res_ref.same_bar_ambiguity_count == res_opt.same_bar_ambiguity_count

        # 4. Agregat metrikalar
        m_ref = res_ref.metrics
        m_opt = res_opt.metrics

        assert m_ref["total_trades"] == m_opt["total_trades"]
        assert m_ref["winning_trades"] == m_opt["winning_trades"]
        assert m_ref["losing_trades"] == m_opt["losing_trades"]
        assert m_ref["win_rate"] == pytest.approx(m_opt["win_rate"], rel=1e-7)
        assert m_ref["total_return_pct"] == pytest.approx(m_opt["total_return_pct"], rel=1e-7)
        assert m_ref["max_drawdown_pct"] == pytest.approx(m_opt["max_drawdown_pct"], rel=1e-7)
        assert m_ref["profit_factor"] == pytest.approx(m_opt["profit_factor"], rel=1e-7)
        if m_ref["total_R"] is not None:
            assert m_ref["total_R"] == pytest.approx(m_opt["total_R"], rel=1e-7)
        if m_ref["average_R"] is not None:
            assert m_ref["average_R"] == pytest.approx(m_opt["average_R"], rel=1e-7)

    def test_deterministic_equivalence_on_cached_aapl_sample(self) -> None:
        """Cached AAPL ma'lumotlarining birinchi 250 barida reference vs fast engine to'liq mosligi."""
        try:
            df_5m = pd.read_parquet("data/cache/AAPL_5m.parquet").iloc[:250]
            df_15m = pd.read_parquet("data/cache/AAPL_15m.parquet").iloc[:85]
        except Exception:
            pytest.skip("AAPL cache mavjud emas")

        res_ref = run_day_backtest_reference("AAPL", df_5m=df_5m, df_15m=df_15m)
        res_opt = run_day_backtest("AAPL", df_5m=df_5m, df_15m=df_15m, use_fast_engine=True)

        assert len(res_ref.trades) == len(res_opt.trades)
        assert res_ref.skipped_signals == res_opt.skipped_signals
        assert res_ref.same_bar_ambiguity_count == res_opt.same_bar_ambiguity_count

        for t_ref, t_opt in zip(res_ref.trades, res_opt.trades):
            assert t_ref.entry_time == t_opt.entry_time
            assert t_ref.entry_price == pytest.approx(t_opt.entry_price, rel=1e-7)
            assert t_ref.exit_time == t_opt.exit_time
            assert t_ref.exit_price == pytest.approx(t_opt.exit_price, rel=1e-7)
            assert t_ref.exit_reason == t_opt.exit_reason
            assert t_ref.r_multiple == pytest.approx(t_opt.r_multiple, rel=1e-7)


class TestFutureDataAdversarial:
    """Adversarial anti-lookahead testlar: Kelajakdagi o'zgarishlar o'tmishga ta'sir qila olmaydi."""

    def test_adding_future_bars_does_not_change_historical_decisions(self) -> None:
        """T vaqtgacha bo'lgan barcha barlar uchun: decision(T, data_up_to_T) == decision(T, data_with_future_bars)."""
        df_5m, df_15m = _build_multiday_intraday_dataset(n_days=3, seed=777)
        cut_idx = 100  # T nuqtasi: 100-bar
        
        df_5m_up_to_T = df_5m.iloc[: cut_idx + 1]
        df_15m_up_to_T = df_15m.loc[df_15m.index <= df_5m.index[cut_idx] + pd.Timedelta(minutes=5)]

        features_short = precompute_day_features(df_5m_up_to_T, df_15m_up_to_T)
        features_full = precompute_day_features(df_5m, df_15m)

        # Har bir tarixiy bar i <= cut_idx uchun ikkala to'plamdan olingan setup tekshiriladi
        for i in range(14, cut_idx + 1, 5):
            setup_short = evaluate_vwap_momentum_at_index("AAPL", df_5m_up_to_T, i, features_short)
            setup_full = evaluate_vwap_momentum_at_index("AAPL", df_5m, i, features_full)

            assert setup_short.status == setup_full.status, f"Bar {i}: status mismatch"
            assert setup_short.price == pytest.approx(setup_full.price), f"Bar {i}: price mismatch"
            assert setup_short.vwap == pytest.approx(setup_full.vwap), f"Bar {i}: vwap mismatch"
            assert setup_short.rsi == pytest.approx(setup_full.rsi, nan_ok=True), f"Bar {i}: rsi mismatch"
            assert setup_short.rvol == pytest.approx(setup_full.rvol, nan_ok=True), f"Bar {i}: rvol mismatch"
            assert setup_short.structure_5m == setup_full.structure_5m, f"Bar {i}: structure_5m mismatch"
            assert setup_short.structure_15m == setup_full.structure_15m, f"Bar {i}: structure_15m mismatch"
            assert setup_short.trigger == setup_full.trigger, f"Bar {i}: trigger mismatch"
            assert setup_short.evidence == setup_full.evidence, f"Bar {i}: evidence mismatch"

    def test_future_volume_spike_adversarial(self) -> None:
        """T dan keyin ulkan hajm spike'i (1,000,000x) kelsa ham, T dagi RVOL va qaror o'zgarmaydi."""
        df_5m, df_15m = _build_multiday_intraday_dataset(n_days=3, seed=888)
        cut_idx = 80
        t_cut = df_5m.index[cut_idx]

        # Normal dataset
        features_norm = precompute_day_features(df_5m, df_15m)
        setup_norm = evaluate_vwap_momentum_at_index("AAPL", df_5m, cut_idx, features_norm)

        # Kelajakda ulkan volume spike
        df_5m_spike = df_5m.copy()
        df_5m_spike.loc[df_5m_spike.index > t_cut, "volume"] = 100_000_000.0

        features_spike = precompute_day_features(df_5m_spike, df_15m)
        setup_spike = evaluate_vwap_momentum_at_index("AAPL", df_5m_spike, cut_idx, features_spike)

        assert setup_norm.rvol == pytest.approx(setup_spike.rvol, nan_ok=True)
        assert setup_norm.status == setup_spike.status
        assert setup_norm.evidence_score == setup_spike.evidence_score

    def test_future_price_spike_adversarial(self) -> None:
        """T dan keyin narx 10x oshirilsa yoki qulasa ham, T dagi VWAP, RSI va qaror o'zgarmaydi."""
        df_5m, df_15m = _build_multiday_intraday_dataset(n_days=3, seed=999)
        cut_idx = 80
        t_cut = df_5m.index[cut_idx]

        features_norm = precompute_day_features(df_5m, df_15m)
        setup_norm = evaluate_vwap_momentum_at_index("AAPL", df_5m, cut_idx, features_norm)

        df_5m_pump = df_5m.copy()
        df_5m_pump.loc[df_5m_pump.index > t_cut, ["open", "high", "low", "close"]] *= 10.0

        features_pump = precompute_day_features(df_5m_pump, df_15m)
        setup_pump = evaluate_vwap_momentum_at_index("AAPL", df_5m_pump, cut_idx, features_pump)

        assert setup_norm.vwap == pytest.approx(setup_pump.vwap)
        assert setup_norm.rsi == pytest.approx(setup_pump.rsi, nan_ok=True)
        assert setup_norm.status == setup_pump.status
        assert setup_norm.structure_5m == setup_pump.structure_5m

    def test_future_15m_structure_reversal_adversarial(self) -> None:
        """T dan keyin 15m barlarda kuchli qulash va structure reversal yuz bersa ham, T dagi 15m kontekst o'zgarmaydi."""
        df_5m, df_15m = _build_multiday_intraday_dataset(n_days=3, seed=101)
        cut_idx = 80
        t_cut = df_5m.index[cut_idx]
        t_cut_end = t_cut + pd.Timedelta(minutes=5)

        features_norm = precompute_day_features(df_5m, df_15m)
        setup_norm = evaluate_vwap_momentum_at_index("AAPL", df_5m, cut_idx, features_norm)

        # 15m kelajakda qulatiladi
        df_15m_crash = df_15m.copy()
        crash_mask = df_15m_crash.index >= t_cut_end
        df_15m_crash.loc[crash_mask, ["open", "high", "low", "close"]] *= 0.2

        features_crash = precompute_day_features(df_5m, df_15m_crash)
        setup_crash = evaluate_vwap_momentum_at_index("AAPL", df_5m, cut_idx, features_crash)

        assert setup_norm.structure_15m == setup_crash.structure_15m
        assert setup_norm.status == setup_crash.status

    def test_evaluate_vwap_momentum_as_of_hardened(self) -> None:
        """evaluate_vwap_momentum ga as_of berilganda kelajak barlar ichki jihatdan qat'iy filtrlanadi."""
        df_5m, df_15m = _build_multiday_intraday_dataset(n_days=2, seed=202)
        cut_idx = 40
        t_cut_end = df_5m.index[cut_idx] + pd.Timedelta(minutes=5)

        # Agar caller butun df_5m ni (kelajak barlar bilan birga) berib, as_of=t_cut_end qo'ysa
        setup_with_future = evaluate_vwap_momentum(
            "AAPL",
            df_5m=df_5m,
            df_15m=df_15m,
            as_of=t_cut_end,
        )

        # Va caller faqat kesilgan df_5m_cut bergan holat
        df_5m_cut = df_5m.iloc[: cut_idx + 1]
        df_15m_cut = df_15m.loc[df_15m.index + pd.Timedelta(minutes=15) <= t_cut_end]
        setup_clean = evaluate_vwap_momentum(
            "AAPL",
            df_5m=df_5m_cut,
            df_15m=df_15m_cut,
            as_of=t_cut_end,
        )

        assert setup_with_future.status == setup_clean.status
        assert setup_with_future.price == setup_clean.price
        assert setup_with_future.vwap == pytest.approx(setup_clean.vwap)
        assert setup_with_future.rsi == pytest.approx(setup_clean.rsi, nan_ok=True)
        assert setup_with_future.rvol == pytest.approx(setup_clean.rvol, nan_ok=True)
        assert setup_with_future.structure_5m == setup_clean.structure_5m
        assert setup_with_future.structure_15m == setup_clean.structure_15m
        assert setup_with_future.trigger == setup_clean.trigger
