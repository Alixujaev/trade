"""acquisition/v2/reevaluate.py: DAY-18B offline re-evaluation of an existing Stage R snapshot under v2.0.2.

    python -m acquisition.v2.reevaluate --snapshot <snapshot_dir> --expect-manifest-sha256 <sha256>

- OFFLINE: no HTTP client is imported and socket connections are refused for the whole run.
- The source snapshot is READ ONLY: every file is hashed before and after; the manifest's own SHA-256 must equal
  the expected value and every manifest entry must verify. Any mismatch aborts (before) or fails the run (after).
- Recomputes identity (v2.0.1 C2 + v2.0.2 rule 4a), event normalisation, complete/all comparison, structural
  validation, the raw/all cross-check (v2.0.2 items 1-2) and review classification from the stored bars and
  stored corporate-action records.
- Writes to the deterministic, write-once directory <stage_r_root>/reviews/v2_0_2__<snapshot_id>/.
No signal, return, index or performance value is computed; no price is printed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pandas as pd

from acquisition.contract import ROOT_DIR
from acquisition.snapshot import _write_readonly
from acquisition.v2 import crosscheck as cc
from acquisition.v2 import events as ev
from acquisition.v2 import identity as idn
from acquisition.v2 import reviews as rv
from acquisition.v2 import validation as val
from acquisition.v2.contract import (
    AMENDMENT_002_COMMIT, AMENDMENT_002_FILES, AMENDMENT_COMMIT, AMENDMENT_FILES, CA_QUERY_ALIASES, EVENT_DATE_MAX,
    FORBIDDEN_WRITE_ROOTS, FREEZE_COMMIT, PROTOCOL_FILES, PROTOCOL_VERSION, REVIEW_SCHEMA_VERSION, STAGE_R_ROOT,
)
from acquisition.v2.sessions import session_of_label, stage_r_sessions


class ImmutabilityError(RuntimeError):
    """The source snapshot does not match its manifest or changed during re-evaluation."""


class LeakageError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_tree(snap: Path) -> dict[str, str]:
    return {str(p.relative_to(snap)).replace("\\", "/"): _sha(p) for p in sorted(Path(snap).rglob("*")) if p.is_file()}


def verify_snapshot(snap: Path, expect_manifest_sha256: str) -> dict[str, Any]:
    """Pre-check: manifest SHA-256 == expected; every manifest entry verifies; no file outside manifest+entries."""
    tree = hash_tree(snap)
    problems: list[str] = []
    if tree.get("manifest.json") != expect_manifest_sha256:
        problems.append("manifest.json SHA-256 differs from the expected value")
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    listed = manifest.get("files_sha256", {})
    bad = sorted(k for k, v in listed.items() if tree.get(k) != v)
    extra = sorted(set(tree) - set(listed) - {"manifest.json"})
    if bad:
        problems.append(f"files differing from manifest: {bad}")
    if extra:
        problems.append(f"files not listed in manifest: {extra}")
    if problems:
        raise ImmutabilityError("; ".join(problems))
    return {"file_count": len(tree), "manifest_entries": len(listed), "manifest_sha256": tree["manifest.json"],
            "tree_sha256": hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest(), "files": tree}


def assert_no_leakage(*payloads: Any) -> int:
    seen = 0

    def walk(o: Any) -> None:
        nonlocal seen
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("event_date", "ex_date") and v:
                    seen += 1
                    if str(v)[:10] > EVENT_DATE_MAX:
                        raise LeakageError(f"{k} beyond Stage R boundary in a re-evaluation payload")
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    for p in payloads:
        walk(p)
    return seen


def _check_location(path: Path) -> None:
    rp = Path(path).resolve()
    for root in FORBIDDEN_WRITE_ROOTS:
        if rp.is_relative_to(root.resolve()):
            raise ValueError(f"refusing to write under {root}")


def _write_json_once(path: Path, obj: Any) -> str:
    _check_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, sort_keys=True, default=str).encode("utf-8")
    _write_readonly(path, payload)
    return hashlib.sha256(payload).hexdigest()


def output_dir_for(snap: Path, stage_r_root: Path = STAGE_R_ROOT) -> Path:
    return Path(stage_r_root) / "reviews" / f"v2_0_2__{Path(snap).name}"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout.strip()


def protocol_chain() -> dict[str, Any]:
    out: dict[str, Any] = {"version": PROTOCOL_VERSION, "commits": {"v2.0 R1": FREEZE_COMMIT, "v2.0.1": AMENDMENT_COMMIT,
                                                                   "v2.0.2": AMENDMENT_002_COMMIT}, "files": {}}
    for path, commit in ([(p, FREEZE_COMMIT) for p in PROTOCOL_FILES] + [(p, AMENDMENT_COMMIT) for p in AMENDMENT_FILES]
                         + [(p, AMENDMENT_002_COMMIT) for p in AMENDMENT_002_FILES]):
        blob = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT_DIR, capture_output=True, check=True).stdout
        wt = ROOT_DIR / path
        out["files"][path] = {"commit": commit, "blob_sha256": hashlib.sha256(blob).hexdigest(),
                              "worktree_matches_commit": wt.exists() and _sha(wt) == hashlib.sha256(blob).hexdigest()}
    return out


def code_identity() -> dict[str, Any]:
    files = sorted((ROOT_DIR / "acquisition" / "v2").glob("*.py"))
    return {"git_head": _git("rev-parse", "HEAD"),
            "git_status_porcelain": _git("status", "--porcelain", "--untracked-files=all").splitlines(),
            "acquisition_v2_sha256": {f"acquisition/v2/{p.name}": _sha(p) for p in files}}


def _load(snap: Path) -> tuple[dict[str, dict[str, pd.DataFrame]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    frames: dict[str, dict[str, pd.DataFrame]] = {"raw": {}, "all": {}}
    for adj in ("raw", "all"):
        for p in sorted((snap / f"bars_{adj}").glob("*.parquet")):
            frames[adj][p.stem] = pd.read_parquet(p)
    ca = {q: json.loads((snap / f"corporate_actions_{q}.json").read_text(encoding="utf-8"))["records"]
          for q in ("complete", "all")}
    run = json.loads((snap / "run.json").read_text(encoding="utf-8"))
    return frames, ca, run


def reevaluate(snap: Path, *, expect_manifest_sha256: str, stage_r_root: Path = STAGE_R_ROOT,
               provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    snap = Path(snap)
    pre = verify_snapshot(snap, expect_manifest_sha256)
    out_dir = output_dir_for(snap, stage_r_root)
    _check_location(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"re-evaluation directory already exists (write-once): {out_dir}")
    if out_dir.resolve().is_relative_to(snap.resolve()):
        raise ImmutabilityError("output directory lies inside the source snapshot")

    frames, ca, run = _load(snap)
    symbols = sorted(frames["raw"])
    if symbols != sorted(frames["all"]):
        raise ImmutabilityError("raw/all symbol sets differ in the snapshot")
    queried = run.get("ca_query_symbols") or sorted(set(symbols) | set(CA_QUERY_ALIASES))
    sessions = stage_r_sessions()

    identity = idn.resolve(ca["complete"], symbols, queried)
    normalised = ev.normalise(ca["complete"], identity)
    quality = ev.compare_quality(ca["complete"], ca["all"], {a["id"] for a in identity["assignments"]})
    per_series: dict[str, Any] = {}
    raw_vs_all: dict[str, Any] = {}
    for s in symbols:
        r = val.check_series(frames["raw"][s], sessions)
        a = val.check_series(frames["all"][s], sessions)
        per_series[f"{s}/raw"], per_series[f"{s}/all"] = r, a
        raw_vs_all[s] = val.check_raw_all(r, a)
    validation = {"per_series": per_series, "raw_vs_all": raw_vs_all,
                  "status_counts": {st: sum(1 for v in per_series.values() if v["status"] == st)
                                    for st in ("OK", "BLOCKING", "HARD_FAIL")}}
    crosscheck = cc.crosscheck_all(frames["raw"], frames["all"], normalised["events"], session_of_label)
    ca_counts = run.get("ca_counts", {})
    reviews = rv.classify(records=ca["complete"], identity=identity, normalised=normalised, quality=quality,
                          crosscheck=crosscheck, validation=validation, ca_counts=ca_counts)
    leak = assert_no_leakage(identity, normalised, crosscheck, reviews, quality)

    files: dict[str, str] = {}
    for name, obj in {"identity.json": identity, "events_normalised.json": normalised,
                      "data_quality_comparison.json": quality, "validation.json": validation,
                      "crosscheck.json": crosscheck, "reviews.json": reviews}.items():
        files[name] = _write_json_once(out_dir / name, obj)

    post = verify_snapshot(snap, expect_manifest_sha256)
    unchanged = post["files"] == pre["files"]
    final = ("INVALID_REVIEW" if not unchanged else "USABLE_FOR_RESEARCH" if reviews["usable_for_research"]
             else "BLOCKED")
    summary = {
        "symbols_evaluated": len(symbols),
        "crosscheck_ok": sorted(s for s, v in crosscheck["per_symbol"].items() if v["status"] == "OK"),
        "crosscheck_blocking": crosscheck["blocking_symbols"],
        "per_symbol": {s: {k: v.get(k) for k in ("status", "d", "delta", "common_sessions", "detected_changes",
                                                  "expected_events", "matched_events")}
                       | {"unexplained_changes": len(v.get("unexplained_changes", [])),
                          "unconfirmed_events": len(v.get("unconfirmed_events", [])),
                          "split_checks": [c["ok"] for c in v.get("split_magnitude_checks", [])],
                          "precision_degenerate_pairs": len(v.get("precision_degenerate_pairs", [])),
                          "first_session_untestable": len(v.get("first_session_untestable", [])),
                          "uncheckable_events": len(v.get("uncheckable_events", []))}
                       for s, v in crosscheck["per_symbol"].items()},
        "first_session_untestable": crosscheck["first_session_untestable"],
        "identity_counts": identity["counts"],
        "review_status_counts": reviews["status_counts"],
        "blocking_items": [{k: i.get(k) for k in ("item", "entity", "event_date", "status", "reason")}
                           for i in reviews["items"] if i["status"] in ("BLOCKING", "HARD_FAIL")],
        "spy": {"crosscheck": {k: crosscheck["per_symbol"].get("SPY", {}).get(k) for k in
                               ("status", "d", "detected_changes", "expected_events", "matched_events")},
                "status": ("RESOLVED" if crosscheck["per_symbol"].get("SPY", {}).get("status") == "OK" else "BLOCKING")},
    }
    evaluation = {
        "schema_version": REVIEW_SCHEMA_VERSION, "protocol_chain": protocol_chain(),
        "source_snapshot": {"path": str(snap.relative_to(ROOT_DIR)).replace("\\", "/") if snap.resolve().is_relative_to(ROOT_DIR) else str(snap),
                            "manifest_sha256": pre["manifest_sha256"], "file_count": pre["file_count"],
                            "tree_sha256_before": pre["tree_sha256"], "tree_sha256_after": post["tree_sha256"],
                            "unchanged": unchanged},
        "evaluated_utc": datetime.now(timezone.utc).isoformat(), "offline": True, "network_calls": 0,
        "provenance": provenance or {}, "leakage_dates_checked": leak, "output_files_sha256": files,
        "summary": summary, "final_status": final, "usable_for_research": final == "USABLE_FOR_RESEARCH",
    }
    files["evaluation.json"] = _write_json_once(out_dir / "evaluation.json", evaluation)
    _write_json_once(out_dir / "manifest.json", {"schema_version": REVIEW_SCHEMA_VERSION, "files_sha256": files,
                                                 "source_manifest_sha256": pre["manifest_sha256"],
                                                 "final_status": final})
    if not unchanged:
        raise ImmutabilityError("source snapshot changed during re-evaluation")
    return {"out_dir": str(out_dir), "evaluation": evaluation}


def _refuse_network(*_a: Any, **_k: Any) -> None:
    raise RuntimeError("network access is forbidden during offline re-evaluation")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DAY-18B offline Stage R re-evaluation under v2.0.2")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--expect-manifest-sha256", required=True)
    a = ap.parse_args(argv)
    socket.socket.connect = _refuse_network            # offline guard for the whole run
    snap = Path(a.snapshot)
    if not snap.is_absolute():
        snap = ROOT_DIR / snap
    res = reevaluate(snap, expect_manifest_sha256=a.expect_manifest_sha256, provenance=code_identity())
    e = res["evaluation"]
    print(json.dumps({"out_dir": res["out_dir"], "final_status": e["final_status"],
                      "snapshot_unchanged": e["source_snapshot"]["unchanged"],
                      "file_count": e["source_snapshot"]["file_count"],
                      "crosscheck_ok": e["summary"]["crosscheck_ok"], "crosscheck_blocking": e["summary"]["crosscheck_blocking"],
                      "review_status_counts": e["summary"]["review_status_counts"],
                      "identity_counts": e["summary"]["identity_counts"], "spy": e["summary"]["spy"],
                      "first_session_untestable": e["summary"]["first_session_untestable"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
