"""backtest/v11_rebaseline.py: DAY-15H — DAY-04 baseline re-run on the protocol v1.1 Alpaca SIP research data.

Orchestration only. The strategy, engine and execution model are the unchanged DAY-04 path:
backtest.day_engine.run_day_backtest(..., config=ExecutionConfig(), use_fast_engine=True).

v1.1 differences are confined to the data handed to the engine (protocol-v1.1.md §4, §21):
- the engine receives warmup + research bars (one continuous SIP series) so indicators have history;
- only trades whose signal bar lies in a research session are evaluated. Positions never cross sessions
  (forced exit / session change) and the frequency cap is off, so this equals a trade-window gate;
- research-session counters = (warmup+research run) − (warmup-only run). That subtraction is valid only if the
  warmup-only run reproduces the warmup trades of the full run, which is asserted (PIT prefix check);
- the embargo session is never loaded (data/v11_research_loader.py), so no signal is computed for it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, fields
from datetime import date
import hashlib
import json
import math
from typing import Any, Callable

import numpy as np
import pandas as pd

from backtest.day_engine import run_day_backtest
from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.metrics import compute_day_metrics
from data.session import get_session_date, to_eastern
from data.v11_research_loader import V11ResearchData

COST_LEVELS_BPS = (0.0, 5.0, 10.0)
PRIMARY_COST_BPS = 5.0
COUNTERS = ("candidate_signals", "skipped_signals", "insufficient_data_count", "same_bar_ambiguity_count",
            "simulation_none_count", "cap_rejected_signals", "window_rejected_signals")
TOD_BUCKETS = (("09:30–10:00", "09:30", "10:00"), ("10:00–11:00", "10:00", "11:00"), ("11:00–12:00", "11:00", "12:00"),
               ("12:00–14:00", "12:00", "14:00"), ("14:00–15:00", "14:00", "15:00"), ("15:00–16:00", "15:00", "16:00"))


# ------------------------------------------------------------------ helpers

def trade_session(t: DayBacktestTrade) -> date:
    return get_session_date(t.setup_time)


def trade_key(t: DayBacktestTrade) -> str:
    """Canonical, NaN-safe serialisation of every trade field (for equality and hashing)."""
    d = {}
    for f in fields(t):
        v = getattr(t, f.name)
        if isinstance(v, float):
            v = "nan" if math.isnan(v) else repr(v)
        elif isinstance(v, pd.Timestamp):
            v = v.isoformat()
        elif isinstance(v, tuple):
            v = list(v)
        d[f.name] = v
    return json.dumps(d, sort_keys=True, default=str)


def cost_return(t: DayBacktestTrade, bps: float, cfg: ExecutionConfig) -> float:
    """DAY-04 formula (backtest/multi_symbol.py §7): (1+g)(1−s)/(1+s) − 1 on raw entry/exit prices."""
    raw_ent = t.entry_price / (1.0 + cfg.slippage_bps / 10000.0)
    raw_ex = (t.exit_price + cfg.commission_per_share) / (1.0 - cfg.slippage_bps / 10000.0)
    new_ent = raw_ent * (1.0 + bps / 10000.0) + cfg.commission_per_share
    new_ex = raw_ex * (1.0 - bps / 10000.0) - cfg.commission_per_share
    return (new_ex - new_ent) / new_ent


def _compounded_and_dd(returns: list[float]) -> tuple[float, float]:
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in returns:
        eq *= 1.0 + r
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    return (eq - 1.0) * 100.0, mdd * 100.0


def _pf(rets: list[float]) -> float:
    g = sum(r for r in rets if r > 0)
    l = abs(sum(r for r in rets if r < 0))
    return g / l if l > 0 else (float("inf") if g > 0 else 0.0)


# ------------------------------------------------------------------ per-symbol run

def run_symbol(data: V11ResearchData, sym: str, cfg: ExecutionConfig,
               frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    """frames: optional replacement {interval: warmup+research frame} (used by the PIT mutation tests)."""
    f5 = frames["5m"] if frames else data.frame(sym, "5m")
    f15 = frames["15m"] if frames else data.frame(sym, "15m")
    warm_set, research_set = set(data.warmup_sessions), set(data.research_sessions)
    full = run_day_backtest(sym, df_5m=f5, df_15m=f15, config=cfg, use_fast_engine=True)
    s5 = pd.Series(to_eastern(f5.index).date, index=f5.index)
    s15 = pd.Series(to_eastern(f15.index).date, index=f15.index)
    w5, w15 = f5.loc[s5.isin(warm_set).to_numpy()], f15.loc[s15.isin(warm_set).to_numpy()]
    warm = run_day_backtest(sym, df_5m=w5, df_15m=w15, config=cfg, use_fast_engine=True)
    sessions_in_trades = {trade_session(t) for t in full.trades}
    outside = sessions_in_trades - warm_set - research_set
    if outside:
        raise RuntimeError(f"{sym}: trades in sessions outside warmup+research: {sorted(outside)}")
    full_warm = [trade_key(t) for t in full.trades if trade_session(t) in warm_set]
    prefix_ok = full_warm == [trade_key(t) for t in warm.trades]
    research_trades = [t for t in full.trades if trade_session(t) in research_set]
    counters = {c: int(getattr(full, c)) - int(getattr(warm, c)) for c in COUNTERS}
    r5 = f5.loc[s5.isin(research_set).to_numpy()]
    research_sessions_present = sorted(set(pd.Series(to_eastern(r5.index).date)))
    bnh = (float(r5["close"].iloc[-1]) - float(r5["open"].iloc[0])) / float(r5["open"].iloc[0]) * 100.0
    return {"symbol": sym, "research_trades": research_trades, "counters": counters, "prefix_ok": prefix_ok,
            "warmup_trades": len(full_warm), "bnh": bnh, "research_sessions": len(research_sessions_present),
            "research_bars_5m": int(len(r5)), "first_research_bar": r5.index[0].isoformat(),
            "last_research_bar": r5.index[-1].isoformat(), "max_bar_seen": f5.index.max().isoformat(),
            "full_total_sessions": int(full.total_sessions)}


def per_symbol_metrics(run: dict[str, Any], cfg: ExecutionConfig) -> dict[str, Any]:
    trades = run["research_trades"]
    m = compute_day_metrics(trades, buy_and_hold_return=run["bnh"])
    out = {"symbol": run["symbol"], "sessions": run["research_sessions"], "bars_5m": run["research_bars_5m"],
           "trades": len(trades), "wins": m["winning_trades"], "losses": m["losing_trades"],
           "breakevens": m["breakeven_trades"], "win_rate": m["win_rate"],
           "strategy_total_return": m["total_return_pct"], "avg_trade_return": m["average_return_pct"],
           "median_trade_return": m["median_return_pct"], "profit_factor": m["profit_factor"],
           "max_drawdown": m["max_drawdown_pct"], "avg_R": m.get("average_R"), "median_R": m.get("median_R"),
           "total_R": m.get("total_R"), "buy_hold_return": run["bnh"],
           "return_difference_vs_buy_hold": m["total_return_pct"] - run["bnh"], **run["counters"]}
    for bps in COST_LEVELS_BPS:
        rets = [cost_return(t, bps, cfg) for t in trades]
        comp, _ = _compounded_and_dd(rets)
        out[f"return_{int(bps)}bps"] = comp
        out[f"mean_net_trade_return_{int(bps)}bps"] = float(np.mean(rets)) * 100.0 if rets else 0.0
    return out


# ------------------------------------------------------------------ pooled

def pooled_metrics(runs: list[dict[str, Any]], cfg: ExecutionConfig) -> dict[str, Any]:
    trades = sorted((t for r in runs for t in r["research_trades"]), key=lambda t: (t.entry_time, t.symbol))
    n = len(trades)
    net = [t.net_return for t in trades]
    r_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
    agg = {"total_trades": n, "wins": sum(1 for x in net if x > 0), "losses": sum(1 for x in net if x < 0),
           "breakevens": sum(1 for x in net if x == 0)}
    agg["win_rate"] = agg["wins"] / n if n else 0.0
    agg["profit_factor"] = _pf(net)
    agg["expectancy_pct"] = float(np.mean(net)) * 100.0 if n else 0.0
    agg["total_R"] = float(sum(r_vals)) if r_vals else 0.0
    agg["avg_R"] = float(np.mean(r_vals)) if r_vals else 0.0
    agg["median_R"] = float(np.median(r_vals)) if r_vals else 0.0
    agg["r_std"] = float(np.std(r_vals)) if len(r_vals) > 1 else 0.0
    costs = {}
    for bps in COST_LEVELS_BPS:
        rets = [cost_return(t, bps, cfg) for t in trades]
        comp, dd = _compounded_and_dd(rets)
        costs[f"{int(bps)} bps"] = {
            "compounded_return_pct": comp, "max_drawdown_pct": dd,
            "mean_net_trade_return_pct": float(np.mean(rets)) * 100.0 if rets else 0.0,
            "median_net_trade_return_pct": float(np.median(rets)) * 100.0 if rets else 0.0,
            "win_rate": sum(1 for r in rets if r > 0) / n if n else 0.0, "profit_factor": _pf(rets)}
    counters = {c: sum(r["counters"][c] for r in runs) for c in COUNTERS}
    exit_reasons = dict(Counter(t.exit_reason for t in trades))
    statuses = dict(Counter(t.setup_status for t in trades))
    by_month: dict[str, list[DayBacktestTrade]] = defaultdict(list)
    by_tod: dict[str, list[DayBacktestTrade]] = defaultdict(list)
    for t in trades:
        et = to_eastern(t.entry_time)
        by_month[et.strftime("%Y-%m")].append(t)
        hm = et.strftime("%H:%M")
        for name, a, b in TOD_BUCKETS:
            if a <= hm < b:
                by_tod[name].append(t)

    def _grp(ts: list[DayBacktestTrade]) -> dict[str, Any]:
        rr = [x.r_multiple for x in ts if x.r_multiple is not None]
        r5 = [cost_return(x, PRIMARY_COST_BPS, cfg) for x in ts]
        return {"trades": len(ts), "total_R": float(sum(rr)), "mean_net_trade_return_5bps_pct": float(np.mean(r5)) * 100.0 if r5 else 0.0}

    return {"aggregate": agg, "cost_scenarios": costs, "counters": counters, "exit_reasons": exit_reasons,
            "setup_status": statuses, "by_month": {k: _grp(v) for k, v in sorted(by_month.items())},
            "by_time_of_day": {k: _grp(by_tod.get(k, [])) for k, _, _ in TOD_BUCKETS},
            "primary_metric": {"name": "mean_net_trade_return_5bps_pct",
                               "value": costs["5 bps"]["mean_net_trade_return_pct"]}}


def distribution(per_symbol: list[dict[str, Any]]) -> dict[str, Any]:
    s = [m["strategy_total_return"] for m in per_symbol]
    b = [m["buy_hold_return"] for m in per_symbol]
    tot_r = sorted(((m["total_R"] or 0.0) for m in per_symbol), reverse=True)
    sum_r = sum(tot_r)
    return {"symbols_tested": len(per_symbol), "positive_strategy_symbols": sum(1 for x in s if x > 0),
            "negative_strategy_symbols": sum(1 for x in s if x < 0), "zero_strategy_symbols": sum(1 for x in s if x == 0),
            "outperformed_buy_hold_count": sum(1 for m in per_symbol if m["strategy_total_return"] > m["buy_hold_return"]),
            "positive_total_R_symbols": sum(1 for m in per_symbol if (m["total_R"] or 0) > 0),
            "median_strategy_return": float(np.median(s)), "mean_strategy_return": float(np.mean(s)),
            "benchmark_equal_weight_return": float(np.mean(b)), "median_buy_hold_return": float(np.median(b)),
            "strategy_mean_minus_benchmark": float(np.mean(s)) - float(np.mean(b)),
            "top2_total_R": tot_r[:2], "top2_share_of_total_R": (sum(tot_r[:2]) / sum_r) if sum_r else None}


def trades_digest(runs: list[dict[str, Any]]) -> str:
    keys = sorted(trade_key(t) for r in runs for t in r["research_trades"])
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def run_baseline(data: V11ResearchData, cfg: ExecutionConfig | None = None,
                 frame_override: Callable[[str], dict[str, pd.DataFrame] | None] | None = None,
                 log: Callable[[str], None] = lambda _m: None) -> list[dict[str, Any]]:
    cfg = cfg or ExecutionConfig()
    runs = []
    for sym in sorted(data.frames):
        runs.append(run_symbol(data, sym, cfg, frames=frame_override(sym) if frame_override else None))
        log(f"{sym}: {len(runs[-1]['research_trades'])} research trades")
    return runs


# ------------------------------------------------------------------ PIT mutations

def mutate_from(df: pd.DataFrame, cutoff: date, *, before: bool = False) -> pd.DataFrame:
    """Deterministic distortion of bars on/after (or before) `cutoff`: prices ×1.3 with open/close swapped,
    volume ×3. OHLC stays internally consistent."""
    out = df.copy()
    sess = pd.Series(to_eastern(out.index).date, index=out.index)
    mask = (sess < cutoff) if before else (sess >= cutoff)
    m = mask.to_numpy()
    o, c = out.loc[m, "open"].copy(), out.loc[m, "close"].copy()
    out.loc[m, "open"], out.loc[m, "close"] = c * 1.3, o * 1.3
    out.loc[m, "high"] = out.loc[m, "high"] * 1.3
    out.loc[m, "low"] = out.loc[m, "low"] * 1.3
    out.loc[m, "volume"] = out.loc[m, "volume"] * 3.0
    return out


def future_mutation_check(data: V11ResearchData, base_runs: list[dict[str, Any]], cutoff: date,
                          cfg: ExecutionConfig) -> dict[str, Any]:
    def override(sym: str) -> dict[str, pd.DataFrame]:
        return {iv: mutate_from(data.frame(sym, iv), cutoff) for iv in ("5m", "15m")}
    mutated = run_baseline(data, cfg, frame_override=override)
    changed, compared, later_changed = [], 0, 0
    for a, b in zip(base_runs, mutated):
        ea = [trade_key(t) for t in a["research_trades"] if trade_session(t) < cutoff]
        eb = [trade_key(t) for t in b["research_trades"] if trade_session(t) < cutoff]
        compared += len(ea)
        if ea != eb:
            changed.append(a["symbol"])
        la = [trade_key(t) for t in a["research_trades"] if trade_session(t) >= cutoff]
        lb = [trade_key(t) for t in b["research_trades"] if trade_session(t) >= cutoff]
        later_changed += int(la != lb)
    return {"cutoff_session": cutoff.isoformat(), "earlier_trades_compared": compared,
            "symbols_with_changed_earlier_trades": changed, "passed": not changed,
            "symbols_with_changed_later_trades": later_changed,
            "note": "later trades are expected to change (sanity check that the mutation was effective)"}


def warmup_mutation_check(data: V11ResearchData, base_runs: list[dict[str, Any]], cfg: ExecutionConfig) -> dict[str, Any]:
    first_research = min(data.research_sessions)

    def override(sym: str) -> dict[str, pd.DataFrame]:
        return {iv: mutate_from(data.frame(sym, iv), first_research, before=True) for iv in ("5m", "15m")}
    mutated = run_baseline(data, cfg, frame_override=override)
    a_keys = {trade_key(t) for r in base_runs for t in r["research_trades"]}
    b_keys = {trade_key(t) for r in mutated for t in r["research_trades"]}
    return {"description": "warmup bars mutated; research trades may legitimately change via RVOL/RSI/structure history",
            "research_trades_base": len(a_keys), "research_trades_mutated": len(b_keys),
            "research_trades_identical": len(a_keys & b_keys), "research_trades_changed_or_new": len(b_keys - a_keys),
            "gate_relevance": "descriptive only (not a pass/fail condition)"}


# ------------------------------------------------------------------ gate

def research_gate(primary_value: float, hard: dict[str, bool]) -> dict[str, Any]:
    """Protocol v1.1 §21: PASS iff mean net trade return at 5 bps per side >= 0 AND every hard requirement holds.
    No other threshold exists."""
    sign_ok = primary_value >= 0.0
    failed = [k for k, v in hard.items() if not v]
    return {"decision": "PASS" if (sign_ok and not failed) else "FAIL",
            "primary_metric": "mean_net_trade_return_5bps_pct", "primary_value": primary_value,
            "primary_condition": ">= 0", "primary_condition_met": sign_ok,
            "hard_requirements": hard, "failed_hard_requirements": failed}


def execution_config_dict(cfg: ExecutionConfig) -> dict[str, Any]:
    d = asdict(cfg)
    d["valid_statuses"] = [s.value if hasattr(s, "value") else str(s) for s in cfg.valid_statuses]
    d["force_exit_time"] = str(cfg.force_exit_time)
    return d
