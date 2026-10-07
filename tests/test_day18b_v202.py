"""tests/test_day18b_v202.py: DAY-18B - protocol v2.0.2 rules and offline Stage R re-evaluation.

Synthetic data only; sockets are blocked by tests/conftest.py. No real snapshot is read.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import stat

import numpy as np
import pandas as pd
import pytest

from acquisition.v2 import crosscheck as cc
from acquisition.v2 import events as ev
from acquisition.v2 import identity as idn
from acquisition.v2 import reevaluate as re_
from acquisition.v2 import reviews as rv
from acquisition.v2.ca_client import boundary_filter
from acquisition.v2.sessions import stage_r_sessions
from acquisition.v2 import stage_r as sr
from tests.test_day18_stage_r import FakeAlpaca, http

SESS = stage_r_sessions()[:300]


def series(values, start=0):
    return pd.Series(np.asarray(values, dtype=np.float64), index=SESS[start:start + len(values)])


def jittery_raw(n=300, base=100.0):
    return base + 0.37 * np.arange(n) + 0.013 * np.sin(np.arange(n))


# ---------------------------------------------------------------- decimals / precision

def test_decimals_of():
    assert cc.decimals_of(23.45) == 2 and cc.decimals_of(23.4) == 1 and cc.decimals_of(23.0) == 0
    assert cc.decimals_of(0.1234) == 4 and cc.decimals_of(1e-05) == 5 and cc.decimals_of(100.10) == 1
    d, delta = cc.precision_of(pd.Series([1.5, 2.25, 3.125]))
    assert d == 3 and delta == 0.0005


# ---------------------------------------------------------------- 1. precision interval

def test_rounding_alone_detects_nothing_but_old_fixed_rule_would():
    raw = jittery_raw()
    adj = np.round(raw * 0.987654321, 2)
    f = raw / adj
    assert (np.abs(f[1:] / f[:-1] - 1) > 1e-6).sum() > 100          # the retired 1e-6 rule flags noise
    r = cc.crosscheck_symbol(series(raw), series(adj), [], precision_model="v2.0.2")   # DAY-18D: pin v2.0.2 model
    assert r["status"] == "OK" and r["detected_changes"] == 0 and r["d"] == 2 and r["delta"] == 0.005


def test_event_step_detected_and_matched():
    raw = jittery_raw()
    factor = np.where(np.arange(300) < 150, 0.99 * 0.98, 0.98)      # backward adjustment: earlier sessions scaled
    adj = np.round(raw * factor, 2)
    ev_ = [{"id": "d1", "event": "cash_dividend", "ex_date": SESS[150].isoformat()}]
    r = cc.crosscheck_symbol(series(raw), series(adj), ev_)
    assert r["status"] == "OK" and r["detected_changes"] == 1 and r["matched_events"] == 1


def test_price_level_dependence():
    eps = 1e-4                                              # same relative perturbation at two price levels
    low_a = np.array([1.00, 1.00]); low_r = np.array([1.0, 1.0 * (1 + eps)])
    high_a = np.array([1000.00, 1000.00]); high_r = np.array([1000.0, 1000.0 * (1 + eps)])
    det_low, _ = cc.detect_changes(low_r, low_a, 0.005)
    det_high, _ = cc.detect_changes(high_r, high_a, 0.005)
    assert not det_low[0] and det_high[0]


# ---------------------------------------------------------------- 2. degenerate pair

def test_precision_degenerate_pair_is_blocking():
    det, deg = cc.detect_changes(np.array([1.0, 1.0]), np.array([0.004, 0.004]), 0.005)
    assert deg[0] and not det[0]
    raw = jittery_raw(10)
    adj = np.round(raw, 2)
    adj[5] = 0.0
    r = cc.crosscheck_symbol(series(raw), series(adj), [])
    assert r["status"] == "BLOCKING" and len(r["precision_degenerate_pairs"]) == 2


# ---------------------------------------------------------------- 3/4/7. coincidence

def test_change_without_event_is_blocking():
    raw = jittery_raw()
    adj = np.round(raw * np.where(np.arange(300) < 200, 0.97, 1.0), 2)
    r = cc.crosscheck_symbol(series(raw), series(adj), [])
    assert r["status"] == "BLOCKING" and r["unexplained_changes"] == [SESS[200].isoformat()]


def test_event_without_change_is_blocking_no_precision_exemption():
    raw = jittery_raw()
    adj = np.round(raw, 2)
    r = cc.crosscheck_symbol(series(raw), series(adj),
                             [{"id": "tiny", "event": "cash_dividend", "ex_date": SESS[120].isoformat()}])
    assert r["status"] == "BLOCKING" and r["unconfirmed_events"] == [SESS[120].isoformat()]


def test_first_session_untestable_but_later_missing_event_still_blocks():
    raw = jittery_raw()
    adj = np.round(raw, 2)
    first = [{"id": "f", "event": "cash_dividend", "ex_date": SESS[0].isoformat()}]
    ok = cc.crosscheck_symbol(series(raw), series(adj), first)
    assert ok["status"] == "OK" and ok["first_session_untestable"][0]["classification"] == "FIRST_SESSION_UNTESTABLE"
    assert ok["expected_events"] == 0 and ok["unconfirmed_events"] == []
    adj2 = np.round(raw * np.where(np.arange(300) < 250, 0.96, 1.0), 2)
    bad = cc.crosscheck_symbol(series(raw), series(adj2), first)
    assert bad["status"] == "BLOCKING" and bad["unexplained_changes"] == [SESS[250].isoformat()]
    assert len(bad["first_session_untestable"]) == 1


# ---------------------------------------------------------------- 5. split tolerance 0.1 %

@pytest.mark.parametrize("err,ok", [(0.0005, True), (0.002, False)])
def test_split_magnitude_tolerance(err, ok):
    raw = np.where(np.arange(300) < 100, 400.0, 100.0) + 0.0001 * np.arange(300)
    adj = np.round(np.where(np.arange(300) < 100, raw / (4.0 * (1 + err)), raw), 4)
    r = cc.crosscheck_symbol(series(raw), series(adj),
                             [{"id": "s", "event": "forward_split", "ex_date": SESS[100].isoformat(), "q": 4.0}])
    assert r["split_magnitude_checks"][0]["ok"] is ok
    assert (r["status"] == "OK") is ok


# ---------------------------------------------------------------- 8/9/10. identity rule 4a

RECS = [
    ("stock_and_cash_mergers", {"id": "m-crm", "acquirer_symbol": "CRM", "acquirer_cusip": "79466L302",
                                "acquiree_symbol": "WORK", "acquiree_cusip": "83088V102",
                                "effective_date": "2021-07-21", "process_date": "2021-07-21"}),
    ("stock_mergers", {"id": "m-amd", "acquirer_symbol": "AMD", "acquirer_cusip": "007903107",
                       "acquiree_symbol": "XLNX", "acquiree_cusip": "983919101",
                       "effective_date": "2022-02-14", "process_date": "2022-02-14"}),
    ("name_changes", {"id": "n-fb-meta", "old_symbol": "FB", "new_symbol": "META", "old_cusip": "30303M102",
                      "new_cusip": "30303M102", "process_date": "2022-06-09"}),
    ("name_changes", {"id": "n-meta-metv", "old_symbol": "META", "new_symbol": "METV", "old_cusip": "ETFCUSIP9",
                      "new_cusip": "ETFCUSIP9", "process_date": "2022-01-31"}),
]


def _identity():
    kept = boundary_filter(list(RECS))[0]
    return kept, idn.resolve(kept, ["AMD", "CRM", "META"], ["AMD", "CRM", "FB", "META"])


def test_anchorless_records_are_identity_unverified_not_foreign():
    _, res = _identity()
    unv = {u["id"]: u for u in res["identity_unverified_records"]}
    assert set(unv) == {"m-crm", "m-amd"} and all(u["classification"] == "IDENTITY_UNVERIFIED" for u in unv.values())
    assert {f["id"] for f in res["foreign_entity_records"]} == {"n-meta-metv"}     # META anchored -> still foreign
    assert res["anchors"]["CRM"] is None and res["anchors"]["AMD"] is None
    assert res["counts"]["identity_unverified"] == 2 and res["conflicts"] == []


def test_identity_unverified_is_blocking_in_reviews():
    kept, res = _identity()
    norm = ev.normalise(kept, res)
    crosscheck = {"per_symbol": {s: {"status": "OK", "unexplained_changes": []} for s in ("AMD", "CRM", "META")}}
    validation = {"per_series": {}, "raw_vs_all": {}}
    quality = {"blocking": False, "only_in_all": [], "only_in_complete": [], "same_id_content_differs": []}
    out = rv.classify(records=kept, identity=res, normalised=norm, quality=quality, crosscheck=crosscheck,
                      validation=validation, ca_counts={})
    st = {i["item"]: i["status"] for i in out["items"]}
    assert st["identity-unverified stock_and_cash_mergers CRM<-WORK"] == "BLOCKING"
    assert st["identity-unverified stock_mergers AMD<-XLNX"] == "BLOCKING"
    assert st["foreign-entity name_changes META->METV"] == "RESOLVED_EXCLUDED"
    assert st["name_change FB->META"] == "RESOLVED"
    assert out["usable_for_research"] is False


# ---------------------------------------------------------------- 11. SPY same path

def test_spy_uses_the_same_rule_and_blocks_on_missing_event():
    assert "SPY" not in inspect.getsource(cc)
    raw = jittery_raw()
    adj = np.round(raw * np.where(np.arange(300) < 80, 0.995, 1.0), 2)
    idx = [pd.Timestamp(d.isoformat()).tz_localize("America/New_York").tz_convert("UTC") for d in SESS]
    frames = {"SPY": pd.DataFrame({"close": raw}, index=pd.DatetimeIndex(idx))}
    adjf = {"SPY": pd.DataFrame({"close": adj}, index=pd.DatetimeIndex(idx))}
    from acquisition.v2.sessions import session_of_label
    out = cc.crosscheck_all(frames, adjf, [], session_of_label)
    assert out["blocking_symbols"] == ["SPY"] and out["per_symbol"]["SPY"]["unexplained_changes"] == [SESS[80].isoformat()]
    out2 = cc.crosscheck_all(frames, adjf, [{"id": "s", "entity": "SPY", "event": "cash_dividend",
                                             "ex_date": SESS[80].isoformat()}], session_of_label)
    assert out2["per_symbol"]["SPY"]["status"] == "OK"


# ---------------------------------------------------------------- 12. snapshot immutability (offline re-evaluation)

def _snapshot(tmp_path, sid="snap1"):
    res = sr.capture(http=http(FakeAlpaca()), asof="2026-10-07", env={"protocol": {"version": "test"}},
                     root=tmp_path, symbols=["AAPL", "META", "SPY"], snapshot_id=sid)
    snap = Path(res["snapshot_dir"])
    return snap, re_._sha(snap / "manifest.json")


def test_reevaluate_offline_writes_elsewhere_and_leaves_snapshot_unchanged(tmp_path):
    snap, msha = _snapshot(tmp_path)
    before = re_.hash_tree(snap)
    res = re_.reevaluate(snap, expect_manifest_sha256=msha, stage_r_root=tmp_path, protocol="v2.0.2")
    out_dir = Path(res["out_dir"])
    assert out_dir == tmp_path / "reviews" / "v2_0_2__snap1" and not out_dir.is_relative_to(snap)
    assert re_.hash_tree(snap) == before
    e = res["evaluation"]
    assert e["source_snapshot"]["unchanged"] is True and e["source_snapshot"]["manifest_sha256"] == msha
    assert e["offline"] is True and e["final_status"] == "USABLE_FOR_RESEARCH"
    assert e["summary"]["spy"]["status"] == "RESOLVED"
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(
        ["identity.json", "events_normalised.json", "data_quality_comparison.json", "validation.json",
         "crosscheck.json", "reviews.json", "evaluation.json", "manifest.json"])
    with pytest.raises(FileExistsError):
        re_.reevaluate(snap, expect_manifest_sha256=msha, stage_r_root=tmp_path, protocol="v2.0.2")
    assert re_.hash_tree(snap) == before


def test_reevaluate_refuses_wrong_manifest_hash_and_tampered_snapshot(tmp_path):
    snap, msha = _snapshot(tmp_path, "snap2")
    with pytest.raises(re_.ImmutabilityError):
        re_.reevaluate(snap, expect_manifest_sha256="0" * 64, stage_r_root=tmp_path, protocol="v2.0.2")
    victim = snap / "events_normalised.json"
    os.chmod(victim, stat.S_IWRITE | stat.S_IREAD)
    victim.write_text(victim.read_text() + " ", encoding="utf-8")
    with pytest.raises(re_.ImmutabilityError):
        re_.reevaluate(snap, expect_manifest_sha256=msha, stage_r_root=tmp_path, protocol="v2.0.2")
    assert not (tmp_path / "reviews" / "v2_0_2__snap2").exists()
