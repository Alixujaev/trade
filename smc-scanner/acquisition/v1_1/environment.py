"""acquisition/v1_1/environment.py: v1.1 environment manifest (no secrets)."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
import platform
from typing import Any

from acquisition.environment import capture_environment


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def capture_v11_environment(protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    env = capture_environment()
    env.update({
        "os": platform.platform(),
        "packages": {p: _version(p) for p in ("exchange_calendars", "requests", "pandas", "numpy", "pyarrow")},
        "alpaca_client": "requests (direct REST); alpaca-py SDK not used",
        "acquisition_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol or {},
    })
    return env
