"""backtest/frequency_cap.py: DAY-10 — H3 Session Trade Frequency Cap Research Engine.

Hypothesis H3:
    Many signals / re-entries per symbol within one RTH session may increase churn and
    transaction-cost drag. Does a per-symbol, per-session cap on ACTUAL entries change
    signal quality or net outcome?

Principles:
    1. Signal generation, indicators, entry timing, SIGNAL_LOW stop, 2R target, STOP_FIRST,
       15:55 ET forced exit, long-only and the cost model are 100% frozen (DAY-01/DAY-02).
    2. The cap is applied inside the existing run_day_backtest engine, after the existing
       position-open skip and before entry (backtest.session_gate.SessionEntryGate).
       Only actual entries are counted; the count resets every RTH session.
    3. Caps are pre-declared (H3_CAPS). NO optimization, NO new thresholds.
    4. Trade-sequence attribution (#1..#5+) is explanatory only and never used to pick a cap.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict
import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.dynamic_stop import DynamicStopMetrics, compute_metrics_for_trades
from backtest.failure_analysis import enrich_trade_record, map_exit_reason
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.multi_types import MultiSymbolDayBacktestResult
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.provider import DataProvider
from data.session import get_session_date

logger = logging.getLogger(__name__)

# Pre-declared variants (frozen before seeing results). None = baseline (no cap).
H3_CAPS: tuple[int | None, ...] = (None, 1, 2, 3, 4, 5)

BASELINE_EXPECTED = {
    "total_trades": 5691,
    "win_rate": 0.3042,
    "profit_factor": 0.9388,
    "total_R": -738.98,
    "gross_return_compounded": -41.19,
}

H3_STATUS_RULE = (
    "Pre-declared, mechanical. SUPPORTED: every cap 1-5 has profit_factor AND avg_R above the no-cap "
    "baseline (0 bps) AND its 5 bps compounded return is above the baseline's AND >= 0%. "
    "NOT SUPPORTED: no cap improves both profit_factor and avg_R over the baseline. "
    "INCONCLUSIVE: anything else."
)

_EXIT_KEYS = ("STOP", "TARGET", "FORCED_EXIT")
_SEQ_BUCKETS = ("#1", "#2", "#3", "#4", "#5+")


def variant_name(cap: int | None) -> str:
    return "NO CAP" if cap is None else f"CAP {cap}"


def trade_fingerprint(t: DayBacktestTrade) -> tuple:
    """Execution-relevant fields used for exact baseline/variant comparison (NaN-safe)."""
    return (
        t.symbol, t.setup_time, t.entry_time, t.entry_price, t.exit_time, t.exit_price,
        t.exit_reason, t.stop_price, t.target_price, t.risk_per_share, t.r_multiple, t.gross_return,
    )


def _all_trades(multi: MultiSymbolDayBacktestResult) -> list[DayBacktestTrade]:
    return [t for s in multi.tested_symbols for t in multi.symbol_results[s].trades]


def group_by_symbol_session(trades: Sequence[DayBacktestTrade]) -> dict[tuple[str, Any], list[DayBacktestTrade]]:
    """Trades per (symbol, RTH session), each list in entry order."""
    out: dict[tuple[str, Any], list[DayBacktestTrade]] = defaultdict(list)
    for t in trades:
        out[(t.symbol, get_session_date(t.entry_time))].append(t)
    for k in out:
        out[k].sort(key=lambda t: t.entry_time)
    return out


def _dist(values: Sequence[float]) -> dict[str, float]:
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not vals:
        return {"n": 0}
    a = np.asarray(vals)
    return {
        "n": int(a.size),
        "mean": round(float(a.mean()), 4),
        "p10": round(float(np.percentile(a, 10)), 4),
        "p25": round(float(np.percentile(a, 25)), 4),
        "median": round(float(np.median(a)), 4),
        "p75": round(float(np.percentile(a, 75)), 4),
        "p90": round(float(np.percentile(a, 90)), 4),
        "max": round(float(a.max()), 4),
    }


def _total_r(trades: Sequence[DayBacktestTrade]) -> float:
    return float(sum(t.r_multiple for t in trades if t.r_multiple is not None and not math.isnan(t.r_multiple)))


def _pf(trades: Sequence[DayBacktestTrade]) -> float:
    gw = sum(t.gross_return for t in trades if t.gross_return > 0)
    gl = sum(abs(t.gross_return) for t in trades if t.gross_return < 0)
    if gl > 0:
        return round(gw / gl, 4)
    return 999.0 if gw > 0 else 0.0


def _subgroup_stats(trades: Sequence[DayBacktestTrade], diag: dict[tuple, Any]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"count": 0}
    r_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
    mfe = [diag[trade_fingerprint(t)].mfe_r for t in trades if diag[trade_fingerprint(t)].mfe_r is not None]
    mae = [diag[trade_fingerprint(t)].mae_r for t in trades if diag[trade_fingerprint(t)].mae_r is not None]
    exits = Counter(map_exit_reason(t.exit_reason) for t in trades)
    return {
        "count": n,
        "win_rate": round(sum(1 for t in trades if t.gross_return > 0) / n, 4),
        "profit_factor": _pf(trades),
        "avg_R": round(float(np.mean(r_vals)), 4) if r_vals else 0.0,
        "total_R": round(float(np.sum(r_vals)), 2) if r_vals else 0.0,
        "exit_counts": {k: int(exits.get(k, 0)) for k in _EXIT_KEYS},
        "avg_hold_minutes": round(float(np.mean([t.hold_duration_minutes for t in trades])), 1),
        "avg_stop_distance_pct": round(
            float(np.mean([t.risk_per_share / t.entry_price * 100.0 for t in trades if t.risk_per_share])), 4
        ),
        "avg_mfe_R": round(float(np.mean(mfe)), 4) if mfe else None,
        "avg_mae_R": round(float(np.mean(mae)), 4) if mae else None,
    }


def _seq_bucket(n: int) -> str:
    return f"#{n}" if n <= 4 else "#5+"


def _frequency_distribution(trades: Sequence[DayBacktestTrade], total_symbol_sessions: int) -> dict[str, Any]:
    groups = group_by_symbol_session(trades)
    counts = [len(v) for v in groups.values()]
    hist = Counter(min(c, 5) for c in counts)
    active = len(counts)
    padded = counts + [0] * max(total_symbol_sessions - active, 0)
    return {
        "symbol_sessions_with_entries": active,
        "symbol_sessions_total": total_symbol_sessions,
        "distribution_active_sessions": {
            ("5+" if k == 5 else str(k)): {"sessions": hist.get(k, 0), "pct": round(hist.get(k, 0) / active * 100, 2) if active else 0.0}
            for k in (1, 2, 3, 4, 5)
        },
        "mean_per_active_session": round(float(np.mean(counts)), 3) if counts else 0.0,
        "median_per_active_session": float(np.median(counts)) if counts else 0.0,
        "max_per_session": int(max(counts)) if counts else 0,
        "mean_per_all_symbol_sessions": round(float(np.mean(padded)), 3) if padded else 0.0,
    }


# =====================================================================
# Experiment runner
# =====================================================================

def run_day10_frequency_cap_experiment(
    symbols: Sequence[str] | None = None,
    provider: DataProvider | None = None,
    caps: Sequence[int | None] = H3_CAPS,
) -> dict[str, Any]:
    """Run every pre-declared cap through the unchanged DAY-02 engine on the frozen dataset."""
    prov = provider or get_provider()
    symbols_list = list(symbols) if symbols is not None else get_day_universe()
    if caps[0] is not None:
        raise ValueError("First variant must be the no-cap baseline (None)")

    runs: dict[int | None, MultiSymbolDayBacktestResult] = {}
    for cap in caps:
        runs[cap] = run_multi_symbol_day_backtest(
            symbols=symbols_list,
            provider=prov,
            config=ExecutionConfig(max_trades_per_session=cap),
        )

    base_run = runs[None]
    tested = list(base_run.tested_symbols)
    total_symbol_sessions = len(tested) * base_run.total_sessions
    bnh = {m.symbol: m.buy_hold_return for m in base_run.per_symbol_metrics}
    base_trades = _all_trades(base_run)
    base_groups = group_by_symbol_session(base_trades)

    metrics: dict[str, DynamicStopMetrics] = {}
    accounting: dict[str, dict[str, Any]] = {}
    frequency: dict[str, dict[str, Any]] = {}
    integrity: dict[str, dict[str, Any]] = {}
    concentration: dict[str, dict[str, Any]] = {}

    for cap, run in runs.items():
        name = variant_name(cap)
        trades = _all_trades(run)
        metrics[name] = compute_metrics_for_trades(trades, name, bnh)
        sr = [run.symbol_results[s] for s in run.tested_symbols]
        acc = {
            "candidate_signals": sum(r.candidate_signals for r in sr),
            "actual_entries": len(trades),
            "cap_rejected_entries": sum(r.cap_rejected_signals for r in sr),
            "existing_engine_skipped_position_open": sum(r.skipped_signals for r in sr),
            "simulation_none": sum(r.simulation_none_count for r in sr),
            "window_rejected": sum(r.window_rejected_signals for r in sr),  # DAY-11 gate; always 0 in DAY-10
            "data_insufficient_bars": sum(r.insufficient_data_count for r in sr),
            "same_bar_ambiguity": sum(r.same_bar_ambiguity_count for r in sr),
            "baseline_entries_removed": len(base_trades) - len(trades),
        }
        acc["identity_holds"] = acc["candidate_signals"] == (
            acc["actual_entries"] + acc["existing_engine_skipped_position_open"]
            + acc["cap_rejected_entries"] + acc["window_rejected"] + acc["simulation_none"]
        )
        accounting[name] = acc
        frequency[name] = _frequency_distribution(trades, total_symbol_sessions)

        # exact prefix / subset check against the baseline
        groups = group_by_symbol_session(trades)
        prefix_ok = True
        for key, v_trades in groups.items():
            b = base_groups.get(key, [])
            if [trade_fingerprint(t) for t in v_trades] != [trade_fingerprint(t) for t in b[: len(v_trades)]]:
                prefix_ok = False
                break
        expected_n = sum(len(b) if cap is None else min(len(b), cap) for b in base_groups.values())
        integrity[name] = {
            "candidate_signals_equal_baseline": acc["candidate_signals"] == accounting[variant_name(None)]["candidate_signals"],
            "trades_are_per_session_prefix_of_baseline": prefix_ok,
            "trade_count_equals_min(baseline_session_count, cap)": len(trades) == expected_n,
            "max_entries_per_session_le_cap": cap is None or frequency[name]["max_per_session"] <= cap,
        }

        sym_r: dict[str, float] = defaultdict(float)
        for t in trades:
            sym_r[t.symbol] += t.r_multiple or 0.0
        ranked = sorted(sym_r.items(), key=lambda kv: abs(kv[1]), reverse=True)
        top2 = {s for s, _ in ranked[:2]}
        rest = [t for t in trades if t.symbol not in top2]
        concentration[name] = {
            "per_symbol_total_R": {s: round(sym_r.get(s, 0.0), 2) for s in tested},
            "top2_symbols": [s for s, _ in ranked[:2]],
            "top2_total_R": round(sum(v for _, v in ranked[:2]), 2),
            "excluding_top2_total_R": round(_total_r(rest), 2),
            "excluding_top2_profit_factor": _pf(rest),
            "symbols_with_positive_R": sum(1 for s in tested if sym_r.get(s, 0.0) > 0),
            "symbols_total": len(tested),
        }

    # ---- baseline regression ----
    bm = metrics[variant_name(None)]
    checks = {
        "total_trades": (bm.total_trades, BASELINE_EXPECTED["total_trades"], bm.total_trades == BASELINE_EXPECTED["total_trades"]),
        "win_rate": (bm.win_rate, BASELINE_EXPECTED["win_rate"], abs(bm.win_rate - BASELINE_EXPECTED["win_rate"]) <= 0.0001),
        "profit_factor": (bm.profit_factor, BASELINE_EXPECTED["profit_factor"], abs(bm.profit_factor - BASELINE_EXPECTED["profit_factor"]) <= 0.0005),
        "total_R": (bm.total_R, BASELINE_EXPECTED["total_R"], abs(bm.total_R - BASELINE_EXPECTED["total_R"]) <= 0.01),
        "gross_return_compounded": (bm.gross_return_compounded, BASELINE_EXPECTED["gross_return_compounded"],
                                    abs(bm.gross_return_compounded - BASELINE_EXPECTED["gross_return_compounded"]) <= 0.01),
    }
    regression_ok = all(v[2] for v in checks.values())
    integrity_ok = all(all(v.values()) for v in integrity.values()) and all(a["identity_holds"] for a in accounting.values())

    # ---- trade-sequence attribution on baseline trades (explanatory only) ----
    df_by_sym: dict[str, pd.DataFrame] = {}
    for s in tested:
        try:
            df_by_sym[s] = prov.get_ohlcv(s, "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
        except Exception:
            df_by_sym[s] = pd.DataFrame()
    diag = {trade_fingerprint(t): enrich_trade_record(t, df_by_sym[t.symbol]) for t in base_trades}

    seq_groups: dict[str, list[DayBacktestTrade]] = {b: [] for b in _SEQ_BUCKETS}
    gap_minutes: list[float] = []
    gap_by_seq: dict[str, list[float]] = {b: [] for b in _SEQ_BUCKETS[1:]}
    after_prev_exit: dict[str, list[DayBacktestTrade]] = {k: [] for k in _EXIT_KEYS}
    for group in base_groups.values():
        for n, t in enumerate(group, start=1):
            seq_groups[_seq_bucket(n)].append(t)
            if n >= 2:
                prev = group[n - 2]
                gap = (t.entry_time - prev.exit_time).total_seconds() / 60.0
                gap_minutes.append(gap)
                gap_by_seq[_seq_bucket(n)].append(gap)
                after_prev_exit[map_exit_reason(prev.exit_reason)].append(t)

    sequence_attribution = {b: _subgroup_stats(v, diag) for b, v in seq_groups.items()}
    repeated_entry = {
        "minutes_from_previous_exit_to_next_entry": _dist(gap_minutes),
        "minutes_from_previous_exit_by_sequence": {b: _dist(v) for b, v in gap_by_seq.items()},
        "re_entries_by_previous_exit_reason": {k: _subgroup_stats(v, diag) for k, v in after_prev_exit.items()},
    }

    # ---- pre-declared H3 status ----
    capped = [variant_name(c) for c in caps if c is not None]
    b = metrics[variant_name(None)]
    improves_both = {n: (metrics[n].profit_factor > b.profit_factor and metrics[n].avg_R > b.avg_R) for n in capped}
    five_bps_ok = {n: (metrics[n].slippage_5bps > b.slippage_5bps and metrics[n].slippage_5bps >= 0.0) for n in capped}
    if not regression_ok or not integrity_ok:
        h3_status = "NOT VALIDATED"
    elif all(improves_both.values()) and all(five_bps_ok.values()):
        h3_status = "SUPPORTED"
    elif not any(improves_both.values()):
        h3_status = "NOT SUPPORTED"
    else:
        h3_status = "INCONCLUSIVE"
    worst_5bps = min(metrics[n].slippage_5bps for n in capped)
    best_5bps = max(metrics[n].slippage_5bps for n in capped)

    return {
        "metadata": {
            "experiment": "DAY-10 H3 Session Trade Frequency Cap",
            "variants": [variant_name(c) for c in caps],
            "caps": list(caps),
            "cap_semantics": "per symbol + per RTH session (09:30-16:00 ET); counts ACTUAL entries executed before "
            "the current signal; reset each session; checked after the existing position-open skip and before entry",
            "engine": "backtest.day_engine.run_day_backtest (fast engine, unchanged execution) via run_multi_symbol_day_backtest",
            "execution_rules": {
                "entry": "T + 1 5m OPEN", "initial_stop": "SIGNAL_LOW", "target": "2.0R",
                "same_bar_ambiguity": "STOP_FIRST", "forced_exit": "15:55 ET", "direction": "long-only",
                "costs": "0 bps simulated; 5/10 bps applied post-hoc (DAY-07 compounded model)",
            },
            "h3_status_rule": H3_STATUS_RULE,
            "denominators": {
                "win_rate/profit_factor/R stats": "actual entries of the variant",
                "compounded_return": "product of (1 + gross_return) over the variant's trades by entry_time, 1 unit/trade",
                "frequency distribution": "symbol-sessions with >=1 entry (DAY-05 definition); "
                "mean_per_all_symbol_sessions uses all symbols x sessions",
            },
        },
        "frozen_dataset": {
            "universe_size": len(tested),
            "universe_symbols": tested,
            "period_start": str(base_run.study_window_start),
            "period_end": str(base_run.study_window_end),
            "rth_sessions": base_run.total_sessions,
            "symbol_sessions_total": total_symbol_sessions,
            "timeframes": ["5m", "15m (context)"],
        },
        "baseline_regression": {
            "checks": {k: {"actual": v[0], "expected": v[1], "pass": v[2]} for k, v in checks.items()},
            "regression_verified": regression_ok,
        },
        "metrics": {k: asdict(v) for k, v in metrics.items()},
        "accounting": accounting,
        "frequency_distribution": frequency,
        "integrity": integrity,
        "concentration": concentration,
        "sequence_attribution_baseline": sequence_attribution,
        "repeated_entry_diagnostics_baseline": repeated_entry,
        "pit_validation": {
            "count_uses_only_prior_entries": True,
            "session_reset": True,
            "symbol_isolation": "one gate per symbol backtest run",
            "future_session_information_used": False,
            "verified_by_tests": "tests/test_day10_frequency_cap.py",
        },
        "h3_evaluation": {
            "improves_pf_and_avg_r_vs_baseline": improves_both,
            "five_bps_above_baseline_and_non_negative": five_bps_ok,
            "capped_5bps_range_pct": [worst_5bps, best_5bps],
            "transaction_cost_problem_resolved_at_5bps": best_5bps >= 0.0,
            "h3_status": h3_status,
        },
    }


# =====================================================================
# Report formatter (neutral; never names a best cap)
# =====================================================================

def format_frequency_cap_report(res: dict[str, Any]) -> str:
    L: list[str] = []
    p = L.append
    md, ds, reg = res["metadata"], res["frozen_dataset"], res["baseline_regression"]
    names = md["variants"]
    M, A, F = res["metrics"], res["accounting"], res["frequency_distribution"]

    p("=" * 110)
    p("DAY-10 — H3 SESSION TRADE FREQUENCY CAP — RESEARCH EXPERIMENT REPORT")
    p("=" * 110)
    p("")
    p("1. HYPOTHESIS & DESIGN")
    p("-" * 110)
    p("H3: Many re-entries per symbol per session may increase churn and cost drag. Does a per-session cap on")
    p("actual entries change outcomes? Pre-declared caps only; no cap is selected or called best/optimal.")
    p(f"  Variants      : {', '.join(names)}")
    p(f"  Cap semantics : {md['cap_semantics']}")
    p(f"  Engine        : {md['engine']}")
    for k, v in md["execution_rules"].items():
        p(f"  {k:<14}: {v}")
    p("")
    p("2. FROZEN DATASET")
    p("-" * 110)
    p(f"  {ds['universe_size']} symbols, {ds['rth_sessions']} RTH sessions, {ds['period_start']} -> {ds['period_end']}")
    p(f"  symbol-sessions: {ds['symbol_sessions_total']}  timeframes: {', '.join(ds['timeframes'])}")
    p("")
    p("3. BASELINE REGRESSION (NO CAP == DAY-02 baseline)")
    p("-" * 110)
    for k, v in reg["checks"].items():
        p(f"  {k:<26}: actual={v['actual']}  expected={v['expected']}  {'OK' if v['pass'] else 'MISMATCH'}")
    p(f"  Regression verified: {reg['regression_verified']}")
    p("")

    def table(title: str, rows: list[tuple[str, Any]]) -> None:
        p(title)
        p("-" * 110)
        p(f"{'':<34}" + "".join(f"{n:>15}" for n in names))
        for label, fn in rows:
            p(f"{label:<34}" + "".join(f"{fn(n):>15}" for n in names))
        p("")

    table("4. SIGNAL vs TRADE POPULATION", [
        ("Candidate signals", lambda n: A[n]["candidate_signals"]),
        ("Actual entries", lambda n: A[n]["actual_entries"]),
        ("Cap-rejected entries", lambda n: A[n]["cap_rejected_entries"]),
        ("Engine skipped (position open)", lambda n: A[n]["existing_engine_skipped_position_open"]),
        ("Simulation none (EOD/data end)", lambda n: A[n]["simulation_none"]),
        ("Baseline entries removed", lambda n: A[n]["baseline_entries_removed"]),
        ("Accounting identity holds", lambda n: A[n]["identity_holds"]),
    ])
    table("5. CRITICAL COMPARISON (0 bps unless stated)", [
        ("Trades", lambda n: M[n]["total_trades"]),
        ("Avg trades / active session", lambda n: F[n]["mean_per_active_session"]),
        ("Win rate", lambda n: f"{M[n]['win_rate'] * 100:.2f}%"),
        ("Profit factor", lambda n: f"{M[n]['profit_factor']:.4f}"),
        ("Expectancy (%/trade)", lambda n: f"{M[n]['expectancy']:.4f}"),
        ("Total R", lambda n: f"{M[n]['total_R']:.2f}"),
        ("Average R", lambda n: f"{M[n]['avg_R']:.4f}"),
        ("Median R", lambda n: f"{M[n]['median_R']:.4f}"),
        ("R std", lambda n: f"{M[n]['r_std']:.4f}"),
        ("Max drawdown", lambda n: f"{M[n]['max_drawdown_pct']:.2f}%"),
        ("Compounded 0 bps", lambda n: f"{M[n]['slippage_0bps']:.2f}%"),
        ("Compounded 5 bps", lambda n: f"{M[n]['slippage_5bps']:.2f}%"),
        ("Compounded 10 bps", lambda n: f"{M[n]['slippage_10bps']:.2f}%"),
        ("Wins / Losses / BE", lambda n: f"{M[n]['wins']}/{M[n]['losses']}/{M[n]['breakevens']}"),
        ("Exit STOP", lambda n: M[n]["exit_counts"].get("STOP", 0)),
        ("Exit TARGET", lambda n: M[n]["exit_counts"].get("TARGET", 0)),
        ("Exit FORCED_EXIT", lambda n: M[n]["exit_counts"].get("FORCED_EXIT", 0)),
        ("Same-bar ambiguity", lambda n: A[n]["same_bar_ambiguity"]),
        ("Avg hold (min)", lambda n: M[n]["avg_hold_duration_mins"]),
    ])
    table("6. SESSION FREQUENCY DISTRIBUTION (denominator: symbol-sessions with >=1 entry)", [
        ("Active symbol-sessions", lambda n: F[n]["symbol_sessions_with_entries"]),
        *[(f"{k} trade(s)/session", lambda n, k=k: f"{F[n]['distribution_active_sessions'][k]['sessions']} "
           f"({F[n]['distribution_active_sessions'][k]['pct']:.1f}%)") for k in ("1", "2", "3", "4", "5+")],
        ("Median / active session", lambda n: F[n]["median_per_active_session"]),
        ("Max / session", lambda n: F[n]["max_per_session"]),
        ("Mean / all symbol-sessions", lambda n: F[n]["mean_per_all_symbol_sessions"]),
    ])
    p("7. TRADE-SEQUENCE ATTRIBUTION (baseline trades; explanatory only — NOT used to choose a cap)")
    p("-" * 110)
    p(f"{'Seq':<6}{'Count':>7}{'WR':>9}{'PF':>9}{'Avg R':>9}{'Total R':>10}{'STOP':>7}{'TGT':>6}{'FRC':>6}"
      f"{'Hold':>7}{'Stop%':>9}{'MFE_R':>8}{'MAE_R':>8}")
    for seq, s in res["sequence_attribution_baseline"].items():
        if not s.get("count"):
            p(f"{seq:<6}{0:>7}")
            continue
        e = s["exit_counts"]
        p(f"{seq:<6}{s['count']:>7}{s['win_rate'] * 100:>8.2f}%{s['profit_factor']:>9.4f}{s['avg_R']:>9.4f}"
          f"{s['total_R']:>10.2f}{e['STOP']:>7}{e['TARGET']:>6}{e['FORCED_EXIT']:>6}{s['avg_hold_minutes']:>7.1f}"
          f"{s['avg_stop_distance_pct']:>9.4f}{(s['avg_mfe_R'] or 0):>8.3f}{(s['avg_mae_R'] or 0):>8.3f}")
    p("")
    p("8. REPEATED-ENTRY DIAGNOSTICS (baseline)")
    p("-" * 110)
    rd = res["repeated_entry_diagnostics_baseline"]
    g = rd["minutes_from_previous_exit_to_next_entry"]
    p(f"  Minutes from previous exit to next entry (same symbol-session): n={g.get('n')} median={g.get('median')} "
      f"p25={g.get('p25')} p75={g.get('p75')} p90={g.get('p90')}")
    for seq, d in rd["minutes_from_previous_exit_by_sequence"].items():
        p(f"    {seq}: n={d.get('n')} median={d.get('median')} p75={d.get('p75')}")
    p("  Re-entry outcome by previous trade's exit reason:")
    for k, s in rd["re_entries_by_previous_exit_reason"].items():
        if s.get("count"):
            p(f"    after {k:<12}: n={s['count']}  WR={s['win_rate'] * 100:.2f}%  PF={s['profit_factor']:.4f}  "
              f"avg R={s['avg_R']:.4f}  total R={s['total_R']:.2f}")
    p("")
    p("9. SYMBOL CONCENTRATION")
    p("-" * 110)
    p(f"{'Variant':<10}{'Top-2':>14}{'Top-2 R':>10}{'Ex-top2 R':>12}{'Ex-top2 PF':>12}{'Sym R>0':>10}")
    for n in names:
        c = res["concentration"][n]
        p(f"{n:<10}{','.join(c['top2_symbols']):>14}{c['top2_total_R']:>10.2f}{c['excluding_top2_total_R']:>12.2f}"
          f"{c['excluding_top2_profit_factor']:>12.4f}{c['symbols_with_positive_R']:>6}/{c['symbols_total']}")
    p("")
    p("10. INTEGRITY & POINT-IN-TIME")
    p("-" * 110)
    for n, chk in res["integrity"].items():
        p(f"  {n:<8}: " + ", ".join(f"{k}={v}" for k, v in chk.items()))
    for k, v in res["pit_validation"].items():
        p(f"  {k:<34}: {v}")
    p("")
    p("11. DENOMINATORS")
    p("-" * 110)
    for k, v in md["denominators"].items():
        p(f"  {k:<30}: {v}")
    p("")
    ev = res["h3_evaluation"]
    p("12. H3 EVALUATION (pre-declared rule)")
    p("-" * 110)
    p(f"  Rule: {md['h3_status_rule']}")
    p(f"  PF and avg R above baseline          : {ev['improves_pf_and_avg_r_vs_baseline']}")
    p(f"  5 bps above baseline and >= 0%        : {ev['five_bps_above_baseline_and_non_negative']}")
    p(f"  Capped 5 bps compounded range        : {ev['capped_5bps_range_pct'][0]:.2f}% .. {ev['capped_5bps_range_pct'][1]:.2f}%")
    p(f"  Transaction-cost problem resolved @5bps: {ev['transaction_cost_problem_resolved_at_5bps']}")
    p(f"  H3 STATUS: {ev['h3_status']}")
    p("")
    p("13. INTERPRETATION RULES")
    p("-" * 110)
    p("  - No cap is declared best, optimal or production-ready; no new caps are derived from these results.")
    p("  - Trade-sequence subgroups are explanatory diagnostics only.")
    p("  - Gross (0 bps) changes must be read together with 5/10 bps, drawdown, sample size and symbol spread.")
    p("  - H3 is tested in isolation (SIGNAL_LOW, 2R, existing execution); no H2/H4/time-of-day combination.")
    p("=" * 110)
    return "\n".join(L) + "\n"
