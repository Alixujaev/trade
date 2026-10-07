"""tests/test_day18d_v203.py: DAY-18D - protocol v2.0.3 per-value precision and committed review records.

Synthetic data only; sockets blocked by tests/conftest.py. Review-record tests use a throwaway git repository in
tmp_path; no record is ever written to the real repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from acquisition.v2 import crosscheck as cc
from acquisition.v2 import review_records as rr
from acquisition.v2 import reviews as rv
from acquisition.v2.contract import PROTOCOL_VERSION
from acquisition.v2.sessions import stage_r_sessions

SESS = stage_r_sessions()[:300]


def series(values):
    return pd.Series(np.asarray(values, dtype=np.float64), index=SESS[:len(values)])


def jittery_raw(n=300, base=40.0):
    return base + 0.37 * np.arange(n) + 0.013 * np.sin(np.arange(n))


# ================================================================ precision (v2.0.3 item 1)

def test_per_value_decimals_and_two_decimal_floor():
    d, delta = cc.per_value_deltas(np.array([23.4, 23.45, 23.456, 23.0, 0.1234]))
    assert d.tolist() == [1, 2, 3, 0, 4]
    assert np.allclose(delta, [0.005, 0.005, 0.0005, 0.005, 0.00005])


def test_mixed_precision_pair_uses_delta_p_and_delta_k_exactly():
    a = np.array([9.99, 9.987])                         # d_p = 2 (delta 0.005), d_k = 3 (delta 0.0005)
    r = np.array([10.0, 10.0 * (a[1] / a[0]) * (1 + 3e-4)])   # ratio move ~3e-4: inside v2.0.3 bound (~5.5e-4),
                                                              # outside a single v2.0.2 delta = 0.0005 (~1e-4)
    dp, dk = 0.005, 0.0005
    rho = (r[1] / a[1]) / (r[0] / a[0])
    lo = rho * (a[1] / (a[1] + dk)) * ((a[0] - dp) / a[0])
    hi = rho * (a[1] / (a[1] - dk)) * ((a[0] + dp) / a[0])
    det, deg = cc.detect_changes(r, a, cc.per_value_deltas(a)[1])
    assert not deg[0] and bool(det[0]) == (not (lo <= 1.0 <= hi))
    det_scalar, _ = cc.detect_changes(r, a, 0.0005)     # v2.0.2-style single max-precision delta
    assert det_scalar[0] and not det[0]                 # the same pair: noise under v2.0.2, inside v2.0.3 bound


def test_mixed_precision_series_rounding_only_v203_vs_v202():
    raw = jittery_raw()
    true_adj = raw * 0.987654321
    adj = np.round(true_adj, 2)
    adj[::50] = np.round(true_adj[::50], 3)             # a minority stored with 3 decimals (AVGO-like)
    v3 = cc.crosscheck_symbol(series(raw), series(adj), [])
    v2 = cc.crosscheck_symbol(series(raw), series(adj), [], precision_model="v2.0.2")
    assert v3["status"] == "OK" and v3["detected_changes"] == 0
    assert v3["precision_histogram"].get("3", 0) >= 5 and v3["precision_model"] == "v2.0.3"
    assert v2["status"] == "BLOCKING" and v2["detected_changes"] > 50


def test_event_still_detected_under_v203_with_mixed_precision():
    raw = jittery_raw()
    factor = np.where(np.arange(300) < 150, 0.99 * 0.98, 0.98)
    adj = np.round(raw * factor, 2)
    adj[::50] = np.round((raw * factor)[::50], 3)
    r = cc.crosscheck_symbol(series(raw), series(adj),
                             [{"id": "d1", "event": "cash_dividend", "ex_date": SESS[150].isoformat()}])
    assert r["status"] == "OK" and r["detected_changes"] == 1 and r["matched_events"] == 1


def test_degenerate_and_non_finite_pairs_are_blocking():
    det, deg = cc.detect_changes(np.array([1.0, 1.0]), np.array([0.004, 0.004]), np.array([0.005, 0.005]))
    assert deg[0] and not det[0]
    raw = jittery_raw(10)
    adj = np.round(raw, 2)
    adj[4] = 0.0
    r = cc.crosscheck_symbol(series(raw), series(adj), [])
    assert r["status"] == "BLOCKING" and len(r["precision_degenerate_pairs"]) == 2
    adj2 = np.round(raw, 2)
    adj2[6] = np.nan
    assert cc.crosscheck_symbol(series(raw), series(adj2), [])["status"] == "BLOCKING"


def test_boundary_one_inside_interval_is_not_a_change():
    det, deg = cc.detect_changes(np.array([10.0, 10.0]), np.array([10.0, 10.0]), np.array([0.0, 0.0]))
    assert not det[0] and not deg[0]                    # rho_min == rho_max == 1 -> inside, not detected


def test_unexplained_and_unconfirmed_under_v203():
    raw = jittery_raw()
    adj = np.round(raw * np.where(np.arange(300) < 200, 0.97, 1.0), 2)
    r = cc.crosscheck_symbol(series(raw), series(adj),
                             [{"id": "e1", "event": "cash_dividend", "ex_date": SESS[100].isoformat()}])
    assert r["unexplained_changes"] == [SESS[200].isoformat()]
    assert r["unexplained_pairs"] == [{"p": SESS[199].isoformat(), "k": SESS[200].isoformat()}]
    assert r["unconfirmed_event_records"][0]["id"] == "e1" and r["status"] == "BLOCKING"


def test_split_tolerance_unchanged_and_determinism():
    raw = np.where(np.arange(300) < 100, 400.0, 100.0) + 0.0001 * np.arange(300)
    ok_adj = np.round(np.where(np.arange(300) < 100, raw / (4.0 * 1.0005), raw), 4)
    bad_adj = np.round(np.where(np.arange(300) < 100, raw / (4.0 * 1.002), raw), 4)
    ev = [{"id": "s", "event": "forward_split", "ex_date": SESS[100].isoformat(), "q": 4.0}]
    a = cc.crosscheck_symbol(series(raw), series(ok_adj), ev)
    assert a["split_magnitude_checks"][0]["ok"] is True
    assert cc.crosscheck_symbol(series(raw), series(bad_adj), ev)["split_magnitude_checks"][0]["ok"] is False
    assert cc.crosscheck_symbol(series(raw), series(ok_adj), ev) == a


# ================================================================ review records (v2.0.3 items 2-5)

SNAP_ID = "stage_r_TEST"
CA_COMPLETE = [{"id": "nv-div", "symbol": "NVDA", "cusip": "67066G104", "rate": 0.04, "ex_date": "2022-03-02",
                "event_date": "2022-03-02", "ca_type": "cash_dividends", "process_date": "2022-04-01"},
               {"id": "crm-m", "acquirer_symbol": "CRM", "acquirer_cusip": "79466L302", "acquiree_symbol": "WORK",
                "effective_date": "2021-07-21", "event_date": "2021-07-21", "ca_type": "stock_and_cash_mergers",
                "process_date": "2021-07-21"}]
IDENTITY = {"aliases": {}, "assignments": [{"id": "nv-div", "entity": "NVDA", "match": "cusip", "role": "subject"}],
            "identity_unverified_records": [{"id": "crm-m", "entity": "CRM", "event_date": "2021-07-21",
                                             "ca_type": "stock_and_cash_mergers", "role": "acquirer", "ticker": "CRM"}],
            "foreign_entity_records": [], "conflicts": [], "unassigned_records": []}
CROSSCHECK = {"per_symbol": {
    "AMZN": {"status": "BLOCKING", "unexplained_changes": ["2016-02-22"],
             "unexplained_pairs": [{"p": "2016-02-19", "k": "2016-02-22"}], "unconfirmed_event_records": [],
             "split_magnitude_checks": [], "precision_degenerate_pairs": [], "uncheckable_events": [],
             "first_session_untestable": []},
    "NVDA": {"status": "BLOCKING", "unexplained_changes": [], "unexplained_pairs": [],
             "unconfirmed_event_records": [{"id": "nv-div", "event": "cash_dividend", "ex_date": "2022-03-02",
                                            "session": "2022-03-02"}],
             "unconfirmed_events": ["2022-03-02"], "split_magnitude_checks": [], "precision_degenerate_pairs": [],
             "uncheckable_events": [], "first_session_untestable": []},
    "CRM": {"status": "OK", "unexplained_changes": [], "unexplained_pairs": [], "unconfirmed_event_records": [],
            "split_magnitude_checks": [], "precision_degenerate_pairs": [], "uncheckable_events": [],
            "first_session_untestable": []}}}


@pytest.fixture()
def env(tmp_path):
    repo = tmp_path / "repo"
    rec_dir = repo / "artifacts" / "reviews" / "stage_r"
    rec_dir.mkdir(parents=True)
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["config", "core.autocrlf", "false"], ["commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    stage_r_root = tmp_path / "stage_r"
    (stage_r_root / SNAP_ID).mkdir(parents=True)
    ev_file = stage_r_root / SNAP_ID / "corporate_actions_complete.json"
    ev_file.write_text(json.dumps({"records": CA_COMPLETE}), encoding="utf-8")
    later = stage_r_root / "stage_r_LATER"
    later.mkdir()
    (later / "corporate_actions_complete.json").write_text("{}", encoding="utf-8")
    manifest_sha = "a" * 64
    return {"repo": repo, "rec_dir": rec_dir, "stage_r_root": stage_r_root, "manifest_sha": manifest_sha,
            "ev_sha": hashlib.sha256(ev_file.read_bytes()).hexdigest(),
            "later_sha": hashlib.sha256((later / "corporate_actions_complete.json").read_bytes()).hexdigest()}


def record(env, record_id="r1", **over):
    rec = {"record_id": record_id, "item_type": "UNEXPLAINED_CHANGE",
           "item_key": {"entity": "AMZN", "session": "2016-02-22"},
           "source_snapshot_manifest_sha256": env["manifest_sha"], "protocol_version": PROTOCOL_VERSION,
           "evidence": [{"type": "same_provider_record", "reference": f"snapshot:{SNAP_ID}/corporate_actions_complete.json",
                         "retrieved_utc": "2026-10-07T00:00:00Z", "sha256": env["ev_sha"]}],
           "decision": "PROVIDER_ADJUSTMENT_ARTIFACT", "reasoning": "documented reasoning", "reviewer": "protocol owner",
           "decided_utc": "2026-10-07T00:00:00Z", "supersedes": None}
    rec.update(over)
    return rec


def put(env, name, content, commit=True):
    p = env["rec_dir"] / f"{name}.json"
    p.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode("utf-8"))
    if commit:
        subprocess.run(["git", "add", "-A"], cwd=env["repo"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", name], cwd=env["repo"], check=True, capture_output=True)
    return p


def load(env, payloads=None):
    ca = payloads or {"complete": list(CA_COMPLETE), "all": list(CA_COMPLETE)}
    return rr.load(env["rec_dir"], repo_root=env["repo"], stage_r_root=env["stage_r_root"], snapshot_id=SNAP_ID,
                   snapshot_manifest_sha256=env["manifest_sha"], open_items=rv.open_items(CROSSCHECK, IDENTITY),
                   ca_payloads=ca, identity=IDENTITY)


def classify(inv):
    norm = {"review_items": [], "blocking": [], "events": []}
    quality = {"blocking": False, "only_in_all": [], "only_in_complete": [], "same_id_content_differs": []}
    return rv.classify(records=CA_COMPLETE, identity=IDENTITY, normalised=norm, quality=quality,
                       crosscheck=CROSSCHECK, validation={"per_series": {}, "raw_vs_all": {}}, ca_counts={},
                       review_inventory=inv)


def test_no_records_everything_stays_blocking(env):
    inv = load(env)
    assert inv["files_found"] == [] and inv["applied"] == {} and inv["invalid"] == []
    out = classify(inv)
    cats = {i["item"]: (i["status"], i["category"]) for i in out["items"]}
    assert cats["unexplained-change AMZN 2016-02-22"] == ("BLOCKING", "UNRESOLVED")
    assert cats["unconfirmed-event NVDA cash_dividend 2022-03-02"] == ("BLOCKING", "UNRESOLVED")
    assert cats["identity-unverified stock_and_cash_mergers CRM<-WORK"] == ("BLOCKING", "IDENTITY_UNVERIFIED")
    assert out["usable_for_research"] is False


def test_valid_committed_record_resolves_only_its_item(env):
    put(env, "r1", record(env))
    inv = load(env)
    assert inv["invalid"] == [] and list(inv["applied"]) == ["UNEXPLAINED_CHANGE|entity=AMZN|session=2016-02-22"]
    assert inv["applied"]["UNEXPLAINED_CHANGE|entity=AMZN|session=2016-02-22"]["blob_sha256"]
    st = {i["item"]: i["status"] for i in classify(inv)["items"]}
    assert st["unexplained-change AMZN 2016-02-22"] == "RESOLVED"
    assert st["unconfirmed-event NVDA cash_dividend 2022-03-02"] == "BLOCKING"


@pytest.mark.parametrize("mutate,reason", [
    (lambda e: {k: v for k, v in record(e).items() if k != "reviewer"}, "missing required fields"),
    (lambda e: record(e, decision="NOISE"), "invalid decision"),
    (lambda e: record(e, item_type="SOMETHING"), "invalid item_type"),
    (lambda e: record(e, source_snapshot_manifest_sha256="b" * 64), "source_snapshot_manifest_sha256"),
    (lambda e: record(e, protocol_version="2.0 R1 + 2.0.1 + 2.0.2"), "protocol_version"),
    (lambda e: record(e, record_id="other"), "record_id does not equal"),
    (lambda e: record(e, evidence=[]), "requires >= 1 evidence"),
    (lambda e: record(e, evidence=[{**record(e)["evidence"][0], "sha256": "XYZ"}]), "64 lowercase hex"),
    (lambda e: record(e, evidence=[{**record(e)["evidence"][0], "sha256": "0" * 64}]), "does not match the referenced"),
    (lambda e: record(e, evidence=[{"type": "regulatory_filing", "reference": "url:https://example.org/x",
                                    "retrieved_utc": "t", "sha256": "0" * 64}]), "admissible only for IDENTITY"),
    (lambda e: record(e, item_key={"entity": "AMZN", "session": "2017-01-03"}), "matches no open item"),
])
def test_invalid_records_are_listed_and_resolve_nothing(env, mutate, reason):
    put(env, "r1", mutate(env))
    inv = load(env)
    assert inv["applied"] == {} and len(inv["invalid"]) == 1
    assert any(reason in r for r in inv["invalid"][0]["reasons"]), inv["invalid"][0]["reasons"]
    out = classify(inv)
    assert any(i["item"] == "invalid review record r1.json" and i["status"] == "BLOCKING" for i in out["items"])
    assert out["usable_for_research"] is False


def test_malformed_json_record(env):
    put(env, "r1", b"{not json")
    inv = load(env)
    assert inv["applied"] == {} and "malformed JSON" in " ".join(inv["invalid"][0]["reasons"])


def test_uncommitted_and_modified_after_commit_records(env):
    put(env, "r1", record(env), commit=False)
    inv = load(env)
    assert inv["applied"] == {} and "not committed" in " ".join(inv["invalid"][0]["reasons"])
    put(env, "r1", record(env))                                   # now committed
    p = env["rec_dir"] / "r1.json"
    p.write_bytes(p.read_bytes() + b" ")                          # worktree differs from committed blob
    inv2 = load(env)
    assert inv2["applied"] == {} and "wrong git hash" in " ".join(inv2["invalid"][0]["reasons"])


def test_mechanical_check_refutes_provider_artifact(env):
    put(env, "r1", record(env))
    extra = {"id": "amzn-x", "symbol": "AMZN", "ex_date": "2016-02-22", "event_date": "2016-02-22", "ca_type": "cash_dividends"}
    inv = load(env, {"complete": CA_COMPLETE + [extra], "all": CA_COMPLETE + [extra]})
    assert inv["applied"] == {} and "refuted" in " ".join(inv["invalid"][0]["reasons"])


def test_supersedes_and_conflicts(env):
    put(env, "r1", record(env, decision="UNRESOLVED", evidence=[]))
    put(env, "r2", record(env, "r2", supersedes="r1"))
    inv = load(env)
    assert inv["superseded"] == ["r1"] and inv["applied"]["UNEXPLAINED_CHANGE|entity=AMZN|session=2016-02-22"]["record_id"] == "r2"
    put(env, "r3", record(env, "r3"))                             # second active record for the same item
    inv2 = load(env)
    assert inv2["applied"] == {} and sum("conflict" in " ".join(x["reasons"]) for x in inv2["invalid"]) == 2


def test_identity_same_entity_with_regulatory_filing_and_event_records(env):
    put(env, "id1", record(env, "id1", item_type="IDENTITY_UNVERIFIED",
                           item_key={"entity": "CRM", "event_date": "2021-07-21", "ca_id": "crm-m"},
                           decision="SAME_ENTITY",
                           evidence=[{"type": "regulatory_filing", "reference": "url:https://www.sec.gov/example",
                                      "retrieved_utc": "2026-10-07T00:00:00Z", "sha256": "1" * 64}]))
    put(env, "ev1", record(env, "ev1", item_type="UNCONFIRMED_EVENT",
                           item_key={"entity": "NVDA", "ex_date": "2022-03-02", "ca_id": "nv-div"}, decision="EVENT_RETAINED"))
    inv = load(env)
    assert inv["invalid"] == [] and len(inv["applied"]) == 2
    st = {i["item"]: i["status"] for i in classify(inv)["items"]}
    assert st["identity-unverified stock_and_cash_mergers CRM<-WORK"] == "RESOLVED"
    assert st["unconfirmed-event NVDA cash_dividend 2022-03-02"] == "RESOLVED"
    assert st["unexplained-change AMZN 2016-02-22"] == "BLOCKING"


def test_event_rejected_requires_later_snapshot_evidence(env):
    key = {"entity": "NVDA", "ex_date": "2022-03-02", "ca_id": "nv-div"}
    put(env, "e1", record(env, "e1", item_type="UNCONFIRMED_EVENT", item_key=key, decision="EVENT_REJECTED"))
    inv = load(env)
    assert inv["applied"] == {} and "different (later) snapshot" in " ".join(inv["invalid"][0]["reasons"])
    put(env, "e2", record(env, "e2", item_type="UNCONFIRMED_EVENT", item_key=key, decision="EVENT_REJECTED",
                          supersedes="e1" if False else None,
                          evidence=[{"type": "same_provider_record", "reference": "snapshot:stage_r_LATER/corporate_actions_complete.json",
                                     "retrieved_utc": "t", "sha256": env["later_sha"]}]))
    inv2 = load(env)
    assert list(inv2["applied"].values())[0]["record_id"] == "e2"
    out = classify(inv2)
    assert "nv-div" in out["events_excluded_by_review"]


def test_v203_classification_without_inventory_argument_is_v202_path():
    norm = {"review_items": [], "blocking": [], "events": []}
    quality = {"blocking": False, "only_in_all": [], "only_in_complete": [], "same_id_content_differs": []}
    out = rv.classify(records=CA_COMPLETE, identity=IDENTITY, normalised=norm, quality=quality, crosscheck=CROSSCHECK,
                      validation={"per_series": {}, "raw_vs_all": {}}, ca_counts={})
    assert "category_counts" not in out and out["usable_for_research"] is False
