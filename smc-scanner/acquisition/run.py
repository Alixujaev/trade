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

from acquisition.capture_policy import (
    CAPTURE_NOT_BEFORE_ET, MARKET_CLOSE_ET, assert_capture_allowed, capturable_sessions,
)
from acquisition.contract import (
    EXCHANGE_TZ, OOS_ROOT, OOS_RULE, PROTOCOL_VERSION, RESEARCH_WINDOW_END, ROOT_DIR, SCHEMA_VERSION,
    SUPPORTED_INTERVALS, ProviderConfig, oos_universe,
)
from acquisition.pipeline import acquire_one
from acquisition.provider_adapter import YFinanceAdapter, provider_version
from acquisition.sessions import OOSSession, calendar_info, resolve_oos_sessions
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


def capture_run(*, now: datetime, env: dict[str, Any], adapter: YFinanceAdapter | None = None,
                root: Path = OOS_ROOT, symbols: list[str] | None = None,
                intervals: tuple[str, ...] = tuple(sorted(SUPPORTED_INTERVALS)),
                acquisition_commit: str | None = None) -> dict[str, Any]:
    """Capture every frozen symbol x interval for all sessions completed (>= 16:15 ET) by `now`."""
    _check_location(root)
    adapter = adapter or YFinanceAdapter(ProviderConfig())
    sessions = resolve_oos_sessions()
    cap = capturable_sessions(sessions, now)
    if not cap:
        raise PreflightError("no OOS session is capturable yet (capture_not_before 16:15 ET)")
    for s in cap:
        assert_capture_allowed(s, now)
    universe = oos_universe()
    symbols = list(symbols) if symbols is not None else universe
    if not set(symbols) <= set(universe):  # subsets are for tests only; never substitutes
        raise ValueError(f"symbols outside the frozen universe: {sorted(set(symbols) - set(universe))}")
    now_et = pd.Timestamp(now).tz_convert(EXCHANGE_TZ)
    snapshot_id = f"capture_{now_et:%Y%m%dT%H%M}ET_s{cap[0].index:03d}-s{cap[-1].index:03d}"
    start = _et_midnight(cap[0].session)
    end = _et_midnight(cap[-1].session) + timedelta(days=1)   # yfinance 'end' is exclusive
    cal = calendar_info()
    extra = {
        "calendar": cal,
        "capture_policy": {"market_close_et": MARKET_CLOSE_ET.isoformat(), "capture_not_before_et": CAPTURE_NOT_BEFORE_ET.isoformat(),
                           "timezone": EXCHANGE_TZ},
        "captured_sessions": [s.session.isoformat() for s in cap],
        "acquisition_commit": acquisition_commit or env.get("git_commit"),
        "python_version": env.get("python_version"),
    }
    previous = sorted(p for p in (Path(root) / "snapshots").glob("*") if p.is_dir() and p.name != snapshot_id) \
        if (Path(root) / "snapshots").exists() else []
    results: list[dict[str, Any]] = []
    for sym in symbols:
        for iv in intervals:
            rec: dict[str, Any] = {"symbol": sym, "interval": iv}
            try:
                res = acquire_one(adapter, root, snapshot_id, sym, iv, start.to_pydatetime(), end.to_pydatetime(), env,
                                  extra_meta=dict(extra))
            except Exception as exc:  # recorded, never substituted
                rec.update(status="MISSING", error=f"{type(exc).__name__}: {exc}")
                results.append(rec)
                continue
            df = res.pop("frame")
            meta = res.pop("metadata")
            cov = calendar_coverage(df, iv, cap)
            rec.update(status=res["status"], content_sha256=meta["content_sha256"], row_count=meta["row_count"],
                       structural_passed=res["structural_checks_passed"], structural_errors=res["structural_errors"],
                       adj_close_equals_close_all_rows=meta["structural_checks"].get("adj_close_equals_close_all_rows"),
                       adj_close_differs_rows=meta["structural_checks"].get("adj_close_differs_rows"),
                       duplicate_timestamps=meta["structural_checks"].get("duplicate_timestamps"),
                       off_grid_bars=meta["structural_checks"].get("off_grid_bars"),
                       non_rth_bars=meta["structural_checks"].get("non_rth_bars"),
                       ohlc_inconsistent_rows=meta["structural_checks"].get("ohlc_inconsistent_rows"),
                       negative_volume_rows=meta["structural_checks"].get("negative_volume_rows"),
                       zero_volume_rows=meta["structural_checks"].get("zero_volume_rows"),
                       nan_cells=meta["structural_checks"].get("nan_cells"),
                       tz=meta["timezone"], coverage={k: v for k, v in cov.items() if k != "per_session"},
                       coverage_per_session=cov["per_session"])
            overlaps = []
            for prev in previous:
                pf = prev / f"{sym}_{iv}.parquet"
                if pf.exists():
                    ov = compare_overlap(pd.read_parquet(pf), df)
                    overlaps.append({"previous_snapshot": prev.name, **{k: ov[k] for k in (
                        "common_timestamps", "differing_rows", "differing_cells_by_column", "identical_on_overlap")}})
            rec["overlap_with_previous"] = overlaps
            rec["corporate_action_status"] = {
                "adj_close_equals_close_all_rows": rec["adj_close_equals_close_all_rows"],
                "overlap_discrepancy": any(not o["identical_on_overlap"] for o in overlaps),
                "reacquisition_status": res["status"],
            }
            results.append(rec)
    run = {
        "schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "snapshot_id": snapshot_id,
        "run_utc": pd.Timestamp(now).tz_convert("UTC").isoformat(), "oos_rule": OOS_RULE,
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "provider": "yfinance", "provider_version": provider_version(),
        "provider_config": ProviderConfig().download_kwargs(), **extra,
        "environment_sha256": env.get("environment_sha256"), "results": results,
    }
    run_path = Path(root) / "snapshots" / snapshot_id / "run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    _write_readonly(run_path, json.dumps(run, indent=2, sort_keys=True, default=str).encode("utf-8"))
    build_manifest(root)
    return run


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
        "note": "Derived index regenerated from write-once snapshot files. Contains no trading or performance information.",
    }
    path = Path(root) / "manifest.json"
    if path.exists():
        path.chmod(0o644)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
