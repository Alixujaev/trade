"""tests/test_multi_symbol.py: DAY-04 — Multi-Symbol Validation, PIT Adversarial, and Aggregation Tests."""

from __future__ import annotations

import math
from datetime import datetime
import numpy as np
import pandas as pd
import pytest

from backtest.day_types import ExecutionConfig
from backtest.multi_symbol import (
    format_multi_symbol_report,
    run_multi_symbol_day_backtest,
)
from backtest.multi_types import DataCoverageStatus
from config.day_universe import (
    FROZEN_DAY_UNIVERSE,
    MARKET_BENCHMARK_SYMBOLS,
    get_day_universe,
    normalize_symbol,
    validate_universe_symbols,
)
from data.bars import filter_closed_bars
from data.provider import DataProvider
from strategy.day.vwap_momentum import (
    evaluate_vwap_momentum_at_index,
    precompute_day_features,
)


def _create_synthetic_symbol_bars(
    start_str: str = "2026-01-05 09:30",
    n_bars: int = 150,
    base_price: float = 100.0,
    drift: float = 0.05,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministik 5m va 15m sinov ma'lumotlarini yaratadi."""
    rng = np.random.default_rng(seed)
    idx_5m = pd.date_range(start_str, periods=n_bars, freq="5min", tz="America/New_York")
    
    closes = []
    curr = base_price
    for _ in range(n_bars):
        curr += rng.normal(drift, 0.3)
        curr = max(5.0, curr)
        closes.append(curr)

    highs = [c + rng.uniform(0.1, 0.4) for c in closes]
    lows = [c - rng.uniform(0.1, 0.4) for c in closes]
    opens = [c + rng.uniform(-0.1, 0.1) for c in closes]
    vols = [float(rng.uniform(1000.0, 5000.0)) for _ in range(n_bars)]

    df_5m = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=idx_5m,
    )
    df_15m = (
        df_5m.resample("15min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    return df_5m, df_15m


class MockMultiDataProvider(DataProvider):
    """Ko'p aksiyali testlar uchun mock DataProvider."""

    def __init__(self, data_map: dict[str, tuple[pd.DataFrame, pd.DataFrame]]) -> None:
        self.data_map = data_map

    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        *,
        use_cache: bool = True,
        include_extended_hours: bool = False,
        closed_only: bool = False,
        as_of: datetime | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        sym = symbol.upper()
        if sym not in self.data_map:
            raise ValueError(f"MockProvider: {sym} topilmadi")
        
        df_5m, df_15m = self.data_map[sym]
        df = df_5m if interval == "5m" else df_15m
        if closed_only and not df.empty:
            df = filter_closed_bars(df, interval, as_of=as_of)
        return df


class TestDayUniverse:
    """1. Universe xususiyatlari tekshiruvi."""

    def test_universe_is_deterministic_and_frozen(self) -> None:
        """Universe o'zgarmas, kamida 20 ta, takrorlanishsiz va katta harflarda bo'lishi shart."""
        univ = get_day_universe()
        assert len(univ) == 25, f"Universe 25 ta aksiyadan iborat bo'lishi kerak, berildi: {len(univ)}"
        assert len(set(univ)) == len(univ), "Universe'da dublikat tickerlar bo'lmasligi kerak"
        for s in univ:
            assert s == s.upper(), f"Ticker katta harfda bo'lishi kerak: {s}"
            assert s.isalpha(), f"Ticker faqat harflardan iborat bo'lishi kerak: {s}"

        # Frozen tuple bilan aynan mosligi
        assert univ == list(FROZEN_DAY_UNIVERSE)

    def test_normalize_symbol_and_validation(self) -> None:
        """Belgilar to'g'ri tozalanishi va tartib saqlanishi kerak."""
        raw = [" aapl ", "msft", "NVDA", "AAPL", ""]
        cleaned = validate_universe_symbols(raw)
        assert cleaned == ["AAPL", "MSFT", "NVDA"]


class TestMultiSymbolRunner:
    """2. Ko'p aksiyali runner va qamrov tekshiruvi."""

    def test_runner_processes_symbols_independently(self) -> None:
        """Har bir aksiya mustaqil ravishda ishlanishi va natija berishi kerak."""
        df_5m_a, df_15m_a = _create_synthetic_symbol_bars("2026-01-05 09:30", 150, base_price=100.0, seed=1)
        df_5m_b, df_15m_b = _create_synthetic_symbol_bars("2026-01-05 09:30", 150, base_price=200.0, seed=2)

        prov = MockMultiDataProvider({
            "SYM_A": (df_5m_a, df_15m_a),
            "SYM_B": (df_5m_b, df_15m_b),
        })

        res = run_multi_symbol_day_backtest(
            symbols=["SYM_A", "SYM_B"],
            provider=prov,
            include_market_context=False,
        )

        assert res.tested_symbols == ["SYM_A", "SYM_B"]
        assert len(res.per_symbol_metrics) == 2
        assert "SYM_A" in res.symbol_results
        assert "SYM_B" in res.symbol_results
        assert res.coverage["SYM_A"].status == DataCoverageStatus.AVAILABLE
        assert res.coverage["SYM_B"].status == DataCoverageStatus.AVAILABLE

    def test_failed_symbol_does_not_corrupt_others(self) -> None:
        """Bitta aksiyada xatolik yuz bersa, boshqa aksiyalar normal ishlashi va qamrovda UNAVAILABLE deb ko'rsatilishi kerak."""
        df_5m_a, df_15m_a = _create_synthetic_symbol_bars("2026-01-05 09:30", 150, base_price=100.0, seed=3)

        prov = MockMultiDataProvider({
            "SYM_GOOD": (df_5m_a, df_15m_a),
            # SYM_BAD yo'q -> xatolik chaqiradi
        })

        res = run_multi_symbol_day_backtest(
            symbols=["SYM_GOOD", "SYM_BAD"],
            provider=prov,
            include_market_context=False,
        )

        assert res.tested_symbols == ["SYM_GOOD"]
        assert res.coverage["SYM_BAD"].status == DataCoverageStatus.UNAVAILABLE
        assert "SYM_GOOD" in res.symbol_results
        assert len(res.per_symbol_metrics) == 1


class TestPointInTimeSafety:
    """3. Qat'iy PIT va Adversarial xavfsizlik tekshiruvlari."""

    def test_a_future_prices_adversarial(self) -> None:
        """Test A: T dan keyingi narxlar ekstremal o'zgartirilsa ham T dagi qaror 100% IDENTICAL bo'lishi shart."""
        df_5m, df_15m = _create_synthetic_symbol_bars("2026-01-05 09:30", 100, seed=10)
        t_cut = 50

        feat_norm = precompute_day_features(df_5m, df_15m)
        dec_norm = evaluate_vwap_momentum_at_index("TEST", df_5m, t_cut, feat_norm)

        # Kelajak narxlarni 5x ga oshiramiz
        df_5m_spike = df_5m.copy()
        df_5m_spike.iloc[t_cut + 1:, df_5m_spike.columns.get_indexer(["open", "high", "low", "close"])] *= 5.0

        feat_spike = precompute_day_features(df_5m_spike, df_15m)
        dec_spike = evaluate_vwap_momentum_at_index("TEST", df_5m_spike, t_cut, feat_spike)

        assert dec_norm.status == dec_spike.status
        assert dec_norm.price == dec_spike.price
        assert dec_norm.vwap == pytest.approx(dec_spike.vwap)
        assert dec_norm.trigger == dec_spike.trigger

    def test_b_future_volume_adversarial(self) -> None:
        """Test B: T dan keyingi hajm 1,000,000 barobarga oshirilsa ham T dagi RVOL va qaror o'zgarmasligi shart."""
        df_5m, df_15m = _create_synthetic_symbol_bars("2026-01-05 09:30", 100, seed=20)
        t_cut = 50

        feat_norm = precompute_day_features(df_5m, df_15m)
        dec_norm = evaluate_vwap_momentum_at_index("TEST", df_5m, t_cut, feat_norm)

        df_5m_vol = df_5m.copy()
        df_5m_vol.iloc[t_cut + 1:, df_5m_vol.columns.get_loc("volume")] *= 1_000_000.0

        feat_vol = precompute_day_features(df_5m_vol, df_15m)
        dec_vol = evaluate_vwap_momentum_at_index("TEST", df_5m_vol, t_cut, feat_vol)

        assert dec_norm.rvol == pytest.approx(dec_vol.rvol, nan_ok=True)
        assert dec_norm.status == dec_vol.status

    def test_c_future_15m_structure_adversarial(self) -> None:
        """Test C: T dan keyingi 15m struktura o'zgartirilsa ham T dagi 15m kontekst o'zgarmaydi."""
        df_5m, df_15m = _create_synthetic_symbol_bars("2026-01-05 09:30", 100, seed=30)
        t_cut = 50
        t_cut_end = df_5m.index[t_cut] + pd.Timedelta(minutes=5)

        feat_norm = precompute_day_features(df_5m, df_15m)
        dec_norm = evaluate_vwap_momentum_at_index("TEST", df_5m, t_cut, feat_norm)

        df_15m_mod = df_15m.copy()
        future_mask = df_15m_mod.index >= t_cut_end
        df_15m_mod.loc[future_mask, ["open", "high", "low", "close"]] *= 0.1

        feat_mod = precompute_day_features(df_5m, df_15m_mod)
        dec_mod = evaluate_vwap_momentum_at_index("TEST", df_5m, t_cut, feat_mod)

        assert dec_norm.structure_15m == dec_mod.structure_15m
        assert dec_norm.status == dec_mod.status

    def test_d_cross_symbol_contamination_adversarial(self) -> None:
        """Test D: A aksiyasining kelajak ma'lumotlari buzilsa ham, B aksiyasining natijasi 100% IDENTICAL qolishi shart."""
        df_5m_a, df_15m_a = _create_synthetic_symbol_bars("2026-01-05 09:30", 120, base_price=100.0, seed=40)
        df_5m_b, df_15m_b = _create_synthetic_symbol_bars("2026-01-05 09:30", 120, base_price=200.0, seed=50)

        # Baseline: normal A va B
        prov_norm = MockMultiDataProvider({
            "SYM_A": (df_5m_a, df_15m_a),
            "SYM_B": (df_5m_b, df_15m_b),
        })
        res_norm = run_multi_symbol_day_backtest(symbols=["SYM_A", "SYM_B"], provider=prov_norm, include_market_context=False)

        # A ning kelajagini zaharlaymiz (narx va hajm buziladi)
        df_5m_a_polluted = df_5m_a.copy()
        df_5m_a_polluted.iloc[60:, df_5m_a_polluted.columns.get_indexer(["open", "high", "low", "close"])] *= 10.0
        df_5m_a_polluted.iloc[60:, df_5m_a_polluted.columns.get_loc("volume")] *= 1000.0

        prov_polluted = MockMultiDataProvider({
            "SYM_A": (df_5m_a_polluted, df_15m_a),
            "SYM_B": (df_5m_b, df_15m_b),  # B ga tegmadik
        })
        res_polluted = run_multi_symbol_day_backtest(symbols=["SYM_A", "SYM_B"], provider=prov_polluted, include_market_context=False)

        # B natijalari ikkalasida ham 100% bir xil bo'lishi shart
        m_b_norm = res_norm.symbol_results["SYM_B"]
        m_b_polluted = res_polluted.symbol_results["SYM_B"]

        assert len(m_b_norm.trades) == len(m_b_polluted.trades)
        for t1, t2 in zip(m_b_norm.trades, m_b_polluted.trades):
            assert t1.entry_time == t2.entry_time
            assert t1.entry_price == t2.entry_price
            assert t1.exit_price == t2.exit_price
            assert t1.net_return == t2.net_return
            assert t1.exit_reason == t2.exit_reason

    def test_e_order_independence(self) -> None:
        """Test E: Aksiyalar ketma-ketligi ([A, B] vs [B, A]) natijalarni o'zgartirmasligi shart (no global mutable state)."""
        df_5m_a, df_15m_a = _create_synthetic_symbol_bars("2026-01-05 09:30", 120, base_price=100.0, seed=60)
        df_5m_b, df_15m_b = _create_synthetic_symbol_bars("2026-01-05 09:30", 120, base_price=200.0, seed=70)

        prov = MockMultiDataProvider({
            "SYM_A": (df_5m_a, df_15m_a),
            "SYM_B": (df_5m_b, df_15m_b),
        })

        res_order1 = run_multi_symbol_day_backtest(symbols=["SYM_A", "SYM_B"], provider=prov, include_market_context=False)
        res_order2 = run_multi_symbol_day_backtest(symbols=["SYM_B", "SYM_A"], provider=prov, include_market_context=False)

        res_a_1 = res_order1.symbol_results["SYM_A"]
        res_a_2 = res_order2.symbol_results["SYM_A"]
        assert len(res_a_1.trades) == len(res_a_2.trades)
        for t1, t2 in zip(res_a_1.trades, res_a_2.trades):
            assert t1.entry_time == t2.entry_time
            assert t1.entry_price == t2.entry_price
            assert t1.exit_price == t2.exit_price

        res_b_1 = res_order1.symbol_results["SYM_B"]
        res_b_2 = res_order2.symbol_results["SYM_B"]
        assert len(res_b_1.trades) == len(res_b_2.trades)
        for t1, t2 in zip(res_b_1.trades, res_b_2.trades):
            assert t1.entry_time == t2.entry_time
            assert t1.entry_price == t2.entry_price
            assert t1.exit_price == t2.exit_price


class TestAggregationAndBenchmark:
    """4. Agregatsiya, B&H benchmark va slippage tahlili tekshiruvi."""

    def test_buy_and_hold_benchmark_calculation(self) -> None:
        """Buy & Hold birinchi RTH Open va oxirgi RTH Close narxlaridan to'g'ri hisoblanishi kerak."""
        df_5m, df_15m = _create_synthetic_symbol_bars("2026-01-05 09:30", 50, base_price=100.0, seed=80)
        prov = MockMultiDataProvider({"TEST": (df_5m, df_15m)})

        res = run_multi_symbol_day_backtest(symbols=["TEST"], provider=prov, include_market_context=False)
        m = res.per_symbol_metrics[0]

        expected_bnh = (df_5m["close"].iloc[-1] - df_5m["open"].iloc[0]) / df_5m["open"].iloc[0] * 100.0
        assert m.buy_hold_return == pytest.approx(expected_bnh, rel=1e-5)
        assert m.return_difference_vs_buy_hold == pytest.approx(m.strategy_total_return - expected_bnh, rel=1e-5)

    def test_slippage_levels_monotonic_decay(self) -> None:
        """Slippage (0 -> 5 -> 10 bps) ortgan sari umumiy daromad kamayishi kerak."""
        df_5m, df_15m = _create_synthetic_symbol_bars("2026-01-05 09:30", 150, base_price=100.0, seed=90)
        prov = MockMultiDataProvider({"TEST": (df_5m, df_15m)})

        res = run_multi_symbol_day_backtest(symbols=["TEST"], provider=prov, include_market_context=False)
        m = res.per_symbol_metrics[0]

        if m.trades > 0:
            assert m.slippage_0bps >= m.slippage_5bps
            assert m.slippage_5bps >= m.slippage_10bps

    def test_format_multi_symbol_report_output(self) -> None:
        """Hisobot matni barcha majburiy bo'limlarni o'z ichiga olishi va xolis bo'lishi kerak."""
        df_5m, df_15m = _create_synthetic_symbol_bars("2026-01-05 09:30", 100, base_price=100.0, seed=99)
        prov = MockMultiDataProvider({"TEST": (df_5m, df_15m)})

        res = run_multi_symbol_day_backtest(symbols=["TEST"], provider=prov, include_market_context=False)
        report = format_multi_symbol_report(res)

        assert "DAY-04 — MULTI-SYMBOL VALIDATION REPORT" in report
        assert "DATA COVERAGE & INTEGRITY" in report
        assert "PER-SYMBOL VALIDATION METRICS" in report
        assert "AGGREGATE TRADE STATISTICS" in report
        assert "SYMBOL-LEVEL DISTRIBUTION" in report
        assert "SLIPPAGE SENSITIVITY" in report
        assert "RESEARCH METHODOLOGY NOTES" in report
        assert "NO VALIDATED MARKET EDGE" in report
