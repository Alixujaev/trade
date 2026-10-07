"""tests/test_day18_stage_r.py: DAY-18 Stage R acquisition (protocol v2.0 R1 + v2.0.1).

All provider calls go through a fake `get` (tests/conftest.py blocks real sockets). Prices are synthetic
constants; the synthetic `adjustment=all` series is built from the synthetic events so the cross-check has a
known answer. Nothing here reads real market data.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from acquisition.v2 import crosscheck as cc
from acquisition.v2 import events as ev
from acquisition.v2 import identity as idn
from acquisition.v2 import validation as val
from acquisition.v2.bars_client import DailyBarsClient, PageConflictError, normalize_daily
from acquisition.v2.ca_client import CorporateActionsClient, boundary_filter, event_date
from acquisition.v2.contract import CA_WINDOWS, EVENT_DATE_MAX, stage_r_symbols, universe
from acquisition.v2.http import AlpacaRequestError, HttpClient, RequestGuardError
from acquisition.v2.sessions import label_for, session_of_label, stage_r_sessions
from acquisition.v2 import stage_r as sr

SESSIONS = stage_r_sessions()
KEY, SECRET = "test-key-id-XYZ", "test-secret-ABC"
LEAK_ID = "LEAK-SENTINEL-7f3a"
AAPL_C, META_C, ETF_C, SPY_C = "037833100", "30303M102", "ETFCUSIP9", "78462F103"


# ---------------------------------------------------------------- synthetic world

EVENTS = {  # entity -> list of (kind, ex_date, value)
    "AAPL": [("div", date(2019, 5, 10), 0.77), ("split", date(2020, 8, 31), 4.0)],
    "SPY": [("div", date(2021, 3, 19), 1.0), ("div", date(2022, 12, 16), 1.5)],
    "META": [],
}


def raw_close(sym: str, d: date) -> float:
    if sym == "AAPL":
        return 100.0 if d < date(2020, 8, 31) else 25.0
    return 200.0


def adj_factor(sym: str, d: date) -> float:
    """Backward adjustment A(d): product of factors for events with ex_date > d."""
    a = 1.0
    for kind, ex, val_ in EVENTS.get(sym, []):
        if ex > d:
            if kind == "split":
                a /= val_
            else:
                prev = max(s for s in SESSIONS if s < ex)
                a *= 1.0 - val_ / raw_close(sym, prev)
    return a


def bars_for(sym: str, adjustment: str) -> list[dict]:
    out = []
    for d in SESSIONS:
        c = raw_close(sym, d) * (adj_factor(sym, d) if adjustment == "all" else 1.0)
        out.append({"t": label_for(d).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": c, "h": c, "l": c, "c": c, "v": 1000,
                    "n": 10, "vw": c})
    return out


CA_RECORDS = [
    ("cash_dividends", {"id": "d-aapl-2019", "symbol": "AAPL", "cusip": "", "rate": 0.77, "special": False,
                        "foreign": False, "ex_date": "2019-05-10", "record_date": "2019-05-13",
                        "payable_date": "2019-05-16", "process_date": "2019-05-16"}),
    ("forward_splits", {"id": "s-aapl-2020", "symbol": "AAPL", "cusip": AAPL_C, "new_rate": 4, "old_rate": 1,
                        "ex_date": "2020-08-31", "record_date": "2020-08-24", "payable_date": "2020-08-28",
                        "process_date": "2020-08-31"}),
    ("cash_dividends", {"id": "d-spy-2021", "symbol": "SPY", "cusip": SPY_C, "rate": 1.0, "special": False,
                        "foreign": False, "ex_date": "2021-03-19", "record_date": "2021-03-22",
                        "payable_date": "2021-04-30", "process_date": "2021-04-30"}),
    # Q2: process_date after 2022-12-30 but ex_date inside Stage R -> must be KEPT
    ("cash_dividends", {"id": "d-spy-2022q4", "symbol": "SPY", "cusip": SPY_C, "rate": 1.5, "special": False,
                        "foreign": False, "ex_date": "2022-12-16", "record_date": "2022-12-19",
                        "payable_date": "2023-01-31", "process_date": "2023-01-31"}),
    # Q2: ex_date after Stage R -> must be DISCARDED and never persisted
    ("cash_dividends", {"id": LEAK_ID, "symbol": "SPY", "cusip": SPY_C, "rate": 9.99, "special": False,
                        "foreign": False, "ex_date": "2023-03-17", "record_date": "2023-03-20",
                        "payable_date": "2023-03-28", "process_date": "2023-03-28"}),
    ("name_changes", {"id": "n-fb-meta", "old_symbol": "FB", "new_symbol": "META", "old_cusip": META_C,
                      "new_cusip": META_C, "process_date": "2022-06-09"}),
    ("name_changes", {"id": "n-meta-metv", "old_symbol": "META", "new_symbol": "METV", "old_cusip": ETF_C,
                      "new_cusip": ETF_C, "process_date": "2022-06-01"}),
    ("cash_mergers", {"id": "m-aapl-xyz", "acquirer_symbol": "AAPL", "acquirer_cusip": AAPL_C,
                      "acquiree_symbol": "XYZ", "acquiree_cusip": "XYZCUSIP0", "rate": 10.0,
                      "effective_date": "2021-06-01", "process_date": "2021-06-01"}),
]


class Resp:
    def __init__(self, status=200, body=None, rid="rid"):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = {"X-Request-ID": rid}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeAlpaca:
    def __init__(self, ca_records=None, bar_page=10000, script=None):
        self.calls: list[tuple[str, dict]] = []
        self.ca_records = CA_RECORDS if ca_records is None else ca_records
        self.bar_page = bar_page
        self.script = list(script or [])

    def __call__(self, url, params=None, headers=None, timeout=None):
        params = dict(params or {})
        self.calls.append((url, params))
        if self.script:
            return self.script.pop(0)
        if "/v2/assets/" in url:
            sym = url.rsplit("/", 1)[1]
            return Resp(body={"symbol": sym, "name": sym, "exchange": "NASDAQ", "class": "us_equity",
                              "status": "active", "tradable": True, "cusip": None})
        if url.endswith("/v2/stocks/bars"):
            assert params.get("asof"), "asof must be explicit"
            sym = params["symbols"]
            rows = [b for b in bars_for(sym, params["adjustment"]) if params["start"] <= b["t"] <= params["end"]]
            off = int(params.get("page_token") or 0)
            page = rows[off:off + self.bar_page]
            nxt = str(off + self.bar_page) if off + self.bar_page < len(rows) else None
            return Resp(body={"bars": {sym: page}, "next_page_token": nxt})
        if url.endswith("/v1/corporate-actions"):
            syms = set(params["symbols"].split(","))
            out: dict[str, list] = {}
            for typ, rec in self.ca_records:
                refs = {rec.get(k) for k in ("symbol", "old_symbol", "new_symbol", "acquirer_symbol", "acquiree_symbol")}
                if params["start"] <= rec["process_date"] <= params["end"] and refs & syms:
                    out.setdefault(typ, []).append(dict(rec))
            return Resp(body={"corporate_actions": out, "next_page_token": None})
        raise AssertionError(f"unexpected url {url}")


def http(fake, **kw):
    return HttpClient(KEY, SECRET, get=fake, sleep=lambda s: None, clock=lambda: 0.0, **kw)


# ---------------------------------------------------------------- sessions / labels

def test_stage_r_sessions_and_labels():
    assert len(SESSIONS) == 1762 and SESSIONS[0] == date(2016, 1, 4) and SESSIONS[-1] == date(2022, 12, 30)
    assert label_for(date(2016, 1, 4)).strftime("%H:%M") == "05:00"       # EST
    assert label_for(date(2016, 7, 1)).strftime("%H:%M") == "04:00"       # EDT
    d, midnight = session_of_label(pd.Timestamp("2016-07-01T04:00:00Z"))
    assert d == date(2016, 7, 1) and midnight
    assert session_of_label(pd.Timestamp("2016-07-01T05:00:00Z"))[1] is False


def test_universe_and_symbols_frozen():
    assert len(universe()) == 25 and stage_r_symbols() == sorted(universe() + ["SPY"])


# ---------------------------------------------------------------- bars client

def test_bars_guard_rejects_out_of_range_before_any_request():
    fake = FakeAlpaca()
    c = DailyBarsClient(http(fake), asof="2026-10-07")
    with pytest.raises(RequestGuardError):
        c.fetch("AAPL", "raw", end=label_for(date(2023, 1, 3)))
    with pytest.raises(RequestGuardError):
        c.fetch("AAPL", "raw", start=label_for(date(2015, 12, 31)))
    with pytest.raises(RequestGuardError):
        c.fetch("AAPL", "split")
    assert fake.calls == []


def test_bars_full_range_pagination_asof_and_no_credentials():
    fake = FakeAlpaca(bar_page=700)
    df, rec = DailyBarsClient(http(fake), asof="2026-10-07").fetch("AAPL", "raw")
    assert len(df) == 1762 and rec["page_count"] == 3
    assert all(p["asof"] == "2026-10-07" and p["feed"] == "sip" and p["timeframe"] == "1Day" for _, p in fake.calls)
    assert fake.calls[0][1]["end"] == "2022-12-30T05:00:00Z"
    blob = json.dumps(rec)
    assert KEY not in blob and SECRET not in blob


def test_bars_conflicting_duplicate_raises():
    b = {"t": "2016-01-04T05:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
    with pytest.raises(PageConflictError):
        normalize_daily([b, dict(b, c=2)])
    df, dupes = normalize_daily([b, dict(b)])
    assert len(df) == 1 and dupes == 1


def test_fatal_403_not_retried():
    fake = FakeAlpaca(script=[Resp(403, {"message": "forbidden"})])
    with pytest.raises(AlpacaRequestError) as ei:
        DailyBarsClient(http(fake), asof="2026-10-07").fetch("AAPL", "raw")
    assert ei.value.fatal and len(fake.calls) == 1


# ---------------------------------------------------------------- corporate actions + LEAKAGE

def test_event_date_fallback_order():
    assert event_date({"ex_date": "2020-01-02", "effective_date": "2020-03-01", "process_date": "2020-04-01"}) == "2020-01-02"
    assert event_date({"effective_date": "2020-03-01", "process_date": "2020-04-01"}) == "2020-03-01"
    assert event_date({"process_date": "2020-04-01"}) == "2020-04-01"


def test_boundary_filter_keeps_q2_in_range_and_drops_post_boundary():
    kept, counts = boundary_filter([(t, r) for t, r in CA_RECORDS])
    ids = {r["id"] for r in kept}
    assert "d-spy-2022q4" in ids                       # process 2023-01-31, ex 2022-12-16 -> KEPT
    assert LEAK_ID not in ids                          # ex 2023-03-17 -> DROPPED
    assert counts["discarded_after_stage_r"] == 1
    assert all(r["event_date"] <= EVENT_DATE_MAX for r in kept)
    kept2, c2 = boundary_filter([("cash_dividends", {"id": "old", "ex_date": "2015-12-30", "process_date": "2016-01-05"})])
    assert kept2 == [] and c2["discarded_before_stage_r"] == 1


def test_ca_client_never_returns_post_boundary_record_and_only_counts_it():
    fake = FakeAlpaca()
    kept, rec = CorporateActionsClient(http(fake)).fetch_window("Q2", "complete", ["SPY"])
    assert [r["id"] for r in kept] == ["d-spy-2022q4"]
    assert rec["counts"]["discarded_after_stage_r"] == 1
    assert LEAK_ID not in json.dumps(rec) and "2023-03-17" not in json.dumps(rec) and "9.99" not in json.dumps(rec)
    assert fake.calls[0][1]["start"] == "2022-12-31" and fake.calls[0][1]["end"] == "2023-03-31"


def test_ca_window_and_quality_guard():
    c = CorporateActionsClient(http(FakeAlpaca()))
    with pytest.raises(RequestGuardError):
        c.fetch_window("Q3", "complete", ["SPY"])
    with pytest.raises(RequestGuardError):
        c.fetch_window("Q1", "partial", ["SPY"])
    assert CA_WINDOWS == {"Q1": ("2016-01-01", "2022-12-30"), "Q2": ("2022-12-31", "2023-03-31")}


# ---------------------------------------------------------------- identity

def _kept(records=CA_RECORDS):
    return boundary_filter([(t, r) for t, r in records])[0]


def test_identity_fb_meta_and_foreign_metv():
    res = idn.resolve(_kept(), ["AAPL", "META", "SPY"], ["AAPL", "FB", "META", "SPY"])
    assert res["anchors"]["META"] == META_C and res["anchor_source"]["META"] == "name_change"
    assert res["aliases"] == {"FB": "META"}
    assert [f["id"] for f in res["foreign_entity_records"]] == ["n-meta-metv"]
    assert not any(a["id"] == "n-meta-metv" for a in res["assignments"])
    assert res["anchors"]["AAPL"] == AAPL_C
    by = {(a["id"], a["entity"]): a for a in res["assignments"]}
    assert by[("d-aapl-2019", "AAPL")]["match"] == "ticker_only"        # empty CUSIP, no foreign entity for AAPL
    assert by[("m-aapl-xyz", "AAPL")]["role"] == "acquirer"
    assert res["conflicts"] == []


def test_identity_empty_cusip_with_foreign_entity_is_conflict():
    recs = CA_RECORDS + [("cash_dividends", {"id": "d-meta-blank", "symbol": "META", "cusip": "", "rate": 0.1,
                                             "ex_date": "2019-01-02", "process_date": "2019-01-10"})]
    res = idn.resolve(_kept(recs), ["AAPL", "META", "SPY"], ["AAPL", "FB", "META", "SPY"])
    assert any(c["kind"] == "b_empty_cusip_with_foreign_entity" and c["entity"] == "META" for c in res["conflicts"])


def test_identity_unlinked_cusips_and_missed_alias():
    recs = [("cash_dividends", {"id": "a1", "symbol": "KO", "cusip": "AAA111111", "rate": 1, "ex_date": "2020-06-01",
                                "process_date": "2020-06-10"}),
            ("cash_dividends", {"id": "a2", "symbol": "KO", "cusip": "BBB222222", "rate": 1, "ex_date": "2021-06-01",
                                "process_date": "2021-06-10"}),
            ("name_changes", {"id": "n1", "old_symbol": "OLDX", "new_symbol": "PEP", "old_cusip": "PPP", "new_cusip": "PPP",
                              "process_date": "2020-01-10"})]
    res = idn.resolve(_kept(recs), ["KO", "PEP"], ["KO", "PEP"])
    kinds = {c["kind"] for c in res["conflicts"]}
    assert "a_unlinked_cusips" in kinds and "missed_alias" in kinds


# ---------------------------------------------------------------- normalisation

def test_normalise_dividend_and_split():
    kept = _kept()
    res = ev.normalise(kept, idn.resolve(kept, ["AAPL", "META", "SPY"], ["AAPL", "FB", "META", "SPY"]))
    by = {e["id"]: e for e in res["events"]}
    assert by["s-aapl-2020"]["q"] == 4.0 and by["s-aapl-2020"]["event"] == "forward_split"
    assert by["d-aapl-2019"]["d"] == 0.77                         # declared, unadjusted (v2.0.1 C3)
    assert {i["id"] for i in res["review_items"]} == {"n-fb-meta", "m-aapl-xyz"}
    assert res["blocking"] == []


def test_normalise_blockers():
    recs = [("forward_splits", {"id": "s1", "symbol": "AAPL", "cusip": AAPL_C, "new_rate": 1, "old_rate": 4,
                                "ex_date": "2020-08-31", "process_date": "2020-08-31"}),
            ("cash_dividends", {"id": "d1", "symbol": "AAPL", "cusip": AAPL_C, "rate": 0.2, "ex_date": "2021-02-05",
                                "process_date": "2021-02-11"}),
            ("cash_dividends", {"id": "d2", "symbol": "AAPL", "cusip": AAPL_C, "rate": 0.2, "ex_date": "2021-02-05",
                                "process_date": "2021-02-12"}),
            ("forward_splits", {"id": "s2", "symbol": "AAPL", "cusip": AAPL_C, "new_rate": 2, "old_rate": 1,
                                "ex_date": "2021-02-05", "process_date": "2021-02-05"})]
    kept = _kept(recs)
    res = ev.normalise(kept, idn.resolve(kept, ["AAPL"], ["AAPL"]))
    kinds = {b["kind"] for b in res["blocking"]}
    assert {"forward_split_ratio_direction_invalid", "duplicate_records", "same_ex_date_split_and_dividend"} <= kinds


def test_compare_quality_difference_is_blocking():
    a = [{"id": "1", "x": 1}, {"id": "2", "x": 1}]
    assert ev.compare_quality(a, list(a), set())["blocking"] is False
    assert ev.compare_quality(a, a + [{"id": "3"}], set())["blocking"] is True
    assert ev.compare_quality(a, [{"id": "1", "x": 2}, {"id": "2", "x": 1}], set())["blocking"] is True


# ---------------------------------------------------------------- structural validation

def _frame(sym="META", adjustment="raw"):
    return normalize_daily(bars_for(sym, adjustment))[0]


def test_validation_ok_and_hard_fails():
    assert val.check_series(_frame(), SESSIONS)["status"] == "OK"
    df = _frame()
    bad = df.copy()
    bad.index = bad.index + pd.Timedelta(hours=1)
    assert any("label_not_ny_midnight" in h for h in val.check_series(bad, SESSIONS)["hard_fail"])
    extra = pd.concat([df, df.iloc[[0]].set_axis([label_for(date(2023, 1, 3))])])
    assert any("rows_after_stage_r" in h for h in val.check_series(extra, SESSIONS)["hard_fail"])
    ohlc = df.copy()
    ohlc.iloc[5, ohlc.columns.get_loc("high")] = 1.0
    assert any("ohlc_inconsistent" in h for h in val.check_series(ohlc, SESSIONS)["hard_fail"])


def test_validation_missing_sessions_listed_and_blocking_over_two_percent():
    df = _frame()
    few = df.drop(df.index[1000:1005])
    r = val.check_series(few, SESSIONS)
    assert r["status"] == "OK" and len(r["missing_sessions"]) == 5
    many = df.drop(df.index[400:440])
    assert val.check_series(many, SESSIONS)["status"] == "BLOCKING"
    late = df.drop(df.index[:10])
    assert any("first bar" in b for b in val.check_series(late, SESSIONS)["blocking"])
    assert val.check_raw_all(val.check_series(few, SESSIONS), val.check_series(df, SESSIONS))["status"] == "HARD_FAIL"


# ---------------------------------------------------------------- cross-check

def _cc(sym, events):
    raw, adj = _frame(sym, "raw"), _frame(sym, "all")
    rc = pd.Series(raw["close"].to_numpy(), index=[session_of_label(t)[0] for t in raw.index])
    ac = pd.Series(adj["close"].to_numpy(), index=[session_of_label(t)[0] for t in adj.index])
    return cc.crosscheck_symbol(rc, ac, events)


def test_crosscheck_matches_split_and_dividend():
    evs = [{"id": "d", "event": "cash_dividend", "ex_date": "2019-05-10", "entity": "AAPL"},
           {"id": "s", "event": "forward_split", "ex_date": "2020-08-31", "q": 4.0, "entity": "AAPL"}]
    r = _cc("AAPL", evs)
    assert r["status"] == "OK" and r["factor_changes"] == 2 and r["split_magnitude_checks"] == [{"session": "2020-08-31", "ok": True}]


def test_crosscheck_detects_missing_event_extra_event_and_wrong_ratio():
    assert _cc("AAPL", [{"id": "s", "event": "forward_split", "ex_date": "2020-08-31", "q": 4.0}])["unmatched_changes"] == ["2019-05-10"]
    extra = _cc("META", [{"id": "x", "event": "cash_dividend", "ex_date": "2018-03-01"}])
    assert extra["status"] == "BLOCKING" and extra["unmatched_events"] == ["2018-03-01"]
    wrong = _cc("AAPL", [{"id": "d", "event": "cash_dividend", "ex_date": "2019-05-10"},
                         {"id": "s", "event": "forward_split", "ex_date": "2020-08-31", "q": 2.0}])
    assert wrong["status"] == "BLOCKING" and wrong["split_magnitude_checks"][0]["ok"] is False


# ---------------------------------------------------------------- leakage guard + end-to-end snapshot

def test_assert_no_leakage_raises_on_post_boundary_dates():
    assert sr.assert_no_leakage({"records": [{"event_date": "2022-12-30"}]}) == 1
    with pytest.raises(sr.LeakageError):
        sr.assert_no_leakage({"a": [{"x": {"ex_date": "2023-01-03"}}]})


def test_end_to_end_capture_writes_once_and_never_persists_post_boundary(tmp_path):
    fake = FakeAlpaca(bar_page=1000)
    res = sr.capture(http=http(fake), asof="2026-10-07", env={"protocol": {"version": "test"}}, root=tmp_path,
                     symbols=["AAPL", "META", "SPY"], snapshot_id="snap1")
    snap = Path(res["snapshot_dir"])
    m = res["manifest"]
    assert m["usable_for_research"] is True, json.loads((snap / "reviews.json").read_text())
    assert m["crosscheck_blocking_symbols"] == [] and m["validation_status_counts"]["OK"] == 6
    reviews = json.loads((snap / "reviews.json").read_text())
    st = {i["item"]: i["status"] for i in reviews["items"]}
    assert st["name_change FB->META"] == "RESOLVED"
    assert st["cash_mergers AAPL<-XYZ"] == "RESOLVED"
    assert st["foreign-entity name_changes META->METV"] == "RESOLVED_EXCLUDED"
    # Q2 in-range record persisted; post-boundary record nowhere on disk
    comp = json.loads((snap / "corporate_actions_complete.json").read_text())
    assert "d-spy-2022q4" in {r["id"] for r in comp["records"]}
    assert comp["counts_by_window"]["Q2"]["discarded_after_stage_r"] == 1
    for p in snap.rglob("*"):
        if p.is_file():
            blob = p.read_bytes()
            assert LEAK_ID.encode() not in blob and b"2023-03-17" not in blob, p
    # no bar request outside Stage R
    for url, p in fake.calls:
        if url.endswith("/v2/stocks/bars"):
            assert p["start"] >= "2016-01-04T05:00:00Z" and p["end"] <= "2022-12-30T05:00:00Z"
    # write-once
    with pytest.raises(FileExistsError):
        sr.capture(http=http(FakeAlpaca()), asof="2026-10-07", env={}, root=tmp_path, symbols=["SPY"], snapshot_id="snap1")
    ro = snap / "manifest.json"
    with pytest.raises(PermissionError):
        open(ro, "ab").close()


def test_forbidden_roots():
    from acquisition.contract import ROOT_DIR
    for bad in (ROOT_DIR / "data" / "cache" / "x", ROOT_DIR / "artifacts" / "x",
                ROOT_DIR / "data" / "oos_cache" / "protocol_v1.1" / "x"):
        with pytest.raises(sr.SnapshotPathError):
            sr.check_location(bad)
