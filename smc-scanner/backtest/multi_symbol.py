"""backtest/multi_symbol.py: DAY-04 — Multi-Symbol Validation of the Frozen Day Strategy.

QAT'IY METODOLOGIK QOIDALAR:
- Bu modul mavjud muzlatilgan DAY-01/DAY-02 strategiyasi va DAY-03 optimallashtirilgan engine'i
  asosida bir nechta aksiyalar bo'yicha tadqiqot validatsiyasini o'tkazadi.
- Strategiya logikasi, threshold'lar, parametrlar yoki qoidalariga hech qanday o'zgartirish kiritilmaydi.
- Natijalar xolis, factual o'lchov sifatida taqdim etiladi. Hech qanday "BUY/SELL", "PROFITABLE",
  "EDGE VALIDATED" da'volari qilinmaydi.
- Barcha hisob-kitoblar Buy-and-Hold benchmarki bilan taqqoslanadi.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
import numpy as np
import pandas as pd

from backtest.day_engine import run_day_backtest
from backtest.day_types import DayBacktestResult, DayBacktestTrade, ExecutionConfig
from backtest.multi_types import (
    AggregateTradeStats,
    DataCoverageStatus,
    MarketContextSummary,
    MultiSymbolDayBacktestResult,
    PerSymbolMetrics,
    SymbolCoverage,
    SymbolDistributionStats,
)
from config.day_universe import (
    MARKET_BENCHMARK_SYMBOLS,
    get_day_universe,
    validate_universe_symbols,
)
from data.factory import get_provider
from data.provider import DataProvider
from data.session import get_session_dates, get_session_date

logger = logging.getLogger(__name__)


def run_multi_symbol_day_backtest(
    symbols: Sequence[str] | None = None,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    config: ExecutionConfig | None = None,
    provider: DataProvider | None = None,
    common_window_only: bool = True,
    include_market_context: bool = True,
    market_symbols: Sequence[str] | None = None,
    slippage_levels: Sequence[float] = (0.0, 5.0, 10.0),
) -> MultiSymbolDayBacktestResult:
    """Muzlatilgan DAY-01/DAY-02 strategiyasini ko'p aksiyali tadqiqot universe'ida validatsiya qiladi.

    Parameters
    ----------
    symbols : Sequence[str] | None, optional
        Tekshiriladigan aksiyalar ro'yxati. None bo'lsa muzlatilgan FROZEN_DAY_UNIVERSE olinadi.
    start_date : str | pd.Timestamp | None, optional
        Tadqiqot boshlanish sanasi.
    end_date : str | pd.Timestamp | None, optional
        Tadqiqot tugash sanasi.
    config : ExecutionConfig | None, optional
        Execution parametrlari (muzlatilgan DAY-02 gipotezalari).
    provider : DataProvider | None, optional
        Bozor ma'lumotlari provayderi. None bo'lsa default olinadi.
    common_window_only : bool, optional
        True bo'lsa (default), barcha mavjud aksiyalar uchun umumiy bo'lgan yagona vaqt oralig'i olinadi.
    include_market_context : bool, optional
        SPY/QQQ kunlik yo'nalishi bo'yicha diagnostik tahlilni qo'shish (strategiya filtri emas).
    market_symbols : Sequence[str] | None, optional
        Diagnostik indeks belgilari (standart: SPY, QQQ).
    slippage_levels : Sequence[float], optional
        Slippage sezgirlik darajalari (bps).

    Returns
    -------
    MultiSymbolDayBacktestResult
        Aksiyalar kesimida va jamlangan statistik natijalar.
    """
    exec_config = config or ExecutionConfig()
    prov = provider or get_provider()

    # 1. Universe'ni normalizatsiya qilish
    raw_symbols = list(symbols) if symbols is not None else get_day_universe()
    target_universe = validate_universe_symbols(raw_symbols)

    coverage_map: dict[str, SymbolCoverage] = {}
    loaded_data: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}

    # 2. Har bir aksiya ma'lumotlarini yuklash va dastlabki tekshirish
    for sym in target_universe:
        try:
            df_5m = prov.get_ohlcv(
                sym,
                "5m",
                include_extended_hours=False,
                closed_only=False,
                ignore_cache_expiry=True,
            )
            df_15m = prov.get_ohlcv(
                sym,
                "15m",
                include_extended_hours=False,
                closed_only=False,
                ignore_cache_expiry=True,
            )
        except Exception as exc:
            coverage_map[sym] = SymbolCoverage(
                symbol=sym,
                status=DataCoverageStatus.UNAVAILABLE,
                reason=f"Download error: {exc}",
            )
            continue

        if df_5m.empty or len(df_5m) < 15:
            coverage_map[sym] = SymbolCoverage(
                symbol=sym,
                status=DataCoverageStatus.INVALID,
                bars_5m=len(df_5m),
                bars_15m=len(df_15m) if df_15m is not None else 0,
                reason="Insufficient 5m bars (< 15)",
            )
            continue

        loaded_data[sym] = (df_5m, df_15m)

    valid_symbols = list(loaded_data.keys())

    if not valid_symbols:
        now_ts = pd.Timestamp.now()
        empty_agg = AggregateTradeStats(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        empty_dist = SymbolDistributionStats(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0)
        return MultiSymbolDayBacktestResult(
            study_window_start=now_ts,
            study_window_end=now_ts,
            total_sessions=0,
            universe=target_universe,
            tested_symbols=[],
            coverage=coverage_map,
            per_symbol_metrics=[],
            aggregate_trade_stats=empty_agg,
            symbol_distribution=empty_dist,
            slippage_sensitivity={},
            execution_config=exec_config,
        )

    # 3. Umumiy mavjud vaqt oralig'ini (common historical period) aniqlash
    all_starts = [loaded_data[s][0].index[0] for s in valid_symbols]
    all_ends = [loaded_data[s][0].index[-1] for s in valid_symbols]

    effective_start = pd.Timestamp(start_date) if start_date is not None else max(all_starts)
    effective_end = pd.Timestamp(end_date) if end_date is not None else min(all_ends)

    # Timezone moslash
    ref_tz = loaded_data[valid_symbols[0]][0].index.tz
    if effective_start.tz is None and ref_tz is not None:
        effective_start = effective_start.tz_localize(ref_tz)
    if effective_end.tz is None and ref_tz is not None:
        effective_end = effective_end.tz_localize(ref_tz)

    # Qamrov holatini yakuniy belgilash
    tested_symbols: list[str] = []
    symbol_results: dict[str, DayBacktestResult] = {}
    per_symbol_metrics_list: list[PerSymbolMetrics] = []

    for sym in valid_symbols:
        df_5m_raw, df_15m_raw = loaded_data[sym]
        s_start = df_5m_raw.index[0]
        s_end = df_5m_raw.index[-1]

        # Common window bilan kesish
        if common_window_only:
            df_5m = df_5m_raw.loc[(df_5m_raw.index >= effective_start) & (df_5m_raw.index <= effective_end)]
            df_15m = (
                df_15m_raw.loc[(df_15m_raw.index >= effective_start) & (df_15m_raw.index <= effective_end + pd.Timedelta(minutes=15))]
                if df_15m_raw is not None and not df_15m_raw.empty
                else None
            )
        else:
            df_5m = df_5m_raw
            df_15m = df_15m_raw

        if df_5m.empty or len(df_5m) < 15:
            coverage_map[sym] = SymbolCoverage(
                symbol=sym,
                status=DataCoverageStatus.PARTIAL,
                bars_5m=len(df_5m),
                bars_15m=len(df_15m) if df_15m is not None else 0,
                start_date=s_start,
                end_date=s_end,
                reason="Insufficient bars within common study window",
            )
            continue

        is_full_coverage = (s_start <= effective_start) and (s_end >= effective_end)
        cov_status = DataCoverageStatus.AVAILABLE if is_full_coverage else DataCoverageStatus.PARTIAL

        coverage_map[sym] = SymbolCoverage(
            symbol=sym,
            status=cov_status,
            bars_5m=len(df_5m),
            bars_15m=len(df_15m) if df_15m is not None else 0,
            start_date=df_5m.index[0],
            end_date=df_5m.index[-1],
            reason="Full window coverage" if is_full_coverage else "Partial window coverage",
        )

        # 4. Mavjud optimallashtirilgan engine'ni ishga tushirish (O(N) tezlik)
        res = run_day_backtest(
            sym,
            df_5m=df_5m,
            df_15m=df_15m,
            config=exec_config,
            use_fast_engine=True,
        )

        symbol_results[sym] = res
        tested_symbols.append(sym)

        m = res.metrics
        trades_list = res.trades
        n_trades = len(trades_list)
        wins = sum(1 for t in trades_list if t.net_return > 0)
        losses = sum(1 for t in trades_list if t.net_return < 0)
        breakevens = sum(1 for t in trades_list if t.net_return == 0)
        win_rate = wins / n_trades if n_trades > 0 else 0.0

        median_ret = (
            float(np.median([t.net_return * 100.0 for t in trades_list]))
            if trades_list
            else 0.0
        )

        bnh = res.buy_and_hold_return
        strat_ret = m["total_return_pct"]
        diff_bnh = strat_ret - bnh

        slip_0 = res.sensitivity_results.get("0 bps", {}).get("total_return_pct", strat_ret)
        slip_5 = res.sensitivity_results.get("5 bps", {}).get("total_return_pct", float("nan"))
        slip_10 = res.sensitivity_results.get("10 bps", {}).get("total_return_pct", float("nan"))

        sym_metrics = PerSymbolMetrics(
            symbol=sym,
            data_start=res.window_start,
            data_end=res.window_end,
            sessions=res.total_sessions,
            bars_5m=res.total_bars,
            bars_15m=len(df_15m) if df_15m is not None else 0,
            data_status=cov_status.value,
            trades=n_trades,
            wins=wins,
            losses=losses,
            breakevens=breakevens,
            win_rate=win_rate,
            strategy_total_return=strat_ret,
            strategy_avg_trade_return=m["average_return_pct"],
            strategy_median_trade_return=median_ret,
            profit_factor=m["profit_factor"],
            expectancy=m["average_return_pct"],
            max_drawdown=m["max_drawdown_pct"],
            avg_R=m["average_R"],
            median_R=m["median_R"],
            total_R=m["total_R"],
            skipped_signals=res.skipped_signals,
            insufficient_data=res.insufficient_data_count,
            same_bar_ambiguity=res.same_bar_ambiguity_count,
            buy_hold_return=bnh,
            return_difference_vs_buy_hold=diff_bnh,
            slippage_0bps=slip_0,
            slippage_5bps=slip_5,
            slippage_10bps=slip_10,
        )
        per_symbol_metrics_list.append(sym_metrics)

    # 5. Savdo-darajasidagi agregatsiya (Trade-level aggregate across all symbols)
    all_trades: list[DayBacktestTrade] = [
        t for res in symbol_results.values() for t in res.trades
    ]
    total_trades_count = len(all_trades)
    all_wins = sum(1 for t in all_trades if t.net_return > 0)
    all_losses = sum(1 for t in all_trades if t.net_return < 0)
    all_bes = sum(1 for t in all_trades if t.net_return == 0)
    agg_win_rate = all_wins / total_trades_count if total_trades_count > 0 else 0.0

    gross_gains = sum(t.net_return for t in all_trades if t.net_return > 0)
    gross_losses = abs(sum(t.net_return for t in all_trades if t.net_return < 0))
    if gross_losses > 0:
        agg_pf = gross_gains / gross_losses
    elif gross_gains > 0:
        agg_pf = float("inf")
    else:
        agg_pf = 0.0

    agg_expectancy = (
        float(np.mean([t.net_return * 100.0 for t in all_trades]))
        if all_trades
        else 0.0
    )

    r_vals = [t.r_multiple for t in all_trades if t.r_multiple is not None]
    agg_total_r = float(sum(r_vals)) if r_vals else 0.0
    agg_avg_r = float(np.mean(r_vals)) if r_vals else 0.0
    agg_median_r = float(np.median(r_vals)) if r_vals else 0.0
    agg_r_std = float(np.std(r_vals)) if len(r_vals) > 1 else 0.0

    agg_trade_stats = AggregateTradeStats(
        total_trades=total_trades_count,
        wins=all_wins,
        losses=all_losses,
        breakevens=all_bes,
        win_rate=agg_win_rate,
        profit_factor=agg_pf,
        expectancy=agg_expectancy,
        total_R=agg_total_r,
        avg_R=agg_avg_r,
        median_R=agg_median_r,
        r_std=agg_r_std,
    )

    # 6. Aksiya-darajasidagi taqsimot (Symbol-level distribution)
    strat_returns = [m.strategy_total_return for m in per_symbol_metrics_list]
    bnh_returns = [m.buy_hold_return for m in per_symbol_metrics_list]

    pos_syms = sum(1 for r in strat_returns if r > 0)
    neg_syms = sum(1 for r in strat_returns if r < 0)
    zero_syms = sum(1 for r in strat_returns if r == 0)
    outperf_count = sum(1 for m in per_symbol_metrics_list if m.strategy_total_return > m.buy_hold_return)

    sym_distribution = SymbolDistributionStats(
        total_symbols_tested=len(per_symbol_metrics_list),
        positive_strategy_symbols=pos_syms,
        negative_strategy_symbols=neg_syms,
        zero_strategy_symbols=zero_syms,
        median_strategy_return=float(np.median(strat_returns)) if strat_returns else 0.0,
        mean_strategy_return=float(np.mean(strat_returns)) if strat_returns else 0.0,
        median_buy_hold_return=float(np.median(bnh_returns)) if bnh_returns else 0.0,
        mean_buy_hold_return=float(np.mean(bnh_returns)) if bnh_returns else 0.0,
        outperformed_buy_hold_count=outperf_count,
    )

    # 7. Umumiy slippage sezgirligi (0, 5, 10 bps) barcha savdolar bo'ylab
    agg_slippage_sensitivity: dict[str, dict[str, float]] = {}
    for slip in slippage_levels:
        sim_returns = []
        for t in all_trades:
            raw_ent = t.entry_price / (1.0 + (exec_config.slippage_bps / 10000.0))
            raw_ex = (t.exit_price + exec_config.commission_per_share) / (
                1.0 - (exec_config.slippage_bps / 10000.0)
            )
            new_ent = raw_ent * (1.0 + (slip / 10000.0)) + exec_config.commission_per_share
            new_ex = raw_ex * (1.0 - (slip / 10000.0)) - exec_config.commission_per_share
            sim_returns.append((new_ex - new_ent) / new_ent)

        c_ret = 1.0
        for r in sim_returns:
            c_ret *= 1.0 + r
        tot_pct = (c_ret - 1.0) * 100.0 if sim_returns else 0.0

        slip_wins = sum(1 for r in sim_returns if r > 0)
        slip_wr = slip_wins / len(sim_returns) if sim_returns else 0.0

        agg_slippage_sensitivity[f"{int(slip)} bps"] = {
            "compounded_return_pct": tot_pct,
            "avg_trade_return_pct": float(np.mean([r * 100.0 for r in sim_returns])) if sim_returns else 0.0,
            "win_rate": slip_wr,
        }

    # 8. Diagnostik bozor konteksti (SPY / QQQ) — strategiya filtri EMAS
    market_context: MarketContextSummary | None = None
    if include_market_context:
        m_symbols = list(market_symbols) if market_symbols else list(MARKET_BENCHMARK_SYMBOLS)
        spy_sym = m_symbols[0] if len(m_symbols) > 0 else "SPY"
        qqq_sym = m_symbols[1] if len(m_symbols) > 1 else "QQQ"

        spy_days: dict[datetime.date, float] = {}
        qqq_days: dict[datetime.date, float] = {}
        spy_bnh = 0.0
        qqq_bnh = 0.0

        try:
            df_spy = prov.get_ohlcv(spy_sym, "5m", ignore_cache_expiry=True)
            df_spy = df_spy.loc[(df_spy.index >= effective_start) & (df_spy.index <= effective_end)]
            if not df_spy.empty:
                s_dates = get_session_dates(df_spy.index)
                for d in s_dates.unique():
                    sub = df_spy.loc[s_dates == d]
                    if len(sub) >= 2:
                        ret = (sub["close"].iloc[-1] - sub["open"].iloc[0]) / sub["open"].iloc[0]
                        spy_days[d] = ret
                spy_bnh = (df_spy["close"].iloc[-1] - df_spy["open"].iloc[0]) / df_spy["open"].iloc[0] * 100.0
        except Exception as e:
            logger.warning("SPY diagnostic context failed: %s", e)

        try:
            df_qqq = prov.get_ohlcv(qqq_sym, "5m", ignore_cache_expiry=True)
            df_qqq = df_qqq.loc[(df_qqq.index >= effective_start) & (df_qqq.index <= effective_end)]
            if not df_qqq.empty:
                q_dates = get_session_dates(df_qqq.index)
                for d in q_dates.unique():
                    sub = df_qqq.loc[q_dates == d]
                    if len(sub) >= 2:
                        ret = (sub["close"].iloc[-1] - sub["open"].iloc[0]) / sub["open"].iloc[0]
                        qqq_days[d] = ret
                qqq_bnh = (df_qqq["close"].iloc[-1] - df_qqq["open"].iloc[0]) / df_qqq["open"].iloc[0] * 100.0
        except Exception as e:
            logger.warning("QQQ diagnostic context failed: %s", e)

        # Savdolarni SPY / QQQ kunlariga moslashtirish
        spy_pos_trades = []
        spy_neg_trades = []
        qqq_pos_trades = []
        qqq_neg_trades = []

        for t in all_trades:
            t_day = get_session_date(t.setup_time)
            if t_day in spy_days:
                if spy_days[t_day] > 0:
                    spy_pos_trades.append(t)
                else:
                    spy_neg_trades.append(t)
            if t_day in qqq_days:
                if qqq_days[t_day] > 0:
                    qqq_pos_trades.append(t)
                else:
                    qqq_neg_trades.append(t)

        def _stats(t_list: list[DayBacktestTrade]) -> tuple[int, float, float]:
            if not t_list:
                return 0, 0.0, 0.0
            n = len(t_list)
            wr = sum(1 for tr in t_list if tr.net_return > 0) / n
            avg_r = float(np.mean([tr.net_return * 100.0 for tr in t_list]))
            return n, wr, avg_r

        sp_n, sp_wr, sp_avg = _stats(spy_pos_trades)
        sn_n, sn_wr, sn_avg = _stats(spy_neg_trades)
        qp_n, qp_wr, qp_avg = _stats(qqq_pos_trades)
        qn_n, qn_wr, qn_avg = _stats(qqq_neg_trades)

        market_context = MarketContextSummary(
            spy_positive_trades=sp_n,
            spy_positive_win_rate=sp_wr,
            spy_positive_avg_return=sp_avg,
            spy_negative_trades=sn_n,
            spy_negative_win_rate=sn_wr,
            spy_negative_avg_return=sn_avg,
            qqq_positive_trades=qp_n,
            qqq_positive_win_rate=qp_wr,
            qqq_positive_avg_return=qp_avg,
            qqq_negative_trades=qn_n,
            qqq_negative_win_rate=qn_wr,
            qqq_negative_avg_return=qn_avg,
            spy_bnh_return=spy_bnh,
            qqq_bnh_return=qqq_bnh,
        )

    # 9. Yakuniy umumiy sessiyalar soni
    first_res = list(symbol_results.values())[0] if symbol_results else None
    tot_sessions = first_res.total_sessions if first_res else 0

    return MultiSymbolDayBacktestResult(
        study_window_start=effective_start,
        study_window_end=effective_end,
        total_sessions=tot_sessions,
        universe=target_universe,
        tested_symbols=tested_symbols,
        coverage=coverage_map,
        per_symbol_metrics=per_symbol_metrics_list,
        aggregate_trade_stats=agg_trade_stats,
        symbol_distribution=sym_distribution,
        slippage_sensitivity=agg_slippage_sensitivity,
        market_context=market_context,
        symbol_results=symbol_results,
        execution_config=exec_config,
        metadata={
            "strategy": "DAY-01 VWAP Momentum (Frozen)",
            "execution": "DAY-02 Assumptions (Frozen)",
            "engine": "DAY-03 Optimized Causal Precomputed",
            "provider": prov.__class__.__name__,
        },
    )


def format_multi_symbol_report(result: MultiSymbolDayBacktestResult) -> str:
    """MultiSymbolDayBacktestResult obyektidan toza, professional va non-directive hisobot matnini tuzadi."""
    lines: list[str] = [
        "================================================================================",
        "DAY-04 — MULTI-SYMBOL VALIDATION REPORT",
        "================================================================================",
        "",
        "Overview & Configuration:",
        f"  Strategy: {result.metadata.get('strategy', 'DAY-01 VWAP Momentum')}",
        f"  Execution: {result.metadata.get('execution', 'DAY-02 Assumptions')}",
        f"  Engine: {result.metadata.get('engine', 'DAY-03 Optimized Causal')}",
        f"  Provider: {result.metadata.get('provider', 'DataProvider')}",
        f"  Study Window: {result.study_window_start.strftime('%Y-%m-%d')} → {result.study_window_end.strftime('%Y-%m-%d')}",
        f"  Total Sessions: {result.total_sessions}",
        f"  Symbols Requested: {len(result.universe)}",
        f"  Symbols Tested: {len(result.tested_symbols)}",
        "",
        "Execution Assumptions (Frozen DAY-02):",
        "  Entry: next 5m bar OPEN | Forced exit: 15:55 ET | Stop: SIGNAL_LOW | Target: 2.0R",
        "  Same-bar ambiguity: STOP_FIRST | Long-only | Single position per symbol",
        "",
        "--------------------------------------------------------------------------------",
        "DATA COVERAGE & INTEGRITY",
        "--------------------------------------------------------------------------------",
        f"{'Symbol':<7} | {'Status':<11} | {'5m Bars':<8} | {'15m Bars':<8} | Notes",
        "-" * 80,
    ]

    for sym in result.universe:
        cov = result.coverage.get(sym)
        if cov:
            lines.append(
                f"{sym:<7} | {cov.status.value:<11} | {cov.bars_5m:<8} | {cov.bars_15m:<8} | {cov.reason}"
            )
        else:
            lines.append(f"{sym:<7} | {'MISSING':<11} | {'0':<8} | {'0':<8} | Not processed")

    lines.extend(
        [
            "",
            "--------------------------------------------------------------------------------",
            "PER-SYMBOL VALIDATION METRICS",
            "--------------------------------------------------------------------------------",
            f"{'Symbol':<6} | {'Trades':<6} | {'WinRate':<7} | {'Strat Ret':<9} | {'B&H Ret':<9} | {'Diff':<8} | {'PF':<5} | {'MaxDD':<6} | {'Total R':<8}",
            "-" * 80,
        ]
    )

    for m in result.per_symbol_metrics:
        total_r_str = f"{m.total_R:+.1f}R" if m.total_R is not None else "N/A"
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor < 100 else ">99"
        lines.append(
            f"{m.symbol:<6} | {m.trades:<6} | {m.win_rate*100.0:>6.1f}% | {m.strategy_total_return:>+8.2f}% | {m.buy_hold_return:>+8.2f}% | {m.return_difference_vs_buy_hold:>+7.2f}% | {pf_str:<5} | {m.max_drawdown:>5.2f}% | {total_r_str:<8}"
        )

    agg = result.aggregate_trade_stats
    dist = result.symbol_distribution

    lines.extend(
        [
            "",
            "--------------------------------------------------------------------------------",
            "AGGREGATE TRADE STATISTICS (Trade-Level Pooled)",
            "--------------------------------------------------------------------------------",
            f"  Total Trades: {agg.total_trades}",
            f"  Wins / Losses / Breakevens: {agg.wins} / {agg.losses} / {agg.breakevens}",
            f"  Win Rate: {agg.win_rate * 100.0:.1f}%",
            f"  Profit Factor: {agg.profit_factor:.2f}",
            f"  Expectancy (Avg trade return): {agg.expectancy:+.2f}%",
            f"  Total R: {agg.total_R:+.2f}R",
            f"  Average R: {agg.avg_R:+.2f}R",
            f"  Median R: {agg.median_R:+.2f}R",
            f"  R Standard Deviation: {agg.r_std:.2f}",
            "",
            "--------------------------------------------------------------------------------",
            "SYMBOL-LEVEL DISTRIBUTION",
            "--------------------------------------------------------------------------------",
            f"  Total Symbols Tested: {dist.total_symbols_tested}",
            f"  Positive Strategy Return Symbols: {dist.positive_strategy_symbols} ({dist.positive_strategy_symbols/dist.total_symbols_tested*100:.1f}%)",
            f"  Negative Strategy Return Symbols: {dist.negative_strategy_symbols} ({dist.negative_strategy_symbols/dist.total_symbols_tested*100:.1f}%)",
            f"  Outperformed Buy & Hold Count: {dist.outperformed_buy_hold_count} / {dist.total_symbols_tested} ({dist.outperformed_buy_hold_count/dist.total_symbols_tested*100:.1f}%)",
            f"  Median Symbol Strategy Return: {dist.median_strategy_return:+.2f}%",
            f"  Mean Symbol Strategy Return: {dist.mean_strategy_return:+.2f}%",
            f"  Median Symbol Buy & Hold Return: {dist.median_buy_hold_return:+.2f}%",
            f"  Mean Symbol Buy & Hold Return: {dist.mean_buy_hold_return:+.2f}%",
            "",
            "--------------------------------------------------------------------------------",
            "SLIPPAGE SENSITIVITY (Cross-Universe Aggregated)",
            "--------------------------------------------------------------------------------",
        ]
    )

    for slip_label, s_data in result.slippage_sensitivity.items():
        lines.append(
            f"  {slip_label:<7}: Compounded Return: {s_data['compounded_return_pct']:>+7.2f}% | Win Rate: {s_data['win_rate']*100:>5.1f}% | Avg Trade Return: {s_data['avg_trade_return_pct']:>+5.2f}%"
        )

    if result.market_context:
        mc = result.market_context
        lines.extend(
            [
                "",
                "--------------------------------------------------------------------------------",
                "MARKET REGIME CONTEXT (Diagnostic Only — NOT a strategy filter)",
                "--------------------------------------------------------------------------------",
                f"  SPY Benchmark Total Return: {mc.spy_bnh_return:+.2f}%",
                f"  QQQ Benchmark Total Return: {mc.qqq_bnh_return:+.2f}%",
                f"  Trades on SPY Positive Days: {mc.spy_positive_trades} trades | Win Rate: {mc.spy_positive_win_rate*100:.1f}% | Avg Return: {mc.spy_positive_avg_return:+.2f}%",
                f"  Trades on SPY Negative Days: {mc.spy_negative_trades} trades | Win Rate: {mc.spy_negative_win_rate*100:.1f}% | Avg Return: {mc.spy_negative_avg_return:+.2f}%",
                f"  Trades on QQQ Positive Days: {mc.qqq_positive_trades} trades | Win Rate: {mc.qqq_positive_win_rate*100:.1f}% | Avg Return: {mc.qqq_positive_avg_return:+.2f}%",
                f"  Trades on QQQ Negative Days: {mc.qqq_negative_trades} trades | Win Rate: {mc.qqq_negative_win_rate*100:.1f}% | Avg Return: {mc.qqq_negative_avg_return:+.2f}%",
            ]
        )

    lines.extend(
        [
            "",
            "--------------------------------------------------------------------------------",
            "RESEARCH METHODOLOGY NOTES & LIMITATIONS",
            "--------------------------------------------------------------------------------",
            "1. These results represent historical observations over a common ~60-day window.",
            "2. No parameter optimization was conducted; all rules are identical to DAY-01/02.",
            "3. Multi-symbol aggregation is reported purely as trade-level pooling and symbol distributions.",
            "   No equal-weight portfolio claims are made since capital allocation was not simulated.",
            "4. Slippage severely deteriorates strategy expectancy across all equities.",
            "5. NO VALIDATED MARKET EDGE OR PROFITABILITY IS CLAIMED.",
            "================================================================================",
        ]
    )

    return "\n".join(lines)
