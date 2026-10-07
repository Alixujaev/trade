"""backtest/time_window.py: DAY-11 — H5 Time-of-Day Execution Window Research Engine.

Hypothesis H5:
    Does restricting the time of day during which NEW entries are allowed improve gross and
    transaction-cost-adjusted performance?

Principles:
    1. Signal generation, position-open semantics, entry timing (T+1 5m OPEN), SIGNAL_LOW stop,
       2R target, STOP_FIRST, 15:55 ET forced exit, long-only and the cost model are frozen.
    2. The window gates only the ACTUAL entry-bar open timestamp (not the signal bar), as a
       half-open ET interval [start, end). It never closes or modifies an open position.
    3. FULL = [09:30, 16:00) = existing semantics (any same-session RTH entry bar), so FULL must
       reproduce the no-gate baseline exactly (incl. the 15:50-signal / 15:55-entry trades).
    4. Windows are pre-declared (session_gate.ENTRY_WINDOWS). No optimization, no new windows,
       no combination with H3 caps or H4 ATR stops.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict
import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.dynamic_stop import compute_metrics_for_trades
from backtest.failure_analysis import get_time_of_day_bucket, map_exit_reason
from backtest.frequency_cap import _frequency_distribution, group_by_symbol_session, trade_fingerprint
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.multi_types import MultiSymbolDayBacktestResult
from backtest.session_gate import ENTRY_WINDOWS, EntryWindow
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.provider import DataProvider
from data.session import to_eastern

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
DAY10_RESULTS = ROOT_DIR / "artifacts" / "day10" / "frequency-cap-results.json"
TOD_BINS = ("09:30–10:00", "10:00–11:00", "11:00–12:00", "12:00–14:00", "14:00–15:00", "15:00–15:55")
_EXIT_KEYS = ("STOP", "TARGET", "FORCED_EXIT")
_ANCHOR_KEYS = (
    "total_trades", "win_rate", "profit_factor", "total_R", "avg_R",
    "max_drawdown_pct", "slippage_0bps", "slippage_5bps", "slippage_10bps",
)

# Analyst criterion written BEFORE DAY-11 results were computed. It is NOT part of the research
# protocol's pre-declared rules; it operationalises the prompt's qualitative definitions.
H5_STATUS_CRITERION = (
    "Analyst criterion defined before DAY-11 results were viewed (not a protocol-predeclared rule). "
    "SUPPORTED: at least one restricted window has profit_factor > 1, a non-negative 5 bps compounded "
    "return, AND positive total R in a majority of symbols. NOT VALIDATED: no restricted window improves "
    "both profit_factor and avg_R over FULL. INCONCLUSIVE: anything else."
)


def _bucket(ts) -> str:
    return get_time_of_day_bucket(to_eastern(ts).time())


def _all_trades(multi: MultiSymbolDayBacktestResult) -> list[DayBacktestTrade]:
    return [t for s in multi.tested_symbols for t in multi.symbol_results[s].trades]


def _pf(trades: Sequence[DayBacktestTrade]) -> float:
    gw = sum(t.gross_return for t in trades if t.gross_return > 0)
    gl = sum(abs(t.gross_return) for t in trades if t.gross_return < 0)
    if gl > 0:
        return round(gw / gl, 4)
    return 999.0 if gw > 0 else 0.0


def _quality(trades: Sequence[DayBacktestTrade]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"count": 0}
    r = [t.r_multiple for t in trades if t.r_multiple is not None]
    ex = Counter(map_exit_reason(t.exit_reason) for t in trades)
    return {
        "count": n,
        "win_rate": round(sum(1 for t in trades if t.gross_return > 0) / n, 4),
        "profit_factor": _pf(trades),
        "avg_R": round(float(np.mean(r)), 4) if r else 0.0,
        "total_R": round(float(np.sum(r)), 2) if r else 0.0,
        "exit_counts": {k: int(ex.get(k, 0)) for k in _EXIT_KEYS},
        "avg_hold_minutes": round(float(np.mean([t.hold_duration_minutes for t in trades])), 1),
    }


def load_regression_anchors(path: Path = DAY10_RESULTS) -> dict[str, float]:
    """Regression anchors from the frozen DAY-10 NO CAP output (not hardcoded in logic)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    m = data["metrics"]["NO CAP"]
    return {k: m[k] for k in _ANCHOR_KEYS}


def run_day11_time_window_experiment(
    symbols: Sequence[str] | None = None,
    provider: DataProvider | None = None,
    windows: Sequence[EntryWindow] = ENTRY_WINDOWS,
    anchors_path: Path = DAY10_RESULTS,
) -> dict[str, Any]:
    prov = provider or get_provider()
    symbols_list = list(symbols) if symbols is not None else get_day_universe()

    ref = run_multi_symbol_day_backtest(symbols=symbols_list, provider=prov)  # no gate = baseline
    runs = {
        w.name: run_multi_symbol_day_backtest(
            symbols=symbols_list, provider=prov, config=ExecutionConfig(entry_window=w)
        )
        for w in windows
    }

    tested = list(ref.tested_symbols)
    total_symbol_sessions = len(tested) * ref.total_sessions
    bnh = {m.symbol: m.buy_hold_return for m in ref.per_symbol_metrics}
    ref_trades = _all_trades(ref)
    ref_fp = [trade_fingerprint(t) for t in ref_trades]
    ref_candidates = sum(ref.symbol_results[s].candidate_signals for s in tested)

    metrics: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    accounting: dict[str, Any] = {}
    frequency: dict[str, Any] = {}
    integrity: dict[str, Any] = {}
    accepted_by_bin: dict[str, Any] = {}
    rejected_by_bin: dict[str, Any] = {}
    concentration: dict[str, Any] = {}

    for w in windows:
        run = runs[w.name]
        trades = _all_trades(run)
        sr = [run.symbol_results[s] for s in run.tested_symbols]
        m = compute_metrics_for_trades(trades, w.name, bnh)
        metrics[w.name] = asdict(m)
        holds = [t.hold_duration_minutes for t in trades]
        extra[w.name] = {
            "median_hold_minutes": float(np.median(holds)) if holds else 0.0,
            "benchmark_mean_bnh_return_pct": m.mean_bnh_return,
        }
        acc = {
            "candidate_signals": sum(r.candidate_signals for r in sr),
            "actual_entries": len(trades),
            "window_rejected": sum(r.window_rejected_signals for r in sr),
            "position_open_skips": sum(r.skipped_signals for r in sr),
            "cap_rejected": sum(r.cap_rejected_signals for r in sr),
            "simulation_none": sum(r.simulation_none_count for r in sr),
            "same_bar_ambiguity": sum(r.same_bar_ambiguity_count for r in sr),
            "baseline_entries_not_taken": len(ref_trades) - len(trades),
        }
        acc["identity"] = "candidates = entries + position_open_skips + cap_rejected + window_rejected + simulation_none"
        acc["identity_holds"] = acc["candidate_signals"] == (
            acc["actual_entries"] + acc["position_open_skips"] + acc["cap_rejected"]
            + acc["window_rejected"] + acc["simulation_none"]
        )
        accounting[w.name] = acc
        frequency[w.name] = _frequency_distribution(trades, total_symbol_sessions)

        expected = [fp for fp, t in zip(ref_fp, ref_trades) if w.allows(t.entry_time)]
        got = [trade_fingerprint(t) for t in trades]
        integrity[w.name] = {
            "candidate_signals_equal_baseline": acc["candidate_signals"] == ref_candidates,
            "trades_equal_baseline_filtered_by_window": got == expected,
            "all_entries_inside_window": all(w.allows(t.entry_time) for t in trades),
            "no_cap_applied": acc["cap_rejected"] == 0,
            "stop_mode_signal_low_target_2r": run.execution_config.stop_mode == "SIGNAL_LOW"
            and run.execution_config.target_multiple == 2.0,
        }

        accepted_by_bin[w.name] = {b: 0 for b in TOD_BINS}
        for t in trades:
            accepted_by_bin[w.name][_bucket(t.entry_time)] = accepted_by_bin[w.name].get(_bucket(t.entry_time), 0) + 1
        rejected_by_bin[w.name] = {b: 0 for b in TOD_BINS}
        for r in sr:
            for ts in r.window_rejected_entry_times:
                rejected_by_bin[w.name][_bucket(ts)] = rejected_by_bin[w.name].get(_bucket(ts), 0) + 1

        sym_r: dict[str, float] = defaultdict(float)
        for t in trades:
            sym_r[t.symbol] += t.r_multiple or 0.0
        concentration[w.name] = {
            "per_symbol_total_R": {s: round(sym_r.get(s, 0.0), 2) for s in tested},
            "symbols_with_positive_R": sum(1 for s in tested if sym_r.get(s, 0.0) > 0),
            "symbols_total": len(tested),
            "top2_abs_R_symbols": [s for s, _ in sorted(sym_r.items(), key=lambda kv: abs(kv[1]), reverse=True)[:2]],
        }

    # ---- regression: no-gate reference and FULL vs frozen DAY-10 NO CAP anchors ----
    anchors = load_regression_anchors(anchors_path)
    ref_m = asdict(compute_metrics_for_trades(ref_trades, "NO GATE", bnh))
    regression = {
        "anchors_source": str(anchors_path.relative_to(ROOT_DIR)),
        "no_gate_matches_anchors": {k: ref_m[k] == anchors[k] for k in _ANCHOR_KEYS},
        "full_matches_anchors": {k: metrics["FULL"][k] == anchors[k] for k in _ANCHOR_KEYS},
        "full_trades_identical_to_no_gate": [trade_fingerprint(t) for t in _all_trades(runs["FULL"])] == ref_fp,
        "anchors": anchors,
    }
    regression["regression_verified"] = (
        all(regression["no_gate_matches_anchors"].values())
        and all(regression["full_matches_anchors"].values())
        and regression["full_trades_identical_to_no_gate"]
    )

    # ---- baseline diagnostics (explanatory only) ----
    by_bin: dict[str, list[DayBacktestTrade]] = {b: [] for b in TOD_BINS}
    for t in ref_trades:
        by_bin.setdefault(_bucket(t.entry_time), []).append(t)
    entry_1555 = [t for t in ref_trades if to_eastern(t.entry_time).strftime("%H:%M") == "15:55"]
    boundary_entries = {
        hhmm: sum(1 for t in ref_trades if to_eastern(t.entry_time).strftime("%H:%M") == hhmm)
        for hhmm in ("11:00", "12:00", "13:00", "14:00", "15:55")
    }

    # ---- status evidence ----
    full = metrics["FULL"]
    restricted = [w.name for w in windows if w.name != "FULL"]
    evidence = {}
    for n in restricted:
        mm = metrics[n]
        evidence[n] = {
            "pf_and_avg_r_above_full": mm["profit_factor"] > full["profit_factor"] and mm["avg_R"] > full["avg_R"],
            "pf_above_1": mm["profit_factor"] > 1.0,
            "five_bps_non_negative": mm["slippage_5bps"] >= 0.0,
            "ten_bps_non_negative": mm["slippage_10bps"] >= 0.0,
            "majority_symbols_positive_R": concentration[n]["symbols_with_positive_R"] > len(tested) / 2,
        }
    integrity_ok = all(all(v.values()) for v in integrity.values()) and all(a["identity_holds"] for a in accounting.values())
    if not regression["regression_verified"] or not integrity_ok:
        status = "NOT VALIDATED (regression/integrity failure)"
    elif any(e["pf_above_1"] and e["five_bps_non_negative"] and e["majority_symbols_positive_R"] for e in evidence.values()):
        status = "SUPPORTED"
    elif not any(e["pf_and_avg_r_above_full"] for e in evidence.values()):
        status = "NOT VALIDATED"
    else:
        status = "INCONCLUSIVE"

    ranked_gross = sorted(restricted, key=lambda n: metrics[n]["slippage_0bps"], reverse=True)

    return {
        "metadata": {
            "experiment": "DAY-11 H5 Time-of-Day Execution Window",
            "research_question": "Does restricting the time of day during which NEW entries are allowed improve "
            "gross and transaction-cost-adjusted performance?",
            "windows": {w.name: w.describe() for w in windows},
            "window_semantics": "Half-open ET interval [start, end) applied to the ACTUAL entry bar open timestamp "
            "(T+1 5m OPEN). Gate order: candidate -> position-open skip -> (cap, unused) -> window gate -> "
            "simulate_trade_execution. A signal with no same-session entry bar is simulation_none, not window-rejected. "
            "The window never closes or modifies an open position.",
            "full_definition_note": "FULL = [09:30, 16:00) = existing semantics; chosen over a literal '< 15:55' "
            "because 128 baseline trades enter at the 15:55 bar open (15:50 signal) and are forced out at that "
            "bar's close. Decision confirmed by the user before implementation.",
            "timestamp_semantics": "5m bar timestamp = bar OPEN; signal observable at bar END; entry at next bar OPEN.",
            "execution_rules": {
                "entry": "T + 1 5m OPEN", "initial_stop": "SIGNAL_LOW", "target": "2.0R",
                "same_bar_ambiguity": "STOP_FIRST", "forced_exit": "15:55 ET", "direction": "long-only",
                "frequency_cap": "none", "costs": "0 bps simulated; 5/10 bps applied post-hoc (DAY-07 compounded model)",
            },
            "benchmark": "per-symbol buy & hold: first RTH open -> last RTH close over the same period "
            "(mean across symbols), unchanged and independent of the entry window",
            "status_criterion": H5_STATUS_CRITERION,
        },
        "frozen_dataset": {
            "universe_size": len(tested),
            "universe_symbols": tested,
            "period_start": str(ref.study_window_start),
            "period_end": str(ref.study_window_end),
            "rth_sessions": ref.total_sessions,
            "symbol_sessions_total": total_symbol_sessions,
        },
        "baseline_regression": regression,
        "metrics": metrics,
        "extra_metrics": extra,
        "accounting": accounting,
        "frequency_distribution": frequency,
        "integrity": integrity,
        "accepted_entries_by_bin": accepted_by_bin,
        "rejected_candidate_entries_by_bin": rejected_by_bin,
        "baseline_quality_by_entry_bin": {b: _quality(v) for b, v in by_bin.items()},
        "baseline_boundary_entries": boundary_entries,
        "baseline_1555_entries": _quality(entry_1555),
        "concentration": concentration,
        "h5_evaluation": {
            "evidence_by_restricted_window": evidence,
            "restricted_windows_by_gross_0bps_desc": ranked_gross,
            "status": status,
        },
    }


# =====================================================================
# Report formatter (neutral; never selects a window)
# =====================================================================

def format_time_window_report(res: dict[str, Any]) -> str:
    L: list[str] = []
    p = L.append
    md, ds, reg = res["metadata"], res["frozen_dataset"], res["baseline_regression"]
    names = list(md["windows"].keys())
    M, X, A, F = res["metrics"], res["extra_metrics"], res["accounting"], res["frequency_distribution"]
    W = 15

    def table(rows):
        p(f"{'':<34}" + "".join(f"{n:>{W}}" for n in names))
        for label, fn in rows:
            p(f"{label:<34}" + "".join(f"{fn(n):>{W}}" for n in names))
        p("")

    p("=" * 115)
    p("DAY-11 — H5 TIME-OF-DAY EXECUTION WINDOW — RESEARCH EXPERIMENT REPORT")
    p("=" * 115)
    p("")
    p("1. RESEARCH QUESTION")
    p("-" * 115)
    p(f"  {md['research_question']}")
    p("  Tested in isolation: no frequency cap, no ATR stop, no BE, no gap/index filter.")
    p("")
    p("2. FROZEN BASELINE & DATA")
    p("-" * 115)
    p(f"  Universe     : {ds['universe_size']} symbols ({', '.join(ds['universe_symbols'])})")
    p(f"  Period       : {ds['period_start']} -> {ds['period_end']} ({ds['rth_sessions']} RTH sessions, "
      f"{ds['symbol_sessions_total']} symbol-sessions)")
    p(f"  Benchmark    : {md['benchmark']}")
    p("")
    p("3. WINDOW DEFINITIONS & SEMANTICS")
    p("-" * 115)
    for n, d in md["windows"].items():
        p(f"  {n:<12}: {d}")
    p(f"  Semantics    : {md['window_semantics']}")
    p(f"  Timestamps   : {md['timestamp_semantics']}")
    p(f"  FULL note    : {md['full_definition_note']}")
    p("")
    p("4. EXECUTION ASSUMPTIONS")
    p("-" * 115)
    for k, v in md["execution_rules"].items():
        p(f"  {k:<18}: {v}")
    p("")
    p("5. REGRESSION (no-gate run and FULL vs frozen DAY-10 NO CAP anchors)")
    p("-" * 115)
    p(f"  Anchors source: {reg['anchors_source']}")
    for k, v in reg["anchors"].items():
        p(f"  {k:<20}: anchor={v}  no-gate={'OK' if reg['no_gate_matches_anchors'][k] else 'MISMATCH'}  "
          f"FULL={'OK' if reg['full_matches_anchors'][k] else 'MISMATCH'}")
    p(f"  FULL trades identical to no-gate baseline: {reg['full_trades_identical_to_no_gate']}")
    p(f"  Regression verified: {reg['regression_verified']}")
    p("")
    p("6. SIGNAL vs TRADE POPULATION (candidate invariance)")
    p("-" * 115)
    table([
        ("Candidate signals", lambda n: A[n]["candidate_signals"]),
        ("Actual entries", lambda n: A[n]["actual_entries"]),
        ("Window-rejected", lambda n: A[n]["window_rejected"]),
        ("Position-open skips", lambda n: A[n]["position_open_skips"]),
        ("Cap-rejected", lambda n: A[n]["cap_rejected"]),
        ("Simulation none", lambda n: A[n]["simulation_none"]),
        ("Baseline entries not taken", lambda n: A[n]["baseline_entries_not_taken"]),
        ("Identity holds", lambda n: A[n]["identity_holds"]),
    ])
    p(f"  Identity: {A[names[0]]['identity']}")
    p("")
    p("7. RESULTS (0 bps unless stated)")
    p("-" * 115)
    table([
        ("Trades", lambda n: M[n]["total_trades"]),
        ("Avg trades / active session", lambda n: F[n]["mean_per_active_session"]),
        ("Wins / Losses / BE", lambda n: f"{M[n]['wins']}/{M[n]['losses']}/{M[n]['breakevens']}"),
        ("Win rate", lambda n: f"{M[n]['win_rate'] * 100:.2f}%"),
        ("Profit factor", lambda n: f"{M[n]['profit_factor']:.4f}"),
        ("Total R", lambda n: f"{M[n]['total_R']:.2f}"),
        ("Average R", lambda n: f"{M[n]['avg_R']:.4f}"),
        ("Median R", lambda n: f"{M[n]['median_R']:.4f}"),
        ("R std", lambda n: f"{M[n]['r_std']:.4f}"),
        ("Max drawdown", lambda n: f"{M[n]['max_drawdown_pct']:.2f}%"),
        ("Avg hold (min)", lambda n: M[n]["avg_hold_duration_mins"]),
        ("Median hold (min)", lambda n: X[n]["median_hold_minutes"]),
        ("Exit STOP", lambda n: M[n]["exit_counts"].get("STOP", 0)),
        ("Exit TARGET", lambda n: M[n]["exit_counts"].get("TARGET", 0)),
        ("Exit FORCED_EXIT", lambda n: M[n]["exit_counts"].get("FORCED_EXIT", 0)),
        ("Same-bar ambiguity", lambda n: A[n]["same_bar_ambiguity"]),
        ("Benchmark mean B&H %", lambda n: f"{X[n]['benchmark_mean_bnh_return_pct']:.2f}"),
    ])
    p("8. TRANSACTION COSTS (compounded, 1 unit/trade, by entry_time)")
    p("-" * 115)
    table([
        ("0 bps", lambda n: f"{M[n]['slippage_0bps']:.2f}%"),
        ("5 bps", lambda n: f"{M[n]['slippage_5bps']:.2f}%"),
        ("10 bps", lambda n: f"{M[n]['slippage_10bps']:.2f}%"),
    ])
    p("9. ACCEPTED ENTRIES BY DAY-05 TIME BIN")
    p("-" * 115)
    table([(b, lambda n, b=b: res["accepted_entries_by_bin"][n].get(b, 0)) for b in TOD_BINS])
    p("10. WINDOW-REJECTED CANDIDATE ENTRIES BY TIME BIN (bin of the would-be entry bar)")
    p("-" * 115)
    table([(b, lambda n, b=b: res["rejected_candidate_entries_by_bin"][n].get(b, 0)) for b in TOD_BINS])
    p("11. BASELINE TRADE QUALITY BY ENTRY BIN (explanatory only — NOT used to select a window)")
    p("-" * 115)
    p(f"{'Bin':<16}{'Count':>7}{'WR':>9}{'PF':>9}{'Avg R':>9}{'Total R':>10}{'STOP':>7}{'TGT':>6}{'FRC':>6}{'Hold':>7}")
    for b, q in res["baseline_quality_by_entry_bin"].items():
        if not q.get("count"):
            continue
        e = q["exit_counts"]
        p(f"{b:<16}{q['count']:>7}{q['win_rate'] * 100:>8.2f}%{q['profit_factor']:>9.4f}{q['avg_R']:>9.4f}"
          f"{q['total_R']:>10.2f}{e['STOP']:>7}{e['TARGET']:>6}{e['FORCED_EXIT']:>6}{q['avg_hold_minutes']:>7.1f}")
    q = res["baseline_1555_entries"]
    p(f"  Baseline 15:55-entry trades (enter and forced-exit on the same bar): {q.get('count', 0)}, "
      f"total R {q.get('total_R', 0)}, avg R {q.get('avg_R', 0)}")
    p(f"  Baseline entries exactly at window boundaries: {res['baseline_boundary_entries']}")
    p("")
    p("12. SYMBOL SPREAD")
    p("-" * 115)
    table([
        ("Symbols with positive R", lambda n: f"{res['concentration'][n]['symbols_with_positive_R']}/{res['concentration'][n]['symbols_total']}"),
        ("Top-2 |R| symbols", lambda n: ",".join(res["concentration"][n]["top2_abs_R_symbols"])),
    ])
    p("13. INTEGRITY")
    p("-" * 115)
    for n, chk in res["integrity"].items():
        p(f"  {n:<12}: " + ", ".join(f"{k}={v}" for k, v in chk.items()))
    if "validation" in res:
        p("")
        p("14. TESTS, PIT, BOUNDARIES & CACHE VERIFICATION")
        p("-" * 115)
        for k, v in res["validation"].items():
            p(f"  {k}: {v}")
    p("")
    ev = res["h5_evaluation"]
    p("15. FACTUAL INTERPRETATION & H5 STATUS")
    p("-" * 115)
    top = ev["restricted_windows_by_gross_0bps_desc"][0]
    p(f"  {top} produced the highest gross (0 bps) compounded return among the tested pre-declared restricted "
      f"variants ({M[top]['slippage_0bps']:.2f}%); at 5 bps it is {M[top]['slippage_5bps']:.2f}% and at 10 bps "
      f"{M[top]['slippage_10bps']:.2f}%. This is not a selection.")
    for n, e in ev["evidence_by_restricted_window"].items():
        p(f"  {n:<12}: " + ", ".join(f"{k}={v}" for k, v in e.items()))
    p(f"  Status criterion: {res['metadata']['status_criterion']}")
    p(f"  H5 STATUS: {ev['status']}")
    p("  No window is declared best, optimal or production-ready.")
    p("=" * 115)
    return "\n".join(L) + "\n"
