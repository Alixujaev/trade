"""acquisition/snapshot.py: write-once OOS snapshots, content hashing and overlap comparison.

Rules (DAY-14 data-expansion-spec §4, DAY-15A acquisition-design):
- A snapshot file is written once and made read-only; it is never overwritten, refreshed or merged into.
- Re-acquiring the same snapshot is compared by content hash: IDENTICAL -> an attempt record is added;
  different -> DISCREPANCY, the new data is preserved separately under conflicts/ and the original kept.
- Overlapping observations between snapshots are compared cell by cell; nothing is chosen or replaced.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

import numpy as np
import pandas as pd

from acquisition.contract import FORBIDDEN_WRITE_ROOTS, PROTOCOL_VERSION, SCHEMA_VERSION, STORED_COLUMNS


class SnapshotPathError(ValueError):
    """Refused write location (frozen research cache or research artifacts)."""


def canonical_bytes(df: pd.DataFrame) -> bytes:
    """Deterministic serialisation independent of the parquet writer: sorted UTC int64-ns index + fixed columns."""
    d = df[list(STORED_COLUMNS)].copy()
    d.index = d.index.tz_convert("UTC")
    d = d.sort_index(kind="mergesort")
    ns = d.index.asi8.astype(np.int64)
    vals = d.to_numpy(dtype=np.float64)
    lines = ["ts_ns," + ",".join(STORED_COLUMNS)]
    lines += [f"{t}," + ",".join(repr(float(x)) for x in row) for t, row in zip(ns, vals)]
    return ("\n".join(lines) + "\n").encode("ascii")


def content_sha256(df: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_bytes(df)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _check_location(path: Path) -> None:
    rp = Path(path).resolve()
    for root in FORBIDDEN_WRITE_ROOTS:
        if rp.is_relative_to(root.resolve()):
            raise SnapshotPathError(f"refusing to write OOS snapshot data under {root}")


def _write_readonly(path: Path, data: bytes) -> None:
    with open(path, "xb") as f:  # 'x': fail if the file already exists
        f.write(data)
    os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def build_metadata(
    df: pd.DataFrame, *, symbol: str, interval: str, snapshot_id: str, request: dict[str, Any],
    checks: dict[str, Any], environment_digest: str | None, acquisition_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "snapshot_id": snapshot_id,
        "symbol": symbol,
        "interval": interval,
        "acquisition_utc": acquisition_utc,
        "requested_start": request.get("requested_start"),
        "requested_end": request.get("requested_end"),
        "session_rule": request.get("session_rule"),
        "actual_first_timestamp": df.index.min().isoformat() if len(df) else None,
        "actual_last_timestamp": df.index.max().isoformat() if len(df) else None,
        "row_count": int(len(df)),
        "timezone": str(df.index.tz),
        "timestamp_semantics": "bar OPEN (UTC); signal usable at bar_open + interval",
        "provider": request.get("provider"),
        "provider_version": request.get("provider_version"),
        "provider_config": request.get("provider_config"),
        "columns": list(STORED_COLUMNS),
        "content_sha256": content_sha256(df),
        "structural_checks": checks,
        "environment_sha256": environment_digest,
        "request": request,
    }


def write_snapshot(
    root: Path, snapshot_id: str, symbol: str, interval: str, df: pd.DataFrame, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Write-once store. Returns {'status': 'WRITTEN' | 'IDENTICAL' | 'DISCREPANCY', ...}."""
    _check_location(root)
    snap_dir = Path(root) / "snapshots" / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    data_path = snap_dir / f"{symbol}_{interval}.parquet"
    meta_path = snap_dir / f"{symbol}_{interval}.meta.json"
    new_hash = content_sha256(df)
    if metadata.get("content_sha256") != new_hash:
        raise ValueError("metadata content_sha256 does not match the frame")

    if not data_path.exists():
        tmp = snap_dir / f".{symbol}_{interval}.parquet.tmp"
        df[list(STORED_COLUMNS)].to_parquet(tmp)
        payload = tmp.read_bytes()
        tmp.unlink()
        _write_readonly(data_path, payload)
        meta = dict(metadata, file_sha256=file_sha256(data_path))
        _write_readonly(meta_path, json.dumps(meta, indent=2, sort_keys=True).encode("utf-8"))
        return {"status": "WRITTEN", "data_path": str(data_path), "content_sha256": new_hash}

    original_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    original_hash = original_meta["content_sha256"]
    if content_sha256(pd.read_parquet(data_path)) != original_hash:
        raise ValueError(f"stored snapshot {data_path} no longer matches its recorded content hash")
    stamp = _utc_stamp()
    attempts = snap_dir / "attempts"
    attempts.mkdir(exist_ok=True)
    record = {"symbol": symbol, "interval": interval, "attempt_utc": stamp, "original_content_sha256": original_hash,
              "new_content_sha256": new_hash}
    if new_hash == original_hash:
        record["status"] = "IDENTICAL"
    else:
        record["status"] = "DISCREPANCY"
        conflicts = snap_dir / "conflicts"
        conflicts.mkdir(exist_ok=True)
        cpath = conflicts / f"{stamp}_{symbol}_{interval}.parquet"
        tmp = conflicts / f".{stamp}.tmp"
        df[list(STORED_COLUMNS)].to_parquet(tmp)
        payload = tmp.read_bytes()
        tmp.unlink()
        _write_readonly(cpath, payload)
        record["conflict_path"] = str(cpath)
        record["overlap"] = compare_overlap(pd.read_parquet(data_path), df)
    _write_readonly(attempts / f"{stamp}_{symbol}_{interval}.json", json.dumps(record, indent=2, sort_keys=True).encode("utf-8"))
    return record


def compare_overlap(a: pd.DataFrame, b: pd.DataFrame) -> dict[str, Any]:
    """Compare two snapshots on common timestamps. Reports differences; never picks a winner."""
    ia, ib = a.index.tz_convert("UTC"), b.index.tz_convert("UTC")
    common = ia.intersection(ib)
    out: dict[str, Any] = {
        "common_timestamps": int(len(common)),
        "only_in_a": int(len(ia.difference(ib))),
        "only_in_b": int(len(ib.difference(ia))),
    }
    aa = a.set_axis(ia).loc[common, list(STORED_COLUMNS)]
    bb = b.set_axis(ib).loc[common, list(STORED_COLUMNS)]
    neq = ~((aa == bb) | (aa.isna() & bb.isna()))
    rows = neq.any(axis=1)
    out["differing_rows"] = int(rows.sum())
    out["differing_cells_by_column"] = {c: int(neq[c].sum()) for c in STORED_COLUMNS}
    out["differing_timestamps"] = [t.isoformat() for t in common[rows.to_numpy()]][:500]
    out["identical_on_overlap"] = out["differing_rows"] == 0
    return out
