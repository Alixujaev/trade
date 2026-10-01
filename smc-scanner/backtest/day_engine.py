"""backtest/day_engine.py: DAY-02 — VWAP Momentum Backtest Engine.

QAT'IY METODOLOGIK QOIDA:
- NO PARAMETER OPTIMIZATION
- NO THRESHOLD TUNING
- NO STRATEGY MODIFICATION
- NO LOOKAHEAD (Faqat as_of gacha bo'lgan yopilgan barlar)
- NO PROFITABILITY CLAIM (Natijalar o'tmish kuzatuvlari, tasdiqlangan edge emas)
- Long-only, no overnight positions, no overlapping trades.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
import numpy as np
import pandas as pd

from backtest.day_types import (
    DayBacktestResult,
    DayBacktestTrade,
    ExecutionConfig,
)
from backtest.execution import simulate_trade_execution
from backtest.metrics import compute_day_metrics
from backtest.session_gate import SessionEntryGate
from data.bars import filter_closed_bars
from data.factory import get_provider
from data.provider import DataProvider
from data.session import get_session_date, get_session_dates, is_rth_series, to_eastern
from strategy.day.types import DaySetupStatus, VwapRelation
from strategy.day.vwap_momentum import (
    evaluate_vwap_momentum,
    evaluate_vwap_momentum_at_index,
    precompute_day_features,
)


def _prospective_entry_time(df_5m: pd.DataFrame, setup_bar_idx: int) -> pd.Timestamp | None:
    """Entry bar (T+1) open timestamp, mirroring simulate_trade_execution's entry rule.

    Returns None when no same-session next bar exists; then no entry is possible and
    simulate_trade_execution returns None (counted as simulation_none, not as a window rejection).
    """
    entry_idx = setup_bar_idx + 1
    if entry_idx >= len(df_5m):
        return None
    entry_ts = df_5m.index[entry_idx]
    if get_session_date(entry_ts) != get_session_date(df_5m.index[setup_bar_idx]):
        return None
    return entry_ts


def run_day_backtest(
    symbol: str,
    *,
    provider: DataProvider | None = None,
    config: ExecutionConfig | None = None,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    df_extended_5m: pd.DataFrame | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    use_fast_engine: bool = True,
) -> DayBacktestResult:
    """Belgilangan symbol uchun DAY-01 VWAP Momentum strategiyasini point-in-time simulyatsiya qiladi.

    Parameters
    ----------
    symbol : str
        Ticker belgisi (masalan 'AAPL').
    provider : DataProvider | None, optional
        Bozor ma'lumotlari provayderi. None bo'lsa default olinadi.
    config : ExecutionConfig | None, optional
        Execution parametrlari (slippage, stop mode, target, forced exit).
    df_5m : pd.DataFrame | None, optional
        5m barlar (to'g'ridan-to'g'ri berilsa provayderga murojaat qilinmaydi).
    df_15m : pd.DataFrame | None, optional
        15m barlar (MTF kontekst uchun).
    df_extended_5m : pd.DataFrame | None, optional
        Premarket va RTH ni o'z ichiga olgan 5m ma'lumotlar (darajalar uchun).
    start_date : str | pd.Timestamp | None, optional
        Boshlanish sanasi.
    end_date : str | pd.Timestamp | None, optional
        Tugash sanasi.
    use_fast_engine : bool, optional
        True bo'lsa (default), sababiy xususiyatlar bir marta oldindan hisoblanadi (O(N) tezlik).
        False bo'lsa, asl slice-by-slice reference simulyatsiyasi bajariladi.

    Returns
    -------
    DayBacktestResult
        Simulyatsiya natijalari, savdolar ro'yxati va metrikalar.
    """
    exec_config = config or ExecutionConfig()
    prov = provider or get_provider()

    # 1. Ma'lumotlarni olish
    if df_5m is None or df_5m.empty:
        try:
            df_5m = prov.get_ohlcv(
                symbol,
                "5m",
                include_extended_hours=False,
                closed_only=False,
            )
        except Exception as exc:
            now_ts = pd.Timestamp.now()
            return DayBacktestResult(
                symbol=symbol,
                window_start=now_ts,
                window_end=now_ts,
                total_sessions=0,
                total_bars=0,
                trades=[],
                metrics=compute_day_metrics([], 0.0),
                buy_and_hold_return=0.0,
                time_of_day_breakdown={},
                component_breakdown={},
                sensitivity_results={},
                execution_config=exec_config,
            )

    if (df_15m is None or df_15m.empty) and prov is not None:
        try:
            df_15m = prov.get_ohlcv(
                symbol,
                "15m",
                include_extended_hours=False,
                closed_only=False,
            )
        except Exception:
            df_15m = None

    # Sana bo'yicha filtrlash (agar berilgan bo'lsa)
    if start_date is not None:
        ts_start = pd.Timestamp(start_date)
        if df_5m.index.tz is not None and ts_start.tz is None:
            ts_start = ts_start.tz_localize(df_5m.index.tz)
        df_5m = df_5m.loc[df_5m.index >= ts_start]

    if end_date is not None:
        ts_end = pd.Timestamp(end_date)
        if df_5m.index.tz is not None and ts_end.tz is None:
            ts_end = ts_end.tz_localize(df_5m.index.tz)
        df_5m = df_5m.loc[df_5m.index <= ts_end]

    if df_5m.empty or len(df_5m) < 15:
        now_ts = pd.Timestamp.now()
        return DayBacktestResult(
            symbol=symbol,
            window_start=now_ts,
            window_end=now_ts,
            total_sessions=0,
            total_bars=len(df_5m),
            trades=[],
            metrics=compute_day_metrics([], 0.0),
            buy_and_hold_return=0.0,
            time_of_day_breakdown={},
            component_breakdown={},
            sensitivity_results={},
            execution_config=exec_config,
        )

    window_start = df_5m.index[0]
    window_end = df_5m.index[-1]
    sessions = get_session_dates(df_5m.index).unique()
    total_sessions = len(sessions)

    # Buy & Hold daromadi
    first_open = float(df_5m["open"].iloc[0])
    last_close = float(df_5m["close"].iloc[-1])
    bnh_return_pct = (
        ((last_close - first_open) / first_open * 100.0)
        if first_open > 0
        else 0.0
    )

    # 2. Point-in-time bar-by-bar simulyatsiya
    trades: list[DayBacktestTrade] = []
    current_position_exit_idx: int = -1
    skipped_signals: int = 0
    insufficient_data_count: int = 0
    same_bar_ambiguity_count: int = 0
    candidate_signals: int = 0
    cap_rejected_signals: int = 0
    simulation_none_count: int = 0
    window_rejected_signals: int = 0
    window_rejected_entry_times: list[pd.Timestamp] = []
    entry_gate = SessionEntryGate(exec_config.max_trades_per_session)

    n_bars = len(df_5m)
    rth_mask = is_rth_series(df_5m.index)

    if use_fast_engine:
        # Sababiy indikatorlar to'plamini bir marta hisoblash
        features = precompute_day_features(
            df_5m,
            df_15m=df_15m,
            df_extended_5m=df_extended_5m,
        )

        for i in range(14, n_bars):
            if not rth_mask.iloc[i]:
                continue

            setup = evaluate_vwap_momentum_at_index(
                symbol,
                df_5m,
                idx=i,
                features=features,
            )

            if setup.status is DaySetupStatus.DATA_INSUFFICIENT:
                insufficient_data_count += 1
                continue

            if setup.status in exec_config.valid_statuses:
                candidate_signals += 1
                if i < current_position_exit_idx:
                    skipped_signals += 1
                    continue

                # DAY-10 H3: faqat oldin amalga oshgan entry'lar soniga qarab yangi entry'ni cheklash
                signal_session = get_session_date(df_5m.index[i])
                if not entry_gate.allows(signal_session):
                    cap_rejected_signals += 1
                    continue

                # DAY-11 H5: haqiqiy ENTRY bar (T+1 open) vaqti oynadan tashqarida bo'lsa yangi pozitsiya ochilmaydi
                if exec_config.entry_window is not None:
                    entry_ts = _prospective_entry_time(df_5m, i)
                    if entry_ts is not None and not exec_config.entry_window.allows(entry_ts):
                        window_rejected_signals += 1
                        window_rejected_entry_times.append(entry_ts)
                        continue

                sim = simulate_trade_execution(
                    df_5m,
                    setup_bar_idx=i,
                    setup=setup,
                    config=exec_config,
                )

                if sim is not None:
                    trades.append(sim.trade)
                    entry_gate.record_entry(signal_session)
                    current_position_exit_idx = sim.exit_bar_index
                    if sim.was_ambiguous:
                        same_bar_ambiguity_count += 1
                else:
                    simulation_none_count += 1
    else:
        # Reference (slice-by-slice) simulyatsiya
        for i in range(14, n_bars):
            if not rth_mask.iloc[i]:
                continue

            bar_ts = df_5m.index[i]
            bar_end_time = bar_ts + pd.Timedelta(minutes=5)

            df_5m_slice = df_5m.iloc[: i + 1]

            df_15m_slice: pd.DataFrame | None = None
            if df_15m is not None and not df_15m.empty:
                df_15m_slice = filter_closed_bars(df_15m, "15m", as_of=bar_end_time)

            df_ext_slice: pd.DataFrame | None = None
            if df_extended_5m is not None and not df_extended_5m.empty:
                df_ext_slice = filter_closed_bars(df_extended_5m, "5m", as_of=bar_end_time)

            setup = evaluate_vwap_momentum(
                symbol,
                df_5m_slice,
                df_15m=df_15m_slice,
                df_extended_5m=df_ext_slice,
                as_of=bar_end_time,
            )

            if setup.status is DaySetupStatus.DATA_INSUFFICIENT:
                insufficient_data_count += 1
                continue

            if setup.status in exec_config.valid_statuses:
                candidate_signals += 1
                if i < current_position_exit_idx:
                    skipped_signals += 1
                    continue

                # DAY-10 H3: faqat oldin amalga oshgan entry'lar soniga qarab yangi entry'ni cheklash
                signal_session = get_session_date(df_5m.index[i])
                if not entry_gate.allows(signal_session):
                    cap_rejected_signals += 1
                    continue

                # DAY-11 H5: haqiqiy ENTRY bar (T+1 open) vaqti oynadan tashqarida bo'lsa yangi pozitsiya ochilmaydi
                if exec_config.entry_window is not None:
                    entry_ts = _prospective_entry_time(df_5m, i)
                    if entry_ts is not None and not exec_config.entry_window.allows(entry_ts):
                        window_rejected_signals += 1
                        window_rejected_entry_times.append(entry_ts)
                        continue

                sim = simulate_trade_execution(
                    df_5m,
                    setup_bar_idx=i,
                    setup=setup,
                    config=exec_config,
                )

                if sim is not None:
                    trades.append(sim.trade)
                    entry_gate.record_entry(signal_session)
                    current_position_exit_idx = sim.exit_bar_index
                    if sim.was_ambiguous:
                        same_bar_ambiguity_count += 1
                else:
                    simulation_none_count += 1

    # 3. Metrikalar hisoblash
    metrics = compute_day_metrics(trades, buy_and_hold_return=bnh_return_pct)

    # 4. Time-of-day breakdown (bozor vaqti bo'yicha tahlil)
    tod_buckets: dict[str, list[DayBacktestTrade]] = {
        "09:30–10:00": [],
        "10:00–11:00": [],
        "11:00–12:00": [],
        "12:00–14:00": [],
        "14:00–15:00": [],
        "15:00–16:00": [],
    }

    for t in trades:
        t_et = to_eastern(pd.DatetimeIndex([t.setup_time]))[0].time()
        if time(9, 30) <= t_et < time(10, 0):
            tod_buckets["09:30–10:00"].append(t)
        elif time(10, 0) <= t_et < time(11, 0):
            tod_buckets["10:00–11:00"].append(t)
        elif time(11, 0) <= t_et < time(12, 0):
            tod_buckets["11:00–12:00"].append(t)
        elif time(12, 0) <= t_et < time(14, 0):
            tod_buckets["12:00–14:00"].append(t)
        elif time(14, 0) <= t_et < time(15, 0):
            tod_buckets["14:00–15:00"].append(t)
        else:
            tod_buckets["15:00–16:00"].append(t)

    tod_summary = {}
    for bucket_name, b_trades in tod_buckets.items():
        tod_summary[bucket_name] = {
            "trades": len(b_trades),
            "win_rate": (
                sum(1 for tr in b_trades if tr.net_return > 0) / len(b_trades)
                if b_trades
                else 0.0
            ),
            "avg_return_pct": (
                float(np.mean([tr.net_return * 100.0 for tr in b_trades]))
                if b_trades
                else 0.0
            ),
            "avg_R": (
                float(
                    np.mean(
                        [
                            tr.r_multiple
                            for tr in b_trades
                            if tr.r_multiple is not None
                        ]
                    )
                )
                if any(tr.r_multiple is not None for tr in b_trades)
                else None
            ),
        }

    # 5. Component breakdown (har bir gipoteza komponenti bo'yicha)
    def _comp_stats(filtered: list[DayBacktestTrade]) -> dict[str, Any]:
        if not filtered:
            return {"count": 0, "win_rate": 0.0, "avg_return_pct": 0.0}
        return {
            "count": len(filtered),
            "win_rate": sum(1 for tr in filtered if tr.net_return > 0) / len(filtered),
            "avg_return_pct": float(np.mean([tr.net_return * 100.0 for tr in filtered])),
        }

    component_summary = {
        "vwap_reclaim": _comp_stats(
            [t for t in trades if any("VWAP reclaim" in e for e in t.evidence)]
        ),
        "vwap_hold": _comp_stats(
            [t for t in trades if not any("VWAP reclaim" in e for e in t.evidence)]
        ),
        "rsi_above_50": _comp_stats([t for t in trades if t.rsi_at_setup > 50.0]),
        "rsi_below_50": _comp_stats([t for t in trades if t.rsi_at_setup <= 50.0]),
        "rvol_ge_2": _comp_stats([t for t in trades if t.rvol_at_setup >= 2.0]),
        "rvol_lt_2": _comp_stats([t for t in trades if t.rvol_at_setup < 2.0]),
        "structure_15m_bullish": _comp_stats(
            [t for t in trades if t.structure_15m == "BULLISH"]
        ),
        "structure_15m_non_bullish": _comp_stats(
            [t for t in trades if t.structure_15m != "BULLISH"]
        ),
    }

    # 6. Slippage sensitivity tahlili (0 bps, 5 bps, 10 bps)
    sensitivity_results = {}
    for slip_bps in (0.0, 5.0, 10.0):
        slip_cfg = ExecutionConfig(
            slippage_bps=slip_bps,
            commission_per_share=exec_config.commission_per_share,
            stop_mode=exec_config.stop_mode,
            target_multiple=exec_config.target_multiple,
            force_exit_time=exec_config.force_exit_time,
            same_bar_rule=exec_config.same_bar_rule,
        )
        # Savdolar ustidan xarajatlarni qayta hisoblash
        sim_returns = []
        for t in trades:
            raw_ent = t.entry_price / (1.0 + (exec_config.slippage_bps / 10000.0))
            raw_ex = (t.exit_price + exec_config.commission_per_share) / (
                1.0 - (exec_config.slippage_bps / 10000.0)
            )

            new_ent = raw_ent * (1.0 + (slip_bps / 10000.0)) + slip_cfg.commission_per_share
            new_ex = raw_ex * (1.0 - (slip_bps / 10000.0)) - slip_cfg.commission_per_share
            sim_returns.append((new_ex - new_ent) / new_ent)

        c_ret = 1.0
        for r in sim_returns:
            c_ret *= 1.0 + r
        tot_pct = (c_ret - 1.0) * 100.0 if sim_returns else 0.0
        sensitivity_results[f"{int(slip_bps)} bps"] = {
            "total_return_pct": tot_pct,
            "avg_return_pct": (
                float(np.mean([r * 100.0 for r in sim_returns])) if sim_returns else 0.0
            ),
        }

    return DayBacktestResult(
        symbol=symbol,
        window_start=window_start,
        window_end=window_end,
        total_sessions=total_sessions,
        total_bars=n_bars,
        trades=trades,
        metrics=metrics,
        buy_and_hold_return=bnh_return_pct,
        time_of_day_breakdown=tod_summary,
        component_breakdown=component_summary,
        sensitivity_results=sensitivity_results,
        skipped_signals=skipped_signals,
        insufficient_data_count=insufficient_data_count,
        same_bar_ambiguity_count=same_bar_ambiguity_count,
        execution_config=exec_config,
        candidate_signals=candidate_signals,
        cap_rejected_signals=cap_rejected_signals,
        simulation_none_count=simulation_none_count,
        window_rejected_signals=window_rejected_signals,
        window_rejected_entry_times=window_rejected_entry_times,
    )


def run_day_backtest_reference(
    symbol: str,
    *,
    provider: DataProvider | None = None,
    config: ExecutionConfig | None = None,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    df_extended_5m: pd.DataFrame | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> DayBacktestResult:
    """Asl unoptimized slice-by-slice simulyatsiyani bajaradi (ekvivalentlik testlari uchun)."""
    return run_day_backtest(
        symbol,
        provider=provider,
        config=config,
        df_5m=df_5m,
        df_15m=df_15m,
        df_extended_5m=df_extended_5m,
        start_date=start_date,
        end_date=end_date,
        use_fast_engine=False,
    )


def format_day_backtest_report(result: DayBacktestResult) -> str:
    """DayBacktestResult obyektidan toza, xolis va non-directive hisobot matnini generatsiya qiladi."""
    m = result.metrics
    lines = [
        "DAY-02 VWAP MOMENTUM BACKTEST",
        "==============================",
        "",
        "Data:",
        f"Symbol: {result.symbol}",
        "Interval: 5m",
        f"Window: {result.window_start.strftime('%Y-%m-%d')} → {result.window_end.strftime('%Y-%m-%d')}",
        f"Sessions: {result.total_sessions}",
        f"Bars: {result.total_bars}",
        "",
        "Strategy (Frozen DAY-01):",
        "RSI(14) > 50",
        "RVOL >= 2.0",
        "VWAP reclaim",
        "5m trigger",
        "15m context",
        "",
        "Execution (Backtest Assumptions):",
        "Entry: next bar open",
        f"Forced exit: {result.execution_config.force_exit_time.strftime('%H:%M')} ET",
        f"Slippage: {result.execution_config.slippage_bps:.0f} bps",
        f"Commission: ${result.execution_config.commission_per_share:.2f}",
        f"Same-bar ambiguity: {result.execution_config.same_bar_rule}",
        f"Stop mode: {result.execution_config.stop_mode}",
        f"Target multiple: {result.execution_config.target_multiple}R",
        "",
        "Results:",
        f"Trades: {m['total_trades']}",
        f"Wins: {m['winning_trades']}",
        f"Losses: {m['losing_trades']}",
        f"Win rate: {m['win_rate'] * 100.0:.1f}%",
        "",
        "Return:",
        f"Strategy: {m['total_return_pct']:+.2f}%",
        f"Buy & Hold: {result.buy_and_hold_return:+.2f}%",
        f"Average trade return: {m['average_return_pct']:+.2f}%",
        "",
        "Risk:",
        f"Max drawdown: {m['max_drawdown_pct']:.2f}%",
        f"Profit factor: {m['profit_factor']:.2f}",
    ]

    if m["average_R"] is not None:
        lines.extend(
            [
                "",
                "R Metrics:",
                f"Average R: {m['average_R']:+.2f}",
                f"Median R: {m['median_R']:+.2f}",
                f"Total R: {m['total_R']:+.2f}",
            ]
        )

    lines.extend(
        [
            "",
            "Data Quality & Execution:",
            f"Skipped signals (position open): {result.skipped_signals}",
            f"Insufficient data bars: {result.insufficient_data_count}",
            f"Same-bar ambiguous bars: {result.same_bar_ambiguity_count}",
            "",
            "Time-of-Day Breakdown:",
        ]
    )

    for tod, stats in result.time_of_day_breakdown.items():
        lines.append(
            f"  {tod}: {stats['trades']} trades | Win rate: {stats['win_rate']*100:.1f}% | Avg return: {stats['avg_return_pct']:+.2f}%"
        )

    lines.extend(["", "Slippage Sensitivity:"])
    for slip, s_stats in result.sensitivity_results.items():
        lines.append(f"  {slip}: Total return: {s_stats['total_return_pct']:+.2f}%")

    lines.extend(
        [
            "",
            "IMPORTANT:",
            "These are historical observations, not a validated trading edge.",
        ]
    )

    return "\n".join(lines)
