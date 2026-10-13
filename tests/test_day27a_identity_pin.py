"""DRAFT (not in the repo): DAY-27A protocol v2.4 A1 pinned identity alias FB->META. Offline, read-only.

Requires the reviewed diff (day27a-identity-pin.diff): `identity.resolve(..., pinned_aliases)`,
`contract.PINNED_ALIASES`, `stage_h.derive` passing it, `forward.check_adoption_24`. Against today's code these
tests fail at import / signature, by design. Snapshot tests skip when the gitignored Stage R/H snapshots are absent
(CI); they verify the pinned manifest SHA-256 before reading anything else.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from acquisition.contract import ROOT_DIR
from acquisition.v2 import identity as idn
from acquisition.v2 import stage_h as sh
from acquisition.v2.contract import PINNED_ALIASES, ca_query_symbols, stage_r_symbols

STAGE_R = ROOT_DIR / "data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z"
STAGE_H = ROOT_DIR / "data/oos_cache/protocol_v2/stage_h/stage_h_20261008T100604Z"
MANIFEST_SHA = {STAGE_R: "aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd",   # artifacts/day18
                STAGE_H: "eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34"}   # artifacts/day20
BOUNDARY = "2025-01-02"                         # paper HISTORY_START == STAGE_F_FIRST_SESSION
ENTS, QUERIED = stage_r_symbols(), ca_query_symbols()

# The five reused-ticker records seen by the 2026-10-13 paper failure (public corporate-action data).
FB_REUSED = [
    {"ca_type": "cash_dividends", "symbol": "FB", "cusip": "74349Y613", "event_date": d, "ex_date": d,
     "id": i, "rate": rate, "foreign": False, "special": False}
    for i, d, rate in (("1ab26fcd-1a98-478d-9750-3a4588436712", "2025-09-24", 0.144678),
                       ("dd73e539-c6a8-4403-a9b2-5d7563491bfc", "2025-12-24", 0.242008),
                       ("282f080d-4f98-405b-9f57-be0050b810f0", "2026-03-25", 0.163365),
                       ("b179e9be-5718-4836-827b-c17568e546c8", "2026-06-24", 0.336037),
                       ("d88e6089-fcdd-4725-934b-bde4f5af876e", "2026-09-23", 0.0908))]
FB_IDS = {r["id"] for r in FB_REUSED}
# META's own in-window dividends (Stage H snapshot, CUSIP 30303M102) - the anchor that verifies the pin.
META_DIVS = [
    {"ca_type": "cash_dividends", "symbol": "META", "cusip": "30303M102", "event_date": d, "ex_date": d,
     "id": i, "rate": 0.525, "foreign": False, "special": False}
    for i, d in (("bf9d536d-3a19-48ef-841e-f5c5cc336c90", "2025-03-14"),
                 ("338f396d-d4fe-424f-b3fd-0fc4178b210e", "2025-06-16"),
                 ("568747f1-7940-4e9f-950b-a5530669b274", "2025-09-22"))]


def _resolve(records, pins=PINNED_ALIASES):
    return idn.resolve(copy.deepcopy(records), ENTS, QUERIED, pins)


def _canon(o) -> str:
    return json.dumps(o, sort_keys=True, default=str)


def _snapshot_records(snap: Path) -> list[dict]:
    if not snap.is_dir():
        pytest.skip(f"snapshot not present (gitignored): {snap.name}")
    assert hashlib.sha256((snap / "manifest.json").read_bytes()).hexdigest() == MANIFEST_SHA[snap]
    man = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    raw = (snap / "corporate_actions_complete.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == man["files_sha256"]["corporate_actions_complete.json"]
    d = json.loads(raw)
    return d["records"] if isinstance(d, dict) else d


# ------------------------------------------------------------------ the pin itself

def test_pin_is_exactly_the_snapshot_name_change():
    assert PINNED_ALIASES == ({"old_symbol": "FB", "new_symbol": "META", "cusip": "30303M102",
                               "source_id": "ed6f16b1-fc46-443e-8dba-898ed9007a7a", "name_change_date": "2022-06-09"},)


@pytest.mark.parametrize("snap", [STAGE_R, STAGE_H])
def test_pin_is_supported_by_both_pinned_snapshots(snap):
    nc = [r for r in _snapshot_records(snap) if r["id"] == PINNED_ALIASES[0]["source_id"]]
    assert nc == [{"ca_type": "name_changes", "event_date": "2022-06-09", "process_date": "2022-06-09",
                   "id": "ed6f16b1-fc46-443e-8dba-898ed9007a7a", "old_symbol": "FB", "old_cusip": "30303M102",
                   "new_symbol": "META", "new_cusip": "30303M102"}]


# ------------------------------------------------------------------ T1: the five FB records

def test_five_reused_fb_dividends_are_unassigned_without_the_pin():
    out = _resolve(FB_REUSED + META_DIVS, pins=())
    assert {u["id"] for u in out["unassigned_records"]} == FB_IDS        # today's failure, reproduced offline
    assert "pinned_aliases_applied" not in out


def test_five_reused_fb_dividends_are_foreign_with_the_pin():
    out = _resolve(FB_REUSED + META_DIVS)
    assert out["unassigned_records"] == [] and out["conflicts"] == []
    assert {f["id"] for f in out["foreign_entity_records"]} == FB_IDS
    assert all(f["ticker"] == "FB" and f["entity"] == "META" for f in out["foreign_entity_records"])
    assert {a["id"] for a in out["assignments"]} == {r["id"] for r in META_DIVS}     # never assigned to META
    assert out["pinned_aliases_applied"] == list(PINNED_ALIASES)


# ------------------------------------------------------------------ T2-T4: still fail closed

def test_unknown_identity_still_unassigned():
    unknown = {"ca_type": "cash_dividends", "symbol": "ZZZQ", "cusip": "000000000", "event_date": "2026-01-02",
               "id": "synthetic-unknown"}
    out = _resolve(FB_REUSED + META_DIVS + [unknown])
    assert [u["id"] for u in out["unassigned_records"]] == ["synthetic-unknown"]


def test_paper_build_market_data_still_raises_on_unassigned(monkeypatch):
    from paper import data as pdata
    ident = _resolve(FB_REUSED + META_DIVS + [{"ca_type": "cash_dividends", "symbol": "ZZZQ", "cusip": "000000000",
                                                "event_date": "2026-01-02", "id": "synthetic-unknown"}])
    fake = {"validation": {"status_counts": {"OK": 1, "HARD_FAIL": 0, "BLOCKING": 0}}, "identity": ident}
    monkeypatch.setattr(sh, "derive", lambda *_a, **_k: fake)
    monkeypatch.setattr(pdata, "sessions_between", lambda *_a: [__import__("datetime").date(2026, 10, 12)])
    with pytest.raises(pdata.DataFailClosed, match="identity"):
        pdata.build_market_data({"session": __import__("datetime").date(2026, 10, 12), "frames": {}, "ca": {},
                                 "q_syms": [], "ca_counts": {}}, __import__("datetime").date(2026, 10, 12))


def test_pin_unverifiable_without_meta_anchor_leaves_fb_unassigned():
    out = _resolve(FB_REUSED)                                            # no META CUSIP-bearing record in window
    assert out["conflicts"] == [] and "pinned_aliases_applied" not in out
    assert [p["source_id"] for p in out["pinned_aliases_not_applied"]] == [PINNED_ALIASES[0]["source_id"]]
    assert {u["id"] for u in out["unassigned_records"]} == FB_IDS     # still fails closed (paper P5, Stage F)


def test_unverifiable_pin_does_not_block_a_window_without_fb_records():
    out = _resolve([])                                                   # e.g. no corporate actions at all
    assert out["conflicts"] == [] and out["unassigned_records"] == []


def test_pin_with_wrong_target_or_cusip_fails_closed():
    for bad in ({**PINNED_ALIASES[0], "new_symbol": "AAPL"}, {**PINNED_ALIASES[0], "cusip": "74349Y613"}):
        out = _resolve(FB_REUSED + META_DIVS, pins=(bad,))
        assert "pinned_aliases_applied" not in out and len(out["pinned_aliases_not_applied"]) == 1
        assert {u["id"] for u in out["unassigned_records"]} == FB_IDS


def test_pin_contradicted_by_in_window_record_is_a_conflict():
    nc = {"ca_type": "name_changes", "event_date": "2025-05-01", "process_date": "2025-05-01", "id": "synthetic-nc",
          "old_symbol": "FB", "old_cusip": "037833100", "new_symbol": "AAPL", "new_cusip": "037833100"}
    aapl = {"ca_type": "cash_dividends", "symbol": "AAPL", "cusip": "037833100", "event_date": "2025-05-12",
            "id": "synthetic-aapl"}
    out = _resolve(META_DIVS + [nc, aapl])
    assert "pinned_alias_mismatch" in [c["kind"] for c in out["conflicts"]]


def test_fb_with_empty_cusip_is_still_a_conflict():
    blank = {"ca_type": "cash_dividends", "symbol": "FB", "cusip": "", "event_date": "2026-01-02", "id": "synthetic-blank"}
    out = _resolve(FB_REUSED + META_DIVS + [blank])
    assert [c["kind"] for c in out["conflicts"]] == ["b_empty_cusip_with_foreign_entity"]


# ------------------------------------------------------------------ T5: existing assignments unchanged

def test_existing_assignments_unchanged_at_the_2025_boundary():
    """Offline proxy for the live 141: the pinned Stage H records inside the paper / Stage F boundary."""
    rs = [r for r in _snapshot_records(STAGE_H) if r["event_date"] >= BOUNDARY]
    before, after = _resolve(rs, pins=()), _resolve(rs)
    assert len(rs) == 115 and len(before["assignments"]) == 112
    assert _canon(before["assignments"]) == _canon(after["assignments"])
    moved = {u["id"] for u in before["unassigned_records"]}
    assert moved == {f["id"] for f in after["foreign_entity_records"]} and moved <= FB_IDS and len(moved) == 3
    assert after["unassigned_records"] == [] and after["conflicts"] == []


# ------------------------------------------------------------------ T6-T7: Stage H / Stage F consistency

def test_stage_h_recompute_byte_identical():
    stored = json.loads((STAGE_H / "identity.json").read_text(encoding="utf-8"))
    out = _resolve(_snapshot_records(STAGE_H))
    assert _canon(out) == _canon(stored) and "pinned_aliases_applied" not in out   # pin is a no-op in-window


def test_stage_r_pin_is_a_no_op():
    rs = _snapshot_records(STAGE_R)
    assert _canon(_resolve(rs)) == _canon(_resolve(rs, pins=()))     # stored R predates rule 4a; compare code paths


def test_derive_is_the_single_injection_point(monkeypatch):
    """stage_h.derive is called by Stage H validate, Stage F capture/validate and paper.data.build_market_data."""
    seen = []
    real = idn.resolve
    monkeypatch.setattr(idn, "resolve", lambda *a, **k: seen.append(a[3] if len(a) > 3 else k.get("pinned_aliases"))
                        or real(*a, **k))
    with pytest.raises(Exception):                                       # stops after identity on empty frames
        sh.derive({"raw": {}, "all": {}}, {"complete": FB_REUSED + META_DIVS, "all": []}, QUERIED, {}, sessions=[])
    assert seen == [PINNED_ALIASES]


def test_gate2_access_and_paper_runner_require_v24_adoption(tmp_path):
    """Until v2.4 is adopted and committed, fwd-gate2 access and the paper runner are refused."""
    from backtest.v2 import forward as fw
    with pytest.raises(fw.ForwardAccessRefused, match="2.4"):
        fw.check_adoption_24(tmp_path, git_ok=lambda *_a: True)


def test_applied_pin_passes_stage_f_leakage_guard():
    """The pin's historical date must not reach a persisted Stage F payload as event_date/ex_date."""
    rs = [r for r in _snapshot_records(STAGE_H) if r["event_date"] >= BOUNDARY]
    out = _resolve(rs)
    assert out["pinned_aliases_applied"]
    assert sh.assert_no_leakage_h(out, lo=BOUNDARY, hi="2026-12-09") > 0
