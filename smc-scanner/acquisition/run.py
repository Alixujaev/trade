"""acquisition/run.py: DAY-15B capture run — preflight, capture, overlap, derived manifest.

Only raw bars and structural facts are produced. No indicator, signal, return or performance value is
computed anywhere in this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

import pandas as pd

from acquisition.capture_policy import CAPTURE_NOT_BEFORE_ET, MARKET_CLOSE_ET, assert_capture_allowed
from acquisition.contract import (
    EXCHANGE_TZ, OOS_ROOT, OOS_RULE, PROTOCOL_VERSION, RESEARCH_WINDOW_END, ROOT_DIR, SCHEMA_VERSION,
    SUPPORTED_INTERVALS, ProviderConfig, oos_universe,
)
from acquisition.ledger import capture_state, complete_units
from acquisition.pipeline import acquire_one
from acquisition.provider_adapter import YFinanceAdapter, provider_version
from acquisition.sessions import calendar_info, resolve_oos_sessions
from acquisition.snapshot import _check_location, _write_readonly, compare_overlap
from acquisition.validation import calendar_coverage

INTEGRITY_BASELINE = ROOT_DIR / "artifacts" / "day15" / "integrity-baseline.json"
FROZEN_DIRS = ["data/cache"] + [f"artifacts/{d}" for d in (
    "day04", "day05", "day06", "day06a", "day07", "day07a", "day08", "day08b", "day09", "day10", "day11",
    "day12a", "day12b", "day13", "day14")]
# Untracked paths that may exist when a capture starts (pre-existing / produced by earlier captures).
GIT_UNTRACKED_ALLOWLIST = ("day08-market-cache.tar.gz", "artifacts/day15/day15b-acquisition.md")


class PreflightError(RuntimeError):
    """A preflight condition failed; nothing may be downloaded."""


def hash_dirs(root: Path = ROOT_DIR, dirs: list[str] = FROZEN_DIRS) -> dict[str, dict[str, str]]:
    out = {}
    for d in dirs:
        base = root / d
        out[d] = {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(base.rglob("*")) if p.is_file()} if base.is_dir() else {}
    return out


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout


def git_state() -> dict[str, Any]:
    lines = [ln for ln in _git("status", "--porcelain", "--untracked-files=all").splitlines() if ln.strip()]
    tracked = [ln for ln in lines if not ln.startswith("??")]
    untracked = [ln[3:].strip() for ln in lines if ln.startswith("??")]
    unexpected = [u for u in untracked if not any(u.endswith(a) for a in GIT_UNTRACKED_ALLOWLIST)]
    return {"commit": _git("rev-parse", "HEAD").strip(), "tracked_changes": tracked,
            "untracked": untracked, "unexpected_untracked": unexpected}


def preflight(*, baseline_path: Path = INTEGRITY_BASELINE, require_clean_git: bool = True,
              hasher: Callable[[], dict] = hash_dirs, git: Callable[[], dict] = git_state) -> dict[str, Any]:
    problems: list[str] = []
    if not baseline_path.exists():
        problems.append(f"integrity baseline missing: {baseline_path}")
        baseline = {}
    else:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["hashes"]
    current = hasher()
    changed = sorted(d for d in baseline if baseline.get(d) != current.get(d))
    if changed:
        problems.append(f"frozen data/artifacts changed: {changed}")
    s1, s2 = resolve_oos_sessions(), resolve_oos_sessions()
    if len(s1) != 60 or s1 != s2:
        problems.append("calendar did not resolve exactly 60 deterministic sessions")
    if s1 and s1[0].session <= RESEARCH_WINDOW_END:
        problems.append("first OOS session not strictly after the boundary")
    g = git()
    if require_clean_git and (g["tracked_changes"] or g["unexpected_untracked"]):
        problems.append(f"git working tree not clean: tracked={g['tracked_changes']} untracked={g['unexpected_untracked']}")
    if problems:
        raise PreflightError("; ".join(problems))
    return {"passed": True, "frozen_dirs_checked": len(baseline), "git": g, "sessions": len(s1)}


def _et_midnight(d) -> pd.Timestamp:
    return pd.Timestamp(d).tz_localize(EXCHANGE_TZ)


class AcquisitionBlockedError(RuntimeError):
    """The earliest remaining OOS session is outside the provider's (INFERRED) intraday window."""


def capture_run(*, now: datetime, env: dict[str, Any], adapter: YFinanceAdapter | None = None,
                root: Path = OOS_ROOT, symbols: list[str] | None = None,
                intervals: tuple[str, ...] = tuple(sorted(SUPPORTED_INTERVALS)),
                acquisition_commit: str | None = None) -> dict[str, Any]:
    """Incremental capture: request only missing, capturable units inside the provider window.

    COMPLETE (60/60) and UP_TO_DATE are no-ops (no request, no snapshot, no manifest write).
    BLOCKED raises before any request; no session is dropped or substituted.
    """
    _check_location(root)
    sessions = resolve_oos_sessions()
    universe = oos_universe()
    symbols = list(symbols) if symbols is not None else universe
    if not set(symbols) <= set(universe):  # subsets are for tests only; never substitutes
        raise ValueError(f"symbols outside the frozen universe: {sorted(set(symbols) - set(universe))}")
    state = capture_state(root, sessions, now, symbols=symbols, intervals=intervals)
    if state["status"] == "COMPLETE":
        return {"status": "COMPLETE", "progress": state["progress"], "state": state, "results": []}
    if not state["capturable_sessions"]:
        raise PreflightError("no OOS session is capturable yet (capture_not_before 16:15 ET)")
    if state["status"] == "UP_TO_DATE":
        return {"status": "UP_TO_DATE", "progress": state["progress"], "state": state, "results": []}
    if state["status"] == "BLOCKED":
        raise AcquisitionBlockedError(
            f"ACQUISITION BLOCKED: earliest missing session {state['earliest_missing_capturable_session']} is before the "
            f"provider window start {state['provider_window']['earliest_requestable_start_utc']} (INFERRED lookback). "
            "No session is dropped, substituted or redefined.")
    by_index = {s.index: s for s in sessions}
    for p in state["planned_requests"]:
        for i in range(p["first_index"], p["last_index"] + 1):
            assert_capture_allowed(by_index[i], now)
    adapter = adapter or YFinanceAdapter(ProviderConfig())
    now_et = pd.Timestamp(now).tz_convert(EXCHANGE_TZ)
    lo = min(p["first_index"] for p in state["planned_requests"])
    hi = max(p["last_index"] for p in state["planned_requests"])
    snapshot_id = f"capture_{now_et:%Y%m%dT%H%M}ET_s{lo:03d}-s{hi:03d}"
    extra = {
        "calendar": calendar_info(),
        "capture_policy": {"market_close_et": MARKET_CLOSE_ET.isoformat(), "capture_not_before_et": CAPTURE_NOT_BEFORE_ET.isoformat(),
                           "timezone": EXCHANGE_TZ},
        "provider_window": state["provider_window"],
        "acquisition_commit": acquisition_commit or env.get("git_commit"),
        "python_version": env.get("python_version"),
    }
    snaps_root = Path(root) / "snapshots"
    previous = sorted(p for p in snaps_root.glob("*") if p.is_dir() and p.name != snapshot_id) if snaps_root.exists() else []
    results: list[dict[str, Any]] = []
    for p in state["planned_requests"]:
        sym, iv = p["symbol"], p["interval"]
        req_sessions = [by_index[i] for i in range(p["first_index"], p["last_index"] + 1)]
        part = f"s{p['first_index']:03d}-s{p['last_index']:03d}"
        start = _et_midnight(req_sessions[0].session)
        end = _et_midnight(req_sessions[-1].session) + timedelta(days=1)   # yfinance 'end' is exclusive
        rec: dict[str, Any] = {"symbol": sym, "interval": iv, "part": part,
                               "requested_sessions": [s.session.isoformat() for s in req_sessions]}
        try:
            res = acquire_one(adapter, root, snapshot_id, sym, iv, start.to_pydatetime(), end.to_pydatetime(), env,
                              extra_meta=dict(extra, captured_sessions=rec["requested_sessions"]), part=part)
        except Exception as exc:  # recorded, never substituted
            rec.update(status="MISSING", error=f"{type(exc).__name__}: {exc}")
            results.append(rec)
            continue
        df = res.pop("frame")
        meta = res.pop("metadata")
        cov = calendar_coverage(df, iv, req_sessions)
        sc = meta["structural_checks"]
        rec.update(status=res["status"], data_file=res.get("data_file") or Path(res["data_path"]).name,
                   content_sha256=meta["content_sha256"], row_count=meta["row_count"],
                   structural_passed=res["structural_checks_passed"], structural_errors=res["structural_errors"],
                   adj_close_equals_close_all_rows=sc.get("adj_close_equals_close_all_rows"),
                   adj_close_differs_rows=sc.get("adj_close_differs_rows"),
                   duplicate_timestamps=sc.get("duplicate_timestamps"), off_grid_bars=sc.get("off_grid_bars"),
                   non_rth_bars=sc.get("non_rth_bars"), ohlc_inconsistent_rows=sc.get("ohlc_inconsistent_rows"),
                   negative_volume_rows=sc.get("negative_volume_rows"), zero_volume_rows=sc.get("zero_volume_rows"),
                   nan_cells=sc.get("nan_cells"), tz=meta["timezone"],
                   coverage={k: v for k, v in cov.items() if k != "per_session"}, coverage_per_session=cov["per_session"])
        overlaps = []
        for prev in previous:
            for pf in sorted(prev.glob(f"{sym}_{iv}*.parquet")):
                ov = compare_overlap(pd.read_parquet(pf), df)
                if ov["common_timestamps"]:
                    overlaps.append({"previous_snapshot": prev.name, "previous_file": pf.name, **{k: ov[k] for k in (
                        "common_timestamps", "differing_rows", "differing_cells_by_column", "identical_on_overlap")}})
        rec["overlap_with_previous"] = overlaps
        rec["corporate_action_status"] = {
            "adj_close_equals_close_all_rows": rec["adj_close_equals_close_all_rows"],
            "overlap_discrepancy": any(not o["identical_on_overlap"] for o in overlaps),
            "reacquisition_status": res["status"],
        }
        results.append(rec)
    captured = sorted({s for r in results for s in r["requested_sessions"]})
    run = {
        "schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "snapshot_id": snapshot_id,
        "run_utc": pd.Timestamp(now).tz_convert("UTC").isoformat(), "oos_rule": OOS_RULE,
        "requested_start": min(r["requested_sessions"][0] for r in results),
        "requested_end": max(r["requested_sessions"][-1] for r in results),
        "provider": "yfinance", "provider_version": provider_version(),
        "provider_config": ProviderConfig().download_kwargs(), **extra,
        "captured_sessions": captured, "state_before": {k: v for k, v in state.items() if k != "planned_requests"},
        "environment_sha256": env.get("environment_sha256"), "results": results,
    }
    run_path = Path(root) / "snapshots" / snapshot_id / "run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    _write_readonly(run_path, json.dumps(run, indent=2, sort_keys=True, default=str).encode("utf-8"))
    manifest = build_manifest(root)
    run["status"] = "CAPTURED"
    run["progress"] = manifest["progress"]["progress"]
    return run


def _progress(root: Path, sessions) -> dict[str, Any]:
    """Ledger progress over the full frozen universe (complete session = every symbol x interval verified)."""
    done = complete_units(root)
    combos = [(s, i) for s in oos_universe() for i in sorted(SUPPORTED_INTERVALS)]
    complete = [s.session.isoformat() for s in sessions
                if all((s.session.isoformat(), sym, iv) in done for sym, iv in combos)]
    return {"complete_sessions": complete, "progress": f"{len(complete)}/{len(sessions)}",
            "units_per_session": len(combos), "complete_units": len(done)}


def build_manifest(root: Path = OOS_ROOT) -> dict[str, Any]:
    """Derived index over the write-once snapshot files (regenerable; not itself source data)."""
    _check_location(root)
    sessions = resolve_oos_sessions()
    snaps = []
    for run_path in sorted((Path(root) / "snapshots").glob("*/run.json")):
        run = json.loads(run_path.read_text(encoding="utf-8"))
        files = []
        for meta_path in sorted(run_path.parent.glob("*.meta.json")):
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            files.append({"path": str(meta_path.with_suffix("").with_suffix(".parquet").relative_to(root)).replace("\\", "/"),
                          "symbol": m["symbol"], "interval": m["interval"], "content_sha256": m["content_sha256"],
                          "file_sha256": m["file_sha256"], "row_count": m["row_count"],
                          "structural_passed": m["structural_checks"]["passed"], "acquisition_utc": m["acquisition_utc"]})
        attempts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(run_path.parent.glob("attempts/*.json"))]
        snaps.append({
            "snapshot_id": run["snapshot_id"], "run_utc": run["run_utc"], "captured_sessions": run["captured_sessions"],
            "acquisition_commit": run["acquisition_commit"], "environment_sha256": run["environment_sha256"],
            "environment_manifest": str((run_path.parent / "environment.json").relative_to(root)).replace("\\", "/"),
            "run_record": str(run_path.relative_to(root)).replace("\\", "/"),
            "run_record_sha256": hashlib.sha256(run_path.read_bytes()).hexdigest(),
            "files": files,
            "missing": [{"symbol": r["symbol"], "interval": r["interval"], "error": r.get("error")}
                        for r in run["results"] if r["status"] == "MISSING"],
            "discrepancies": [a for a in attempts if a.get("status") == "DISCREPANCY"]
            + [{"symbol": r["symbol"], "interval": r["interval"], "overlap": o} for r in run["results"]
               for o in r.get("overlap_with_previous", []) if not o["identical_on_overlap"]],
        })
    manifest = {
        "schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "boundary_date": RESEARCH_WINDOW_END.isoformat(), "oos_rule": OOS_RULE, "calendar": calendar_info(),
        "oos_sessions": [{"index": s.index, "session": s.session.isoformat(), "open_et": s.open_et.isoformat(),
                          "close_et": s.close_et.isoformat(), "early_close": s.early_close} for s in sessions],
        "symbols": oos_universe(), "intervals": sorted(SUPPORTED_INTERVALS),
        "provider": "yfinance", "provider_version": provider_version(), "provider_config": ProviderConfig().download_kwargs(),
        "snapshots": snaps,
        "progress": _progress(root, sessions),
        "note": "Derived index regenerated from write-once snapshot files. Contains no trading or performance information.",
    }
    path = Path(root) / "manifest.json"
    if path.exists():
        path.chmod(0o644)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
