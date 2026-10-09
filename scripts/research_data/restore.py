"""scripts/research_data/restore.py: restore an immutable vault version (DAY-26).

    python -m scripts.research_data.restore --version protocol-v2-historical-v1 [--components stage_r stage_h evidence]
                                            [--dest data/oos_cache/protocol_v2] [--from-dir DIR]

Downloads only the selected release assets from the private data repository with the GitHub CLI's existing
credentials (or GH_TOKEN), verifies them against the pinned manifest in scripts/research_data/vaults/, and restores
them without ever overwriting an existing unit. Re-running is a verified no-op. Exit code 1 on any mismatch.
No market-data provider is contacted; no forward data is fetched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts.research_data.vault import (
    DATA_REPO, DEFAULT_DEST, VAULTS_DIR, VaultError, dir_fetch, gh_fetch, load_pinned, restore,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="immutable vault version id (release tag)")
    ap.add_argument("--components", nargs="*", help="subset of components (default: all)")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--repo", default=DATA_REPO)
    ap.add_argument("--from-dir", type=Path, help="read assets from a local directory instead of GitHub")
    ap.add_argument("--vaults-dir", type=Path, default=VAULTS_DIR, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        pinned = load_pinned(a.version, a.vaults_dir)
        fetch = dir_fetch(a.from_dir) if a.from_dir else gh_fetch(a.version, a.repo)
        rep = restore(pinned, a.dest, fetch, a.components)
    except VaultError as e:
        print(f"RESTORE FAILED (nothing overwritten): {e}", file=sys.stderr)
        return 1
    for u in rep["units"]:
        print(f"{u['action']:>36}  {u['path']}")
    print(json.dumps({"version": rep["version"], "dest": rep["dest"], "components": rep["components"]}, indent=2))
    print("RESTORE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
