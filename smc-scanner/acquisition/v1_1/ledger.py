"""acquisition/v1_1/ledger.py: v1.1 research completeness ledger.

A unit is (session, symbol, interval). It is accepted only if a snapshot's units.json marks it COMPLETE and
the referenced data file's bytes still match the recorded SHA-256. The earliest snapshot wins; later
re-acquisitions never replace it. Reads JSON metadata and file bytes only (no parquet parsing).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

Unit = tuple[str, str, str]   # (session_iso, symbol, interval)


def _snapshot_dirs(root: Path) -> list[Path]:
    snaps = Path(root) / "snapshots"
    if not snaps.exists():
        return []
    return sorted(p for p in snaps.iterdir() if p.is_dir() and (p / "units.json").exists())


def accepted_units(root: Path) -> dict[Unit, dict[str, Any]]:
    out: dict[Unit, dict[str, Any]] = {}
    file_ok: dict[Path, bool] = {}
    for snap in _snapshot_dirs(root):
        units = json.loads((snap / "units.json").read_text(encoding="utf-8"))
        files = json.loads((snap / "files.json").read_text(encoding="utf-8")) if (snap / "files.json").exists() else {}
        for u in units:
            if u.get("status") != "COMPLETE" or not u.get("data_file"):
                continue
            path = snap / u["data_file"]
            expected = files.get(u["data_file"], {}).get("file_sha256")
            if path not in file_ok:
                file_ok[path] = path.exists() and expected is not None and \
                    hashlib.sha256(path.read_bytes()).hexdigest() == expected
            if not file_ok[path]:
                continue
            key = (u["session"], u["symbol"], u["interval"])
            out.setdefault(key, {"snapshot_id": snap.name, "data_file": u["data_file"],
                                 "unit_content_sha256": u.get("unit_content_sha256")})
    return out


def account(root: Path, expected: list[Unit]) -> dict[str, Any]:
    """Every expected unit is counted exactly once: accepted or not accepted."""
    acc = accepted_units(root)
    exp = list(dict.fromkeys(expected))
    accepted = [u for u in exp if u in acc]
    pending = [u for u in exp if u not in acc]
    return {"expected_units": len(exp), "accepted_units": len(accepted), "pending_units": len(pending),
            "pending": [list(u) for u in pending], "complete": not pending,
            "duplicate_expected_entries": len(expected) - len(exp)}
