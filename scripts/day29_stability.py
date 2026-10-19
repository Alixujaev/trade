"""scripts/day29_stability.py: DAY-29 V2-MOM active-day and ticker-recurrence stability diagnostics
(frozen predeclaration 06fc45f, artifacts/day29/day29-stability-predeclaration.md — FROZEN, NOT AUTHORIZED TO RUN until a
separate run authorization).

    .venv/Scripts/python.exe -m scripts.day29_stability --authorization "<approval reference>"

Every output is descriptive only: "robustness diagnostic on reused historical data — not independent or forward
evidence". No threshold, pass/fail rule, flag or statistical test exists here. Inputs are the committed DAY-19/DAY-21
run artifacts (frozen §2) only; nothing is re-simulated and no market data is read.

- Gates (main): frozen-document SHA-256 (LF-normalised, §14), explicit authorization, network sockets refused.
- Shared stage S1-S9 (frozen §4, first): raw-byte input pins, run-summary pins, segment definitions, equity.csv structure,
  session identity, exchange_calendars==4.13.2 and XNYS sessions, finite positive equity, exact equity/metrics equality,
  allow-listed reads. Any failure aborts the whole run (ABORTED_SHARED_INTEGRITY): the shared record is written
  write-once to artifacts/day29/preflight/shared_integrity_record.json and no diagnostic output is created.
- Diagnostics T0-T3, K1-K3 (frozen §5, §6), 5 bps primary and 10 bps secondary, computed twice in process (S10); the
  record checks K2-C0..C4 and the K3 comparison block only the diagnostics that require them (frozen §7).
- Outputs are written to a temporary directory and renamed into place; an existing output is never overwritten.
Per frozen §15 nothing is imported from backtest/v2 except forward.lf_sha256, engine.E0 and metrics.ANN.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys

import numpy as np

from acquisition.contract import ROOT_DIR
from backtest.v2.engine import E0
from backtest.v2.forward import lf_sha256
from backtest.v2.metrics import ANN

# ------------------------------------------------------------------ frozen constants (DAY-29 predeclaration)

FROZEN_COMMIT = "06fc45f90b4059a1bcba65514c7a6e4598c8d3e7"
FROZEN_MD = "artifacts/day29/day29-stability-predeclaration.md"
FROZEN_DOC_LF_SHA256 = "7f9d1bea5236de2a9c0dc89fc60331f3f9ec82c3a316d95e49ff95fc9409ae39"
EVIDENCE_LABEL = "robustness diagnostic on reused historical data — not independent or forward evidence"
COST_LABELS = {"5bps": "primary analysis (5 bps)",
               "10bps": "secondary cost sensitivity (10 bps) — not primary evidence"}
DEFAULT_OUT = ROOT_DIR / "artifacts" / "day29" / "run"
DEFAULT_RECORD = ROOT_DIR / "artifacts" / "day29" / "preflight" / "shared_integrity_record.json"
INPUT_FILES = ("decisions.json", "episodes.json", "equity.csv", "executions.json", "fills.csv", "metrics.json")
EQUITY_HEADER = "session,equity,exposure,n_held"
FILLS_HEADER = "session,ticker,side,shares,price,notional,cost,lambda,slot"
SEG_END = " (segment end)"
T2_DISCLOSURES = [
    "the return path is spliced; this is not a re-simulation and not a tradable strategy",
    "removal is outcome-dependent by construction",
    "if the last session is in the removed set, its liquidation cost is removed with it",
    "a change after tail removal is not, by itself, evidence of failure or of robustness",
]
K2_REQUIRED = ("K2-C0", "K2-C1", "K2-C2", "K2-C3", "K2-C4")
K3_REQUIRED = ("K2-C0", "K2-C1", "K2-C2", "K2-C4")          # frozen §6 "Required by"; K2-C3 is K2 only


@dataclass(frozen=True)
class Segment:
    id: str
    run_dir: str            # relative to the root, e.g. artifacts/day19/v2
    first: str
    last: str
    sessions: int
    mom: str
    b1: str


@dataclass(frozen=True)
class Spec:
    """Frozen DAY-29 parameters. Tests build a synthetic Spec; the real run uses FROZEN_SPEC only."""
    segments: tuple[Segment, ...]
    k1_files: tuple[tuple[str, str], ...]     # (path, raw SHA-256 recorded in the frozen document)
    k1_pins: str
    ks: tuple[int, ...] = (5, 10, 20)
    costs: tuple[str, ...] = ("5bps", "10bps")
    calendar_version: str = "4.13.2"


FROZEN_SPEC = Spec(
    segments=(
        Segment("research", "artifacts/day19/v2", "2017-02-01", "2022-12-30", 1490, "V2-MOM-R001", "V2-B1-research"),
        Segment("holdout", "artifacts/day21/v2", "2023-01-03", "2026-06-02", 856, "V2-MOM-H001", "V2-B1-holdout"),
    ),
    k1_files=(("artifacts/day25b/run/d1.json", "9dfe44deb86c3d10164eda61f14b04c7d07f95a1c222bca461521c2b0b069670"),
              ("artifacts/day25b/run/d2.json", "541a9226c0ca1629767dfd1272b04d708e6163c73c24dfdf97df572fe2293bf5"),
              ("artifacts/day25b/run/d5.json", "1738dd9eae9bb3e7d2af2e13c53a0b570ef3da11455708eca3d9f925ed43d864")),
    k1_pins="artifacts/day25b/run/run_summary.json",
)


class Day29Error(RuntimeError):
    pass


class SharedIntegrityAbort(Day29Error):
    """A frozen §4 S1-S10 failure: the entire run aborts and no diagnostic output exists."""


class _CheckFailed(Exception):
    def __init__(self, check: str, detail: dict):
        super().__init__(check)
        self.check, self.detail = check, detail


# ------------------------------------------------------------------ helpers

def _refuse(*_a, **_k):
    raise RuntimeError("network access is forbidden during the DAY-29 run")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _dump(path: Path, obj) -> str:
    """Same byte format as backtest/v2/run.py::_dump (indent 1, sorted keys, no NaN, trailing LF)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    b = _canon(obj)
    path.write_bytes(b)
    return _sha(b)


def undefined(reason: str) -> dict:
    return {"undefined": reason}


def _iso(s) -> str:
    if not isinstance(s, str) or len(s) != 10 or date.fromisoformat(s).isoformat() != s:
        raise ValueError(f"not an ISO session date: {s!r}")
    return s


def _git(*a) -> str:
    return subprocess.run(["git", *a], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout.strip()


def _import_calendar():
    return importlib.import_module("exchange_calendars")


def fingerprint() -> dict:
    try:
        xc = _import_calendar().__version__
    except Exception as e:                                     # recorded, never used to relax a check
        xc = f"unavailable: {type(e).__name__}"
    return {"python": sys.version.split()[0], "executable": sys.executable, "platform": platform.platform(),
            "numpy": np.__version__, "exchange_calendars": xc}


class Reader:
    """Every input read goes through here; a path outside the allow-list is a frozen S9 failure."""

    def __init__(self, root: Path, spec: Spec):
        self.root = Path(root)
        allowed = {spec.k1_pins} | {p for p, _ in spec.k1_files}
        for seg in spec.segments:
            allowed |= {f"{seg.run_dir}/run_summary.json", f"{seg.run_dir}/run_provenance.json"}
            allowed |= {f"{seg.run_dir}/{e}/{c}/{f}" for e in (seg.mom, seg.b1) for c in spec.costs for f in INPUT_FILES}
        self.allowed = frozenset(allowed)

    def read(self, rel: str) -> bytes:
        if rel not in self.allowed:
            raise _CheckFailed("S9", {"refused_path": rel, "rule": "only frozen §2 inputs and K1 citations are read"})
        return (self.root / rel).read_bytes()


class Calendar:
    """XNYS via exchange_calendars, version-checked (frozen S6). The window matches backtest/v2/run.py."""

    def __init__(self, required_version: str):
        try:
            xc = _import_calendar()
        except Exception as e:
            raise _CheckFailed("S6", {"expected": f"exchange_calendars=={required_version}",
                                      "observed": f"unavailable ({type(e).__name__}: {e})"})
        if xc.__version__ != required_version:
            raise _CheckFailed("S6", {"expected": f"exchange_calendars=={required_version}",
                                      "observed": f"exchange_calendars=={xc.__version__}"})
        self.version = xc.__version__
        self.cal = xc.get_calendar("XNYS", start="2015-12-01", end="2027-12-31")

    def sessions(self, first: str, last: str) -> list[str]:
        return [str(s.date()) for s in self.cal.sessions_in_range(first, last)]

    def next_session(self, s: str) -> str:
        return str(self.cal.next_session(s).date())

    def month_sessions(self, ym: str) -> list[str]:
        y, m = int(ym[:4]), int(ym[5:7])
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        return self.sessions(date(y, m, 1).isoformat(), (nxt - timedelta(days=1)).isoformat())


# ------------------------------------------------------------------ shared stage (frozen §4)

_REPR_FLOAT = re.compile(r"-?\d+(?:\.\d+)?(?:e[-+]\d+)?")    # finite float repr(): 123.45, -0.0, 1e-05, 1.5e+20
_COUNT = re.compile(r"\d+")


def _float_cell(s: str) -> float:
    """A float cell as backtest/v2/run.py::_csv writes it: repr(v). Under numpy 2 the engine's np.float64 values repr
    as 'np.float64(<shortest round-trip literal>)' (verified in the DAY-19/21 inputs); the literal is read exactly.
    Only these two forms of a finite repr literal are accepted; anything else is malformed (S4). Exactness is
    confirmed independently by S8."""
    lit = s[len("np.float64("):-1] if s.startswith("np.float64(") and s.endswith(")") else s
    if not _REPR_FLOAT.fullmatch(lit):
        raise ValueError(f"malformed float cell: {s!r}")
    return float(lit)


def _parse_equity(b: bytes) -> tuple[list[str], list[float], list[int]]:
    text = b.decode("utf-8")
    if not text.endswith("\n"):
        raise ValueError("equity.csv does not end with LF")
    lines = text.split("\n")[:-1]
    if not lines or lines[0] != EQUITY_HEADER:
        raise ValueError(f"equity.csv header {lines[0] if lines else None!r} != {EQUITY_HEADER!r}")
    sess, eq, nh = [], [], []
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) != 4:
            raise ValueError(f"equity.csv row has {len(parts)} fields: {ln!r}")
        sess.append(_iso(parts[0]))
        eq.append(_float_cell(parts[1]))
        if not _COUNT.fullmatch(parts[3]):
            raise ValueError(f"malformed n_held cell: {parts[3]!r}")
        nh.append(int(parts[3]))
    return sess, eq, nh


def returns(equity: list[float]) -> np.ndarray:
    """r_d = E(d)/E(d-1) - 1 with E(0) = E_0; identical arithmetic to backtest/v2/metrics.py::returns (frozen §3)."""
    e = np.array([E0] + list(equity))
    return e[1:] / e[:-1] - 1.0


def load_inputs(root: Path, spec: Spec, cal_factory=Calendar, log: dict | None = None) -> dict:
    """Run S1-S9 in order, filling `log` with the passed checks; raises _CheckFailed at the first failing check."""
    rd, log = Reader(root, spec), ({} if log is None else log)
    raw: dict[str, bytes] = {}
    summaries: dict[str, dict] = {}
    for seg in spec.segments:                                                     # S1, S2
        s_bytes = rd.read(f"{seg.run_dir}/run_summary.json")
        prov = json.loads(rd.read(f"{seg.run_dir}/run_provenance.json"))
        if _sha(s_bytes) != prov.get("run_summary_sha256"):
            raise _CheckFailed("S2", {"file": f"{seg.run_dir}/run_summary.json", "expected": prov.get("run_summary_sha256"),
                                      "observed_raw_sha256": _sha(s_bytes)})
        summaries[seg.id] = json.loads(s_bytes)
        pins = summaries[seg.id].get("result_files_sha256", {})
        for e in (seg.mom, seg.b1):
            for c in spec.costs:
                for f in INPUT_FILES:
                    key, rel = f"{e}/{c}/{f}", f"{seg.run_dir}/{e}/{c}/{f}"
                    b = rd.read(rel)
                    if key not in pins or _sha(b) != pins[key]:
                        raise _CheckFailed("S1", {"file": rel, "expected": pins.get(key), "observed_raw_sha256": _sha(b),
                                                  "rule": "raw on-disk bytes, no normalisation"})
                    raw[rel] = b
    log["S1"] = {"files_verified_raw": len(raw)}
    log["S2"] = {"run_summaries_verified_raw": len(spec.segments)}
    for seg in spec.segments:                                                     # S3
        got = {k: summaries[seg.id].get("segment", {}).get(k) for k in ("first", "last", "sessions")}
        exp = {"first": seg.first, "last": seg.last, "sessions": seg.sessions}
        if got != exp:
            raise _CheckFailed("S3", {"segment": seg.id, "expected": exp, "observed": got})
    log["S3"] = "segments equal the frozen definitions"
    parsed: dict = {}
    for seg in spec.segments:                                                     # S4, S5
        ref = None
        for c in spec.costs:
            for e in (seg.mom, seg.b1):
                rel = f"{seg.run_dir}/{e}/{c}/equity.csv"
                try:
                    sess, eq, nh = _parse_equity(raw[rel])
                except (ValueError, UnicodeDecodeError) as x:
                    raise _CheckFailed("S4", {"file": rel, "error": str(x)})
                if len(sess) != seg.sessions or len(set(sess)) != len(sess) or sess != sorted(sess) \
                        or sess[0] != seg.first or sess[-1] != seg.last:
                    raise _CheckFailed("S4", {"file": rel, "expected": {"rows": seg.sessions, "first": seg.first,
                                                                        "last": seg.last, "unique_ascending": True},
                                              "observed": {"rows": len(sess), "first": sess[0] if sess else None,
                                                           "last": sess[-1] if sess else None,
                                                           "unique_ascending": len(set(sess)) == len(sess) and sess == sorted(sess)}})
                if ref is None:
                    ref = sess
                elif sess != ref:
                    raise _CheckFailed("S5", {"segment": seg.id, "file": rel, "rule": "session column identical across "
                                              "V2-MOM/B1 and 5/10 bps"})
                parsed[(seg.id, c, "mom" if e == seg.mom else "b1")] = {"sessions": sess, "equity": eq, "n_held": nh}
    log["S4"] = log["S5"] = "passed"
    cal = cal_factory(spec.calendar_version)                                     # S6
    for seg in spec.segments:
        xnys = cal.sessions(seg.first, seg.last)
        if parsed[(seg.id, spec.costs[0], "mom")]["sessions"] != xnys:
            raise _CheckFailed("S6", {"segment": seg.id, "rule": "session column equals XNYS sessions in [first, last]",
                                      "xnys_count": len(xnys)})
    log["S6"] = {"exchange_calendars": cal.version}
    for key, p in parsed.items():                                                 # S7
        e = np.array(p["equity"])
        r = returns(p["equity"])
        if not (np.all(np.isfinite(e)) and np.all(e > 0) and np.all(1.0 + r > 0)):
            raise _CheckFailed("S7", {"series": list(key), "rule": "equity finite and > 0; 1 + r_d > 0"})
        p["r"] = r
    log["S7"] = "passed"
    for seg in spec.segments:                                                     # S8
        for c in spec.costs:
            m = {k: json.loads(raw[f"{seg.run_dir}/{e}/{c}/metrics.json"]) for k, e in (("mom", seg.mom), ("b1", seg.b1))}
            for k in ("mom", "b1"):
                p = parsed[(seg.id, c, k)]
                if m[k].get("ending_equity") != p["equity"][-1] or m[k].get("sessions") != len(p["equity"]):
                    raise _CheckFailed("S8", {"series": [seg.id, c, k], "expected": {"ending_equity": m[k].get("ending_equity"),
                                              "sessions": m[k].get("sessions")}, "observed": {"last_equity": p["equity"][-1],
                                              "rows": len(p["equity"])}})
                p["metrics"] = m[k]
            if m["mom"].get("b1_ending_equity") != parsed[(seg.id, c, "b1")]["equity"][-1]:
                raise _CheckFailed("S8", {"series": [seg.id, c, "mom"], "expected_b1_ending_equity": m["mom"].get("b1_ending_equity"),
                                          "observed_b1_last_equity": parsed[(seg.id, c, "b1")]["equity"][-1]})
    log["S8"] = "passed"
    for seg in spec.segments:                                                     # V2-MOM records for K2/K3 (already S1-pinned)
        for c in spec.costs:
            p = parsed[(seg.id, c, "mom")]
            p["decisions_raw"] = raw[f"{seg.run_dir}/{seg.mom}/{c}/decisions.json"]
            p["episodes_raw"] = raw[f"{seg.run_dir}/{seg.mom}/{c}/episodes.json"]
            p["fills_raw"] = raw[f"{seg.run_dir}/{seg.mom}/{c}/fills.csv"]
            p["decision_count_pinned"] = summaries[seg.id].get("decision_counts", {}).get("V2-MOM")
            p["metrics_path"] = f"{seg.run_dir}/{seg.mom}/{c}/metrics.json"
            parsed[(seg.id, c, "b1")]["metrics_path"] = f"{seg.run_dir}/{seg.b1}/{c}/metrics.json"
    k1 = {"pins": {}, "files": {}}
    try:                                       # K1 is a citation only (frozen §6); no §7 level applies to it
        k1["pins"] = json.loads(rd.read(spec.k1_pins)).get("result_files_sha256", {})
    except (OSError, ValueError):
        pass
    for p, _ in spec.k1_files:
        try:
            k1["files"][p] = _sha(rd.read(p))
        except OSError:
            k1["files"][p] = None
    log["S9"] = {"allow_listed_paths": len(rd.allowed)}
    return {"series": parsed, "pins": {s.id: summaries[s.id]["result_files_sha256"] for s in spec.segments},
            "k1": k1, "calendar": cal}


# ------------------------------------------------------------------ T0-T3 (frozen §5)

def t0(sessions, r_m, r_b, mom, b1, pins_rel) -> dict:
    lm, lb = np.log(1.0 + r_m), np.log(1.0 + r_b)
    l = lm - lb
    L = math.fsum(l.tolist())
    log_ratio = math.log(mom["equity"][-1] / b1["equity"][-1])
    return {"N": len(sessions), "L": L, "log_ending_equity_ratio": log_ratio,
            "L_minus_log_ratio": L - log_ratio, "identity_note": "descriptive floating-point difference; not a check",
            "cagr_copied": {"V2-MOM": {"value": mom["metrics"]["cagr"], "source": mom["metrics_path"],
                                       "pinned_sha256": pins_rel(mom["metrics_path"])},
                            "B1": {"value": b1["metrics"]["cagr"], "source": b1["metrics_path"],
                                   "pinned_sha256": pins_rel(b1["metrics_path"])}},
            "rows": [{"session": s, "r_mom": float(a), "r_b1": float(b), "l": float(x)}
                     for s, a, b, x in zip(sessions, r_m, r_b, l)]}, l


def tail_sets(l: np.ndarray, sessions: list[str], k: int) -> tuple[list[int], list[int]] | None:
    """Best-k: l descending; worst-k: l ascending; ties by ascending session date. None when N < 2k."""
    n = len(l)
    if n < 2 * k:
        return None
    best = sorted(range(n), key=lambda i: (-l[i], sessions[i]))[:k]
    worst = sorted(range(n), key=lambda i: (l[i], sessions[i]))[:k]
    return best, worst


def t1(l: np.ndarray, sessions: list[str], ks) -> dict:
    n = len(l)
    n_pos, n_zero = int(np.sum(l > 0)), int(np.sum(l == 0))
    counts = {"N": n, "n_pos": n_pos, "n_zero": n_zero, "n_neg": n - n_pos - n_zero,
              "share_positive_days": n_pos / n, "share_denominator": "N (all aligned sessions, zero-active days included)",
              "L_context_only": math.fsum(l.tolist())}
    out = {}
    for k in ks:
        sets = tail_sets(l, sessions, k)
        if sets is None:
            out[str(k)] = undefined("insufficient observations: N < 2k")
            continue
        out[str(k)] = {tail: {"sessions": [sessions[i] for i in idx], "l": [float(l[i]) for i in idx],
                              "sum_l": math.fsum(float(l[i]) for i in idx)}
                       for tail, idx in (("best", sets[0]), ("worst", sets[1]))}
    return {"counts": counts, "by_k": out, "label": "outcome-dependent selection by realised l_d"}


def t2(l, sessions, r_m, r_b, ks, t0_cagr: dict) -> dict:
    n, out = len(l), {}
    for k in ks:
        sets = tail_sets(l, sessions, k)
        if sets is None:
            out[str(k)] = undefined("insufficient observations: N < 2k")
            continue
        out[str(k)] = {}
        for tail, idx in (("best_removed", sets[0]), ("worst_removed", sets[1])):
            keep = np.ones(n, dtype=bool)
            keep[idx] = False
            nk = int(keep.sum())                                  # = N - k (distinct dates)
            g_m, g_b = float(np.prod(1 + r_m[keep])), float(np.prod(1 + r_b[keep]))
            c_m, c_b = g_m ** (ANN / nk) - 1, g_b ** (ANN / nk) - 1     # DAY-25B D4c convention
            out[str(k)][tail] = {"sessions_removed": sorted(sessions[i] for i in idx), "sessions_remaining": nk,
                                 "last_session_removed": (n - 1) in idx,
                                 "remaining_total_return": {"V2-MOM": g_m - 1, "B1": g_b - 1},
                                 "cagr_excl": {"V2-MOM": c_m, "B1": c_b},
                                 "active_cagr": c_m - c_b, "active_total_return": (g_m - 1) - (g_b - 1)}
    return {"by_k": out, "unremoved_t0_cagr_copied": {k: v["value"] for k, v in t0_cagr.items()},
            "disclosures": T2_DISCLOSURES, "annualisation": "G^(252/(N-k)) - 1 (DAY-25B D4c)"}


def _compound(xs) -> float:
    acc = 1.0
    for x in xs:                                              # same loop as backtest/v2/metrics.py::_period_returns
        acc *= 1.0 + x
    return acc - 1.0


def t3(sessions, r_m, r_b, l, cal) -> dict:
    months: dict[str, list[int]] = {}
    for i, s in enumerate(sessions):
        months.setdefault(s[:7], []).append(i)
    rows = []
    for ym in sorted(months):
        idx = months[ym]
        seg_days = [sessions[i] for i in idx]
        full = cal.month_sessions(ym) == seg_days
        rm, rb = _compound(float(r_m[i]) for i in idx), _compound(float(r_b[i]) for i in idx)
        rows.append({"month": ym, "label": "full" if full else f"partial ({seg_days[0]}..{seg_days[-1]})",
                     "n_sessions": len(idx), "r_mom": rm, "r_b1": rb, "active": rm - rb,
                     "log_active": math.fsum(float(l[i]) for i in idx)})

    def counts(rs):
        return {"months": len(rs), "active_gt_0": sum(r["active"] > 0 for r in rs),
                "active_eq_0": sum(r["active"] == 0 for r in rs), "active_lt_0": sum(r["active"] < 0 for r in rs)}
    return {"rows": rows, "counts_all_months": counts(rows),
            "counts_full_months": counts([r for r in rows if r["label"] == "full"]),
            "calendar": f"exchange_calendars {cal.version} XNYS"}


# ------------------------------------------------------------------ K1-K3 (frozen §6)

def k1(spec: Spec, k1_inputs: dict) -> dict:
    rows = []
    for path, frozen in spec.k1_files:
        name = path.rsplit("/", 1)[1]
        obs, pin = k1_inputs["files"][path], k1_inputs["pins"].get(name)
        rows.append({"path": path, "frozen_document_sha256": frozen, "day25b_run_summary_pin": pin,
                     "observed_raw_sha256": obs, "matches": obs == frozen == pin})
    return {"citations": rows, "note": "reference only; DAY-25B values are not recomputed, restated or reinterpreted"}


def _parse_records(p: dict, sessions: list[str]) -> tuple[dict, dict]:
    """Parse V2-MOM decisions/episodes/fills and evaluate K2-C0..C4. Returns (records, {check: failure detail})."""
    fail: dict[str, dict] = {}
    rec: dict = {"decisions": None, "episodes": None, "fills": None}
    try:                                                                          # K2-C0
        dec = json.loads(p["decisions_raw"])
        recs, discarded = [], 0
        for x in dec:
            _iso(x["close"])
            if ("targets" in x) == ("discarded" in x):
                raise ValueError(f"record needs exactly one of targets/discarded: {x}")
            if "discarded" in x:
                discarded += 1
                continue
            for t, w in x["targets"].items():
                if not isinstance(w, (int, float)) or isinstance(w, bool) or not math.isfinite(w) or w < 0:
                    raise ValueError(f"invalid target weight {t}={w!r} at {x['close']}")
            recs.append(x)
        if len(recs) != p["decision_count_pinned"]:
            fail["K2-C0"] = {"expected_decision_records": p["decision_count_pinned"], "observed": len(recs)}
        rec["decisions"], rec["discarded"] = recs, discarded
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        fail["K2-C0"] = {"error": str(e)}
    last = sessions[-1]
    try:                                                                          # K2-C1
        eps = []
        for x in json.loads(p["episodes_raw"]):
            end, seg_end = x["end"], x["end"].endswith(SEG_END)
            eps.append({"ticker": x["ticker"], "start": _iso(x["start"]), "seg_end": seg_end,
                        "end": _iso(end[:-len(SEG_END)] if seg_end else end)})
        by_t: dict[str, list] = {}
        for e in eps:
            by_t.setdefault(e["ticker"], []).append(e)
        for t, lst in by_t.items():
            for i, e in enumerate(lst):
                if e["seg_end"] and i != len(lst) - 1:
                    raise ValueError(f"{t}: segment-end episode is not the ticker's last")
                if not e["seg_end"] and not e["start"] < e["end"]:
                    raise ValueError(f"{t}: normal episode with start {e['start']} >= end {e['end']}")
                if i and not lst[i - 1]["end"] <= e["start"]:
                    raise ValueError(f"{t}: episodes not ordered / overlapping at {e['start']}")
        rec["episodes"] = eps
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        fail["K2-C1"] = {"error": str(e)}
    if rec["episodes"] is not None:
        held = held_sets(rec["episodes"], sessions)
        bad = [(s, len(held[s]), n) for s, n in zip(sessions, p["n_held"]) if len(held[s]) != n]   # K2-C2
        if bad:
            fail["K2-C2"] = {"mismatching_sessions": len(bad), "first": {"session": bad[0][0], "episodes_held": bad[0][1],
                                                                         "equity_n_held": bad[0][2]}}
        if len(rec["episodes"]) != p["metrics"].get("position_episodes"):                            # K2-C3
            fail["K2-C3"] = {"expected_position_episodes": p["metrics"].get("position_episodes"),
                             "observed_episodes": len(rec["episodes"])}
        rec["held"] = held
    else:
        for c in ("K2-C2", "K2-C3"):
            fail[c] = {"error": "episodes.json unusable (see K2-C1)"}
    try:                                                                          # K2-C4
        text = p["fills_raw"].decode("utf-8")
        lines = text.split("\n")[:-1]
        if not text.endswith("\n") or not lines or lines[0] != FILLS_HEADER:
            raise ValueError("fills.csv header or line ending differs from backtest/v2/run.py")
        fills = []
        for ln in lines[1:]:
            parts = ln.split(",")
            if len(parts) != 9:
                raise ValueError(f"fills.csv row has {len(parts)} fields")
            fills.append((_iso(parts[0]), parts[1], parts[2]))
        rec["fills"] = fills
        if rec["episodes"] is None:
            raise ValueError("episodes.json unusable (see K2-C1)")
        problems = []
        for e in rec["episodes"]:
            t, hi = e["ticker"], (last if e["seg_end"] else e["end"])
            if (e["start"], t, "buy") not in fills:
                problems.append(f"{t}: no buy fill at start {e['start']}")
            if not e["seg_end"] and (e["end"], t, "sell") not in fills:
                problems.append(f"{t}: no sell fill at end {e['end']}")
        for s, t, _side in fills:
            if not any(e["ticker"] == t and e["start"] <= s <= (last if e["seg_end"] else e["end"]) for e in rec["episodes"]):
                problems.append(f"{t}: fill at {s} outside every episode")
        if problems:
            fail["K2-C4"] = {"problems": len(problems), "first": problems[0]}
    except (ValueError, UnicodeDecodeError) as e:
        fail["K2-C4"] = {"error": str(e)}
    return rec, fail


def held_sets(episodes: list[dict], sessions: list[str]) -> dict[str, frozenset]:
    """Tickers held at each close: normal start <= s < end; segment-end start <= s <= last session (frozen §6 K2)."""
    last = sessions[-1]
    out = {s: set() for s in sessions}
    for e in episodes:
        for s in sessions:
            if e["start"] <= s and (s <= last if e["seg_end"] else s < e["end"]):
                out[s].add(e["ticker"])
    return {s: frozenset(v) for s, v in out.items()}


def k2(rec: dict, sessions: list[str]) -> dict:
    n, sel, ep, h = len(sessions), {}, {}, {}
    for d in rec["decisions"]:
        for t, w in d["targets"].items():
            if w > 0:
                sel[t] = sel.get(t, 0) + 1
    for e in rec["episodes"]:
        ep[e["ticker"]] = ep.get(e["ticker"], 0) + 1
    for s in sessions:
        for t in rec["held"][s]:
            h[t] = h.get(t, 0) + 1
    tickers = sorted(set(sel) | set(ep) | set(h))
    return {"rows": [{"ticker": t, "sel": sel.get(t, 0), "ep": ep.get(t, 0), "h": h.get(t, 0), "h_share": h.get(t, 0) / n}
                     for t in tickers],
            "totals": {"N": n, "decision_records": len(rec["decisions"]), "discarded_records": rec["discarded"],
                       "episodes": len(rec["episodes"]), "held_ticker_sessions": sum(h.values()),
                       "distinct_selected": len(sel), "distinct_held": len(h)},
            "note": "no P&L of any kind (frozen §11)"}


def target_holdings(decisions: list[dict], s: str):
    """T(s): weight>0 tickers of the latest decision with close date strictly before s (frozen §6 K3)."""
    prior = [d for d in decisions if d["close"] < s]
    if not prior:
        return undefined("no prior decision")
    latest = max(d["close"] for d in prior)
    same = [d for d in prior if d["close"] == latest]
    if len(same) != 1:
        return undefined(f"{len(same)} decision records share the latest close {latest}")
    return frozenset(t for t, w in same[0]["targets"].items() if w > 0)


def reporting_sessions(sessions: list[str], cal) -> list[str]:
    """Frozen §6 K3 [C6]: first session, each session after a month-end session in [first, last-1], last session."""
    pick = {sessions[0], sessions[-1]}
    for s in sessions[:-1]:
        nxt = cal.next_session(s)
        if nxt[:7] != s[:7]:
            pick.add(nxt)
    return sorted(pick)


def k3(rec: dict, sessions: list[str], cal) -> tuple[dict, bool]:
    held, mism, undef, tgt = rec["held"], [], [], {}
    for s in sessions:
        t = target_holdings(rec["decisions"], s)
        tgt[s] = t
        if isinstance(t, dict):
            undef.append({"session": s, "reason": t["undefined"]})
            continue
        for x in sorted(t - held[s]):
            mism.append({"session": s, "ticker": x, "direction": "in T only"})
        for x in sorted(held[s] - t):
            mism.append({"session": s, "ticker": x, "direction": "in H only"})
    if mism or undef:
        return {"status": "BLOCKED", "failed": "K3: T(s) = H(s) for every segment session",
                "compared_sessions": len(sessions), "mismatch_count": len(mism),
                "mismatching_sessions": sorted({m["session"] for m in mism} | {u["session"] for u in undef}),
                "mismatches": mism, "undefined_sessions": undef}, False

    def fmt(x):
        return sorted(x)
    rows = []
    for s in reporting_sessions(sessions, cal):
        i = sessions.index(s)
        prior = sessions[i - 1] if i else "pre-segment close"
        rows.append({"session": s, "prior_close": prior,
                     "T_prior": fmt(tgt[sessions[i - 1]]) if i else [], "H_prior": fmt(held[sessions[i - 1]]) if i else [],
                     "T_current": fmt(tgt[s]), "H_current": fmt(held[s])})
    return {"status": "COMPLETED", "compared_sessions": len(sessions), "mismatch_count": 0, "mismatches": [],
            "reporting_sessions": rows}, True


# ------------------------------------------------------------------ orchestration

def compute_diagnostics(inputs: dict, spec: Spec) -> tuple[dict, list[dict]]:
    """All T and K outputs, keyed by cost then diagnostic then segment; plus the list of blocked units."""
    series, cal = inputs["series"], inputs["calendar"]

    def pin_of(rel: str) -> str:
        for seg in spec.segments:
            if rel.startswith(seg.run_dir + "/"):
                return inputs["pins"][seg.id][rel[len(seg.run_dir) + 1:]]
        raise Day29Error(rel)

    out: dict = {"k1": k1(spec, inputs["k1"])}
    blocked: list[dict] = []
    for c in spec.costs:
        res = {d: {} for d in ("t0", "t1", "t2", "t3", "k2", "k3")}
        for seg in spec.segments:
            mom, b1 = series[(seg.id, c, "mom")], series[(seg.id, c, "b1")]
            sessions = mom["sessions"]
            res["t0"][seg.id], l = t0(sessions, mom["r"], b1["r"], mom, b1, pin_of)
            res["t1"][seg.id] = t1(l, sessions, spec.ks)
            res["t2"][seg.id] = t2(l, sessions, mom["r"], b1["r"], spec.ks, res["t0"][seg.id]["cagr_copied"])
            res["t3"][seg.id] = t3(sessions, mom["r"], b1["r"], l, cal)
            rec, fail = _parse_records(mom, sessions)
            k2_fail = {x: fail[x] for x in K2_REQUIRED if x in fail}
            k3_fail = {x: fail[x] for x in K3_REQUIRED if x in fail}
            if k2_fail:
                res["k2"][seg.id] = {"status": "BLOCKED", "failed_checks": k2_fail}
                blocked.append({"diagnostic": "K2", "segment": seg.id, "cost": c, "failed": sorted(k2_fail)})
            else:
                res["k2"][seg.id] = {"status": "COMPLETED"} | k2(rec, sessions)
            if k3_fail:
                res["k3"][seg.id] = {"status": "BLOCKED", "failed_checks": k3_fail}
                blocked.append({"diagnostic": "K3", "segment": seg.id, "cost": c, "failed": sorted(k3_fail)})
            else:
                res["k3"][seg.id], ok = k3(rec, sessions, cal)
                if not ok:
                    blocked.append({"diagnostic": "K3", "segment": seg.id, "cost": c, "failed": ["K3 T(s)=H(s)"]})
        out[c] = res
    return out, blocked


def _write_record(path: Path, record: dict) -> str:
    if path.exists():
        raise Day29Error(f"shared integrity record already exists (write-once): {path}")
    return _dump(path, record)


def run(root: Path, spec: Spec, out_dir: Path, record_path: Path, authorization: str,
        extra_repro: dict | None = None, cal_factory=Calendar) -> dict:
    """Shared stage first; on PASS compute everything twice (S10) and write atomically to out_dir."""
    out_dir, record_path = Path(out_dir), Path(record_path)
    if not authorization.strip():
        raise Day29Error("a separate, explicit run authorization is required")
    if out_dir.exists():
        raise Day29Error(f"output directory already exists, refusing to overwrite: {out_dir}")
    if record_path.exists():
        raise Day29Error(f"shared integrity record already exists (write-once): {record_path}")
    record = {"task": "DAY-29", "stage": "shared integrity and session alignment (frozen §4)",
              "authorizes_diagnostics": False, "frozen_commit": FROZEN_COMMIT, "environment": fingerprint()}

    def abort(check: str, detail: dict, log: dict):
        record.update(status="ABORTED_SHARED_INTEGRITY", failed_check=check, detail=detail, passed_checks=log)
        _write_record(record_path, record)
        raise SharedIntegrityAbort(f"{check}: {detail}")

    log: dict = {}
    try:
        inputs = load_inputs(root, spec, cal_factory, log)
    except _CheckFailed as e:
        abort(e.check, e.detail, log)
    except (OSError, ValueError, KeyError, TypeError) as e:          # unreadable or malformed input: fail closed
        abort("S1-S9", {"error": f"{type(e).__name__}: {e}"}, log)
    first, blocked = compute_diagnostics(inputs, spec)
    try:
        second, blocked2 = compute_diagnostics(load_inputs(root, spec, cal_factory), spec)
    except (_CheckFailed, OSError, ValueError, KeyError, TypeError) as e:
        abort("S10", {"rule": "second in-process execution", "error": f"{type(e).__name__}: {e}"}, log)
    if _canon([first, blocked]) != _canon([second, blocked2]):
        abort("S10", {"rule": "two in-process executions must produce byte-identical outputs"}, log)
    log["S10"] = "byte-identical in-process outputs"
    record.update(status="PASSED", checks=log)
    record_sha = _write_record(record_path, record)
    status = "COMPLETED_WITH_BLOCKED_DIAGNOSTICS" if blocked else "COMPLETED"
    tmp = out_dir.parent / f".{out_dir.name}.tmp-{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        files = {"k1.json": _dump(tmp / "k1.json", {"diagnostic": "K1", "evidence_label": EVIDENCE_LABEL,
                                                    "descriptive_only": True, "results": first["k1"]})}
        for c in spec.costs:
            for d, val in first[c].items():
                rel = f"{c}/{d}.json"
                files[rel] = _dump(tmp / rel, {"diagnostic": d.upper(), "cost": c, "cost_label": COST_LABELS.get(c, c),
                                               "evidence_label": EVIDENCE_LABEL, "descriptive_only": True,
                                               "family_scope": "V2-MOM only" if d.startswith("k") else "V2-MOM vs B1",
                                               "results": val})
        summary = {
            "task": "DAY-29", "status": status, "evidence_label": EVIDENCE_LABEL, "descriptive_only": True,
            "decision_rules": "none; no output changes V2-MOM status (frozen §9)", "authorization": authorization,
            "cost_analyses": COST_LABELS, "blocked_diagnostics": blocked,
            "segments": {s.id: {"first": s.first, "last": s.last, "sessions": s.sessions} for s in spec.segments},
            "shared_integrity_record": {"path": str(record_path), "sha256": record_sha},
            "determinism_in_process": True,
            "reproducibility": {"frozen_commit": FROZEN_COMMIT, "frozen_doc": FROZEN_MD,
                                "frozen_doc_lf_sha256": FROZEN_DOC_LF_SHA256, "environment": fingerprint(),
                                "input_pins_verified": {s.id: inputs["pins"][s.id] for s in spec.segments}}
                               | (extra_repro or {}),
            "result_files_sha256": files,
        }
        _dump(tmp / "run_summary.json", summary)
        os.replace(tmp, out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return summary


def verify_frozen_doc(root: Path = ROOT_DIR) -> str:
    got = lf_sha256(Path(root) / FROZEN_MD)
    if got != FROZEN_DOC_LF_SHA256:
        raise Day29Error(f"frozen DAY-29 predeclaration changed: LF SHA-256 {got} != {FROZEN_DOC_LF_SHA256}")
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authorization", default="", help="reference of the explicit run authorization (required)")
    a = ap.parse_args(argv)
    if not a.authorization.strip():
        print("REFUSED: --authorization is required; no input was read", file=sys.stderr)
        return 2
    socket.socket.connect = _refuse
    try:
        verify_frozen_doc()
        summary = run(ROOT_DIR, FROZEN_SPEC, DEFAULT_OUT, DEFAULT_RECORD, a.authorization,
                      extra_repro={"git_commit": _git("rev-parse", "HEAD"),
                                   "git_status_porcelain": _git("status", "--porcelain").splitlines()})
    except SharedIntegrityAbort as e:
        print(f"ABORTED_SHARED_INTEGRITY: {e}", file=sys.stderr)
        return 1
    except Day29Error as e:
        print(f"DAY-29 REFUSED: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"status": summary["status"], "out": str(DEFAULT_OUT),
                      "blocked_diagnostics": summary["blocked_diagnostics"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
