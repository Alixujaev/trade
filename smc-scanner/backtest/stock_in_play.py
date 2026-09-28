"""backtest/stock_in_play.py: DAY-06 — Stock-in-Play Context Hypothesis Backtest Runner.

QAT'IY METODOLOGIK QOIDALAR:
- Baseline (DAY-01 muzlatilgan strategiya) natijalariga aslo tegilmaydi.
- H1 (Stock-in-Play) eksperimenti xolis gipoteza tekshiruvi hisoblanadi (optimization emas).
- Variantlar (Gap-only, Premarket-RVOL-only, Combined) alohida taqqoslanadi.
- Hech bir variantga "eng yaxshi" deb etiket qo'yilmaydi.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
import logging
import math
from typing import Any
import numpy as np
import pandas as pd

from backtest.day_types import ExecutionConfig
from backtest.failure_analysis import (
    DiagnosticTradeRecord,
    compute_group_metrics,
    enrich_trade_record,
    get_duration_bucket,
    get_stop_distance_bucket,
    get_time_of_day_bucket,
)
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.multi_types import MultiSymbolDayBacktestResult
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.provider import DataProvider
from data.session import get_session_date
from strategy.day.stock_in_play import (
    DEFAULT_GAP_THRESHOLD_PCT,
    DEFAULT_PREMARKET_RVOL_THRESHOLD,
    StockInPlayContext,
    compute_stock_in_play_contexts,
)

logger = logging.getLogger(__name__)


@dataclass
class VariantMetrics:
    """Bitta variant bo'yicha to'liq taqqoslovchi statistika."""

    variant_name: str
    eligible_symbol_sessions: int
    ineligible_symbol_sessions: int
    eligible_sessions_pct: float

    total_trades: int
    trade_reduction_pct: float
    trades_per_eligible_session_mean: float
    trades_per_eligible_session_median: float

    # Sessiyalar bo'yicha savdo taqsimoti
    sessions_with_1_trade: int
    sessions_with_ge_2_trades: int
    sessions_with_ge_3_trades: int
    sessions_with_ge_5_trades: int

    # Asosiy savdo metrikalari
    wins: int
    losses: int
    breakevens: int
    win_rate: float
    profit_factor: float
    expectancy: float
    median_return: float
    total_R: float
    avg_R: float
    median_R: float
    r_std: float

    # Stop va hold geometriyasi
    avg_stop_distance_pct: float
    median_stop_distance_pct: float
    avg_hold_duration_mins: float
    median_hold_duration_mins: float

    # Aksiyalar darajasidagi taqsimot
    mean_symbol_return: float
    median_symbol_return: float
    positive_symbols_count: int
    negative_symbols_count: int
    outperformed_bnh_symbols: int

    # Benchmark taqqoslash
    mean_bnh_return: float
    strategy_vs_bnh_diff: float

    # Slippage sezgirligi
    slippage_0bps: float
    slippage_5bps: float
    slippage_10bps: float

    # Failure mode diagnostikasi
    early_stops_0_5m_count: int
    early_stops_0_5m_pct: float
    stops_5_10m_count: int
    stops_5_10m_pct: float
    stop_dist_lt_0_25pct_count: int
    stop_dist_lt_0_25pct_pct: float

    mfe_ge_0_5r_count: int
    mfe_ge_0_5r_pct: float
    mfe_ge_1_0r_count: int
    mfe_ge_1_0r_pct: float
    mfe_ge_1_5r_count: int
    mfe_ge_1_5r_pct: float
    mfe_ge_2_0r_count: int
    mfe_ge_2_0r_pct: float
    nearly_winning_losers_ge_1r_count: int
    nearly_winning_losers_ge_1r_pct: float

    exit_reasons: dict[str, int]
    time_of_day_breakdown: dict[str, dict[str, Any]]
    market_context_breakdown: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """JSON serializatsiya."""
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d


@dataclass
class StockInPlayExperimentResult:
    """DAY-06 gipoteza eksperimentining to'liq natijasi."""

    metadata: dict[str, Any]
    study_period: dict[str, Any]
    universe: list[str]
    assumptions: dict[str, Any]

    baseline: VariantMetrics
    h1_gap_only: VariantMetrics
    h1_premarket_rvol_only: VariantMetrics
    h1_combined: VariantMetrics
    h1_positive_gap: VariantMetrics
    h1_negative_gap: VariantMetrics

    symbol_sessions_data: dict[str, dict[str, Any]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        """JSON serializatsiya."""
        return {
            "metadata": self.metadata,
            "study_period": self.study_period,
            "universe": self.universe,
            "assumptions": self.assumptions,
            "variants": {
                "baseline": self.baseline.to_dict(),
                "h1_gap_only": self.h1_gap_only.to_dict(),
                "h1_premarket_rvol_only": self.h1_premarket_rvol_only.to_dict(),
                "h1_combined": self.h1_combined.to_dict(),
                "h1_positive_gap": self.h1_positive_gap.to_dict(),
                "h1_negative_gap": self.h1_negative_gap.to_dict(),
            },
            "limitations": self.limitations,
        }


def compute_variant_metrics(
    variant_name: str,
    eligible_records: list[DiagnosticTradeRecord],
    all_contexts: list[StockInPlayContext],
    is_eligible_fn: Any,
    baseline_trade_count: int,
    bnh_by_symbol: dict[str, float],
    spy_qqq_context: dict[str, dict[str, Any]],
) -> VariantMetrics:
    """Bitta variant uchun to'liq tahliliy ko'rsatkichlarni hisoblaydi."""
    # 1. Sessiyalar hisobi
    eligible_contexts = [c for c in all_contexts if is_eligible_fn(c)]
    total_sessions = len(all_contexts)
    n_eligible_sess = len(eligible_contexts)
    n_ineligible_sess = total_sessions - n_eligible_sess
    elig_pct = (n_eligible_sess / total_sessions * 100.0) if total_sessions > 0 else 0.0

    n_trades = len(eligible_records)
    trade_reduction = ((baseline_trade_count - n_trades) / baseline_trade_count * 100.0) if baseline_trade_count > 0 else 0.0

    # Sessiya bo'yicha savdo sonlari
    trades_per_sess_map = defaultdict(int)
    for r in eligible_records:
        trades_per_sess_map[(r.symbol, r.session_date)] += 1

    # Har bir eligible sessiyadagi savdolar (0 ta savdosi bo'lgan sessiyalarni ham hisobga olish)
    sess_counts: list[int] = []
    for c in eligible_contexts:
        sess_counts.append(trades_per_sess_map.get((c.symbol, str(c.session_date)), 0))

    mean_trades_sess = float(np.mean(sess_counts)) if sess_counts else 0.0
    median_trades_sess = float(np.median(sess_counts)) if sess_counts else 0.0

    c_1 = sum(1 for c in sess_counts if c == 1)
    c_ge_2 = sum(1 for c in sess_counts if c >= 2)
    c_ge_3 = sum(1 for c in sess_counts if c >= 3)
    c_ge_5 = sum(1 for c in sess_counts if c >= 5)

    # 2. Savdo ko'rsatkichlari
    wins = sum(1 for r in eligible_records if r.is_winner)
    losses = sum(1 for r in eligible_records if r.is_loser)
    bes = sum(1 for r in eligible_records if r.is_breakeven)
    win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0

    returns = [r.net_return * 100.0 for r in eligible_records]
    expectancy = float(np.mean(returns)) if returns else 0.0
    median_ret = float(np.median(returns)) if returns else 0.0

    gross_wins = sum(r.gross_return for r in eligible_records if r.gross_return > 0)
    gross_losses = sum(abs(r.gross_return) for r in eligible_records if r.gross_return < 0)
    if gross_losses > 0:
        pf = gross_wins / gross_losses
    elif gross_wins > 0:
        pf = float("inf")
    else:
        pf = 0.0

    r_vals = [r.r_multiple for r in eligible_records if r.r_multiple is not None and not math.isnan(r.r_multiple)]
    total_R = float(np.sum(r_vals)) if r_vals else 0.0
    avg_R = float(np.mean(r_vals)) if r_vals else 0.0
    median_R = float(np.median(r_vals)) if r_vals else 0.0
    r_std = float(np.std(r_vals)) if r_vals else 0.0

    # 3. Stop va Hold geometriyasi
    stop_dists = [r.stop_distance_pct * 100.0 for r in eligible_records if r.stop_distance_pct is not None]
    avg_stop_dist = float(np.mean(stop_dists)) if stop_dists else 0.0
    med_stop_dist = float(np.median(stop_dists)) if stop_dists else 0.0

    hold_mins = [r.hold_duration_minutes for r in eligible_records]
    avg_hold = float(np.mean(hold_mins)) if hold_mins else 0.0
    med_hold = float(np.median(hold_mins)) if hold_mins else 0.0

    # 4. Symbol darajasidagi natijalar
    trades_by_sym = defaultdict(list)
    for r in eligible_records:
        trades_by_sym[r.symbol].append(r)

    sym_returns: list[float] = []
    pos_syms = 0
    neg_syms = 0
    outperformed_bnh = 0

    for sym, bnh_ret in bnh_by_symbol.items():
        sym_recs = trades_by_sym.get(sym, [])
        if sym_recs:
            # Compounded return
            comp = 1.0
            for r in sym_recs:
                comp *= (1.0 + r.net_return)
            strat_ret = (comp - 1.0) * 100.0
        else:
            strat_ret = 0.0

        sym_returns.append(strat_ret)
        if strat_ret > 0:
            pos_syms += 1
        elif strat_ret < 0:
            neg_syms += 1
        if strat_ret > bnh_ret:
            outperformed_bnh += 1

    mean_sym_ret = float(np.mean(sym_returns)) if sym_returns else 0.0
    med_sym_ret = float(np.median(sym_returns)) if sym_returns else 0.0
    mean_bnh = float(np.mean(list(bnh_by_symbol.values()))) if bnh_by_symbol else 0.0
    diff_bnh = mean_sym_ret - mean_bnh

    # 5. Slippage sezgirligi (0 bps, 5 bps, 10 bps)
    slip_0_comp = 1.0
    slip_5_comp = 1.0
    slip_10_comp = 1.0

    for r in eligible_records:
        slip_0_comp *= (1.0 + r.net_return)
        # 5 bps kirish va chiqish = 10 bps (0.10%) qo'shimcha drag
        r_5 = r.gross_return - 0.0010
        slip_5_comp *= (1.0 + r_5)
        # 10 bps kirish va chiqish = 20 bps (0.20%) drag
        r_10 = r.gross_return - 0.0020
        slip_10_comp *= (1.0 + r_10)

    slippage_0 = (slip_0_comp - 1.0) * 100.0
    slippage_5 = (slip_5_comp - 1.0) * 100.0
    slippage_10 = (slip_10_comp - 1.0) * 100.0

    # 6. Failure mode taqqoslovi
    early_0_5 = sum(1 for r in eligible_records if r.exit_reason == "STOP" and r.hold_duration_minutes <= 5)
    stops_5_10 = sum(1 for r in eligible_records if r.exit_reason == "STOP" and 5 < r.hold_duration_minutes <= 10)
    stop_lt_025 = sum(1 for r in eligible_records if r.stop_distance_pct is not None and r.stop_distance_pct < 0.0025)

    mfe_05 = sum(1 for r in eligible_records if r.target_0_5r_reached)
    mfe_10 = sum(1 for r in eligible_records if r.target_1_0r_reached)
    mfe_15 = sum(1 for r in eligible_records if r.target_1_5r_reached)
    mfe_20 = sum(1 for r in eligible_records if r.target_2_0r_reached)

    loss_recs = [r for r in eligible_records if r.is_loser]
    near_win_losers = sum(1 for r in loss_recs if r.target_1_0r_reached)

    exit_counts: dict[str, int] = defaultdict(int)
    for r in eligible_records:
        exit_counts[r.exit_reason] += 1

    # 7. Time of day
    tod_map = defaultdict(list)
    for r in eligible_records:
        tod_map[r.entry_time_bucket].append(r)
    tod_order = ["09:30–10:00", "10:00–11:00", "11:00–12:00", "12:00–14:00", "14:00–15:00", "15:00–15:55"]
    tod_breakdown = {b: compute_group_metrics(tod_map.get(b, [])) for b in tod_order}

    # 8. Market context
    mkt_breakdown: dict[str, dict[str, Any]] = {}
    for idx_name, date_map in spy_qqq_context.items():
        pos_recs = [r for r in eligible_records if date_map.get(r.session_date) == "POS"]
        neg_recs = [r for r in eligible_records if date_map.get(r.session_date) == "NEG"]
        mkt_breakdown[f"{idx_name}_positive_days"] = compute_group_metrics(pos_recs)
        mkt_breakdown[f"{idx_name}_negative_days"] = compute_group_metrics(neg_recs)

    return VariantMetrics(
        variant_name=variant_name,
        eligible_symbol_sessions=n_eligible_sess,
        ineligible_symbol_sessions=n_ineligible_sess,
        eligible_sessions_pct=round(elig_pct, 2),
        total_trades=n_trades,
        trade_reduction_pct=round(trade_reduction, 2),
        trades_per_eligible_session_mean=round(mean_trades_sess, 2),
        trades_per_eligible_session_median=round(median_trades_sess, 2),
        sessions_with_1_trade=c_1,
        sessions_with_ge_2_trades=c_ge_2,
        sessions_with_ge_3_trades=c_ge_3,
        sessions_with_ge_5_trades=c_ge_5,
        wins=wins,
        losses=losses,
        breakevens=bes,
        win_rate=round(win_rate, 2),
        profit_factor=round(pf, 2) if pf != float("inf") else 999.0,
        expectancy=round(expectancy, 4),
        median_return=round(median_ret, 4),
        total_R=round(total_R, 2),
        avg_R=round(avg_R, 4),
        median_R=round(median_R, 4),
        r_std=round(r_std, 4),
        avg_stop_distance_pct=round(avg_stop_dist, 4),
        median_stop_distance_pct=round(med_stop_dist, 4),
        avg_hold_duration_mins=round(avg_hold, 1),
        median_hold_duration_mins=round(med_hold, 1),
        mean_symbol_return=round(mean_sym_ret, 2),
        median_symbol_return=round(med_sym_ret, 2),
        positive_symbols_count=pos_syms,
        negative_symbols_count=neg_syms,
        outperformed_bnh_symbols=outperformed_bnh,
        mean_bnh_return=round(mean_bnh, 2),
        strategy_vs_bnh_diff=round(diff_bnh, 2),
        slippage_0bps=round(slippage_0, 2),
        slippage_5bps=round(slippage_5, 2),
        slippage_10bps=round(slippage_10, 2),
        early_stops_0_5m_count=early_0_5,
        early_stops_0_5m_pct=round(early_0_5 / n_trades * 100, 2) if n_trades else 0,
        stops_5_10m_count=stops_5_10,
        stops_5_10m_pct=round(stops_5_10 / n_trades * 100, 2) if n_trades else 0,
        stop_dist_lt_0_25pct_count=stop_lt_025,
        stop_dist_lt_0_25pct_pct=round(stop_lt_025 / n_trades * 100, 2) if n_trades else 0,
        mfe_ge_0_5r_count=mfe_05,
        mfe_ge_0_5r_pct=round(mfe_05 / n_trades * 100, 2) if n_trades else 0,
        mfe_ge_1_0r_count=mfe_10,
        mfe_ge_1_0r_pct=round(mfe_10 / n_trades * 100, 2) if n_trades else 0,
        mfe_ge_1_5r_count=mfe_15,
        mfe_ge_1_5r_pct=round(mfe_15 / n_trades * 100, 2) if n_trades else 0,
        mfe_ge_2_0r_count=mfe_20,
        mfe_ge_2_0r_pct=round(mfe_20 / n_trades * 100, 2) if n_trades else 0,
        nearly_winning_losers_ge_1r_count=near_win_losers,
        nearly_winning_losers_ge_1r_pct=round(near_win_losers / len(loss_recs) * 100, 2) if loss_recs else 0,
        exit_reasons=dict(exit_counts),
        time_of_day_breakdown=tod_breakdown,
        market_context_breakdown=mkt_breakdown,
    )


def run_stock_in_play_backtest(
    symbols: Sequence[str] | None = None,
    *,
    gap_threshold_pct: float = DEFAULT_GAP_THRESHOLD_PCT,
    premarket_rvol_threshold: float = DEFAULT_PREMARKET_RVOL_THRESHOLD,
    provider: DataProvider | None = None,
    multi_result: MultiSymbolDayBacktestResult | None = None,
) -> StockInPlayExperimentResult:
    """DAY-06: Stock-in-Play kontekst gipotezasini baseline bilan to'liq taqqoslaydi."""
    prov = provider or get_provider()

    # 1. Multi-symbol natijalari (agar berilmagan bo'lsa hisoblash)
    if multi_result is None:
        logger.info("Executing baseline multi-symbol backtest...")
        multi_result = run_multi_symbol_day_backtest(symbols=symbols, provider=prov)

    # 2. 5m va extended 5m ma'lumotlarni yuklash va StockInPlayContext larni hisoblash
    contexts_by_symbol_date: dict[tuple[str, str], StockInPlayContext] = {}
    all_contexts_list: list[StockInPlayContext] = []
    ohlcv_5m_cache: dict[str, pd.DataFrame] = {}

    for sym in multi_result.tested_symbols:
        try:
            df_5m = prov.get_ohlcv(sym, "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
            ohlcv_5m_cache[sym] = df_5m
        except Exception:
            df_5m = pd.DataFrame()

        try:
            df_ext = prov.get_ohlcv(sym, "5m", include_extended_hours=True, closed_only=False, ignore_cache_expiry=True)
        except Exception:
            df_ext = None

        sym_ctxs = compute_stock_in_play_contexts(
            sym,
            df_5m,
            df_extended_5m=df_ext,
            gap_threshold_pct=gap_threshold_pct,
            premarket_rvol_threshold=premarket_rvol_threshold,
        )

        for d, ctx in sym_ctxs.items():
            contexts_by_symbol_date[(sym, str(d))] = ctx
            all_contexts_list.append(ctx)

    # 3. Savdolarni boyitish (DiagnosticTradeRecord)
    enriched_trades: list[DiagnosticTradeRecord] = []
    for sym, res in multi_result.symbol_results.items():
        sym_df = ohlcv_5m_cache.get(sym, pd.DataFrame())
        for t in res.trades:
            enriched = enrich_trade_record(t, sym_df)
            enriched_trades.append(enriched)

    enriched_trades.sort(key=lambda r: r.entry_time)
    baseline_count = len(enriched_trades)

    # 4. Buy and hold ma'lumotlari
    bnh_by_sym = {m.symbol: m.buy_hold_return for m in multi_result.per_symbol_metrics}

    # 5. SPY va QQQ konteksti
    spy_qqq_context: dict[str, dict[str, str]] = {}
    for mkt_sym in ("SPY", "QQQ"):
        try:
            df_mkt = prov.get_ohlcv(mkt_sym, "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
            from data.session import filter_rth, get_session_dates
            rth = filter_rth(df_mkt)
            dates = get_session_dates(rth.index)
            date_dict: dict[str, str] = {}
            for d, grp in rth.groupby(dates):
                ret = (grp["close"].iloc[-1] - grp["open"].iloc[0]) / grp["open"].iloc[0]
                date_dict[str(d)] = "POS" if ret > 0 else "NEG"
            spy_qqq_context[mkt_sym] = date_dict
        except Exception:
            spy_qqq_context[mkt_sym] = {}

    # 6. Variantlar bo'yicha filtrlash
    # Baseline: barcha savdolar
    baseline_metrics = compute_variant_metrics(
        "Baseline (Unfiltered)",
        enriched_trades,
        all_contexts_list,
        lambda c: True,
        baseline_count,
        bnh_by_sym,
        spy_qqq_context,
    )

    # Variant A: Gap only
    def is_gap_only(c: StockInPlayContext) -> bool:
        return c.gap_only_eligible

    gap_only_trades = [
        r for r in enriched_trades
        if contexts_by_symbol_date.get((r.symbol, r.session_date), None) is not None
        and contexts_by_symbol_date[(r.symbol, r.session_date)].gap_only_eligible
    ]
    h1_gap_only = compute_variant_metrics(
        f"H1 Variant A (Gap >= {gap_threshold_pct * 100:.1f}%)",
        gap_only_trades,
        all_contexts_list,
        is_gap_only,
        baseline_count,
        bnh_by_sym,
        spy_qqq_context,
    )

    # Variant B: Premarket RVOL only
    def is_pm_rvol(c: StockInPlayContext) -> bool:
        return c.premarket_only_eligible

    pm_rvol_trades = [
        r for r in enriched_trades
        if contexts_by_symbol_date.get((r.symbol, r.session_date), None) is not None
        and contexts_by_symbol_date[(r.symbol, r.session_date)].premarket_only_eligible
    ]
    h1_pm_rvol = compute_variant_metrics(
        f"H1 Variant B (Premarket RVOL >= {premarket_rvol_threshold:.1f}x)",
        pm_rvol_trades,
        all_contexts_list,
        is_pm_rvol,
        baseline_count,
        bnh_by_sym,
        spy_qqq_context,
    )

    # Variant C: Combined (Gap AND Premarket RVOL)
    def is_combined(c: StockInPlayContext) -> bool:
        return c.combined_eligible

    combined_trades = [
        r for r in enriched_trades
        if contexts_by_symbol_date.get((r.symbol, r.session_date), None) is not None
        and contexts_by_symbol_date[(r.symbol, r.session_date)].combined_eligible
    ]
    h1_combined = compute_variant_metrics(
        "H1 Variant C (Combined Gap + Premarket RVOL)",
        combined_trades,
        all_contexts_list,
        is_combined,
        baseline_count,
        bnh_by_sym,
        spy_qqq_context,
    )

    # Subsets: Positive gap vs Negative gap
    def is_pos_gap(c: StockInPlayContext) -> bool:
        return c.gap_eligible and c.is_positive_gap

    pos_gap_trades = [
        r for r in enriched_trades
        if contexts_by_symbol_date.get((r.symbol, r.session_date), None) is not None
        and contexts_by_symbol_date[(r.symbol, r.session_date)].gap_eligible
        and contexts_by_symbol_date[(r.symbol, r.session_date)].is_positive_gap
    ]
    h1_pos_gap = compute_variant_metrics(
        f"H1 Subset: Positive Gap (>= +{gap_threshold_pct * 100:.1f}%)",
        pos_gap_trades,
        all_contexts_list,
        is_pos_gap,
        baseline_count,
        bnh_by_sym,
        spy_qqq_context,
    )

    def is_neg_gap(c: StockInPlayContext) -> bool:
        return c.gap_eligible and c.is_negative_gap

    neg_gap_trades = [
        r for r in enriched_trades
        if contexts_by_symbol_date.get((r.symbol, r.session_date), None) is not None
        and contexts_by_symbol_date[(r.symbol, r.session_date)].gap_eligible
        and contexts_by_symbol_date[(r.symbol, r.session_date)].is_negative_gap
    ]
    h1_neg_gap = compute_variant_metrics(
        f"H1 Subset: Negative Gap (<= -{gap_threshold_pct * 100:.1f}%)",
        neg_gap_trades,
        all_contexts_list,
        is_neg_gap,
        baseline_count,
        bnh_by_sym,
        spy_qqq_context,
    )

    limitations = [
        "Catalyst data unavailable: No historical point-in-time structured news/catalyst feed exists in the dataset. catalyst_available=False.",
        "Premarket volume limitation: yfinance historical extended-hours 5m dataset provides premarket OHLC prices but records volume as 0.0 for premarket bars. Premarket RVOL evaluates to None/False on historical yfinance data.",
        "Exploratory assumptions: The gap threshold of 2.0% is an explicit research assumption, not an optimized parameter.",
        "Long-only execution: Both positive and negative gaps were evaluated as long-only context; negative gaps were not treated as short setups.",
    ]

    return StockInPlayExperimentResult(
        metadata={
            "experiment": "DAY-06: Stock-in-Play Context Hypothesis",
            "strategy": "FROZEN DAY-01 VWAP Momentum (unaltered)",
            "execution": "FROZEN DAY-02 Execution Model (unaltered)",
        },
        study_period={
            "start": str(multi_result.study_window_start),
            "end": str(multi_result.study_window_end),
            "sessions": multi_result.total_sessions,
        },
        universe=multi_result.tested_symbols,
        assumptions={
            "gap_threshold_pct": gap_threshold_pct,
            "premarket_rvol_threshold": premarket_rvol_threshold,
            "catalyst_available": False,
            "point_in_time_cutoff": "09:30:00 America/New_York",
        },
        baseline=baseline_metrics,
        h1_gap_only=h1_gap_only,
        h1_premarket_rvol_only=h1_pm_rvol,
        h1_combined=h1_combined,
        h1_positive_gap=h1_pos_gap,
        h1_negative_gap=h1_neg_gap,
        symbol_sessions_data={f"{k[0]}_{k[1]}": v.to_dict() for k, v in list(contexts_by_symbol_date.items())[:50]},
        limitations=limitations,
    )


def format_stock_in_play_report(res: StockInPlayExperimentResult) -> str:
    """DAY-06 gipoteza taqqoslash hisobotini toza matn formatida yaratadi."""
    lines: list[str] = []
    lines.append("=" * 85)
    lines.append("DAY-06 — STOCK-IN-PLAY CONTEXT HYPOTHESIS: COMPARATIVE RESEARCH REPORT")
    lines.append("=" * 85)
    lines.append(f"Study Period:   {res.study_period['start']} to {res.study_period['end']} ({res.study_period['sessions']} RTH sessions)")
    lines.append(f"Universe:       {len(res.universe)} liquid US equities")
    lines.append(f"Gap Threshold:  abs(gap) >= {res.assumptions['gap_threshold_pct'] * 100:.1f}% (Research assumption)")
    lines.append(f"Premarket RVOL: >= {res.assumptions['premarket_rvol_threshold']:.1f}x (Research assumption)")
    lines.append(f"Catalyst Data:  {res.assumptions['catalyst_available']} (Marked unavailable, zero fabrication)")
    lines.append(f"Strategy:       FROZEN DAY-01 VWAP Momentum (Rules, indicators, stops 100% untouched)")
    lines.append("")

    # 1. Comparative Performance Table
    lines.append("-" * 85)
    lines.append("1. CORE METRICS COMPARISON (Baseline vs H1 Variants)")
    lines.append("-" * 85)
    hdr = f"{'Variant':<28} {'Trades':<8} {'Reduct':<8} {'WinRate':<9} {'PF':<6} {'Exp(Avg)':<10} {'Total_R':<9} {'Avg_R':<8} {'Slippage 0/5/10bps'}"
    lines.append(hdr)

    variants = [
        res.baseline,
        res.h1_gap_only,
        res.h1_positive_gap,
        res.h1_negative_gap,
        res.h1_premarket_rvol_only,
        res.h1_combined,
    ]

    for v in variants:
        slip_str = f"{v.slippage_0bps:.0f}% / {v.slippage_5bps:.0f}% / {v.slippage_10bps:.0f}%"
        lines.append(
            f"{v.variant_name:<28} {v.total_trades:<8} {v.trade_reduction_pct:<7.1f}% "
            f"{v.win_rate:<8.1f}% {v.profit_factor:<6.2f} {v.expectancy:<9.4f}% "
            f"{v.total_R:<9.1f} {v.avg_R:<8.2f} {slip_str}"
        )
    lines.append("")

    # 2. Trade Population & Churn Analysis
    lines.append("-" * 85)
    lines.append("2. TRADE POPULATION & SESSION CHURN DYNAMICS")
    lines.append("-" * 85)
    lines.append(f"{'Variant':<28} {'Elig.Sess':<11} {'Trades/Sess(Avg)':<18} {'Sess>=2Tr':<12} {'Sess>=5Tr':<12} {'AvgStopDist':<13} {'AvgHold'}")
    for v in variants:
        sess_ge2_str = f"{v.sessions_with_ge_2_trades}"
        sess_ge5_str = f"{v.sessions_with_ge_5_trades}"
        lines.append(
            f"{v.variant_name:<28} {v.eligible_symbol_sessions:<11} {v.trades_per_eligible_session_mean:<18.2f} "
            f"{sess_ge2_str:<12} {sess_ge5_str:<12} {v.avg_stop_distance_pct:<12.3f}% {v.avg_hold_duration_mins:<6.1f}m"
        )
    lines.append("")

    # 3. Failure Mode Diagnostics Comparison
    lines.append("-" * 85)
    lines.append("3. FAILURE-MODE COMPARISON (DAY-05 Diagnostics Across Variants)")
    lines.append("-" * 85)
    lines.append(f"{'Variant':<28} {'0-5m Stops':<13} {'Stop<0.25%':<13} {'MFE>=1.0R':<12} {'MFE>=2.0R':<12} {'Loss>=1R then lost'}")
    for v in variants:
        e05_str = f"{v.early_stops_0_5m_count} ({v.early_stops_0_5m_pct}%)"
        s025_str = f"{v.stop_dist_lt_0_25pct_count} ({v.stop_dist_lt_0_25pct_pct}%)"
        m10_str = f"{v.mfe_ge_1_0r_count} ({v.mfe_ge_1_0r_pct}%)"
        m20_str = f"{v.mfe_ge_2_0r_count} ({v.mfe_ge_2_0r_pct}%)"
        near_win_str = f"{v.nearly_winning_losers_ge_1r_count} ({v.nearly_winning_losers_ge_1r_pct}%)"
        lines.append(
            f"{v.variant_name:<28} {e05_str:<13} {s025_str:<13} {m10_str:<12} {m20_str:<12} {near_win_str}"
        )
    lines.append("")

    # 4. Symbol & Benchmark Distribution
    lines.append("-" * 85)
    lines.append("4. SYMBOL-LEVEL DISTRIBUTION & BUY-AND-HOLD COMPARISON")
    lines.append("-" * 85)
    lines.append(f"{'Variant':<28} {'Mean Sym Ret':<15} {'Med Sym Ret':<15} {'Pos/Neg Syms':<15} {'Beat B&H':<10} {'Mean B&H'}")
    for v in variants:
        pn_str = f"{v.positive_symbols_count} / {v.negative_symbols_count}"
        lines.append(
            f"{v.variant_name:<28} {v.mean_symbol_return:<14.2f}% {v.median_symbol_return:<14.2f}% "
            f"{pn_str:<15} {v.outperformed_bnh_symbols:<10} {v.mean_bnh_return:<.2f}%"
        )
    lines.append("")

    # 5. Data Limitations & Methodology Notes
    lines.append("-" * 85)
    lines.append("5. DATA LIMITATIONS & METHODOLOGY NOTES")
    lines.append("-" * 85)
    for lim in res.limitations:
        lines.append(f"• {lim}")
    lines.append("")
    lines.append("=" * 85)
    lines.append("END OF DAY-06 RESEARCH REPORT")
    lines.append("=" * 85)

    return "\n".join(lines)
