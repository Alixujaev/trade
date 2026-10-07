"""acquisition/pipeline.py: one symbol/interval acquisition step.

fetch (adapter) -> structural checks -> metadata -> write-once snapshot (+ environment manifest).
No signal, indicator, return or performance computation happens anywhere in this path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from acquisition.contract import OOS_RULE
from acquisition.provider_adapter import YFinanceAdapter
from acquisition.snapshot import _check_location, _write_readonly, build_metadata, write_snapshot
from acquisition.validation import structural_checks


def write_environment_manifest(root: Path, snapshot_id: str, env: dict[str, Any]) -> Path:
    """Write the snapshot's environment manifest once; an existing one is never replaced."""
    _check_location(root)
    snap_dir = Path(root) / "snapshots" / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / "environment.json"
    if not path.exists():
        _write_readonly(path, json.dumps(env, indent=2, sort_keys=True).encode("utf-8"))
    return path


def acquire_one(
    adapter: YFinanceAdapter, root: Path, snapshot_id: str, symbol: str, interval: str,
    start: datetime, end: datetime, env: dict[str, Any], extra_meta: dict[str, Any] | None = None,
    part: str | None = None,
) -> dict[str, Any]:
    _check_location(root)
    df, request = adapter.fetch(symbol, interval, start, end)
    request["session_rule"] = OOS_RULE
    checks = structural_checks(df, interval)
    meta = build_metadata(
        df, symbol=symbol, interval=interval, snapshot_id=snapshot_id, request=request, checks=checks,
        environment_digest=env.get("environment_sha256"), acquisition_utc=datetime.now(timezone.utc).isoformat(),
    )
    meta["git_commit"] = env.get("git_commit")
    meta["git_dirty"] = env.get("git_dirty")
    meta.update(extra_meta or {})
    write_environment_manifest(root, snapshot_id, env)
    result = write_snapshot(root, snapshot_id, symbol, interval, df, meta, part=part)
    result["structural_checks_passed"] = checks["passed"]
    result["structural_errors"] = checks["errors"]
    result["metadata"] = meta
    result["frame"] = df
    return result
