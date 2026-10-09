"""tests/test_day26_research_data.py: DAY-26 research-data vault (build / restore / verify), synthetic fixtures only.

No network, no market-data provider, no real snapshot is needed except for the governance test, which reads only the
committed pinned vault manifest and the signed-off constants.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import gzip

import pandas as pd
import pytest

from scripts.research_data import publish, restore as restore_cli, vault
from scripts.research_data.vault import VaultError

ROOT = Path(__file__).parents[1]
VERSION = "synthetic-v1"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write_bars(p: Path, sessions: list[str]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex([pd.Timestamp(s).tz_localize("America/New_York") for s in sessions]).tz_convert("UTC")
    pd.DataFrame({"open": 1.0, "close": 1.0}, index=idx).to_parquet(p)


def _seal(d: Path, **extra) -> str:
    """Write manifest.json listing every other file of d (the real snapshot/review/validation format)."""
    files = {q.relative_to(d).as_posix(): _sha(q.read_bytes()) for q in sorted(d.rglob("*")) if q.is_file()}
    (d / "manifest.json").write_text(json.dumps({"files_sha256": files, **extra}, sort_keys=True), encoding="utf-8")
    return _sha((d / "manifest.json").read_bytes())


def make_src(root: Path, last_bar: str = "2020-01-31", last_ex: str = "2020-01-15") -> dict[str, str]:
    snap = root / "stage_x" / "snap_1"
    _write_bars(snap / "bars_raw" / "AAA.parquet", ["2020-01-02", "2020-01-03", last_bar])
    (snap / "events_normalised.json").write_text(json.dumps({"events": [
        {"id": "e1", "ex_date": last_ex, "event_date": last_ex, "payable_date": "2020-03-01"}]}), encoding="utf-8")
    snap_sha = _seal(snap, snapshot_id="snap_1")
    rev = root / "stage_x" / "reviews" / "rev_1"
    rev.mkdir(parents=True)
    (rev / "reviews.json").write_text("{}", encoding="utf-8")
    rev_sha = _seal(rev, final_status="USABLE_FOR_RESEARCH", source_manifest_sha256=snap_sha)
    body = b"<html>filing</html>"
    ev = root / "evidence" / "sec"
    ev.mkdir(parents=True)
    (ev / f"{_sha(body)}.htm").write_bytes(body)
    return {"snap": snap_sha, "rev": rev_sha}


def make_spec(h: dict[str, str]) -> dict:
    return {
        "stage_x": {"boundary": {"first_session": "2020-01-02", "last_session": "2020-01-31"}, "units": [
            {"path": "stage_x/snap_1", "kind": "dir", "anchor": "x_snapshot", "pinned": h["snap"],
             "expect": {"manifest.json": {"snapshot_id": "snap_1"}}},
            {"path": "stage_x/reviews/rev_1", "kind": "dir", "anchor": "x_review", "pinned": h["rev"],
             "expect": {"manifest.json": {"final_status": "USABLE_FOR_RESEARCH", "source_manifest_sha256": h["snap"]}}},
        ]},
        "evidence": {"asset_prefix": "evidence-sec", "boundary": None,
                     "units": [{"glob": "evidence/sec/*.htm", "kind": "file", "content_addressed": True}]},
    }


@pytest.fixture
def built(tmp_path):
    src = tmp_path / "src"
    h = make_src(src)
    stg = tmp_path / "staging"
    raw = publish.build(src, stg, VERSION, make_spec(h), "deadbeef", "synthetic: no forward data")
    return src, stg, raw


def _writable(root: Path) -> None:
    for p in root.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)


# --------------------------------------------------------------------------------------------------- success paths

def test_successful_restore_and_verify(built, tmp_path):
    src, stg, raw = built
    dest = tmp_path / "dest"
    rep = vault.restore(raw, dest, vault.dir_fetch(stg))
    assert {u["action"] for u in rep["units"]} == {"restored"}
    assert rep["components"]["stage_x"]["boundary"] == {"bars_first": "2020-01-02", "bars_last": "2020-01-31",
                                                       "events_last": "2020-01-15"}
    for f in json.loads(raw)["components"]["stage_x"]["files"]:
        assert (dest / f["path"]).read_bytes() == (src / f["path"]).read_bytes()
    vault.verify_tree(dest, vault.parse_manifest(raw))
    assert not list(tmp_path.glob(".vr-*"))                 # temp area cleaned up


def test_build_is_deterministic(tmp_path):
    src = tmp_path / "src"
    spec = make_spec(make_src(src))
    a = publish.build(src, tmp_path / "a", VERSION, spec, "c", "")
    b = publish.build(src, tmp_path / "b", VERSION, spec, "c", "")
    assert a == b
    for c in json.loads(a)["components"].values():
        assert (tmp_path / "a" / c["asset"]).read_bytes() == (tmp_path / "b" / c["asset"]).read_bytes()


def test_restore_is_idempotent(built, tmp_path):
    _, stg, raw = built
    dest = tmp_path / "dest"
    vault.restore(raw, dest, vault.dir_fetch(stg))
    before = {p: p.stat().st_mtime_ns for p in dest.rglob("*") if p.is_file()}
    rep = vault.restore(raw, dest, vault.dir_fetch(stg))
    assert {u["action"] for u in rep["units"]} == {"already present, verified, skipped"}
    assert {p: p.stat().st_mtime_ns for p in dest.rglob("*") if p.is_file()} == before


def test_restore_selected_component_only(built, tmp_path):
    _, stg, raw = built
    fetched = []
    inner = vault.dir_fetch(stg)
    rep = vault.restore(raw, tmp_path / "dest", lambda a, d: (fetched.append(a), inner(a, d))[1], ["evidence"])
    assert fetched == [vault.MANIFEST_ASSET, f"evidence-sec-{VERSION}.tar.gz"]
    assert not (tmp_path / "dest" / "stage_x").exists()
    assert [u["component"] for u in rep["units"]] == ["evidence"]


def test_cli_restore_and_verify(built, tmp_path):
    _, stg, raw = built
    vdir = tmp_path / "vaults"
    vdir.mkdir()
    (vdir / f"{VERSION}.json").write_bytes(raw)
    args = ["--version", VERSION, "--dest", str(tmp_path / "dest"), "--vaults-dir", str(vdir)]
    assert restore_cli.main(args + ["--from-dir", str(stg)]) == 0
    assert restore_cli.main(args + ["--from-dir", str(stg)]) == 0
    from scripts.research_data import verify as verify_cli
    assert verify_cli.main(args) == 0
    assert restore_cli.main(["--version", "missing-v9", "--vaults-dir", str(vdir), "--from-dir", str(stg)]) == 1


# --------------------------------------------------------------------------------------------------- refusals

def test_refuses_to_overwrite_existing_different_snapshot(built, tmp_path):
    _, stg, raw = built
    dest = tmp_path / "dest"
    vault.restore(raw, dest, vault.dir_fetch(stg))
    _writable(dest)
    target = dest / "stage_x" / "reviews" / "rev_1" / "reviews.json"
    target.write_text('{"tampered": true}', encoding="utf-8")
    for p in (dest / "evidence").rglob("*.htm"):
        p.unlink()                                                      # would be restorable on its own
    with pytest.raises(VaultError, match="refusing to overwrite"):
        vault.restore(raw, dest, vault.dir_fetch(stg))
    assert target.read_text(encoding="utf-8") == '{"tampered": true}'  # untouched
    assert not list((dest / "evidence").rglob("*.htm"))                # nothing moved after the refusal


def test_filesystem_error_while_staging_fails_closed(built, tmp_path, monkeypatch):
    """E.g. a Windows path over 260 characters: a clean VaultError, nothing written, temp area removed."""
    _, stg, raw = built
    def boom(*_a, **_k):
        raise FileNotFoundError(2, "No such file or directory", "x" * 270)
    monkeypatch.setattr(vault, "safe_extract", boom)
    with pytest.raises(VaultError, match="nothing was changed.*LongPathsEnabled"):
        vault.restore(raw, tmp_path / "dest", vault.dir_fetch(stg))
    assert not any((tmp_path / "dest").iterdir())
    assert not list(tmp_path.glob(".vr-*"))


def test_archive_checksum_mismatch(built, tmp_path):
    _, stg, raw = built
    a = stg / f"stage_x-{VERSION}.tar.gz"
    os.chmod(a, stat.S_IWRITE | stat.S_IREAD)
    with open(a, "ab") as f:
        f.write(b"\0")
    with pytest.raises(VaultError, match="archive SHA-256"):
        vault.restore(raw, tmp_path / "dest", vault.dir_fetch(stg))
    assert not (tmp_path / "dest" / "stage_x").exists()


def test_downloaded_manifest_differs_from_pinned(built, tmp_path):
    _, stg, raw = built
    (stg / vault.MANIFEST_ASSET).write_bytes(raw.replace(b"deadbeef", b"deadbeee"))
    with pytest.raises(VaultError, match="differs from the pinned manifest"):
        vault.restore(raw, tmp_path / "dest", vault.dir_fetch(stg))


def test_manifest_file_entry_mismatch(built, tmp_path):
    """A pinned manifest whose file entry disagrees with the (correctly checksummed) archive content."""
    _, stg, raw = built
    m = json.loads(raw)
    f = next(x for x in m["components"]["stage_x"]["files"] if x["path"].endswith("reviews.json"))
    f["sha256"] = "0" * 64
    bad = (json.dumps(m, indent=2, sort_keys=True) + "\n").encode()
    (stg / vault.MANIFEST_ASSET).write_bytes(bad)
    with pytest.raises(VaultError, match="extracted SHA-256"):
        vault.restore(bad, tmp_path / "dest", vault.dir_fetch(stg))


def _tar(entries) -> Path:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz, tarfile.open(fileobj=gz, mode="w",
                                                                          format=tarfile.PAX_FORMAT) as t:
        for name, kind, data in entries:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
            else:
                ti.type = {"sym": tarfile.SYMTYPE, "hard": tarfile.LNKTYPE, "dir": tarfile.DIRTYPE,
                           "fifo": tarfile.FIFOTYPE}[kind]
                ti.linkname = "ok.txt"
                t.addfile(ti)
    return buf.getvalue()


@pytest.mark.parametrize("entries,match", [
    ([("../evil.txt", "file", b"x")], "unsafe archive entry"),
    ([("/abs/evil.txt", "file", b"x")], "unsafe archive entry"),
    ([("C:/evil.txt", "file", b"x")], "unsafe archive entry"),
    ([("a\\..\\evil.txt", "file", b"x")], "unsafe archive entry"),
    ([("a/./ok.txt", "file", b"x")], "unsafe archive entry"),
    ([("link.txt", "sym", b"")], "not a regular file"),
    ([("link.txt", "hard", b"")], "not a regular file"),
    ([("fifo", "fifo", b"")], "not a regular file"),
    ([("ok.txt", "file", b"x"), ("ok.txt", "file", b"x")], "duplicate"),
    ([("ok.txt", "file", b"x"), ("OK.TXT", "file", b"x")], "duplicate"),
    ([("ok.txt", "file", b"x"), ("unlisted.txt", "file", b"y")], "not listed"),
])
def test_unsafe_archive_entries_rejected(tmp_path, entries, match):
    arc = tmp_path / "a.tar.gz"
    arc.write_bytes(_tar(entries))
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(VaultError, match=match):
        vault.safe_extract(arc, dest, {"ok.txt": {"size": 1, "sha256": _sha(b"x")}})
    assert not (tmp_path / "evil.txt").exists() and not Path("/abs/evil.txt").exists()


def test_archive_missing_file(tmp_path):
    arc = tmp_path / "a.tar.gz"
    arc.write_bytes(_tar([("ok.txt", "file", b"x")]))
    (tmp_path / "out").mkdir()
    with pytest.raises(VaultError, match="missing files"):
        vault.safe_extract(arc, tmp_path / "out", {"ok.txt": {"size": 1, "sha256": _sha(b"x")},
                                                   "gone.txt": {"size": 1, "sha256": _sha(b"y")}})


def test_verify_detects_missing_and_extra_files(built, tmp_path):
    _, stg, raw = built
    dest = tmp_path / "dest"
    vault.restore(raw, dest, vault.dir_fetch(stg))
    m = vault.parse_manifest(raw)
    _writable(dest)
    extra = dest / "stage_x" / "snap_1" / "extra.json"
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(VaultError, match="not in the vault manifest"):
        vault.verify_tree(dest, m)
    extra.unlink()
    (dest / "stage_x" / "snap_1" / "events_normalised.json").unlink()
    with pytest.raises(VaultError, match="missing files"):
        vault.verify_tree(dest, m)


@pytest.mark.parametrize("kw,match", [({"last_bar": "2020-02-03"}, "outside the permitted boundary"),
                                      ({"last_ex": "2020-02-03"}, "beyond boundary")])
def test_date_boundary_violation(tmp_path, kw, match):
    src = tmp_path / "src"
    spec = make_spec(make_src(src, **kw))
    with pytest.raises(VaultError, match=match):
        publish.build(src, tmp_path / "stg", VERSION, spec, "c", "")


def test_build_refuses_wrong_signed_off_manifest(tmp_path):
    src = tmp_path / "src"
    h = make_src(src)
    with pytest.raises(VaultError, match="signed-off value"):
        publish.build(src, tmp_path / "stg", VERSION, make_spec({**h, "snap": "0" * 64}), "c", "")


def test_pin_never_overwrites_a_different_manifest(tmp_path):
    publish.pin(b"a", VERSION, tmp_path)
    publish.pin(b"a", VERSION, tmp_path)                                # identical: no-op
    with pytest.raises(VaultError, match="refusing to overwrite"):
        publish.pin(b"b", VERSION, tmp_path)


def test_invalid_version_ids_rejected():
    for v in ("../x", "", "A", "x/y", "x" * 80):
        with pytest.raises(VaultError):
            vault.check_version(v)


# --------------------------------------------------------------------------------------------------- governance

def test_pinned_protocol_v2_manifest_binds_signed_off_anchors():
    from acquisition.v2 import contract as k
    from backtest.v2 import data as d
    m = vault.parse_manifest(vault.load_pinned(publish.VERSION))
    assert m["data_repo"] == "Alixujaev/trade-research-data"
    a = m["anchors"]
    assert a["stage_r_snapshot"]["manifest_sha256"] == d.SNAPSHOT_MANIFEST_SHA256 == \
        "aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd"
    assert a["stage_h_snapshot"]["manifest_sha256"] == d.SNAPSHOT_MANIFEST_SHA256_H == \
        "eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34"
    assert a["stage_r_review_output"]["manifest_sha256"] == d.REVIEW_OUTPUT_MANIFEST_SHA256
    assert a["stage_h_validation"]["manifest_sha256"] == d.VALIDATION_H_MANIFEST_SHA256
    c = m["components"]
    assert c["stage_r"]["boundary"] == {"first_session": k.STAGE_R_FIRST_SESSION.isoformat(),
                                        "last_session": k.STAGE_R_LAST_SESSION.isoformat()}
    assert c["stage_h"]["boundary"] == {"first_session": k.STAGE_H_FIRST_SESSION.isoformat(),
                                        "last_session": k.STAGE_H_LAST_SESSION.isoformat()}
    assert k.STAGE_H_LAST_SESSION.isoformat() == "2026-06-02"           # nothing from the forward window
    for comp in c.values():
        assert all("forward" not in f["path"].lower() for f in comp["files"])
