"""scripts/research_data/vault.py: immutable research-data vault core (DAY-26).

Code and research artifacts live in the main repository; the immutable market-data snapshots live as versioned
release assets in the PRIVATE data repository; derived results are reproducible outputs, never source snapshots.

- A vault version is described by `vault-manifest.json`; the trust root is the byte copy of that manifest committed
  under scripts/research_data/vaults/<version>.json. A downloaded manifest must be byte-identical to it.
- Archive SHA-256 is verified BEFORE extraction; extraction is entry-by-entry into an empty temporary directory and
  rejects absolute/drive/backslash/`..` paths, links, devices, duplicates and any entry not in the manifest.
- Every restored file is verified (size + SHA-256); every snapshot / review / validation directory is re-verified
  against its own manifest.json with the existing `verify_snapshot`; bar indexes and event ex/event dates are
  checked against the per-component historical boundary.
- An existing unit is never overwritten: identical -> skipped (idempotent); different -> the restore fails and
  nothing is moved. Any mismatch raises VaultError (fail closed).
- Network: only `gh release download` from the data repository. No market-data provider is ever contacted and no
  forward data exists in, or is fetched by, the vault.
"""

from __future__ import annotations

from datetime import date
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from typing import Any, Callable, Iterable

SCHEMA = "trade-research-data/vault-manifest/1"
DATA_REPO = "Alixujaev/trade-research-data"
MANIFEST_ASSET = "vault-manifest.json"
ROOT_DIR = Path(__file__).resolve().parents[2]
VAULTS_DIR = Path(__file__).resolve().parent / "vaults"
DEFAULT_DEST = ROOT_DIR / "data" / "oos_cache" / "protocol_v2"
MARKET_TZ = "America/New_York"
BOUNDED_EVENT_FIELDS = ("ex_date", "event_date")
_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
_CHUNK = 1 << 20

Fetch = Callable[[str, Path], Path]


class VaultError(RuntimeError):
    """Any integrity, safety, boundary or overwrite violation. Nothing is changed after it is raised."""


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def check_rel_path(name: str) -> str:
    """A safe, POSIX-style relative path: no absolute/drive/UNC form, backslash, '.', '..', empty part or NUL."""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name or name.startswith("/"):
        raise VaultError(f"unsafe path: {name!r}")
    if any(part in ("", ".", "..") for part in name.split("/")):
        raise VaultError(f"unsafe path: {name!r}")
    return name


def check_version(version: str) -> str:
    if not _VERSION_RE.match(version or ""):
        raise VaultError(f"invalid vault version id: {version!r}")
    return version


# ---------------------------------------------------------------------------------------------------------- manifest

def parse_manifest(raw: bytes) -> dict[str, Any]:
    try:
        m = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise VaultError(f"vault manifest is not valid JSON: {e}") from None
    if m.get("schema") != SCHEMA:
        raise VaultError(f"unsupported vault manifest schema {m.get('schema')!r}")
    check_version(m.get("version", ""))
    comps = m.get("components")
    if not isinstance(comps, dict) or not comps:
        raise VaultError("vault manifest has no components")
    for name, c in comps.items():
        for key in ("asset", "size", "sha256", "files", "units"):
            if key not in c:
                raise VaultError(f"component {name}: missing {key}")
        check_rel_path(c["asset"])
        if "/" in c["asset"]:
            raise VaultError(f"component {name}: asset name must be a plain file name")
        paths = [check_rel_path(f["path"]) for f in c["files"]]
        if len(set(p.lower() for p in paths)) != len(paths):
            raise VaultError(f"component {name}: duplicate (or case-colliding) file paths")
        for u in c["units"]:
            check_rel_path(u["path"])
            if u["kind"] not in ("dir", "file"):
                raise VaultError(f"component {name}: unit {u['path']} has unknown kind {u['kind']!r}")
        owned = [p for p in paths if any(_in_unit(p, u) for u in c["units"])]
        if len(owned) != len(paths):
            raise VaultError(f"component {name}: files outside every unit")
    return m


def load_pinned(version: str, vaults_dir: Path = VAULTS_DIR) -> bytes:
    p = Path(vaults_dir) / f"{check_version(version)}.json"
    if not p.is_file():
        raise VaultError(f"no pinned vault manifest for version {version!r} at {p}")
    raw = p.read_bytes()
    parse_manifest(raw)
    return raw


def _in_unit(path: str, unit: dict) -> bool:
    return path == unit["path"] if unit["kind"] == "file" else path.startswith(unit["path"] + "/")


def _unit_files(comp: dict, unit: dict) -> dict[str, dict]:
    return {f["path"]: f for f in comp["files"] if _in_unit(f["path"], unit)}


# ---------------------------------------------------------------------------------------------------------- archive

def build_archive(src_root: Path, rel_files: Iterable[str], out: Path) -> None:
    """Deterministic tar.gz: sorted regular-file entries only, mtime 0, uid/gid 0, no owner names, mode 0444."""
    src_root = Path(src_root)
    with open(out, "xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for rel in sorted(rel_files):
            p = src_root / check_rel_path(rel)
            if p.is_symlink() or not p.is_file():
                raise VaultError(f"not a regular file: {rel}")
            ti = tarfile.TarInfo(rel)
            ti.size, ti.mtime, ti.mode, ti.type = p.stat().st_size, 0, 0o444, tarfile.REGTYPE
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            with open(p, "rb") as f:
                tar.addfile(ti, f)


def safe_extract(archive: Path, dest: Path, expected: dict[str, dict]) -> None:
    """Extract only the manifest-listed regular files of `archive` into the EMPTY directory `dest`, verifying each."""
    dest = Path(dest)
    if not dest.is_dir() or any(dest.iterdir()):
        raise VaultError(f"extraction target must be an existing empty directory: {dest}")
    base = dest.resolve()
    seen: set[str] = set()
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar:
            name = m.name
            try:
                check_rel_path(name)
            except VaultError:
                raise VaultError(f"unsafe archive entry: {name!r}") from None
            if not m.isreg():
                raise VaultError(f"unsafe archive entry (not a regular file): {name!r}")
            if name.lower() in seen:
                raise VaultError(f"duplicate archive entry: {name!r}")
            seen.add(name.lower())
            exp = expected.get(name)
            if exp is None:
                raise VaultError(f"archive entry not listed in the vault manifest: {name!r}")
            if m.size != exp["size"]:
                raise VaultError(f"{name}: archive size {m.size} != manifest size {exp['size']}")
            target = dest.joinpath(*name.split("/"))
            if not target.resolve().is_relative_to(base):
                raise VaultError(f"unsafe archive entry (escapes target): {name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            src = tar.extractfile(m)
            with open(target, "xb") as f:
                for chunk in iter(lambda: src.read(_CHUNK), b""):
                    h.update(chunk)
                    f.write(chunk)
            if h.hexdigest() != exp["sha256"]:
                raise VaultError(f"{name}: extracted SHA-256 does not match the vault manifest")
            os.chmod(target, stat.S_IREAD)
    missing = sorted(p for p in expected if p.lower() not in seen)
    if missing:
        raise VaultError(f"archive is missing files listed in the vault manifest: {missing}")


# ---------------------------------------------------------------------------------------------------------- verify

def _snapshot_check(unit_dir: Path, manifest_sha256: str) -> None:
    from acquisition.v2.reevaluate import ImmutabilityError, verify_snapshot   # lazy: heavy research imports
    try:
        verify_snapshot(unit_dir, manifest_sha256)
    except (ImmutabilityError, FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        raise VaultError(f"{unit_dir.name}: {e}") from None


def verify_unit(root: Path, comp: dict, unit: dict) -> None:
    """Exact contents (no missing / extra / changed file), own manifest hash, recorded bindings."""
    root = Path(root)
    target = root.joinpath(*unit["path"].split("/"))
    files = _unit_files(comp, unit)
    if target.is_symlink():
        raise VaultError(f"{unit['path']}: is a link")
    if unit["kind"] == "file":
        if not target.is_file():
            raise VaultError(f"{unit['path']}: missing")
        actual = {unit["path"]: target}
    else:
        if not target.is_dir():
            raise VaultError(f"{unit['path']}: missing")
        actual = {}
        for p in sorted(target.rglob("*")):
            if p.is_symlink() or not (p.is_file() or p.is_dir()):
                raise VaultError(f"{unit['path']}: unsafe entry {p.name}")
            if p.is_file():
                actual[p.relative_to(root).as_posix()] = p
    missing, extra = sorted(set(files) - set(actual)), sorted(set(actual) - set(files))
    if missing:
        raise VaultError(f"{unit['path']}: missing files {missing}")
    if extra:
        raise VaultError(f"{unit['path']}: files not in the vault manifest {extra}")
    for rel, p in actual.items():
        if p.stat().st_size != files[rel]["size"] or sha256_file(p) != files[rel]["sha256"]:
            raise VaultError(f"{rel}: content does not match the vault manifest")
    if unit.get("content_addressed") and Path(unit["path"]).stem != files[unit["path"]]["sha256"]:
        raise VaultError(f"{unit['path']}: content-addressed name does not match its SHA-256")
    if unit.get("manifest_sha256"):
        _snapshot_check(target, unit["manifest_sha256"])
    for fname, kv in unit.get("expect", {}).items():
        doc = json.loads((target / fname).read_text(encoding="utf-8"))
        for k, v in kv.items():
            if doc.get(k) != v:
                raise VaultError(f"{unit['path']}/{fname}: {k} = {doc.get(k)!r}, expected {v!r}")


def _bar_dates(p: Path) -> tuple[date, date]:
    import pandas as pd
    idx = pd.read_parquet(p, columns=[]).index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None:
        raise VaultError(f"{p.name}: bar index is not a timezone-aware DatetimeIndex")
    if not len(idx):
        raise VaultError(f"{p.name}: no bars")
    local = idx.tz_convert(MARKET_TZ)
    return local.min().date(), local.max().date()


def check_boundaries(root: Path, comp: dict) -> dict[str, Any]:
    """No bar session and no event ex/event date outside [first_session, last_session] of the component."""
    b = comp.get("boundary")
    if not b:
        return {}
    first, last = date.fromisoformat(b["first_session"]), date.fromisoformat(b["last_session"])
    lo = hi = None
    ev_hi = None
    for f in comp["files"]:
        p = Path(root).joinpath(*f["path"].split("/"))
        if p.suffix == ".parquet":
            a, z = _bar_dates(p)
            if a < first or z > last:
                raise VaultError(f"{f['path']}: bars {a}..{z} outside the permitted boundary {first}..{last}")
            lo, hi = min(lo or a, a), max(hi or z, z)
        elif p.name == "events_normalised.json":
            for e in json.loads(p.read_text(encoding="utf-8"))["events"]:
                for k in BOUNDED_EVENT_FIELDS:
                    if e.get(k):
                        d = date.fromisoformat(str(e[k])[:10])
                        if d > last:
                            raise VaultError(f"{f['path']}: event {e.get('id')} {k} {d} beyond boundary {last}")
                        ev_hi = max(ev_hi or d, d)
    return {"bars_first": lo and lo.isoformat(), "bars_last": hi and hi.isoformat(),
            "events_last": ev_hi and ev_hi.isoformat()}


def verify_tree(root: Path, manifest: dict, components: Iterable[str] | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for name in select_components(manifest, components):
        comp = manifest["components"][name]
        for unit in comp["units"]:
            verify_unit(root, comp, unit)
        report[name] = {"units": len(comp["units"]), "files": len(comp["files"]),
                        "boundary": check_boundaries(root, comp)}
    return report


def select_components(manifest: dict, components: Iterable[str] | None) -> list[str]:
    names = list(components) if components else sorted(manifest["components"])
    unknown = sorted(set(names) - set(manifest["components"]))
    if unknown:
        raise VaultError(f"unknown components {unknown}; available: {sorted(manifest['components'])}")
    return sorted(set(names))


# ---------------------------------------------------------------------------------------------------------- fetch

def gh_fetch(version: str, repo: str = DATA_REPO) -> Fetch:
    """Download one release asset with the GitHub CLI's existing credentials (or GH_TOKEN). Tokens are never read
    or printed here."""
    def fetch(asset: str, out_dir: Path) -> Path:
        if shutil.which("gh") is None:
            raise VaultError("GitHub CLI (gh) not found: install it and run `gh auth login` (see README)")
        r = subprocess.run(["gh", "release", "download", version, "-R", repo, "-p", asset, "-D", str(out_dir)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise VaultError(f"gh release download {version} {asset} failed: {r.stderr.strip()}")
        return Path(out_dir) / asset
    return fetch


def dir_fetch(src: Path) -> Fetch:
    def fetch(asset: str, out_dir: Path) -> Path:
        p = Path(src) / asset
        if not p.is_file():
            raise VaultError(f"asset {asset} not found in {src}")
        shutil.copyfile(p, Path(out_dir) / asset)
        return Path(out_dir) / asset
    return fetch


# ---------------------------------------------------------------------------------------------------------- restore

def _rmtree(p: Path) -> None:
    def onexc(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(p, onexc=onexc)


def restore(pinned: bytes, dest: Path, fetch: Fetch, components: Iterable[str] | None = None) -> dict[str, Any]:
    """Restore the selected components of the pinned vault version into `dest`. Fails closed; idempotent."""
    manifest = parse_manifest(pinned)
    names = select_components(manifest, components)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".vault-restore-", dir=dest.parent))
    try:
        dl, stage = work / "download", work / "stage"
        dl.mkdir()
        stage.mkdir()
        if fetch(MANIFEST_ASSET, dl).read_bytes() != pinned:
            raise VaultError("downloaded vault manifest differs from the pinned manifest committed in this repo")
        archives = {}
        for n in names:
            comp = manifest["components"][n]
            a = fetch(comp["asset"], dl)
            if a.stat().st_size != comp["size"] or sha256_file(a) != comp["sha256"]:
                raise VaultError(f"{comp['asset']}: archive SHA-256/size does not match the pinned manifest")
            archives[n] = a
        for n in names:
            part = stage / n
            part.mkdir()
            safe_extract(archives[n], part, {f["path"]: f for f in manifest["components"][n]["files"]})
            verify_tree(part, manifest, [n])
        # decide everything before moving anything
        actions: list[tuple[str, str, str]] = []
        for n in names:
            comp = manifest["components"][n]
            for unit in comp["units"]:
                target = dest.joinpath(*unit["path"].split("/"))
                if target.exists() or target.is_symlink():
                    try:
                        verify_unit(dest, comp, unit)
                    except VaultError as e:
                        raise VaultError(f"{unit['path']} already exists and does not match the vault; "
                                         f"refusing to overwrite ({e})") from None
                    actions.append((n, unit["path"], "skipped"))
                else:
                    actions.append((n, unit["path"], "restore"))
        for n, upath, act in actions:
            if act == "restore":
                target = dest.joinpath(*upath.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / n / upath, target)
        report = verify_tree(dest, manifest, names)
    finally:
        _rmtree(work)
    return {"version": manifest["version"], "dest": str(dest), "components": report,
            "units": [{"component": n, "path": p, "action": "restored" if a == "restore" else "already present, verified, skipped"}
                      for n, p, a in actions]}
