"""scripts/research_data/publish.py: maintainer-only build / upload of an immutable vault version (DAY-26).

    python -m scripts.research_data.publish build  --out <staging_dir> [--pin]
    python -m scripts.research_data.publish upload --staging <staging_dir> --confirm

build:  verifies the local Stage R / Stage H trees against the signed-off manifest hashes (backtest/v2/data.py) and
        the contract boundaries (acquisition/v2/contract.py), writes deterministic archives + vault-manifest.json to
        a staging directory OUTSIDE the repository, then round-trips them through a full restore into a temp dir.
        --pin copies vault-manifest.json to scripts/research_data/vaults/<version>.json (never overwrites a
        different pinned manifest). The source trees are only read.
upload: requires the staged manifest to equal the pinned one; creates the PRIVATE data repository only if absent
        (refuses a public one), refuses an existing release tag, creates the release, then downloads every asset
        back into a fresh temp dir and runs the full restore verification. Never edits or deletes a release.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from scripts.research_data.vault import (
    DATA_REPO, DEFAULT_DEST, MANIFEST_ASSET, ROOT_DIR, SCHEMA, VAULTS_DIR, VaultError, build_archive, check_rel_path,
    check_version, dir_fetch, gh_fetch, parse_manifest, restore, sha256_file, verify_tree,
)

VERSION = "protocol-v2-historical-v1"
READY_H = "READY_FOR_HISTORICAL_HOLDOUT_EVALUATION"


def protocol_v2_spec() -> dict[str, Any]:
    """Vault content for VERSION. Anchors come from the signed-off constants, never re-typed here."""
    from acquisition.v2 import contract as k
    from backtest.v2 import data as d
    r, h = d.SNAPSHOT_ID, d.SNAPSHOT_ID_H
    review = lambda name, **exp: {"path": f"stage_r/reviews/{name}", "kind": "dir",
                                  "expect": {"manifest.json": {"source_manifest_sha256": d.SNAPSHOT_MANIFEST_SHA256, **exp}}}
    return {
        "stage_r": {
            "boundary": {"first_session": k.STAGE_R_FIRST_SESSION.isoformat(), "last_session": k.STAGE_R_LAST_SESSION.isoformat()},
            "units": [
                {"path": f"stage_r/{r}", "kind": "dir", "anchor": "stage_r_snapshot",
                 "pinned": d.SNAPSHOT_MANIFEST_SHA256, "expect": {"manifest.json": {"snapshot_id": r}}},
                review(f"v2_0_2__{r}"), review(f"v2_0_3__{r}"), review(f"v2_0_3__{r}__day18g"),
                {**review(f"v2_0_4__{r}", final_status="USABLE_FOR_RESEARCH"), "anchor": "stage_r_review_output",
                 "pinned": d.REVIEW_OUTPUT_MANIFEST_SHA256},
            ]},
        "stage_h": {
            "boundary": {"first_session": k.STAGE_H_FIRST_SESSION.isoformat(), "last_session": k.STAGE_H_LAST_SESSION.isoformat()},
            "units": [
                {"path": f"stage_h/{h}", "kind": "dir", "anchor": "stage_h_snapshot",
                 "pinned": d.SNAPSHOT_MANIFEST_SHA256_H, "expect": {"manifest.json": {"snapshot_id": h}}},
                {"path": f"stage_h/validation__{h}", "kind": "dir",
                 "expect": {"manifest.json": {"snapshot_manifest_sha256": d.SNAPSHOT_MANIFEST_SHA256_H}}},
                {"path": f"stage_h/{d.VALIDATION_H}", "kind": "dir", "anchor": "stage_h_validation",
                 "pinned": d.VALIDATION_H_MANIFEST_SHA256,
                 "expect": {"manifest.json": {"status": READY_H, "snapshot_manifest_sha256": d.SNAPSHOT_MANIFEST_SHA256_H},
                            "validation_report.json": {"status": READY_H, "snapshot_manifest_sha256": d.SNAPSHOT_MANIFEST_SHA256_H}}},
            ]},
        "evidence": {"asset_prefix": "evidence-sec", "boundary": None, "units": [{"glob": "evidence/sec/*.htm", "kind": "file", "content_addressed": True}]},
    }


def _files_of(src: Path, unit: dict) -> list[str]:
    p = src.joinpath(*unit["path"].split("/"))
    if p.is_symlink():
        raise VaultError(f"{unit['path']}: is a link")
    if unit["kind"] == "file":
        return [unit["path"]]
    if not p.is_dir():
        raise VaultError(f"{unit['path']}: missing in source")
    out = []
    for q in sorted(p.rglob("*")):
        if q.is_symlink():
            raise VaultError(f"{q}: is a link")
        if q.is_file():
            out.append(check_rel_path(q.relative_to(src).as_posix()))
    return out


def build(src: Path, out: Path, version: str, spec: dict[str, Any], source_commit: str,
          forward_statement: str = "") -> bytes:
    """Write archives + vault-manifest.json into the empty directory `out`; return the manifest bytes."""
    src, out = Path(src), Path(out)
    check_version(version)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise VaultError(f"staging directory is not empty: {out}")
    components: dict[str, Any] = {}
    anchors: dict[str, Any] = {}
    for name in sorted(spec):
        cs = spec[name]
        units: list[dict] = []
        for u in cs["units"]:
            if "glob" in u:
                matches = sorted(p.relative_to(src).as_posix() for p in src.glob(u["glob"]) if p.is_file())
                if not matches:
                    raise VaultError(f"{name}: no files match {u['glob']}")
                units += [{k: v for k, v in u.items() if k != "glob"} | {"path": m} for m in matches]
            else:
                units.append(dict(u))
        files: list[dict] = []
        for u in units:
            for rel in _files_of(src, u):
                p = src.joinpath(*rel.split("/"))
                files.append({"path": rel, "size": p.stat().st_size, "sha256": sha256_file(p)})
            if u["kind"] == "dir":
                u["manifest_sha256"] = sha256_file(src.joinpath(*u["path"].split("/"), "manifest.json"))
            pinned = u.pop("pinned", None)
            if pinned is not None and u["manifest_sha256"] != pinned:
                raise VaultError(f"{u['path']}: manifest.json SHA-256 differs from the signed-off value {pinned}")
            if "anchor" in u:
                anchors[u["anchor"]] = {"path": u["path"], "manifest_sha256": u["manifest_sha256"]}
        asset = f"{cs.get('asset_prefix', name)}-{version}.tar.gz"
        build_archive(src, [f["path"] for f in files], out / asset)
        components[name] = {"asset": asset, "size": (out / asset).stat().st_size, "sha256": sha256_file(out / asset),
                            "boundary": cs["boundary"], "units": units, "files": sorted(files, key=lambda f: f["path"])}
    manifest = {"schema": SCHEMA, "version": version, "data_repo": DATA_REPO,
                "restore_root": "data/oos_cache/protocol_v2", "source_commit": source_commit,
                "forward_data": forward_statement, "anchors": anchors, "components": components}
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    parsed = parse_manifest(raw)
    verify_tree(src, parsed)                                    # source matches what was archived, boundaries hold
    (out / MANIFEST_ASSET).write_bytes(raw)
    with tempfile.TemporaryDirectory(prefix="vault-roundtrip-") as tmp:
        restore(raw, Path(tmp) / "dest", dir_fetch(out))        # archives restore and verify end to end
    return raw


def pin(raw: bytes, version: str, vaults_dir: Path = VAULTS_DIR) -> Path:
    p = Path(vaults_dir) / f"{check_version(version)}.json"
    if p.exists():
        if p.read_bytes() != raw:
            raise VaultError(f"a different pinned manifest already exists at {p}; refusing to overwrite")
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    return p


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    if shutil.which("gh") is None:
        raise VaultError("GitHub CLI (gh) not found: install it and run `gh auth login`")
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise VaultError(f"gh {args[0]} {args[1] if len(args) > 1 else ''} failed: {r.stderr.strip()}")
    return r


def upload(staging: Path, version: str, repo: str = DATA_REPO, vaults_dir: Path = VAULTS_DIR) -> dict[str, Any]:
    staging = Path(staging)
    raw = (staging / MANIFEST_ASSET).read_bytes()
    pinned = Path(vaults_dir) / f"{check_version(version)}.json"
    if not pinned.is_file() or pinned.read_bytes() != raw:
        raise VaultError("staged vault manifest is not identical to the pinned manifest; run build --pin first")
    manifest = parse_manifest(raw)
    assets = [staging / MANIFEST_ASSET] + [staging / c["asset"] for c in manifest["components"].values()]
    for c in manifest["components"].values():
        if sha256_file(staging / c["asset"]) != c["sha256"]:
            raise VaultError(f"staged {c['asset']} does not match the manifest")
    _gh("auth", "status")
    view = _gh("repo", "view", repo, "--json", "isPrivate", check=False)
    created = False
    if view.returncode != 0:
        if "Could not resolve to a Repository" not in view.stderr:
            raise VaultError(f"gh repo view {repo} failed: {view.stderr.strip()}")
        _gh("repo", "create", repo, "--private", "--add-readme",
            "--description", "Immutable research-data snapshots for Alixujaev/trade (release assets only)")
        created = True
        view = _gh("repo", "view", repo, "--json", "isPrivate")
    if json.loads(view.stdout).get("isPrivate") is not True:
        raise VaultError(f"{repo} is not private; refusing to upload")
    if _gh("release", "view", version, "-R", repo, check=False).returncode == 0:
        raise VaultError(f"release {version} already exists in {repo}; versions are immutable, refusing")
    notes = (f"Immutable research-data vault version {version}. Restore and verify with\n"
             f"`python -m scripts.research_data.restore --version {version}` from the main repository.\n"
             f"Pinned manifest SHA-256: {sha256_file(staging / MANIFEST_ASSET)}\n{manifest.get('forward_data', '')}")
    _gh("release", "create", version, *map(str, assets), "-R", repo, "--title", version, "--notes", notes)
    # round trip: download back into a fresh temp dir and verify everything
    with tempfile.TemporaryDirectory(prefix="vault-download-") as tmp:
        fetch = gh_fetch(version, repo)
        dl = Path(tmp) / "assets"
        dl.mkdir()
        downloaded = {}
        for a in assets:
            got = fetch(a.name, dl)
            downloaded[a.name] = {"size": got.stat().st_size, "sha256": sha256_file(got),
                                  "matches_local": sha256_file(got) == sha256_file(a)}
            if not downloaded[a.name]["matches_local"]:
                raise VaultError(f"downloaded {a.name} differs from the uploaded file")
        rep = restore(raw, Path(tmp) / "restore", fetch)
    return {"repo": repo, "repo_created": created, "release": version, "downloaded": downloaded, "restore": rep}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--src", type=Path, default=DEFAULT_DEST)
    b.add_argument("--version", default=VERSION)
    b.add_argument("--pin", action="store_true")
    u = sub.add_parser("upload")
    u.add_argument("--staging", type=Path, required=True)
    u.add_argument("--version", default=VERSION)
    u.add_argument("--repo", default=DATA_REPO)
    u.add_argument("--confirm", action="store_true", help="required: publishes to the private data repository")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            if Path(a.out).resolve().is_relative_to(ROOT_DIR):
                raise VaultError("staging directory must be outside the repository")
            commit = subprocess.run(["git", "-C", str(ROOT_DIR), "rev-parse", "HEAD"], capture_output=True,
                                    text=True, check=True).stdout.strip()
            from acquisition.v2.contract import STAGE_H_ASOF
            raw = build(a.src, a.out, a.version, protocol_v2_spec(), commit,
                        f"No forward data: Stage R bars/events end {protocol_v2_spec()['stage_r']['boundary']['last_session']}, "
                        f"Stage H bars/events end {protocol_v2_spec()['stage_h']['boundary']['last_session']} "
                        f"(Stage H freeze {STAGE_H_ASOF}); nothing after the historical boundaries is included.")
            m = json.loads(raw)
            for c in m["components"].values():
                print(f"{c['asset']}  size={c['size']}  sha256={c['sha256']}  files={len(c['files'])}")
            print(f"{MANIFEST_ASSET}  sha256={sha256_file(Path(a.out) / MANIFEST_ASSET)}")
            if a.pin:
                print(f"pinned: {pin(raw, a.version)}")
            print("BUILD OK (verified + local round-trip restore)")
        else:
            if not a.confirm:
                raise VaultError("upload publishes to the private data repository; pass --confirm")
            rep = upload(a.staging, a.version, a.repo)
            print(json.dumps({k: v for k, v in rep.items() if k != "restore"}, indent=2))
            print(json.dumps(rep["restore"]["components"], indent=2))
            print("UPLOAD OK (downloaded back and verified)")
    except VaultError as e:
        print(f"PUBLISH FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
