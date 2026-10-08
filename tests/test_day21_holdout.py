"""tests/test_day21_holdout.py: DAY-21 holdout segment configuration of backtest/v2/run.py (synthetic; no data read).

Checks that the holdout runner uses the frozen segment, evaluates only the research-passed families (V2-LRV is never
run, §15.3), uses the holdout outcome vocabulary and the identical research configuration (§15.7).
"""

from __future__ import annotations

from datetime import date
import json

from acquisition.contract import ROOT_DIR
from acquisition.v2.sessions import stage_h_sessions
from backtest.v2 import metrics as mt
from backtest.v2 import run as rn


def test_holdout_segment_is_frozen_and_lrv_not_run():
    h = rn.SEGMENTS["holdout"]
    assert (h["first"], h["last"], h["sessions"], h["inputs_before"]) == (date(2023, 1, 3), date(2026, 6, 2), 856, 503)
    assert h["families"] == ("V2-MOM", "V2-STR") and "V2-LRV" not in h["experiment"]
    assert h["status_prefix"] == "HOLDOUT" and h["experiment"]["V2-MOM"] == "V2-MOM-H001"
    s = stage_h_sessions()
    i0, i1 = s.index(h["first"]), s.index(h["last"])
    assert i0 == 503 and i1 - i0 + 1 == 856 and s[i0 - 1] == date(2022, 12, 30)


def test_research_segment_unchanged():
    r = rn.SEGMENTS["research"]
    assert (r["first"], r["last"], r["sessions"], r["inputs_before"]) == (date(2017, 2, 1), date(2022, 12, 30), 1490, 272)
    assert r["families"] == ("V2-MOM", "V2-STR", "V2-LRV") and r["status_prefix"] == "RESEARCH"


def test_holdout_config_identical_to_research():
    protocol = json.loads((ROOT_DIR / rn.PROTOCOL_FILES[1]).read_text(encoding="utf-8"))
    for f in ("V2-MOM", "V2-STR", "V2-LRV"):
        assert rn.strategy_config_sha(protocol, f) == rn.RESEARCH_CONFIG_SHA256[f]


def test_holm_with_two_families():
    assert mt.holm({"V2-MOM": 0.04, "V2-STR": 0.30}) == {"V2-MOM": 0.08, "V2-STR": 0.30}
