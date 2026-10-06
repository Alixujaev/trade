"""acquisition/v1_1/snapshot.py: write-once v1.1 snapshot files and content hashing.

Files are created with mode 'xb' (fail if present) and made read-only (acquisition.snapshot._write_readonly).
Nothing is overwritten; a repeated acquisition goes into a new snapshot directory and is compared by hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acquisition.snapshot import _write_readonly
from acquisition.v1_1.contract import FORBIDDEN_WRITE_ROOTS, STORED_COLUMNS


class SnapshotPathError(ValueError):
    """Refused write location (frozen research cache, artifacts, or the v1.0 OOS tree)."""


def check_location(path: Path) -> None:
    rp = Path(path).resolve()
    for root in FORBIDDEN_WRITE_ROOTS:
        if rp.is_relative_to(root.resolve()):
            raise SnapshotPathError(f"refusing to write v1.1 snapshot data under {root}")


def canonical_bytes(df: pd.DataFrame) -> bytes:
    """Deterministic serialisation: sorted UTC int64-ns index + fixed v1.1 columns (float repr)."""
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


def write_parquet_once(path: Path, df: pd.DataFrame) -> str:
    """Write-once parquet; returns the file SHA-256. Raises FileExistsError if the file exists."""
    path = Path(path)
    check_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"snapshot file already exists (write-once): {path}")
    tmp = path.with_name(f".{path.name}.tmp")
    df.to_parquet(tmp)
    payload = tmp.read_bytes()
    tmp.unlink()
    _write_readonly(path, payload)
    return hashlib.sha256(payload).hexdigest()


def write_json_once(path: Path, obj: Any) -> str:
    path = Path(path)
    check_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, sort_keys=True, default=str).encode("utf-8")
    _write_readonly(path, payload)
    return hashlib.sha256(payload).hexdigest()


def compare_status(original_sha: str | None, new_sha: str) -> str:
    """IDENTICAL / DISCREPANCY against an accepted original; WRITTEN when there is none."""
    if original_sha is None:
        return "WRITTEN"
    return "IDENTICAL" if original_sha == new_sha else "DISCREPANCY"
