"""acquisition/v1_1/research.py: DAY-15G research acquisition (warmup + research + embargo), protocol v1.1.

    python -m acquisition.v1_1.research --dry-run          # plan only, no network
    python -m acquisition.v1_1.research --capture          # acquire pending units
    python -m acquisition.v1_1.research --capture --recheck  # re-acquire everything into a new snapshot, compare

Hard rules enforced in code:
- only sessions 2026-06-03 .. 2026-09-28 (assert_not_oos per unit; client rejects end > 2026-09-28 close);
- one request per (session, symbol, interval): start = session open, end = LAST BAR OPEN (Alpaca end is inclusive);
- order: session (chronological) -> symbol (sorted) -> interval (5m, 15m);
- write-once snapshot directory per run; nothing is overwritten; the earliest complete unit is accepted;
- structural facts only. No indicator, signal, return or performance value is computed in this module.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import pandas as pd

from acquisition.contract import ROOT_DIR
from acquisition.run import INTEGRITY_BASELINE, hash_dirs
from acquisition.sessions import calendar_info
from acquisition.v1_1.alpaca_client import AlpacaBarsClient, AlpacaRequestError
from acquisition.v1_1.contract import (
    DAY15G_LAST_SESSION, INTERVAL_ORDER, PROTOCOL_DOC, PROTOCOL_VERSION, RESEARCH_ROOT, SCHEMA_VERSION,
    STORED_COLUMNS, AlpacaBarsConfig, bar_minutes, v11_universe,
)
from acquisition.v1_1.ledger import Unit, accepted_units, account
from acquisition.v1_1.sessions import V11Session, assert_not_oos, research_acquisition_sessions
from acquisition.v1_1.snapshot import (
    check_location, compare_status, content_sha256, write_json_once, write_parquet_once,
)
from acquisition.v1_1.validation import unit_checks

INTEGRITY_REPORT = ROOT_DIR / "artifacts" / "day15" / "day15g-integrity.json"
GIT_UNTRACKED_ALLOWLIST = ("day08-market-cache.tar.gz",)
DAY15_DOCS = ("protocol-v1.1.md", "day15b-acquisition.md", "day15c-provider-audit.md", "day15d-oos-window-redesign.md",
              "day15e-alpaca-access.md", "day15g-alpaca-15m-access.md")


class PreflightError(RuntimeError):
    """A preflight condition failed; nothing may be requested."""


def expected_units(sessions: list[V11Session], symbols: list[str],
                   intervals: tuple[str, ...] = INTERVAL_ORDER) -> list[Unit]:
    return [(s.session.isoformat(), sym, iv) for s in sessions for sym in sorted(symbols) for iv in intervals]


def request_bounds(session: V11Session, interval: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """start = session open; end = last bar OPEN (close - step). Alpaca `end` is INCLUSIVE, so this returns
    exactly the session's RTH bars and never touches the next session or the close boundary."""
    step = timedelta(minutes=bar_minutes(interval))
    start = pd.Timestamp(session.open_et).tz_convert("UTC")
    end = (pd.Timestamp(session.close_et) - step).tz_convert("UTC")
    return start, end


def unit_hash(df: pd.DataFrame) -> str:
    return content_sha256(df)


def capture(*, client: AlpacaBarsClient, env: dict[str, Any], root: Path = RESEARCH_ROOT,
            sessions: list[V11Session] | None = None, symbols: list[str] | None = None,
            intervals: tuple[str, ...] = INTERVAL_ORDER, recheck: bool = False,
            snapshot_id: str | None = None, log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    check_location(root)
    sessions = research_acquisition_sessions(sessions)
    universe = v11_universe()
    symbols = sorted(symbols) if symbols is not None else universe
    if not set(symbols) <= set(universe):  # subsets are for tests only; never substitutes
        raise ValueError(f"symbols outside the frozen universe: {sorted(set(symbols) - set(universe))}")
    for iv in intervals:
        bar_minutes(iv)
    expected = expected_units(sessions, symbols, intervals)
    accepted = accepted_units(root)
    plan = expected if recheck else [u for u in expected if u not in accepted]
    if not plan:
        return {"status": "COMPLETE", "planned_units": 0, "ledger": account(root, expected)}

    by_date = {s.session.isoformat(): s for s in sessions}
    not_after = pd.Timestamp(max(s.close_et for s in sessions)).tz_convert("UTC")
    if max(s.session for s in sessions) > DAY15G_LAST_SESSION:
        raise PreflightError("session list extends past the DAY-15G limit")
    snapshot_id = snapshot_id or "research_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap_dir = Path(root) / "snapshots" / snapshot_id
    check_location(snap_dir)
    if snap_dir.exists():
        raise FileExistsError(f"snapshot directory already exists (write-once): {snap_dir}")

    run_started = datetime.now(timezone.utc).isoformat()
    frames: dict[tuple[str, str], list[pd.DataFrame]] = defaultdict(list)
    ext_frames: dict[tuple[str, str], list[pd.DataFrame]] = defaultdict(list)
    units: list[dict[str, Any]] = []
    aborted: str | None = None
    for n, (sess_iso, sym, iv) in enumerate(plan, start=1):
        s = by_date[sess_iso]
        assert_not_oos(s.session)                      # hard guard, before any request
        start, end = request_bounds(s, iv)
        unit: dict[str, Any] = {"session": sess_iso, "segment": s.segment, "symbol": sym, "interval": iv,
                                "requested_start_utc": start.isoformat(), "requested_end_utc": end.isoformat(),
                                "end_semantics": "inclusive"}
        if aborted:
            unit.update(status="NOT_REQUESTED", error=f"run aborted: {aborted}")
            units.append(unit)
            continue
        try:
            df, req = client.fetch(sym, iv, start.to_pydatetime(), end.to_pydatetime(), not_after=not_after.to_pydatetime())
        except AlpacaRequestError as exc:
            unit.update(status="MISSING", error=str(exc)[:300], http_status=exc.status)
            units.append(unit)
            if exc.fatal:
                aborted = f"fatal HTTP {exc.status}"
            continue
        except Exception as exc:  # recorded, never substituted
            unit.update(status="MISSING", error=f"{type(exc).__name__}: {str(exc)[:300]}")
            units.append(unit)
            continue
        rth, rep = unit_checks(df, s, iv)
        ext = df.loc[~df.index.isin(rth.index)] if len(df) else df
        unit.update(
            status="COMPLETE" if rep["passed"] else "STRUCTURAL_FAIL",
            checks=rep, unit_content_sha256=unit_hash(rth), rth_rows=int(len(rth)),
            request={k: req[k] for k in ("params", "page_count", "pages", "page_overlap_duplicates",
                                         "returned_rows", "request_utc")},
        )
        if recheck and (sess_iso, sym, iv) in accepted:
            orig = accepted[(sess_iso, sym, iv)]
            unit["recheck"] = {"accepted_snapshot": orig["snapshot_id"],
                               "status": compare_status(orig.get("unit_content_sha256"), unit["unit_content_sha256"])}
        frames[(sym, iv)].append(rth)
        if len(ext):
            ext_frames[(sym, iv)].append(ext)
        units.append(unit)
        if n % 100 == 0 or n == len(plan):
            log(f"{n}/{len(plan)} units requested")

    files: dict[str, dict[str, Any]] = {}
    acq_utc = datetime.now(timezone.utc).isoformat()
    for (sym, iv), parts in sorted(frames.items()):
        df = pd.concat(parts).sort_index(kind="mergesort")
        if df.index.duplicated().any():
            raise RuntimeError(f"duplicate timestamps across units for {sym} {iv}")
        name = f"{sym}_{iv}.parquet"
        fsha = write_parquet_once(snap_dir / name, df[list(STORED_COLUMNS)])
        u_here = [u for u in units if u["symbol"] == sym and u["interval"] == iv and "checks" in u]
        meta = {
            "schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "snapshot_id": snapshot_id,
            "symbol": sym, "interval": iv, "provider_config": client.config.as_dict(),
            "columns": list(STORED_COLUMNS), "strategy_columns": ["open", "high", "low", "close", "volume"],
            "provider_vwap_policy": "provenance only; strategy VWAP is computed from OHLCV (indicators/vwap.py)",
            "timestamp_semantics": "UTC index = bar START; usable at bar_start + interval",
            "timezone": "UTC", "rth_only": True,
            "requested_start_utc": min(u["requested_start_utc"] for u in u_here),
            "requested_end_utc": max(u["requested_end_utc"] for u in u_here),
            "actual_first_timestamp": df.index.min().isoformat() if len(df) else None,
            "actual_last_timestamp": df.index.max().isoformat() if len(df) else None,
            "row_count": int(len(df)), "expected_row_count": int(sum(u["checks"].get("expected_bars", 0) for u in u_here)),
            "extended_rows_excluded": int(sum(u["checks"].get("extended_rows", 0) for u in u_here)),
            "sessions": [u["session"] for u in u_here],
            "content_sha256": content_sha256(df), "file_sha256": fsha, "acquisition_utc": acq_utc,
        }
        write_json_once(snap_dir / f"{sym}_{iv}.meta.json", meta)
        files[name] = {"file_sha256": fsha, "content_sha256": meta["content_sha256"], "row_count": meta["row_count"]}
        for u in u_here:
            u["data_file"] = name
    for (sym, iv), parts in sorted(ext_frames.items()):
        name = f"raw/{sym}_{iv}_extended.parquet"
        df = pd.concat(parts).sort_index(kind="mergesort")
        files[name] = {"file_sha256": write_parquet_once(snap_dir / name, df[list(STORED_COLUMNS)]),
                       "content_sha256": content_sha256(df), "row_count": int(len(df)), "role": "provenance only"}

    write_json_once(snap_dir / "environment.json", env)
    write_json_once(snap_dir / "files.json", files)
    write_json_once(snap_dir / "units.json", units)
    status_counts: dict[str, int] = defaultdict(int)
    for u in units:
        status_counts[u["status"]] += 1
    rechecks: dict[str, int] = defaultdict(int)
    for u in units:
        if "recheck" in u:
            rechecks[u["recheck"]["status"]] += 1
    run = {
        "schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "protocol_doc": PROTOCOL_DOC,
        "snapshot_id": snapshot_id, "run_started_utc": run_started, "run_finished_utc": acq_utc,
        "provider_config": client.config.as_dict(), "calendar": calendar_info(),
        "segments": {seg: [x.session.isoformat() for x in sessions if x.segment == seg]
                     for seg in ("warmup", "research", "embargo")},
        "symbols": symbols, "intervals": list(intervals), "recheck": recheck,
        "planned_units": len(plan), "unit_status_counts": dict(status_counts), "recheck_status_counts": dict(rechecks),
        "aborted": aborted, "max_requested_end_utc": max(u["requested_end_utc"] for u in units),
        "environment_sha256": env.get("environment_sha256"), "git_commit": env.get("git_commit"),
        "protocol": env.get("protocol"),
    }
    write_json_once(snap_dir / "run.json", run)
    manifest = build_manifest(root, expected)
    run["ledger"] = manifest["ledger"]
    run["status"] = "ABORTED" if aborted else ("COMPLETE" if manifest["ledger"]["complete"] else "INCOMPLETE")
    return run


def build_manifest(root: Path, expected: list[Unit]) -> dict[str, Any]:
    """Derived index (regenerable, not source data) over all v1.1 research snapshots."""
    check_location(root)
    snaps = []
    for snap in sorted((Path(root) / "snapshots").glob("*/run.json")):
        d = snap.parent
        run = json.loads(snap.read_text(encoding="utf-8"))
        snaps.append({"snapshot_id": run["snapshot_id"], "run_finished_utc": run["run_finished_utc"],
                      "unit_status_counts": run["unit_status_counts"], "recheck_status_counts": run["recheck_status_counts"],
                      "aborted": run["aborted"], "git_commit": run["git_commit"],
                      "run_sha256": hashlib.sha256(snap.read_bytes()).hexdigest(),
                      "units_sha256": hashlib.sha256((d / "units.json").read_bytes()).hexdigest(),
                      "files": json.loads((d / "files.json").read_text(encoding="utf-8"))})
    ledger = account(root, expected)
    manifest = {"schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "snapshots": snaps,
                "ledger": {k: v for k, v in ledger.items() if k != "pending"}, "pending_units": ledger["pending"][:200],
                "note": "Derived index. Structural facts only; no trading or performance information."}
    path = Path(root) / "manifest.json"
    if path.exists():
        path.chmod(0o644)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- preflight / CLI

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol_identity() -> dict[str, Any]:
    path = ROOT_DIR / PROTOCOL_DOC
    if not path.exists():
        raise PreflightError(f"protocol file missing: {PROTOCOL_DOC}")
    try:
        _git("ls-files", "--error-unmatch", PROTOCOL_DOC)
    except subprocess.CalledProcessError as exc:
        raise PreflightError(f"protocol file is not committed: {PROTOCOL_DOC}") from exc
    return {"path": PROTOCOL_DOC, "sha256": _sha(path), "commit": _git("log", "-1", "--format=%H", "--", PROTOCOL_DOC).strip()}


def preflight() -> dict[str, Any]:
    problems: list[str] = []
    baseline = json.loads(INTEGRITY_BASELINE.read_text(encoding="utf-8"))["hashes"]
    current = hash_dirs()
    changed = sorted(d for d in baseline if baseline.get(d) != current.get(d))
    if changed:
        problems.append(f"frozen data/artifacts changed: {changed}")
    lines = [ln for ln in _git("status", "--porcelain", "--untracked-files=all").splitlines() if ln.strip()]
    tracked = [ln for ln in lines if not ln.startswith("??")]
    untracked = [ln[3:].strip() for ln in lines if ln.startswith("??")]
    unexpected = [u for u in untracked if not any(u.endswith(a) for a in GIT_UNTRACKED_ALLOWLIST)]
    if tracked or unexpected:
        problems.append(f"git working tree not clean: tracked={tracked} untracked={unexpected}")
    s1, s2 = research_acquisition_sessions(), research_acquisition_sessions()
    if s1 != s2 or len(s1) != 81 or s1[-1].session != DAY15G_LAST_SESSION:
        problems.append("calendar did not resolve the 81 deterministic DAY-15G sessions")
    try:
        proto = protocol_identity()
    except PreflightError as exc:
        problems.append(str(exc))
        proto = {}
    if problems:
        raise PreflightError("; ".join(problems))
    return {"passed": True, "frozen_dirs_checked": len(baseline), "git_commit": _git("rev-parse", "HEAD").strip(),
            "untracked": untracked, "sessions": len(s1), "protocol": proto}


def _tree_hashes(base: Path) -> dict[str, str]:
    if not base.exists():
        return {}
    return {str(p.relative_to(ROOT_DIR)).replace("\\", "/"): _sha(p) for p in sorted(base.rglob("*")) if p.is_file()}


def write_integrity_report(run: dict[str, Any], pre: dict[str, Any], root: Path = RESEARCH_ROOT) -> Path:
    """The only artifact this command writes: artifacts/day15/day15g-integrity.json (structural facts only)."""
    frozen = hash_dirs()
    report = {
        "protocol_version": PROTOCOL_VERSION, "protocol": pre.get("protocol"),
        "snapshot_id": run.get("snapshot_id"), "run_status": run.get("status"),
        "unit_status_counts": run.get("unit_status_counts"), "ledger": run.get("ledger"),
        "max_requested_end_utc": run.get("max_requested_end_utc"),
        "dataset_manifest": str((Path(root) / "manifest.json").relative_to(ROOT_DIR)).replace("\\", "/"),
        "dataset_manifest_sha256": _sha(Path(root) / "manifest.json"),
        "frozen_v10_hashes": frozen,
        "frozen_v10_dir_digests": {d: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
                                   for d, v in frozen.items()},
        "oos_cache_protocol_v1_0_hashes": _tree_hashes(ROOT_DIR / "data" / "oos_cache" / "protocol_v1.0"),
        "day15_doc_hashes": {f: _sha(ROOT_DIR / "artifacts" / "day15" / f) for f in DAY15_DOCS
                             if (ROOT_DIR / "artifacts" / "day15" / f).exists()},
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    INTEGRITY_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return INTEGRITY_REPORT


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
    ap = argparse.ArgumentParser(description="DAY-15G v1.1 research acquisition (no OOS)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--capture", action="store_true")
    ap.add_argument("--recheck", action="store_true")
    a = ap.parse_args(argv)
    sessions = research_acquisition_sessions()
    expected = expected_units(sessions, v11_universe())
    if a.dry_run:
        acc = accepted_units(RESEARCH_ROOT)
        pending = [u for u in expected if u not in acc]
        print(json.dumps({"sessions": len(sessions), "first": sessions[0].session.isoformat(),
                          "last": sessions[-1].session.isoformat(),
                          "segments": {seg: sum(1 for s in sessions if s.segment == seg)
                                       for seg in ("warmup", "research", "embargo")},
                          "expected_units": len(expected), "accepted_units": len(expected) - len(pending),
                          "planned_requests": len(expected) if a.recheck else len(pending),
                          "provider_config": AlpacaBarsConfig().as_dict()}, indent=2))
        return 0
    pre = preflight()
    from acquisition.v1_1.environment import capture_v11_environment
    env = capture_v11_environment(pre["protocol"])
    key, secret = _credentials()
    client = AlpacaBarsClient(key, secret)
    run = capture(client=client, env=env, recheck=a.recheck, log=lambda m: print(m, flush=True))
    if run.get("planned_units", 1) == 0:
        print(json.dumps({"status": run["status"], "ledger": {k: v for k, v in run["ledger"].items() if k != "pending"}}))
        return 0
    path = write_integrity_report(run, pre)
    print(json.dumps({k: run.get(k) for k in ("status", "snapshot_id", "unit_status_counts", "recheck_status_counts",
                                              "aborted", "max_requested_end_utc", "ledger")}, indent=2))
    print(f"integrity report: {path}")
    return 0 if run["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    sys.exit(main())
