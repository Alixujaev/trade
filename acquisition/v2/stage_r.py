"""acquisition/v2/stage_r.py: DAY-18 Stage R acquisition (protocol v2.0 R1 + v2.0.1).

    python -m acquisition.v2.stage_r --dry-run    # plan only, no network
    python -m acquisition.v2.stage_r --capture    # preflight, acquire, validate, write one write-once snapshot

Scope: SIP 1Day bars (raw + all) 2016-01-04..2022-12-30 for 25 universe symbols + SPY; corporate actions
Q1/Q2 x complete/all with the v2.0.1 event-date boundary; identity, normalisation, structural checks, raw/all
cross-check, review classification. Everything is held in memory until all checks have run; then a new
snapshot directory is written once. Console output: statuses and counts only (no prices, rates, factors).
No signal, return, index or performance value is computed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from acquisition.contract import EXCHANGE_TZ, ROOT_DIR
from acquisition.snapshot import _write_readonly
from acquisition.v2 import crosscheck as cc
from acquisition.v2 import events as ev
from acquisition.v2 import identity as idn
from acquisition.v2 import reviews as rv
from acquisition.v2 import validation as val
from acquisition.v2.bars_client import DailyBarsClient
from acquisition.v2.ca_client import CorporateActionsClient
from acquisition.v2.contract import (
    AMENDMENT_002_COMMIT, AMENDMENT_002_FILES, AMENDMENT_003_COMMIT, AMENDMENT_003_FILES, AMENDMENT_COMMIT, AMENDMENT_FILES, ASSETS_URL, CA_DATA_QUALITY, CA_WINDOWS, EVENT_DATE_MAX, FORBIDDEN_WRITE_ROOTS,
    FREEZE_COMMIT, PROTOCOL_FILES, PROTOCOL_VERSION, SCHEMA_VERSION, STAGE_R_ROOT, ca_query_symbols,
    stage_r_symbols,
)
from acquisition.v2.http import HttpClient
from acquisition.v2.sessions import session_of_label, stage_r_sessions


class PreflightError(RuntimeError):
    """A preflight condition failed; nothing may be requested."""


class LeakageError(RuntimeError):
    """A record with event_date > 2022-12-30 reached a persisted payload (must never happen)."""


class SnapshotPathError(ValueError):
    pass


# ------------------------------------------------------------------ snapshot helpers

def check_location(path: Path) -> None:
    rp = Path(path).resolve()
    for root in FORBIDDEN_WRITE_ROOTS:
        if rp.is_relative_to(root.resolve()):
            raise SnapshotPathError(f"refusing to write Stage R data under {root}")


def _write_bytes_once(path: Path, payload: bytes) -> str:
    check_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_readonly(path, payload)            # open(..., 'xb'): fails if present; then read-only
    return hashlib.sha256(payload).hexdigest()


def write_json_once(path: Path, obj: Any) -> str:
    return _write_bytes_once(path, json.dumps(obj, indent=2, sort_keys=True, default=str).encode("utf-8"))


def write_parquet_once(path: Path, df: pd.DataFrame) -> str:
    check_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"snapshot file already exists (write-once): {path}")
    tmp = path.with_name(f".{path.name}.tmp")
    df.to_parquet(tmp)
    payload = tmp.read_bytes()
    tmp.unlink()
    return _write_bytes_once(path, payload)


# ------------------------------------------------------------------ leakage guard

def assert_no_leakage(*payloads: Any) -> int:
    """Walk payloads; any 'event_date' or 'ex_date' value later than EVENT_DATE_MAX raises. Returns #dates seen."""
    seen = 0

    def walk(o: Any) -> None:
        nonlocal seen
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("event_date", "ex_date") and v:
                    seen += 1
                    if str(v)[:10] > EVENT_DATE_MAX:
                        raise LeakageError(f"{k} beyond Stage R boundary reached a persisted payload")
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    for p in payloads:
        walk(p)
    return seen


# ------------------------------------------------------------------ capture

def capture(*, http: HttpClient, asof: str, env: dict[str, Any], root: Path = STAGE_R_ROOT,
            symbols: list[str] | None = None, snapshot_id: str | None = None,
            log: Callable[[str], None] = lambda _m: None, fetch_assets: bool = True) -> dict[str, Any]:
    check_location(root)
    sessions = stage_r_sessions()
    all_syms = stage_r_symbols()
    symbols = sorted(symbols) if symbols is not None else all_syms
    if not set(symbols) <= set(all_syms):
        raise ValueError(f"symbols outside the Stage R set: {sorted(set(symbols) - set(all_syms))}")
    snapshot_id = snapshot_id or "stage_r_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = Path(root) / snapshot_id
    check_location(snap)
    if snap.exists():
        raise FileExistsError(f"snapshot directory already exists (write-once): {snap}")
    started = datetime.now(timezone.utc).isoformat()
    requests_log: list[dict[str, Any]] = []

    assets: dict[str, Any] = {}
    if fetch_assets:
        for s in symbols:
            body, info = http.get_json(f"{ASSETS_URL}/{s}", {})
            assets[s] = {k: body.get(k) for k in ("symbol", "name", "exchange", "class", "status", "tradable", "cusip")}
            requests_log.append({"kind": "asset", "symbol": s, **info})
        log(f"assets: {len(assets)}")

    bars_client = DailyBarsClient(http, asof=asof)
    frames: dict[str, dict[str, pd.DataFrame]] = {"raw": {}, "all": {}}
    for adj in ("raw", "all"):
        for s in symbols:
            df, rec = bars_client.fetch(s, adj)
            frames[adj][s] = df
            requests_log.append({"kind": "bars", **rec})
        log(f"bars {adj}: {len(frames[adj])} symbols")

    ca_client = CorporateActionsClient(http)
    q_syms = ca_query_symbols() if symbols == all_syms else sorted(set(symbols) | {"FB"})
    ca: dict[str, list[dict[str, Any]]] = {q: [] for q in CA_DATA_QUALITY}
    ca_counts: dict[str, Any] = {}
    for q in CA_DATA_QUALITY:
        for w in CA_WINDOWS:
            kept, rec = ca_client.fetch_window(w, q, q_syms)
            ca[q].extend(kept)
            ca_counts[f"{w}_{q}"] = rec["counts"]
            requests_log.append({"kind": "corporate_actions", **rec})
    log("corporate actions: " + json.dumps({k: v["kept"] for k, v in ca_counts.items()}))

    # de-duplicate records that appear in both windows (same id) - identical content required
    for q in CA_DATA_QUALITY:
        uniq: dict[str, dict[str, Any]] = {}
        for r in ca[q]:
            rid = str(r.get("id"))
            if rid in uniq and uniq[rid] != r:
                raise RuntimeError(f"corporate action id {rid} returned with different content across windows")
            uniq[rid] = r
        ca[q] = [uniq[k] for k in sorted(uniq)]

    identity = idn.resolve(ca["complete"], all_syms if symbols == all_syms else symbols, q_syms)
    normalised = ev.normalise(ca["complete"], identity)
    quality = ev.compare_quality(ca["complete"], ca["all"], {a["id"] for a in identity["assignments"]})

    per_series: dict[str, Any] = {}
    raw_vs_all: dict[str, Any] = {}
    for s in symbols:
        r = val.check_series(frames["raw"][s], sessions)
        a = val.check_series(frames["all"][s], sessions)
        per_series[f"{s}/raw"] = r
        per_series[f"{s}/all"] = a
        raw_vs_all[s] = val.check_raw_all(r, a)
    validation = {"per_series": per_series, "raw_vs_all": raw_vs_all,
                  "status_counts": {st: sum(1 for v in per_series.values() if v["status"] == st)
                                    for st in ("OK", "BLOCKING", "HARD_FAIL")}}
    crosscheck = cc.crosscheck_all(frames["raw"], frames["all"], normalised["events"], session_of_label)
    reviews = rv.classify(records=ca["complete"], identity=identity, normalised=normalised, quality=quality,
                          crosscheck=crosscheck, validation=validation, ca_counts=ca_counts)

    ca_payloads = {q: {"records": ca[q], "boundary": {"event_date_min": "2016-01-04", "event_date_max": EVENT_DATE_MAX},
                       "counts_by_window": {w: ca_counts[f"{w}_{q}"] for w in CA_WINDOWS}} for q in CA_DATA_QUALITY}
    leak_dates = assert_no_leakage(ca_payloads, normalised, identity, crosscheck, reviews)   # before any write

    files: dict[str, str] = {}
    for adj in ("raw", "all"):
        for s, df in frames[adj].items():
            out = df.copy()
            out["session_date"] = [session_of_label(t)[0].isoformat() for t in out.index]
            files[f"bars_{adj}/{s}.parquet"] = write_parquet_once(snap / f"bars_{adj}" / f"{s}.parquet", out)
    jsons = {"corporate_actions_complete.json": ca_payloads["complete"], "corporate_actions_all.json": ca_payloads["all"],
             "events_normalised.json": normalised, "identity.json": identity, "data_quality_comparison.json": quality,
             "validation.json": validation, "crosscheck.json": crosscheck, "reviews.json": reviews,
             "assets.json": assets, "environment.json": env}
    for name, obj in jsons.items():
        files[name] = write_json_once(snap / name, obj)
    run = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "snapshot_id": snapshot_id,
           "asof": asof, "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
           "symbols": symbols, "ca_query_symbols": q_syms, "sessions": len(sessions),
           "session_range": [sessions[0].isoformat(), sessions[-1].isoformat()],
           "ca_windows": CA_WINDOWS, "ca_counts": ca_counts, "requests": requests_log,
           "leakage_dates_checked": leak_dates}
    files["run.json"] = write_json_once(snap / "run.json", run)
    manifest = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "snapshot_id": snapshot_id,
                "protocol": env.get("protocol"), "files_sha256": files,
                "usable_for_research": reviews["usable_for_research"], "review_status_counts": reviews["status_counts"],
                "validation_status_counts": validation["status_counts"],
                "crosscheck_blocking_symbols": crosscheck["blocking_symbols"],
                "identity_counts": identity["counts"], "event_counts": normalised["counts"],
                "data_quality_blocking": quality["blocking"]}
    write_json_once(snap / "manifest.json", manifest)
    return {"status": "WRITTEN", "snapshot_id": snapshot_id, "snapshot_dir": str(snap), "manifest": manifest,
            "requests": len(requests_log)}


# ------------------------------------------------------------------ preflight / CLI

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout


def protocol_identity() -> dict[str, Any]:
    out: dict[str, Any] = {"version": PROTOCOL_VERSION, "freeze_commit": FREEZE_COMMIT,
                           "amendment_commit": AMENDMENT_COMMIT, "amendment_002_commit": AMENDMENT_002_COMMIT, "amendment_003_commit": AMENDMENT_003_COMMIT,
                           "files": {}}
    for path, commit in ([(p, FREEZE_COMMIT) for p in PROTOCOL_FILES] + [(p, AMENDMENT_COMMIT) for p in AMENDMENT_FILES]
                         + [(p, AMENDMENT_002_COMMIT) for p in AMENDMENT_002_FILES]
                         + [(p, AMENDMENT_003_COMMIT) for p in AMENDMENT_003_FILES]):
        if subprocess.run(["git", "diff", "--quiet", commit, "--", path], cwd=ROOT_DIR).returncode != 0:
            raise PreflightError(f"{path} differs from commit {commit}")
        blob = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT_DIR, capture_output=True, check=True).stdout
        out["files"][path] = {"commit": commit, "blob_sha256": hashlib.sha256(blob).hexdigest()}
    return out


def preflight() -> dict[str, Any]:
    from acquisition.run import INTEGRITY_BASELINE, hash_dirs
    problems: list[str] = []
    baseline = json.loads(INTEGRITY_BASELINE.read_text(encoding="utf-8"))["hashes"]
    current = hash_dirs()
    changed = sorted(d for d in baseline if baseline.get(d) != current.get(d))
    if changed:
        problems.append(f"frozen data/artifacts changed: {changed}")
    if _git("status", "--porcelain", "--untracked-files=all").strip():
        problems.append("git working tree not clean")
    try:
        proto = protocol_identity()
    except (PreflightError, subprocess.CalledProcessError) as exc:
        problems.append(str(exc))
        proto = {}
    sessions = stage_r_sessions()
    if problems:
        raise PreflightError("; ".join(problems))
    return {"passed": True, "git_commit": _git("rev-parse", "HEAD").strip(), "sessions": len(sessions), "protocol": proto}


def _credentials() -> tuple[str, str]:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT_DIR / ".env")
    except ImportError:
        pass
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise PreflightError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    return key, secret


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DAY-18 Stage R acquisition (v2.0 R1 + v2.0.1)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--capture", action="store_true")
    a = ap.parse_args(argv)
    sessions = stage_r_sessions()
    syms = stage_r_symbols()
    if a.dry_run:
        print(json.dumps({"sessions": len(sessions), "first": sessions[0].isoformat(), "last": sessions[-1].isoformat(),
                          "symbols": syms, "ca_query_symbols": ca_query_symbols(), "ca_windows": CA_WINDOWS,
                          "planned_requests": {"assets": len(syms), "bars": 2 * len(syms),
                                               "corporate_actions_min": 2 * len(CA_WINDOWS)},
                          "target_root": str(STAGE_R_ROOT)}, indent=2))
        return 0
    pre = preflight()
    from acquisition.v1_1.environment import capture_v11_environment
    env = capture_v11_environment(pre["protocol"])
    env["preflight"] = {k: v for k, v in pre.items() if k != "protocol"}
    key, secret = _credentials()
    asof = datetime.now(ZoneInfo(EXCHANGE_TZ)).date().isoformat()
    res = capture(http=HttpClient(key, secret), asof=asof, env=env, log=lambda m: print(m, flush=True))
    m = res["manifest"]
    print(json.dumps({"status": res["status"], "snapshot_id": res["snapshot_id"], "requests": res["requests"],
                      "usable_for_research": m["usable_for_research"], "review_status_counts": m["review_status_counts"],
                      "validation_status_counts": m["validation_status_counts"],
                      "crosscheck_blocking_symbols": m["crosscheck_blocking_symbols"],
                      "identity_counts": m["identity_counts"], "event_counts": m["event_counts"],
                      "data_quality_blocking": m["data_quality_blocking"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
