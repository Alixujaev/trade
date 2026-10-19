"""scripts/day30_attribution.py: DAY-30 V2-MOM day-by-ticker attribution of active return against B1
(frozen predeclaration 2f94f7d, artifacts/day30/day30-attribution-predeclaration.md — FROZEN).

    .venv/Scripts/python.exe -m scripts.day30_attribution --authorization DAY30-ATTRIBUTION-RUN

Descriptive accounting attribution of the existing DAY-19/DAY-21 portfolio paths (frozen §1-§5): no engine run, replay,
re-simulation or counterfactual. Every output carries the evidence, conditional, outcome-dependence and
survivor-universe labels. G7/G8 are conditional bounds, valid only under the unproven premises A1 and A4 (frozen §6A).

- Refusals before any input is read (frozen §10): the token must be exactly DAY30-ATTRIBUTION-RUN; the document's
  LF-normalised SHA-256 must equal the frozen-file hash of the freeze commit, and reverting its two freeze rows must
  reproduce the owner-approved pre-freeze hash (§12); network sockets are refused.
- Gates G1-G8 (frozen §6, §6A): any failure aborts the run; the gate record is written once to
  artifacts/day30/preflight/gate_record.json and no output is created.
- Exact side: every float64 input becomes fractions.Fraction; attribution, residuals, bounds and comparisons are exact.
  Float64 arithmetic is used only for the §3 state updates and the G5a-G5d checkpoint recomputations (frozen §6A.7).
- Outputs are written to a temporary directory and renamed into place; an existing output is never overwritten.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Callable

import numpy as np

from acquisition.contract import ROOT_DIR
from backtest.v2.engine import E0
from backtest.v2.forward import lf_sha256
from scripts.day29_stability import FILLS_HEADER, SEG_END, _float_cell, _iso, _parse_equity, fingerprint, held_sets

# ------------------------------------------------------------------ frozen constants (DAY-30 predeclaration)

FROZEN_COMMIT = "2f94f7d8f760a31107ce609be14232f4b654c0cc"
FROZEN_MD = "artifacts/day30/day30-attribution-predeclaration.md"
FROZEN_DOC_LF_SHA256 = "09f8b4e6be9355ef3f962905fbcbddb0fdf45533dadca6b2282f8a1229fec72e"
APPROVED_PREFREEZE_LF_SHA256 = "5f25ae08c43de2faef836b27a5c20b81fb71a1b44c690fe9fa1ec14adbc818b4"
PREFREEZE_ROWS = ("| Status | **DRAFT — NOT APPROVED — NOT FROZEN — NOT AUTHORIZED TO RUN** |",
                  "| Freeze | None. OD-1 and OD-2 are decided (§11). Freezing follows §12. |")
AUTH_TOKEN = "DAY30-ATTRIBUTION-RUN"
EVIDENCE_LABEL = ("descriptive attribution on reused historical data — outcome-dependent day and ticker sets — "
                  "survivor-universe — not independent or forward evidence")
CONDITIONAL_LABEL = ("G7/G8 reconciliation is conditional on unproven premises A1 (IEEE-754 platform arithmetic) and A4 "
                     "(bit-identical reconstructed share/price state); see §6A")
OUTCOME_LABEL = "outcome-dependent sets: day sets selected by realised l_d, ticker sets selected by realised P&L"
SURVIVOR_LABEL = "survivor-universe: the frozen 25-symbol universe was chosen with present knowledge"
COST_LABELS = {"5bps": "primary analysis (5 bps)",
               "10bps": "secondary cost sensitivity (10 bps) — not primary evidence"}
COST_S = {"5bps": 0.0005, "10bps": 0.0010}          # backtest/v2/run.py:40 COSTS (the engine's float64 s)
DEFAULT_OUT = ROOT_DIR / "artifacts" / "day30" / "run"
DEFAULT_RECORD = ROOT_DIR / "artifacts" / "day30" / "preflight" / "gate_record.json"
I1_FILES = ("equity.csv", "fills.csv", "episodes.json", "metrics.json")
U = Fraction(1, 2 ** 53)
MIN_NORMAL = Fraction(1, 2 ** 1022)
SERIES = ("V2-MOM", "B1")


@dataclass(frozen=True)
class Segment:
    id: str
    run_dir: str
    first: str
    last: str
    sessions: int
    mom: str
    b1: str
    d2: tuple[str, ...]          # DAY-25B D2 top-two tickers (frozen §2 I4)


@dataclass(frozen=True)
class Spec:
    """Frozen DAY-30 parameters. Tests build a synthetic Spec; the real run uses FROZEN_SPEC only."""
    segments: tuple[Segment, ...]
    t1_files: tuple[tuple[str, str, str], ...]       # (cost, path, raw SHA-256 from frozen §2 I3)
    day29_summary: tuple[str, str]                   # (path, raw SHA-256)
    d2_file: tuple[str, str]                         # (path, raw SHA-256 from frozen §2 I4)
    d2_pins: str                                     # DAY-25B run_summary.json
    ks: tuple[int, ...] = (5, 10, 20)
    costs: tuple[str, ...] = ("5bps", "10bps")
    calendar_version: str = "4.13.2"
    cost_s: tuple[tuple[str, float], ...] = tuple(COST_S.items())


FROZEN_SPEC = Spec(
    segments=(
        Segment("research", "artifacts/day19/v2", "2017-02-01", "2022-12-30", 1490, "V2-MOM-R001", "V2-B1-research",
                ("TSLA", "NVDA")),
        Segment("holdout", "artifacts/day21/v2", "2023-01-03", "2026-06-02", 856, "V2-MOM-H001", "V2-B1-holdout",
                ("MU", "AMD")),
    ),
    t1_files=(("5bps", "artifacts/day29/run/5bps/t1.json", "f02769bfe41babd0ae108377c3ac9416b4150d6d7453f9c9374bbc7cbfdf7f58"),
              ("10bps", "artifacts/day29/run/10bps/t1.json", "5025aa6d4d3de2a0a14ff5407933cc343cbbafde64312fa7bd174eeccce23f73")),
    day29_summary=("artifacts/day29/run/run_summary.json", "d7795bb91ebad4bf371f9f7254491a76378b4a0ed551b17519dc13c5134cdfc9"),
    d2_file=("artifacts/day25b/run/d2.json", "541a9226c0ca1629767dfd1272b04d708e6163c73c24dfdf97df572fe2293bf5"),
    d2_pins="artifacts/day25b/run/run_summary.json",
)


class Day30Error(RuntimeError):
    pass


class GateAbort(Day30Error):
    """A frozen §6 G1-G8 failure: the entire run aborts and no output exists."""


class _GateFailed(Exception):
    def __init__(self, gate: str, detail: dict):
        super().__init__(gate)
        self.gate, self.detail = gate, detail


# ------------------------------------------------------------------ helpers

def _refuse(*_a, **_k):
    raise RuntimeError("network access is forbidden during the DAY-30 run")


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


def _git(*a) -> str:
    return subprocess.run(["git", *a], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout.strip()


def git_head_blob(root: Path, rel: str) -> bytes | None:
    """Bytes of `rel` in HEAD's tree, or None when it is not tracked there (frozen G3)."""
    p = subprocess.run(["git", "cat-file", "blob", f"HEAD:{rel}"], cwd=root, capture_output=True)
    return p.stdout if p.returncode == 0 else None


def calendar_version() -> str:
    import exchange_calendars
    return exchange_calendars.__version__


def real_loaders() -> dict[str, Callable]:
    from backtest.v2 import data
    return {"research": data.load_stage_r, "holdout": data.load_stage_h}


def gamma(n: int) -> Fraction:
    """γ_n = n·u / (1 − n·u); γ_n = 0 for n ≤ 0 (frozen §6A notation)."""
    return Fraction(0) if n <= 0 else n * U / (1 - n * U)


def tree_sum(xs) -> Fraction:
    xs = list(xs)
    if not xs:
        return Fraction(0)
    while len(xs) > 1:
        xs = [xs[i] + xs[i + 1] if i + 1 < len(xs) else xs[i] for i in range(0, len(xs), 2)]
    return xs[0]


def _fx(x) -> Fraction:
    x = float(x)
    if not math.isfinite(x):
        raise _GateFailed("G7", {"rule": "A2: every value on the bound paths is finite", "value": repr(x)})
    return Fraction(x)


def _range_ok(x: Fraction, what: str) -> Fraction:
    """A2: an exact × or ÷ result on the bound paths is 0 or has magnitude ≥ 2^-1022 (frozen §6A.2)."""
    if x != 0 and abs(x) < MIN_NORMAL:
        raise _GateFailed("G7", {"rule": "A2 range condition", "operation": what})
    return x


def _num(x: Fraction) -> float:
    return float(x)


class Reader:
    """Every artifact read goes through here; a path outside I1, I3, I4 and their pin files is a G6 failure."""

    def __init__(self, root: Path, spec: Spec):
        self.root = Path(root)
        allowed = {spec.day29_summary[0], spec.d2_file[0], spec.d2_pins} | {p for _, p, _ in spec.t1_files}
        for seg in spec.segments:
            allowed |= {f"{seg.run_dir}/run_summary.json", f"{seg.run_dir}/run_provenance.json"}
            allowed |= {f"{seg.run_dir}/{e}/{c}/{f}" for e in (seg.mom, seg.b1) for c in spec.costs for f in I1_FILES}
        self.allowed = frozenset(allowed)

    def read(self, rel: str) -> bytes:
        if rel not in self.allowed:
            raise _GateFailed("G6", {"refused_path": rel, "rule": "reads come only from I1-I4 and the frozen document"})
        return (self.root / rel).read_bytes()


# ------------------------------------------------------------------ parsing (I1)

@dataclass
class Fill:
    session: str
    ticker: str
    side: str
    shares: float
    price: float
    notional: float
    cost: float
    lam: float | None


def parse_fills(b: bytes) -> list[Fill]:
    text = b.decode("utf-8")
    lines = text.split("\n")[:-1]
    if not text.endswith("\n") or not lines or lines[0] != FILLS_HEADER:
        raise ValueError("fills.csv header or line ending differs from backtest/v2/run.py")
    out = []
    for ln in lines[1:]:
        p = ln.split(",")
        if len(p) != 9 or p[2] not in ("buy", "sell"):
            raise ValueError(f"malformed fills.csv row: {ln!r}")
        lam = _float_cell(p[7]) if p[2] == "buy" else None
        if p[2] == "sell" and p[7] != "":
            raise ValueError(f"sell row carries a lambda: {ln!r}")
        out.append(Fill(_iso(p[0]), p[1], p[2], _float_cell(p[3]), _float_cell(p[4]), _float_cell(p[5]),
                        _float_cell(p[6]), lam))
    return out


def parse_episodes(b: bytes) -> list[dict]:
    eps = []
    for x in json.loads(b):
        end = x["end"]
        seg_end = end.endswith(SEG_END)
        fnm = x["final_net_mark"]
        if not isinstance(fnm, float) or not math.isfinite(fnm):
            raise ValueError(f"episode final_net_mark is not a finite float: {x}")
        eps.append({"ticker": x["ticker"], "start": _iso(x["start"]), "seg_end": seg_end,
                    "end": _iso(end[:-len(SEG_END)] if seg_end else end), "final_net_mark": fnm})
    return eps


# ------------------------------------------------------------------ G1, G3: pinned artifacts

def load_artifacts(rd: Reader, spec: Spec, head_blob, log: dict) -> dict:
    summaries, series = {}, {}
    n_files = 0
    for seg in spec.segments:                                                          # G1
        s_bytes = rd.read(f"{seg.run_dir}/run_summary.json")
        prov = json.loads(rd.read(f"{seg.run_dir}/run_provenance.json"))
        if _sha(s_bytes) != prov.get("run_summary_sha256"):
            raise _GateFailed("G1", {"file": f"{seg.run_dir}/run_summary.json", "expected": prov.get("run_summary_sha256"),
                                     "observed_raw_sha256": _sha(s_bytes)})
        summaries[seg.id] = summ = json.loads(s_bytes)
        pins = summ.get("result_files_sha256", {})
        for c in spec.costs:
            for name, e in (("V2-MOM", seg.mom), ("B1", seg.b1)):
                raw = {}
                for f in I1_FILES:
                    key, rel = f"{e}/{c}/{f}", f"{seg.run_dir}/{e}/{c}/{f}"
                    b = rd.read(rel)
                    if key not in pins or _sha(b) != pins[key]:
                        raise _GateFailed("G1", {"file": rel, "expected": pins.get(key), "observed_raw_sha256": _sha(b),
                                                 "rule": "raw on-disk bytes, no normalisation"})
                    raw[f] = b
                    n_files += 1
                try:
                    sess, eq, nh = _parse_equity(raw["equity.csv"])
                    fills = parse_fills(raw["fills.csv"])
                    eps = parse_episodes(raw["episodes.json"])
                    contrib = json.loads(raw["metrics.json"])["symbol_pnl_contribution"]
                    if not all(isinstance(v, float) and math.isfinite(v) for v in contrib.values()):
                        raise ValueError("symbol_pnl_contribution holds a non-finite or non-float value")
                except (ValueError, KeyError, TypeError, UnicodeDecodeError) as x:
                    raise _GateFailed("G1", {"series": [seg.id, c, name], "rule": "I1 inputs parse exactly",
                                             "error": f"{type(x).__name__}: {x}"})
                series[(seg.id, c, name)] = {"sessions": sess, "equity": eq, "n_held": nh, "fills": fills,
                                             "episodes": eps, "contrib": contrib}
    log["G1"] = {"files_verified_raw": n_files, "run_summaries_verified_raw": len(spec.segments)}

    def tracked(rel: str, b: bytes, expected: str):                                   # G3
        blob = head_blob(rd.root, rel)
        if blob is None:
            raise _GateFailed("G3", {"file": rel, "rule": "tracked in git at HEAD"})
        if blob != b:
            raise _GateFailed("G3", {"file": rel, "rule": "HEAD blob bytes equal the working file"})
        if _sha(b) != expected:
            raise _GateFailed("G3", {"file": rel, "expected": expected, "observed_raw_sha256": _sha(b)})

    s29_path, s29_sha = spec.day29_summary
    s29 = rd.read(s29_path)
    tracked(s29_path, s29, s29_sha)
    pins29 = json.loads(s29).get("result_files_sha256", {})
    t1 = {}
    for c, path, sha in spec.t1_files:
        b = rd.read(path)
        tracked(path, b, sha)
        if pins29.get(f"{c}/t1.json") != sha:
            raise _GateFailed("G3", {"file": path, "rule": "equals its pin in the DAY-29 run_summary.json",
                                     "pin": pins29.get(f"{c}/t1.json")})
        t1[c] = json.loads(b)
    d2_path, d2_sha = spec.d2_file
    d2b = rd.read(d2_path)
    tracked(d2_path, d2b, d2_sha)
    pins25 = json.loads(rd.read(spec.d2_pins)).get("result_files_sha256", {})
    if pins25.get(d2_path.rsplit("/", 1)[1]) != d2_sha:
        raise _GateFailed("G3", {"file": d2_path, "rule": "equals its DAY-25B run_summary pin",
                                 "pin": pins25.get(d2_path.rsplit("/", 1)[1])})
    d2 = json.loads(d2b)
    for seg in spec.segments:
        r = d2.get("results", {}).get(seg.id, {})
        got = tuple(x.get("ticker") for x in r.get("removed", []))
        if got != seg.d2 or r.get("same_symbols_at_all_costs") is not True:
            raise _GateFailed("G3", {"segment": seg.id, "rule": "D2 ticker set equals frozen §2 I4",
                                     "expected": list(seg.d2), "observed": list(got),
                                     "same_symbols_at_all_costs": r.get("same_symbols_at_all_costs")})
    day_sets = {}
    for c in spec.costs:
        for seg in spec.segments:
            for k in spec.ks:
                for tail in ("best", "worst"):
                    try:
                        ss = t1[c]["results"][seg.id]["by_k"][str(k)][tail]["sessions"]
                        ss = [_iso(s) for s in ss]
                    except (KeyError, TypeError, ValueError) as x:
                        raise _GateFailed("G3", {"cost": c, "segment": seg.id, "k": k, "tail": tail,
                                                 "rule": "I3 day set readable", "error": str(x)})
                    if len(ss) != k or len(set(ss)) != k:
                        raise _GateFailed("G3", {"cost": c, "segment": seg.id, "k": k, "tail": tail,
                                                 "rule": "I3 day set holds k distinct sessions"})
                    day_sets[(c, seg.id, k, tail)] = ss
    log["G3"] = {"day29_t1_files": len(spec.t1_files), "d2_sets": {s.id: list(s.d2) for s in spec.segments},
                 "day_sets": len(day_sets)}
    return {"summaries": summaries, "series": series, "day_sets": day_sets}


# ------------------------------------------------------------------ G2: snapshots via the verifying loaders

def load_market(spec: Spec, art: dict, loaders: dict, cal_version, log: dict) -> dict:
    got = cal_version()
    if got != spec.calendar_version:
        raise _GateFailed("G2", {"expected": f"exchange_calendars=={spec.calendar_version}",
                                 "observed": f"exchange_calendars=={got}"})
    market = {}
    for seg in spec.segments:
        try:
            data, info = loaders[seg.id]()
        except Exception as x:                                     # any loader verification failure: fail closed
            raise _GateFailed("G2", {"segment": seg.id, "rule": "verifying loader", "error": f"{type(x).__name__}: {x}"})
        rep = art["summaries"][seg.id].get("reproducibility", {}).get("data", {})
        for key in ("manifest_sha256", "tree_sha256"):
            if info.get(key) is None or info.get(key) != rep.get(key):
                raise _GateFailed("G2", {"segment": seg.id, "field": key, "expected": rep.get(key),
                                         "observed": info.get(key)})
        summ_seg = art["summaries"][seg.id].get("segment", {})
        if {k: summ_seg.get(k) for k in ("first", "last", "sessions")} != \
                {"first": seg.first, "last": seg.last, "sessions": seg.sessions}:
            raise _GateFailed("G2", {"segment": seg.id, "rule": "run_summary segment equals the frozen segment"})
        iso = [s.isoformat() for s in data.sessions]
        if seg.first not in iso or seg.last not in iso:
            raise _GateFailed("G2", {"segment": seg.id, "rule": "segment inside the loaded sessions"})
        k0, kT = iso.index(seg.first), iso.index(seg.last)
        seg_sessions = iso[k0:kT + 1]
        if len(seg_sessions) != seg.sessions:
            raise _GateFailed("G2", {"segment": seg.id, "rule": "segment session count", "observed": len(seg_sessions)})
        for c in spec.costs:
            for name in SERIES:
                if art["series"][(seg.id, c, name)]["sessions"] != seg_sessions:
                    raise _GateFailed("G2", {"segment": seg.id, "cost": c, "series": name,
                                             "rule": "equity.csv sessions equal the loaded segment sessions"})
        if any(t not in data.universe for t in seg.d2):
            raise _GateFailed("G2", {"segment": seg.id, "rule": "D2 tickers are universe tickers"})
        market[seg.id] = {"data": data, "k0": k0, "kT": kT, "sessions": seg_sessions,
                          "snapshot": {"snapshot_id": info.get("snapshot_id"), "manifest_sha256": info["manifest_sha256"],
                                       "tree_sha256": info["tree_sha256"], "missing_bars": info.get("missing_bars")}}
    for key, ss in art["day_sets"].items():
        if not set(ss) <= set(market[key[1]]["sessions"]):
            raise _GateFailed("G3", {"key": list(key), "rule": "day-set sessions lie in the segment"})
    log["G2"] = {"exchange_calendars": got,
                 "snapshots": {s.id: market[s.id]["snapshot"] for s in spec.segments}}
    return market


# ------------------------------------------------------------------ §3 reconstruction (G4, G5) and §4 accounting

def reconstruct(mk: dict, ser: dict, s: float, label: list) -> dict:
    """Rebuild the per-ticker state with the engine's float64 operations in the engine's order (frozen §3), evaluate
    §4 P&L exactly, and collect the operands of the §6A bounds. Raises _GateFailed for G4/G5 failures."""
    data, k0, kT, sessions = mk["data"], mk["k0"], mk["kT"], mk["sessions"]
    tickers, universe = data.tickers, set(data.universe)
    m = len(tickers)
    col = {t: j for j, t in enumerate(tickers)}
    pos = {sv: i for i, sv in enumerate(sessions)}
    by_k: dict[int, list[Fill]] = {}
    seen = set()
    for f in ser["fills"]:                                                             # G4
        if f.session not in pos:
            raise _GateFailed("G4", {"series": label, "rule": "fill session lies in the segment", "session": f.session})
        if f.ticker not in universe:
            raise _GateFailed("G4", {"series": label, "rule": "fill ticker is a universe ticker", "ticker": f.ticker})
        if (f.session, f.ticker) in seen:
            raise _GateFailed("G4", {"series": label, "rule": "at most one fill per ticker per session",
                                     "session": f.session, "ticker": f.ticker})
        seen.add((f.session, f.ticker))
        k = k0 + pos[f.session]
        if not (f.price == data.open[k, col[f.ticker]]):
            raise _GateFailed("G4", {"series": label, "rule": "fill price equals open[session, ticker] exactly",
                                     "session": f.session, "ticker": f.ticker})
        by_k.setdefault(k, []).append(f)
    for k, fl in by_k.items():                                                         # engine order: sells, then buys
        sides = [f.side for f in fl]
        if sides != sorted(sides, key=lambda x: 0 if x == "sell" else 1):
            raise _GateFailed("G5", {"series": label, "rule": "sells precede buys within a session",
                                     "session": sessions[k - k0]})
    eps = ser["episodes"]
    held_ep = held_sets(eps, sessions)
    full_sell = {(e["end"], e["ticker"]) for e in eps if not e["seg_end"]}
    s_f, one_minus_s = Fraction(s), 1.0 - s
    shares = np.zeros(m)
    mark = np.full(m, np.nan)
    flows: dict[int, float] = {}
    days = []
    for k in range(k0, kT + 1):
        i, last = k - k0, k == kT
        S_prev, M_prev = shares.copy(), mark.copy()
        divs, splits = [], []
        for j in np.nonzero(shares)[0]:                                                # engine.py:53-68
            dv = data.d[k, j]
            if dv:
                divs.append((j, shares[j], dv))
                flows[j] = flows.get(j, 0.0) + shares[j] * dv
            qv = data.q[k, j]
            if qv != 1.0:
                splits.append((j, shares[j], mark[j], qv))
                shares[j] *= qv
                mark[j] /= qv
        for j in range(m):
            if not shares[j] and data.q[k, j] != 1.0 and not math.isnan(mark[j]):
                mark[j] /= data.q[k, j]
        Sp, Mp = shares.copy(), mark.copy()
        traded = {col[f.ticker] for f in by_k.get(k, [])}
        for j in set(np.nonzero(Sp)[0]) | traded:                                      # G4: no NaN open if held/traded
            if math.isnan(data.open[k, j]):
                raise _GateFailed("G4", {"series": label, "rule": "no NaN open where held or traded",
                                         "session": sessions[i], "ticker": tickers[j]})
        sells, buys, cost_k = [], [], {}
        for f in by_k.get(k, []):
            j = col[f.ticker]
            cost_k[j] = cost_k.get(j, Fraction(0)) + _fx(f.cost)
            if f.side == "sell":
                pre = shares[j]
                full = f.shares == pre
                if (f.session, f.ticker) in full_sell and not full:                    # G5a
                    raise _GateFailed("G5", {"series": label, "check": "G5a", "session": f.session, "ticker": f.ticker,
                                             "rule": "recorded full-sell shares equal reconstructed S'"})
                shares[j] = 0.0 if full else shares[j] - f.shares                      # engine.py:85
                if shares[j] < 0:
                    raise _GateFailed("G5", {"series": label, "rule": "shares never negative", "session": f.session,
                                             "ticker": f.ticker})
                flows[j] = flows.get(j, 0.0) + (np.float64(f.notional) - np.float64(f.cost))
                sells.append((j, f, pre, full))
            else:
                if not (np.float64(f.shares) == np.float64(f.notional) / np.float64(f.price)):   # G5b
                    raise _GateFailed("G5", {"series": label, "check": "G5b", "session": f.session, "ticker": f.ticker,
                                             "rule": "recorded shares equal float64 notional/price"})
                pre = shares[j]
                shares[j] += np.float64(f.shares)                                      # engine.py:104
                flows[j] = flows.get(j, 0.0) - np.float64(f.notional) - np.float64(f.cost)
                buys.append((j, f, pre))
        c = data.close[k]                                                              # engine.py:113-117
        have = ~np.isnan(c)
        mark[have] = c[have]
        held = np.nonzero(shares)[0]
        if len(held) != ser["n_held"][i]:                                              # G5
            raise _GateFailed("G5", {"series": label, "rule": "count of S != 0 equals n_held", "session": sessions[i],
                                     "reconstructed": len(held), "n_held": ser["n_held"][i]})
        if frozenset(tickers[j] for j in held) != held_ep[sessions[i]]:
            raise _GateFailed("G5", {"series": label, "rule": "held set equals the DAY-29 K2 episode-interval set",
                                     "session": sessions[i]})
        # §4 per-ticker P&L, exact
        pnl = {}
        div_exact = {j: _range_ok(_fx(Sv) * _fx(dv), "S·d") for j, Sv, dv in divs}
        for j in set(div_exact) | set(np.nonzero(Sp)[0]) | set(held) | set(cost_k):
            V = data.open[k, j] if not math.isnan(data.open[k, j]) else Mp[j]
            x = div_exact.get(j, Fraction(0)) - cost_k.get(j, Fraction(0))
            if Sp[j]:
                x += _fx(Sp[j]) * (_fx(V) - _fx(Mp[j]))
            if shares[j]:
                x += _fx(shares[j]) * (_fx(mark[j]) - _fx(V))
                if last:
                    x -= s_f * _range_ok(_fx(shares[j]) * _fx(mark[j]), "S·M")
            pnl[j] = x
        sm = {j: _range_ok(_fx(shares[j]) * _fx(mark[j]), "S·M") for j in held}
        split_sm = []
        for j, Sv, Mv, qv in splits:
            _range_ok(_fx(Sv) * _fx(qv), "S·q")
            _range_ok(_fx(Mv) / _fx(qv), "M/q")
            split_sm.append((j, _range_ok(_fx(Sv) * _fx(Mv), "S·M split")))
        day = {"pnl": pnl, "divs": [(_fx(Sv), _fx(dv)) for _, Sv, dv in divs],
               "div_by_j": {j: (_fx(Sv), _fx(dv)) for j, Sv, dv in divs}, "splits": split_sm,
               "sells": [(j, _fx(f.shares), _fx(f.price), _fx(f.notional), _fx(f.cost), not full, _fx(pre))
                         for j, f, pre, full in sells],
               "buys": [(j, _fx(f.notional), _fx(f.cost), _fx(f.shares), _fx(f.price), _fx(pre), f.lam)
                        for j, f, pre in buys],
               "sum_sm": sum(sm.values(), Fraction(0)), "sum_abs_sm": sum(map(abs, sm.values()), Fraction(0)),
               "h": len(held),
               "state": {j: (S_prev[j], Sp[j], shares[j], M_prev[j], Mp[j], mark[j]) for j in pnl}}
        for _, qty, px, *_r in day["sells"]:
            _range_ok(qty * px, "qty·px")
        for _, N, _C, _sh, px, *_r in day["buys"]:
            _range_ok(N / px, "N/px")
        days.append(day)
    for j in np.nonzero(shares)[0]:                                                    # engine.py:124-130
        flows[j] = flows.get(j, 0.0) + shares[j] * mark[j] * (1 - s)
    replicated = {tickers[j]: float(v) for j, v in sorted(flows.items(), key=lambda kv: tickers[kv[0]])}
    if replicated != ser["contrib"] or list(replicated) != sorted(ser["contrib"]):     # G5d
        raise _GateFailed("G5", {"series": label, "check": "G5d",
                                 "rule": "float64 flows-chain replication equals symbol_pnl_contribution"})
    for e in eps:                                                                      # G5c
        if e["seg_end"]:
            j = col[e["ticker"]]
            if not (np.float64(e["final_net_mark"]) == shares[j] * mark[j] * one_minus_s):
                raise _GateFailed("G5", {"series": label, "check": "G5c", "ticker": e["ticker"],
                                         "rule": "final_net_mark equals float64 S_T·M_T·(1 − s)"})
    return {"days": days, "final": {j: (_fx(shares[j]), _fx(mark[j])) for j in np.nonzero(shares)[0]},
            "tickers": tickers}


def pnl_function(S_prev, M_prev, q, d, V, S_after, M_now, cost, s, last) -> Fraction:
    """Frozen §4 per-ticker P&L for one session, exact (exposed for hand-checked tests)."""
    S_prev, M_prev, q, d, V, S_after, M_now, cost, s = map(Fraction, (S_prev, M_prev, q, d, V, S_after, M_now, cost, s))
    Sp, Mp = S_prev * q, M_prev / q
    return d * S_prev + Sp * (V - Mp) + S_after * (M_now - V) - cost - (s * S_after * M_now if last else 0)


# ------------------------------------------------------------------ §6A bounds (G7, G8)

def sigma_bar(sum_sm: Fraction, h: int) -> Fraction:
    return (U + (1 + U) * gamma(h - 1)) * sum_sm


def daily_tau(days: list, eq: list[Fraction], s: float) -> list[Fraction]:
    """τ_k for every session (frozen §6A.3, §6A.4)."""
    sf = Fraction(s)
    T = len(days) - 1
    out = []
    for i, d in enumerate(days):
        Ek, last = eq[i + 1], i == T
        sig = d["sum_abs_sm"]
        sb = sigma_bar(sig, d["h"])
        tau = Fraction(0)
        if not last:                                                                   # D15-D17 at close k
            tau += sb + U * abs(Ek)
            c_bar_k = abs(Ek - d["sum_sm"]) + sb + U * abs(Ek)
        else:                                                                          # D19
            pre = abs(Ek) / (1 - U) + (1 + U) * sf * (sig + sb)
            tau += sb + U * pre + sf * sb + U * sf * (sig + sb) + U * abs(Ek)
            c_bar_k = (1 + U) * pre + sig + sb
        if i == 0:                                                                     # C̄_0 = E_0 exactly
            cash = Fraction(E0)
        else:                                                                          # D18 and C̄_{k-1}
            p, Ep = days[i - 1], eq[i]
            sbp = sigma_bar(p["sum_abs_sm"], p["h"])
            tau += sbp + U * abs(Ep)
            cash = abs(Ep - p["sum_sm"]) + sbp + U * abs(Ep)
        for Sv, dv in d["divs"]:                                                       # D1, D2
            x = abs(Sv * dv)
            tau += U * x
            cash = (cash + (1 + U) * x) * (1 + U)
            tau += U * cash
        for _, sm in d["splits"]:                                                      # D3
            tau += (2 * U + U * U) * abs(sm)
        for _, qty, px, N, C, partial, pre in d["sells"]:                              # D4-D7
            tau += U * abs(qty * px) + U * abs(N - C)
            cash = (cash + (1 + U) * abs(N - C)) * (1 + U)
            tau += U * cash
            if partial:
                tau += U * abs(pre - qty) * px
        if d["buys"]:                                                                  # D8-D14
            lams = {b[6] for b in d["buys"]}
            if len(lams) != 1 or None in lams:
                raise _GateFailed("G7", {"rule": "one recorded λ per rebalance", "lambdas": sorted(map(repr, lams))})
            lam = lams.pop()
            if not 0 < lam <= 1:
                raise _GateFailed("G7", {"rule": "recorded λ in (0, 1]", "lambda": repr(lam)})
            g = gamma(len(d["buys"]) - 1)                                              # m buys: m − 1 additions
            for _, N, C, sh, px, pre, _l in d["buys"]:
                tau += U * N + U * abs(pre + sh) * px                                  # φ_i, π_i·V
            Ns = sum((b[1] for b in d["buys"]), Fraction(0))
            if lam == 1.0:
                B = Ns
                tau += B * U * (1 + sf) + (1 + U) * (1 + sf) * g * B + U * (1 + U) * (1 + sf) * (1 + g) * B
                tau += U * c_bar_k + sum((U * sf * b[1] for b in d["buys"]), Fraction(0))
            else:
                lf = Fraction(lam)
                Bb = Ns / (lf * (1 - U))
                Pb = (1 + U) ** 2 * (1 + sf) * (1 + g) * Bb
                tau += lf * (Bb * U * (1 + sf) + (1 + U) * (1 + sf) * g * Bb + U * Pb) + Pb * U * lf
                tau += (1 + sf) * U * Ns + sum((U * b[2] for b in d["buys"]), Fraction(0))
        out.append(tau)
    return out


def ticker_tau(rec: dict, contrib: dict, s: float) -> dict[str, Fraction]:
    """τ_j for every universe ticker (frozen §6A.5)."""
    sf, tickers = Fraction(s), rec["tickers"]
    tau, F = {}, {}
    for d in rec["days"]:
        for j, (Sv, dv) in d["div_by_j"].items():                                      # P1, P2
            x = abs(Sv * dv)
            F[j] = (F.get(j, Fraction(0)) + (1 + U) * x) * (1 + U)
            tau[j] = tau.get(j, Fraction(0)) + U * x + U * F[j]
        for j, sm in d["splits"]:                                                      # P3
            tau[j] = tau.get(j, Fraction(0)) + (2 * U + U * U) * abs(sm)
        for j, qty, px, N, C, partial, pre in d["sells"]:                              # P4-P7
            F[j] = (F.get(j, Fraction(0)) + (1 + U) * abs(N - C)) * (1 + U)
            tau[j] = tau.get(j, Fraction(0)) + U * abs(qty * px) + U * abs(N - C) + U * F[j] \
                + (U * abs(pre - qty) * px if partial else 0)
        for j, N, C, sh, px, pre, _l in d["buys"]:                                     # P8-P11
            G = (F.get(j, Fraction(0)) + N) * (1 + U)
            F[j] = (G + C) * (1 + U)
            tau[j] = tau.get(j, Fraction(0)) + U * N + U * abs(pre + sh) * px + U * G + U * F[j]
    for j, (Sv, Mv) in rec["final"].items():                                           # P12-P15
        sm = abs(_range_ok(Sv * Mv, "S·M liquidation"))
        tau[j] = tau.get(j, Fraction(0)) + U * (1 - sf) * sm * (2 + U + (1 + U) ** 2) \
            + U * abs(Fraction(contrib.get(tickers[j], 0.0)))
    return {tickers[j]: v for j, v in tau.items()}


def g8_check(rec: dict, contrib: dict, s: float, universe, label) -> dict:
    """G8: |Σ_k pnl_j,k − symbol_pnl_contribution_j| ≤ τ_j for every universe ticker (absent ticker: value 0, τ_j 0)."""
    tau_j = ticker_tau(rec, contrib, s)
    diffs = {}
    for t in universe:
        j = rec["tickers"].index(t)
        diff = tree_sum(d["pnl"].get(j, Fraction(0)) for d in rec["days"]) - Fraction(contrib.get(t, 0.0))
        tj = tau_j.get(t, Fraction(0))
        if abs(diff) > tj:
            raise _GateFailed("G8", {"series": label, "ticker": t, "abs_difference": _num(abs(diff)),
                                     "tau_j": _num(tj), "conditional": CONDITIONAL_LABEL})
        diffs[t] = (diff, tj)
    return diffs


# ------------------------------------------------------------------ orchestration

def compute(root: Path, spec: Spec, loaders: dict, head_blob, cal_version, log: dict) -> dict:
    rd = Reader(root, spec)
    art = load_artifacts(rd, spec, head_blob, log)
    market = load_market(spec, art, loaders, cal_version, log)
    cost_s = dict(spec.cost_s)
    recs, g4, g5, g7, g8 = {}, 0, 0, {}, {}
    for seg in spec.segments:
        mk = market[seg.id]
        universe = mk["data"].universe
        for c in spec.costs:
            s = cost_s[c]
            for name in SERIES:
                ser = art["series"][(seg.id, c, name)]
                label = [seg.id, c, name]
                for f in ser["fills"]:                     # the engine's s: recorded cost == fl(notional·s) (§6A D5/D10)
                    if not (np.float64(f.cost) == np.float64(f.notional) * s):
                        raise _GateFailed("G7", {"series": label, "rule": "recorded cost equals float64 notional·s",
                                                 "session": f.session, "ticker": f.ticker})
                rec = reconstruct(mk, ser, s, label)
                g4 += len(ser["fills"])
                g5 += len(rec["days"])
                eq = [Fraction(E0)] + [_fx(e) for e in ser["equity"]]
                eps_k = [(eq[i + 1] - eq[i]) - tree_sum(d["pnl"].values()) for i, d in enumerate(rec["days"])]
                tau_k = daily_tau(rec["days"], eq, s)
                bad = [i for i, (e, t) in enumerate(zip(eps_k, tau_k)) if abs(e) > t]
                if bad:
                    i = bad[0]
                    raise _GateFailed("G7", {"series": label, "failing_sessions": len(bad), "first": mk["sessions"][i],
                                             "abs_eps": _num(abs(eps_k[i])), "tau": _num(tau_k[i]),
                                             "conditional": CONDITIONAL_LABEL})
                diffs = g8_check(rec, ser["contrib"], s, universe, label)
                recs[(seg.id, c, name)] = {"rec": rec, "eq": eq, "eps": eps_k, "tau": tau_k}
                g7[tuple(label)] = len(eps_k)
                g8[tuple(label)] = diffs
    log["G4"] = {"fills_checked": g4, "rule": "price == open, in segment, universe ticker, ≤1 fill per ticker-session, "
                                               "no NaN open where held or traded"}
    log["G5"] = {"sessions_checked": g5, "checkpoints": ["G5a", "G5b", "G5c", "G5d"],
                 "note": "integrity checks only; not proof of bit-identical state at every step (§6A.6)"}
    log["G7"] = {"series_sessions_checked": {"/".join(k): v for k, v in g7.items()}, "status": "passed",
                 "conditional": CONDITIONAL_LABEL}
    log["G8"] = {"series_checked": len(g8), "tickers_per_series": len(next(iter(g8.values()))) if g8 else 0,
                 "status": "passed", "conditional": CONDITIONAL_LABEL}
    return {"art": art, "market": market, "recs": recs, "g8": g8}


def attribution_outputs(spec: Spec, res: dict) -> dict:
    """O1, O2, O3 per cost (frozen §5)."""
    out = {}
    for c in spec.costs:
        o1, o2, o3, csvs = {}, {}, {}, {}
        for seg in spec.segments:
            mk = res["market"][seg.id]
            sessions, universe = mk["sessions"], mk["data"].universe
            mo, bo = res["recs"][(seg.id, c, "V2-MOM")], res["recs"][(seg.id, c, "B1")]
            tickers = mo["rec"]["tickers"]
            n = len(sessions)
            a, cc, bb, e, tot = {t: [] for t in universe}, {t: [] for t in universe}, {t: [] for t in universe}, [], []
            for i in range(n):
                Em, Eb = mo["eq"][i], bo["eq"][i]
                pm, pb = mo["rec"]["days"][i]["pnl"], bo["rec"]["days"][i]["pnl"]
                for t in universe:
                    j = tickers.index(t)
                    cv, bv = pm.get(j, Fraction(0)) / Em, pb.get(j, Fraction(0)) / Eb
                    cc[t].append(cv)
                    bb[t].append(bv)
                    a[t].append(cv - bv)
                e.append(mo["eps"][i] / Em - bo["eps"][i] / Eb)
                tot.append((mo["eq"][i + 1] - Em) / Em - (bo["eq"][i + 1] - Eb) / Eb)
                if tree_sum(a[t][i] for t in universe) + e[i] != tot[i]:
                    raise Day30Error(f"§4 exact identity violated at {seg.id} {c} {sessions[i]}")
            seg_tot = {t: (tree_sum(a[t]), tree_sum(cc[t]), tree_sum(bb[t])) for t in universe}
            total, e_tot = tree_sum(tot), tree_sum(e)
            d2 = set(seg.d2)
            o1[seg.id], o2[seg.id] = {}, {}
            for k in spec.ks:
                o1[seg.id][str(k)], o2[seg.id][str(k)] = {}, {}
                for tail in ("best", "worst"):
                    ds = res["art"]["day_sets"][(c, seg.id, k, tail)]
                    idx = sorted(sessions.index(x) for x in ds)
                    in_set = {t: (tree_sum(a[t][i] for i in idx), tree_sum(cc[t][i] for i in idx),
                                  tree_sum(bb[t][i] for i in idx)) for t in universe}
                    e_in = tree_sum(e[i] for i in idx)
                    cells = {
                        "day_set": {"d2_top_two": tree_sum(in_set[t][0] for t in universe if t in d2),
                                    "other_tickers": tree_sum(in_set[t][0] for t in universe if t not in d2),
                                    "engine_residual": e_in},
                        "other_days": {"d2_top_two": tree_sum(seg_tot[t][0] - in_set[t][0] for t in universe if t in d2),
                                       "other_tickers": tree_sum(seg_tot[t][0] - in_set[t][0] for t in universe
                                                                 if t not in d2),
                                       "engine_residual": e_tot - e_in}}
                    if tree_sum(v for r in cells.values() for v in r.values()) != total:
                        raise Day30Error(f"O1 cells do not add up to the total at {seg.id} {c} k={k} {tail}")
                    o1[seg.id][str(k)][tail] = {
                        "day_set_sessions": sorted(ds), "d2_tickers": list(seg.d2),
                        "cells": {r: {col: {"sum": _num(v), "share_of_total": (_num(v / total) if total != 0 else
                                                                                {"undefined": "total is zero"})}
                                       for col, v in row.items()} for r, row in cells.items()},
                        "total": _num(total),
                        "total_definition": "Σ over segment sessions of the exact daily simple active return "
                                            "r_MOM − r_B1 (denominator for the shares only)"}
                    o2[seg.id][str(k)][tail] = {"rows": [
                        {"ticker": t,
                         "active": {"day_set": _num(in_set[t][0]), "other_days": _num(seg_tot[t][0] - in_set[t][0]),
                                    "segment": _num(seg_tot[t][0])},
                         "mom_side": {"day_set": _num(in_set[t][1]), "other_days": _num(seg_tot[t][1] - in_set[t][1]),
                                      "segment": _num(seg_tot[t][1])},
                         "b1_side": {"day_set": _num(in_set[t][2]), "other_days": _num(seg_tot[t][2] - in_set[t][2]),
                                     "segment": _num(seg_tot[t][2])}}
                        for t in sorted(universe)], "order": "ASCII ticker order; no ranking"}
            o3[seg.id] = {}
            for name, ro in (("V2-MOM", mo), ("B1", bo)):
                ab = [abs(x) for x in ro["eps"]]
                imax = max(range(n), key=lambda i: (ab[i], -i))
                ratio = [(ab[i] / ro["tau"][i]) if ro["tau"][i] else (Fraction(0) if ab[i] == 0 else None)
                         for i in range(n)]
                rmax = max(range(n), key=lambda i: (ratio[i], -i))
                o3[seg.id][name] = {
                    "max_abs_eps": {"value": _num(ab[imax]), "session": sessions[imax]},
                    "max_abs_eps_over_tau": {"value": _num(ratio[rmax]), "session": sessions[rmax]},
                    "g7": {"sessions": n, "passed": n},
                    "g8": [{"ticker": t, "tau_j": _num(res["g8"][(seg.id, c, name)][t][1]),
                            "difference": _num(res["g8"][(seg.id, c, name)][t][0]), "passed": True}
                           for t in sorted(universe)]}
            rows = ["session,eps_mom,tau_mom,eps_b1,tau_b1"]
            for i in range(n):
                rows.append(",".join([sessions[i], repr(_num(mo["eps"][i])), repr(_num(mo["tau"][i])),
                                      repr(_num(bo["eps"][i])), repr(_num(bo["tau"][i]))]))
            csvs[f"o3_sessions_{seg.id}.csv"] = ("\n".join(rows) + "\n").encode("utf-8")
        out[c] = {"o1": o1, "o2": o2, "o3": o3, "csv": csvs}
    return out


def _labels(c: str) -> dict:
    return {"cost": c, "cost_label": COST_LABELS.get(c, c), "evidence_label": EVIDENCE_LABEL,
            "conditional_label": CONDITIONAL_LABEL, "outcome_dependence_label": OUTCOME_LABEL,
            "survivor_universe_label": SURVIVOR_LABEL, "descriptive_only": True,
            "decision_rule": "none; no outcome triggers any action, status change or gate (frozen §1)"}


def _payloads(spec: Spec, outs: dict) -> dict[str, bytes]:
    files = {}
    for c in spec.costs:
        for o in ("o1", "o2", "o3"):
            body = {"output": o.upper()} | _labels(c) | {"results": outs[c][o]}
            if o == "o3":
                body["note"] = ("G7/G8 passed under the conditional bounds of §6A; a pass is consistency evidence "
                                "under premises A1 and A4, not proof of exact reconstruction")
            files[f"{c}/{o}.json"] = _canon(body)
        for name, b in outs[c]["csv"].items():
            files[f"{c}/{name}"] = b
    return files


def _write_record(path: Path, record: dict) -> str:
    if path.exists():
        raise Day30Error(f"gate record already exists (write-once): {path}")
    return _dump(path, record)


def run(root: Path, spec: Spec, out_dir: Path, record_path: Path, authorization: str, loaders: dict | None = None,
        head_blob=git_head_blob, cal_version=calendar_version, extra_repro: dict | None = None) -> dict:
    out_dir, record_path = Path(out_dir), Path(record_path)
    if authorization != AUTH_TOKEN:
        raise Day30Error("the --authorization value must be exactly DAY30-ATTRIBUTION-RUN (frozen §10)")
    if out_dir.exists():
        raise Day30Error(f"output directory already exists, refusing to overwrite: {out_dir}")
    if record_path.exists():
        raise Day30Error(f"gate record already exists (write-once): {record_path}")
    loaders = loaders if loaders is not None else real_loaders()
    record = {"task": "DAY-30", "stage": "integrity gates G1-G8 (frozen §6, §6A)", "frozen_commit": FROZEN_COMMIT,
              "frozen_doc_lf_sha256": FROZEN_DOC_LF_SHA256, "environment": fingerprint(),
              "conditional_label": CONDITIONAL_LABEL}

    def abort(gate: str, detail: dict, log: dict):
        record.update(status="ABORTED", failed_gate=gate, detail=detail, passed_gates=log)
        _write_record(record_path, record)
        raise GateAbort(f"{gate}: {detail}")

    log: dict = {}
    try:
        res = compute(root, spec, loaders, head_blob, cal_version, log)
        files = _payloads(spec, attribution_outputs(spec, res))
        log2: dict = {}
        files2 = _payloads(spec, attribution_outputs(spec, compute(root, spec, loaders, head_blob, cal_version, log2)))
    except _GateFailed as e:
        abort(e.gate, e.detail, log)
    except Day30Error as e:                                          # an exact §4/§5 identity failed: fail closed
        abort("internal", {"error": str(e)}, log)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as e:   # unreadable or malformed input: fail closed
        abort("G1-G8", {"error": f"{type(e).__name__}: {e}"}, log)
    if files != files2 or _canon(log) != _canon(log2):
        abort("G6", {"rule": "two in-process executions must produce byte-identical outputs"}, log)
    log["G6"] = {"reads": "I1-I4 via the allow-list and I2 via the verifying loaders", "network": "refused in main",
                 "determinism_in_process": "byte-identical outputs in two executions"}
    record.update(status="PASSED", gates=log)
    record_sha = _write_record(record_path, record)
    tmp = out_dir.parent / f".{out_dir.name}.tmp-{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        hashes = {}
        for rel, b in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
            hashes[rel] = _sha(b)
        summary = {
            "task": "DAY-30", "status": "COMPLETED", "authorization": authorization,
            "evidence_label": EVIDENCE_LABEL, "conditional_label": CONDITIONAL_LABEL,
            "outcome_dependence_label": OUTCOME_LABEL, "survivor_universe_label": SURVIVOR_LABEL,
            "descriptive_only": True, "decision_rule": "none (frozen §1)", "cost_analyses": COST_LABELS,
            "segments": {s.id: {"first": s.first, "last": s.last, "sessions": s.sessions, "d2_tickers": list(s.d2)}
                         for s in spec.segments},
            "ks": list(spec.ks), "gate_record": {"path": str(record_path), "sha256": record_sha},
            "gates": {g: "passed" for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")},
            "conditional_premises": {"A1": "assumed (platform IEEE-754 arithmetic); not checked",
                                     "A4": "premise; not proven; G5a-G5d are integrity checks only",
                                     "D3": "loaded input arrays never recorded; not proven"},
            "reproducibility": {"frozen_commit": FROZEN_COMMIT, "frozen_doc": FROZEN_MD,
                                "frozen_doc_lf_sha256": FROZEN_DOC_LF_SHA256,
                                "approved_prefreeze_lf_sha256": APPROVED_PREFREEZE_LF_SHA256,
                                "environment": fingerprint(),
                                "snapshots": {s.id: res["market"][s.id]["snapshot"] for s in spec.segments},
                                "input_pins_verified": {s.id: res["art"]["summaries"][s.id]["result_files_sha256"]
                                                        for s in spec.segments}} | (extra_repro or {}),
            "result_files_sha256": hashes,
        }
        _dump(tmp / "run_summary.json", summary)
        os.replace(tmp, out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return summary


def verify_frozen_doc(root: Path = ROOT_DIR) -> str:
    """Frozen §10/§12: the frozen file's LF hash, and the approved pre-freeze hash with the two freeze rows reverted."""
    p = Path(root) / FROZEN_MD
    got = lf_sha256(p)
    if got != FROZEN_DOC_LF_SHA256:
        raise Day30Error(f"frozen DAY-30 predeclaration changed: LF SHA-256 {got} != {FROZEN_DOC_LF_SHA256}")
    lines = p.read_bytes().replace(b"\r\n", b"\n").decode("utf-8").split("\n")
    if not (lines[4].startswith("| Status | **FROZEN") and lines[5].startswith("| Freeze |")
            and APPROVED_PREFREEZE_LF_SHA256 in lines[5]):
        raise Day30Error("frozen DAY-30 predeclaration freeze rows are not as frozen")
    lines[4], lines[5] = PREFREEZE_ROWS
    pre = _sha("\n".join(lines).encode("utf-8"))
    if pre != APPROVED_PREFREEZE_LF_SHA256:
        raise Day30Error(f"reverting the freeze rows gives {pre}, not the approved {APPROVED_PREFREEZE_LF_SHA256}")
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authorization", default="", help="must be exactly DAY30-ATTRIBUTION-RUN (frozen §10)")
    a = ap.parse_args(argv)
    if a.authorization != AUTH_TOKEN:
        print("REFUSED: --authorization must be exactly DAY30-ATTRIBUTION-RUN; no input was read", file=sys.stderr)
        return 2
    try:
        verify_frozen_doc()
    except Day30Error as e:
        print(f"REFUSED: {e}; no input was read", file=sys.stderr)
        return 2
    socket.socket.connect = _refuse
    try:
        summary = run(ROOT_DIR, FROZEN_SPEC, DEFAULT_OUT, DEFAULT_RECORD, a.authorization,
                      extra_repro={"git_commit": _git("rev-parse", "HEAD"),
                                   "git_status_porcelain": _git("status", "--porcelain").splitlines()})
    except GateAbort as e:
        print(f"ABORTED: {e}", file=sys.stderr)
        return 1
    except Day30Error as e:
        print(f"DAY-30 REFUSED: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"status": summary["status"], "out": str(DEFAULT_OUT),
                      "result_files_sha256": summary["result_files_sha256"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
