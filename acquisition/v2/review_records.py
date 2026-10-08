"""acquisition/v2/review_records.py: strict loader/validator for committed Stage R review records (v2.0.3 item 2).

Records live at artifacts/reviews/stage_r/<record_id>.json and are decided and committed by the protocol owner.
This module NEVER creates, edits or decides a record. A record is applied only if ALL checks pass:
- the file is tracked by git and its worktree bytes equal the HEAD blob (uncommitted / modified -> invalid);
- valid JSON with every required field; record_id == file stem;
- source_snapshot_manifest_sha256 == the evaluated snapshot; protocol_version == the v2.0.3 chain;
- item_type / decision from the v2.0.3 enums; item_key matches exactly one open item of that type;
- evidence items well-formed; regulatory filings only for IDENTITY_UNVERIFIED; 'snapshot:' references are
  hash-verified offline ('url:' references are format-checked only and flagged verified_offline=false);
- every decision other than UNRESOLVED carries >= 1 evidence item;
- mechanical evidence checks defined by v2.0.3 items 3-4 pass;
- supersedes chains are honoured; two active records for one item are a conflict (both invalid).
Anything else is INVALID, listed with reasons, and resolves nothing (the item stays BLOCKING).

v2.0.4 (accepted_protocol_versions / moot_keys supplied by the caller): existing v2.0.3 records remain valid; a record
whose only defect is that its item no longer exists under exact evaluation, while that item was open under the v2.0.3
evaluation of the same snapshot (moot_keys), is MOOT - listed separately, not INVALID, resolving nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from acquisition.v2.contract import PROTOCOL_VERSION

ITEM_TYPES = ("UNEXPLAINED_CHANGE", "UNCONFIRMED_EVENT", "IDENTITY_UNVERIFIED")
DECISIONS = {
    "UNEXPLAINED_CHANGE": ("PROVIDER_ADJUSTMENT_ARTIFACT", "MISSING_EVENT_CONFIRMED", "UNRESOLVED"),
    "UNCONFIRMED_EVENT": ("EVENT_RETAINED", "EVENT_REJECTED", "UNRESOLVED"),
    "IDENTITY_UNVERIFIED": ("SAME_ENTITY", "DIFFERENT_ENTITY", "UNRESOLVED"),
}
REQUIRED = ("record_id", "item_type", "item_key", "source_snapshot_manifest_sha256", "protocol_version", "evidence",
            "decision", "reasoning", "reviewer", "decided_utc", "supersedes")
KEY_FIELDS = {"UNEXPLAINED_CHANGE": ("entity", "session"), "UNCONFIRMED_EVENT": ("entity", "ex_date", "ca_id"),
              "IDENTITY_UNVERIFIED": ("entity", "event_date", "ca_id")}
EVIDENCE_TYPES = ("same_provider_record", "regulatory_filing")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def item_key_str(item_type: str, key: dict[str, Any]) -> str:
    return item_type + "|" + "|".join(f"{f}={key.get(f)}" for f in KEY_FIELDS[item_type])


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True)


def _committed_blob(repo: Path, path: Path) -> tuple[bytes | None, str | None]:
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    if _git(repo, "ls-files", "--error-unmatch", rel).returncode != 0:
        return None, "file is not committed (untracked)"
    show = _git(repo, "show", f"HEAD:{rel}")
    if show.returncode != 0:
        return None, "file is not present in HEAD (staged but not committed)"
    if show.stdout != path.read_bytes():
        return None, "worktree content differs from the committed blob (wrong git hash)"
    return show.stdout, None


def _check_evidence(rec: dict[str, Any], stage_r_root: Path) -> list[str]:
    errs: list[str] = []
    ev = rec.get("evidence")
    if not isinstance(ev, list):
        return ["evidence must be a list"]
    if rec.get("decision") != "UNRESOLVED" and not ev:
        errs.append("decision other than UNRESOLVED requires >= 1 evidence item")
    for i, e in enumerate(ev):
        if not isinstance(e, dict):
            errs.append(f"evidence[{i}] is not an object")
            continue
        for f in ("type", "reference", "retrieved_utc", "sha256"):
            if not e.get(f):
                errs.append(f"evidence[{i}] missing {f}")
        t, ref, h = e.get("type"), str(e.get("reference") or ""), str(e.get("sha256") or "")
        if t not in EVIDENCE_TYPES:
            errs.append(f"evidence[{i}] invalid type {t!r}")
        if t == "regulatory_filing" and rec.get("item_type") != "IDENTITY_UNVERIFIED":
            errs.append(f"evidence[{i}] regulatory_filing is admissible only for IDENTITY_UNVERIFIED")
        if h and not _HEX64.match(h):
            errs.append(f"evidence[{i}] sha256 is not 64 lowercase hex characters")
        if t == "regulatory_filing" and not ref.startswith("url:"):
            errs.append(f"evidence[{i}] regulatory_filing reference must start with 'url:'")
        if t == "same_provider_record":
            if not ref.startswith("snapshot:"):
                errs.append(f"evidence[{i}] same_provider_record reference must start with 'snapshot:'")
            elif _HEX64.match(h):
                target = (stage_r_root / ref[len("snapshot:"):].split("#", 1)[0]).resolve()
                if not target.is_relative_to(stage_r_root.resolve()) or not target.is_file():
                    errs.append(f"evidence[{i}] referenced snapshot file does not exist")
                elif hashlib.sha256(target.read_bytes()).hexdigest() != h:
                    errs.append(f"evidence[{i}] sha256 does not match the referenced snapshot file")
    return errs


def _refs_entity(rec: dict[str, Any], entity: str, aliases: dict[str, str]) -> bool:
    for k in ("symbol", "old_symbol", "new_symbol", "acquirer_symbol", "acquiree_symbol", "source_symbol", "target_symbol"):
        t = rec.get(k)
        if t and (t == entity or aliases.get(t) == entity):
            return True
    return False


def _mechanical(rec: dict[str, Any], item: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    d, key = rec["decision"], rec["item_key"]
    if d == "PROVIDER_ADJUSTMENT_ARTIFACT":
        p, k = item["p"], item["k"]
        for q, payload in ctx["ca_payloads"].items():
            for r in payload:
                dates = {str(r.get(x))[:10] for x in ("event_date", "ex_date") if r.get(x)}
                if _refs_entity(r, key["entity"], ctx["aliases"]) and any(p < dt <= k for dt in dates):
                    errs.append(f"PROVIDER_ADJUSTMENT_ARTIFACT refuted: a corporate-action record for {key['entity']} "
                                f"has an event in ({p}, {k}] in data_quality={q}")
                    break
    elif d == "EVENT_RETAINED":
        cid = str(key.get("ca_id"))
        found = {q: [r for r in payload if str(r.get("id")) == cid] for q, payload in ctx["ca_payloads"].items()}
        if any(len(v) != 1 for v in found.values()):
            errs.append("EVENT_RETAINED: record must appear exactly once in both data_quality payloads")
        elif found["complete"][0] != found["all"][0]:
            errs.append("EVENT_RETAINED: record content differs between data_quality payloads")
        if not any(a["id"] == cid and a["entity"] == key["entity"] for a in ctx["assignments"]):
            errs.append("EVENT_RETAINED: record is not identity-resolved to the entity")
        if cid in ctx["duplicate_ids"]:
            errs.append("EVENT_RETAINED: record is part of a duplicate group")
    elif d == "EVENT_REJECTED":
        src = ctx["snapshot_id"]
        ok = [e for e in rec["evidence"] if e.get("type") == "same_provider_record"
              and str(e.get("reference", "")).startswith("snapshot:")
              and not str(e["reference"])[len("snapshot:"):].startswith(src)]
        if not ok:
            errs.append("EVENT_REJECTED requires same-provider evidence from a different (later) snapshot")
    return errs


def load(records_dir: Path, *, repo_root: Path, stage_r_root: Path, snapshot_id: str, snapshot_manifest_sha256: str,
         open_items: dict[str, dict[str, Any]], ca_payloads: dict[str, list[dict[str, Any]]],
         identity: dict[str, Any], duplicate_ids: set[str] | None = None,
         accepted_protocol_versions: tuple[str, ...] = (PROTOCOL_VERSION,),
         moot_keys: set[str] | None = None) -> dict[str, Any]:
    """open_items: item_key_str -> item (with item_type, item_key and, for UNEXPLAINED_CHANGE, p/k)."""
    records_dir = Path(records_dir)
    v204 = moot_keys is not None
    moot_keys = moot_keys or set()
    moot: list[dict[str, Any]] = []
    files = sorted(records_dir.glob("*.json")) if records_dir.is_dir() else []
    ctx = {"ca_payloads": ca_payloads, "aliases": identity.get("aliases", {}),
           "assignments": identity.get("assignments", []), "duplicate_ids": duplicate_ids or set(),
           "snapshot_id": snapshot_id}
    candidates: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for f in files:
        errs: list[str] = []
        blob, gerr = _committed_blob(repo_root, f)
        if gerr:
            errs.append(gerr)
        try:
            rec = json.loads(f.read_bytes())
        except (ValueError, UnicodeDecodeError) as exc:
            invalid.append({"file": f.name, "reasons": errs + [f"malformed JSON: {type(exc).__name__}"]})
            continue
        if not isinstance(rec, dict):
            invalid.append({"file": f.name, "reasons": errs + ["record is not a JSON object"]})
            continue
        missing = [k for k in REQUIRED if k not in rec]
        if missing:
            errs.append(f"missing required fields {missing}")
        if rec.get("record_id") != f.stem:
            errs.append("record_id does not equal the file name")
        if rec.get("source_snapshot_manifest_sha256") != snapshot_manifest_sha256:
            errs.append("source_snapshot_manifest_sha256 does not match the evaluated snapshot")
        if rec.get("protocol_version") not in accepted_protocol_versions:
            errs.append("protocol_version must be " + " or ".join(repr(v) for v in accepted_protocol_versions))
        it = rec.get("item_type")
        if it not in ITEM_TYPES:
            errs.append(f"invalid item_type {it!r}")
        elif rec.get("decision") not in DECISIONS[it]:
            errs.append(f"invalid decision {rec.get('decision')!r} for {it}")
        for f2 in ("reasoning", "reviewer", "decided_utc"):
            if f2 in rec and not str(rec.get(f2) or "").strip():
                errs.append(f"{f2} is empty")
        item = None
        if it in ITEM_TYPES and isinstance(rec.get("item_key"), dict):
            item = open_items.get(item_key_str(it, rec["item_key"]))
            if item is None:
                errs.append("item_key matches no open item of this type")
        elif it in ITEM_TYPES:
            errs.append("item_key must be an object")
        if "evidence" in rec:
            errs += _check_evidence(rec, Path(stage_r_root))
        if not errs and item is not None:
            errs += _mechanical(rec, item, ctx)
        entry = {"file": f.name, "record_id": rec.get("record_id"),
                 "blob_sha256": hashlib.sha256(blob).hexdigest() if blob is not None else None,
                 "url_evidence_verified_offline": False if any(str(e.get("reference", "")).startswith("url:")
                                                               for e in rec.get("evidence") or [] if isinstance(e, dict)) else None}
        if (errs == ["item_key matches no open item of this type"]
                and item_key_str(it, rec["item_key"]) in moot_keys):
            moot.append({**entry, "key": item_key_str(it, rec["item_key"]), "decision": rec.get("decision"),
                         "status": "MOOT", "reason": "item open under v2.0.3 evaluation no longer exists under exact "
                                                     "v2.0.4 evaluation; record remains in history"})
        elif errs:
            invalid.append({**entry, "reasons": errs})
        else:
            candidates.append({**entry, "record": rec, "key": item_key_str(it, rec["item_key"])})

    # supersedes: a superseded record is inactive; a reference to an unknown/invalid record invalidates the superseder
    by_id = {c["record_id"]: c for c in candidates}
    superseded: set[str] = set()
    for c in list(candidates):
        s = c["record"].get("supersedes")
        if s:
            if s not in by_id:
                invalid.append({k: c[k] for k in ("file", "record_id", "blob_sha256")} |
                               {"reasons": [f"supersedes unknown or invalid record {s!r}"]})
                candidates.remove(c)
            else:
                superseded.add(s)
    active = [c for c in candidates if c["record_id"] not in superseded]
    per_key: dict[str, list[dict[str, Any]]] = {}
    for c in active:
        per_key.setdefault(c["key"], []).append(c)
    applied: dict[str, dict[str, Any]] = {}
    for key, cs in per_key.items():
        if len(cs) > 1:
            for c in cs:
                invalid.append({k: c[k] for k in ("file", "record_id", "blob_sha256")} |
                               {"reasons": [f"conflict: {len(cs)} active records for {key}"]})
            continue
        c = cs[0]
        applied[key] = {"record_id": c["record_id"], "decision": c["record"]["decision"], "blob_sha256": c["blob_sha256"],
                        "reviewer": c["record"]["reviewer"], "file": c["file"]}
    out = {"records_dir": str(records_dir), "files_found": [f.name for f in files], "valid_active": len(applied),
           "superseded": sorted(superseded), "invalid": invalid, "applied": applied,
           "agent_created_records": 0}
    if v204:
        out["moot"] = moot
    return out
