"""backtest/breakeven_05.py: DAY-12B — +0.5R -> Breakeven counterfactual (ONE exit-management hypothesis).

Hypothesis (new; NOT pre-declared by earlier research):
    "Move the stop to breakeven after the trade has reached +0.5R."

Provenance / multiple-testing caveat:
    The 0.5R level was chosen AFTER viewing DAY-12A (which reported the share of losers reaching +0.5R)
    and after DAY-07 (BE @ 1.0R) and DAY-07A (BE @ 0.75 / 1.00 / 1.25R) were evaluated on the SAME frozen
    dataset. DAY-12B is therefore effectively a fourth threshold of the H2 breakeven family, selected
    with knowledge of the data. Results are in-sample and subject to data-snooping bias.

Semantics (reuses the existing opt-in DAY-07 engine path, ExecutionConfig.breakeven_trigger_r; no engine change):
    - R = entry - original SIGNAL_LOW stop (never recalculated). Trigger price = entry + 0.5 * R.
    - The trigger is recognised only from a CLOSED 5m bar that produced no exit and whose High >= trigger.
      The BE stop (exactly entry) is active from the NEXT bar; never applied retroactively to the trigger bar.
    - Stopped before a closed bar confirms +0.5R -> normal STOP at the original stop.
    - Target = entry + 2 * R (unchanged). A target touched on the trigger bar executes normally.
    - Later bar touching both BE stop and target -> existing STOP_FIRST rule -> "breakeven" exit (ambiguous).
    - A bar opening below entry after BE is active fills at entry (existing engine stop-fill convention);
      such gap-through BE exits are counted as a limitation.
    - 15:55 ET forced exit, long-only, 0 bps simulation with 5/10 bps applied post-hoc: unchanged.

Population: PAIRED 1:1 (same as DAY-07/07A/09). Every baseline trade is re-simulated from its own signal
bar; the candidate and traded populations are exactly the 5,691 baseline trades. Earlier BE exits that
would free the position slot for baseline-skipped signals are deliberately NOT modelled.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.dynamic_stop import compute_metrics_for_trades
from backtest.execution import simulate_trade_execution
from backtest.exit_decomposition import HOLD_BINS, _bin, _label, baseline_config_is_plain, load_symbol_bars
from backtest.failure_analysis import get_time_of_day_bucket, map_exit_reason
from backtest.frequency_cap import trade_fingerprint
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.time_window import TOD_BINS, load_regression_anchors
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.provider import DataProvider
from data.session import to_eastern
from strategy.day.types import DaySetup, DaySetupStatus

ROOT_DIR = Path(__file__).resolve().parent.parent
DAY10_RESULTS = ROOT_DIR / "artifacts" / "day10" / "frequency-cap-results.json"

DAY12B_BE_TRIGGER_R = 0.5          # the ONLY threshold; no sweep
VARIANTS = ("BASELINE", "BE_0.5R")
EXIT_KEYS = ("STOP", "BREAKEVEN", "TARGET", "FORCED_EXIT")

# Written BEFORE DAY-12B results were computed. Qualitative; introduces no new numeric acceptance threshold.
H12B_STATUS_CRITERION = (
    "Analyst criterion defined before DAY-12B results were viewed (not protocol-predeclared). "
    "Evaluated in three separate parts: (1) mechanism — does BE materially change the exit distribution "
    "(BE exits occur, baseline STOP exits convert to BE); (2) gross 0 bps effect — total R, profit factor and "
    "max drawdown vs BASELINE; (3) transaction-cost robustness — 5 and 10 bps compounded returns. "
    "MECHANISM SUPPORTED: total R AND profit factor improve at 0 bps, the 5 bps compounded return is "
    "non-negative, AND per-symbol R delta is positive in a majority of symbols. "
    "MECHANISM NOT SUPPORTED: total R or profit factor does not improve at 0 bps. "
    "MECHANISM INCONCLUSIVE: anything else (e.g. gross improvement that does not survive costs). "
    "If 5/10 bps returns remain strongly negative the report states that transaction costs remain unresolved. "
    "No classification implies a validated trading edge or production readiness."
)


def be_config() -> ExecutionConfig:
    """Plain baseline config with ONLY the stop-management change (opt-in)."""
    return ExecutionConfig(breakeven_trigger_r=DAY12B_BE_TRIGGER_R)


def _setup_from_trade(t: DayBacktestTrade) -> DaySetup:
    # Same reconstruction as DAY-07 (backtest/dynamic_stop.py): the execution simulator only reads
    # symbol / vwap (stop fallback) and copies the remaining context fields into the trade record.
    return DaySetup(
        symbol=t.symbol, timestamp=t.setup_time, status=DaySetupStatus.CONFIRMED,
        price=t.observed_price_at_setup, vwap=t.vwap_at_setup, rsi=t.rsi_at_setup, rvol=t.rvol_at_setup,
        structure_5m=t.structure_5m, structure_15m=t.structure_15m, evidence=t.evidence,
        warnings=t.warnings, trigger=t.trigger_type,
    )


def resimulate_paired(
    trades: Sequence[DayBacktestTrade], bars_by_symbol: dict[str, pd.DataFrame], config: ExecutionConfig
) -> tuple[list[DayBacktestTrade], list[bool], list[str]]:
    """Re-simulate each trade from its own signal bar with ``config``. No silent fallback."""
    out: list[DayBacktestTrade] = []
    ambiguous: list[bool] = []
    failures: list[str] = []
    for i, t in enumerate(trades):
        df = bars_by_symbol[t.symbol]
        try:
            loc = df.index.get_loc(t.setup_time)
        except KeyError:
            failures.append(f"#{i} {t.symbol} {t.setup_time}: signal bar missing")
            continue
        if not isinstance(loc, (int, np.integer)):
            failures.append(f"#{i} {t.symbol} {t.setup_time}: signal bar not unique")
            continue
        sim = simulate_trade_execution(df, setup_bar_idx=int(loc), setup=_setup_from_trade(t), config=config)
        if sim is None:
            failures.append(f"#{i} {t.symbol} {t.setup_time}: simulation returned None")
            continue
        out.append(sim.trade)
        ambiguous.append(bool(sim.was_ambiguous))
    return out, ambiguous, failures


# =====================================================================
# Diagnostics helpers (descriptive only)
# =====================================================================

def _pf(trades) -> float | None:
    gw = sum(t.gross_return for t in trades if t.gross_return > 0)
    gl = sum(-t.gross_return for t in trades if t.gross_return < 0)
    return round(gw / gl, 4) if gl > 0 else None


def _r(t: DayBacktestTrade) -> float:
    return float(t.r_multiple) if t.r_multiple is not None else 0.0


def _pair_stats(pairs: Sequence[tuple[DayBacktestTrade, DayBacktestTrade]]) -> dict[str, Any]:
    n = len(pairs)
    if n == 0:
        return {"count": 0}
    b = [p[0] for p in pairs]
    v = [p[1] for p in pairs]
    rb, rv = sum(_r(t) for t in b), sum(_r(t) for t in v)
    return {
        "count": n,
        "baseline_total_R": round(rb, 2),
        "be_total_R": round(rv, 2),
        "delta_R": round(rv - rb, 2),
        "baseline_avg_R": round(rb / n, 4),
        "be_avg_R": round(rv / n, 4),
        "baseline_win_rate": round(sum(1 for t in b if t.gross_return > 0) / n, 4),
        "be_win_rate": round(sum(1 for t in v if t.gross_return > 0) / n, 4),
        "baseline_pf": _pf(b),
        "be_pf": _pf(v),
        "be_activated": sum(1 for t in v if t.be_triggered),
        "be_exits": sum(1 for t in v if map_exit_reason(t.exit_reason) == "BREAKEVEN"),
    }


def _transition_matrix(pairs) -> dict[str, dict[str, int]]:
    m: dict[str, dict[str, int]] = {a: {b: 0 for b in EXIT_KEYS} for a in EXIT_KEYS}
    for b, v in pairs:
        m[map_exit_reason(b.exit_reason)][map_exit_reason(v.exit_reason)] += 1
    return m


def _symbol_concentration(pairs) -> dict[str, Any]:
    by: dict[str, list] = defaultdict(list)
    for p in pairs:
        by[p[0].symbol].append(p)
    per = {s: _pair_stats(ps) for s, ps in sorted(by.items())}
    deltas = {s: d["delta_R"] for s, d in per.items()}
    total_abs = sum(abs(x) for x in deltas.values())
    top2 = sorted(deltas, key=lambda s: abs(deltas[s]), reverse=True)[:2]
    pos_sum = sum(x for x in deltas.values() if x > 0)
    top2_pos = sorted((x for x in deltas.values() if x > 0), reverse=True)[:2]
    return {
        "per_symbol": per,
        "symbols_total": len(per),
        "symbols_delta_positive": sum(1 for x in deltas.values() if x > 0),
        "symbols_delta_negative": sum(1 for x in deltas.values() if x < 0),
        "symbols_delta_zero": sum(1 for x in deltas.values() if x == 0),
        "median_symbol_delta_R": round(float(np.median(list(deltas.values()))), 2) if deltas else None,
        "min_symbol_delta_R": min(deltas.values()) if deltas else None,
        "max_symbol_delta_R": max(deltas.values()) if deltas else None,
        "top2_abs_delta_share_pct": round(100 * sum(abs(deltas[s]) for s in top2) / total_abs, 2) if total_abs else None,
        "top2_positive_delta_share_of_positive_pct": round(100 * sum(top2_pos) / pos_sum, 2) if pos_sum else None,
    }


# =====================================================================
# Experiment runner
# =====================================================================

def run_day12b_experiment(
    symbols: Sequence[str] | None = None,
    provider: DataProvider | None = None,
    anchors_path: Path = DAY10_RESULTS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prov = provider or get_provider()
    symbols_list = list(symbols) if symbols is not None else get_day_universe()

    base = run_multi_symbol_day_backtest(symbols=symbols_list, provider=prov)
    tested = list(base.tested_symbols)
    base_trades = [t for s in tested for t in base.symbol_results[s].trades]
    bnh = {m.symbol: m.buy_hold_return for m in base.per_symbol_metrics}
    bars = {s: load_symbol_bars(prov, s) for s in tested}
    cfg = be_config()

    # ---- regression ----
    anchors = load_regression_anchors(anchors_path)
    bm = asdict(compute_metrics_for_trades(base_trades, "BASELINE", bnh))
    replay, _, replay_fail = resimulate_paired(base_trades, bars, base.execution_config)
    regression = {
        "anchors_source": str(anchors_path.relative_to(ROOT_DIR)),
        "anchors": anchors,
        "baseline_matches_anchors": {k: bm[k] == anchors[k] for k in anchors},
        "plain_baseline_config": baseline_config_is_plain(base.execution_config),
        "paired_replay_with_baseline_config_identical": not replay_fail
        and [trade_fingerprint(t) for t in replay] == [trade_fingerprint(t) for t in base_trades],
    }
    regression["regression_verified"] = (
        all(regression["baseline_matches_anchors"].values())
        and all(regression["plain_baseline_config"].values())
        and regression["paired_replay_with_baseline_config_identical"]
    )

    # ---- counterfactual (paired) ----
    be_trades, be_amb, failures = resimulate_paired(base_trades, bars, cfg)
    complete = not failures and len(be_trades) == len(base_trades)
    pairs = list(zip(base_trades, be_trades)) if complete else []
    same_population = complete and all(
        b.symbol == v.symbol and b.setup_time == v.setup_time and b.entry_time == v.entry_time
        and b.entry_price == v.entry_price and b.risk_per_share == v.risk_per_share
        and b.stop_price == v.stop_price and b.target_price == v.target_price
        for b, v in pairs
    )
    vm = asdict(compute_metrics_for_trades(be_trades, "BE_0.5R", bnh))
    base_amb = sum(base.symbol_results[s].same_bar_ambiguity_count for s in tested)

    metrics = {"BASELINE": bm, "BE_0.5R": vm}
    extra = {
        "BASELINE": {"same_bar_ambiguity": base_amb, "median_R": bm["median_R"]},
        "BE_0.5R": {"same_bar_ambiguity": sum(be_amb), "median_R": vm["median_R"]},
    }

    # ---- accounting ----
    n = len(pairs)
    deltas = [_r(v) - _r(b) for b, v in pairs]
    activated = [v for _, v in pairs if v.be_triggered]
    base_losers = [(b, v) for b, v in pairs if b.gross_return < 0]
    gap_be = 0
    gap_be_open_r = 0.0   # descriptive size of the fill-convention limitation (NOT applied to results)
    for _, v in pairs:
        if map_exit_reason(v.exit_reason) == "BREAKEVEN":
            o = float(bars[v.symbol]["open"].loc[v.exit_time])
            if o < v.entry_price:
                gap_be += 1
                gap_be_open_r += (o - v.entry_price) / v.risk_per_share
    changed = [(b, v) for b, v in pairs if trade_fingerprint(b) != trade_fingerprint(v)]
    trans = _transition_matrix(pairs)
    accounting = {
        "baseline_trades": len(base_trades),
        "be_trades": len(be_trades),
        "resimulation_failures": failures,
        "same_population": same_population,
        "be_activated_trades": len(activated),
        "be_activated_pct_of_all": round(100 * len(activated) / n, 2) if n else None,
        "baseline_losers": len(base_losers),
        "baseline_losers_with_be_activated": sum(1 for _, v in base_losers if v.be_triggered),
        "baseline_losers_outcome_changed": sum(1 for b, v in base_losers if _r(v) != _r(b)),
        "baseline_losers_affected_pct": round(100 * sum(1 for b, v in base_losers if _r(v) != _r(b)) / len(base_losers), 2)
        if base_losers else None,
        "baseline_stop_to_be": trans["STOP"]["BREAKEVEN"],
        "baseline_target_changed": sum(trans["TARGET"][k] for k in EXIT_KEYS if k != "TARGET"),
        "baseline_target_to_be": trans["TARGET"]["BREAKEVEN"],
        "baseline_forced_to_be": trans["FORCED_EXIT"]["BREAKEVEN"],
        "exit_transition_matrix_baseline_to_be": trans,
        "trades_changed": len(changed),
        "trades_unchanged": n - len(changed),
        "be_activated_but_unchanged_outcome": sum(1 for b, v in pairs if v.be_triggered and _r(v) == _r(b)),
        "sum_delta_R": round(sum(deltas), 4),
        "total_R_difference": round(sum(_r(v) for v in be_trades) - sum(_r(b) for b in base_trades), 4),
        "delta_R_positive_trades": sum(1 for d in deltas if d > 1e-12),
        "delta_R_negative_trades": sum(1 for d in deltas if d < -1e-12),
        "sum_positive_delta_R": round(sum(d for d in deltas if d > 0), 2),
        "sum_negative_delta_R": round(sum(d for d in deltas if d < 0), 2),
        "be_exit_gap_through_open_below_entry": gap_be,
        "be_exit_gap_through_sum_R_if_filled_at_open": round(gap_be_open_r, 2),
        "be_exit_r_all_zero": all(abs(_r(v)) < 1e-12 for _, v in pairs if map_exit_reason(v.exit_reason) == "BREAKEVEN"),
    }
    accounting["reconciles"] = math.isclose(accounting["sum_delta_R"], accounting["total_R_difference"], abs_tol=1e-6)

    # ---- diagnostics (grouped by BASELINE attributes; descriptive only) ----
    def grouped(keyfn, labels):
        g: dict[str, list] = {lab: [] for lab in labels}
        for p in pairs:
            g.setdefault(keyfn(p), []).append(p)
        return {k: _pair_stats(v) for k, v in g.items()}

    trig_bars = Counter()
    for v in activated:
        k = int((v.be_trigger_time - v.entry_time).total_seconds() // 300)
        trig_bars["5+" if k >= 5 else str(k)] += 1
    diagnostics = {
        "by_baseline_exit_reason": grouped(lambda p: map_exit_reason(p[0].exit_reason), ("STOP", "TARGET", "FORCED_EXIT")),
        "by_baseline_holding_bucket": grouped(lambda p: _bin(p[0].hold_duration_minutes, HOLD_BINS),
                                              [_label(*b) for b in HOLD_BINS]),
        "by_entry_time_of_day": grouped(lambda p: get_time_of_day_bucket(to_eastern(p[0].entry_time).time()), TOD_BINS),
        "be_trigger_bar_after_entry_distribution": {k: trig_bars.get(k, 0) for k in ("0", "1", "2", "3", "4", "5+")},
        "symbol_concentration": _symbol_concentration(pairs),
    }

    # ---- classification (pre-declared qualitative rule) ----
    gross = {
        "total_R_improved": vm["total_R"] > bm["total_R"],
        "profit_factor_improved": vm["profit_factor"] > bm["profit_factor"],
        "max_drawdown_improved": vm["max_drawdown_pct"] > bm["max_drawdown_pct"],
        "compounded_0bps_improved": vm["slippage_0bps"] > bm["slippage_0bps"],
    }
    costs = {
        "baseline": {k: bm[k] for k in ("slippage_0bps", "slippage_5bps", "slippage_10bps")},
        "be": {k: vm[k] for k in ("slippage_0bps", "slippage_5bps", "slippage_10bps")},
        "five_bps_non_negative": vm["slippage_5bps"] >= 0.0,
        "ten_bps_non_negative": vm["slippage_10bps"] >= 0.0,
    }
    mechanism_effect = {
        "be_exits": vm["exit_counts"].get("BREAKEVEN", 0),
        "stop_exits_baseline": bm["exit_counts"].get("STOP", 0),
        "stop_exits_be": vm["exit_counts"].get("STOP", 0),
        "target_exits_baseline": bm["exit_counts"].get("TARGET", 0),
        "target_exits_be": vm["exit_counts"].get("TARGET", 0),
        "exit_distribution_changed": vm["exit_counts"] != bm["exit_counts"],
    }
    sc = diagnostics["symbol_concentration"]
    majority_symbols = sc["symbols_delta_positive"] > sc["symbols_total"] / 2
    integrity_ok = regression["regression_verified"] and complete and same_population and accounting["reconciles"]
    if not integrity_ok:
        status = "NOT EVALUATED (regression/integrity failure)"
    elif not (gross["total_R_improved"] and gross["profit_factor_improved"]):
        status = "MECHANISM NOT SUPPORTED"
    elif costs["five_bps_non_negative"] and majority_symbols:
        status = "MECHANISM SUPPORTED"
    else:
        status = "MECHANISM INCONCLUSIVE"
    cost_unresolved = not (costs["five_bps_non_negative"] and costs["ten_bps_non_negative"])

    rows = []
    for i, ((b, v), amb) in enumerate(zip(pairs, be_amb)):
        rows.append({
            "trade_id": i, "symbol": b.symbol, "session": str(to_eastern(b.entry_time).date()),
            "signal_time": b.setup_time, "entry_time": b.entry_time, "entry_price": b.entry_price,
            "original_stop": b.stop_price, "risk_R_unit": b.risk_per_share, "target_price": b.target_price,
            "be_trigger_price": b.entry_price + DAY12B_BE_TRIGGER_R * b.risk_per_share,
            "baseline_exit_time": b.exit_time, "baseline_exit_price": b.exit_price,
            "baseline_exit_reason": map_exit_reason(b.exit_reason), "baseline_R": _r(b),
            "baseline_hold_minutes": b.hold_duration_minutes,
            "be_exit_time": v.exit_time, "be_exit_price": v.exit_price, "be_exit_reason": map_exit_reason(v.exit_reason),
            "be_R": _r(v), "be_hold_minutes": v.hold_duration_minutes,
            "be_triggered": v.be_triggered, "be_trigger_time": v.be_trigger_time,
            "be_stop_price": v.effective_exit_stop_price, "be_same_bar_ambiguous": amb,
            "delta_R": _r(v) - _r(b), "changed": trade_fingerprint(b) != trade_fingerprint(v),
        })

    res = {
        "metadata": {
            "experiment": "DAY-12B +0.5R -> Breakeven (single counterfactual exit-management hypothesis)",
            "hypothesis": "Move the stop to breakeven after the trade has reached +0.5R.",
            "provenance": "New hypothesis, NOT pre-declared. 0.5R was chosen after viewing DAY-12A and after DAY-07 "
            "(1.0R) and DAY-07A (0.75/1.00/1.25R) were evaluated on the same frozen data: effectively a 4th threshold "
            "of the H2 BE family, in-sample, subject to data-snooping / multiple-testing bias.",
            "be_trigger_r": DAY12B_BE_TRIGGER_R,
            "semantics": {
                "risk_unit": "R = entry - original SIGNAL_LOW stop; never recalculated after the stop moves",
                "trigger": "entry + 0.5R, recognised only from a CLOSED 5m bar that produced no exit (High >= trigger)",
                "activation": "BE stop active from the NEXT bar; never applied retroactively to the trigger bar",
                "be_stop": "exactly entry_price (R = 0 on a BE exit)",
                "pre_confirmation_stop": "original stop hit before a closed bar confirms +0.5R -> normal STOP",
                "target": "entry + 2R (original R); target touched on the trigger bar executes normally",
                "same_bar": "later bar touching both BE stop and target -> existing STOP_FIRST -> BREAKEVEN (ambiguous)",
                "gap_fill": "bar opening below entry after BE activation fills at entry (existing engine stop-fill "
                "convention, no gap slippage) — counted as a limitation",
                "forced_exit": "15:55 ET bar close, unchanged (no stop/target/BE checks on that bar)",
                "implementation": "existing opt-in ExecutionConfig.breakeven_trigger_r path in backtest/execution.py "
                "(DAY-07); no engine/strategy/signal code changed",
            },
            "population": "PAIRED 1:1: each baseline trade re-simulated from its own signal bar. Candidate and traded "
            "populations identical to the baseline. Position slots freed by earlier BE exits are NOT re-used "
            "(baseline-skipped signals stay skipped) — documented limitation.",
            "costs": "0 bps simulated; 5/10 bps applied post-hoc with the existing DAY-07 compounded model "
            "(compute_metrics_for_trades)",
            "status_criterion": H12B_STATUS_CRITERION,
        },
        "frozen_dataset": {
            "universe_size": len(tested), "universe_symbols": tested,
            "period_start": str(base.study_window_start), "period_end": str(base.study_window_end),
            "rth_sessions": base.total_sessions,
            "candidate_signals": sum(base.symbol_results[s].candidate_signals for s in tested),
            "baseline_trades": len(base_trades),
        },
        "baseline_regression": regression,
        "metrics": metrics,
        "extra_metrics": extra,
        "accounting": accounting,
        "diagnostics": diagnostics,
        "evaluation": {
            "mechanism_effect": mechanism_effect,
            "gross_effect_0bps": gross,
            "transaction_costs": costs,
            "majority_symbols_delta_positive": majority_symbols,
            "transaction_costs_unresolved": cost_unresolved,
            "status": status,
        },
    }
    return res, rows


# =====================================================================
# Report (neutral; no adoption recommendation)
# =====================================================================

def _f(x, nd=4):
    if x is None:
        return "-"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def format_day12b_report(res: dict[str, Any]) -> str:
    L: list[str] = []
    p = L.append
    md, ds, reg, M, X, A, D, E = (res["metadata"], res["frozen_dataset"], res["baseline_regression"], res["metrics"],
                                  res["extra_metrics"], res["accounting"], res["diagnostics"], res["evaluation"])
    bar, sub = "=" * 110, "-" * 110

    p(bar)
    p("DAY-12B — +0.5R -> BREAKEVEN — SINGLE COUNTERFACTUAL EXIT-MANAGEMENT EXPERIMENT")
    p(bar)
    p("")
    p("1. HYPOTHESIS & PROVENANCE")
    p(sub)
    p(f"  {md['hypothesis']}")
    p(f"  {md['provenance']}")
    p("")
    p("2. FROZEN BASELINE")
    p(sub)
    p(f"  Universe : {ds['universe_size']} symbols ({', '.join(ds['universe_symbols'])})")
    p(f"  Period   : {ds['period_start']} -> {ds['period_end']} ({ds['rth_sessions']} RTH sessions)")
    p(f"  Candidate signals: {ds['candidate_signals']}   Baseline trades: {ds['baseline_trades']}")
    p(f"  Regression vs {reg['anchors_source']}:")
    for k, v in reg["anchors"].items():
        p(f"    {k:<18}: anchor={v}  {'OK' if reg['baseline_matches_anchors'][k] else 'MISMATCH'}")
    p(f"  Plain-baseline config: {reg['plain_baseline_config']}")
    p(f"  Paired replay with baseline config reproduces every baseline trade: {reg['paired_replay_with_baseline_config_identical']}")
    p(f"  Regression verified: {reg['regression_verified']}")
    p("")
    p("3. METHODOLOGY & INTRABAR SEMANTICS")
    p(sub)
    for k, v in md["semantics"].items():
        p(f"  {k:<22}: {v}")
    p(f"  population            : {md['population']}")
    p(f"  costs                 : {md['costs']}")
    p("")
    p("4. RESULTS (0 bps unless stated)")
    p(sub)
    rows = [
        ("Trades", lambda v: M[v]["total_trades"]),
        ("Wins / Losses / BE", lambda v: f"{M[v]['wins']}/{M[v]['losses']}/{M[v]['breakevens']}"),
        ("Win rate", lambda v: f"{M[v]['win_rate'] * 100:.2f}%"),
        ("Profit factor", lambda v: f"{M[v]['profit_factor']:.4f}"),
        ("Expectancy (avg trade return)", lambda v: f"{M[v]['expectancy']:.4f}"),
        ("Total R", lambda v: f"{M[v]['total_R']:.2f}"),
        ("Average R", lambda v: f"{M[v]['avg_R']:.4f}"),
        ("Median R", lambda v: f"{M[v]['median_R']:.4f}"),
        ("Max drawdown (compounded)", lambda v: f"{M[v]['max_drawdown_pct']:.2f}%"),
        ("Geometric (compounded) return", lambda v: f"{M[v]['gross_return_compounded']:.2f}%"),
        ("Return 0 bps", lambda v: f"{M[v]['slippage_0bps']:.2f}%"),
        ("Return 5 bps", lambda v: f"{M[v]['slippage_5bps']:.2f}%"),
        ("Return 10 bps", lambda v: f"{M[v]['slippage_10bps']:.2f}%"),
        ("Exit STOP", lambda v: M[v]["exit_counts"].get("STOP", 0)),
        ("Exit BREAKEVEN", lambda v: M[v]["exit_counts"].get("BREAKEVEN", 0)),
        ("Exit TARGET", lambda v: M[v]["exit_counts"].get("TARGET", 0)),
        ("Exit FORCED_EXIT", lambda v: M[v]["exit_counts"].get("FORCED_EXIT", 0)),
        ("Same-bar ambiguity", lambda v: X[v]["same_bar_ambiguity"]),
        ("Avg hold (min)", lambda v: M[v]["avg_hold_duration_mins"]),
    ]
    p(f"  {'':<32}" + "".join(f"{v:>16}" for v in VARIANTS))
    for label, fn in rows:
        p(f"  {label:<32}" + "".join(f"{fn(v):>16}" for v in VARIANTS))
    p("")
    p("5. TRADE-BY-TRADE ACCOUNTING")
    p(sub)
    for k, v in A.items():
        if k != "exit_transition_matrix_baseline_to_be":
            p(f"  {k}: {v}")
    p("  Exit transition matrix (rows = BASELINE exit, cols = BE_0.5R exit):")
    tm = A["exit_transition_matrix_baseline_to_be"]
    p(f"    {'':<14}" + "".join(f"{k:>13}" for k in EXIT_KEYS))
    for a in EXIT_KEYS:
        p(f"    {a:<14}" + "".join(f"{tm[a][b]:>13}" for b in EXIT_KEYS))
    p("")

    def pair_table(title, groups):
        p(title)
        p(sub)
        p(f"  {'Group':<16}{'N':>6}{'base R':>10}{'BE R':>10}{'dR':>9}{'base WR':>9}{'BE WR':>8}{'base PF':>9}{'BE PF':>8}"
          f"{'BE act':>8}{'BE exits':>9}")
        for g, d in groups.items():
            if not d.get("count"):
                p(f"  {g:<16}{0:>6}")
                continue
            p(f"  {g:<16}{d['count']:>6}{d['baseline_total_R']:>10.2f}{d['be_total_R']:>10.2f}{d['delta_R']:>9.2f}"
              f"{d['baseline_win_rate'] * 100:>8.2f}%{d['be_win_rate'] * 100:>7.2f}%{_f(d['baseline_pf']):>9}{_f(d['be_pf']):>8}"
              f"{d['be_activated']:>8}{d['be_exits']:>9}")
        p("")

    pair_table("6. BY BASELINE EXIT REASON", D["by_baseline_exit_reason"])
    pair_table("7. BY BASELINE HOLDING-TIME BUCKET", D["by_baseline_holding_bucket"])
    pair_table("8. BY ENTRY TIME OF DAY (DAY-05 bins; explanatory only)", D["by_entry_time_of_day"])
    p("9. BE ACTIVATION TIMING (trigger bar index after entry; 0 = entry bar)")
    p(sub)
    p(f"  {D['be_trigger_bar_after_entry_distribution']}")
    p("")
    sc = D["symbol_concentration"]
    pair_table("10. BY SYMBOL (alphabetical; NOT a ranking or selection)", sc["per_symbol"])
    p(f"  Symbols with positive / negative / zero delta R: {sc['symbols_delta_positive']} / {sc['symbols_delta_negative']} / "
      f"{sc['symbols_delta_zero']} of {sc['symbols_total']}")
    p(f"  Median / min / max symbol delta R: {sc['median_symbol_delta_R']} / {sc['min_symbol_delta_R']} / {sc['max_symbol_delta_R']}")
    p(f"  Top-2 symbols' share of total |delta R|: {sc['top2_abs_delta_share_pct']}%; top-2 share of positive delta R: "
      f"{sc['top2_positive_delta_share_of_positive_pct']}%")
    p("")
    p("11. TRANSACTION-COST SENSITIVITY (compounded, 1 unit/trade)")
    p(sub)
    c = E["transaction_costs"]
    for lvl in ("slippage_0bps", "slippage_5bps", "slippage_10bps"):
        p(f"  {lvl:<16}: BASELINE {c['baseline'][lvl]:>9.2f}%   BE_0.5R {c['be'][lvl]:>9.2f}%")
    p("")
    if "validation" in res:
        p("12. TESTS, PIT & HASH VERIFICATION")
        p(sub)
        for k, v in res["validation"].items():
            p(f"  {k}: {v}")
        p("")
    p("13. CLASSIFICATION")
    p(sub)
    p(f"  (1) Mechanism effect : {E['mechanism_effect']}")
    p(f"  (2) Gross 0 bps      : {E['gross_effect_0bps']}")
    p(f"  (3) Costs            : 5 bps non-negative={c['five_bps_non_negative']}, 10 bps non-negative={c['ten_bps_non_negative']}")
    p(f"  Majority of symbols with positive delta R: {E['majority_symbols_delta_positive']}")
    p(f"  Criterion: {md['status_criterion']}")
    p(f"  DAY-12B STATUS: {E['status']}")
    if E["transaction_costs_unresolved"]:
        p("  TRANSACTION COSTS REMAIN UNRESOLVED: the 5 / 10 bps compounded returns are negative for BE_0.5R.")
    p("  This is an in-sample counterfactual on the frozen dataset (threshold chosen after viewing DAY-12A).")
    p("  It is NOT a validated trading edge and is NOT a recommendation for production adoption.")
    p(bar)
    return "\n".join(L) + "\n"
