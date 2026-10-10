"""acquisition/v2/stage_f.py: protocol 2.1 Stage F (forward) acquisition and data validation (DAY-26B).

    python -m acquisition.v2.stage_f --dry-run --segment fwd-diag
    python -m acquisition.v2.stage_f --capture --segment fwd-diag --authorization "<reference>"
    python -m acquisition.v2.stage_f --validate <snapshot_id> --segment fwd-diag --expect-manifest-sha256 <sha>
                                     [--diag-snapshot <id> --diag-manifest-sha256 <sha>] [--out <dir>]

Protocol 2.1 (artifacts/day26b/protocol-v2.1-amendment.md; acquisition parameters in protocol-v2.1-adoption.json):
- F-D (fwd-diag): raw + all 1Day bars and corporate actions 2025-01-02 -> 2026-11-05, acquired once, not before
  2026-11-05 16:15 America/New_York. F-G (fwd-gate): 2025-01-02 -> 2027-01-07, once, not before 2027-01-07 16:15.
- Nothing dated after the segment's last session is requested or persisted (bars: hard request bound; corporate
  actions: event_date boundary with in-memory discard and counts only, v2.0.1 C1 precedent).
- Capture and validation both refuse (backtest.v2.forward.check_forward_access) unless protocol 2.1 is adopted and
  committed and the segment's earliest time has passed. The checks run before any client or network object exists.

DATA ONLY: no signal, TR index, return, portfolio, metric or gate is computed; no price is printed or reported.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
from typing import Any, Callable

from acquisition.contract import ROOT_DIR
from acquisition.v2 import review_records as rr
from acquisition.v2 import reviews as rv
from acquisition.v2 import stage_h as sh
from acquisition.v2 import stage_r as sr
from acquisition.v2.bars_client import DailyBarsClient
from acquisition.v2.ca_client import CorporateActionsClient
from acquisition.v2.contract import (
    CA_DATA_QUALITY, FORWARD_SEGMENTS, PROTOCOL_VERSION, PROTOCOL_VERSION_004, PROTOCOL_VERSION_21,
    REVIEW_RECORDS_DIR_F, SCHEMA_VERSION, STAGE_F_FIRST_SESSION, STAGE_F_ROOT, STAGE_H_ROOT, ca_query_symbols,
    stage_r_symbols,
)
from acquisition.v2.http import HttpClient
from acquisition.v2.reevaluate import verify_snapshot
from acquisition.v2.sessions import stage_f_sessions
from backtest.v2.forward import ForwardAccessRefused, check_forward_access, check_snapshot_immutable, segment_window

STAGE = "stage_f"
READY = "READY_FOR_FORWARD_EVALUATION"
OVERLAP_H = ("2025-01-02", "2026-06-02")                   # H∩F (frozen §3.9 overlap control)
STAGE_H_SNAPSHOT = "stage_h_20261008T100604Z"
STAGE_H_MANIFEST_SHA256 = "eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34"


def params(seg_id: str) -> dict[str, Any]:
    """Acquisition parameters recorded in the protocol-2.1 adoption record (DAY-20 decision precedent)."""
    first, last, n = segment_window(seg_id)
    last_iso = last.isoformat()
    return {"segment": seg_id, "segment_first": first, "segment_last": last, "segment_sessions": n,
            "range": (STAGE_F_FIRST_SESSION, last), "asof": last_iso,
            "ca_windows": {"Q1": ("2025-01-01", last_iso)},
            "event_min": STAGE_F_FIRST_SESSION.isoformat(), "event_max": last_iso,
            "snapshot_prefix": f"stage_f_{seg_id}_"}


def existing_snapshots(seg_id: str, root: Path = STAGE_F_ROOT) -> list[str]:
    pre = params(seg_id)["snapshot_prefix"]
    return sorted(p.name for p in Path(root).glob(pre + "*") if p.is_dir()) if Path(root).is_dir() else []


def capture(seg_id: str, *, http_factory: Callable[[], HttpClient], env: dict[str, Any], root: Path = STAGE_F_ROOT,
            now: datetime | None = None, snapshot_id: str | None = None,
            log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    access = check_forward_access(seg_id, now)                  # adoption commit + earliest time; nothing touched yet
    if existing_snapshots(seg_id, root):
        raise FileExistsError(f"Stage F for {seg_id} was already acquired (acquired once): {existing_snapshots(seg_id, root)}")
    p = params(seg_id)
    sr.check_location(root)
    sessions = stage_f_sessions(p["segment_last"])
    syms = stage_r_symbols()
    snapshot_id = snapshot_id or p["snapshot_prefix"] + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = Path(root) / snapshot_id
    sr.check_location(snap)
    started = datetime.now(timezone.utc).isoformat()
    http = http_factory()
    requests_log: list[dict[str, Any]] = []
    bars = DailyBarsClient(http, asof=p["asof"], first_session=STAGE_F_FIRST_SESSION, last_session=p["segment_last"])
    frames: dict[str, dict[str, Any]] = {"raw": {}, "all": {}}
    for adj in ("raw", "all"):
        for s in syms:
            df, rec = bars.fetch(s, adj)
            frames[adj][s] = df
            requests_log.append({"kind": "bars", **rec})
        log(f"bars {adj}: {len(frames[adj])} symbols")
    ca_client = CorporateActionsClient(http)
    q_syms = ca_query_symbols()
    ca: dict[str, list[dict[str, Any]]] = {q: [] for q in CA_DATA_QUALITY}
    ca_counts: dict[str, Any] = {}
    for q in CA_DATA_QUALITY:
        for w in p["ca_windows"]:
            kept, rec = ca_client.fetch_window(w, q, q_syms, windows=p["ca_windows"], event_min=p["event_min"],
                                               event_max=p["event_max"], stage=STAGE)
            ca[q].extend(kept)
            ca_counts[f"{w}_{q}"] = rec["counts"]
            requests_log.append({"kind": "corporate_actions", **rec})
    for q in CA_DATA_QUALITY:
        uniq: dict[str, dict[str, Any]] = {}
        for r in ca[q]:
            rid = str(r.get("id"))
            if rid in uniq and uniq[rid] != r:
                raise sh.DataValidationIssue(f"corporate action id {rid} returned with different content across windows")
            uniq[rid] = r
        ca[q] = [uniq[k] for k in sorted(uniq)]
    extra = sh.unqueried_aliases(ca["complete"] + ca["all"], q_syms)
    if extra:
        raise sh.DataValidationIssue(f"name change into a universe symbol from unqueried alias(es) {extra} (C2 rule 2)")
    d = sh.derive(frames, ca, q_syms, ca_counts, sessions=sessions, segment_first=p["segment_first"])
    ca_payloads = {q: {"records": ca[q], "boundary": {"event_date_min": p["event_min"], "event_date_max": p["event_max"]},
                       "counts_by_window": {w: ca_counts[f"{w}_{q}"] for w in p["ca_windows"]}} for q in CA_DATA_QUALITY}
    leak = sh.assert_no_leakage_h(ca_payloads, d["normalised"], d["identity"], d["crosscheck"], d["reviews"],
                                  lo=p["event_min"], hi=p["event_max"])
    from acquisition.v2.sessions import session_of_label
    files: dict[str, str] = {}
    details: dict[str, Any] = {}
    for adj in ("raw", "all"):
        for s, df in frames[adj].items():
            out = df.copy()
            out["session_date"] = [session_of_label(t)[0].isoformat() for t in out.index]
            if len(out) and out["session_date"].max() > p["event_max"]:
                raise sr.LeakageError(f"{s} {adj}: bar after the segment's last session")
            name = f"bars_{adj}/{s}.parquet"
            files[name] = sr.write_parquet_once(snap / name, out)
            details[name] = {"symbol": s, "series": f"adjustment={adj}", "rows": int(len(out)),
                             "first_session": out["session_date"].min() if len(out) else None,
                             "last_session": out["session_date"].max() if len(out) else None,
                             "bytes": (snap / name).stat().st_size}
    jsons = {"corporate_actions_complete.json": ca_payloads["complete"], "corporate_actions_all.json": ca_payloads["all"],
             "events_normalised.json": d["normalised"], "identity.json": d["identity"],
             "data_quality_comparison.json": d["quality"], "validation.json": d["validation"],
             "crosscheck.json": d["crosscheck"], "reviews.json": d["reviews"], "environment.json": env}
    for name, obj in jsons.items():
        files[name] = sr.write_json_once(snap / name, obj)
        details[name] = {"bytes": (snap / name).stat().st_size}
    run = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION_21, "stage": "F", "segment": seg_id,
           "snapshot_id": snapshot_id, "asof": p["asof"], "forward_access": access,
           "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "symbols": syms,
           "ca_query_symbols": q_syms, "sessions": len(sessions),
           "session_range": [sessions[0].isoformat(), sessions[-1].isoformat()],
           "segment_range": [p["segment_first"].isoformat(), p["segment_last"].isoformat(), p["segment_sessions"]],
           "ca_windows": p["ca_windows"], "ca_counts": ca_counts, "assets_endpoint_called": False,
           "requests": requests_log, "leakage_dates_checked": leak}
    files["run.json"] = sr.write_json_once(snap / "run.json", run)
    details["run.json"] = {"bytes": (snap / "run.json").stat().st_size}
    manifest = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION_21, "stage": "F", "segment": seg_id,
                "snapshot_id": snapshot_id, "files_sha256": files, "file_details": details,
                "provider": {"bars": "alpaca-market-data-v2 /v2/stocks/bars feed=sip timeframe=1Day",
                             "corporate_actions": "alpaca-market-data-v1 /v1/corporate-actions"},
                "acquired_utc": started, "asof": p["asof"],
                "usable_for_research": d["reviews"]["usable_for_research"],
                "review_status_counts": d["reviews"]["status_counts"],
                "validation_status_counts": d["validation"]["status_counts"],
                "crosscheck_blocking_symbols": d["crosscheck"]["blocking_symbols"],
                "identity_counts": d["identity"]["counts"], "event_counts": d["normalised"]["counts"],
                "data_quality_blocking": d["quality"]["blocking"]}
    sr.write_json_once(snap / "manifest.json", manifest)
    return {"status": "WRITTEN", "snapshot_id": snapshot_id, "snapshot_dir": str(snap), "manifest": manifest,
            "requests": len(requests_log)}


# ------------------------------------------------------------------ offline validation

def validate(seg_id: str, snapshot_id: str, expect_manifest_sha256: str, out_dir: Path, *, root: Path = STAGE_F_ROOT,
             records_dir: Path = REVIEW_RECORDS_DIR_F, diag_snapshot: tuple[str, str] | None = None,
             now: datetime | None = None) -> dict[str, Any]:
    check_forward_access(seg_id, now)
    p = params(seg_id)
    snap = Path(root) / snapshot_id
    if not snapshot_id.startswith(p["snapshot_prefix"]):
        raise ValueError(f"{snapshot_id} is not a {seg_id} Stage F snapshot")
    pre = verify_snapshot(snap, expect_manifest_sha256)
    check_snapshot_immutable(snap)                             # protocol 2.2 D4: write-once, read-only
    h_dir = STAGE_H_ROOT / STAGE_H_SNAPSHOT
    h_pre = verify_snapshot(h_dir, STAGE_H_MANIFEST_SHA256)
    frames, ca, run = sh._load(snap)
    sessions = stage_f_sessions(p["segment_last"])
    q_syms = run["ca_query_symbols"]
    d0 = sh.derive(frames, ca, q_syms, run["ca_counts"], sessions=sessions, segment_first=p["segment_first"])
    persisted = {k: json.loads((snap / f).read_text(encoding="utf-8")) for k, f in (
        ("identity", "identity.json"), ("normalised", "events_normalised.json"), ("quality", "data_quality_comparison.json"),
        ("validation", "validation.json"), ("crosscheck", "crosscheck.json"), ("reviews", "reviews.json"))}
    recompute = {k: sh._canon(d0[k]) == persisted[k] for k in persisted}
    dup_ids = {i for b in d0["normalised"]["blocking"] if b.get("kind") == "duplicate_records" for i in b.get("ids", [])}
    inventory = rr.load(records_dir, repo_root=ROOT_DIR, stage_r_root=Path(root), snapshot_id=snapshot_id,
                        snapshot_manifest_sha256=pre["manifest_sha256"],
                        open_items=rv.open_items(d0["crosscheck"], d0["identity"]), ca_payloads=ca,
                        identity=d0["identity"], duplicate_ids=dup_ids,
                        accepted_protocol_versions=(PROTOCOL_VERSION, PROTOCOL_VERSION_004, PROTOCOL_VERSION_21),
                        moot_keys=set())
    d = sh.derive(frames, ca, q_syms, run["ca_counts"], inventory, sessions=sessions, segment_first=p["segment_first"])
    seg_first_iso, last_iso = p["segment_first"].isoformat(), p["event_max"]
    per_symbol = {}
    for key, v in d["validation"]["per_series"].items():
        miss = v.get("missing_sessions", [])
        per_symbol[key] = {"status": v["status"], "rows": v.get("rows"), "sessions_present": v.get("sessions_present"),
                           "missing_lookback": sum(1 for m in miss if m < seg_first_iso),
                           "missing_segment": sum(1 for m in miss if m >= seg_first_iso),
                           "hard_fail": v.get("hard_fail", []), "blocking": v.get("blocking", [])}
    all_dates = [x for v in d["validation"]["per_series"].values() for x in v.get("session_dates", [])]
    req = run["requests"]
    bar_ends = sorted({r["params"]["end"] for r in req if r["kind"] == "bars"})
    ca_windows = sorted({tuple(r["process_date_window"]) for r in req if r["kind"] == "corporate_actions"})
    gate_first = FORWARD_SEGMENTS["fwd-gate"][0].isoformat()
    later = lambda x: str(x)[:10] > last_iso                     # noqa: E731
    boundary = {
        "segment": seg_id, "sessions_expected": len(sessions), "segment_range": run["segment_range"],
        "min_bar_session": min(all_dates) if all_dates else None, "max_bar_session": max(all_dates) if all_dates else None,
        "no_bar_after_segment_last": not all_dates or max(all_dates) <= last_iso,
        "no_bar_before_stage_f_first": not all_dates or min(all_dates) >= p["event_min"],
        "bar_request_ends": bar_ends, "ca_process_date_windows": [list(w) for w in ca_windows],
        "ca_windows_match_adoption": [list(w) for w in ca_windows] == sorted([list(v) for v in p["ca_windows"].values()]),
        "ca_records_event_date_within_boundary": all(p["event_min"] <= x["event_date"] <= last_iso for q in ca for x in ca[q]),
        "asof_matches_adoption": run["asof"] == p["asof"],
        "assets_endpoint_called": any(r["kind"] == "asset" for r in req),
        "data_after_segment_requested": any(later(e) for e in bar_ends) or any(later(x) for w in ca_windows for x in w),
        "fwd_gate_data_requested": seg_id == "fwd-diag" and (any(e[:10] >= gate_first for e in bar_ends)
                                                            or any(str(x) >= gate_first for w in ca_windows for x in w)),
    }
    boundary["pass"] = all(boundary[k] for k in ("no_bar_after_segment_last", "no_bar_before_stage_f_first",
                                                 "ca_windows_match_adoption", "ca_records_event_date_within_boundary",
                                                 "asof_matches_adoption")) \
        and not (boundary["assets_endpoint_called"] or boundary["data_after_segment_requested"]
                 or boundary["fwd_gate_data_requested"])
    overlaps = {"stage_h": sh.overlap_control(frames, ca, h_dir, rng=OVERLAP_H)}
    if seg_id == "fwd-gate":
        if diag_snapshot:
            d_id, d_sha = diag_snapshot
            verify_snapshot(Path(root) / d_id, d_sha)
            overlaps["fwd_diag"] = sh.overlap_control(frames, ca, Path(root) / d_id,
                                                      rng=(p["event_min"], FORWARD_SEGMENTS["fwd-diag"][1].isoformat()))
        else:
            overlaps["fwd_diag"] = {"status": "not available (no F-D snapshot supplied)"}
    structural_ok = (d["validation"]["status_counts"]["HARD_FAIL"] == 0 and d["validation"]["status_counts"]["BLOCKING"] == 0
                     and all(v["status"] == "OK" for v in d["validation"]["raw_vs_all"].values()))
    identity_ok = not d["identity"]["conflicts"] and not d["identity"]["unassigned_records"]
    blocking_items = [{k: i.get(k) for k in ("item", "entity", "event_date", "status", "category", "reason")}
                      for i in d["reviews"]["items"] if i["status"] in ("BLOCKING", "HARD_FAIL")]
    checks = {"manifest_verified": True, "recompute_matches_capture": all(recompute.values()), "structural": structural_ok,
              "boundary": boundary["pass"], "identity_no_conflicts": identity_ok,
              "data_quality_complete_vs_all": not d["quality"]["blocking"],
              "normalisation_no_blocking": not d["normalised"]["blocking"],
              "overlap_raw_bars_identical": all(o.get("raw_bars_status", "IDENTICAL") == "IDENTICAL" for o in overlaps.values()),
              "overlap_events_identical": all(o.get("events", {}).get("status", "IDENTICAL") == "IDENTICAL" for o in overlaps.values()),
              "frozen_review_items_resolved": not blocking_items}
    data_fail = [k for k, v in checks.items() if not v and k != "frozen_review_items_resolved"]
    status = ("BLOCKED" if data_fail else "BLOCKED (pending protocol-owner review records)" if blocking_items else READY)
    report = {"schema_version": "1.0", "task": "DAY-26B", "kind": "Stage F data validation (no strategy evaluation)",
              "protocol_version": PROTOCOL_VERSION_21, "segment": seg_id, "snapshot_id": snapshot_id,
              "snapshot_manifest_sha256": pre["manifest_sha256"], "snapshot_tree_sha256": pre["tree_sha256"],
              "snapshot_file_count": pre["file_count"],
              "stage_h": {"snapshot_id": STAGE_H_SNAPSHOT, "manifest_sha256": h_pre["manifest_sha256"]},
              "checks": checks, "data_failures": data_fail, "status": status, "recompute_vs_capture": recompute,
              "boundary": boundary, "per_series": per_symbol,
              "validation_status_counts": d["validation"]["status_counts"],
              "review_records": {"dir": str(Path(records_dir).relative_to(ROOT_DIR)).replace("\\", "/"),
                                 "files_found": len(inventory["files_found"]), "applied": len(inventory["applied"]),
                                 "invalid": len(inventory["invalid"])},
              "blocking_items": blocking_items, "overlap_control": overlaps,
              "no_strategy_evaluation": True, "no_performance_metric": True}
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"validation output exists (write-once): {out_dir}")
    files = {"validation_report.json": sr.write_json_once(out_dir / "validation_report.json", report)}
    sr.write_json_once(out_dir / "manifest.json", {"files_sha256": files, "snapshot_id": snapshot_id, "segment": seg_id,
                                                  "snapshot_manifest_sha256": pre["manifest_sha256"], "status": status})
    return report


# ------------------------------------------------------------------ preflight (protocol 2.2 D1)

LEGACY_CACHE_DIR = "data/cache"            # DAY-15 baseline entry retired by protocol 2.2 D1 (unrecoverable)


def eol_equivalent_sha(path: Path, expected: str) -> bool:
    """True if the file equals the baseline up to line endings only: its raw, LF-normalised or CRLF-normalised bytes
    hash to `expected` (the DAY-15 baseline mixes LF and CRLF files; DAY-25B line-ending precedent)."""
    raw = Path(path).read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    import hashlib
    return expected in {hashlib.sha256(b).hexdigest() for b in (raw, lf, lf.replace(b"\n", b"\r\n"))}


def frozen_baseline_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    """DAY-15 integrity baseline for every frozen directory except the retired legacy data/cache (protocol 2.2 D1):
    the same file set, each file equal up to line endings. Raises sr.PreflightError on any difference."""
    from acquisition.run import INTEGRITY_BASELINE
    baseline = json.loads(INTEGRITY_BASELINE.read_text(encoding="utf-8"))["hashes"]
    problems, checked = [], 0
    for d, files in sorted(baseline.items()):
        if d == LEGACY_CACHE_DIR:
            continue
        base = Path(root) / d
        present = {str(p.relative_to(root)).replace("\\", "/") for p in base.rglob("*") if p.is_file()} if base.is_dir() else set()
        if present != set(files):
            problems.append(f"{d}: file set differs")
            continue
        for rel, sha in files.items():
            checked += 1
            if not eol_equivalent_sha(Path(root) / rel, sha):
                problems.append(f"{rel}: content differs from the DAY-15 baseline")
    if problems:
        raise sr.PreflightError("frozen data/artifacts changed: " + "; ".join(problems))
    return {"frozen_dirs_checked": len(baseline) - 1, "files_checked": checked,
            "retired": f"{LEGACY_CACHE_DIR} (protocol 2.2 D1; unrecoverable)"}


def preflight(seg_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Stage F capture preflight: forward access (status, time, adoption chain, config SHA, calendar, quarantine) first,
    then the DAY-15 baseline without the retired legacy cache, a clean git tree, the frozen protocol identity, the
    unchanged v2.0.4 amendment and the committed DAY-20 decisions (as stage_h.preflight)."""
    import subprocess
    from acquisition.v2.contract import AMENDMENT_004_COMMIT, AMENDMENT_004_FILES, DAY20_DECISIONS_COMMIT
    access = check_forward_access(seg_id, now)
    baseline = frozen_baseline_check()
    if sr._git("status", "--porcelain", "--untracked-files=all").strip():
        raise sr.PreflightError("git working tree not clean")
    proto = sr.protocol_identity()
    for p in AMENDMENT_004_FILES:
        if subprocess.run(["git", "diff", "--quiet", AMENDMENT_004_COMMIT, "--", p], cwd=ROOT_DIR).returncode != 0:
            raise sr.PreflightError(f"{p} differs from {AMENDMENT_004_COMMIT}")
    if subprocess.run(["git", "merge-base", "--is-ancestor", DAY20_DECISIONS_COMMIT, "HEAD"], cwd=ROOT_DIR).returncode != 0:
        raise sr.PreflightError("DAY-20 decision record is not committed at HEAD")
    return {"passed": True, "forward_access": access, "baseline": baseline, "protocol": proto,
            "git_commit": sr._git("rev-parse", "HEAD").strip(), "amendment_004_commit": AMENDMENT_004_COMMIT,
            "day20_decisions_commit": DAY20_DECISIONS_COMMIT}


# ------------------------------------------------------------------ CLI

def _refuse(*_a, **_k):
    raise RuntimeError("network access is forbidden during offline Stage F validation")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DAY-26B protocol 2.1 Stage F acquisition and data validation")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--capture", action="store_true")
    g.add_argument("--validate", metavar="SNAPSHOT_ID")
    ap.add_argument("--segment", required=True, choices=sorted(FORWARD_SEGMENTS))
    ap.add_argument("--authorization", default="")
    ap.add_argument("--expect-manifest-sha256")
    ap.add_argument("--diag-snapshot")
    ap.add_argument("--diag-manifest-sha256")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    p = params(a.segment)
    if a.dry_run:                                              # calendar facts only; no data, no network
        sessions = stage_f_sessions(p["segment_last"])
        print(json.dumps({"segment": a.segment, "stage_f_sessions": len(sessions),
                          "range": [sessions[0].isoformat(), sessions[-1].isoformat()],
                          "segment_range": [p["segment_first"].isoformat(), p["segment_last"].isoformat(),
                                            p["segment_sessions"]],
                          "asof": p["asof"], "ca_windows": p["ca_windows"],
                          "existing_snapshots": existing_snapshots(a.segment), "target_root": str(STAGE_F_ROOT)},
                         indent=2))
        return 0
    try:
        if a.validate:
            socket.socket.connect = _refuse
            out = Path(a.out) if a.out else STAGE_F_ROOT / f"validation__{a.validate}"
            diag = (a.diag_snapshot, a.diag_manifest_sha256) if a.diag_snapshot else None
            rep = validate(a.segment, a.validate, a.expect_manifest_sha256, out, diag_snapshot=diag)
            print(json.dumps({"status": rep["status"], "checks": rep["checks"], "out": str(out)}, indent=2))
            return 0
        if not a.authorization.strip():
            print("REFUSED: --authorization is required for a Stage F capture", file=sys.stderr)
            return 2
        pre = preflight(a.segment)                             # forward access first; before credentials or any client
        from acquisition.v1_1.environment import capture_v11_environment
        env = capture_v11_environment(pre["protocol"])
        env["preflight"] = {k: v for k, v in pre.items() if k != "protocol"}
        env["authorization"] = a.authorization
        res = capture(a.segment, http_factory=lambda: HttpClient(*sr._credentials()), env=env,
                      log=lambda m: print(m, flush=True))
    except (ForwardAccessRefused, sr.PreflightError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    m = res["manifest"]
    print(json.dumps({"status": res["status"], "snapshot_id": res["snapshot_id"], "requests": res["requests"],
                      "validation_status_counts": m["validation_status_counts"],
                      "crosscheck_blocking_symbols": m["crosscheck_blocking_symbols"],
                      "review_status_counts": m["review_status_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
