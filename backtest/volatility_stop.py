"""backtest/volatility_stop.py: DAY-09 — H4 Volatility-Scaled (ATR) Stop Distance Research Engine.

Hypothesis H4:
    SIGNAL_LOW asosidagi tor stoplar intraday shovqin sabab tez-tez urilishi mumkin.
    5m ATR asosidagi volatility-scaled stop geometriyasi natijalarni qanday o'zgartiradi?

Principles:
    1. Signals, entry timing (T+1 5m OPEN), 2R target rule, STOP_FIRST, 15:55 ET forced exit,
       long-only and the cost model are 100% frozen from DAY-01/DAY-02.
    2. Only the initial stop distance changes:
           risk_distance = ATR_5m(signal_time) * multiplier
           stop_price    = entry_price - risk_distance
           target_price  = entry_price + 2 * risk_distance
    3. ATR(14) = indicators.atr.compute_atr (simple rolling mean of True Range) computed only
       from 5m bars with bar_end <= signal_time = setup_time + 5m (signal bar inclusive).
       The entry bar (forming at signal_time) and every later bar are excluded.
    4. Multipliers are pre-declared (H4_MULTIPLIERS). NO optimization, NO parameter search.
    5. Trades without a valid ATR are never silently replaced by the baseline trade: they are
       excluded from every H4 variant and reported with a reason code.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from backtest.day_types import DayBacktestTrade, DaySetupStatus, ExecutionConfig
from backtest.dynamic_stop import DynamicStopMetrics, compute_metrics_for_trades
from backtest.execution import simulate_trade_execution
from backtest.failure_analysis import map_exit_reason
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.multi_types import MultiSymbolDayBacktestResult
from config.day_universe import get_day_universe
from config.settings import ATR_PERIOD
from data.factory import get_provider
from data.provider import DataProvider
from data.session import get_session_date
from indicators.atr import compute_atr
from strategy.day.types import DaySetup

logger = logging.getLogger(__name__)

# Pre-declared H4 variants (frozen before seeing results)
H4_MULTIPLIERS: tuple[float, ...] = (0.50, 0.75, 1.00, 1.25)
TARGET_MULTIPLE: float = 2.0

# Frozen DAY-02/DAY-04 baseline regression invariants
BASELINE_EXPECTED = {
    "total_trades": 5691,
    "win_rate": 0.3042,
    "profit_factor": 0.9388,
    "total_R": -738.98,
    "gross_return_compounded": -41.19,
}

REASON_SETUP_BAR_NOT_FOUND = "SETUP_BAR_NOT_FOUND"
REASON_ATR_WARMUP_NAN = "ATR_WARMUP_NAN"
REASON_ATR_NON_POSITIVE = "ATR_NON_POSITIVE"
REASON_SIMULATION_NONE = "SIMULATION_NONE"

_EXIT_KEYS = ("STOP", "TARGET", "FORCED_EXIT", "BREAKEVEN")


def variant_name(multiplier: float) -> str:
    return f"H4 ATRx{multiplier:.2f}"


# =====================================================================
# 1. Point-in-time ATR and setup reconstruction
# =====================================================================

def atr_at_signal(df_5m: pd.DataFrame, setup_bar_idx: int, period: int = ATR_PERIOD) -> float:
    """5m ATR(period) observable at signal_time = close of the setup bar.

    Only bars [0 .. setup_bar_idx] are used, so the entry bar (forming at signal_time)
    and all future bars can never influence the value. Returns NaN during warm-up.
    """
    if setup_bar_idx < 0 or setup_bar_idx >= len(df_5m):
        raise IndexError(f"setup_bar_idx {setup_bar_idx} out of range for {len(df_5m)} bars")
    window = df_5m.iloc[: setup_bar_idx + 1]
    return float(compute_atr(window, period=period).iloc[-1])


def setup_from_trade(trade: DayBacktestTrade) -> DaySetup:
    """Rebuild the frozen DAY-01 setup from a baseline trade (same as DAY-07)."""
    return DaySetup(
        symbol=trade.symbol,
        timestamp=trade.setup_time,
        status=DaySetupStatus.CONFIRMED,
        price=trade.observed_price_at_setup,
        vwap=trade.vwap_at_setup,
        rsi=trade.rsi_at_setup,
        rvol=trade.rvol_at_setup,
        structure_5m=trade.structure_5m,
        structure_15m=trade.structure_15m,
        evidence=trade.evidence,
        warnings=trade.warnings,
        trigger=trade.trigger_type,
    )


def h4_execution_config(multiplier: float) -> ExecutionConfig:
    """Baseline execution config with only the stop geometry replaced."""
    return ExecutionConfig(
        slippage_bps=0.0,
        commission_per_share=0.0,
        target_multiple=TARGET_MULTIPLE,
        stop_mode="ATR",
        atr_stop_multiplier=multiplier,
    )


# =====================================================================
# 2. Result structures
# =====================================================================

@dataclass
class InsufficientTrade:
    symbol: str
    setup_time: str
    session: str
    reason: str


@dataclass
class VariantDiagnostics:
    """Risk geometry, exits and paired comparison for one variant."""

    variant_name: str
    population: int
    same_bar_ambiguity_count: int
    stop_distance_pct: dict[str, float]
    risk_atr_multiple: dict[str, float]
    r_multiple: dict[str, float]
    hold_minutes: dict[str, float]
    exit_counts: dict[str, int]
    entry_time_matches_baseline: int
    entry_price_matches_baseline: int
    transition_vs_baseline: dict[str, dict[str, int]] = field(default_factory=dict)
    r_delta_vs_baseline_total: float = 0.0
    r_delta_vs_baseline_mean: float = 0.0


@dataclass
class H4ExperimentResult:
    metadata: dict[str, Any]
    coverage: dict[str, Any]
    baseline_regression: dict[str, Any]
    metrics: dict[str, DynamicStopMetrics]
    diagnostics: dict[str, VariantDiagnostics]
    symbol_distribution: dict[str, dict[str, Any]]
    concentration: dict[str, dict[str, Any]]
    insufficient_trades: list[InsufficientTrade]
    pit_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "coverage": self.coverage,
            "baseline_regression": self.baseline_regression,
            "metrics": {k: asdict(v) for k, v in self.metrics.items()},
            "diagnostics": {k: asdict(v) for k, v in self.diagnostics.items()},
            "symbol_distribution": self.symbol_distribution,
            "concentration": self.concentration,
            "insufficient_trades": [asdict(t) for t in self.insufficient_trades],
            "pit_summary": self.pit_summary,
        }


# =====================================================================
# 3. Helpers
# =====================================================================

def _distribution(values: Sequence[float]) -> dict[str, float]:
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not vals:
        return {"n": 0}
    arr = np.asarray(vals)
    return {
        "n": int(arr.size),
        "mean": round(float(arr.mean()), 4),
        "p10": round(float(np.percentile(arr, 10)), 4),
        "p25": round(float(np.percentile(arr, 25)), 4),
        "median": round(float(np.median(arr)), 4),
        "p75": round(float(np.percentile(arr, 75)), 4),
        "p90": round(float(np.percentile(arr, 90)), 4),
    }


def _trade_key(t: DayBacktestTrade) -> tuple[str, pd.Timestamp]:
    return (t.symbol, t.setup_time)


def _exit_counts(trades: Sequence[DayBacktestTrade]) -> dict[str, int]:
    c = Counter(map_exit_reason(t.exit_reason) for t in trades)
    return {k: int(c.get(k, 0)) for k in _EXIT_KEYS}


def _profit_factor(trades: Sequence[DayBacktestTrade]) -> float:
    gw = sum(t.gross_return for t in trades if t.gross_return > 0)
    gl = sum(abs(t.gross_return) for t in trades if t.gross_return < 0)
    if gl > 0:
        return round(gw / gl, 4)
    return 999.0 if gw > 0 else 0.0


def _total_r(trades: Sequence[DayBacktestTrade]) -> float:
    return float(sum(t.r_multiple for t in trades if t.r_multiple is not None and not math.isnan(t.r_multiple)))


def _symbol_breakdown(trades: Sequence[DayBacktestTrade], symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
    by_sym: dict[str, list[DayBacktestTrade]] = defaultdict(list)
    for t in trades:
        by_sym[t.symbol].append(t)
    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        tr = sorted(by_sym.get(sym, []), key=lambda t: t.entry_time)
        c = 1.0
        for t in tr:
            c *= 1.0 + t.gross_return
        wins = sum(1 for t in tr if t.gross_return > 0)
        out[sym] = {
            "trades": len(tr),
            "win_rate": round(wins / len(tr), 4) if tr else 0.0,
            "total_R": round(_total_r(tr), 2),
            "profit_factor": _profit_factor(tr),
            "compounded_return_pct": round((c - 1.0) * 100.0, 2),
        }
    return out


def _concentration(trades: Sequence[DayBacktestTrade], sym_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """How much of the aggregate total R comes from the 1-2 largest |R| contributors."""
    total = _total_r(trades)
    ranked = sorted(sym_stats.items(), key=lambda kv: abs(kv[1]["total_R"]), reverse=True)
    top1 = ranked[:1]
    top2 = ranked[:2]
    top2_syms = {s for s, _ in top2}
    rest = [t for t in trades if t.symbol not in top2_syms]
    positive_syms = sum(1 for _, v in sym_stats.items() if v["total_R"] > 0)
    return {
        "aggregate_total_R": round(total, 2),
        "top1_symbol": top1[0][0] if top1 else None,
        "top1_total_R": top1[0][1]["total_R"] if top1 else 0.0,
        "top2_symbols": [s for s, _ in top2],
        "top2_total_R": round(sum(v["total_R"] for _, v in top2), 2),
        "excluding_top2_trades": len(rest),
        "excluding_top2_total_R": round(_total_r(rest), 2),
        "excluding_top2_profit_factor": _profit_factor(rest),
        "symbols_with_positive_total_R": positive_syms,
        "symbols_total": len(sym_stats),
    }


# =====================================================================
# 4. Experiment runner
# =====================================================================

def run_day09_volatility_stop_experiment(
    symbols: Sequence[str] | None = None,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    provider: DataProvider | None = None,
    multi_result: MultiSymbolDayBacktestResult | None = None,
    multipliers: Sequence[float] = H4_MULTIPLIERS,
) -> H4ExperimentResult:
    """Execute DAY-09 H4 ATR-stop experiment, paired 1:1 with the frozen baseline trades."""
    prov = provider or get_provider()
    symbols_list = list(symbols) if symbols is not None else get_day_universe()

    if multi_result is None:
        multi_result = run_multi_symbol_day_backtest(
            symbols=symbols_list,
            start_date=start_date,
            end_date=end_date,
            provider=prov,
        )

    bnh_by_symbol = {m.symbol: m.buy_hold_return for m in multi_result.per_symbol_metrics}
    tested = list(multi_result.tested_symbols)

    baseline_trades: list[DayBacktestTrade] = []
    evaluable_baseline: list[DayBacktestTrade] = []
    insufficient: list[InsufficientTrade] = []
    atr_by_key: dict[tuple[str, pd.Timestamp], float] = {}
    h4_trades: dict[float, list[DayBacktestTrade]] = {m: [] for m in multipliers}
    h4_ambiguous: dict[float, int] = {m: 0 for m in multipliers}
    reference_resim_matches = 0
    reference_resim_total = 0
    reference_config = ExecutionConfig(slippage_bps=0.0, commission_per_share=0.0, target_multiple=TARGET_MULTIPLE)

    for sym in tested:
        res = multi_result.symbol_results[sym]
        try:
            df_5m = prov.get_ohlcv(
                sym, "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True
            )
        except Exception:
            df_5m = pd.DataFrame()

        atr_full = compute_atr(df_5m, period=ATR_PERIOD) if not df_5m.empty else pd.Series(dtype=float)

        for b in res.trades:
            baseline_trades.append(b)
            session = str(get_session_date(b.setup_time))

            if df_5m.empty or b.setup_time not in df_5m.index:
                insufficient.append(InsufficientTrade(sym, str(b.setup_time), session, REASON_SETUP_BAR_NOT_FOUND))
                continue
            setup_idx = df_5m.index.get_loc(b.setup_time)
            if isinstance(setup_idx, slice):
                setup_idx = setup_idx.start
            setup_idx = int(setup_idx)

            # Causal rolling mean -> identical to atr_at_signal(df_5m, setup_idx); full-series
            # computation is only a speed-up (asserted equal in tests).
            atr = float(atr_full.iloc[setup_idx])
            if math.isnan(atr):
                insufficient.append(InsufficientTrade(sym, str(b.setup_time), session, REASON_ATR_WARMUP_NAN))
                continue
            if atr <= 0.0:
                insufficient.append(InsufficientTrade(sym, str(b.setup_time), session, REASON_ATR_NON_POSITIVE))
                continue

            setup = setup_from_trade(b)

            # Reference engine equivalence for the baseline geometry (diagnostic only)
            ref = simulate_trade_execution(df_5m, setup_bar_idx=setup_idx, setup=setup, config=reference_config)
            reference_resim_total += 1
            if ref is not None and ref.trade.exit_time == b.exit_time and ref.trade.exit_reason == b.exit_reason:
                reference_resim_matches += 1

            sims = {}
            for m in multipliers:
                sims[m] = simulate_trade_execution(
                    df_5m, setup_bar_idx=setup_idx, setup=setup, config=h4_execution_config(m), atr_value=atr
                )
            if any(s is None for s in sims.values()):
                insufficient.append(InsufficientTrade(sym, str(b.setup_time), session, REASON_SIMULATION_NONE))
                continue

            evaluable_baseline.append(b)
            atr_by_key[_trade_key(b)] = atr
            for m, s in sims.items():
                h4_trades[m].append(s.trade)
                if s.was_ambiguous:
                    h4_ambiguous[m] += 1

    # ---- population integrity (H4 must not change entries or the signal population) ----
    base_keys = [_trade_key(t) for t in evaluable_baseline]
    for m in multipliers:
        keys = [_trade_key(t) for t in h4_trades[m]]
        if keys != base_keys:
            raise AssertionError(f"{variant_name(m)}: signal population differs from baseline")

    # ---- metrics ----
    metrics: dict[str, DynamicStopMetrics] = {
        "BASELINE": compute_metrics_for_trades(baseline_trades, "BASELINE (SIGNAL_LOW, all trades)", bnh_by_symbol),
        "BASELINE_EVALUABLE": compute_metrics_for_trades(
            evaluable_baseline, "BASELINE (SIGNAL_LOW, H4-evaluable population)", bnh_by_symbol
        ),
    }
    for m in multipliers:
        metrics[variant_name(m)] = compute_metrics_for_trades(h4_trades[m], variant_name(m), bnh_by_symbol)

    # ---- diagnostics ----
    base_by_key = {_trade_key(t): t for t in evaluable_baseline}

    def _diag(name: str, trades: list[DayBacktestTrade], ambiguous: int, paired: bool) -> VariantDiagnostics:
        stop_pct = [t.risk_per_share / t.entry_price * 100.0 for t in trades if t.risk_per_share]
        risk_atr = [
            t.risk_per_share / atr_by_key[_trade_key(t)]
            for t in trades
            if t.risk_per_share and _trade_key(t) in atr_by_key
        ]
        r_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
        trans: dict[str, dict[str, int]] = {k: {j: 0 for j in _EXIT_KEYS} for k in _EXIT_KEYS}
        time_match = price_match = 0
        r_delta: list[float] = []
        if paired:
            for t in trades:
                b = base_by_key[_trade_key(t)]
                trans[map_exit_reason(b.exit_reason)][map_exit_reason(t.exit_reason)] += 1
                time_match += int(t.entry_time == b.entry_time)
                price_match += int(t.entry_price == b.entry_price)
                if t.r_multiple is not None and b.r_multiple is not None:
                    r_delta.append(t.r_multiple - b.r_multiple)
        return VariantDiagnostics(
            variant_name=name,
            population=len(trades),
            same_bar_ambiguity_count=ambiguous,
            stop_distance_pct=_distribution(stop_pct),
            risk_atr_multiple=_distribution(risk_atr),
            r_multiple=_distribution(r_vals),
            hold_minutes=_distribution([t.hold_duration_minutes for t in trades]),
            exit_counts=_exit_counts(trades),
            entry_time_matches_baseline=time_match if paired else len(trades),
            entry_price_matches_baseline=price_match if paired else len(trades),
            transition_vs_baseline=trans if paired else {},
            r_delta_vs_baseline_total=round(float(sum(r_delta)), 2) if paired else 0.0,
            r_delta_vs_baseline_mean=round(float(np.mean(r_delta)), 4) if (paired and r_delta) else 0.0,
        )

    base_ambiguous = sum(multi_result.symbol_results[s].same_bar_ambiguity_count for s in tested)
    diagnostics: dict[str, VariantDiagnostics] = {
        "BASELINE_EVALUABLE": _diag("BASELINE_EVALUABLE", evaluable_baseline, -1, paired=False),
    }
    for m in multipliers:
        diagnostics[variant_name(m)] = _diag(variant_name(m), h4_trades[m], h4_ambiguous[m], paired=True)

    # ---- symbol distribution & concentration ----
    symbol_distribution: dict[str, dict[str, Any]] = {}
    concentration: dict[str, dict[str, Any]] = {}
    for name, trades in [("BASELINE", baseline_trades), ("BASELINE_EVALUABLE", evaluable_baseline)] + [
        (variant_name(m), h4_trades[m]) for m in multipliers
    ]:
        sym_stats = _symbol_breakdown(trades, tested)
        symbol_distribution[name] = sym_stats
        concentration[name] = _concentration(trades, sym_stats)

    # ---- coverage ----
    reasons = Counter(t.reason for t in insufficient)
    by_session = Counter(t.session for t in insufficient)
    by_symbol = Counter(t.symbol for t in insufficient)
    coverage = {
        "baseline_trades": len(baseline_trades),
        "h4_evaluable_trades": len(evaluable_baseline),
        "h4_insufficient_trades": len(insufficient),
        "h4_coverage_pct": round(len(evaluable_baseline) / len(baseline_trades) * 100.0, 2) if baseline_trades else 0.0,
        "insufficient_by_reason": dict(sorted(reasons.items())),
        "insufficient_by_session": dict(sorted(by_session.items())),
        "insufficient_by_symbol": dict(sorted(by_symbol.items())),
        "baseline_same_bar_ambiguity_count": base_ambiguous,
        "reference_engine_resim_baseline_matches": reference_resim_matches,
        "reference_engine_resim_baseline_total": reference_resim_total,
    }

    # ---- baseline regression ----
    bm = metrics["BASELINE"]
    checks = {
        "total_trades": (bm.total_trades, BASELINE_EXPECTED["total_trades"], bm.total_trades == BASELINE_EXPECTED["total_trades"]),
        "win_rate": (bm.win_rate, BASELINE_EXPECTED["win_rate"], abs(bm.win_rate - BASELINE_EXPECTED["win_rate"]) <= 0.0001),
        "profit_factor": (bm.profit_factor, BASELINE_EXPECTED["profit_factor"], abs(bm.profit_factor - BASELINE_EXPECTED["profit_factor"]) <= 0.0005),
        "total_R": (bm.total_R, BASELINE_EXPECTED["total_R"], abs(bm.total_R - BASELINE_EXPECTED["total_R"]) <= 0.01),
        "gross_return_compounded": (
            bm.gross_return_compounded,
            BASELINE_EXPECTED["gross_return_compounded"],
            abs(bm.gross_return_compounded - BASELINE_EXPECTED["gross_return_compounded"]) <= 0.01,
        ),
    }
    regression_ok = all(v[2] for v in checks.values())
    baseline_regression = {
        "checks": {k: {"actual": v[0], "expected": v[1], "pass": v[2]} for k, v in checks.items()},
        "regression_verified": regression_ok,
        "h4_status": "EVALUATED" if regression_ok else "NOT VALIDATED",
    }

    metadata = {
        "experiment": "DAY-09 H4 Volatility-Scaled Stop Distance",
        "universe_size": len(tested),
        "universe_symbols": tested,
        "period_start": str(multi_result.study_window_start),
        "period_end": str(multi_result.study_window_end),
        "total_sessions": multi_result.total_sessions,
        "multipliers": list(multipliers),
        "atr": f"5m ATR({ATR_PERIOD}) = simple rolling mean of True Range (indicators/atr.py), continuous RTH series",
        "stop_formula": "risk = ATR_5m(signal_time) * multiplier; stop = entry - risk; target = entry + 2 * risk",
        "baseline_stop": "SIGNAL_LOW (DAY-02, unchanged)",
        "execution_rules": {
            "signal": "closed 5m bar T",
            "entry": "T + 1 5m OPEN",
            "target": "2.0R",
            "same_bar_ambiguity": "STOP_FIRST",
            "forced_exit": "15:55 ET",
            "direction": "long-only",
            "costs": "0 bps in simulation; 5/10 bps applied post-hoc to compounded return",
        },
        "population_rule": "H4 re-simulates every baseline trade 1:1 (same setup bar, same entry bar). "
        "Baseline open-position skip decisions are frozen and not re-evaluated under H4 exit times.",
        "denominators": {
            "win_rate": "trades in the variant population",
            "profit_factor": "sum of positive gross returns / |sum of negative gross returns| (trade level)",
            "total_R / avg_R / median_R": "trade-level R multiples of the variant's own initial risk",
            "compounded_return": "product of (1 + gross_return) over trades sorted by entry_time (1 unit, no sizing)",
        },
    }

    pit_summary = {
        "atr_bars_used": "bars [0 .. setup_bar] only (bar_end <= signal_time = setup_time + 5m)",
        "forming_entry_bar_excluded": True,
        "future_bars_excluded": True,
        "stop_and_target_fixed_at_entry": True,
        "intrabar_engine": "backtest.execution.simulate_trade_execution (same as DAY-07 reference engine)",
    }

    return H4ExperimentResult(
        metadata=metadata,
        coverage=coverage,
        baseline_regression=baseline_regression,
        metrics=metrics,
        diagnostics=diagnostics,
        symbol_distribution=symbol_distribution,
        concentration=concentration,
        insufficient_trades=insufficient,
        pit_summary=pit_summary,
    )


# =====================================================================
# 5. Report formatter (neutral; never ranks variants)
# =====================================================================

def format_volatility_stop_report(result: H4ExperimentResult) -> str:
    L: list[str] = []
    p = L.append
    md, cov, reg = result.metadata, result.coverage, result.baseline_regression
    names = list(result.metrics.keys())

    p("=" * 100)
    p("DAY-09 — H4 VOLATILITY-SCALED (ATR) STOP DISTANCE — RESEARCH EXPERIMENT REPORT")
    p("=" * 100)
    p("")
    p("1. HYPOTHESIS & DESIGN")
    p("-" * 100)
    p("H4: Tight SIGNAL_LOW stops may be hit by intraday noise. How does a 5m ATR-scaled stop geometry")
    p("change outcomes? Pre-declared multipliers only; no variant is selected or called 'best'.")
    p(f"  Stop formula   : {md['stop_formula']}")
    p(f"  ATR            : {md['atr']}")
    p(f"  Baseline stop  : {md['baseline_stop']}")
    p(f"  Multipliers    : {', '.join(f'{m:.2f}' for m in md['multipliers'])}")
    for k, v in md["execution_rules"].items():
        p(f"  {k:<15}: {v}")
    p(f"  Population     : {md['population_rule']}")
    p("")
    p("2. FROZEN DATA & COVERAGE")
    p("-" * 100)
    p(f"  Universe       : {md['universe_size']} symbols")
    p(f"  Study window   : {md['period_start']} -> {md['period_end']} ({md['total_sessions']} RTH sessions)")
    p(f"  Baseline trades            : {cov['baseline_trades']}")
    p(f"  H4-evaluable trades        : {cov['h4_evaluable_trades']} ({cov['h4_coverage_pct']:.2f}%)")
    p(f"  H4 insufficient (excluded) : {cov['h4_insufficient_trades']}")
    p(f"    by reason  : {cov['insufficient_by_reason']}")
    p(f"    by session : {cov['insufficient_by_session']}")
    p(f"    by symbol  : {cov['insufficient_by_symbol']}")
    p(f"  Reference-engine re-sim of baseline (SIGNAL_LOW) exit match: "
      f"{cov['reference_engine_resim_baseline_matches']}/{cov['reference_engine_resim_baseline_total']}")
    p("")
    p("3. BASELINE REGRESSION (DAY-02/DAY-04 frozen invariants)")
    p("-" * 100)
    for k, v in reg["checks"].items():
        p(f"  {k:<26}: actual={v['actual']}  expected={v['expected']}  {'OK' if v['pass'] else 'MISMATCH'}")
    p(f"  Regression verified : {reg['regression_verified']}   -> H4 status: {reg['h4_status']}")
    p("")
    p("4. AGGREGATE METRICS (0 bps gross; trade-level R and compounded return are reported separately)")
    p("-" * 100)
    hdr = f"{'Metric':<26}" + "".join(f"{n[:18]:>19}" for n in names)
    p(hdr)
    p("-" * len(hdr))

    def row(label: str, fn) -> None:
        p(f"{label:<26}" + "".join(f"{fn(result.metrics[n]):>19}" for n in names))

    row("Trades (denominator)", lambda m: m.total_trades)
    row("Wins / Losses / BE", lambda m: f"{m.wins}/{m.losses}/{m.breakevens}")
    row("Win rate", lambda m: f"{m.win_rate * 100:.2f}%")
    row("Profit factor", lambda m: f"{m.profit_factor:.4f}")
    row("Expectancy (%/trade)", lambda m: f"{m.expectancy:.4f}%")
    row("Total R", lambda m: f"{m.total_R:.2f}R")
    row("Average R", lambda m: f"{m.avg_R:.4f}R")
    row("Median R", lambda m: f"{m.median_R:.4f}R")
    row("Compounded return (0bps)", lambda m: f"{m.gross_return_compounded:.2f}%")
    row("Max drawdown (0bps)", lambda m: f"{m.max_drawdown_pct:.2f}%")
    row("Avg hold (min)", lambda m: f"{m.avg_hold_duration_mins:.1f}")
    for k in ("STOP", "TARGET", "FORCED_EXIT"):
        row(f"Exit: {k}", lambda m, k=k: m.exit_counts.get(k, 0))
    p("")
    p("5. FRICTION SENSITIVITY (compounded portfolio return, 1 unit per trade, by entry_time)")
    p("-" * 100)
    p(f"{'Variant':<50}{'0 bps':>14}{'5 bps':>14}{'10 bps':>14}")
    for n in names:
        m = result.metrics[n]
        p(f"{m.variant_name:<50}{m.slippage_0bps:>13.2f}%{m.slippage_5bps:>13.2f}%{m.slippage_10bps:>13.2f}%")
    p("")
    p("6. RISK GEOMETRY DISTRIBUTIONS (median [p10 .. p90])")
    p("-" * 100)
    p(f"{'Variant':<22}{'Stop dist %':>26}{'Risk / ATR':>26}{'Hold min':>24}{'Ambig':>8}")
    for n, d in result.diagnostics.items():
        def fmt(x):
            return f"{x.get('median', 'n/a')} [{x.get('p10', '')}..{x.get('p90', '')}]" if x.get("n") else "n/a"
        amb = d.same_bar_ambiguity_count if d.same_bar_ambiguity_count >= 0 else cov["baseline_same_bar_ambiguity_count"]
        p(f"{n[:21]:<22}{fmt(d.stop_distance_pct):>26}{fmt(d.risk_atr_multiple):>26}{fmt(d.hold_minutes):>24}{amb:>8}")
    p("  Note: BASELINE_EVALUABLE 'Risk / ATR' = SIGNAL_LOW risk expressed in ATR multiples (same ATR at signal).")
    p("  Note: BASELINE_EVALUABLE ambiguity = baseline engine count over all trades.")
    p("")
    p("7. PAIRED COMPARISON VS BASELINE (same setup, same entry bar)")
    p("-" * 100)
    for n, d in result.diagnostics.items():
        if not d.transition_vs_baseline:
            continue
        p(f"  {n}: entry_time match {d.entry_time_matches_baseline}/{d.population}, "
          f"entry_price match {d.entry_price_matches_baseline}/{d.population}, "
          f"total dR {d.r_delta_vs_baseline_total:+.2f}, mean dR {d.r_delta_vs_baseline_mean:+.4f}")
        p(f"    baseline exit -> H4 exit: " + "; ".join(
            f"{b}->" + ",".join(f"{h}:{c}" for h, c in row_.items() if c)
            for b, row_ in d.transition_vs_baseline.items() if any(row_.values())
        ))
    p("")
    p("8. SYMBOL CONCENTRATION (does 1-2 symbols drive the aggregate?)")
    p("-" * 100)
    p(f"{'Variant':<50}{'Total R':>10}{'Top-2 syms':>16}{'Top-2 R':>10}{'Ex-top2 R':>11}{'Ex-top2 PF':>11}{'Sym R>0':>9}")
    for n, c in result.concentration.items():
        p(f"{result.metrics[n].variant_name[:49]:<50}{c['aggregate_total_R']:>10.2f}{','.join(c['top2_symbols']):>16}"
          f"{c['top2_total_R']:>10.2f}{c['excluding_top2_total_R']:>11.2f}{c['excluding_top2_profit_factor']:>11.4f}"
          f"{c['symbols_with_positive_total_R']:>5}/{c['symbols_total']}")
    p("")
    p("9. PER-SYMBOL TOTAL R")
    p("-" * 100)
    p(f"{'Symbol':<8}" + "".join(f"{n[:18]:>19}" for n in names))
    for sym in md["universe_symbols"]:
        p(f"{sym:<8}" + "".join(f"{result.symbol_distribution[n][sym]['total_R']:>19.2f}" for n in names))
    p("")
    p("10. POINT-IN-TIME STATUS")
    p("-" * 100)
    for k, v in result.pit_summary.items():
        p(f"  {k:<32}: {v}")
    p("")
    p("11. DENOMINATORS")
    p("-" * 100)
    for k, v in md["denominators"].items():
        p(f"  {k:<28}: {v}")
    p("")
    p("12. INTERPRETATION RULES")
    p("-" * 100)
    p("  - H4 variants do NOT share the baseline risk geometry: 1R means a different dollar/percent risk per")
    p("    variant (see section 6). Compare R-multiples together with stop distance %, not in isolation.")
    p("  - Compounded return is 1 unit per trade with no position sizing; it is not a portfolio simulation.")
    p("  - No multiplier is declared best or production-ready. Results must be read with friction (sec. 5),")
    p("    symbol concentration (sec. 8), drawdown and sample size.")
    p("  - This experiment tests stop geometry only; it does not establish that the DAY-01 signal has an edge.")
    p("  - If H4 does not help, parameters are NOT searched further.")
    p("=" * 100)
    return "\n".join(L) + "\n"
