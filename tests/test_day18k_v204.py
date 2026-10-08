"""tests/test_day18k_v204.py: DAY-18K - protocol v2.0.4 exact evaluation of the v2.0.3 precision interval.

Synthetic data only (the AMZN/NFLX-style pairs are the values documented in the DAY-18H rationale, used as constructed
fixtures; the snapshot is never read). Sockets blocked by tests/conftest.py. Review-record tests reuse the throwaway
git repository fixture of test_day18d_v203.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from fractions import Fraction
import math
import random

import numpy as np
import pytest

from acquisition.v2 import crosscheck as cc
from acquisition.v2 import review_records as rr
from acquisition.v2 import reviews as rv
from acquisition.v2.contract import PROTOCOL_VERSION, PROTOCOL_VERSION_004
from tests.test_day18d_v203 import CA_COMPLETE, CROSSCHECK, IDENTITY, SESS, SNAP_ID, env, put, record, series  # noqa: F401

AMZN_STYLE = (534.9, 26.74, 559.5, 27.98)        # rp, ap, rk, ak
NFLX_STYLE = (282.65, 28.26, 288.75, 28.88)
FN_STYLE = (1702.485, 63.05, 937.0349999999999, 34.71)   # constructed: exact rho_max just below 1, float64 gives 1.0


def exact_verdict(rp, ap, rk, ak):
    det, deg, inv = cc.detect_changes_exact(np.array([rp, rk]), np.array([ap, ak]))
    return bool(det[0]), bool(deg[0]), bool(inv[0])


def float_verdict(rp, ap, rk, ak):
    a = np.array([ap, ak])
    det, deg = cc.detect_changes(np.array([rp, rk]), a, cc.per_value_deltas(a)[1])
    return bool(det[0]), bool(deg[0])


# ================================================================ exact interval (v2.0.4 §1)

def test_exact_boundary_rho_max_equal_one_is_not_a_detection():
    # constant factor 10 on the unrounded values 10.005 / 11.995: exact rho_max == 1
    rp, ap, rk, ak = 100.05, 10.0, 119.95, 12.0
    e = cc.pair_evidence(rp, ap, rk, ak)
    assert e["exact"]["rho_max"] == "1" and e["exact"]["rho_max_equals_1"] and e["exact"]["contains_1"]
    assert exact_verdict(rp, ap, rk, ak) == (False, False, False)


def test_exact_value_outside_interval_is_a_detection():
    assert exact_verdict(100.0, 10.0, 132.0, 12.0) == (True, False, False)
    assert exact_verdict(100.0, 10.0, 120.0, 12.0) == (False, False, False)      # interior


@pytest.mark.parametrize("pair", [AMZN_STYLE, NFLX_STYLE], ids=["amzn-style", "nflx-style"])
def test_documented_float_false_positives_are_not_exact_detections(pair):
    e = cc.pair_evidence(*pair)
    assert e["exact"]["rho_max"] == "1" and e["exact"]["detected"] is False
    assert e["float64"]["detected"] is True and float(e["float64"]["rho_max"]) < 1.0
    assert e["numerical_classification"] == "NUMERICAL_FALSE_POSITIVE"
    assert exact_verdict(*pair) == (False, False, False) and float_verdict(*pair) == (True, False)


def test_exact_result_is_authoritative_when_float_disagrees():
    for pair, want in ((AMZN_STYLE, False), (FN_STYLE, True)):
        assert exact_verdict(*pair)[0] is want and float_verdict(*pair)[0] is (not want)


def _with_pair(pair, events=()):
    """10 sessions: a flat series (constant factor) whose sessions 4->5 are the given pair, scaled consistently."""
    rp, ap, rk, ak = pair
    raw = np.array([rp] * 5 + [rk] * 5)
    adj = np.array([ap] * 5 + [ak] * 5)
    return cc.crosscheck_symbol(series(raw), series(adj), list(events), precision_model="v2.0.4")


def test_numerical_false_positive_is_recorded_and_non_blocking():
    r = _with_pair(AMZN_STYLE)
    assert r["status"] == "OK" and r["detected_changes"] == 0 and r["unexplained_changes"] == []
    assert r["numerical_false_positives"] == [{"p": SESS[4].isoformat(), "k": SESS[5].isoformat()}]
    assert r["numerical_false_negatives"] == [] and r["float64_diagnostic"]["detected_changes"] == 1
    v3 = cc.crosscheck_symbol(series([AMZN_STYLE[0]] * 5 + [AMZN_STYLE[2]] * 5),
                              series([AMZN_STYLE[1]] * 5 + [AMZN_STYLE[3]] * 5), [])
    assert v3["status"] == "BLOCKING" and v3["unexplained_changes"] == [SESS[5].isoformat()]   # v2.0.3 unchanged


def test_numerical_false_negative_exact_detection_goes_through_coincidence():
    r = _with_pair(FN_STYLE)
    assert r["numerical_false_negatives"] == [{"p": SESS[4].isoformat(), "k": SESS[5].isoformat()}]
    assert r["status"] == "BLOCKING" and r["unexplained_changes"] == [SESS[5].isoformat()]
    ev = [{"id": "d", "event": "cash_dividend", "ex_date": SESS[5].isoformat()}]
    m = _with_pair(FN_STYLE, ev)
    assert m["status"] == "OK" and m["matched_events"] == 1 and m["numerical_false_negatives"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -26.74])
def test_invalid_values_are_exact_evaluation_invalid_and_blocking(bad):
    with pytest.raises(cc.ExactEvaluationInvalid):
        cc.exact_value(bad)
    assert exact_verdict(534.9, bad, 559.5, 27.98) == (False, False, True)
    assert exact_verdict(bad, 26.74, 559.5, 27.98) == (False, False, True)       # raw side too
    raw = np.array([534.9] * 10)
    adj = np.array([26.74] * 10)
    adj[6] = bad
    r = cc.crosscheck_symbol(series(raw), series(adj), [], precision_model="v2.0.4")
    assert r["status"] == "BLOCKING" and r["exact_evaluation_invalid_pairs"] == [SESS[6].isoformat(), SESS[7].isoformat()]
    for x in ("abc", None):
        with pytest.raises(cc.ExactEvaluationInvalid):
            cc.exact_value(x)


def test_degenerate_check_unchanged_and_unreachable_for_valid_values():
    # PRECISION_DEGENERATE (a - delta <= 0) stays authoritative; for any positive value with d displayed decimals
    # a >= 10^-d > 1/(2*10^max(d,2)), so only invalid (non-positive) inputs could reach it
    for d in range(0, 12):
        assert Fraction(1, 10 ** d) - cc.exact_delta(d) > 0
    assert exact_verdict(1.0, 0.001, 1.0, 0.001) == (False, False, False)


# ================================================================ representation (OQ10)

@pytest.mark.parametrize("x", [534.9, 559.5, 282.65, 26.74, 28.88, 0.1234, 105.35, 1e-7, 123456.789, 2.0 ** 60])
def test_raw_and_adjusted_representation_is_deterministic_and_round_trips(x):
    s = cc.shortest_decimal(x)
    assert s == cc.shortest_decimal(np.float64(x)) == cc.shortest_decimal(float(repr(x)))
    assert float(s) == x                                                # round-trips to the persisted DOUBLE
    assert cc.exact_value(x) == Fraction(Decimal(s)) == cc.exact_value(np.float64(x))
    assert s == np.format_float_positional(np.float64(x), unique=True, trim="-") or Decimal(s) == Decimal(
        np.format_float_positional(np.float64(x), unique=True, trim="-"))   # independent Dragon4


def test_exact_value_is_decimal_not_binary_fraction():
    assert cc.exact_value(105.35) == Fraction(10535, 100)
    assert cc.exact_value(105.35) != Fraction(105.35)                    # binary64 value itself is never used


def test_exact_factor_and_delta_and_no_raw_delta():
    rp, ap, rk, ak = AMZN_STYLE
    e = cc.pair_evidence(rp, ap, rk, ak)
    assert Fraction(e["exact"]["f_p"]) == Fraction(53490, 100) / Fraction(2674, 100)
    assert Fraction(e["exact"]["f_k"]) == Fraction(55950, 100) / Fraction(2798, 100)
    assert cc.exact_delta(2) == Fraction(1, 200) and cc.exact_delta(0) == Fraction(1, 200)
    assert cc.exact_delta(3) == Fraction(1, 2000) and cc.exact_delta(4) == Fraction(1, 20000)
    assert e["delta"] == {"p": "1/200", "k": "1/200"} and e["raw_delta"] is None
    # with no raw delta, rho_max is exactly r_k/(a_k - d_k) / (r_p/(a_p + d_p)); a raw delta would move it off 1
    rho, lo, hi = cc.exact_interval(*(Fraction(Decimal(repr(v))) for v in (rp, ap, rk, ak)), Fraction(1, 200),
                                    Fraction(1, 200))
    assert hi == (Fraction(5595, 10) / (Fraction(2798, 100) - Fraction(1, 200))) / (
        Fraction(5349, 10) / (Fraction(2674, 100) + Fraction(1, 200))) == 1


def test_tie_break_nearest_candidate_property():
    """Shortest round-trip with ties to the candidate nearest the binary value: the chosen string is shortest, and no
    other decimal with the same digit count that round-trips is nearer. A genuine equidistant tie was not found by a
    bounded search (DAY-18K), so the nearest property and an independent Dragon4 implementation are checked."""
    rng = random.Random(18)
    values = [rng.uniform(0.01, 5000.0) for _ in range(2000)] + [5e-324, 2.0 ** -1074, 2.0 ** 53 + 2, 1.7976931348623157e308]
    for x in values:
        s = cc.shortest_decimal(x)
        t = Decimal(s).normalize().as_tuple()
        unit = Decimal((0, (1,), t.exponent))
        exact = Decimal(x)                                               # test oracle only (never protocol input)
        for nb in (Decimal(s) - unit, Decimal(s) + unit):
            if nb > 0 and float(nb) == x:
                assert abs(nb - exact) >= abs(Decimal(s) - exact)
        if len(t.digits) > 1:                                            # one digit fewer never round-trips
            for rounding in (ROUND_FLOOR, ROUND_CEILING):
                shorter = Decimal(s).quantize(unit * 10, rounding=rounding)
                assert shorter == Decimal(s) or float(shorter) != x
        assert Decimal(np.format_float_positional(np.float64(x), unique=True, trim="-")) == Decimal(s) or not math.isfinite(x)


# ================================================================ MOOT and review interaction (v2.0.4 §4)

CC_V204 = {"per_symbol": {**CROSSCHECK["per_symbol"],
                          "AMZN": {**CROSSCHECK["per_symbol"]["AMZN"], "status": "OK", "unexplained_changes": [],
                                   "unexplained_pairs": [],
                                   "numerical_false_positives": [{"p": "2016-02-19", "k": "2016-02-22"}]}}}


def load_v204(env, crosscheck=CC_V204, moot_from=CROSSCHECK):
    moot = set(rv.open_items(moot_from, IDENTITY)) - set(rv.open_items(crosscheck, IDENTITY))
    return rr.load(env["rec_dir"], repo_root=env["repo"], stage_r_root=env["stage_r_root"], snapshot_id=SNAP_ID,
                   snapshot_manifest_sha256=env["manifest_sha"], open_items=rv.open_items(crosscheck, IDENTITY),
                   ca_payloads={"complete": list(CA_COMPLETE), "all": list(CA_COMPLETE)}, identity=IDENTITY,
                   accepted_protocol_versions=(PROTOCOL_VERSION, PROTOCOL_VERSION_004), moot_keys=moot)


def classify_v204(inv, crosscheck=CC_V204):
    norm = {"review_items": [], "blocking": [], "events": []}
    quality = {"blocking": False, "only_in_all": [], "only_in_complete": [], "same_id_content_differs": []}
    return rv.classify(records=CA_COMPLETE, identity=IDENTITY, normalised=norm, quality=quality, crosscheck=crosscheck,
                       validation={"per_series": {}, "raw_vs_all": {}}, ca_counts={}, review_inventory=inv,
                       protocol="v2.0.4")


def test_record_for_disappeared_item_is_moot_not_invalid(env):
    put(env, "r1", record(env, decision="UNRESOLVED", evidence=[]))
    inv = load_v204(env)
    assert inv["invalid"] == [] and inv["applied"] == {}
    assert [m["record_id"] for m in inv["moot"]] == ["r1"] and inv["moot"][0]["status"] == "MOOT"
    out = classify_v204(inv)
    st = {i["item"]: (i["status"], i["category"]) for i in out["items"]}
    assert st["moot review record r1.json"] == ("MOOT", "MOOT")
    assert st["numerical-false-positive AMZN 2016-02-22"] == ("NUMERICAL_FALSE_POSITIVE", "NUMERICAL_FALSE_POSITIVE")
    assert not any(i["item"].startswith("unexplained-change AMZN") for i in out["items"])
    assert out["category_counts"]["MOOT"] == 1 and out["review_records"]["moot"] == 1
    assert all(i["status"] not in ("BLOCKING", "HARD_FAIL") for i in out["items"] if i["entity"] == "AMZN")


def test_v203_records_remain_valid_under_v204_and_wrong_keys_stay_invalid(env):
    put(env, "r1", record(env))                                         # v2.0.3 chain string, still-open item
    inv = load_v204(env, crosscheck=CROSSCHECK)
    assert list(inv["applied"]) == ["UNEXPLAINED_CHANGE|entity=AMZN|session=2016-02-22"] and inv["moot"] == []
    put(env, "r2", record(env, record_id="r2", item_key={"entity": "AMZN", "session": "2017-01-03"}))
    inv2 = load_v204(env, crosscheck=CROSSCHECK)
    assert [i["file"] for i in inv2["invalid"]] == ["r2.json"]          # never open -> INVALID, not MOOT


def test_moot_requires_otherwise_valid_record(env):
    put(env, "r1", record(env, decision="UNRESOLVED", evidence=[], source_snapshot_manifest_sha256="b" * 64))
    inv = load_v204(env)
    assert inv["moot"] == [] and len(inv["invalid"]) == 1


def test_exact_evaluation_invalid_is_blocking_in_review_layer(env):
    cc4 = {"per_symbol": {**CC_V204["per_symbol"],
                          "CRM": {**CC_V204["per_symbol"]["CRM"], "exact_evaluation_invalid_pairs": ["2020-01-03"]}}}
    out = classify_v204(load_v204(env, crosscheck=cc4), crosscheck=cc4)
    st = {i["item"]: (i["status"], i["category"]) for i in out["items"]}
    assert st["exact-evaluation-invalid CRM 2020-01-03"] == ("BLOCKING", "EXACT_EVALUATION_INVALID")
    assert "CRM" in out["crosscheck_symbols_blocking"] and out["usable_for_research"] is False


def test_v203_mode_output_unchanged_by_v204_additions(env):
    put(env, "r1", record(env))
    inv = rr.load(env["rec_dir"], repo_root=env["repo"], stage_r_root=env["stage_r_root"], snapshot_id=SNAP_ID,
                  snapshot_manifest_sha256=env["manifest_sha"], open_items=rv.open_items(CROSSCHECK, IDENTITY),
                  ca_payloads={"complete": list(CA_COMPLETE), "all": list(CA_COMPLETE)}, identity=IDENTITY)
    assert "moot" not in inv
    norm = {"review_items": [], "blocking": [], "events": []}
    quality = {"blocking": False, "only_in_all": [], "only_in_complete": [], "same_id_content_differs": []}
    out = rv.classify(records=CA_COMPLETE, identity=IDENTITY, normalised=norm, quality=quality, crosscheck=CROSSCHECK,
                      validation={"per_series": {}, "raw_vs_all": {}}, ca_counts={}, review_inventory=inv)
    assert out["protocol"] == "v2.0.3" and set(out["category_counts"]) == set(rv.CATEGORIES)
    assert "moot" not in out["review_records"]
    rec304 = record(env, protocol_version=PROTOCOL_VERSION_004)        # v2.0.4 chain string is not valid in v2.0.3 mode
    put(env, "r1", rec304)
    inv2 = rr.load(env["rec_dir"], repo_root=env["repo"], stage_r_root=env["stage_r_root"], snapshot_id=SNAP_ID,
                   snapshot_manifest_sha256=env["manifest_sha"], open_items=rv.open_items(CROSSCHECK, IDENTITY),
                   ca_payloads={"complete": list(CA_COMPLETE), "all": list(CA_COMPLETE)}, identity=IDENTITY)
    assert inv2["applied"] == {} and "protocol_version" in " ".join(inv2["invalid"][0]["reasons"])


def test_v204_crosscheck_is_deterministic_and_has_no_symbol_branch():
    raw = np.array([534.9] * 5 + [559.5] * 5)
    adj = np.array([26.74] * 5 + [27.98] * 5)
    a = cc.crosscheck_symbol(series(raw), series(adj), [], precision_model="v2.0.4")
    assert a == cc.crosscheck_symbol(series(raw), series(adj), [], precision_model="v2.0.4")
    src = open(cc.__file__, encoding="utf-8").read()
    body = src[src.index("class ExactEvaluationInvalid"):]
    assert not any(t in body for t in ("AMZN", "NFLX", "2016-02-22", "2018-11-29"))
