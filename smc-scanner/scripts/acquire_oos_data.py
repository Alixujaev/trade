"""scripts/acquire_oos_data.py: OOS data acquisition entry point (DAY-15B).

Usage:
    python scripts/acquire_oos_data.py --dry-run      # plan only: no network, no market data
    python scripts/acquire_oos_data.py --capture      # preflight, then capture all completed OOS sessions

--capture runs the preflight (frozen hashes, clean git, 60 deterministic sessions) and refuses to download
if anything fails. Output is structural only; no signals, returns or performance values are computed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# UTF-8 stdout configuration for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add smc-scanner root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from acquisition.capture_policy import CAPTURE_NOT_BEFORE_ET, MARKET_CLOSE_ET, capturable_sessions
from acquisition.contract import (
    OOS_ROOT, OOS_RULE, PROTOCOL_COMMIT, PROTOCOL_VERSION, SCHEMA_VERSION, SUPPORTED_INTERVALS,
    ProviderConfig, oos_universe,
)
from acquisition.environment import capture_environment
from acquisition.report import REPORT_DIR, render_report, write_report
from acquisition.run import PreflightError, capture_run, preflight
from acquisition.sessions import calendar_info, resolve_oos_sessions


def dry_run_plan(now: datetime) -> dict:
    sessions = resolve_oos_sessions()
    cap = capturable_sessions(sessions, now)
    env = capture_environment()
    symbols = oos_universe()
    return {
        "mode": "DRY RUN (no network, no market data read or written)",
        "protocol": {"version": PROTOCOL_VERSION, "commit": PROTOCOL_COMMIT, "schema": SCHEMA_VERSION},
        "oos_rule": OOS_RULE,
        "calendar": calendar_info(),
        "oos_sessions": [s.session.isoformat() for s in sessions],
        "early_close_sessions": [s.session.isoformat() for s in sessions if s.early_close],
        "capture_policy": {"market_close_et": MARKET_CLOSE_ET.isoformat(), "capture_not_before_et": CAPTURE_NOT_BEFORE_ET.isoformat()},
        "capturable_now": [s.session.isoformat() for s in cap],
        "symbols": symbols,
        "intervals": sorted(SUPPORTED_INTERVALS),
        "provider_config": {"provider": ProviderConfig().provider, **ProviderConfig().download_kwargs()},
        "snapshot_root": str(OOS_ROOT),
        "environment": {k: env[k] for k in ("python_version", "distributions_sha256", "environment_sha256", "git_commit", "git_dirty")},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OOS data acquisition (DAY-15B)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show the acquisition plan without any download")
    mode.add_argument("--capture", action="store_true", help="Preflight, then capture completed OOS sessions")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.dry_run:
        print(json.dumps(dry_run_plan(now), indent=2))
        return 0
    try:
        pf = preflight()
    except PreflightError as exc:
        print(f"[PREFLIGHT FAILED] {exc}\nNothing was downloaded.", file=sys.stderr)
        return 3
    env = capture_environment()
    run = capture_run(now=now, env=env, acquisition_commit=pf["git"]["commit"])
    manifest = json.loads((OOS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    write_report(REPORT_DIR / "day15b-acquisition.md", render_report(run, manifest, pf))
    missing = [r for r in run["results"] if r["status"] == "MISSING"]
    print(f"[DONE] snapshot {run['snapshot_id']}: {len(run['results']) - len(missing)}/{len(run['results'])} "
          f"symbol-interval files written; report artifacts/day15/day15b-acquisition.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
