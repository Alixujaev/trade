"""acquisition/v2/stage_h.py: DAY-20 Stage H (historical holdout) acquisition and data validation.

    python -m acquisition.v2.stage_h --dry-run
    python -m acquisition.v2.stage_h --capture
    python -m acquisition.v2.stage_h --validate <snapshot_id> --expect-manifest-sha256 <sha> [--out <dir>]

Frozen §3.9 Stage H: raw + adjustment=all 1Day bars and corporate-action events 2021-01-04 -> 2026-06-02 for the 25
universe symbols + SPY (1359 XNYS sessions = 503 lookback inside R∩H + the 856-session holdout 2023-01-03 ->
2026-06-02). DAY-20 protocol-owner decisions (eb7abf7): CA windows mirror v2.0.1 C1 (Q1 process_date
2021-01-01..2026-06-02, Q2 2026-06-03..2026-08-31; event_date boundary [2021-01-04, 2026-06-02], out-of-range records
discarded in memory with counts only); asof = 2026-10-07; no assets endpoint call.

DATA ONLY: no signal, TR index, return, portfolio, metric or gate is computed; no price is printed or reported.
adjustment=all is audit-only (frozen §3.4): used solely by the implied-factor cross-check.
The validator is OFFLINE (socket connections refused) and writes to a new write-once directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any, Callable

import numpy as np
import pandas as pd

from acquisition.contract import ROOT_DIR
from acquisition.v2 import crosscheck as cc
from acquisition.v2 import events as ev
from acquisition.v2 import identity as idn
from acquisition.v2 import review_records as rr
from acquisition.v2 import reviews as rv
from acquisition.v2 import stage_r as sr
from acquisition.v2 import validation as val
from acquisition.v2.bars_client import DailyBarsClient
from acquisition.v2.ca_client import CorporateActionsClient
from acquisition.v2.contract import (
    AMENDMENT_004_COMMIT, AMENDMENT_004_FILES, BAR_COLUMNS, CA_DATA_QUALITY, CA_WINDOWS_H, DAY20_DECISIONS_COMMIT,
    EVENT_DATE_MAX_H, EVENT_DATE_MIN_H, HOLDOUT_EXPECTED_SESSIONS, HOLDOUT_FIRST_SESSION, PROTOCOL_VERSION,
    PROTOCOL_VERSION_004, REVIEW_RECORDS_DIR_H, SCHEMA_VERSION, STAGE_H_ASOF, STAGE_H_EXPECTED_SESSIONS,
    STAGE_H_FIRST_SESSION, STAGE_H_LAST_SESSION, STAGE_H_ROOT, STAGE_R_ROOT, ca_query_symbols, stage_r_symbols,
    universe,
)
from acquisition.v2.http import HttpClient
from acquisition.v2.reevaluate import verify_snapshot
from acquisition.v2.sessions import session_of_label, stage_h_sessions

STAGE = "stage_h"
OVERLAP = ("2021-01-04", "2022-12-30")                    # R∩H (frozen §3.9 overlap control)
FORWARD_FIRST = "2026-10-08"                               # first forward-OOS session (freeze 2026-10-07)
STAGE_R_SNAPSHOT = "stage_r_20261007T093410Z"
STAGE_R_MANIFEST_SHA256 = "aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd"


class DataValidationIssue(RuntimeError):
    """A Stage H data issue that must be reported and decided, never silently resolved."""


def assert_no_leakage_h(*payloads: Any) -> int:
    """No event_date / ex_date outside [2021-01-04, 2026-06-02] may reach a persisted payload."""
    seen = 0

    def walk(o: Any) -> None:
        nonlocal seen
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("event_date", "ex_date") and v:
                    seen += 1
                    if not (EVENT_DATE_MIN_H <= str(v)[:10] <= EVENT_DATE_MAX_H):
                        raise sr.LeakageError(f"{k} outside the Stage H boundary reached a persisted payload")
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    for p in payloads:
        walk(p)
    return seen


def unqueried_aliases(records: list[dict[str, Any]], queried: list[str]) -> list[str]:
    """v2.0.1 C2 rule 2: name changes into a universe symbol from a ticker that was not a query key."""
    uni = set(universe())
    return sorted({r.get("old_symbol") for r in records if r.get("ca_type") in ("name_changes", "name_change")
                   and r.get("new_symbol") in uni and r.get("old_symbol") and r.get("old_symbol") not in queried})


def derive(frames: dict[str, dict[str, pd.DataFrame]], ca: dict[str, list[dict[str, Any]]], q_syms: list[str],
           ca_counts: dict[str, Any], inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Data-only derivations (identity C2, normalisation C3, complete/all C4, structural §3.8, v2.0.4 cross-check,
    v2.0.4 review classification). No price, return or signal is produced."""
    sessions = stage_h_sessions()
    syms = stage_r_symbols()
    identity = idn.resolve(ca["complete"], syms, q_syms)
    normalised = ev.normalise(ca["complete"], identity)
    quality = ev.compare_quality(ca["complete"], ca["all"], {a["id"] for a in identity["assignments"]})
    per_series, raw_vs_all = {}, {}
    for s in syms:
        r = val.check_series(frames["raw"][s], sessions, segment_first=HOLDOUT_FIRST_SESSION)
        a = val.check_series(frames["all"][s], sessions, segment_first=HOLDOUT_FIRST_SESSION)
        per_series[f"{s}/raw"], per_series[f"{s}/all"] = r, a
        raw_vs_all[s] = val.check_raw_all(r, a)
    validation = {"per_series": per_series, "raw_vs_all": raw_vs_all,
                  "status_counts": {st: sum(1 for v in per_series.values() if v["status"] == st)
                                    for st in ("OK", "BLOCKING", "HARD_FAIL")}}
    crosscheck = cc.crosscheck_all(frames["raw"], frames["all"], normalised["events"], session_of_label,
                                   precision_model="v2.0.4")
    inv = inventory if inventory is not None else {"applied": {}, "invalid": [], "files_found": [], "moot": []}
    reviews = rv.classify(records=ca["complete"], identity=identity, normalised=normalised, quality=quality,
                          crosscheck=crosscheck, validation=validation, ca_counts=ca_counts, review_inventory=inv,
                          protocol="v2.0.4")
    return {"identity": identity, "normalised": normalised, "quality": quality, "validation": validation,
            "crosscheck": crosscheck, "reviews": reviews}


def capture(*, http: HttpClient, env: dict[str, Any], root: Path = STAGE_H_ROOT, snapshot_id: str | None = None,
            log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    sr.check_location(root)
    sessions = stage_h_sessions()
    syms = stage_r_symbols()
    snapshot_id = snapshot_id or "stage_h_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = Path(root) / snapshot_id
    sr.check_location(snap)
    if snap.exists():
        raise FileExistsError(f"snapshot directory already exists (write-once): {snap}")
    started = datetime.now(timezone.utc).isoformat()
    requests_log: list[dict[str, Any]] = []
    bars = DailyBarsClient(http, asof=STAGE_H_ASOF, first_session=STAGE_H_FIRST_SESSION,
                           last_session=STAGE_H_LAST_SESSION)
    frames: dict[str, dict[str, pd.DataFrame]] = {"raw": {}, "all": {}}
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
        for w in CA_WINDOWS_H:
            kept, rec = ca_client.fetch_window(w, q, q_syms, windows=CA_WINDOWS_H, event_min=EVENT_DATE_MIN_H,
                                               event_max=EVENT_DATE_MAX_H, stage=STAGE)
            ca[q].extend(kept)
            ca_counts[f"{w}_{q}"] = rec["counts"]
            requests_log.append({"kind": "corporate_actions", **rec})
    log("corporate actions: " + json.dumps({k: v["kept"] for k, v in ca_counts.items()}))
    for q in CA_DATA_QUALITY:                                  # de-duplicate across windows (identical content)
        uniq: dict[str, dict[str, Any]] = {}
        for r in ca[q]:
            rid = str(r.get("id"))
            if rid in uniq and uniq[rid] != r:
                raise DataValidationIssue(f"corporate action id {rid} returned with different content across windows")
            uniq[rid] = r
        ca[q] = [uniq[k] for k in sorted(uniq)]
    extra = unqueried_aliases(ca["complete"] + ca["all"], q_syms)
    if extra:
        raise DataValidationIssue(f"name change into a universe symbol from unqueried alias(es) {extra} (C2 rule 2)")
    d = derive(frames, ca, q_syms, ca_counts)
    ca_payloads = {q: {"records": ca[q], "boundary": {"event_date_min": EVENT_DATE_MIN_H, "event_date_max": EVENT_DATE_MAX_H},
                       "counts_by_window": {w: ca_counts[f"{w}_{q}"] for w in CA_WINDOWS_H}} for q in CA_DATA_QUALITY}
    leak = assert_no_leakage_h(ca_payloads, d["normalised"], d["identity"], d["crosscheck"], d["reviews"])
    files: dict[str, str] = {}
    details: dict[str, Any] = {}
    for adj in ("raw", "all"):
        for s, df in frames[adj].items():
            out = df.copy()
            out["session_date"] = [session_of_label(t)[0].isoformat() for t in out.index]
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
    run = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION_004, "stage": "H",
           "snapshot_id": snapshot_id, "asof": STAGE_H_ASOF, "decisions_commit": DAY20_DECISIONS_COMMIT,
           "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "symbols": syms,
           "ca_query_symbols": q_syms, "sessions": len(sessions),
           "session_range": [sessions[0].isoformat(), sessions[-1].isoformat()],
           "holdout_segment": [HOLDOUT_FIRST_SESSION.isoformat(), STAGE_H_LAST_SESSION.isoformat(), HOLDOUT_EXPECTED_SESSIONS],
           "ca_windows": CA_WINDOWS_H, "ca_counts": ca_counts, "assets_endpoint_called": False,
           "requests": requests_log, "leakage_dates_checked": leak}
    files["run.json"] = sr.write_json_once(snap / "run.json", run)
    details["run.json"] = {"bytes": (snap / "run.json").stat().st_size}
    manifest = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION_004, "stage": "H",
                "snapshot_id": snapshot_id, "protocol": env.get("protocol"), "files_sha256": files, "file_details": details,
                "provider": {"bars": "alpaca-market-data-v2 /v2/stocks/bars feed=sip timeframe=1Day",
                             "corporate_actions": "alpaca-market-data-v1 /v1/corporate-actions"},
                "acquired_utc": started, "asof": STAGE_H_ASOF,
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

def _load(snap: Path) -> tuple[dict, dict, dict]:
    frames: dict[str, dict[str, pd.DataFrame]] = {"raw": {}, "all": {}}
    for adj in ("raw", "all"):
        for p in sorted((snap / f"bars_{adj}").glob("*.parquet")):
            frames[adj][p.stem] = pd.read_parquet(p).drop(columns=["session_date"])
    ca = {q: json.loads((snap / f"corporate_actions_{q}.json").read_text(encoding="utf-8"))["records"]
          for q in CA_DATA_QUALITY}
    run = json.loads((snap / "run.json").read_text(encoding="utf-8"))
    return frames, ca, run


def _canon(o: Any) -> Any:
    return json.loads(json.dumps(o, sort_keys=True, default=str))


def overlap_control(frames_h: dict, ca_h: dict, stage_r_dir: Path) -> dict[str, Any]:
    """Frozen §3.9: raw bars and events on R∩H compared cell by cell -> IDENTICAL / DISCREPANCY.
    adjustment=all levels are excluded (rebasing). Only counts, dates and field names are reported."""
    lo, hi = OVERLAP
    bars: dict[str, Any] = {}
    for s, h in sorted(frames_h["raw"].items()):
        r = pd.read_parquet(stage_r_dir / "bars_raw" / f"{s}.parquet").drop(columns=["session_date"])
        sel = lambda df: df[[lo <= session_of_label(t)[0].isoformat() <= hi for t in df.index]]
        rr_, hh = sel(r), sel(h)
        same_index = rr_.index.equals(hh.index)
        cols = {}
        if same_index:
            for c in BAR_COLUMNS:
                a, b = rr_[c].to_numpy(np.float64), hh[c].to_numpy(np.float64)
                neq = ~((a == b) | (np.isnan(a) & np.isnan(b)))
                if neq.any():
                    cols[c] = {"cells_differing": int(neq.sum()),
                               "first_dates": [session_of_label(t)[0].isoformat() for t in rr_.index[neq][:5]]}
        bars[s] = {"sessions_stage_r": int(len(rr_)), "sessions_stage_h": int(len(hh)), "session_index_identical": same_index,
                   "differing_columns": cols, "status": "IDENTICAL" if same_index and not cols else "DISCREPANCY"}
    r_ca = json.loads((stage_r_dir / "corporate_actions_complete.json").read_text(encoding="utf-8"))["records"]
    in_ov = lambda recs: {str(x["id"]): x for x in recs if lo <= x["event_date"] <= hi}
    R, H = in_ov(r_ca), in_ov(ca_h["complete"])
    differs = {i: sorted(k for k in set(R[i]) | set(H[i]) if R[i].get(k) != H[i].get(k)) for i in sorted(set(R) & set(H))
               if R[i] != H[i]}
    events = {"stage_r_records": len(R), "stage_h_records": len(H), "identical": len(set(R) & set(H)) - len(differs),
              "only_in_stage_r": sorted(set(R) - set(H)), "only_in_stage_h": sorted(set(H) - set(R)),
              "content_differs": {i: {"fields": f, "ca_type": H[i].get("ca_type"), "event_date": H[i].get("event_date")}
                                  for i, f in differs.items()}}
    events["status"] = "IDENTICAL" if not (events["only_in_stage_r"] or events["only_in_stage_h"] or differs) else "DISCREPANCY"
    return {"range": list(OVERLAP), "raw_bars": bars,
            "raw_bars_status": "IDENTICAL" if all(v["status"] == "IDENTICAL" for v in bars.values()) else "DISCREPANCY",
            "events": events, "adjustment_all_levels": "excluded (rebasing expected; frozen §3.9)"}


def validate(snapshot_id: str, expect_manifest_sha256: str, out_dir: Path, *, root: Path = STAGE_H_ROOT,
             records_dir: Path = REVIEW_RECORDS_DIR_H) -> dict[str, Any]:
    snap = Path(root) / snapshot_id
    pre = verify_snapshot(snap, expect_manifest_sha256)
    stage_r_dir = STAGE_R_ROOT / STAGE_R_SNAPSHOT
    r_pre = verify_snapshot(stage_r_dir, STAGE_R_MANIFEST_SHA256)
    frames, ca, run = _load(snap)
    sessions = stage_h_sessions()
    q_syms = run["ca_query_symbols"]
    d0 = derive(frames, ca, q_syms, run["ca_counts"])
    persisted = {k: json.loads((snap / f).read_text(encoding="utf-8")) for k, f in (
        ("identity", "identity.json"), ("normalised", "events_normalised.json"), ("quality", "data_quality_comparison.json"),
        ("validation", "validation.json"), ("crosscheck", "crosscheck.json"), ("reviews", "reviews.json"))}
    recompute = {k: _canon(d0[k]) == persisted[k] for k in persisted}
    dup_ids = {i for b in d0["normalised"]["blocking"] if b.get("kind") == "duplicate_records" for i in b.get("ids", [])}
    inventory = rr.load(records_dir, repo_root=ROOT_DIR, stage_r_root=Path(root), snapshot_id=snapshot_id,
                        snapshot_manifest_sha256=pre["manifest_sha256"],
                        open_items=rv.open_items(d0["crosscheck"], d0["identity"]), ca_payloads=ca,
                        identity=d0["identity"], duplicate_ids=dup_ids,
                        accepted_protocol_versions=(PROTOCOL_VERSION, PROTOCOL_VERSION_004), moot_keys=set())
    d = derive(frames, ca, q_syms, run["ca_counts"], inventory)
    holdout = [s for s in sessions if s >= HOLDOUT_FIRST_SESSION]
    lookback = [s for s in sessions if s < HOLDOUT_FIRST_SESSION]
    per_symbol = {}
    for key, v in d["validation"]["per_series"].items():
        miss = v.get("missing_sessions", [])
        per_symbol[key] = {"status": v["status"], "rows": v.get("rows"), "sessions_present": v.get("sessions_present"),
                           "first_bar": v.get("first_bar"), "last_bar": v.get("last_bar"),
                           "missing_lookback": sum(1 for m in miss if m < HOLDOUT_FIRST_SESSION.isoformat()),
                           "missing_holdout": sum(1 for m in miss if m >= HOLDOUT_FIRST_SESSION.isoformat()),
                           "hard_fail": v.get("hard_fail", []), "blocking": v.get("blocking", [])}
    all_dates = [x for v in d["validation"]["per_series"].values() for x in v.get("session_dates", [])]
    req = run["requests"]
    bar_ends = sorted({r["params"]["end"] for r in req if r["kind"] == "bars"})
    bar_starts = sorted({r["params"]["start"] for r in req if r["kind"] == "bars"})
    ca_windows = sorted({tuple(r["process_date_window"]) for r in req if r["kind"] == "corporate_actions"})
    discarded = {k: {kk: vv for kk, vv in v.items() if kk != "kept"} for k, v in run["ca_counts"].items()}
    boundary = {
        "sessions_expected": len(sessions), "sessions_expected_ok": len(sessions) == STAGE_H_EXPECTED_SESSIONS,
        "holdout_first": holdout[0].isoformat(), "holdout_last": holdout[-1].isoformat(), "holdout_sessions": len(holdout),
        "holdout_ok": len(holdout) == HOLDOUT_EXPECTED_SESSIONS and holdout[0].isoformat() == "2023-01-03"
                      and holdout[-1].isoformat() == "2026-06-02",
        "lookback_sessions": len(lookback), "research_last_session": "2022-12-30",
        "no_research_holdout_overlap_in_evaluated_segment": holdout[0].isoformat() > "2022-12-30",
        "min_bar_session": min(all_dates), "max_bar_session": max(all_dates),
        "no_bar_after_2026_06_02": max(all_dates) <= "2026-06-02", "no_bar_before_2021_01_04": min(all_dates) >= "2021-01-04",
        "bar_request_starts": bar_starts, "bar_request_ends": bar_ends,
        "ca_process_date_windows": [list(w) for w in ca_windows],
        "ca_windows_match_decision": [list(w) for w in ca_windows] == sorted([list(v) for v in CA_WINDOWS_H.values()]),
        "ca_records_event_date_within_boundary": all(EVENT_DATE_MIN_H <= x["event_date"] <= EVENT_DATE_MAX_H
                                                     for q in ca for x in ca[q]),
        "ca_discarded_counts_only": discarded,
        "asof": run["asof"], "asof_matches_decision": run["asof"] == STAGE_H_ASOF,
        "assets_endpoint_called": any(r["kind"] == "asset" for r in req),
        "forward_oos_requested": any(str(x) >= FORWARD_FIRST for w in ca_windows for x in w)
                                 or any(e[:10] >= FORWARD_FIRST for e in bar_ends),
        "leakage_dates_checked_at_capture": run["leakage_dates_checked"],
    }
    boundary["pass"] = all(boundary[k] for k in ("sessions_expected_ok", "holdout_ok", "no_research_holdout_overlap_in_evaluated_segment",
                                                 "no_bar_after_2026_06_02", "no_bar_before_2021_01_04", "ca_windows_match_decision",
                                                 "ca_records_event_date_within_boundary", "asof_matches_decision")) \
        and not boundary["assets_endpoint_called"] and not boundary["forward_oos_requested"]
    overlap = overlap_control(frames, ca, stage_r_dir)
    structural_ok = (d["validation"]["status_counts"]["HARD_FAIL"] == 0 and d["validation"]["status_counts"]["BLOCKING"] == 0
                     and all(v["status"] == "OK" for v in d["validation"]["raw_vs_all"].values()))
    identity_ok = not d["identity"]["conflicts"] and not d["identity"]["unassigned_records"]
    blocking_items = [{k: i.get(k) for k in ("item", "entity", "event_date", "status", "category", "reason")}
                      for i in d["reviews"]["items"] if i["status"] in ("BLOCKING", "HARD_FAIL")]
    checks = {"manifest_verified": True, "recompute_matches_capture": all(recompute.values()), "structural": structural_ok,
              "boundary": boundary["pass"], "identity_no_conflicts": identity_ok,
              "data_quality_complete_vs_all": not d["quality"]["blocking"],
              "normalisation_no_blocking": not d["normalised"]["blocking"],
              "overlap_raw_bars_identical": overlap["raw_bars_status"] == "IDENTICAL",
              "overlap_events_identical": overlap["events"]["status"] == "IDENTICAL",
              "frozen_review_items_resolved": not blocking_items}
    data_fail = [k for k, v in checks.items() if not v and k != "frozen_review_items_resolved"]
    status = ("BLOCKED" if data_fail else
              "BLOCKED (pending protocol-owner review records)" if blocking_items else
              "READY_FOR_HISTORICAL_HOLDOUT_EVALUATION")
    report = {"schema_version": "1.0", "task": "DAY-20", "kind": "Stage H data validation (no strategy evaluation)",
              "snapshot_id": snapshot_id, "snapshot_manifest_sha256": pre["manifest_sha256"],
              "snapshot_tree_sha256": pre["tree_sha256"], "snapshot_file_count": pre["file_count"],
              "stage_r": {"snapshot_id": STAGE_R_SNAPSHOT, "manifest_sha256": r_pre["manifest_sha256"],
                          "tree_sha256": r_pre["tree_sha256"]},
              "checks": checks, "data_failures": data_fail, "status": status, "recompute_vs_capture": recompute,
              "boundary": boundary, "per_series": per_symbol,
              "validation_status_counts": d["validation"]["status_counts"],
              "raw_vs_all_session_sets_equal": all(v["session_sets_equal"] for v in d["validation"]["raw_vs_all"].values()),
              "identity_counts": d["identity"]["counts"],
              "identity_foreign_entity_records": [{k: f.get(k) for k in ("entity", "ca_type", "event_date", "reason")}
                                                  for f in d["identity"]["foreign_entity_records"]],
              "identity_unverified_records": [{k: u.get(k) for k in ("entity", "ca_type", "event_date", "role")}
                                              for u in d["identity"].get("identity_unverified_records", [])],
              "event_counts": d["normalised"]["counts"], "data_quality": {k: (v if not isinstance(v, list) else len(v))
                                                                          for k, v in d["quality"].items()},
              "crosscheck": {"precision_model": "v2.0.4", "blocking_symbols": d["crosscheck"]["blocking_symbols"],
                             "per_symbol": {s: {k: (len(v[k]) if isinstance(v.get(k), list) else v.get(k)) for k in (
                                 "status", "detected_changes", "expected_events", "matched_events", "unexplained_changes",
                                 "unconfirmed_events", "precision_degenerate_pairs", "exact_evaluation_invalid_pairs",
                                 "numerical_false_positives", "numerical_false_negatives", "first_session_untestable",
                                 "uncheckable_events")} for s, v in d["crosscheck"]["per_symbol"].items()},
                             "first_session_untestable": d["crosscheck"]["first_session_untestable"]},
              "review_status_counts": d["reviews"]["status_counts"], "review_category_counts": d["reviews"]["category_counts"],
              "review_records": {"dir": str(records_dir.relative_to(ROOT_DIR)).replace("\\", "/"),
                                 "files_found": len(inventory["files_found"]), "applied": len(inventory["applied"]),
                                 "invalid": len(inventory["invalid"])},
              "blocking_items": blocking_items, "overlap_control": overlap,
              "no_strategy_evaluation": True, "no_performance_metric": True, "forward_oos_accessed": False}
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"validation output exists (write-once): {out_dir}")
    files = {"validation_report.json": sr.write_json_once(out_dir / "validation_report.json", report)}
    sr.write_json_once(out_dir / "manifest.json", {"files_sha256": files, "snapshot_id": snapshot_id,
                                                  "snapshot_manifest_sha256": pre["manifest_sha256"], "status": status})
    return report


# ------------------------------------------------------------------ CLI

def preflight() -> dict[str, Any]:
    pre = sr.preflight()
    for p in AMENDMENT_004_FILES:
        if subprocess.run(["git", "diff", "--quiet", AMENDMENT_004_COMMIT, "--", p], cwd=ROOT_DIR).returncode != 0:
            raise sr.PreflightError(f"{p} differs from {AMENDMENT_004_COMMIT}")
    if subprocess.run(["git", "merge-base", "--is-ancestor", DAY20_DECISIONS_COMMIT, "HEAD"], cwd=ROOT_DIR).returncode != 0:
        raise sr.PreflightError("DAY-20 decision record is not committed at HEAD")
    pre["amendment_004_commit"] = AMENDMENT_004_COMMIT
    pre["day20_decisions_commit"] = DAY20_DECISIONS_COMMIT
    return pre


def _refuse(*_a, **_k):
    raise RuntimeError("network access is forbidden during offline Stage H validation")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DAY-20 Stage H acquisition and data validation (no strategy evaluation)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--capture", action="store_true")
    g.add_argument("--validate", metavar="SNAPSHOT_ID")
    ap.add_argument("--expect-manifest-sha256")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    sessions = stage_h_sessions()
    if a.dry_run:
        print(json.dumps({"sessions": len(sessions), "first": sessions[0].isoformat(), "last": sessions[-1].isoformat(),
                          "holdout_sessions": sum(1 for s in sessions if s >= HOLDOUT_FIRST_SESSION),
                          "symbols": stage_r_symbols(), "ca_query_symbols": ca_query_symbols(), "ca_windows": CA_WINDOWS_H,
                          "asof": STAGE_H_ASOF, "planned_requests": {"bars": 2 * len(stage_r_symbols()),
                                                                      "corporate_actions_min": 2 * len(CA_WINDOWS_H)},
                          "target_root": str(STAGE_H_ROOT)}, indent=2))
        return 0
    if a.validate:
        socket.socket.connect = _refuse
        out = Path(a.out) if a.out else STAGE_H_ROOT / f"validation__{a.validate}"
        rep = validate(a.validate, a.expect_manifest_sha256, out)
        print(json.dumps({"status": rep["status"], "checks": rep["checks"], "blocking_items": rep["blocking_items"],
                          "out": str(out)}, indent=2))
        return 0
    pre = preflight()
    from acquisition.v1_1.environment import capture_v11_environment
    env = capture_v11_environment(pre["protocol"])
    env["preflight"] = {k: v for k, v in pre.items() if k != "protocol"}
    key, secret = sr._credentials()
    res = capture(http=HttpClient(key, secret), env=env, log=lambda m: print(m, flush=True))
    m = res["manifest"]
    print(json.dumps({"status": res["status"], "snapshot_id": res["snapshot_id"], "requests": res["requests"],
                      "validation_status_counts": m["validation_status_counts"],
                      "crosscheck_blocking_symbols": m["crosscheck_blocking_symbols"],
                      "identity_counts": m["identity_counts"], "event_counts": m["event_counts"],
                      "data_quality_blocking": m["data_quality_blocking"], "review_status_counts": m["review_status_counts"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
