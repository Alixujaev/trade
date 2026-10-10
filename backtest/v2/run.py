"""backtest/v2/run.py: frozen v2 evaluation runner (DAY-19 Research on Stage R; DAY-21 Holdout on Stage H).

    python -m backtest.v2.run --out artifacts/day19/v2                       (Research, default)
    python -m backtest.v2.run --segment holdout --out artifacts/day21/v2     (Holdout: V2-MOM, V2-STR only, §15)

Runs V2-MOM, V2-STR, V2-LRV and benchmarks B1, B2 at 0 / 5 / 10 bps per side on the Research segment
(2017-02-01 .. 2022-12-30, 1490 sessions; warmup 2016-01-04 .. 2017-01-31 as inputs only), the §7 PIT tests,
an in-process determinism check, and gate §13 A/B/C. OFFLINE (socket connections refused). Reads only the Stage R
snapshot and the signed-off v2.0.4 review output; no holdout or forward data exists in either.
All result files are deterministic; volatile provenance (UTC times, command) is written to run_provenance.json only.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata as md
import json
import math
from pathlib import Path
import platform
import socket
import subprocess
import sys

import numpy as np

from acquisition.contract import ROOT_DIR
from backtest.v2 import engine as en
from backtest.v2 import forward as fw
from backtest.v2 import metrics as mt
from backtest.v2 import signals as sg
from acquisition.v2.contract import PROTOCOL_VERSION_21, PROTOCOL_VERSION_22
from acquisition.v2.reevaluate import verify_snapshot
from backtest.v2.data import MarketData, load_stage_f, load_stage_h, load_stage_r, tr_index

RESEARCH_FIRST, RESEARCH_LAST = date(2017, 2, 1), date(2022, 12, 30)
EXPECTED_RESEARCH, EXPECTED_WARMUP = 1490, 272
COSTS = {"0bps": 0.0, "5bps": 0.0005, "10bps": 0.0010}
FAMILIES = ("V2-MOM", "V2-STR", "V2-LRV")
EXPERIMENT = {"V2-MOM": "V2-MOM-R001", "V2-STR": "V2-STR-R001", "V2-LRV": "V2-LRV-R001",
              "B1": "V2-B1-research", "B2": "V2-B2-research"}
PROTOCOL_FILES = ("artifacts/day16/research-protocol-v2.md", "artifacts/day16/research-protocol-v2.json",
                  "artifacts/day16/research-checklist.json")
FREEZE_COMMIT = "ba3cefe54ccf2fe14c62f1c609f143d8a0904221"
DEFINITIONS = "artifacts/day19/day19-predeclared-definitions.json"
SEGMENTS = {
    "research": {"id": "research", "first": RESEARCH_FIRST, "last": RESEARCH_LAST, "sessions": EXPECTED_RESEARCH,
                 "inputs_before": EXPECTED_WARMUP, "families": FAMILIES, "experiment": EXPERIMENT,
                 "status_prefix": "RESEARCH", "task": "DAY-19", "loader": load_stage_r},
    # §15: one-shot holdout of every research-passed family (DAY-19 sign-off 48ce878); V2-LRV never run (§15.3)
    "holdout": {"id": "holdout", "first": date(2023, 1, 3), "last": date(2026, 6, 2), "sessions": 856,
                "inputs_before": 503, "families": ("V2-MOM", "V2-STR"),
                "experiment": {"V2-MOM": "V2-MOM-H001", "V2-STR": "V2-STR-H001", "B1": "V2-B1-holdout",
                               "B2": "V2-B2-holdout"},
                "status_prefix": "HOLDOUT", "task": "DAY-21", "loader": load_stage_h},
    # Protocol 2.1 (DAY-26B, artifacts/day26b/protocol-v2.1-amendment.md): one 63-session forward window split
    # 21 + 42, never pooled. Only V2-MOM is eligible (V2-STR HOLDOUT-FAILED, V2-LRV RESEARCH-FAILED). Both segments are
    # loaded by load_stage_f only after backtest.v2.forward.check_forward_access (adoption commit + earliest time).
    "fwd-diag": {"id": "fwd-diag", "first": date(2026, 10, 8), "last": date(2026, 11, 5), "sessions": 21,
                 "inputs_before": 442, "families": ("V2-MOM",),
                 "experiment": {"V2-MOM": "V2-MOM-F002-DIAG", "B1": "V2-B1-fwd-diag", "B2": "V2-B2-fwd-diag"},
                 "status_prefix": "FWD-DIAG", "kind": "diagnostic", "task": "DAY-26B", "loader": None},
    "fwd-gate": {"id": "fwd-gate", "first": date(2026, 11, 6), "last": date(2027, 1, 7), "sessions": 42,
                 "inputs_before": 463, "families": ("V2-MOM",),
                 "experiment": {"V2-MOM": "V2-MOM-F002", "B1": "V2-B1-fwd-gate", "B2": "V2-B2-fwd-gate"},
                 "status_prefix": "FORWARD42", "kind": "gate", "task": "DAY-26B", "loader": None},
    # Protocol 2.2 (DAY-26D, artifacts/day26d/protocol-v2.2-amendment.md): fwd-diag invalid (DAY-26C), fwd-gate
    # superseded; the clean 42-session gate below excludes the exposed sessions 2026-10-08/09 from its sample.
    "fwd-gate2": {"id": "fwd-gate2", "first": date(2026, 10, 12), "last": date(2026, 12, 9), "sessions": 42,
                  "inputs_before": 444, "families": ("V2-MOM",),
                  "experiment": {"V2-MOM": "V2-MOM-F003", "B1": "V2-B1-fwd-gate2", "B2": "V2-B2-fwd-gate2"},
                  "status_prefix": "FORWARD42", "kind": "gate", "task": "DAY-26D", "loader": None,
                  "protocol_version": PROTOCOL_VERSION_22},
}
RESEARCH_CONFIG_SHA256 = {   # §15.7: holdout/forward must use the identical frozen configuration
    "V2-MOM": "62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0",
    "V2-STR": "0fc76b8a9ba8250c8fa1b399871ca6f511d5e0283f0ffe94f9085f0e38aa600e",
    "V2-LRV": "0beffbe1ca5de4d52100fc34c6d42fe03b6bdce5a597d8d1fb17b38429105864",
}
ROBUSTNESS_ITEMS = {   # §16 completeness set (Gate C), per cost scenario
    "1_cost_sensitivity": ["cagr", "total_return"],
    "2_calendar_years": ["calendar_years"],
    "3_breadth_concentration": ["symbol_breadth", "top2_concentration", "weight_hhi"],
    "4_turnover_lambda_cost_drag": ["annual_turnover", "turnover_per_execution_mean", "mean_lambda", "min_lambda",
                                    "cost_drag"],
    "5_exposure_benchmark_relative": ["exposure", "b1_cagr", "b2_cagr", "cagr_minus_b1", "tracking_error_b1",
                                      "information_ratio_b1"],
    "6_drawdown_profile": ["max_drawdown", "worst_month", "worst_year"],
    "7_statistical_diagnostic": ["hac_tstat_active_vs_b1", "holm_adjusted_p"],
}


def _refuse(*_a, **_k):
    raise RuntimeError("network access is forbidden during frozen v2 evaluation")


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _dump(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, default=_jsonable) + "\n").encode("utf-8")
    path.write_bytes(b)
    return _sha_bytes(b)


def _jsonable(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))


def _csv(path: Path, header: list[str], rows: list[list]) -> str:
    lines = [",".join(header)] + [",".join("" if v is None else repr(v) if isinstance(v, float) else str(v) for v in r)
                                  for r in rows]
    b = ("\n".join(lines) + "\n").encode("utf-8")
    path.write_bytes(b)
    return _sha_bytes(b)


class Setup:
    def __init__(self, data: MarketData, seg: dict | None = None):
        import exchange_calendars as xcals
        self.seg = seg or SEGMENTS["research"]
        self.data = data
        self.tr = tr_index(data)
        self.seg_first, self.seg_last = data.index_of(self.seg["first"]), data.index_of(self.seg["last"])
        cal = xcals.get_calendar("XNYS", start="2015-12-01", end="2027-12-31")   # covers the 2.1 forward window
        self.next_session = cal.next_session(self.seg["last"].isoformat()).date()   # calendar rule only, no market data
        self.universe = [data.col(t) for t in data.universe]
        self.month = sg.decision_sessions(sg.month_end_flags(data.sessions, self.next_session), self.seg_first, self.seg_last)
        self.week = sg.decision_sessions(sg.iso_week_end_flags(data.sessions, self.next_session), self.seg_first, self.seg_last)


def run_family(st: Setup, fam: str, s: float, data: MarketData | None = None, tr: np.ndarray | None = None,
               upto: int | None = None) -> en.Result:
    data = data or st.data
    tr = st.tr if tr is None else tr
    uni = [data.col(t) for t in data.universe]
    if fam == "V2-MOM":
        return en.simulate_targets(data, lambda t: sg.mom_targets(tr, t, uni, data.tickers), st.month, s,
                                   st.seg_first, st.seg_last, fam, upto)
    if fam == "V2-STR":
        return en.simulate_targets(data, lambda t: sg.str_targets(tr, t, uni, data.tickers), st.week, s,
                                   st.seg_first, st.seg_last, fam, upto)
    if fam == "V2-LRV":
        return en.simulate_lrv(data, tr, s, st.seg_first, st.seg_last, fam, upto)
    if fam == "B1":
        def b1(t):
            have = [j for j in uni if not math.isnan(data.open[st.seg_first, j])]
            return {j: 1.0 / len(have) for j in have}
        return en.simulate_targets(data, b1, [st.seg_first - 1], s, st.seg_first, st.seg_last, fam, upto)
    if fam == "B2":
        spy = data.col("SPY")
        return en.simulate_targets(data, lambda t: {spy: 1.0}, [st.seg_first - 1], s, st.seg_first, st.seg_last, fam, upto)
    raise ValueError(fam)


# ------------------------------------------------------------------ §7 PIT tests

def _mutate(data: MarketData, t: int, delete: bool) -> MarketData:
    op, cl, q, d = data.open.copy(), data.close.copy(), data.q.copy(), data.d.copy()
    if delete:
        op[t + 1:], cl[t + 1:] = np.nan, np.nan
        q[t + 1:], d[t + 1:] = 1.0, 0.0
    else:
        k = np.arange(len(data.sessions))[t + 1:, None]
        f = 1.0 + 0.5 * np.sin(0.37 * k + np.arange(len(data.tickers))[None, :])
        op[t + 1:] *= f
        cl[t + 1:] *= f[::-1]
        d[t + 1:] = d[t + 1:] * 3.0 + 0.11
        if t + 1 < len(q):
            q[t + 1] = 2.0
    return MarketData(data.sessions, data.tickers, op, cl, q, d)


def _decisions_upto(res: en.Result, t_iso: str) -> list:
    return [x for x in res.decisions if x["close"] <= t_iso]


def pit_tests(st: Setup, full: dict[str, en.Result]) -> dict:
    data, out = st.data, {}
    # 4. index test: TR on data truncated at k equals the full TR
    ks = list(range(0, len(data.sessions), 50)) + [len(data.sessions) - 1]
    idx_ok = all(np.array_equal(tr_index(data.truncate(k)), st.tr[:k + 1], equal_nan=True) for k in ks)
    out["index_test"] = {"pass": idx_ok, "sessions_checked": len(ks)}
    # 1./2. future-mutation and truncation tests on each family's decision log
    for fam in st.seg["families"]:
        if fam == "V2-LRV":
            sched = list(range(st.seg_first - 1, st.seg_last))
        else:
            sched = st.month if fam == "V2-MOM" else st.week
        sample = sorted(set(sched[::10]) | {sched[0], sched[-1]})
        trunc_ok = mut_ok = del_ok = True
        for t in sample:
            t_iso = data.sessions[t].isoformat()
            ref = _decisions_upto(full[fam], t_iso)
            dt = data.truncate(t)
            r_t = run_family(st, fam, 0.0005, dt, tr_index(dt), upto=t)
            trunc_ok &= _decisions_upto(r_t, t_iso) == ref
            for delete in (False, True):
                dm = _mutate(data, t, delete)
                r_m = run_family(st, fam, 0.0005, dm, tr_index(dm), upto=t if delete else None)
                same = _decisions_upto(r_m, t_iso) == ref
                if delete:
                    del_ok &= same
                else:
                    mut_ok &= same
        out[fam] = {"decision_sessions_sampled": len(sample), "truncation_test": trunc_ok,
                    "future_mutation_test": mut_ok, "future_deletion_test": del_ok}
    # 3. fill-source test: every fill = the raw open of its session, executed after its decision close
    pos = {s.isoformat(): i for i, s in enumerate(data.sessions)}
    fill_ok, n_fills, timing_ok = True, 0, True
    for key, res in full.items():
        dec_closes = {x["close"] for x in res.decisions if "discarded" not in x}
        for f in res.fills:
            n_fills += 1
            k, j = pos[f["session"]], data.col(f["ticker"])
            fill_ok &= f["price"] == data.open[k, j] and not math.isnan(f["price"])
            timing_ok &= data.sessions[k - 1].isoformat() in dec_closes or res.label == "V2-LRV" and \
                (k - st.seg_first) % sg.LRV_PERIOD == 0
            timing_ok &= st.seg["first"].isoformat() <= f["session"] <= st.seg["last"].isoformat()
    out["fill_source_test"] = {"pass": fill_ok, "fills_checked": n_fills, "series": "raw open (series A)"}
    out["execution_timing_test"] = {"pass": timing_ok, "rule": "every fill at the open after its decision close "
                                    "(LRV period-end exits at the next cycle start); all fills inside the segment"}
    out["all_pass"] = idx_ok and fill_ok and timing_ok and all(
        v["truncation_test"] and v["future_mutation_test"] and v["future_deletion_test"] for f, v in out.items()
        if f in st.seg["families"])
    return out


# ------------------------------------------------------------------ reproducibility

def _git(*a) -> str:
    return subprocess.run(["git", *a], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout.strip()


def strategy_config_sha(protocol: dict, fam: str) -> str:
    blob = {"family": fam, "strategies." + fam: protocol["strategies"][fam], "price_series": protocol["price_series"],
            "execution": protocol["execution"], "costs": protocol["costs"], "portfolio": protocol["portfolio"]}
    return _sha_bytes(json.dumps(blob, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def environment() -> dict:
    dists = sorted(f"{d.metadata['Name']}=={d.version}" for d in md.distributions() if d.metadata["Name"])
    import exchange_calendars
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "exchange_calendars": exchange_calendars.__version__, "numpy": np.__version__,
            "distributions_sha256": _sha_bytes("\n".join(dists).encode()), "distributions_count": len(dists)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--segment", choices=sorted(SEGMENTS), default="research")
    ap.add_argument("--snapshot", help="Stage F snapshot id (protocol-2.1 forward segments only)")
    ap.add_argument("--expect-manifest-sha256", help="Stage F snapshot manifest SHA-256 (forward segments only)")
    ap.add_argument("--authorization", default="", help="explicit run authorization reference (forward segments only)")
    a = ap.parse_args(argv)
    seg = SEGMENTS[a.segment]
    FAMILIES, EXPERIMENT = seg["families"], seg["experiment"]
    forward = seg.get("kind") in ("diagnostic", "gate")
    socket.socket.connect = _refuse
    started = datetime.now(timezone.utc).isoformat()
    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT_DIR / out
    access = None
    if forward:                       # protocol 2.1: every precondition before any forward file is opened
        if not a.authorization.strip():
            print("REFUSED: --authorization is required for a forward segment; no data was loaded", file=sys.stderr)
            return 2
        try:
            access = fw.check_forward_access(seg["id"])
        except fw.ForwardAccessRefused as e:
            print(f"REFUSED: {e}; no data was loaded", file=sys.stderr)
            return 2
        if out.exists():
            print(f"REFUSED: output directory exists (write-once): {out}", file=sys.stderr)
            return 2
        data, data_info = load_stage_f(seg["id"], a.snapshot, a.expect_manifest_sha256)
    else:
        data, data_info = seg["loader"]()
    st = Setup(data, seg)
    n_research = st.seg_last - st.seg_first + 1
    if n_research != seg["sessions"] or st.seg_first != seg["inputs_before"]:
        raise SystemExit(f"session count mismatch: {seg['id']} {n_research}, inputs before {st.seg_first}")
    protocol = json.loads((ROOT_DIR / PROTOCOL_FILES[1]).read_text(encoding="utf-8"))

    results: dict[str, dict[str, en.Result]] = {c: {} for c in COSTS}
    for c, s in COSTS.items():
        for fam in FAMILIES + ("B1", "B2"):
            results[c][fam] = run_family(st, fam, s)
    # in-process determinism (§13.A3): a second identical simulation must give identical logs and equity
    determinism = {}
    for c, s in COSTS.items():
        for fam in FAMILIES + ("B1", "B2"):
            r2 = run_family(st, fam, s)
            r1 = results[c][fam]
            determinism[f"{fam}@{c}"] = (r1.fills == r2.fills and r1.equity == r2.equity
                                         and r1.decisions == r2.decisions and r1.executions == r2.executions)
    pit = pit_tests(st, results["5bps"])
    stage_dir = {"research": "stage_r", "holdout": "stage_h"}.get(seg["id"], "stage_f")
    post = verify_snapshot(ROOT_DIR / "data/oos_cache/protocol_v2" / stage_dir / data_info["snapshot_id"],
                           data_info["manifest_sha256"])
    snapshot_unchanged = post["tree_sha256"] == data_info["tree_sha256"]

    metrics = {c: {f: mt.compute(results[c][f], results[c]["B1"], results[c]["B2"]) for f in FAMILIES}
               | {b: mt.compute(results[c][b], None, None) for b in ("B1", "B2")} for c in COSTS}
    for c in COSTS:
        ps = {f: metrics[c][f]["hac_p_value"] for f in FAMILIES if isinstance(metrics[c][f]["hac_p_value"], float)}
        adj = mt.holm(ps)
        for f in FAMILIES:
            metrics[c][f]["holm_adjusted_p"] = adj.get(f, mt.undefined("HAC p-value undefined"))
    for f in FAMILIES + ("B1", "B2"):
        for c in ("5bps", "10bps"):
            metrics[c][f]["cost_drag"] = metrics["0bps"][f]["cagr"] - metrics[c][f]["cagr"]
        metrics["0bps"][f]["cost_drag"] = 0.0
    if forward:                       # every calendar year of a forward segment is partial (2.1 §8; P1 precedent)
        for c in COSTS:
            for f in FAMILIES + ("B1", "B2"):
                res, m = results[c][f], metrics[c][f]
                for y, row in m["calendar_years"].items():
                    days = [s for s in res.sessions if s.startswith(y)]
                    row["label"] = f"partial ({days[0]}..{days[-1]})"
                m["worst_year"]["note"] = "every calendar year in a protocol-2.1 forward segment is partial"
                if seg["kind"] == "diagnostic":
                    m["cagr_label"] = fw.DIAG_CAGR_LABEL

    gate_a = {"look_ahead_tests_pass": pit["all_pass"], "data_integrity": snapshot_unchanged,
              "deterministic": all(determinism.values()),
              "reproducibility_block_complete": True, "execution_accounting_semantics": pit["fill_source_test"]["pass"]
              and pit["execution_timing_test"]["pass"], "complete_dataset": data_info["missing_bars"] == 0}
    gates = {}
    diagnostic = fw.diagnostic_report(metrics, gate_a, data_info) if seg.get("kind") == "diagnostic" else None
    for f in (() if diagnostic else FAMILIES):                       # fwd-diag is never gated (2.1 §7)
        m5 = metrics["5bps"][f]
        g1 = m5["cagr"] >= 0.0
        g2 = m5["cagr"] >= metrics["5bps"]["B1"]["cagr"]
        missing = {c: [it for it, keys in ROBUSTNESS_ITEMS.items() for k in keys if k not in metrics[c][f]] for c in COSTS}
        a_ok = all(gate_a.values())
        c_ok = not any(missing.values())
        px = seg["status_prefix"]
        status = (f"{px}-FAILED (methodological)" if not a_ok else f"{px}-FAILED (economic)" if not (g1 and g2)
                  else f"{px}-FAILED (incomplete)" if not c_ok else f"{px}-PASSED")
        gates[f] = {"A_methodological": "PASS" if a_ok else "FAIL",
                    "B1_net_cagr_5bps_ge_0": g1, "B2_net_cagr_5bps_ge_B1": g2,
                    "net_cagr_5bps": m5["cagr"], "b1_net_cagr_5bps": metrics["5bps"]["B1"]["cagr"],
                    "B_economic": "PASS" if (g1 and g2) else "FAIL",
                    "C_completeness": "PASS" if c_ok else "FAIL", "C_missing_items": missing, "status": status}

    files: dict[str, str] = {}
    for c in COSTS:
        for key in FAMILIES + ("B1", "B2"):
            res, d = results[c][key], out / EXPERIMENT[key] / c
            files[f"{EXPERIMENT[key]}/{c}/metrics.json"] = _dump(d / "metrics.json", metrics[c][key])
            files[f"{EXPERIMENT[key]}/{c}/decisions.json"] = _dump(d / "decisions.json", res.decisions)
            files[f"{EXPERIMENT[key]}/{c}/executions.json"] = _dump(d / "executions.json", res.executions)
            files[f"{EXPERIMENT[key]}/{c}/episodes.json"] = _dump(d / "episodes.json", res.episodes)
            files[f"{EXPERIMENT[key]}/{c}/fills.csv"] = _csv(
                d / "fills.csv", ["session", "ticker", "side", "shares", "price", "notional", "cost", "lambda", "slot"],
                [[f["session"], f["ticker"], f["side"], f["shares"], f["price"], f["notional"], f["cost"],
                  f.get("lambda"), f.get("slot")] for f in res.fills])
            files[f"{EXPERIMENT[key]}/{c}/equity.csv"] = _csv(
                d / "equity.csv", ["session", "equity", "exposure", "n_held"],
                [[s, e, x, n] for s, e, x, n in zip(res.sessions, res.equity, res.exposure, res.n_held)])
    git_status = _git("status", "--porcelain", "--untracked-files=all").splitlines()
    repro = {
        "protocol_version": "2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4", "freeze_commit": FREEZE_COMMIT,
        "protocol_files_sha256": {p: _sha_bytes((ROOT_DIR / p).read_bytes()) for p in PROTOCOL_FILES},
        "predeclared_definitions_sha256": _sha_bytes((ROOT_DIR / DEFINITIONS).read_bytes()),
        "git_commit": _git("rev-parse", "HEAD"),
        "data": data_info | ({"stage": "R", "corporate_action_endpoint": "/v1/corporate-actions (Stage R acquisition)"}
                             if seg["id"] == "research" else
                             {"stage": "H", "corporate_action_endpoint": "/v1/corporate-actions (Stage H acquisition, DAY-20)"}
                             if seg["id"] == "holdout" else
                             {"stage": "F", "corporate_action_endpoint": "/v1/corporate-actions (Stage F acquisition, DAY-26B)"}),
        "strategy_config_sha256": {f: strategy_config_sha(protocol, f) for f in FAMILIES},
        "random_seeds": None,
        "engine_sha256": {f"backtest/v2/{p.name}": _sha_bytes(p.read_bytes())
                          for p in sorted((ROOT_DIR / "backtest" / "v2").glob("*.py"))},
    }
    summary = {
        "schema_version": "1.0", "task": seg["task"], "segment": {"id": seg["id"], "first": seg["first"].isoformat(),
                   "last": seg["last"].isoformat(), "sessions": n_research},
        "warmup": {"first": data.sessions[0].isoformat(), "last": data.sessions[st.seg_first - 1].isoformat(),
                   "sessions": st.seg_first},
        "decision_counts": {"V2-MOM": len(st.month), "V2-STR": len(st.week)}
                           | ({"V2-LRV_cycles": len(range(st.seg_first, st.seg_last + 1, sg.LRV_PERIOD))}
                              if "V2-LRV" in FAMILIES else {}),
        "holdout_or_forward_data_read": False, "last_session_loaded": data.sessions[-1].isoformat(),
        "gate_A_checks": gate_a, "determinism_in_process": determinism, "pit_tests": pit, "gates": gates,
        "headline": {c: {f: {"cagr": metrics[c][f]["cagr"], "total_return": metrics[c][f]["total_return"],
                             "ending_equity": metrics[c][f]["ending_equity"]} for f in FAMILIES + ("B1", "B2")}
                     for c in COSTS},
        "reproducibility": repro, "result_files_sha256": files,
    }
    if forward:
        repro["protocol_version"] = seg.get("protocol_version", PROTOCOL_VERSION_21)
        repro["forward_access"] = access
        repro["authorization"] = a.authorization
        summary["holdout_or_forward_data_read"] = True
        summary["protocol_version"] = repro["protocol_version"]
        summary["segments_pooled"] = False
        summary["sample"] = (f"{seg['id']} sessions {seg['first'].isoformat()}..{seg['last'].isoformat()} only; "
                             "earlier sessions are formation inputs, never part of the sample")
        if diagnostic:
            summary["diagnostic"] = diagnostic
            summary["headline_cagr_label"] = fw.DIAG_CAGR_LABEL
    if seg["id"] != "research":
        cfg = summary["reproducibility"]["strategy_config_sha256"]
        summary["config_identical_to_research"] = {f: cfg[f] == RESEARCH_CONFIG_SHA256[f] for f in FAMILIES}
        summary["families_not_run"] = (
            {"V2-LRV": "RESEARCH-FAILED (economic); never run on the holdout (§15.3)"} if not forward else
            {"V2-STR": "HOLDOUT-FAILED (economic); not eligible for the forward stage (§15.10)",
             "V2-LRV": "RESEARCH-FAILED (economic); never run after research (§15.3)"})
        if not all(summary["config_identical_to_research"].values()):
            raise SystemExit("strategy-config SHA-256 differs from the research configuration (§15.7)")
    files_sha = _dump(out / "run_summary.json", summary)
    _dump(out / "run_provenance.json", {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                                         "command": " ".join([sys.executable, "-m", "backtest.v2.run", *sys.argv[1:]]),
                                         "cwd": str(Path.cwd()), "environment": environment(),
                                         "git_status_porcelain": git_status, "git_dirty": bool(git_status),
                                         "run_summary_sha256": files_sha})
    print(json.dumps({"out": str(out), "gates": {f: gates[f]["status"] for f in gates},
                      "diagnostic_status": diagnostic["status"] if diagnostic else None,
                      "pit_all_pass": pit["all_pass"], "deterministic": all(determinism.values()),
                      "run_summary_sha256": files_sha}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
