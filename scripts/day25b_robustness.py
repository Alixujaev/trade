"""scripts/day25b_robustness.py: DAY-25B V2-MOM robustness diagnostics D1-D7 (frozen predeclaration c794bdc).

    python -m scripts.day25b_robustness --out artifacts/day25b/run --authorization "<approval reference>"
    python -m scripts.day25b_robustness --preflight-only --authorization "<approval reference>"

Frozen documents: artifacts/day25b/day25b-robustness-predeclaration.{md,json} (FROZEN — NOT AUTHORIZED TO RUN until a
separate run authorization). Every output is descriptive only: "robustness diagnostic on reused historical data — not
independent or forward evidence". No threshold, pass/fail rule, flag or new statistical test exists here.

- Gates (main): frozen-document SHA-256 (line endings normalised), frozen JSON parameters, V2-MOM config SHA-256,
  network sockets refused, data only via the verifying loaders load_stage_r / load_stage_h (Stage R <= 2022-12-30,
  Stage H <= 2026-06-02; no Excluded or forward data).
- D6 preflight (separate stage, first): recompute the DAY-19/21 0/5/10 bps references with the frozen run_family +
  metrics.compute path and require exact float64 equality of cagr and ending_equity (36 comparisons). The record is
  written write-once to artifacts/day25b/preflight/preflight_record.json, separately from diagnostic results, with
  the environment fingerprint. A differing fingerprint never relaxes equality. Any mismatch raises PreflightMismatch:
  the run aborts, no D1-D7 file is created, and nothing is marked successful. Passing it authorizes nothing.
- A full CLI run does not re-run the preflight: it reuses the existing PASSED record at the frozen path, validated
  read-only (pinned SHA-256, 36/36 exact, no mismatch, not an authorization, frozen commit, environment fingerprint,
  references unchanged), and the re-simulated frozen base runs must reproduce the record exactly before D1-D7.
- Diagnostics are computed fully in memory twice (determinism, frozen §2), then written to a temporary directory and
  renamed into place; an existing output directory is never overwritten.
The frozen engine (backtest/v2/*), universe, snapshots and DAY-19/21 references are imported or read, never modified.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sys

import numpy as np

from acquisition.contract import ROOT_DIR
from backtest.v2 import engine as en
from backtest.v2 import metrics as mt
from backtest.v2 import signals as sg
from backtest.v2.run import (
    PROTOCOL_FILES, SEGMENTS, Setup, _dump, _git, _jsonable, _refuse, environment, run_family, strategy_config_sha,
)
from config.day_universe import FROZEN_DAY_UNIVERSE

# ------------------------------------------------------------------ frozen constants (asserted against the frozen JSON)

FROZEN_COMMIT = "c794bdc58490517b451b81d125a6a41896eb09d9"
FROZEN_MD = "artifacts/day25b/day25b-robustness-predeclaration.md"
FROZEN_JSON = "artifacts/day25b/day25b-robustness-predeclaration.json"
FROZEN_DOC_SHA256 = {FROZEN_MD: "f5b32aed2e31d95feb402a39121f312debb1ad9b8fa344fc9bb708df7b44bfbb",
                     FROZEN_JSON: "c97d3d6804dc17a7da2e14bb1b24499cd44855a617213c004b53c13664ee33ff"}
CONFIG_SHA256 = "62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0"
EVIDENCE_LABEL = "robustness diagnostic on reused historical data — not independent or forward evidence"
DEFAULT_OUT = ROOT_DIR / "artifacts" / "day25b" / "run"
DEFAULT_PREFLIGHT_RECORD = ROOT_DIR / "artifacts" / "day25b" / "preflight" / "preflight_record.json"
# The real standalone D6 preflight (DAY25B-D6-PREFLIGHT-ONLY): PASSED, 36/36 exact. A full run reuses and validates it.
PREFLIGHT_RECORD_SHA256 = "c2e70c47cff4a1a6344b08f256b41c5d02c3c2188a300982d5abb87ff53a501b"
PORTFOLIOS = ("V2-MOM", "B1", "B2")
FIELDS = ("cagr", "ending_equity")


@dataclass(frozen=True)
class Spec:
    """Frozen DAY-25B parameters. Tests may build a synthetic Spec; the real run uses FROZEN_SPEC only."""
    universe: tuple[str, ...]
    seed: int = 20261008
    subset_size: int = 20
    subset_count: int = 300
    costs: dict = field(default_factory=lambda: {"5bps": 0.0005, "10bps": 0.0010})          # primary, secondary
    d6_frozen: dict = field(default_factory=lambda: {"0bps": 0.0, "5bps": 0.0005, "10bps": 0.0010})
    d6_overrides: dict = field(default_factory=lambda: {"15bps": 0.0015, "20bps": 0.0020})
    window: int = 252
    step: int = 21
    expected_windows: dict = field(default_factory=dict)          # segment id -> window count
    year_labels: dict = field(default_factory=dict)               # segment id -> {year: (label, sessions)}
    references: dict = field(default_factory=dict)                # segment id -> {portfolio: dir containing <cost>/metrics.json}
    reference_env_sha256: str = "7b47231b6bf706da340a4c8b940bb5cbd632c228c8f07dc57cde6c065c89379a"


FROZEN_SPEC = Spec(
    universe=tuple(sorted(FROZEN_DAY_UNIVERSE)),
    expected_windows={"research": 59, "holdout": 29},
    year_labels={
        "research": {"2017": ("partial 2017-02-01..2017-12-29", 231), "2018": ("full", 251), "2019": ("full", 252),
                     "2020": ("full", 253), "2021": ("full", 252), "2022": ("full", 251)},
        "holdout": {"2023": ("full", 250), "2024": ("full", 252), "2025": ("full", 250),
                    "2026": ("partial 2026-01-02..2026-06-02", 104)},
    },
    references={
        "research": {"V2-MOM": "artifacts/day19/v2/V2-MOM-R001", "B1": "artifacts/day19/v2/V2-B1-research",
                     "B2": "artifacts/day19/v2/V2-B2-research"},
        "holdout": {"V2-MOM": "artifacts/day21/v2/V2-MOM-H001", "B1": "artifacts/day21/v2/V2-B1-holdout",
                    "B2": "artifacts/day21/v2/V2-B2-holdout"},
    },
)


class Day25bError(RuntimeError):
    """A gate, consistency or write-once check failed; nothing is marked successful."""


class PreflightMismatch(Day25bError):
    """D6 integrity preflight failed: the entire DAY-25B run aborts and no D1-D7 output is created."""


# ------------------------------------------------------------------ gates

def doc_sha256(path: Path) -> str:
    """SHA-256 of a frozen text document with CRLF normalised to LF (the committed blob is LF)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_frozen_docs(root: Path = ROOT_DIR) -> dict[str, str]:
    got = {p: doc_sha256(root / p) for p in FROZEN_DOC_SHA256}
    bad = sorted(p for p in got if got[p] != FROZEN_DOC_SHA256[p])
    if bad:
        raise Day25bError(f"frozen DAY-25B document changed: {bad}")
    return got


def verify_frozen_json(spec: Spec = FROZEN_SPEC, root: Path = ROOT_DIR) -> None:
    j = json.loads((root / FROZEN_JSON).read_text(encoding="utf-8"))
    d = j["diagnostics"]
    rc = d["D6_cost_sensitivity_and_overrides"]["reproduction_check"]
    checks = {
        "status": j["status"] == "FROZEN_NOT_AUTHORIZED_TO_RUN",
        "config": j["frozen_config_sha256"] == CONFIG_SHA256,
        "universe": tuple(j["universe_order"]) == spec.universe,
        "seed": d["D3_random_subsets"]["seed"] == spec.seed,
        "subset_size": d["D3_random_subsets"]["subset_size"] == spec.subset_size,
        "subset_count": d["D3_random_subsets"]["count"] == spec.subset_count,
        "costs": [j["costs"]["primary"], j["costs"]["secondary"]] == list(spec.costs.values()),
        "d6_frozen": j["costs"]["d6_frozen_scenarios"] == list(spec.d6_frozen.values()),
        "d6_overrides": j["costs"]["d6_diagnostic_overrides"] == list(spec.d6_overrides.values()),
        "window": d["D4b_rolling_window"]["window_sessions"] == spec.window and d["D4b_rolling_window"]["step_sessions"] == spec.step,
        "window_counts": d["D4b_rolling_window"]["window_count"] == spec.expected_windows,
        "reference_env": rc["reference_environment"]["distributions_sha256"] == spec.reference_env_sha256,
        "no_relaxation": rc["equality_relaxation"]["automatic"] is False,
    }
    bad = sorted(k for k, ok in checks.items() if not ok)
    if bad:
        raise Day25bError(f"implementation constants differ from the frozen JSON: {bad}")


def assert_config_sha(root: Path = ROOT_DIR) -> str:
    protocol = json.loads((root / PROTOCOL_FILES[1]).read_text(encoding="utf-8"))
    sha = strategy_config_sha(protocol, "V2-MOM")
    if sha != CONFIG_SHA256:
        raise Day25bError(f"V2-MOM config SHA-256 {sha} != frozen {CONFIG_SHA256}")
    return sha


# ------------------------------------------------------------------ D3 subset generator (frozen algorithm)

def generate_subsets(universe: tuple[str, ...], seed: int, k: int, count: int) -> tuple[list[tuple[str, ...]], int]:
    """PCG64(seed); per draw one random_raw() uint64 key per ticker in universe order; keep the k smallest keys
    (ties by universe order); discard a set already accepted; stop at `count` distinct subsets.
    Keys stay Python ints (unsigned 64-bit values); they are never cast to a signed type."""
    if not 0 < k <= len(universe) or count > math.comb(len(universe), k):
        raise Day25bError("impossible subset specification")
    bitgen = np.random.PCG64(seed)
    seen: set[frozenset] = set()
    out: list[tuple[str, ...]] = []
    discards = 0
    while len(out) < count:
        keys = [int(bitgen.random_raw()) for _ in universe]
        chosen = sorted(sorted(range(len(universe)), key=lambda i: (keys[i], i))[:k])
        sub = tuple(universe[i] for i in chosen)
        if frozenset(sub) in seen:
            discards += 1
            continue
        seen.add(frozenset(sub))
        out.append(sub)
    return out, discards


# ------------------------------------------------------------------ simulation primitives (frozen engine, unchanged)

def run_mom(st: Setup, tickers, s: float) -> en.Result:
    """Frozen V2-MOM with the ranking universe restricted to `tickers` (prices are not masked)."""
    data = st.data
    uni = [data.col(t) for t in tickers]
    return en.simulate_targets(data, lambda t: sg.mom_targets(st.tr, t, uni, data.tickers), st.month, s,
                               st.seg_first, st.seg_last, "V2-MOM")


def run_b1_sub(st: Setup, tickers, s: float) -> en.Result:
    """B1 rule of run.run_family restricted to `tickers`: equal weight over those with a bar at the first open."""
    data = st.data
    have = [data.col(t) for t in tickers if not math.isnan(data.open[st.seg_first, data.col(t)])]
    if not have:
        raise Day25bError("B1-sub has no symbol with a bar at the segment's first open")
    return en.simulate_targets(data, lambda t: {j: 1.0 / len(have) for j in have}, [st.seg_first - 1], s,
                               st.seg_first, st.seg_last, "B1")


def run_single(st: Setup, ticker: str, s: float) -> en.Result | None:
    """B2 rule applied to one symbol; None when it has no bar at the first open (reported as undefined)."""
    data = st.data
    j = data.col(ticker)
    if math.isnan(data.open[st.seg_first, j]):
        return None
    return en.simulate_targets(data, lambda t: {j: 1.0}, [st.seg_first - 1], s, st.seg_first, st.seg_last, ticker)


def cagr_of(res: en.Result) -> float:
    return mt.cagr(res.equity[-1], len(res.equity))


def mdd_of(res: en.Result) -> float:
    return mt._mdd(np.array([en.E0] + list(res.equity)))


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, allow_nan=False, default=_jsonable).encode("utf-8")


def _stats(xs) -> dict:
    a = np.asarray(xs, dtype=np.float64)
    return {"n": int(a.size), "mean": float(a.mean()), "median": float(np.median(a)),
            "p5": float(np.percentile(a, 5, method="linear")), "p95": float(np.percentile(a, 95, method="linear")),
            "min": float(a.min()), "max": float(a.max()), "fraction_gt_0": float(np.mean(a > 0))}


def _argmin_first(vals: list[float]) -> int:
    """Index of the minimum; ties resolved to the earliest position (universe order / chronological)."""
    return min(range(len(vals)), key=lambda i: (vals[i], i))


# ------------------------------------------------------------------ D6 integrity preflight (separate stage, first)

def preflight(contexts: dict[str, Setup], spec: Spec, record_path: Path, ref_root: Path = ROOT_DIR) -> dict:
    """Recompute the 0/5/10 bps references; exact equality of cagr and ending_equity or abort.
    Returns {segment: {cost: {portfolio: Result}}} on success. Writes the record write-once in every case."""
    record_path = Path(record_path)
    if record_path.exists():
        raise Day25bError(f"preflight record already exists, refusing to overwrite: {record_path}")
    runs: dict = {}
    comparisons: list[dict] = []
    error: Exception | None = None
    try:
        for seg_id, st in contexts.items():
            runs[seg_id] = {}
            for c, s in spec.d6_frozen.items():
                res = {f: run_family(st, f, s) for f in PORTFOLIOS}
                runs[seg_id][c] = res
                got = {"V2-MOM": mt.compute(res["V2-MOM"], res["B1"], res["B2"]),
                       "B1": mt.compute(res["B1"], None, None), "B2": mt.compute(res["B2"], None, None)}
                for f in PORTFOLIOS:
                    ref_file = Path(ref_root) / spec.references[seg_id][f] / c / "metrics.json"
                    ref = json.loads(ref_file.read_text(encoding="utf-8"))
                    for name in FIELDS:
                        r, g = ref.get(name), got[f][name]
                        equal = isinstance(r, float) and isinstance(g, float) and r == g      # exact float64, no tolerance
                        comparisons.append({"segment": seg_id, "cost": c, "portfolio": f, "field": name,
                                            "reference_file": str(Path(spec.references[seg_id][f]) / c / "metrics.json"),
                                            "reference": r, "recomputed": g, "equal": equal})
    except Exception as exc:                       # reference load/parse, simulation or metric failure: record, then abort
        error = exc
    env = environment()
    mismatches = [x for x in comparisons if not x["equal"]]
    passed = (error is None and not mismatches
              and len(comparisons) == len(contexts) * len(spec.d6_frozen) * len(PORTFOLIOS) * len(FIELDS))
    record = {
        "task": "DAY-25B", "stage": "D6 integrity preflight", "status": "PASSED" if passed else "FAILED",
        "frozen_commit": FROZEN_COMMIT, "equality": "exact float64 (==); no tolerance, rounding or re-baselining",
        "comparisons_total": len(comparisons), "mismatch_count": len(mismatches), "mismatches": mismatches,
        "comparisons": comparisons,
        "environment": env, "reference_environment_distributions_sha256": spec.reference_env_sha256,
        "fingerprint_matches_reference": env["distributions_sha256"] == spec.reference_env_sha256,
        "fingerprint_relaxes_equality": False,
        "authorizes_diagnostics": False,
        "run_status": None if passed else "ABORTED_PREFLIGHT_MISMATCH",
        "error": None if error is None else {"type": type(error).__name__, "message": str(error)},
        "written_utc": datetime.now(timezone.utc).isoformat(),
    }
    _dump(record_path, record)
    if error is not None:
        raise PreflightMismatch(f"D6 preflight raised {type(error).__name__}: {error}; DAY-25B aborted "
                                f"(record: {record_path})") from error
    if not passed:
        raise PreflightMismatch(f"D6 preflight: {len(mismatches)} of {len(comparisons)} comparisons differ; "
                                f"DAY-25B aborted (record: {record_path})")
    return runs


def validate_preflight_record(record_path: Path, expected_sha256: str, spec: Spec,
                              expected_path: Path = DEFAULT_PREFLIGHT_RECORD, ref_root: Path = ROOT_DIR) -> dict:
    """Read-only validation of an existing PASSED preflight record before it is reused (never written, never
    treated as authorization). Any failure raises Day25bError; the preflight is never re-run automatically."""
    record_path = Path(record_path)
    if record_path.resolve() != Path(expected_path).resolve():
        raise Day25bError(f"preflight record path {record_path} is not the frozen path {expected_path}")
    if not record_path.is_file():
        raise Day25bError(f"preflight record missing: {record_path}")
    raw = record_path.read_bytes()
    sha = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()         # CRLF normalised to LF, as doc_sha256() does
    if sha != expected_sha256:
        raise Day25bError(f"preflight record SHA-256 {sha} != expected {expected_sha256}")
    try:
        rec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise Day25bError(f"preflight record is not valid JSON: {e}") from None
    expected_keys = {(seg, c, f, name) for seg in spec.references for c in spec.d6_frozen for f in PORTFOLIOS for name in FIELDS}
    comps = rec.get("comparisons") if isinstance(rec, dict) else None
    if not isinstance(comps, list) or not all(isinstance(c, dict) for c in comps):
        raise Day25bError("preflight record has no valid comparison list")
    keys = [(c.get("segment"), c.get("cost"), c.get("portfolio"), c.get("field")) for c in comps]
    env = environment()
    checks = {
        "task": rec.get("task") == "DAY-25B",
        "status_passed": rec.get("status") == "PASSED",
        "run_status_none": rec.get("run_status") is None,
        "no_error": rec.get("error") is None,
        "comparison_count": rec.get("comparisons_total") == len(comps) == len(expected_keys),
        "comparison_keys": len(set(keys)) == len(keys) and set(keys) == expected_keys,
        "no_mismatch": rec.get("mismatch_count") == 0 and rec.get("mismatches") == [],
        "all_equal": all(c.get("equal") is True and isinstance(c.get("reference"), float)
                         and isinstance(c.get("recomputed"), float) and c["reference"] == c["recomputed"] for c in comps),
        "reference_files": set(keys) == expected_keys and all(
            c.get("reference_file") == str(Path(spec.references[c["segment"]][c["portfolio"]]) / c["cost"] / "metrics.json")
            for c in comps),
        "not_authorization": rec.get("authorizes_diagnostics") is False,
        "no_relaxation": rec.get("fingerprint_relaxes_equality") is False,
        "frozen_commit": rec.get("frozen_commit") == FROZEN_COMMIT,
        "reference_env": rec.get("reference_environment_distributions_sha256") == spec.reference_env_sha256,
        "record_env": (rec.get("environment") or {}).get("distributions_sha256") == spec.reference_env_sha256,
        "current_env": env["distributions_sha256"] == spec.reference_env_sha256,
        "fingerprint_matched": rec.get("fingerprint_matches_reference") is True,
    }
    bad = sorted(k for k, ok in checks.items() if not ok)
    if bad:
        raise Day25bError(f"preflight record failed validation: {bad}")
    for c in comps:                                # historical references unchanged since the preflight
        try:
            ref = json.loads((Path(ref_root) / c["reference_file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Day25bError(f"reference {c['reference_file']} unreadable: {e}") from None
        if ref.get(c["field"]) != c["reference"]:
            raise Day25bError(f"reference {c['reference_file']} {c['field']} changed since the preflight")
    return {"record": rec, "sha256": sha}


# ------------------------------------------------------------------ diagnostics (pure, in memory)

def _base_metrics(runs_c: dict) -> dict:
    return mt.compute(runs_c["V2-MOM"], runs_c["B1"], runs_c["B2"])


def d1(st, spec, base) -> dict:
    out = {}
    for c, s in spec.costs.items():
        b1_full = cagr_of(base[c]["B1"])
        rows = []
        for x in spec.universe:
            u = [t for t in spec.universe if t != x]
            res, b1s = run_mom(st, u, s), run_b1_sub(st, u, s)
            m = mt.compute(res, None, None)
            rows.append({"dropped": x, "cagr": m["cagr"], "b1_sub_cagr": cagr_of(b1s),
                         "active_vs_b1_sub": m["cagr"] - cagr_of(b1s), "active_vs_b1": m["cagr"] - b1_full,
                         "max_drawdown": m["max_drawdown"], "top2_concentration": m["top2_concentration"],
                         "weight_hhi": m["weight_hhi"]})
        prim = [r["active_vs_b1_sub"] for r in rows]
        sec = [r["active_vs_b1"] for r in rows]
        out[c] = {"rows": rows, "summary": {
            "active_vs_b1_sub": {"min": min(prim), "median": float(np.median(prim)), "max": max(prim),
                                 "count_gt_0": sum(v > 0 for v in prim), "min_dropped": rows[_argmin_first(prim)]["dropped"]},
            "active_vs_b1": {"min": min(sec), "median": float(np.median(sec)), "max": max(sec),
                             "count_gt_0": sum(v > 0 for v in sec), "min_dropped": rows[_argmin_first(sec)]["dropped"]}}}
    return out


def d2_ranking(spec, base) -> list[dict]:
    """Top 2 by |flows| of the frozen full-universe primary-cost run; never-held symbols have no flow (0)."""
    flows = base[next(iter(spec.costs))]["V2-MOM"].flows
    vals = {t: float(flows.get(t, 0.0)) for t in spec.universe}
    absum = sum(abs(v) for v in vals.values())
    order = sorted(spec.universe, key=lambda t: (-abs(vals[t]), spec.universe.index(t)))
    return [{"ticker": t, "signed_contribution": vals[t],
             "share_of_abs_pnl": abs(vals[t]) / absum if absum > 0 else mt.undefined("no P&L contribution")}
            for t in order[:2]]


def d2(st, spec, base) -> dict:
    top2 = d2_ranking(spec, base)
    removed = {r["ticker"] for r in top2}
    u = [t for t in spec.universe if t not in removed]
    per_cost = {}
    for c, s in spec.costs.items():
        res, b1s = run_mom(st, u, s), run_b1_sub(st, u, s)
        m = mt.compute(res, None, None)
        per_cost[c] = {"cagr": m["cagr"], "b1_sub_cagr": cagr_of(b1s), "active_vs_b1_sub": m["cagr"] - cagr_of(b1s),
                       "active_vs_b1": m["cagr"] - cagr_of(base[c]["B1"]), "max_drawdown": m["max_drawdown"],
                       "top2_concentration": m["top2_concentration"]}
    return {"ranking_cost": next(iter(spec.costs)), "removed": top2, "same_symbols_at_all_costs": True,
            "outcome_dependent": True,
            "note": "selection is outcome-dependent by construction; a stress test, not an estimate of expected performance",
            "per_cost": per_cost}


def d3(st, spec, base, subsets) -> dict:
    out = {}
    for c, s in spec.costs.items():
        b1_full = cagr_of(base[c]["B1"])
        rows = []
        for n, u in enumerate(subsets, start=1):
            res, b1s = run_mom(st, u, s), run_b1_sub(st, u, s)
            cg = cagr_of(res)
            rows.append({"subset": n, "tickers": list(u), "cagr": cg, "b1_sub_cagr": cagr_of(b1s),
                         "active_vs_b1_sub": cg - cagr_of(b1s), "active_vs_b1": cg - b1_full})
        out[c] = {"rows": rows, "summary": {k: _stats([r[k] for r in rows]) for k in ("active_vs_b1_sub", "active_vs_b1", "cagr")}}
    return out


def d4(st, spec, base) -> dict:
    seg_id = st.seg["id"]
    out = {}
    for c in spec.costs:
        mom, b1 = base[c]["V2-MOM"], base[c]["B1"]
        sessions = mom.sessions
        cy = _base_metrics(base[c])["calendar_years"]
        labels = spec.year_labels[seg_id]
        if sorted(cy) != sorted(labels):
            raise Day25bError(f"{seg_id}: calendar years {sorted(cy)} != frozen {sorted(labels)}")
        d4a = {}
        for y in sorted(cy):
            label, n_frozen = labels[y]
            if cy[y]["sessions"] != n_frozen:
                raise Day25bError(f"{seg_id} {y}: {cy[y]['sessions']} sessions != frozen {n_frozen}")
            d4a[y] = {"label": label, "sessions": n_frozen, "return": cy[y]["return"], "b1_return": cy[y]["b1_return"],
                      "b2_return": cy[y]["b2_return"], "active_vs_b1": cy[y]["return"] - cy[y]["b1_return"]}
        r, rb = mt.returns(mom), mt.returns(b1)
        n = len(r)
        starts = list(range(0, n - spec.window + 1, spec.step))
        if seg_id in spec.expected_windows and len(starts) != spec.expected_windows[seg_id]:
            raise Day25bError(f"{seg_id}: {len(starts)} windows != frozen {spec.expected_windows[seg_id]}")
        act = [float(np.prod(1 + r[i:i + spec.window]) - np.prod(1 + rb[i:i + spec.window])) for i in starts]
        i_min = _argmin_first(act)                         # earliest window on ties (chronological)
        d4b = {"window_sessions": spec.window, "step_sessions": spec.step, "count": len(act),
               "min": min(act), "median": float(np.median(act)), "max": max(act),
               "fraction_gt_0": float(np.mean(np.asarray(act) > 0)), "min_window_start": sessions[starts[i_min]],
               "windows": [{"start": sessions[i], "active_total_return_diff": a} for i, a in zip(starts, act)],
               "note": "total-return difference over equal-length windows, not annualised; windows overlap"}
        d4c = {}
        for y in sorted(cy):
            keep = np.array([not s_.startswith(y) for s_ in sessions])
            nk = int(keep.sum())
            if nk == 0:                                    # segment is a single calendar year (never for R/H)
                d4c[y] = {"cagr_excl": mt.undefined("no session remains"), "sessions_remaining": 0,
                          "method": "splice (no re-simulation)"}
                continue
            cs = float(np.prod(1 + r[keep]) ** (252 / nk) - 1)
            cb = float(np.prod(1 + rb[keep]) ** (252 / nk) - 1)
            d4c[y] = {"cagr_excl": cs, "b1_cagr_excl": cb, "active_vs_b1": cs - cb, "sessions_remaining": nk,
                      "method": "splice (no re-simulation)"}
        out[c] = {"D4a_calendar_year": d4a, "D4b_rolling_window": d4b, "D4c_leave_one_year_out": d4c}
    return out


def d5(st, spec, base) -> dict:
    out = {}
    for c in spec.costs:
        m = _base_metrics(base[c])
        flows = base[c]["V2-MOM"].flows
        absum = sum(abs(v) for v in flows.values())
        ranked = sorted((abs(v) for v in flows.values()), reverse=True)
        pos = sorted((v for v in flows.values() if v > 0), reverse=True)
        hhi = m["weight_hhi"]
        out[c] = {"flows_signed": dict(sorted(flows.items())),
                  "top_k_share_of_abs_pnl": {str(k): (sum(ranked[:k]) / absum if absum > 0 else mt.undefined("no P&L"))
                                             for k in range(1, 6)},
                  "top2_concentration": m["top2_concentration"], "weight_hhi": hhi,
                  "inverse_weight_hhi": 1.0 / hhi if isinstance(hhi, float) and hhi > 0 else mt.undefined("undefined HHI"),
                  "symbol_breadth": m["symbol_breadth"],
                  "top2_positive_share_of_positive_pnl": (sum(pos[:2]) / sum(pos) if pos
                                                          else mt.undefined("no positive contributor"))}
    return out


def d6(st, spec, frozen_runs) -> dict:
    seg_runs = dict(frozen_runs)
    for c, s in spec.d6_overrides.items():
        seg_runs[c] = {f: run_family(st, f, s) for f in PORTFOLIOS}
    cagr0 = cagr_of(seg_runs["0bps"]["V2-MOM"])
    out = {}
    for c in list(spec.d6_frozen) + list(spec.d6_overrides):
        m = _base_metrics(seg_runs[c])
        out[c] = {"role": "frozen scenario (recomputed, verified by preflight)" if c in spec.d6_frozen else "diagnostic override",
                  "cagr": m["cagr"], "b1_cagr": m["b1_cagr"], "b2_cagr": m["b2_cagr"], "active_vs_b1": m["cagr_minus_b1"],
                  "total_costs": m["total_costs"], "cost_drag_vs_0bps": cagr0 - m["cagr"],
                  "annual_turnover": m["annual_turnover"], "mean_lambda": m["mean_lambda"], "min_lambda": m["min_lambda"]}
    return out


def d7(st, spec, base) -> dict:
    out = {}
    for c, s in spec.costs.items():
        mom_cagr = cagr_of(base[c]["V2-MOM"])
        rows, defined = [], []
        for t in spec.universe:
            res = run_single(st, t, s)
            if res is None:
                rows.append({"ticker": t, "cagr": mt.undefined("no bar at first open")})
                continue
            cg = cagr_of(res)
            defined.append(cg)
            rows.append({"ticker": t, "cagr": cg, "max_drawdown": mdd_of(res)})
        others = defined + [cagr_of(base[c]["B1"]), cagr_of(base[c]["B2"])]
        out[c] = {"rows": rows, "v2mom_cagr": mom_cagr,
                  "v2mom_rank_among_singles_b1_b2": 1 + sum(x > mom_cagr for x in others),
                  "candidates_ranked": len(others) + 1,
                  "count_single_stocks_above_v2mom": sum(x > mom_cagr for x in defined),
                  "note": "hindsight comparator; supplemental; no decision role; never replaces B1 or B2"}
    return out


def compute_diagnostics(contexts: dict[str, Setup], spec: Spec, frozen_runs: dict, subsets) -> dict:
    """All D1-D7 results in memory; nothing is written. Requires a passed preflight (frozen_runs)."""
    out: dict = {k: {} for k in ("D1", "D2", "D3", "D4", "D5", "D6", "D7")}
    for seg_id, st in contexts.items():
        base = {c: frozen_runs[seg_id][c] for c in spec.costs}
        out["D1"][seg_id] = d1(st, spec, base)
        out["D2"][seg_id] = d2(st, spec, base)
        out["D3"][seg_id] = d3(st, spec, base, subsets)
        out["D4"][seg_id] = d4(st, spec, base)
        out["D5"][seg_id] = d5(st, spec, base)
        out["D6"][seg_id] = d6(st, spec, frozen_runs[seg_id])
        out["D7"][seg_id] = d7(st, spec, base)
    return out


# ------------------------------------------------------------------ orchestration

def run(contexts: dict[str, Setup], spec: Spec, out_dir: Path, record_path: Path, authorization: str,
        ref_root: Path = ROOT_DIR, extra_repro: dict | None = None, reuse_preflight_sha256: str | None = None,
        expected_record_path: Path = DEFAULT_PREFLIGHT_RECORD) -> dict:
    """Preflight first; only on PASS compute D1-D7 twice (determinism) and write them atomically to out_dir.
    With reuse_preflight_sha256, the existing PASSED record is validated read-only instead of re-running the
    preflight, and the re-simulated frozen base runs must reproduce its recomputed values exactly."""
    out_dir = Path(out_dir)
    if not authorization:
        raise Day25bError("a separate, explicit run authorization is required")
    if out_dir.exists():
        raise Day25bError(f"output directory already exists, refusing to overwrite: {out_dir}")
    for seg_id, st in contexts.items():
        if tuple(st.data.universe) != spec.universe:
            raise Day25bError(f"{seg_id}: data universe differs from the frozen universe order")
    if reuse_preflight_sha256 is None:
        frozen_runs = preflight(contexts, spec, record_path, ref_root)      # raises PreflightMismatch: no outputs
        record_sha256 = hashlib.sha256(Path(record_path).read_bytes()).hexdigest()   # just written by _dump: LF, no CRLF
    else:
        validated = validate_preflight_record(record_path, reuse_preflight_sha256, spec, expected_record_path, ref_root)
        record_sha256 = validated["sha256"]                                 # the canonical hash actually validated
        frozen_runs = preflight_runs_again(contexts, spec)
        recomputed = {(c["segment"], c["cost"], c["portfolio"], c["field"]): c["recomputed"]
                      for c in validated["record"]["comparisons"]}
        for seg_id, per_cost in frozen_runs.items():                       # base runs must equal the record exactly
            for c, res in per_cost.items():
                got = {"V2-MOM": mt.compute(res["V2-MOM"], res["B1"], res["B2"]),
                       "B1": mt.compute(res["B1"], None, None), "B2": mt.compute(res["B2"], None, None)}
                for f in PORTFOLIOS:
                    for name in FIELDS:
                        if got[f][name] != recomputed[(seg_id, c, f, name)]:
                            raise Day25bError(f"base run {seg_id} {c} {f} {name} differs from the preflight record")
    subsets, discards = generate_subsets(spec.universe, spec.seed, spec.subset_size, spec.subset_count)
    first = compute_diagnostics(contexts, spec, frozen_runs, subsets)
    second = compute_diagnostics(contexts, spec, preflight_runs_again(contexts, spec), subsets)
    if _canon(first) != _canon(second):
        raise Day25bError("determinism check failed: two in-process runs differ; no output written")
    subsets_doc = {"seed": spec.seed, "subset_size": spec.subset_size, "count": spec.subset_count,
                   "discards": discards, "numpy": np.__version__, "universe_order": list(spec.universe),
                   "subsets": [list(u) for u in subsets]}
    tmp = out_dir.parent / f".{out_dir.name}.tmp-{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        files = {"subsets.json": _dump(tmp / "subsets.json", subsets_doc)}
        for key, val in first.items():
            files[f"{key.lower()}.json"] = _dump(tmp / f"{key.lower()}.json",
                                                 {"diagnostic": key, "evidence_label": EVIDENCE_LABEL,
                                                  "descriptive_only": True, "results": val})
        summary = {
            "task": "DAY-25B", "status": "COMPLETED", "evidence_label": EVIDENCE_LABEL, "descriptive_only": True,
            "decision_rules": "none (F1-F5 withdrawn); no output changes V2-MOM status",
            "authorization": authorization, "segments": {k: {"first": v.seg["first"].isoformat(), "last": v.seg["last"].isoformat(),
                                                             "sessions": v.seg_last - v.seg_first + 1} for k, v in contexts.items()},
            "preflight_record": {"path": str(record_path), "sha256": record_sha256,
                                 "reused": reuse_preflight_sha256 is not None, "validated": True},
            "determinism_in_process": True,
            "reproducibility": {"frozen_commit": FROZEN_COMMIT, "config_sha256": CONFIG_SHA256, "seed": spec.seed,
                                "numpy": np.__version__, "subsets_sha256": files["subsets.json"]} | (extra_repro or {}),
            "result_files_sha256": files,
        }
        _dump(tmp / "run_summary.json", summary)
        os.replace(tmp, out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return summary


def preflight_runs_again(contexts: dict[str, Setup], spec: Spec) -> dict:
    """Independent re-simulation of the frozen 0/5/10 bps runs for the second (determinism) pass."""
    return {seg_id: {c: {f: run_family(st, f, s) for f in PORTFOLIOS} for c, s in spec.d6_frozen.items()}
            for seg_id, st in contexts.items()}


def load_contexts() -> tuple[dict[str, Setup], dict]:
    """Real Stage R / Stage H data via the verifying loaders (historical only). Called only by main()."""
    contexts, infos = {}, {}
    for seg_id in ("research", "holdout"):
        seg = SEGMENTS[seg_id]
        data, info = seg["loader"]()
        st = Setup(data, seg)
        if st.seg_last - st.seg_first + 1 != seg["sessions"] or st.seg_first != seg["inputs_before"]:
            raise Day25bError(f"{seg_id}: session count mismatch")
        contexts[seg_id], infos[seg_id] = st, {k: info[k] for k in ("snapshot_id", "manifest_sha256", "tree_sha256",
                                                                      "first_session", "last_session")}
    return contexts, infos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--preflight-record", type=Path, default=DEFAULT_PREFLIGHT_RECORD)
    ap.add_argument("--preflight-only", action="store_true", help="run only the D6 integrity preflight")
    ap.add_argument("--authorization", default="", help="reference of the explicit run authorization (required)")
    a = ap.parse_args(argv)
    if not a.authorization.strip():
        print("REFUSED: --authorization is required; no data was loaded", file=sys.stderr)
        return 2
    out = (a.out if a.out.is_absolute() else ROOT_DIR / a.out).resolve()
    record = (a.preflight_record if a.preflight_record.is_absolute() else ROOT_DIR / a.preflight_record).resolve()
    if out != DEFAULT_OUT.resolve() or record.parent != DEFAULT_PREFLIGHT_RECORD.parent.resolve():
        print(f"REFUSED: outputs must be {DEFAULT_OUT} and a record under {DEFAULT_PREFLIGHT_RECORD.parent} "
              "(frozen §2 isolation); no data was loaded", file=sys.stderr)
        return 2
    if not a.preflight_only and record != DEFAULT_PREFLIGHT_RECORD.resolve():
        print(f"REFUSED: a full run reuses only the frozen preflight record {DEFAULT_PREFLIGHT_RECORD}; "
              "no data was loaded", file=sys.stderr)
        return 2
    socket.socket.connect = _refuse
    try:
        docs = verify_frozen_docs()
        verify_frozen_json()
        assert_config_sha()
        contexts, infos = load_contexts()
        if a.preflight_only:
            preflight(contexts, FROZEN_SPEC, record)
            print(f"PREFLIGHT PASSED (record: {record}); this authorizes no diagnostic")
            return 0
        summary = run(contexts, FROZEN_SPEC, out, record, a.authorization,
                      extra_repro={"frozen_doc_sha256": docs, "data": infos, "git_commit": _git("rev-parse", "HEAD"),
                                   "environment": environment(),
                                   "engine_sha256": {f"backtest/v2/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest()
                                                     for p in sorted((ROOT_DIR / "backtest" / "v2").glob("*.py"))}},
                      reuse_preflight_sha256=PREFLIGHT_RECORD_SHA256)
    except PreflightMismatch as e:
        print(f"ABORTED_PREFLIGHT_MISMATCH: {e}", file=sys.stderr)
        return 1
    except Day25bError as e:
        print(f"DAY-25B ABORTED: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"status": summary["status"], "out": str(out)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
