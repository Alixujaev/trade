"""acquisition/environment.py: exact environment manifest (requirements.txt is unpinned; no lock file)."""

from __future__ import annotations

import hashlib
from importlib import metadata
import json
import platform
import subprocess
import sys
from typing import Any

from acquisition.contract import ROOT_DIR


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def capture_environment() -> dict[str, Any]:
    """pip-freeze-equivalent manifest from importlib.metadata plus code identity."""
    dists = sorted(
        {f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions() if d.metadata.get("Name")},
        key=str.lower,
    )
    status = _git("status", "--porcelain")
    env = {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "distributions": dists,
        "distributions_sha256": hashlib.sha256("\n".join(dists).encode("utf-8")).hexdigest(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "git_dirty_files": status.splitlines() if status else [],
    }
    env["environment_sha256"] = hashlib.sha256(
        json.dumps({k: env[k] for k in ("python_version", "distributions")}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return env
