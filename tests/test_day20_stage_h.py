"""tests/test_day20_stage_h.py: DAY-20 Stage H acquisition and data validation (synthetic; no network).

Provider calls go through a fake `get` (tests/conftest.py blocks sockets). Prices are synthetic constants; no real
market data is read. Checks the frozen Stage H range, the DAY-20 decisions (CA windows mirroring v2.0.1 C1,
asof 2026-10-07, no assets call) and that out-of-range corporate-action records never reach disk.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from acquisition.v2 import stage_h as sh
from acquisition.v2.bars_client import DailyBarsClient
from acquisition.v2.ca_client import CorporateActionsClient, boundary_filter
from acquisition.v2.contract import (
    CA_WINDOWS, CA_WINDOWS_H, EVENT_DATE_MAX_H, EVENT_DATE_MIN_H, STAGE_H_ASOF, STAGE_H_FIRST_SESSION,
    STAGE_H_LAST_SESSION,
)
from acquisition.v2.http import RequestGuardError
from acquisition.v2.sessions import label_for, stage_h_sessions, stage_r_sessions
from tests.test_day18_stage_r import META_C, ETF_C, SPY_C, FakeAlpaca, Resp, http

H = stage_h_sessions()
POST_ID, PRE_ID = "POST-SENTINEL-9c1e", "PRE-SENTINEL-4b2d"
SPY_DIV = ("2026-05-29", 1.0)                   # ex-date inside Stage H, processed in Q2 -> kept


def _bars(sym, adjustment):
    out = []
    for d in H:
        c = 200.0
        if adjustment == "all" and sym == "SPY" and d.isoformat() < SPY_DIV[0]:
            c *= 1.0 - SPY_DIV[1] / 200.0           # backward dividend adjustment -> one factor change
        out.append({"t": label_for(d).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": c, "h": c, "l": c, "c": c, "v": 1000,
                    "n": 10, "vw": c})
    return out


CA_H = [
    ("cash_dividends", {"id": "d-spy-h", "symbol": "SPY", "cusip": SPY_C, "rate": SPY_DIV[1], "special": False,
                        "foreign": False, "ex_date": SPY_DIV[0], "record_date": "2026-06-01",
                        "payable_date": "2026-06-20", "process_date": "2026-06-20"}),
    ("cash_dividends", {"id": POST_ID, "symbol": "SPY", "cusip": SPY_C, "rate": 7.77, "special": False,
                        "foreign": False, "ex_date": "2026-06-15", "record_date": "2026-06-16",
                        "payable_date": "2026-07-01", "process_date": "2026-07-01"}),
    ("cash_dividends", {"id": PRE_ID, "symbol": "SPY", "cusip": SPY_C, "rate": 3.33, "special": False,
                        "foreign": False, "ex_date": "2020-12-30", "record_date": "2020-12-31",
                        "payable_date": "2021-01-02", "process_date": "2021-01-02"}),
    ("name_changes", {"id": "n-fb-meta", "old_symbol": "FB", "new_symbol": "META", "old_cusip": META_C,
                      "new_cusip": META_C, "process_date": "2022-06-09"}),
    ("name_changes", {"id": "n-meta-metv", "old_symbol": "META", "new_symbol": "METV", "old_cusip": ETF_C,
                      "new_cusip": ETF_C, "process_date": "2022-06-01"}),
]


class FakeH(FakeAlpaca):
    def __call__(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/v2/stocks/bars"):
            params = dict(params or {})
            self.calls.append((url, params))
            sym = params["symbols"]
            rows = [b for b in _bars(sym, params["adjustment"]) if params["start"] <= b["t"] <= params["end"]]
            return Resp(body={"bars": {sym: rows}, "next_page_token": None})
        return super().__call__(url, params, headers, timeout)


def test_stage_h_sessions_frozen_range():
    hold = [s for s in H if s >= date(2023, 1, 3)]
    assert len(H) == 1359 and H[0] == date(2021, 1, 4) and H[-1] == date(2026, 6, 2)
    assert len(hold) == 856 and hold[0] == date(2023, 1, 3) and len(H) - len(hold) == 503
    assert max(stage_r_sessions()) < hold[0]                 # no research/holdout overlap


def test_decision_constants():
    assert CA_WINDOWS_H == {"Q1": ("2021-01-01", "2026-06-02"), "Q2": ("2026-06-03", "2026-08-31")}
    assert (EVENT_DATE_MIN_H, EVENT_DATE_MAX_H, STAGE_H_ASOF) == ("2021-01-04", "2026-06-02", "2026-10-07")
    assert all(e < sh.FORWARD_FIRST for _, e in CA_WINDOWS_H.values())
    assert CA_WINDOWS == {"Q1": ("2016-01-01", "2022-12-30"), "Q2": ("2022-12-31", "2023-03-31")}   # Stage R unchanged


def test_bars_guard_stage_h_bounds_and_stage_r_default():
    fake = FakeH()
    c = DailyBarsClient(http(fake), asof=STAGE_H_ASOF, first_session=STAGE_H_FIRST_SESSION,
                        last_session=STAGE_H_LAST_SESSION)
    with pytest.raises(RequestGuardError):
        c.fetch("SPY", "raw", end=label_for(date(2026, 6, 3)))
    with pytest.raises(RequestGuardError):
        c.fetch("SPY", "raw", start=label_for(date(2020, 12, 31)))
    assert fake.calls == []                                  # guard fires before any request
    r = DailyBarsClient(http(fake), asof="2026-10-07")
    assert r.max_label == label_for(date(2022, 12, 30))


def test_boundary_filter_stage_h_counts_only():
    kept, counts = boundary_filter(CA_H, EVENT_DATE_MIN_H, EVENT_DATE_MAX_H, "stage_h")
    ids = {r["id"] for r in kept}
    assert POST_ID not in ids and PRE_ID not in ids and "d-spy-h" in ids
    assert counts["discarded_after_stage_h"] == 1 and counts["discarded_before_stage_h"] == 1


def test_ca_window_guard_uses_frozen_h_windows():
    cl = CorporateActionsClient(http(FakeH(ca_records=CA_H)))
    with pytest.raises(RequestGuardError):
        cl.fetch_window("Q3", "complete", ["SPY"], windows=CA_WINDOWS_H)
    kept, rec = cl.fetch_window("Q2", "complete", ["SPY"], windows=CA_WINDOWS_H, event_min=EVENT_DATE_MIN_H,
                                event_max=EVENT_DATE_MAX_H, stage="stage_h")
    assert rec["process_date_window"] == ["2026-06-03", "2026-08-31"] and {r["id"] for r in kept} == {"d-spy-h"}
    assert POST_ID not in json.dumps(rec)


def test_leakage_guard_both_sides():
    assert sh.assert_no_leakage_h({"r": [{"event_date": "2026-06-02"}, {"ex_date": "2021-01-04"}]}) == 2
    for bad in ("2026-06-03", "2020-12-31"):
        with pytest.raises(sh.sr.LeakageError):
            sh.assert_no_leakage_h({"r": [{"ex_date": bad}]})


def test_unqueried_alias_detected():
    recs = [{"ca_type": "name_changes", "old_symbol": "OLDX", "new_symbol": "AAPL"}]
    assert sh.unqueried_aliases(recs, ["AAPL", "FB"]) == ["OLDX"]
    assert sh.unqueried_aliases([{"ca_type": "name_changes", "old_symbol": "FB", "new_symbol": "META"}], ["FB"]) == []


def test_end_to_end_capture_stage_h(tmp_path):
    fake = FakeH(ca_records=CA_H)
    res = sh.capture(http=http(fake), env={"protocol": {"version": "test"}}, root=tmp_path, snapshot_id="h1")
    snap = Path(res["snapshot_dir"])
    m = res["manifest"]
    assert m["validation_status_counts"] == {"OK": 52, "BLOCKING": 0, "HARD_FAIL": 0}
    assert m["crosscheck_blocking_symbols"] == [] and m["usable_for_research"] is True, \
        json.loads((snap / "reviews.json").read_text())["items"]
    run = json.loads((snap / "run.json").read_text())
    assert run["asof"] == "2026-10-07" and run["assets_endpoint_called"] is False and run["sessions"] == 1359
    assert run["ca_counts"]["Q2_complete"]["discarded_after_stage_h"] == 1
    assert run["ca_counts"]["Q1_complete"]["discarded_before_stage_h"] == 1
    for p in snap.rglob("*"):
        if p.is_file():
            blob = p.read_bytes()
            assert POST_ID.encode() not in blob and PRE_ID.encode() not in blob and b"2026-06-15" not in blob, p
    for url, p in fake.calls:
        assert "/v2/assets/" not in url
        if url.endswith("/v2/stocks/bars"):
            assert p["asof"] == "2026-10-07"
            assert p["start"] >= "2021-01-04T05:00:00Z" and p["end"] <= "2026-06-02T04:00:00Z"
        if url.endswith("/v1/corporate-actions"):
            assert (p["start"], p["end"]) in set(CA_WINDOWS_H.values())
    assert set(m["files_sha256"]) == set(m["file_details"]) - set() and m["file_details"]["bars_raw/SPY.parquet"]["rows"] == 1359
    with pytest.raises(FileExistsError):
        sh.capture(http=http(FakeH()), env={}, root=tmp_path, snapshot_id="h1")
    with pytest.raises(PermissionError):
        open(snap / "manifest.json", "ab").close()


def test_overlap_control_identical_and_discrepancy(tmp_path):
    rdir = tmp_path / "r"
    (rdir / "bars_raw").mkdir(parents=True)
    ov = [d for d in H if d.isoformat() <= "2022-12-30"]
    idx = pd.DatetimeIndex([label_for(d) for d in ov], name="datetime")
    base = pd.DataFrame({c: 10.0 for c in ("open", "high", "low", "close", "volume", "trade_count", "provider_vwap")},
                        index=idx)
    base.assign(session_date=[d.isoformat() for d in ov]).to_parquet(rdir / "bars_raw" / "SPY.parquet")
    rec = {"id": "x1", "ca_type": "cash_dividends", "event_date": "2021-06-01", "rate": 1.0}
    (rdir / "corporate_actions_complete.json").write_text(json.dumps({"records": [rec]}))
    h = base.copy()
    out = sh.overlap_control({"raw": {"SPY": h}}, {"complete": [dict(rec)]}, rdir)
    assert out["raw_bars_status"] == "IDENTICAL" and out["events"]["status"] == "IDENTICAL"
    h2 = base.copy(); h2.iloc[3, h2.columns.get_loc("close")] = 11.0
    out2 = sh.overlap_control({"raw": {"SPY": h2}}, {"complete": [dict(rec, rate=2.0)]}, rdir)
    assert out2["raw_bars"]["SPY"]["differing_columns"]["close"]["cells_differing"] == 1
    assert out2["events"]["content_differs"]["x1"]["fields"] == ["rate"] and out2["events"]["status"] == "DISCREPANCY"
    assert "11.0" not in json.dumps(out2)                    # values never reported
