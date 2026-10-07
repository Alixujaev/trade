"""acquisition/v2/reevaluate.py: offline re-evaluation of an existing Stage R snapshot (DAY-18B v2.0.2, DAY-18D v2.0.3).

    python -m acquisition.v2.reevaluate --snapshot <snapshot_dir> --expect-manifest-sha256 <sha256> [--protocol v2.0.3]

v2.0.3 (default): per-value precision (v2.0.3 item 1) and committed review records (items 2-5) loaded read-only
from artifacts/reviews/stage_r/ by acquisition/v2/review_records.py; output <stage_r_root>/reviews/v2_0_3__<id>/.
Every other existing review-output directory is hashed before and after and must stay unchanged.
v2.0.2: reproduces the DAY-18B evaluation semantics; output <stage_r_root>/reviews/v2_0_2__<id>/.

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
from acquisition.v2 import review_records as rr
from acquisition.v2 import reviews as rv
from acquisition.v2 import validation as val
from acquisition.v2.contract import (
    AMENDMENT_002_COMMIT, AMENDMENT_002_FILES, AMENDMENT_003_COMMIT, AMENDMENT_003_FILES, AMENDMENT_COMMIT,
    AMENDMENT_FILES, CA_QUERY_ALIASES, EVENT_DATE_MAX, FORBIDDEN_WRITE_ROOTS, FREEZE_COMMIT, PROTOCOL_FILES,
    PROTOCOL_VERSION, REVIEW_RECORDS_DIR, REVIEW_SCHEMA_VERSION, STAGE_R_ROOT,
)

PROTOCOLS = ("v2.0.3", "v2.0.2")
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


def output_dir_for(snap: Path, stage_r_root: Path = STAGE_R_ROOT, protocol: str = "v2.0.3") -> Path:
    if protocol not in PROTOCOLS:
        raise ValueError(f"protocol must be one of {PROTOCOLS}")
    return Path(stage_r_root) / "reviews" / f"{protocol.replace('.', '_')}__{Path(snap).name}"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True).stdout.strip()


def protocol_chain(protocol: str = "v2.0.3") -> dict[str, Any]:
    commits = {"v2.0 R1": FREEZE_COMMIT, "v2.0.1": AMENDMENT_COMMIT, "v2.0.2": AMENDMENT_002_COMMIT}
    pairs = ([(p, FREEZE_COMMIT) for p in PROTOCOL_FILES] + [(p, AMENDMENT_COMMIT) for p in AMENDMENT_FILES]
             + [(p, AMENDMENT_002_COMMIT) for p in AMENDMENT_002_FILES])
    if protocol == "v2.0.3":
        commits["v2.0.3"] = AMENDMENT_003_COMMIT
        pairs += [(p, AMENDMENT_003_COMMIT) for p in AMENDMENT_003_FILES]
    out: dict[str, Any] = {"version": PROTOCOL_VERSION if protocol == "v2.0.3" else "2.0 R1 + 2.0.1 + 2.0.2",
                           "evaluated_under": protocol, "commits": commits, "files": {}}
    for path, commit in pairs:
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


def _guard_trees(stage_r_root: Path, out_dir: Path) -> dict[str, dict[str, str]]:
    """Hash every existing review-output directory except the one being written (must stay unchanged)."""
    base = Path(stage_r_root) / "reviews"
    if not base.is_dir():
        return {}
    return {d.name: hash_tree(d) for d in sorted(base.iterdir()) if d.is_dir() and d.resolve() != out_dir.resolve()}


def reevaluate(snap: Path, *, expect_manifest_sha256: str, stage_r_root: Path = STAGE_R_ROOT,
               provenance: dict[str, Any] | None = None, protocol: str = "v2.0.3",
               records_dir: Path = REVIEW_RECORDS_DIR, repo_root: Path = ROOT_DIR) -> dict[str, Any]:
    snap = Path(snap)
    pre = verify_snapshot(snap, expect_manifest_sha256)
    out_dir = output_dir_for(snap, stage_r_root, protocol)
    _check_location(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"re-evaluation directory already exists (write-once): {out_dir}")
    if out_dir.resolve().is_relative_to(snap.resolve()):
        raise ImmutabilityError("output directory lies inside the source snapshot")
    guard_before = _guard_trees(stage_r_root, out_dir)

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
    crosscheck = cc.crosscheck_all(frames["raw"], frames["all"], normalised["events"], session_of_label,
                                   precision_model=protocol)
    ca_counts = run.get("ca_counts", {})
    inventory = None
    if protocol == "v2.0.3":
        dup_ids = {i for b in normalised["blocking"] if b.get("kind") == "duplicate_records" for i in b.get("ids", [])}
        inventory = rr.load(records_dir, repo_root=repo_root, stage_r_root=Path(stage_r_root), snapshot_id=snap.name,
                            snapshot_manifest_sha256=pre["manifest_sha256"],
                            open_items=rv.open_items(crosscheck, identity), ca_payloads=ca, identity=identity,
                            duplicate_ids=dup_ids)
    reviews = rv.classify(records=ca["complete"], identity=identity, normalised=normalised, quality=quality,
                          crosscheck=crosscheck, validation=validation, ca_counts=ca_counts,
                          review_inventory=inventory)
    leak = assert_no_leakage(identity, normalised, crosscheck, reviews, quality)

    files: dict[str, str] = {}
    outputs = {"identity.json": identity, "events_normalised.json": normalised,
               "data_quality_comparison.json": quality, "validation.json": validation,
               "crosscheck.json": crosscheck, "reviews.json": reviews}
    if inventory is not None:
        outputs["review_records.json"] = inventory
    for name, obj in outputs.items():
        files[name] = _write_json_once(out_dir / name, obj)

    post = verify_snapshot(snap, expect_manifest_sha256)
    guard_after = _guard_trees(stage_r_root, out_dir)
    unchanged = post["files"] == pre["files"] and guard_after == guard_before
    final = ("INVALID_REVIEW" if not unchanged else "USABLE_FOR_RESEARCH" if reviews["usable_for_research"]
             else "BLOCKED")
    summary = {
        "symbols_evaluated": len(symbols),
        "crosscheck_ok": sorted(s for s, v in crosscheck["per_symbol"].items() if v["status"] == "OK"),
        "crosscheck_blocking": crosscheck["blocking_symbols"],
        "per_symbol": {s: {k: v.get(k) for k in ("status", "precision_model", "precision_histogram", "d", "delta",
                                                  "common_sessions", "pairs_evaluated", "detected_changes",
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
        "review_category_counts": reviews.get("category_counts"),
        "review_records": (None if inventory is None else
                           {"files_found": inventory["files_found"], "applied": len(inventory["applied"]),
                            "invalid": len(inventory["invalid"]), "agent_created_records": 0}),
        "blocking_items": [{k: i.get(k) for k in ("item", "entity", "event_date", "status", "category", "reason")}
                           for i in reviews["items"] if i["status"] in ("BLOCKING", "HARD_FAIL")],
        "spy": {"crosscheck": {k: crosscheck["per_symbol"].get("SPY", {}).get(k) for k in
                               ("status", "d", "detected_changes", "expected_events", "matched_events")},
                "status": ("RESOLVED" if crosscheck["per_symbol"].get("SPY", {}).get("status") == "OK" else "BLOCKING")},
    }
    evaluation = {
        "schema_version": REVIEW_SCHEMA_VERSION, "protocol_chain": protocol_chain(protocol),
        "source_snapshot": {"path": str(snap.relative_to(ROOT_DIR)).replace("\\", "/") if snap.resolve().is_relative_to(ROOT_DIR) else str(snap),
                            "manifest_sha256": pre["manifest_sha256"], "file_count": pre["file_count"],
                            "tree_sha256_before": pre["tree_sha256"], "tree_sha256_after": post["tree_sha256"],
                            "unchanged": unchanged},
        "other_review_outputs_unchanged": guard_after == guard_before,
        "other_review_outputs_checked": sorted(guard_before),
        "evaluated_utc": datetime.now(timezone.utc).isoformat(), "offline": True, "network_calls": 0,
        "provenance": provenance or {}, "leakage_dates_checked": leak, "output_files_sha256": files,
        "summary": summary, "final_status": final, "usable_for_research": final == "USABLE_FOR_RESEARCH",
    }
    files["evaluation.json"] = _write_json_once(out_dir / "evaluation.json", evaluation)
    _write_json_once(out_dir / "manifest.json", {"schema_version": REVIEW_SCHEMA_VERSION, "files_sha256": files,
                                                 "source_manifest_sha256": pre["manifest_sha256"],
                                                 "final_status": final})
    if not unchanged:
        raise ImmutabilityError("source snapshot or an existing review output changed during re-evaluation")
    return {"out_dir": str(out_dir), "evaluation": evaluation}


def _refuse_network(*_a: Any, **_k: Any) -> None:
    raise RuntimeError("network access is forbidden during offline re-evaluation")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline Stage R re-evaluation (v2.0.3 default; v2.0.2 for reproduction)")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--expect-manifest-sha256", required=True)
    ap.add_argument("--protocol", choices=PROTOCOLS, default="v2.0.3")
    a = ap.parse_args(argv)
    socket.socket.connect = _refuse_network            # offline guard for the whole run
    snap = Path(a.snapshot)
    if not snap.is_absolute():
        snap = ROOT_DIR / snap
    res = reevaluate(snap, expect_manifest_sha256=a.expect_manifest_sha256, provenance=code_identity(),
                     protocol=a.protocol)
    e = res["evaluation"]
    print(json.dumps({"out_dir": res["out_dir"], "final_status": e["final_status"],
                      "snapshot_unchanged": e["source_snapshot"]["unchanged"],
                      "file_count": e["source_snapshot"]["file_count"],
                      "crosscheck_ok": e["summary"]["crosscheck_ok"], "crosscheck_blocking": e["summary"]["crosscheck_blocking"],
                      "review_status_counts": e["summary"]["review_status_counts"],
                      "review_category_counts": e["summary"]["review_category_counts"],
                      "review_records": e["summary"]["review_records"],
                      "other_review_outputs_unchanged": e["other_review_outputs_unchanged"],
                      "identity_counts": e["summary"]["identity_counts"], "spy": e["summary"]["spy"],
                      "first_session_untestable": e["summary"]["first_session_untestable"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
