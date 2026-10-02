"""backtest/exit_decomposition.py: DAY-12A — Exit Failure Decomposition (DIAGNOSTIC ONLY).

Research question:
    For the existing baseline trades, how much favorable price movement occurs before the actual exit,
    and how often do trades that initially move favorably later become losers?

Principles:
    1. Ex-post diagnostic of the FROZEN plain baseline (no cap / SIGNAL_LOW / 2R / STOP_FIRST / 15:55 forced
       exit / 0 bps). Signal, stop, target, execution and cache are untouched; trades are NOT re-simulated
       with modified rules and NO counterfactual exit (BE, trailing, partial, time stop, ...) is evaluated.
    2. Path observation window = entry bar .. actual exit bar (positional slice). No bar after the exit bar
       is ever read, so later data cannot change a trade's excursion.
    3. Exit-bar convention (approved before results were computed):
       PRIMARY      — adverse-first (open -> low -> high), the same spirit as the engine's STOP_FIRST rule:
                      STOP exit bar  : favorable = {open}; adverse = {open, stop fill}
                      TARGET exit bar: favorable = {open, target fill}; adverse = {open, low}
                      FORCED exit bar: held to the close by the engine -> full high/low.
       UPPER_BOUND  — full high/low of the exit bar for every exit reason (sensitivity bound only).
       Entry bar and intermediate bars (checked by the engine without an exit) always contribute their full
       high/low; the entry open itself is a path point, so MFE >= 0 by construction.
    4. R uses the trade's ORIGINAL risk distance (risk_per_share = entry - SIGNAL_LOW stop). No ATR / other
       stop model. Invalid risk (None / <= 0) -> NaN R fields, counted, excluded from R statistics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.dynamic_stop import compute_metrics_for_trades
from backtest.failure_analysis import get_stop_distance_bucket, get_time_of_day_bucket, map_exit_reason
from backtest.frequency_cap import trade_fingerprint
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.multi_types import MultiSymbolDayBacktestResult
from backtest.time_window import TOD_BINS, load_regression_anchors
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.provider import DataProvider
from data.session import to_eastern

ROOT_DIR = Path(__file__).resolve().parent.parent
DAY10_RESULTS = ROOT_DIR / "artifacts" / "day10" / "frequency-cap-results.json"

MODES = ("PRIMARY", "UPPER_BOUND")
EXIT_GROUPS = ("STOP", "TARGET", "FORCED_EXIT")
R_THRESHOLDS = (0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00)
TIME_BINS = ((0, 5), (5, 10), (10, 15), (15, 30), (30, 60), (60, 120), (120, None))
HOLD_BINS = ((0, 5), (5, 15), (15, 30), (30, 60), (60, 120), (120, None))
RAPID_BINS = ((0, 5), (5, 10), (10, 15))
MFE_BUCKETS = ((None, 0.0), (0.0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, None))
STOP_DIST_BINS = ("<0.25%", "0.25–0.50%", "0.50–1.00%", "1.00–2.00%", "2.00%+")
_TOL = 1e-9

# Analyst criterion written BEFORE DAY-12A results were computed. It operationalises the prompt's
# qualitative definitions; it is NOT a protocol-predeclared rule and says nothing about any exit change.
MECHANISM_CRITERION = (
    "Analyst criterion defined before DAY-12A results were viewed (not a protocol-predeclared rule). "
    "MECHANISM SUPPORTED: under the PRIMARY (adverse-first) convention >= 25% of losing trades reached "
    ">= +1.0R MFE before exit, AND that share is >= 25% in a majority of symbols with >= 10 losers. "
    "MECHANISM NOT SUPPORTED: < 15% of losers reached >= +0.5R under PRIMARY AND < 25% under UPPER_BOUND. "
    "MECHANISM INCONCLUSIVE: anything else. The classification only describes whether eventual losers "
    "experienced substantial favorable excursion; it does not imply any exit modification would help."
)


def _label(lo, hi, unit: str = " min") -> str:
    return f"{lo}+{unit}" if hi is None else f"{lo}–{hi}{unit}"


def _bin(value: float, bins) -> str | None:
    for lo, hi in bins:
        if value >= lo and (hi is None or value < hi):
            return _label(lo, hi)
    return None


def _mfe_bucket(mfe_r: float) -> str:
    for lo, hi in MFE_BUCKETS:
        if (lo is None or mfe_r >= lo) and (hi is None or mfe_r < hi):
            if lo is None:
                return f"MFE < {hi:g}R"
            if hi is None:
                return f"MFE >= {lo:g}R"
            return f"{lo:g}R <= MFE < {hi:g}R"
    return "UNKNOWN"


MFE_BUCKET_LABELS = tuple(_mfe_bucket(x) for x in (-1.0, 0.0, 0.5, 1.0, 1.5, 2.0))


# =====================================================================
# 1. Per-trade excursion (pure, PIT-safe)
# =====================================================================

@dataclass(frozen=True)
class TradeExcursion:
    mode: str
    mfe_price: float
    mae_price: float
    mfe: float                   # mfe_price - entry (>= 0)
    mae: float                   # mae_price - entry (<= 0)
    mfe_r: float                 # NaN if risk invalid
    mae_r: float
    mfe_time: pd.Timestamp
    mae_time: pd.Timestamp
    time_to_mfe_minutes: int
    time_to_mae_minutes: int
    bars_observed: int
    exit_bar_same_bar_ambiguous: bool   # stop exit on a bar whose high also reached target (STOP_FIRST)
    exit_bar_gap_through: bool          # exit-bar open already beyond the stop (STOP) / target (TARGET)
    risk_valid: bool


def _locate(bars: pd.DataFrame, ts: pd.Timestamp, what: str) -> int:
    try:
        loc = bars.index.get_loc(ts)
    except KeyError as exc:
        raise ValueError(f"{what} timestamp {ts} not found in bars — cannot reconstruct path") from exc
    if not isinstance(loc, (int, np.integer)):
        raise ValueError(f"{what} timestamp {ts} is not unique in bars")
    return int(loc)


def compute_trade_excursion(bars: pd.DataFrame, trade: DayBacktestTrade, mode: str = "PRIMARY") -> TradeExcursion:
    """MFE/MAE of a completed long trade from its entry bar through its actual exit bar (inclusive).

    Bars after the exit bar are never read. Raises ValueError instead of approximating when the trade
    cannot be located faithfully in ``bars``.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    ei = _locate(bars, trade.entry_time, "entry")
    xi = _locate(bars, trade.exit_time, "exit")
    if xi < ei:
        raise ValueError("exit bar precedes entry bar")
    entry = float(trade.entry_price)
    entry_open = float(bars["open"].iloc[ei])
    if not math.isclose(entry_open, entry, rel_tol=0.0, abs_tol=_TOL * max(1.0, abs(entry))):
        raise ValueError(f"entry_price {entry} != entry-bar open {entry_open} (non-zero cost model?)")

    path = bars.iloc[ei: xi + 1]          # positional: entry bar .. exit bar, nothing after
    highs = path["high"].to_numpy(dtype=float)
    lows = path["low"].to_numpy(dtype=float)
    opens = path["open"].to_numpy(dtype=float)
    times = path.index
    group = map_exit_reason(trade.exit_reason)
    last = len(path) - 1

    # (price, bar_position) candidates in chronological bar order
    fav: list[tuple[float, int]] = [(entry, 0)]
    adv: list[tuple[float, int]] = [(entry, 0)]
    for k in range(last):
        fav.append((highs[k], k))
        adv.append((lows[k], k))

    ambiguous = False
    gap = False
    o, h, lo_ = opens[last], highs[last], lows[last]
    if mode == "UPPER_BOUND" or group == "FORCED_EXIT":
        fav.append((h, last))
        adv.append((lo_, last))
    elif group == "STOP":
        stop_fill = float(trade.exit_price)
        fav.append((o, last))
        adv.extend([(o, last), (stop_fill, last)])
        ambiguous = trade.target_price is not None and h >= float(trade.target_price)
        gap = o < stop_fill
    elif group == "TARGET":
        target_fill = float(trade.exit_price)
        fav.extend([(o, last), (target_fill, last)])
        adv.extend([(o, last), (lo_, last)])
        gap = o > target_fill
    else:  # BREAKEVEN / unknown: not produced by the plain baseline
        raise ValueError(f"unsupported exit reason for DAY-12A baseline: {trade.exit_reason!r}")

    # max/min return the FIRST extreme; candidates are chronological, so ties resolve to the earliest bar
    mfe_price, mfe_k = max(fav, key=lambda c: c[0])
    mae_price, mae_k = min(adv, key=lambda c: c[0])

    risk = trade.risk_per_share
    risk_valid = risk is not None and math.isfinite(risk) and risk > 0.0
    mfe, mae = mfe_price - entry, mae_price - entry
    entry_ts = times[0]
    return TradeExcursion(
        mode=mode,
        mfe_price=float(mfe_price),
        mae_price=float(mae_price),
        mfe=float(mfe),
        mae=float(mae),
        mfe_r=float(mfe / risk) if risk_valid else float("nan"),
        mae_r=float(mae / risk) if risk_valid else float("nan"),
        mfe_time=times[mfe_k],
        mae_time=times[mae_k],
        time_to_mfe_minutes=int((times[mfe_k] - entry_ts).total_seconds() / 60),
        time_to_mae_minutes=int((times[mae_k] - entry_ts).total_seconds() / 60),
        bars_observed=len(path),
        exit_bar_same_bar_ambiguous=bool(ambiguous),
        exit_bar_gap_through=bool(gap),
        risk_valid=bool(risk_valid),
    )


def verify_trade_record(bars: pd.DataFrame, trade: DayBacktestTrade, target_multiple: float = 2.0) -> dict[str, bool]:
    """Consistency of a baseline trade record with the frozen bars and the existing execution semantics."""
    si = _locate(bars, trade.setup_time, "signal")
    ei = _locate(bars, trade.entry_time, "entry")
    xi = _locate(bars, trade.exit_time, "exit")
    entry = float(trade.entry_price)
    risk = trade.risk_per_share
    signal_low = float(bars["low"].iloc[si])
    if signal_low < entry:
        exp_stop = signal_low
    elif not math.isnan(trade.vwap_at_setup) and 0.0 < trade.vwap_at_setup < entry:
        exp_stop = trade.vwap_at_setup
    else:
        exp_stop = entry * 0.99
    close = lambda a, b: a is not None and b is not None and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)
    group = map_exit_reason(trade.exit_reason)
    if group == "STOP":
        exit_ok = close(trade.exit_price, trade.stop_price)
    elif group == "TARGET":
        exit_ok = close(trade.exit_price, trade.target_price)
    else:
        exit_ok = close(trade.exit_price, float(bars["close"].iloc[xi]))
    return {
        "entry_is_next_bar": ei == si + 1,
        "entry_equals_bar_open": close(entry, float(bars["open"].iloc[ei])),
        "stop_matches_signal_low_rule": close(trade.stop_price, exp_stop),
        "risk_matches_entry_minus_stop": close(risk, entry - (trade.stop_price or float("nan"))),
        "target_is_entry_plus_2R": close(trade.target_price, entry + target_multiple * (risk or float("nan"))),
        "exit_price_matches_reason": exit_ok,
        "r_multiple_recomputes": close(trade.r_multiple, (float(trade.exit_price) - entry) / risk) if risk else False,
        "hold_minutes_recomputes": trade.hold_duration_minutes == int((trade.exit_time - trade.entry_time).total_seconds() / 60),
    }


# =====================================================================
# 2. Baseline reconstruction
# =====================================================================

def baseline_config_is_plain(cfg: ExecutionConfig) -> dict[str, bool]:
    return {
        "stop_mode_SIGNAL_LOW": cfg.stop_mode == "SIGNAL_LOW",
        "target_2R": cfg.target_multiple == 2.0,
        "same_bar_STOP_FIRST": cfg.same_bar_rule == "STOP_FIRST",
        "no_breakeven_H2": cfg.breakeven_trigger_r is None,
        "no_atr_stop_H4": cfg.atr_stop_multiplier is None,
        "no_frequency_cap_H3": cfg.max_trades_per_session is None,
        "no_entry_window_H5": cfg.entry_window is None,
        "zero_cost": cfg.slippage_bps == 0.0 and cfg.commission_per_share == 0.0,
        "no_vwap_exit": cfg.exit_on_vwap_cross is False,
    }


def load_symbol_bars(provider: DataProvider, symbol: str) -> pd.DataFrame:
    """Same frozen 5m frame the multi-symbol runner reads (read-only, cache expiry ignored)."""
    return provider.get_ohlcv(symbol, "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)


def _nan_none(x):
    return None if isinstance(x, float) and not math.isfinite(x) else x


def build_trade_rows(
    trades: Sequence[DayBacktestTrade], bars_by_symbol: dict[str, pd.DataFrame]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    check_fail: Counter = Counter()
    for i, t in enumerate(trades):
        bars = bars_by_symbol[t.symbol]
        checks = verify_trade_record(bars, t)
        for k, ok in checks.items():
            if not ok:
                check_fail[k] += 1
        p = compute_trade_excursion(bars, t, "PRIMARY")
        u = compute_trade_excursion(bars, t, "UPPER_BOUND")
        et = to_eastern(t.entry_time)
        rows.append({
            "trade_id": i,
            "symbol": t.symbol,
            "session": str(et.date()),
            "signal_time": t.setup_time,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "entry_price": t.entry_price,
            "stop_price": t.stop_price,
            "target_price": t.target_price,
            "exit_price": t.exit_price,
            "risk_per_share": t.risk_per_share,
            "stop_distance_pct": (t.risk_per_share / t.entry_price) if t.risk_per_share else float("nan"),
            "exit_reason_raw": t.exit_reason,
            "exit_reason": map_exit_reason(t.exit_reason),
            "final_R": t.r_multiple if t.r_multiple is not None else float("nan"),
            "gross_return": t.gross_return,
            "outcome": "WIN" if t.gross_return > 0 else ("LOSS" if t.gross_return < 0 else "BREAKEVEN"),
            "holding_minutes": t.hold_duration_minutes,
            "entry_tod_bin": get_time_of_day_bucket(et.time()),
            "MFE": p.mfe, "MFE_R": p.mfe_r, "MFE_price": p.mfe_price, "MFE_time": p.mfe_time,
            "time_to_MFE_minutes": p.time_to_mfe_minutes,
            "MAE": p.mae, "MAE_R": p.mae_r, "MAE_price": p.mae_price, "MAE_time": p.mae_time,
            "time_to_MAE_minutes": p.time_to_mae_minutes,
            "MFE_R_upper_bound": u.mfe_r, "MAE_R_upper_bound": u.mae_r,
            "bars_observed": p.bars_observed,
            "exit_bar_same_bar_ambiguous": p.exit_bar_same_bar_ambiguous,
            "exit_bar_gap_through": p.exit_bar_gap_through,
            "risk_valid": p.risk_valid,
        })
    integrity = {
        "trades_reconstructed": len(rows),
        "record_check_failures": dict(check_fail),
        "all_record_checks_pass": not check_fail,
        "invalid_risk_trades": sum(1 for r in rows if not r["risk_valid"]),
        "exit_bar_same_bar_ambiguous_stop_trades": sum(1 for r in rows if r["exit_bar_same_bar_ambiguous"]),
        "exit_bar_gap_through_trades": sum(1 for r in rows if r["exit_bar_gap_through"]),
        "primary_mfe_never_exceeds_upper_bound": all(
            r["MFE_R"] <= r["MFE_R_upper_bound"] + 1e-12 for r in rows if r["risk_valid"]),
        "primary_mae_never_below_upper_bound": all(
            r["MAE_R"] >= r["MAE_R_upper_bound"] - 1e-12 for r in rows if r["risk_valid"]),
    }
    return rows, integrity


# =====================================================================
# 3. Aggregations (descriptive only)
# =====================================================================

def _f(values) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def _mean(v) -> float | None:
    v = _f(v)
    return round(float(np.mean(v)), 4) if v else None


def _median(v) -> float | None:
    v = _f(v)
    return round(float(np.median(v)), 4) if v else None


def _pf(rows) -> float | None:
    gw = sum(r["gross_return"] for r in rows if r["gross_return"] > 0)
    gl = sum(-r["gross_return"] for r in rows if r["gross_return"] < 0)
    if gl > 0:
        return round(gw / gl, 4)
    return None


def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def _reach(rows, thr: float, key: str = "MFE_R") -> int:
    return sum(1 for r in rows if r["risk_valid"] and r[key] >= thr - 1e-12)


def group_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"count": 0}
    v = [r for r in rows if r["risk_valid"]]
    ex = Counter(r["exit_reason"] for r in rows)
    return {
        "count": n,
        "win_rate": round(sum(1 for r in rows if r["gross_return"] > 0) / n, 4),
        "profit_factor": _pf(rows),
        "avg_R": _mean(r["final_R"] for r in rows),
        "median_R": _median(r["final_R"] for r in rows),
        "total_R": round(sum(_f(r["final_R"] for r in rows)), 2),
        "avg_MFE_usd": _mean(r["MFE"] for r in rows),
        "median_MFE_usd": _median(r["MFE"] for r in rows),
        "avg_MFE_pct": _mean(100 * r["MFE"] / r["entry_price"] for r in rows),
        "median_MFE_pct": _median(100 * r["MFE"] / r["entry_price"] for r in rows),
        "avg_MFE_R": _mean(r["MFE_R"] for r in v),
        "median_MFE_R": _median(r["MFE_R"] for r in v),
        "avg_MAE_usd": _mean(r["MAE"] for r in rows),
        "median_MAE_usd": _median(r["MAE"] for r in rows),
        "avg_MAE_pct": _mean(100 * r["MAE"] / r["entry_price"] for r in rows),
        "median_MAE_pct": _median(100 * r["MAE"] / r["entry_price"] for r in rows),
        "avg_MAE_R": _mean(r["MAE_R"] for r in v),
        "median_MAE_R": _median(r["MAE_R"] for r in v),
        "avg_hold_minutes": _mean(r["holding_minutes"] for r in rows),
        "median_hold_minutes": _median(r["holding_minutes"] for r in rows),
        "avg_time_to_MFE_minutes": _mean(r["time_to_MFE_minutes"] for r in rows),
        "avg_time_to_MAE_minutes": _mean(r["time_to_MAE_minutes"] for r in rows),
        "pct_reach_0.5R": _pct(_reach(rows, 0.5), len(v)),
        "pct_reach_1R": _pct(_reach(rows, 1.0), len(v)),
        "exit_counts": {k: int(ex.get(k, 0)) for k in EXIT_GROUPS},
    }


def threshold_table(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    groups = {
        "ALL": list(rows),
        "WINNERS": [r for r in rows if r["outcome"] == "WIN"],
        "LOSERS": [r for r in rows if r["outcome"] == "LOSS"],
        "STOP": [r for r in rows if r["exit_reason"] == "STOP"],
        "TARGET": [r for r in rows if r["exit_reason"] == "TARGET"],
        "FORCED_EXIT": [r for r in rows if r["exit_reason"] == "FORCED_EXIT"],
    }
    out: dict[str, Any] = {}
    for g, rs in groups.items():
        d = sum(1 for r in rs if r["risk_valid"])
        out[g] = {"group_size": d, **{
            f"+{t:.2f}R": {"count": _reach(rs, t, key), "pct": _pct(_reach(rs, t, key), d)} for t in R_THRESHOLDS}}
    return out


def time_bin_table(rows, minutes_key: str, value_key: str) -> dict[str, Any]:
    n = len(rows)
    by: dict[str, list] = {_label(lo, hi): [] for lo, hi in TIME_BINS}
    for r in rows:
        by[_bin(r[minutes_key], TIME_BINS)].append(r)
    return {
        b: {
            "count": len(rs),
            "pct": _pct(len(rs), n),
            f"avg_{value_key}": _mean(r[value_key] for r in rs if r["risk_valid"]),
            f"median_{value_key}": _median(r[value_key] for r in rs if r["risk_valid"]),
            "avg_final_R": _mean(r["final_R"] for r in rs),
        }
        for b, rs in by.items()
    }


def _bucketed(rows, keyfn, labels) -> dict[str, list]:
    by: dict[str, list] = {lab: [] for lab in labels}
    for r in rows:
        by.setdefault(keyfn(r), []).append(r)
    return by


def ratio_stats(rows) -> dict[str, Any]:
    vals, undefined = [], 0
    for r in rows:
        if not r["risk_valid"]:
            continue
        if abs(r["MAE_R"]) < 1e-12:
            undefined += 1
            continue
        vals.append(r["MFE_R"] / abs(r["MAE_R"]))
    if not vals:
        return {"defined": 0, "undefined_mae_zero": undefined}
    a = np.asarray(vals)
    return {
        "defined": len(vals),
        "undefined_mae_zero": undefined,
        "mean": round(float(a.mean()), 4),
        "median": round(float(np.median(a)), 4),
        **{f"p{q}": round(float(np.percentile(a, q)), 4) for q in (10, 25, 75, 90)},
    }


def loser_reach(rows, key: str = "MFE_R") -> dict[str, Any]:
    losers = [r for r in rows if r["outcome"] == "LOSS" and r["risk_valid"]]
    return {
        "losers": len(losers),
        **{f"+{t:.2f}R": {"count": _reach(losers, t, key), "pct": _pct(_reach(losers, t, key), len(losers))}
           for t in R_THRESHOLDS},
    }


def symbol_robustness(rows, aggregate_loser_05: float | None, aggregate_loser_1: float | None) -> dict[str, Any]:
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[r["symbol"]].append(r)
    per = {}
    for s, rs in sorted(by.items()):
        lr = loser_reach(rs)
        per[s] = {
            "trades": len(rs),
            "losers": lr["losers"],
            "avg_MFE_R": _mean(r["MFE_R"] for r in rs if r["risk_valid"]),
            "avg_MAE_R": _mean(r["MAE_R"] for r in rs if r["risk_valid"]),
            "loser_pct_reach_0.5R": lr["+0.50R"]["pct"],
            "loser_pct_reach_1R": lr["+1.00R"]["pct"],
            "total_R": round(sum(_f(r["final_R"] for r in rs)), 2),
        }

    def summ(key, agg):
        v = [d[key] for d in per.values() if d[key] is not None]
        if not v:
            return {}
        out = {"median": round(float(np.median(v)), 4), "min": min(v), "max": max(v)}
        if agg is not None:
            out.update({"aggregate": agg, "symbols_above_aggregate": sum(1 for x in v if x > agg),
                        "symbols_at_or_below_aggregate": sum(1 for x in v if x <= agg)})
        return out

    return {
        "per_symbol": per,
        "summary": {
            "avg_MFE_R": summ("avg_MFE_R", None),
            "avg_MAE_R": summ("avg_MAE_R", None),
            "loser_pct_reach_0.5R": summ("loser_pct_reach_0.5R", aggregate_loser_05),
            "loser_pct_reach_1R": summ("loser_pct_reach_1R", aggregate_loser_1),
        },
    }


def classify_mechanism(primary_lr, upper_lr, sym_per) -> dict[str, Any]:
    p1 = primary_lr["+1.00R"]["pct"] or 0.0
    p05 = primary_lr["+0.50R"]["pct"] or 0.0
    u05 = upper_lr["+0.50R"]["pct"] or 0.0
    eligible = {s: d for s, d in sym_per.items() if d["losers"] >= 10}
    sym_ge25 = sum(1 for d in eligible.values() if (d["loser_pct_reach_1R"] or 0.0) >= 25.0)
    evidence = {
        "primary_loser_pct_reach_1R": p1,
        "primary_loser_pct_reach_0.5R": p05,
        "upper_bound_loser_pct_reach_0.5R": u05,
        "symbols_with_>=10_losers": len(eligible),
        "symbols_loser_reach_1R_>=25pct": sym_ge25,
    }
    if p1 >= 25.0 and sym_ge25 > len(eligible) / 2:
        status = "MECHANISM SUPPORTED"
    elif p05 < 15.0 and u05 < 25.0:
        status = "MECHANISM NOT SUPPORTED"
    else:
        status = "MECHANISM INCONCLUSIVE"
    return {"criterion": MECHANISM_CRITERION, "evidence": evidence, "status": status}


def analyze_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    winners = [r for r in rows if r["outcome"] == "WIN"]
    losers = [r for r in rows if r["outcome"] == "LOSS"]
    bes = [r for r in rows if r["outcome"] == "BREAKEVEN"]
    stop_losers = [r for r in losers if r["exit_reason"] == "STOP"]
    other_losers = [r for r in losers if r["exit_reason"] != "STOP"]

    by_exit = {g: group_stats([r for r in rows if r["exit_reason"] == g]) for g in EXIT_GROUPS}
    by_outcome = {"WINNERS": group_stats(winners), "LOSERS": group_stats(losers), "BREAKEVENS": group_stats(bes),
                  "STOP_LOSERS": group_stats(stop_losers), "OTHER_LOSERS": group_stats(other_losers)}

    hold = _bucketed(rows, lambda r: _bin(r["holding_minutes"], HOLD_BINS), [_label(*b) for b in HOLD_BINS])
    rapid = _bucketed([r for r in rows if r["holding_minutes"] < 15],
                      lambda r: _bin(r["holding_minutes"], RAPID_BINS), [_label(*b) for b in RAPID_BINS])
    mfe_b = _bucketed([r for r in rows if r["risk_valid"]], lambda r: _mfe_bucket(r["MFE_R"]), MFE_BUCKET_LABELS)
    sd = _bucketed(rows, lambda r: get_stop_distance_bucket(r["stop_distance_pct"]), STOP_DIST_BINS)
    tod = _bucketed(rows, lambda r: r["entry_tod_bin"], TOD_BINS)

    def tod_stats(rs):
        lr = loser_reach(rs)
        return {
            "trades": len(rs),
            "avg_R": _mean(r["final_R"] for r in rs),
            "avg_MFE_R": _mean(r["MFE_R"] for r in rs if r["risk_valid"]),
            "avg_MAE_R": _mean(r["MAE_R"] for r in rs if r["risk_valid"]),
            "losers": lr["losers"],
            "loser_pct_reach_0.5R": lr["+0.50R"]["pct"],
            "loser_pct_reach_1R": lr["+1.00R"]["pct"],
            "median_hold_minutes": _median(r["holding_minutes"] for r in rs),
        }

    single = [r for r in rows if r["bars_observed"] == 1]
    multi_losers = [r for r in losers if r["bars_observed"] > 1]
    resolution = {
        "note": "Trades whose entry and exit fall in the same 5m bar have no observable intrabar order; their "
        "PRIMARY vs UPPER_BOUND excursion depends entirely on the exit-bar convention. No finer-resolution bars "
        "exist in the frozen cache, so this cannot be resolved without new data.",
        "single_bar_trades": len(single),
        "single_bar_pct_of_all": _pct(len(single), len(rows)),
        "single_bar_exit_counts": {k: sum(1 for r in single if r["exit_reason"] == k) for k in EXIT_GROUPS},
        "single_bar_losers": sum(1 for r in single if r["outcome"] == "LOSS"),
        "losers_with_zero_MFE_primary": sum(1 for r in losers if r["MFE"] == 0.0),
        "multi_bar_losers_PRIMARY": loser_reach(multi_losers, "MFE_R"),
        "multi_bar_losers_UPPER_BOUND": loser_reach(multi_losers, "MFE_R_upper_bound"),
        "single_bar_losers_UPPER_BOUND": loser_reach([r for r in single if r["outcome"] == "LOSS"], "MFE_R_upper_bound"),
    }

    prim_lr = loser_reach(rows, "MFE_R")
    upper_lr = loser_reach(rows, "MFE_R_upper_bound")
    sym = symbol_robustness(rows, prim_lr["+0.50R"]["pct"], prim_lr["+1.00R"]["pct"])
    stop_rows = [r for r in rows if r["exit_reason"] == "STOP"]
    return {
        "exit_reason_decomposition": by_exit,
        "outcome_decomposition": by_outcome,
        "mfe_thresholds": {"PRIMARY": threshold_table(rows, "MFE_R"),
                           "UPPER_BOUND": threshold_table(rows, "MFE_R_upper_bound")},
        "losers_reaching_positive_excursion": {"PRIMARY": prim_lr, "UPPER_BOUND": upper_lr,
                                               "STOP_LOSERS_PRIMARY": loser_reach(stop_losers, "MFE_R"),
                                               "OTHER_LOSERS_PRIMARY": loser_reach(other_losers, "MFE_R")},
        "time_to_mfe": {"ALL": time_bin_table(rows, "time_to_MFE_minutes", "MFE_R"),
                        "LOSERS": time_bin_table(losers, "time_to_MFE_minutes", "MFE_R")},
        "time_to_mae": {"ALL": time_bin_table(rows, "time_to_MAE_minutes", "MAE_R"),
                        "STOP": time_bin_table(stop_rows, "time_to_MAE_minutes", "MAE_R"),
                        "LOSERS": time_bin_table(losers, "time_to_MAE_minutes", "MAE_R")},
        "holding_time": {b: group_stats(rs) for b, rs in hold.items()},
        "mfe_vs_final_r": {b: group_stats(rs) for b, rs in mfe_b.items()},
        "mfe_to_mae_ratio": {"ALL": ratio_stats(rows), "WINNERS": ratio_stats(winners), "LOSERS": ratio_stats(losers)},
        "rapid_exit": {b: group_stats(rs) for b, rs in rapid.items()},
        "stop_distance": {b: group_stats(rs) for b, rs in sd.items()},
        "symbol_robustness": sym,
        "time_of_day": {b: tod_stats(rs) for b, rs in tod.items()},
        "bar_resolution_limit": resolution,
        "mechanism": classify_mechanism(prim_lr, upper_lr, sym["per_symbol"]),
    }


# =====================================================================
# 4. Experiment runner
# =====================================================================

def run_day12a_exit_decomposition(
    symbols: Sequence[str] | None = None,
    provider: DataProvider | None = None,
    anchors_path: Path = DAY10_RESULTS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prov = provider or get_provider()
    symbols_list = list(symbols) if symbols is not None else get_day_universe()

    base: MultiSymbolDayBacktestResult = run_multi_symbol_day_backtest(symbols=symbols_list, provider=prov)
    tested = list(base.tested_symbols)
    trades = [t for s in tested for t in base.symbol_results[s].trades]
    bnh = {m.symbol: m.buy_hold_return for m in base.per_symbol_metrics}

    anchors = load_regression_anchors(anchors_path)
    m = asdict(compute_metrics_for_trades(trades, "BASELINE", bnh))
    cfg_checks = baseline_config_is_plain(base.execution_config)
    regression = {
        "anchors_source": str(anchors_path.relative_to(ROOT_DIR)),
        "anchors": anchors,
        "baseline_matches_anchors": {k: m[k] == anchors[k] for k in anchors},
        "plain_baseline_config": cfg_checks,
        "baseline_exit_counts": m["exit_counts"],
        "baseline_trade_fingerprints_sha_count": len({trade_fingerprint(t) for t in trades}),
    }
    regression["regression_verified"] = all(regression["baseline_matches_anchors"].values()) and all(cfg_checks.values())

    bars = {s: load_symbol_bars(prov, s) for s in tested}
    rows, integrity = build_trade_rows(trades, bars)
    integrity["trades_in_baseline"] = len(trades)
    integrity["all_trades_reconstructed"] = len(rows) == len(trades)
    integrity["raw_exit_reasons"] = dict(Counter(t.exit_reason for t in trades))
    integrity["same_bar_ambiguity_engine_count"] = sum(base.symbol_results[s].same_bar_ambiguity_count for s in tested)

    analysis = analyze_rows(rows)
    res = {
        "metadata": {
            "experiment": "DAY-12A Exit Failure Decomposition (diagnostic only)",
            "research_question": "For the existing baseline trades, how much favorable price movement occurs before "
            "the eventual exit, and how often do trades that initially move favorably later become losers under the "
            "existing exit model?",
            "nature": "Ex-post diagnostic observation of completed trades. NOT tradable rule validation; no "
            "counterfactual exit was simulated.",
            "execution_rules": {
                "entry": "T + 1 5m OPEN", "initial_stop": "SIGNAL_LOW (fallback VWAP / entry*0.99)", "target": "2.0R",
                "same_bar_ambiguity": "STOP_FIRST", "forced_exit": "15:55 ET bar CLOSE", "direction": "long-only",
                "frequency_cap": "none", "entry_window": "none", "costs": "0 bps",
            },
            "path_window": "entry bar .. actual exit bar inclusive (positional slice); no bar after the exit bar is read",
            "exit_bar_convention": {
                "PRIMARY": "adverse-first (open->low->high), consistent with STOP_FIRST. STOP exit bar: favorable={open}, "
                "adverse={open, stop fill}. TARGET exit bar: favorable={open, target fill}, adverse={open, low}. "
                "FORCED exit bar: full high/low (engine holds to the bar close without stop/target checks).",
                "UPPER_BOUND": "full high/low of the exit bar for every exit reason (sensitivity only).",
                "entry_and_intermediate_bars": "full high/low; entry open is a path point (MFE >= 0, MAE <= 0).",
            },
            "r_conversion": "MFE_R = (MFE_price - entry)/risk_per_share; MAE_R = (MAE_price - entry)/risk_per_share; "
            "risk_per_share = original entry - SIGNAL_LOW stop distance",
            "timing": "5m bar-open timestamps; time_to_X = first bar reaching the extreme - entry bar (entry bar = 0 min); "
            "holding_minutes = existing hold_duration_minutes (exit bar open - entry bar open)",
            "outcome_definition": "WIN gross_return > 0, LOSS < 0, BREAKEVEN == 0 (same as prior DAY reports)",
            "mfe_usd_note": "MFE/MAE in USD are not comparable across symbols; % of entry and R are reported alongside.",
        },
        "frozen_dataset": {
            "universe_size": len(tested),
            "universe_symbols": tested,
            "period_start": str(base.study_window_start),
            "period_end": str(base.study_window_end),
            "rth_sessions": base.total_sessions,
            "baseline_trades": len(trades),
        },
        "baseline_regression": regression,
        "integrity": integrity,
        **analysis,
    }
    return res, rows


# =====================================================================
# 5. Report formatter (neutral; no exit recommendation)
# =====================================================================

def _fmt(x, nd=4) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def format_exit_failure_report(res: dict[str, Any]) -> str:
    L: list[str] = []
    p = L.append
    md, ds, reg, integ = res["metadata"], res["frozen_dataset"], res["baseline_regression"], res["integrity"]
    bar = "=" * 118
    sub = "-" * 118

    def stats_table(groups: dict[str, Any], cols: Sequence[tuple[str, str, int]]) -> None:
        p(f"{'Group':<22}" + "".join(f"{h:>{w}}" for h, _, w in cols))
        for g, s in groups.items():
            if not s.get("count") and not s.get("trades"):
                p(f"{g:<22}" + f"{'(empty)':>10}")
                continue
            cells = []
            for _, k, w in cols:
                v = s.get(k)
                if k == "win_rate" and v is not None:
                    v = f"{v * 100:.2f}%"
                cells.append(f"{_fmt(v, 3):>{w}}")
            p(f"{g:<22}" + "".join(cells))
        p("")

    full_cols = [("N", "count", 6), ("WR", "win_rate", 8), ("PF", "profit_factor", 8), ("avgR", "avg_R", 8),
                 ("medR", "median_R", 8), ("totR", "total_R", 10), ("avgMFE%", "avg_MFE_pct", 9),
                 ("medMFE%", "median_MFE_pct", 9), ("avgMFE_R", "avg_MFE_R", 9), ("medMFE_R", "median_MFE_R", 9),
                 ("avgMAE%", "avg_MAE_pct", 9), ("medMAE%", "median_MAE_pct", 9), ("avgMAE_R", "avg_MAE_R", 9),
                 ("medMAE_R", "median_MAE_R", 9), ("avgHold", "avg_hold_minutes", 8), ("medHold", "median_hold_minutes", 8)]

    p(bar)
    p("DAY-12A — EXIT FAILURE DECOMPOSITION — DIAGNOSTIC REPORT (ex-post observation; no counterfactual)")
    p(bar)
    p("")
    p("1. RESEARCH QUESTION")
    p(sub)
    p(f"  {md['research_question']}")
    p(f"  {md['nature']}")
    p("")
    p("2. FROZEN BASELINE")
    p(sub)
    p(f"  Universe : {ds['universe_size']} symbols ({', '.join(ds['universe_symbols'])})")
    p(f"  Period   : {ds['period_start']} -> {ds['period_end']} ({ds['rth_sessions']} RTH sessions)")
    p(f"  Trades   : {ds['baseline_trades']}")
    for k, v in md["execution_rules"].items():
        p(f"  {k:<20}: {v}")
    p(f"  Regression vs {reg['anchors_source']} (DAY-10 NO CAP):")
    for k, v in reg["anchors"].items():
        p(f"    {k:<18}: anchor={v}  {'OK' if reg['baseline_matches_anchors'][k] else 'MISMATCH'}")
    p(f"  Plain-baseline config checks: {reg['plain_baseline_config']}")
    p(f"  Regression verified: {reg['regression_verified']}")
    p("")
    p("3. METHODOLOGY")
    p(sub)
    p("  Baseline trades are produced by the unchanged multi-symbol runner (default ExecutionConfig). Each trade's")
    p("  price path is read from the SAME frozen 5m cache frame, located by its recorded entry/exit timestamps.")
    p(f"  Path window: {md['path_window']}.")
    p(f"  Timing     : {md['timing']}.")
    p(f"  Outcomes   : {md['outcome_definition']}.")
    p("  Every trade record is re-verified against the bars (entry=T+1 open, SIGNAL_LOW stop rule, target=entry+2R,")
    p("  fill price matches exit reason, R and holding minutes recompute). No counterfactual exit is simulated.")
    p("")
    p("4. MFE / MAE DEFINITIONS & EXIT-BAR SEMANTICS")
    p(sub)
    for k, v in md["exit_bar_convention"].items():
        p(f"  {k:<28}: {v}")
    p(f"  R conversion: {md['r_conversion']}")
    p(f"  Note: {md['mfe_usd_note']}")
    p(f"  Stop exits on a bar whose high also reached the target (STOP_FIRST ambiguity): "
      f"{integ['exit_bar_same_bar_ambiguous_stop_trades']} (engine counter: {integ['same_bar_ambiguity_engine_count']})")
    p(f"  Exit bars that opened beyond the fill (gap-through): {integ['exit_bar_gap_through_trades']}")
    p(f"  Invalid-risk trades (excluded from R stats): {integ['invalid_risk_trades']}")
    p("")
    p("5. EXIT-REASON DECOMPOSITION (PRIMARY)")
    p(sub)
    p(f"  Raw exit reasons: {integ['raw_exit_reasons']}")
    stats_table(res["exit_reason_decomposition"], full_cols)
    p("6. WINNER / LOSER DECOMPOSITION (PRIMARY)")
    p(sub)
    stats_table(res["outcome_decomposition"], full_cols)
    p("7. MFE THRESHOLD ANALYSIS (count / % of group reaching MFE_R >= threshold; descriptive only)")
    p(sub)
    for mode in MODES:
        tbl = res["mfe_thresholds"][mode]
        p(f"  [{mode}]")
        p(f"  {'Group':<14}{'N':>6}" + "".join(f"{'+' + format(t, '.2f') + 'R':>16}" for t in R_THRESHOLDS))
        for g, d in tbl.items():
            p(f"  {g:<14}{d['group_size']:>6}" + "".join(
                f"{d[f'+{t:.2f}R']['count']:>7} ({_fmt(d[f'+{t:.2f}R']['pct'], 1):>5}%)" for t in R_THRESHOLDS))
        p("")
    p("8. LOSERS REACHING POSITIVE EXCURSION BEFORE EXIT")
    p(sub)
    for k, d in res["losers_reaching_positive_excursion"].items():
        p(f"  [{k}] losers={d['losers']}")
        p("    " + "  ".join(f"+{t:.2f}R: {d[f'+{t:.2f}R']['count']} ({_fmt(d[f'+{t:.2f}R']['pct'], 2)}%)" for t in R_THRESHOLDS))
    p("")

    def time_table(title, tbl, vk):
        p(f"  [{title}]")
        p(f"  {'Bin':<14}{'N':>7}{'%':>8}{'avg ' + vk:>12}{'med ' + vk:>12}{'avg final R':>13}")
        for b, d in tbl.items():
            p(f"  {b:<14}{d['count']:>7}{_fmt(d['pct'], 2):>8}{_fmt(d[f'avg_{vk}'], 3):>12}"
              f"{_fmt(d[f'median_{vk}'], 3):>12}{_fmt(d['avg_final_R'], 3):>13}")
        p("")

    p("9. TIME-TO-MFE (PRIMARY)")
    p(sub)
    for k, t in res["time_to_mfe"].items():
        time_table(k, t, "MFE_R")
    p("10. TIME-TO-MAE (PRIMARY)")
    p(sub)
    for k, t in res["time_to_mae"].items():
        time_table(k, t, "MAE_R")
    p("11. HOLDING-TIME ANALYSIS (no causal inference)")
    p(sub)
    stats_table(res["holding_time"], full_cols)
    p("12. MFE vs FINAL R (PRIMARY MFE_R buckets)")
    p(sub)
    stats_table(res["mfe_vs_final_r"], [("N", "count", 6), ("WR", "win_rate", 8), ("PF", "profit_factor", 8),
                                        ("avgR", "avg_R", 8), ("medR", "median_R", 8), ("totR", "total_R", 10)])
    for b, s in res["mfe_vs_final_r"].items():
        if s.get("count"):
            p(f"  {b:<22} exits: {s['exit_counts']}")
    p("  Note: 'MFE < 0R' is empty by construction (the entry open is a path point).")
    p("")
    p("  MFE/|MAE| ratio (MAE_R == 0 -> undefined, reported separately):")
    for g, d in res["mfe_to_mae_ratio"].items():
        p(f"    {g:<8}: {d}")
    p("")
    p("13. RAPID-EXIT ANALYSIS (holding < 15 min)")
    p(sub)
    rcols = [("N", "count", 6), ("WR", "win_rate", 8), ("PF", "profit_factor", 8), ("avgR", "avg_R", 8),
             ("avgMFE_R", "avg_MFE_R", 9), ("medMFE_R", "median_MFE_R", 9), ("avgMAE_R", "avg_MAE_R", 9),
             ("medMAE_R", "median_MAE_R", 9), ("%>=0.5R", "pct_reach_0.5R", 9), ("%>=1R", "pct_reach_1R", 8)]
    stats_table(res["rapid_exit"], rcols)
    for b, s in res["rapid_exit"].items():
        if s.get("count"):
            p(f"  {b:<12} exits: {s['exit_counts']}")
    p("")
    p("14. STOP-DISTANCE ANALYSIS (original SIGNAL_LOW risk / entry; existing DAY-05 buckets)")
    p(sub)
    stats_table(res["stop_distance"], rcols)
    for b, s in res["stop_distance"].items():
        if s.get("count"):
            p(f"  {b:<12} exits: {s['exit_counts']}")
    p("")
    p("15. SYMBOL ROBUSTNESS (not a ranking / selection)")
    p(sub)
    sr = res["symbol_robustness"]
    p(f"  {'Symbol':<8}{'N':>6}{'Losers':>8}{'avgMFE_R':>10}{'avgMAE_R':>10}{'L%>=0.5R':>10}{'L%>=1R':>9}{'totR':>9}")
    for s, d in sr["per_symbol"].items():
        p(f"  {s:<8}{d['trades']:>6}{d['losers']:>8}{_fmt(d['avg_MFE_R'], 3):>10}{_fmt(d['avg_MAE_R'], 3):>10}"
          f"{_fmt(d['loser_pct_reach_0.5R'], 2):>10}{_fmt(d['loser_pct_reach_1R'], 2):>9}{_fmt(d['total_R'], 2):>9}")
    for k, v in sr["summary"].items():
        p(f"  {k:<22}: {v}")
    p("")
    p("16. TIME-OF-DAY CROSS-CHECK (DAY-05 bins on the entry bar; explanatory only, H5 not re-run)")
    p(sub)
    p(f"  {'Bin':<14}{'N':>6}{'avgR':>9}{'avgMFE_R':>10}{'avgMAE_R':>10}{'Losers':>8}{'L%>=0.5R':>10}{'L%>=1R':>9}{'medHold':>9}")
    for b, d in res["time_of_day"].items():
        p(f"  {b:<14}{d['trades']:>6}{_fmt(d['avg_R'], 3):>9}{_fmt(d['avg_MFE_R'], 3):>10}{_fmt(d['avg_MAE_R'], 3):>10}"
          f"{d['losers']:>8}{_fmt(d['loser_pct_reach_0.5R'], 2):>10}{_fmt(d['loser_pct_reach_1R'], 2):>9}"
          f"{_fmt(d['median_hold_minutes'], 1):>9}")
    p("")
    p("17. PIT / DATA INTEGRITY")
    p(sub)
    for k, v in integ.items():
        p(f"  {k}: {v}")
    p("")
    p("18. TESTS")
    p(sub)
    for k, v in res.get("validation", {"note": "validation block not embedded"}).items():
        p(f"  {k}: {v}")
    p("")
    p("19. RESEARCH INTERPRETATION (descriptive; ex-post observation, NOT tradable rule validation)")
    p(sub)
    lr = res["losers_reaching_positive_excursion"]["PRIMARY"]
    lu = res["losers_reaching_positive_excursion"]["UPPER_BOUND"]
    p(f"  Under the PRIMARY convention, {lr['+0.50R']['pct']}% of losing trades reached >= +0.5R and "
      f"{lr['+1.00R']['pct']}% reached >= +1.0R before their exit ({lr['losers']} losers).")
    p(f"  Under the UPPER_BOUND convention the corresponding shares are {lu['+0.50R']['pct']}% and {lu['+1.00R']['pct']}%.")
    rl = res["bar_resolution_limit"]
    mp, mu = rl["multi_bar_losers_PRIMARY"], rl["multi_bar_losers_UPPER_BOUND"]
    p(f"  5m RESOLUTION LIMIT: {rl['single_bar_trades']} trades ({rl['single_bar_pct_of_all']}%) enter and exit within the "
      f"same 5m bar (exits {rl['single_bar_exit_counts']}; {rl['single_bar_losers']} losers).")
    p(f"  {rl['note']}")
    p(f"  Losers with zero PRIMARY MFE: {rl['losers_with_zero_MFE_primary']}. Multi-bar losers ({mp['losers']}): "
      f"PRIMARY >= +0.5R {mp['+0.50R']['pct']}%, >= +1R {mp['+1.00R']['pct']}%; UPPER_BOUND >= +0.5R "
      f"{mu['+0.50R']['pct']}%, >= +1R {mu['+1.00R']['pct']}%.")
    sl = rl["single_bar_losers_UPPER_BOUND"]
    p(f"  Single-bar losers ({sl['losers']}) under UPPER_BOUND: >= +0.5R {sl['+0.50R']['pct']}%, >= +1R "
      f"{sl['+1.00R']['pct']}% (PRIMARY is 0 by construction for single-bar STOP losers).")
    p("  PRIMARY and UPPER_BOUND differ ONLY on the exit bar, so their gap is exit-bar intrabar-ordering")
    p("  uncertainty that 5m bars cannot resolve; it is not a measured favorable excursion.")
    mech = res["mechanism"]
    p(f"  Evidence: {mech['evidence']}")
    p(f"  Criterion: {mech['criterion']}")
    p(f"  DIAGNOSTIC CLASSIFICATION: {mech['status']}")
    p("  This classification does NOT mean the strategy is profitable, nor that BE / trailing / partial exits /")
    p("  a different target would improve results. Any such change requires a separate pre-declared hypothesis")
    p("  and counterfactual backtest.")
    p(bar)
    return "\n".join(L) + "\n"


def rows_to_jsonable(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: (str(v) if isinstance(v, pd.Timestamp) else _nan_none(v)) for k, v in r.items()} for r in rows]


def dumps_results(res: dict[str, Any]) -> str:
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, float):
            return _nan_none(o)
        return o
    return json.dumps(clean(res), indent=2, default=str)
