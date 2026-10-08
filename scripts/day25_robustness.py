"""scripts/day25_robustness.py — DAY-25 Pre-forward Robustness & Universe-Stability Research.

GOVERNANCE CONSTRAINTS (absolute):
  - ZERO forward data acquired, inspected, or calculated (nothing after 2026-10-07).
  - Uses ONLY Stage R (<=2022-12-30) and Stage H (<=2026-06-02) already-frozen snapshots.
  - V2-MOM frozen strategy parameters (lookback=252, skip=21, select=5, weight=0.2) are
    NOT modified; only sensitivity variants are explored and reported.
  - This is a RESEARCH characterization task; no forward simulation is run.
  - Output is written to artifacts/day25/.

Usage:
    python -m scripts.day25_robustness --out artifacts/day25
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

# ── engine imports (frozen v2 code, read-only) ──────────────────────────────
from acquisition.contract import ROOT_DIR
from backtest.v2 import engine as en
from backtest.v2 import metrics as mt
from backtest.v2 import signals as sg
from backtest.v2.data import MarketData, load_stage_h, load_stage_r, tr_index
from backtest.v2.run import Setup, run_family, strategy_config_sha, environment, COSTS

# ── frozen V2-MOM reference parameters ──────────────────────────────────────
MOM_LONG_REF = 252      # §4: frozen
MOM_SKIP_REF = 21       # §4: frozen
SELECT_REF   = 5        # §4: frozen
WEIGHT_REF   = 0.20     # §4: frozen

# ── sensitivity grids (never touching forward data) ─────────────────────────
LOOKBACK_GRID = [126, 189, 252, 315]        # quarters: 2Q, 3Q, 4Q✓, 5Q
SKIP_GRID     = [0, 10, 21, 42]             # 0d, 2w, 1m✓, 2m
SELECT_GRID   = [3, 5, 7, 10]              # portfolios sizes; 5✓ is frozen

COST_BPS = 0.0005   # primary: 5 bps


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _jsonable(o):
    if isinstance(o, (np.floating,)):   return float(o)
    if isinstance(o, (np.integer,)):    return int(o)
    if isinstance(o, np.bool_):         return bool(o)
    raise TypeError(type(o))


def _dump(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, default=_jsonable) + "\n").encode("utf-8")
    path.write_bytes(b)
    import hashlib
    return hashlib.sha256(b).hexdigest()


def _cagr(result: en.Result, n_sessions: int) -> float:
    """Annualised CAGR from equity curve (252-session year)."""
    eq = result.equity
    if not eq or eq[-1] <= 0 or eq[0] <= 0:
        return float("nan")
    return (eq[-1] / eq[0]) ** (252.0 / n_sessions) - 1.0


def _total_return(result: en.Result) -> float:
    eq = result.equity
    if not eq or eq[0] <= 0:
        return float("nan")
    return eq[-1] / eq[0] - 1.0


def _max_dd(result: en.Result) -> float:
    eq = np.array(result.equity)
    if len(eq) < 2:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(np.min(dd))


# ═══════════════════════════════════════════════════════════════════════════
# Custom signal runners (variants; do NOT modify frozen sg module)
# ═══════════════════════════════════════════════════════════════════════════

def mom_targets_variant(tr: np.ndarray, t: int, universe: list[int], tickers: tuple[str, ...],
                        lookback: int, skip: int, n_select: int) -> dict[int, float]:
    """Variant of mom_targets with configurable lookback/skip/select."""
    if t - lookback < 0:
        return {}
    scores = {}
    for j in universe:
        a, b = tr[t - skip, j], tr[t - lookback, j]
        if not (math.isnan(a) or math.isnan(b)):
            scores[j] = a / b - 1.0
    ranked = sorted(scores, key=lambda j: (-scores[j], tickers[j]))
    return {j: WEIGHT_REF for j in ranked[:n_select]}


def run_mom_variant(st: Setup, lookback: int, skip: int, n_select: int,
                    cost: float = COST_BPS) -> en.Result:
    """Run V2-MOM with variant parameters on the same data/segment as `st`."""
    data = st.data
    uni  = [data.col(t) for t in data.universe]
    return en.simulate_targets(
        data,
        lambda t: mom_targets_variant(st.tr, t, uni, data.tickers, lookback, skip, n_select),
        st.month,
        cost,
        st.seg_first,
        st.seg_last,
        f"V2-MOM-L{lookback}-K{skip}-N{n_select}",
    )


def run_b1(st: Setup, cost: float = COST_BPS) -> en.Result:
    """Equal-weight benchmark B1 on the same segment."""
    return run_family(st, "B1", cost)


# ═══════════════════════════════════════════════════════════════════════════
# Study 1: Lookback sensitivity (Stage R, 5 bps)
# ═══════════════════════════════════════════════════════════════════════════

def study_lookback(st_r: Setup, n_r: int, b1_r: en.Result) -> list[dict]:
    rows = []
    for lb in LOOKBACK_GRID:
        res = run_mom_variant(st_r, lookback=lb, skip=MOM_SKIP_REF, n_select=SELECT_REF)
        cagr  = _cagr(res, n_r)
        b1c   = _cagr(b1_r, n_r)
        rows.append({
            "lookback_sessions": lb,
            "skip_sessions":  MOM_SKIP_REF,
            "select_n":       SELECT_REF,
            "is_frozen":      lb == MOM_LONG_REF,
            "cagr_5bps":      cagr,
            "b1_cagr_5bps":   b1c,
            "active_return":  cagr - b1c,
            "total_return":   _total_return(res),
            "max_drawdown":   _max_dd(res),
            "n_trades":       len(res.fills),
            "segment":        "research",
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Study 2: Skip-lag sensitivity (Stage R, 5 bps)
# ═══════════════════════════════════════════════════════════════════════════

def study_skip(st_r: Setup, n_r: int, b1_r: en.Result) -> list[dict]:
    rows = []
    for sk in SKIP_GRID:
        if sk >= MOM_LONG_REF:
            continue   # degenerate: skip >= lookback
        res  = run_mom_variant(st_r, lookback=MOM_LONG_REF, skip=sk, n_select=SELECT_REF)
        cagr = _cagr(res, n_r)
        b1c  = _cagr(b1_r, n_r)
        rows.append({
            "lookback_sessions": MOM_LONG_REF,
            "skip_sessions":  sk,
            "select_n":       SELECT_REF,
            "is_frozen":      sk == MOM_SKIP_REF,
            "cagr_5bps":      cagr,
            "b1_cagr_5bps":   b1c,
            "active_return":  cagr - b1c,
            "total_return":   _total_return(res),
            "max_drawdown":   _max_dd(res),
            "n_trades":       len(res.fills),
            "segment":        "research",
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Study 3: Selection-size sensitivity (Stage R, 5 bps)
# ═══════════════════════════════════════════════════════════════════════════

def study_select(st_r: Setup, n_r: int, b1_r: en.Result) -> list[dict]:
    rows = []
    for ns in SELECT_GRID:
        res  = run_mom_variant(st_r, lookback=MOM_LONG_REF, skip=MOM_SKIP_REF, n_select=ns)
        cagr = _cagr(res, n_r)
        b1c  = _cagr(b1_r, n_r)
        rows.append({
            "lookback_sessions": MOM_LONG_REF,
            "skip_sessions":  MOM_SKIP_REF,
            "select_n":       ns,
            "is_frozen":      ns == SELECT_REF,
            "cagr_5bps":      cagr,
            "b1_cagr_5bps":   b1c,
            "active_return":  cagr - b1c,
            "total_return":   _total_return(res),
            "max_drawdown":   _max_dd(res),
            "n_trades":       len(res.fills),
            "segment":        "research",
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Study 4: Universe-drop stability (Stage R + Stage H combined, 5 bps)
# ═══════════════════════════════════════════════════════════════════════════

def run_mom_drop_universe(st: Setup, drop_ticker: str, n_sessions: int, cost: float = COST_BPS) -> dict:
    """Run V2-MOM with one universe symbol masked out (replaced by NaN prices)."""
    data   = st.data
    tickers = data.tickers
    if drop_ticker not in tickers:
        return {"drop": drop_ticker, "error": "ticker not in universe"}
    j_drop = data.col(drop_ticker)

    # Build masked MarketData: zero out open/close/q/d for dropped symbol
    op_m = data.open.copy();  op_m[:, j_drop] = np.nan
    cl_m = data.close.copy(); cl_m[:, j_drop] = np.nan
    q_m  = data.q.copy();     q_m[:, j_drop]  = 1.0
    d_m  = data.d.copy();     d_m[:, j_drop]  = 0.0
    data_m = MarketData(data.sessions, data.tickers, op_m, cl_m, q_m, d_m)

    tr_m = tr_index(data_m)
    uni  = [data_m.col(t) for t in data_m.universe if t != drop_ticker]

    res  = en.simulate_targets(
        data_m,
        lambda t: mom_targets_variant(tr_m, t, uni, data_m.tickers, MOM_LONG_REF, MOM_SKIP_REF, SELECT_REF),
        st.month, cost, st.seg_first, st.seg_last,
        f"V2-MOM-drop-{drop_ticker}",
    )
    b1_res = run_b1(st, cost)
    cagr   = _cagr(res, n_sessions)
    b1c    = _cagr(b1_res, n_sessions)
    return {
        "drop":          drop_ticker,
        "cagr_5bps":     cagr,
        "b1_cagr_5bps":  b1c,
        "active_return": cagr - b1c,
        "total_return":  _total_return(res),
        "max_drawdown":  _max_dd(res),
        "n_trades":      len(res.fills),
    }


def study_universe_drop(st_r: Setup, n_r: int, full_mom_r: en.Result) -> list[dict]:
    """Leave-one-out universe drop on Stage R data."""
    data     = st_r.data
    universe = [t for t in data.universe]
    b1_res   = run_b1(st_r)
    b1_cagr  = _cagr(b1_res, n_r)
    full_cagr = _cagr(full_mom_r, n_r)
    rows = []
    for ticker in sorted(universe):
        row = run_mom_drop_universe(st_r, ticker, n_r)
        row["full_mom_cagr_5bps"] = full_cagr
        row["delta_vs_full_mom"]  = row["cagr_5bps"] - full_cagr
        row["delta_vs_b1"]        = row["cagr_5bps"] - b1_cagr
        row["segment"]            = "research"
        rows.append(row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Study 5: Rolling factor persistence — active return in 252-session windows
# ═══════════════════════════════════════════════════════════════════════════

def study_rolling_active(st_r: Setup, full_mom_r: en.Result, b1_r: en.Result) -> list[dict]:
    """252-session rolling window of active return (MOM − B1) on Stage R."""
    mom_eq = np.array(full_mom_r.equity)
    b1_eq  = np.array(b1_r.equity)
    sessions = full_mom_r.sessions   # list of ISO date strings
    n = len(mom_eq)
    window = 252
    rows = []
    for i in range(window, n + 1):
        # window: [i-window, i)  -> indices 0-based
        w_start = i - window
        w_end   = i - 1
        m_ret   = mom_eq[w_end] / mom_eq[w_start] - 1.0
        b_ret   = b1_eq[w_end]  / b1_eq[w_start]  - 1.0
        cagr_m  = (mom_eq[w_end] / mom_eq[w_start]) ** (252.0 / window) - 1.0
        cagr_b  = (b1_eq[w_end]  / b1_eq[w_start])  ** (252.0 / window) - 1.0
        rows.append({
            "window_start_session": sessions[w_start],
            "window_end_session":   sessions[w_end],
            "mom_cagr":             cagr_m,
            "b1_cagr":              cagr_b,
            "active_cagr":          cagr_m - cagr_b,
            "mom_total_return":     m_ret,
            "b1_total_return":      b_ret,
            "active_beat":          cagr_m > cagr_b,
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Study 6: Joint research+holdout cross-segment robustness summary
# ═══════════════════════════════════════════════════════════════════════════

def cross_segment_summary(st_r: Setup, n_r: int, full_mom_r: en.Result, b1_r: en.Result,
                          st_h: Setup, n_h: int, full_mom_h: en.Result, b1_h: en.Result) -> dict:
    """Key statistics across both segments for cross-segment robustness assessment."""
    def stats(res, b1, n):
        cagr  = _cagr(res, n)
        b1c   = _cagr(b1, n)
        return {
            "cagr_5bps":     cagr,
            "b1_cagr_5bps":  b1c,
            "active_return": cagr - b1c,
            "total_return":  _total_return(res),
            "max_drawdown":  _max_dd(res),
            "n_trades":      len(res.fills),
            "n_sessions":    n,
        }
    return {
        "research_2017_2022":   stats(full_mom_r, b1_r, n_r),
        "holdout_2023_2026h1":  stats(full_mom_h, b1_h, n_h),
        "combined_observation": {
            "both_segments_beat_b1": (_cagr(full_mom_r, n_r) > _cagr(b1_r, n_r)
                                      and _cagr(full_mom_h, n_h) > _cagr(b1_h, n_h)),
            "total_sessions": n_r + n_h,
            "total_trades_r_plus_h": len(full_mom_r.fills) + len(full_mom_h.fills),
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a  = ap.parse_args(argv)
    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT_DIR / out
    out.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    print(f"[DAY-25] Started {started}")

    # ── Load frozen Stage R data ─────────────────────────────────────────
    print("[DAY-25] Loading Stage R data...")
    data_r, info_r = load_stage_r()
    st_r   = Setup(data_r)
    n_r    = st_r.seg_last - st_r.seg_first + 1   # 1490
    print(f"[DAY-25] Stage R sessions: {n_r} ({data_r.sessions[st_r.seg_first]} .. {data_r.sessions[st_r.seg_last]})")

    # ── Load frozen Stage H data ─────────────────────────────────────────
    print("[DAY-25] Loading Stage H data...")
    from backtest.v2.run import SEGMENTS
    seg_h  = SEGMENTS["holdout"]
    data_h, info_h = load_stage_h()
    st_h   = Setup(data_h, seg_h)
    n_h    = st_h.seg_last - st_h.seg_first + 1   # 856
    print(f"[DAY-25] Stage H sessions: {n_h} ({data_h.sessions[st_h.seg_first]} .. {data_h.sessions[st_h.seg_last]})")

    # ── Run reference (frozen V2-MOM) on Stage R ─────────────────────────
    print("[DAY-25] Running reference V2-MOM on Stage R ...")
    full_mom_r = run_family(st_r, "V2-MOM", COST_BPS)
    b1_r       = run_b1(st_r)

    # ── Run reference (frozen V2-MOM) on Stage H ─────────────────────────
    print("[DAY-25] Running reference V2-MOM on Stage H ...")
    full_mom_h = run_family(st_h, "V2-MOM", COST_BPS)
    b1_h       = run_b1(st_h)

    # ── Study 1: Lookback sensitivity ────────────────────────────────────
    print("[DAY-25] Study 1: Lookback sensitivity ...")
    s1 = study_lookback(st_r, n_r, b1_r)
    _dump(out / "study1_lookback_sensitivity.json", {"description": "Lookback sensitivity on Stage R (5 bps)",
                                                      "fixed": {"skip": MOM_SKIP_REF, "select": SELECT_REF},
                                                      "grid": LOOKBACK_GRID, "rows": s1})

    # ── Study 2: Skip-lag sensitivity ────────────────────────────────────
    print("[DAY-25] Study 2: Skip-lag sensitivity ...")
    s2 = study_skip(st_r, n_r, b1_r)
    _dump(out / "study2_skip_sensitivity.json",     {"description": "Skip-lag sensitivity on Stage R (5 bps)",
                                                      "fixed": {"lookback": MOM_LONG_REF, "select": SELECT_REF},
                                                      "grid": SKIP_GRID, "rows": s2})

    # ── Study 3: Selection-size sensitivity ──────────────────────────────
    print("[DAY-25] Study 3: Selection-size sensitivity ...")
    s3 = study_select(st_r, n_r, b1_r)
    _dump(out / "study3_select_sensitivity.json",   {"description": "Selection-size sensitivity on Stage R (5 bps)",
                                                      "fixed": {"lookback": MOM_LONG_REF, "skip": MOM_SKIP_REF},
                                                      "grid": SELECT_GRID, "rows": s3})

    # ── Study 4: Universe-drop stability ─────────────────────────────────
    print("[DAY-25] Study 4: Universe-drop stability (leave-one-out) ...")
    s4 = study_universe_drop(st_r, n_r, full_mom_r)
    _dump(out / "study4_universe_drop_stability.json", {"description": "Leave-one-out universe drop on Stage R (5 bps)",
                                                         "universe_size": 25,
                                                         "fixed": {"lookback": MOM_LONG_REF, "skip": MOM_SKIP_REF, "select": SELECT_REF},
                                                         "rows": s4})

    # ── Study 5: Rolling factor persistence ──────────────────────────────
    print("[DAY-25] Study 5: Rolling 252-session factor persistence (Stage R) ...")
    s5 = study_rolling_active(st_r, full_mom_r, b1_r)
    beat_pct = sum(1 for r in s5 if r["active_beat"]) / len(s5) * 100 if s5 else 0.0
    _dump(out / "study5_rolling_persistence.json", {"description": "252-session rolling active return on Stage R",
                                                     "window_sessions": 252,
                                                     "pct_windows_beat_b1": round(beat_pct, 2),
                                                     "n_windows": len(s5),
                                                     "rows": s5})

    # ── Study 6: Cross-segment summary ───────────────────────────────────
    print("[DAY-25] Study 6: Cross-segment summary ...")
    s6 = cross_segment_summary(st_r, n_r, full_mom_r, b1_r, st_h, n_h, full_mom_h, b1_h)
    _dump(out / "study6_cross_segment_summary.json", {"description": "Cross-segment robustness: Research vs Holdout",
                                                       "summary": s6})

    # ── Aggregate report ─────────────────────────────────────────────────
    finished = datetime.now(timezone.utc).isoformat()
    report = {
        "schema_version": "1.0",
        "task": "DAY-25",
        "task_description": "V2-MOM Pre-forward Robustness & Universe-Stability Research",
        "governance": {
            "forward_data_accessed": False,
            "strategy_modified": False,
            "segments_used": ["stage_r (2017-02-01..2022-12-30, 1490 sessions)",
                              "stage_h (2023-01-03..2026-06-02, 856 sessions)"],
            "last_allowed_session": "2026-10-07",
            "frozen_mom_config_sha256": "62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0",
        },
        "reference_runs": {
            "research_V2-MOM_5bps_cagr":  _cagr(full_mom_r, n_r),
            "research_B1_5bps_cagr":      _cagr(b1_r, n_r),
            "holdout_V2-MOM_5bps_cagr":   _cagr(full_mom_h, n_h),
            "holdout_B1_5bps_cagr":       _cagr(b1_h, n_h),
        },
        "studies": {
            "study1_lookback": {
                "description": "Lookback sensitivity (126, 189, 252, 315 sessions)",
                "n_variants": len(s1),
                "frozen_beats_b1_count": sum(1 for r in s1 if r["active_return"] > 0),
                "rows_summary": [{k: v for k, v in r.items() if k != "segment"} for r in s1],
            },
            "study2_skip": {
                "description": "Skip-lag sensitivity (0, 10, 21, 42 sessions)",
                "n_variants": len(s2),
                "frozen_beats_b1_count": sum(1 for r in s2 if r["active_return"] > 0),
                "rows_summary": [{k: v for k, v in r.items() if k != "segment"} for r in s2],
            },
            "study3_select": {
                "description": "Selection-size sensitivity (3, 5, 7, 10 stocks)",
                "n_variants": len(s3),
                "frozen_beats_b1_count": sum(1 for r in s3 if r["active_return"] > 0),
                "rows_summary": [{k: v for k, v in r.items() if k != "segment"} for r in s3],
            },
            "study4_universe_drop": {
                "description": "Leave-one-out universe drop stability (25 variants)",
                "n_variants": len(s4),
                "all_beat_b1": all(r["active_return"] > 0 for r in s4 if "error" not in r),
                "all_beat_full_mom": all(r.get("delta_vs_full_mom", 0) >= -0.05 for r in s4 if "error" not in r),
                "min_delta_vs_full_mom": min((r["delta_vs_full_mom"] for r in s4 if "error" not in r), default=None),
                "max_delta_vs_full_mom": max((r["delta_vs_full_mom"] for r in s4 if "error" not in r), default=None),
                "most_impactful_drop": max(s4, key=lambda r: abs(r.get("delta_vs_full_mom", 0)) if "error" not in r else 0),
                "least_impactful_drop": min(s4, key=lambda r: abs(r.get("delta_vs_full_mom", 0)) if "error" not in r else 999),
            },
            "study5_rolling_persistence": {
                "description": "252-session rolling active return on Stage R",
                "n_windows": len(s5),
                "pct_windows_beat_b1": round(beat_pct, 2),
                "min_active_cagr": min((r["active_cagr"] for r in s5), default=None),
                "max_active_cagr": max((r["active_cagr"] for r in s5), default=None),
                "mean_active_cagr": float(np.mean([r["active_cagr"] for r in s5])) if s5 else None,
            },
            "study6_cross_segment": {
                "description": "Research vs Holdout cross-segment summary",
                "summary": s6,
            },
        },
        "environment": environment(),
        "started_utc":  started,
        "finished_utc": finished,
    }
    sha = _dump(out / "day25-robustness-report.json", report)
    print(f"[DAY-25] Report written. SHA-256: {sha}")
    print(f"[DAY-25] Finished: {finished}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
