"""DAY-26B: the protocol 2.1 draft's calendar is reproducible from the pinned XNYS schedule, and the .md / .json agree.

Calendar facts only (exchange_calendars); no market data, no network.
"""

import json
import re

from acquisition.contract import ROOT_DIR
from scripts import day26b_forward_calendar as cal26b

MD = ROOT_DIR / "artifacts" / "day26b" / "protocol-v2.1-amendment.md"
JS = ROOT_DIR / "artifacts" / "day26b" / "protocol-v2.1-amendment.json"


def _amendment():
    return json.loads(JS.read_text(encoding="utf-8")), MD.read_text(encoding="utf-8")


def test_window_split_and_boundaries():
    c = cal26b.compute()
    d, g = c["fwd_diag"], c["fwd_gate"]
    assert c["total"] == {"count": 63, "first": "2026-10-08", "last": "2027-01-07"}
    assert (d["count"], d["first"], d["last"], d["session_numbers"]) == (21, "2026-10-08", "2026-11-05", [1, 21])
    assert (g["count"], g["first"], g["last"], g["session_numbers"]) == (42, "2026-11-06", "2027-01-07", [22, 63])
    assert len(set(d["sessions"] + g["sessions"])) == 63 and d["sessions"][-1] < g["sessions"][0]
    assert sum(s.startswith("2026") for s in g["sessions"]) == 38 and sum(s.startswith("2027") for s in g["sessions"]) == 4


def test_decisions_holidays_and_capture_times():
    c = cal26b.compute()
    d, g = c["fwd_diag"], c["fwd_gate"]
    assert (d["initial_decision_close"], d["month_end_decision_closes"], d["rebalance_executions"]) == \
        ("2026-10-07", ["2026-10-30"], ["2026-11-02"])
    assert (g["initial_decision_close"], g["month_end_decision_closes"], g["rebalance_executions"]) == \
        ("2026-11-05", ["2026-11-30", "2026-12-31"], ["2026-12-01", "2027-01-04"])
    assert (d["inputs_before_from_stage_f_start"], g["inputs_before_from_stage_f_start"]) == (442, 463)
    assert c["weekday_holidays_in_window"] == ["2026-11-26", "2026-12-25", "2027-01-01"]
    assert c["early_closes_in_window"] == {"2026-11-27": "13:00", "2026-12-24": "13:00"}
    assert d["earliest_stage_f_capture"]["utc"] == "2026-11-05T21:15:00+00:00"
    assert g["earliest_stage_f_capture"]["utc"] == "2027-01-07T21:15:00+00:00"
    assert d["earliest_stage_f_capture"]["utc_offset"] == g["earliest_stage_f_capture"]["utc_offset"] == "-0500"


def test_json_calendar_block_equals_computation():
    js, _ = _amendment()
    assert js["calendar"] == cal26b.compute()
    assert js["status"] == "ADOPTED" and js["effective"] is True and js["protocol_version"] == "2.1"
    assert js["adoption"]["record"] == "artifacts/day26b/protocol-v2.1-adoption.json"
    assert (js["design"]["total_sessions"], js["design"]["diagnostic_sessions"], js["design"]["gate_sessions"]) == (63, 21, 42)


def test_markdown_session_tables_match_calendar():
    c = cal26b.compute()
    _, md = _amendment()
    numbered = {int(n): day for n, day in re.findall(r"\| (\d{1,2}) \| (\d{4}-\d{2}-\d{2})", md)}
    expected = dict(enumerate(c["fwd_diag"]["sessions"] + c["fwd_gate"]["sessions"], start=1))
    assert numbered == expected


def test_markdown_and_json_name_the_same_ids_labels_and_items():
    js, md = _amendment()
    names = [v for seg in js["ids"]["experiments"].values() for v in seg.values()]
    names += [k.split(" (")[0] for seg in js["statuses"].values() for k in seg]
    names += [x["id"] for key in ("conflicts", "preflight", "approvals_required") for x in js[key]]
    names += [x["step"] for x in js["execution_sequence"]]
    names += ["2026-11-05 16:15 America/New_York", "2027-01-07 16:15 America/New_York", "2026-11-05 21:15 UTC",
              "2027-01-07 21:15 UTC", js["invariants"]["strategy_config_sha256"], "DERIVED FROM PRIOR OBSERVATION"]
    missing = sorted({n for n in names if n not in md})
    assert not missing, missing
    assert [x["id"] for x in js["conflicts"]] == [f"C{i}" for i in range(1, 24)]
    assert [x["id"] for x in js["preflight"]] == [f"P{i}" for i in range(1, 14)]
    assert [x["id"] for x in js["approvals_required"]] == [f"A-{i}" for i in range(1, 10)]
    assert len(re.findall(r"^\| C\d+ \|", md, flags=re.M)) == 23
    assert len(re.findall(r"^\| P\d+ \|", md, flags=re.M)) == 13
    assert len(re.findall(r"^\| S\d+ \|", md, flags=re.M)) == len(js["execution_sequence"]) == 13
    assert len(re.findall(r"^\| A-\d \|", md, flags=re.M)) == 9
