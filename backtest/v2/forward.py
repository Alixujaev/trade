"""backtest/v2/forward.py: protocol 2.1 forward-segment guards and the fwd-diag report (DAY-26B). No market data here.

Protocol 2.1 (artifacts/day26b/protocol-v2.1-amendment.md): one 63-session XNYS forward window 2026-10-08 -> 2027-01-07;
fwd-diag = sessions 1-21 (descriptive, never gating), fwd-gate = sessions 22-63 (42 sessions, blind, §13 gate once).

A forward segment may be acquired, validated or evaluated only when BOTH hold:
1. the protocol-2.1 adoption record and the adopted amendment are committed and unchanged (pinned LF SHA-256, P1);
2. the current time is at or after 16:15 America/New_York on the segment's last session (capture_policy, P8).
Every check runs before any data path, client or network object is touched.

Protocol 2.2 (DAY-26D, artifacts/day26d/protocol-v2.2-amendment.md): fwd-diag stays FWD-DIAG-INVALID (protocol-breach),
the old fwd-gate is SUPERSEDED, and a new clean gate fwd-gate2 (2026-10-12 -> 2026-12-09, 42 sessions) is the only
segment whose status is PENDING. Access additionally requires the v2.2 adoption chain, the frozen V2-MOM config SHA,
a calendar-consistent segment without exposed sessions, and no quarantined incident file in any data path.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Callable
from zoneinfo import ZoneInfo

from acquisition.contract import ROOT_DIR
from acquisition.v2.contract import CAPTURE_NOT_BEFORE, EXPOSED_SESSIONS, FORWARD_SEGMENTS, FORWARD_WINDOW

MARKET_TZ = ZoneInfo("America/New_York")
ADOPTION_JSON = "artifacts/day26b/protocol-v2.1-adoption.json"
AMENDMENT_FILES = ("artifacts/day26b/protocol-v2.1-amendment.md", "artifacts/day26b/protocol-v2.1-amendment.json")
INCIDENT_FILES = ("artifacts/day26c/day26c-forward-data-incident.md", "artifacts/day26c/day26c-forward-data-incident.json")
ADOPTION_JSON_22 = "artifacts/day26d/protocol-v2.2-adoption.json"
AMENDMENT_FILES_22 = ("artifacts/day26d/protocol-v2.2-amendment.md", "artifacts/day26d/protocol-v2.2-amendment.json")
V2_MOM_CONFIG_SHA256 = "62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0"
PROTOCOL_JSON = "artifacts/day16/research-protocol-v2.json"
DIAG_CAGR_LABEL = "annualised from 21 sessions — not meaningful evidence"
DIAG_BREACH = "FWD-DIAG-INVALID (protocol-breach)"          # DAY-26C incident: final, never re-evaluated


class ForwardAccessRefused(RuntimeError):
    """A protocol-2.1 forward precondition (adoption commit or earliest evaluation time) is not met."""


def lf_sha256(path: Path) -> str:
    """SHA-256 of a text file with CRLF normalised to LF (core.autocrlf checkouts; as DAY-25B doc_sha256)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def segment_window(seg_id: str) -> tuple[date, date, int]:
    if seg_id not in FORWARD_SEGMENTS:
        raise ValueError(f"not a protocol-2.1 forward segment: {seg_id}")
    return FORWARD_SEGMENTS[seg_id]


def forward_split() -> dict[str, list[date]]:
    """The 63 forward sessions from the pinned XNYS calendar, split 21 + 42 with no overlap and no gap."""
    from acquisition.v2.sessions import stage_f_sessions
    first, last, n = FORWARD_WINDOW
    window = [s for s in stage_f_sessions(last) if s >= first]
    split = {sid: [s for s in window if f <= s <= l] for sid, (f, l, _n) in FORWARD_SEGMENTS.items()}
    d, g = split["fwd-diag"], split["fwd-gate"]
    if not (len(window) == n and window[0] == first and window[-1] == last and d + g == window
            and [len(d), len(g)] == [FORWARD_SEGMENTS["fwd-diag"][2], FORWARD_SEGMENTS["fwd-gate"][2]]):
        raise ForwardAccessRefused("the pinned XNYS calendar does not reproduce the protocol-2.1 forward split")
    return split


def not_before(seg_id: str) -> datetime:
    """Earliest permitted Stage F capture / evaluation time for a segment (16:15 New York on its last session)."""
    return datetime.combine(segment_window(seg_id)[1], CAPTURE_NOT_BEFORE, tzinfo=MARKET_TZ)


def check_time(seg_id: str, now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    nb = not_before(seg_id)
    if now < nb:
        raise ForwardAccessRefused(f"{seg_id} may not be acquired or evaluated before {nb.isoformat()} "
                                   f"(America/New_York); now {now.astimezone(MARKET_TZ).isoformat()}")


def _git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=ROOT_DIR, capture_output=True).returncode == 0


def check_adoption(root: Path = ROOT_DIR, git_ok: Callable[..., bool] | None = None) -> dict:
    """P1: adoption record ADOPTED, pinned SHA-256 of the amendment unchanged, all three files committed and clean."""
    git_ok = git_ok or _git_ok
    path = Path(root) / ADOPTION_JSON
    if not path.is_file():
        raise ForwardAccessRefused(f"protocol-2.1 adoption record missing: {ADOPTION_JSON}")
    rec = json.loads(path.read_text(encoding="utf-8"))
    if rec.get("final_status") != "ADOPTED" or rec.get("protocol_version") != "2.1":
        raise ForwardAccessRefused("protocol 2.1 is not ADOPTED")
    pinned = rec.get("adopted_files_sha256_lf") or {}
    incident_pins = rec.get("incident_records_sha256_lf") or {}
    for p in AMENDMENT_FILES:
        if pinned.get(p) != lf_sha256(Path(root) / p):
            raise ForwardAccessRefused(f"{p} differs from the adopted SHA-256")
    for p in INCIDENT_FILES:                                   # DAY-26C: the incident disclosure is part of the record
        if not (Path(root) / p).is_file() or incident_pins.get(p) != lf_sha256(Path(root) / p):
            raise ForwardAccessRefused(f"{p} is missing or differs from its pinned SHA-256")
    for p in (ADOPTION_JSON, *AMENDMENT_FILES, *INCIDENT_FILES):
        if not git_ok("ls-files", "--error-unmatch", p) or not git_ok("diff", "--quiet", "HEAD", "--", p):
            raise ForwardAccessRefused(f"{p} is not committed unchanged; the adoption takes effect only from its commit")
    return {"adoption_record": ADOPTION_JSON, "adopted_utc": rec.get("decided_utc"), "adopted_files_sha256_lf": pinned,
            "incident_records_sha256_lf": incident_pins}


def segment_status(root: Path = ROOT_DIR) -> dict:
    """Effective protocol status per forward segment: the v2.1 adoption record (DAY-26C incident) overlaid by the
    v2.2 adoption record (DAY-26D). Only a status starting with PENDING permits access."""
    out: dict = {}
    for rel in (ADOPTION_JSON, ADOPTION_JSON_22):
        path = Path(root) / rel
        if path.is_file():
            out.update(json.loads(path.read_text(encoding="utf-8")).get("segment_status", {}))
    return out


def check_adoption_22(root: Path = ROOT_DIR, git_ok: Callable[..., bool] | None = None) -> dict:
    """Protocol 2.2: record ADOPTED, pinned amendment SHA-256 match, all files committed unchanged; plus the 2.1 chain."""
    git_ok = git_ok or _git_ok
    path = Path(root) / ADOPTION_JSON_22
    if not path.is_file():
        raise ForwardAccessRefused(f"protocol-2.2 adoption record missing: {ADOPTION_JSON_22}")
    rec = json.loads(path.read_text(encoding="utf-8"))
    if rec.get("final_status") != "ADOPTED" or rec.get("protocol_version") != "2.2":
        raise ForwardAccessRefused("protocol 2.2 is not ADOPTED")
    pinned = rec.get("adopted_files_sha256_lf") or {}
    for p in AMENDMENT_FILES_22:
        if not (Path(root) / p).is_file() or pinned.get(p) != lf_sha256(Path(root) / p):
            raise ForwardAccessRefused(f"{p} is missing or differs from the adopted SHA-256")
    for p in (ADOPTION_JSON_22, *AMENDMENT_FILES_22):
        if not git_ok("ls-files", "--error-unmatch", p) or not git_ok("diff", "--quiet", "HEAD", "--", p):
            raise ForwardAccessRefused(f"{p} is not committed unchanged; protocol 2.2 takes effect only from its commit")
    chain = check_adoption(root, git_ok)
    return {"adoption_record_22": ADOPTION_JSON_22, "adopted_utc_22": rec.get("decided_utc"),
            "adopted_files_sha256_lf_22": pinned, **chain}


def check_config_sha(root: Path = ROOT_DIR) -> str:
    """The frozen V2-MOM strategy-config SHA-256 (§17 canonical blob of the DAY-16 JSON) must be unchanged."""
    proto = json.loads((Path(root) / PROTOCOL_JSON).read_text(encoding="utf-8"))
    blob = {"family": "V2-MOM", "strategies.V2-MOM": proto["strategies"]["V2-MOM"], "price_series": proto["price_series"],
            "execution": proto["execution"], "costs": proto["costs"], "portfolio": proto["portfolio"]}
    sha = hashlib.sha256(json.dumps(blob, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    if sha != V2_MOM_CONFIG_SHA256:
        raise ForwardAccessRefused(f"V2-MOM strategy-config SHA-256 {sha} != frozen {V2_MOM_CONFIG_SHA256}")
    return sha


def check_segment_calendar(seg_id: str) -> list[date]:
    """The segment's sessions from the pinned calendar: exact count and ends; no exposed (DAY-26C) session in fwd-gate2."""
    from acquisition.v2.sessions import stage_f_sessions
    first, last, n = segment_window(seg_id)
    sample = [s for s in stage_f_sessions(last) if s >= first]
    if len(sample) != n or sample[0] != first or sample[-1] != last:
        raise ForwardAccessRefused(f"{seg_id}: calendar gives {len(sample)} sessions, declared {n}")
    if seg_id == "fwd-gate2" and set(sample) & set(EXPOSED_SESSIONS):
        raise ForwardAccessRefused(f"{seg_id}: an exposed session is inside the declared sample")
    return sample


def check_snapshot_immutable(snap: Path) -> int:
    """Every file of a Stage F snapshot must be read-only (write-once, D4). Returns the number of files checked."""
    import os
    files = [p for p in Path(snap).rglob("*") if p.is_file()]
    if not files:
        raise ForwardAccessRefused(f"snapshot is empty or missing: {snap}")
    writable = [str(p) for p in files if os.access(p, os.W_OK)]
    if writable:
        raise ForwardAccessRefused(f"snapshot files are writable (mutable): {writable[:3]}")
    return len(files)


def check_quarantine(root: Path = ROOT_DIR, search: tuple[str, ...] = ("data",)) -> int:
    """DAY-26C: no file whose SHA-256 is in the incident inventory may exist in any project data path
    (application cache data/cache included). Returns the number of files scanned."""
    inv = Path(root) / INCIDENT_FILES[1]
    if not inv.is_file():
        raise ForwardAccessRefused(f"incident record missing: {INCIDENT_FILES[1]}")
    banned = {f["sha256"] for f in json.loads(inv.read_text(encoding="utf-8"))["inventory"]["files"]}
    scanned = 0
    for d in search:
        base = Path(root) / d
        for p in (base.rglob("*") if base.is_dir() else []):
            if p.is_file() and p.suffix in (".parquet", ".csv", ".feather", ".pkl", ".json"):
                scanned += 1
                if hashlib.sha256(p.read_bytes()).hexdigest() in banned:
                    raise ForwardAccessRefused(f"quarantined incident file found in a data path: {p}")
    return scanned


def check_forward_access(seg_id: str, now: datetime | None = None) -> dict:
    """All forward preconditions; raises ForwardAccessRefused before any data is touched."""
    if seg_id == "fwd-diag" or segment_status().get(seg_id, "").startswith("FWD-DIAG-INVALID"):
        raise ForwardAccessRefused(f"{seg_id} is {DIAG_BREACH} (DAY-26C incident): no fwd-diag acquisition, "
                                   "validation, load or evaluation is permitted")
    status = segment_status().get(seg_id, "")
    if not status.startswith("PENDING"):
        raise ForwardAccessRefused(f"{seg_id} status is {status or 'unrecorded'}; only a PENDING segment may be accessed")
    now = now or datetime.now(timezone.utc)
    check_time(seg_id, now)
    adoption = check_adoption_22() if seg_id == "fwd-gate2" else check_adoption()
    check_config_sha()
    sessions = check_segment_calendar(seg_id)
    if seg_id != "fwd-gate2":
        forward_split()
    check_quarantine()
    return {"segment": seg_id, "status": status, "checked_utc": now.astimezone(timezone.utc).isoformat(),
            "not_before": not_before(seg_id).isoformat(), "sessions": len(sessions),
            "config_sha256": V2_MOM_CONFIG_SHA256, **adoption}


# ------------------------------------------------------------------ fwd-diag descriptive report (amendment §7)

_DATA_CHECKS = ("data_integrity", "complete_dataset")


def diagnostic_report(metrics: dict, gate_a: dict, data_info: dict, costs: tuple[str, ...] = ("0bps", "5bps", "10bps"),
                      fam: str = "V2-MOM") -> dict:
    """Descriptive only: no threshold, no pass/fail, no consequence for the fwd-gate schedule. Since the DAY-26C
    incident the status is always FWD-DIAG-INVALID (protocol-breach); the other checks are listed, never a status."""
    per_cost = {}
    for c in costs:
        m, b1, b2 = metrics[c][fam], metrics[c]["B1"], metrics[c]["B2"]
        per_cost[c] = {
            "total_return": m["total_return"], "b1_total_return": b1["total_return"], "b2_total_return": b2["total_return"],
            "active_total_return_vs_b1": m["total_return"] - b1["total_return"],
            "active_total_return_vs_b2": m["total_return"] - b2["total_return"],
            "max_drawdown": m["max_drawdown"], "b1_max_drawdown": b1["max_drawdown"], "b2_max_drawdown": b2["max_drawdown"],
            "turnover_total": m["turnover_total"], "turnover_per_execution_mean": m["turnover_per_execution_mean"],
            "executions": m["executions"], "mean_lambda": m["mean_lambda"], "min_lambda": m["min_lambda"],
            "total_costs": m["total_costs"],
            "cost_drag_total_return": metrics["0bps"][fam]["total_return"] - m["total_return"],
            "top2_concentration": m["top2_concentration"], "weight_hhi": m["weight_hhi"],
            "symbol_breadth": m["symbol_breadth"], "exposure": m["exposure"],
        }
    data_fail = [k for k in _DATA_CHECKS if not gate_a.get(k, False)]
    method_fail = [k for k, v in gate_a.items() if not v and k not in _DATA_CHECKS]
    status = DIAG_BREACH
    return {"segment": "fwd-diag", "experiment": "V2-MOM-F002-DIAG", "descriptive_only": True, "thresholds": None,
            "consequence_for_fwd_gate": "none (schedule unconditional)", "headline_cost": "5bps",
            "per_cost": per_cost,
            "data_completeness": {"missing_bars_loaded": data_info.get("missing_bars"),
                                  "missing_sessions_in_segment_by_symbol": data_info.get("missing_in_segment_by_symbol"),
                                  "validation": data_info.get("validation")},
            "protocol_compliance": dict(gate_a), "not_reported": "CAGR, Sharpe, Sortino, Calmar, statistical tests",
            "other_failed_checks": {"data": data_fail, "methodological": method_fail},
            "status": status}
