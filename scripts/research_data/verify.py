"""scripts/research_data/verify.py: verify a local tree against a pinned vault version (DAY-26). Offline.

    python -m scripts.research_data.verify --version protocol-v2-historical-v1 [--components ...] [--dest DIR]

Checks every file (size + SHA-256), every snapshot / review / validation manifest, the review/validation bindings
and the historical date boundaries. Exit code 1 on any mismatch.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts.research_data.vault import DEFAULT_DEST, VAULTS_DIR, VaultError, load_pinned, parse_manifest, verify_tree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--components", nargs="*")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--vaults-dir", type=Path, default=VAULTS_DIR, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        rep = verify_tree(a.dest, parse_manifest(load_pinned(a.version, a.vaults_dir)), a.components)
    except VaultError as e:
        print(f"VERIFY FAILED: {e}", file=sys.stderr)
        return 1
    print(json.dumps(rep, indent=2))
    print("VERIFY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
