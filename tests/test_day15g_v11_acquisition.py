"""tests/test_day15g_v11_acquisition.py: protocol v1.1 Alpaca SIP research acquisition (DAY-15G).

Every provider call goes through a fake `get`; tests/conftest.py blocks real sockets. Prices in the fake are
synthetic constants. Nothing here reads the real v1.1 dataset.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import stat

import pandas as pd
import pytest

from acquisition.validation import expected_bar_opens
from acquisition.v1_1 import research as research_mod
from acquisition.v1_1.alpaca_client import (
    RETRY_SLEEPS_S, AlpacaBarsClient, AlpacaRequestError, EndBeyondLimitError, PageConflictError, normalize_bars,
)
from acquisition.v1_1.contract import FIRST_OOS_SESSION, STORED_COLUMNS, v11_universe
from acquisition.v1_1.ledger import accepted_units, account
from acquisition.v1_1.research import capture, expected_units, request_bounds
from acquisition.v1_1.sessions import (
    OOSRequestRejected, V11Session, assert_not_oos, research_acquisition_sessions, resolve_v11_sessions, segment,
)
from acquisition.v1_1.snapshot import SnapshotPathError, check_location, content_sha256, write_parquet_once
from acquisition.v1_1.validation import unit_checks

SESSIONS = resolve_v11_sessions()
BY_DATE = {s.session: s for s in SESSIONS}
KEY, SECRET = "test-key-id-XYZ", "test-secret-ABC"
ENV = {"environment_sha256": "e" * 64, "git_commit": "c0ffee", "protocol": {"sha256": "p" * 64}}
UTC = timezone.utc


def iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def bar(ts, price=100.0, vol=1000):
    return {"t": iso(ts), "o": price, "h": price + 1, "l": price - 1, "c": price, "v": vol, "n": 10, "vw": price}


class Resp:
    def __init__(self, status=200, body=None, rid="rid"):
        self.status_code = status
        self._body = body or {}
        self.headers = {"X-Request-ID": rid}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeAlpaca:
    """Serves calendar-grid bars (plus optional extended rows), honouring INCLUSIVE end and paging by `page_size`."""

    def __init__(self, page_size=10000, extended=False, mutate=None, script=None):
        self.calls: list[dict] = []
        self.page_size = page_size
        self.extended = extended
        self.mutate = mutate or (lambda sym, tf, bars: bars)
        self.script = list(script or [])   # optional queued Resp objects returned first

    def universe_bars(self, sym, tf):
        iv = {"5Min": "5m", "15Min": "15m"}[tf]
        out = []
        for s in SESSIONS:
            grid = list(expected_bar_opens(s, iv))
            if self.extended:
                out.append(bar(grid[0] - pd.Timedelta(minutes=60)))
            out += [bar(t) for t in grid]
            if self.extended:
                out.append(bar(pd.Timestamp(s.close_et).tz_convert("UTC") + pd.Timedelta(minutes=30)))
        return self.mutate(sym, tf, out)

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        if self.script:
            return self.script.pop(0)
        sym = url.rstrip("/").split("/")[-2]
        start, end = pd.Timestamp(params["start"]), pd.Timestamp(params["end"])
        bars = [b for b in self.universe_bars(sym, params["timeframe"]) if start <= pd.Timestamp(b["t"]) <= end]
        off = int(params.get("page_token") or 0)
        page = bars[off:off + self.page_size]
        nxt = str(off + self.page_size) if off + self.page_size < len(bars) else None
        return Resp(200, {"bars": page, "next_page_token": nxt, "symbol": sym})


def client(fake, **kw):
    return AlpacaBarsClient(KEY, SECRET, get=fake, sleep=lambda s: None, clock=lambda: 0.0, **kw)


def far_limit():
    return datetime(2026, 9, 28, 20, 0, tzinfo=UTC)


# ------------------------------------------------------------------ calendar / timestamps

def test_segments_match_protocol():
    assert [len(segment(SESSIONS, n)) for n in ("warmup", "research", "embargo", "stage1", "stage2")] == [20, 60, 1, 20, 40]
    w, r, e = segment(SESSIONS, "warmup"), segment(SESSIONS, "research"), segment(SESSIONS, "embargo")
    s1, s2 = segment(SESSIONS, "stage1"), segment(SESSIONS, "stage2")
    assert (w[0].session, w[-1].session) == (date(2026, 6, 3), date(2026, 7, 1))
    assert (r[0].session, r[-1].session) == (date(2026, 7, 2), date(2026, 9, 25))
    assert e[0].session == date(2026, 9, 28)
    assert (s1[0].session, s1[-1].session) == (date(2026, 9, 29), date(2026, 10, 26))
    assert (s2[0].session, s2[-1].session) == (date(2026, 10, 27), date(2026, 12, 22))
    assert resolve_v11_sessions() == SESSIONS   # deterministic


def test_research_acquisition_sessions_stop_at_embargo():
    rs = research_acquisition_sessions()
    assert len(rs) == 81 and rs[0].session == date(2026, 6, 3) and rs[-1].session == date(2026, 9, 28)
    assert {s.segment for s in rs} == {"warmup", "research", "embargo"}
    with pytest.raises(OOSRequestRejected):
        research_acquisition_sessions(SESSIONS)   # stage sessions passed explicitly are rejected


def test_utc_to_et_and_dst_transition():
    before = BY_DATE[date(2026, 10, 30)]
    after = BY_DATE[date(2026, 11, 2)]          # first session after the 2026-11-01 DST change
    assert pd.Timestamp(before.open_et).tz_convert("UTC") == pd.Timestamp("2026-10-30T13:30:00Z")
    assert pd.Timestamp(after.open_et).tz_convert("UTC") == pd.Timestamp("2026-11-02T14:30:00Z")
    g = expected_bar_opens(after, "5m")
    assert len(g) == 78 and g[0].tz_convert("America/New_York").strftime("%H:%M") == "09:30"
    assert g[-1].tz_convert("America/New_York").strftime("%H:%M") == "15:55"


def test_early_close_expected_counts_from_calendar():
    ec = BY_DATE[date(2026, 11, 27)]
    assert ec.early_close
    assert len(expected_bar_opens(ec, "5m")) == 42 and len(expected_bar_opens(ec, "15m")) == 14
    full = BY_DATE[date(2026, 7, 2)]
    assert len(expected_bar_opens(full, "5m")) == 78 and len(expected_bar_opens(full, "15m")) == 26


def test_request_bounds_use_last_bar_open_inclusive():
    s = BY_DATE[date(2026, 7, 2)]
    assert request_bounds(s, "5m") == (pd.Timestamp("2026-07-02T13:30:00Z"), pd.Timestamp("2026-07-02T19:55:00Z"))
    assert request_bounds(s, "15m")[1] == pd.Timestamp("2026-07-02T19:45:00Z")
    ec = BY_DATE[date(2026, 11, 27)]
    assert request_bounds(ec, "5m")[1].tz_convert("America/New_York").strftime("%H:%M") == "12:55"


# ------------------------------------------------------------------ inclusive end / pagination / normalization

def test_inclusive_end_bar_is_kept():
    fake = FakeAlpaca()
    df, rec = client(fake).fetch("AAPL", "5m", datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
                                 datetime(2026, 7, 2, 13, 35, tzinfo=UTC), not_after=far_limit())
    assert list(df.index) == [pd.Timestamp("2026-07-02T13:30:00Z"), pd.Timestamp("2026-07-02T13:35:00Z")]
    assert fake.calls[0]["params"]["end"] == "2026-07-02T13:35:00Z" and rec["end_semantics"] == "inclusive"


def test_adjacent_inclusive_requests_overlap_without_duplicates_in_capture(tmp_path):
    # Two sessions in one capture: bounds never overlap across sessions, and the per-file index is unique.
    two = [BY_DATE[date(2026, 7, 1)], BY_DATE[date(2026, 7, 2)]]
    run = capture(client=client(FakeAlpaca()), env=ENV, root=tmp_path, sessions=two, symbols=["AAPL"], snapshot_id="a")
    df = pd.read_parquet(tmp_path / "snapshots" / "a" / "AAPL_5m.parquet")
    assert not df.index.duplicated().any() and len(df) == 156 and run["status"] == "COMPLETE"


def test_pagination_multiple_pages_boundary_on_bar_and_final_page():
    fake = FakeAlpaca(page_size=26)  # 78 bars -> 3 full pages, boundary exactly on bars, final token null
    s = BY_DATE[date(2026, 7, 2)]
    a, b = request_bounds(s, "5m")
    df, rec = client(fake).fetch("AAPL", "5m", a.to_pydatetime(), b.to_pydatetime(), not_after=far_limit())
    assert rec["page_count"] == 3 and [p["bars"] for p in rec["pages"]] == [26, 26, 26]
    assert rec["pages"][-1]["next_page_token_present"] is False
    assert list(df.index) == list(expected_bar_opens(s, "5m"))      # order preserved, boundary bars kept
    assert fake.calls[1]["params"]["page_token"] == "26"


def test_pagination_one_page():
    fake = FakeAlpaca()
    s = BY_DATE[date(2026, 7, 2)]
    a, b = request_bounds(s, "15m")
    df, rec = client(fake).fetch("AAPL", "15m", a.to_pydatetime(), b.to_pydatetime(), not_after=far_limit())
    assert rec["page_count"] == 1 and len(df) == 26 and "page_token" not in fake.calls[0]["params"]


def test_pagination_overlapping_identical_pages_collapse_and_conflicts_raise():
    t0 = pd.Timestamp("2026-07-02T13:30:00Z")
    p1 = [bar(t0), bar(t0 + pd.Timedelta(minutes=5))]
    p2 = [bar(t0 + pd.Timedelta(minutes=5)), bar(t0 + pd.Timedelta(minutes=10))]
    fake = FakeAlpaca(script=[Resp(200, {"bars": p1, "next_page_token": "x"}), Resp(200, {"bars": p2, "next_page_token": None})])
    df, rec = client(fake).fetch("AAPL", "5m", t0.to_pydatetime(), (t0 + pd.Timedelta(minutes=10)).to_pydatetime(),
                                 not_after=far_limit())
    assert len(df) == 3 and rec["page_overlap_duplicates"] == 1 and df.index.is_monotonic_increasing
    with pytest.raises(PageConflictError):
        normalize_bars([bar(t0), bar(t0, price=101.0)])


def test_pagination_empty_page():
    fake = FakeAlpaca(script=[Resp(200, {"bars": [], "next_page_token": None})])
    df, rec = client(fake).fetch("AAPL", "5m", datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
                                 datetime(2026, 7, 2, 13, 35, tzinfo=UTC), not_after=far_limit())
    assert df.empty and rec["page_count"] == 1 and list(df.columns) == list(STORED_COLUMNS)


def test_normalization_schema_and_determinism():
    bars = [bar(pd.Timestamp("2026-07-02T13:35:00Z")), bar(pd.Timestamp("2026-07-02T13:30:00Z"))]
    a, _ = normalize_bars(bars)
    b, _ = normalize_bars([dict(x) for x in bars])
    assert list(a.columns) == list(STORED_COLUMNS) and "adj_close" not in a.columns
    assert str(a.index.tz) == "UTC" and a.index.is_monotonic_increasing
    assert a["provider_vwap"].notna().all() and (a["volume"] == a["volume"].round()).all()
    assert content_sha256(a) == content_sha256(b)


def test_credentials_not_in_request_record():
    fake = FakeAlpaca()
    _, rec = client(fake).fetch("AAPL", "5m", datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
                                datetime(2026, 7, 2, 13, 35, tzinfo=UTC), not_after=far_limit())
    blob = json.dumps(rec)
    assert KEY not in blob and SECRET not in blob
    assert fake.calls[0]["headers"]["APCA-API-KEY-ID"] == KEY
    assert fake.calls[0]["params"]["feed"] == "sip" and fake.calls[0]["params"]["adjustment"] == "raw"


# ------------------------------------------------------------------ retry policy

def test_retry_on_429_then_success_with_deterministic_sleeps():
    sleeps = []
    t0 = pd.Timestamp("2026-07-02T13:30:00Z")
    fake = FakeAlpaca(script=[Resp(429), Resp(200, {"bars": [bar(t0)], "next_page_token": None})])
    c = AlpacaBarsClient(KEY, SECRET, get=fake, sleep=sleeps.append, clock=lambda: 1e9, min_interval_s=0.0)
    df, rec = c.fetch("AAPL", "5m", t0.to_pydatetime(), t0.to_pydatetime(), not_after=far_limit())
    assert len(df) == 1 and sleeps == [RETRY_SLEEPS_S[0]] and len(rec["pages"][0]["attempts"]) == 2


def test_403_is_fatal_and_not_retried():
    fake = FakeAlpaca(script=[Resp(403, {"message": "subscription does not permit"})])
    with pytest.raises(AlpacaRequestError) as ei:
        client(fake).fetch("AAPL", "5m", datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
                           datetime(2026, 7, 2, 13, 35, tzinfo=UTC), not_after=far_limit())
    assert ei.value.fatal and ei.value.status == 403 and len(fake.calls) == 1


# ------------------------------------------------------------------ OOS guard

def test_oos_session_rejected_before_any_request(tmp_path):
    fake = FakeAlpaca()
    oos = BY_DATE[FIRST_OOS_SESSION]
    with pytest.raises(OOSRequestRejected):
        assert_not_oos(oos.session)
    with pytest.raises(OOSRequestRejected):
        research_acquisition_sessions([oos])
    with pytest.raises(OOSRequestRejected):
        capture(client=client(fake), env=ENV, root=tmp_path, sessions=[BY_DATE[date(2026, 9, 28)], oos], symbols=["AAPL"])
    assert fake.calls == []
    for d in (date(2026, 9, 30), date(2026, 12, 22)):
        with pytest.raises(OOSRequestRejected):
            assert_not_oos(d)
    assert_not_oos(date(2026, 9, 28))   # embargo is allowed


def test_client_rejects_end_beyond_limit_before_request():
    fake = FakeAlpaca()
    with pytest.raises(EndBeyondLimitError):
        client(fake).fetch("AAPL", "5m", datetime(2026, 9, 29, 13, 30, tzinfo=UTC), datetime(2026, 9, 29, 13, 35, tzinfo=UTC),
                           not_after=far_limit())
    assert fake.calls == []


def test_capture_never_requests_past_embargo(tmp_path):
    fake = FakeAlpaca()
    sess = [BY_DATE[date(2026, 9, 25)], BY_DATE[date(2026, 9, 28)]]
    run = capture(client=client(fake), env=ENV, root=tmp_path, sessions=sess, symbols=["AAPL"], snapshot_id="x")
    assert max(pd.Timestamp(c["params"]["end"]) for c in fake.calls) == pd.Timestamp("2026-09-28T19:55:00Z")
    assert run["max_requested_end_utc"] <= "2026-09-28T19:55:00+00:00"


# ------------------------------------------------------------------ structural / RTH

def test_extended_rows_excluded_and_counted():
    s = BY_DATE[date(2026, 7, 2)]
    grid = list(expected_bar_opens(s, "5m"))
    raw, _ = normalize_bars([bar(grid[0] - pd.Timedelta(minutes=60))] + [bar(t) for t in grid])
    rth, rep = unit_checks(raw, s, "5m")
    assert len(rth) == 78 and rep["extended_rows"] == 1 and rep["passed"]


@pytest.mark.parametrize("kind", ["missing", "offgrid", "ohlc", "nan"])
def test_structural_failures_flagged(kind):
    s = BY_DATE[date(2026, 7, 2)]
    grid = list(expected_bar_opens(s, "5m"))
    bars = [bar(t) for t in grid]
    if kind == "missing":
        bars.pop(10)
    elif kind == "offgrid":
        bars.append(bar(grid[3] + pd.Timedelta(minutes=2)))
    elif kind == "ohlc":
        bars[5]["h"] = bars[5]["l"] - 5
    elif kind == "nan":
        bars[5]["c"] = None
    df, _ = normalize_bars(bars)
    _, rep = unit_checks(df, s, "5m")
    assert not rep["passed"]


def test_duplicate_timestamps_flagged():
    s = BY_DATE[date(2026, 7, 2)]
    df, _ = normalize_bars([bar(t) for t in expected_bar_opens(s, "5m")])
    df = pd.concat([df, df.iloc[[0]]]).sort_index()
    _, rep = unit_checks(df, s, "5m")
    assert rep["duplicate_timestamps"] == 1 and not rep["passed"]


# ------------------------------------------------------------------ end-to-end ledger / immutability

def test_capture_accounts_every_unit_exactly_once(tmp_path):
    sess = [BY_DATE[date(2026, 6, 3)], BY_DATE[date(2026, 7, 2)], BY_DATE[date(2026, 9, 28)]]
    syms = ["MSFT", "AAPL"]
    fake = FakeAlpaca(extended=True)
    run = capture(client=client(fake), env=ENV, root=tmp_path, sessions=sess, symbols=syms, snapshot_id="s1")
    units = json.loads((tmp_path / "snapshots" / "s1" / "units.json").read_text())
    keys = [(u["session"], u["symbol"], u["interval"]) for u in units]
    assert len(keys) == len(set(keys)) == 3 * 2 * 2 and run["status"] == "COMPLETE"
    # order: session -> symbol (sorted) -> interval (5m, 15m)
    assert keys[:4] == [("2026-06-03", "AAPL", "5m"), ("2026-06-03", "AAPL", "15m"),
                        ("2026-06-03", "MSFT", "5m"), ("2026-06-03", "MSFT", "15m")]
    led = account(tmp_path, expected_units(sess, syms))
    assert led["complete"] and led["accepted_units"] == 12
    meta = json.loads((tmp_path / "snapshots" / "s1" / "AAPL_5m.meta.json").read_text())
    # requests are bounded to [open, last bar open] (inclusive), so extended rows are never returned
    assert meta["row_count"] == meta["expected_row_count"] == 234 and meta["extended_rows_excluded"] == 0
    assert not (tmp_path / "snapshots" / "s1" / "raw").exists()
    assert all(pd.Timestamp(c["params"]["start"]).tz_convert("America/New_York").strftime("%H:%M") == "09:30"
               for c in fake.calls)
    assert KEY not in (tmp_path / "snapshots" / "s1" / "run.json").read_text()
    # second run is a no-op: nothing requested
    n = len(fake.calls)
    assert capture(client=client(fake), env=ENV, root=tmp_path, sessions=sess, symbols=syms)["status"] == "COMPLETE"
    assert len(fake.calls) == n


def test_recheck_identical_and_discrepancy_keep_original(tmp_path):
    sess = [BY_DATE[date(2026, 7, 2)]]
    capture(client=client(FakeAlpaca()), env=ENV, root=tmp_path, sessions=sess, symbols=["AAPL"], snapshot_id="a")
    orig = tmp_path / "snapshots" / "a" / "AAPL_5m.parquet"
    orig_bytes = orig.read_bytes()
    r1 = capture(client=client(FakeAlpaca()), env=ENV, root=tmp_path, sessions=sess, symbols=["AAPL"],
                 recheck=True, snapshot_id="b")
    assert r1["recheck_status_counts"] == {"IDENTICAL": 2}

    def bump(sym, tf, bars):
        return [dict(b, v=b["v"] + 1) for b in bars]
    r2 = capture(client=client(FakeAlpaca(mutate=bump)), env=ENV, root=tmp_path, sessions=sess, symbols=["AAPL"],
                 recheck=True, snapshot_id="c")
    assert r2["recheck_status_counts"] == {"DISCREPANCY": 2}
    assert orig.read_bytes() == orig_bytes
    assert accepted_units(tmp_path)[("2026-07-02", "AAPL", "5m")]["snapshot_id"] == "a"
    assert not os.access(orig, os.W_OK) or not (orig.stat().st_mode & stat.S_IWRITE)


def test_write_once_and_forbidden_locations(tmp_path):
    df, _ = normalize_bars([bar(pd.Timestamp("2026-07-02T13:30:00Z"))])
    p = tmp_path / "x.parquet"
    write_parquet_once(p, df)
    with pytest.raises(FileExistsError):
        write_parquet_once(p, df)
    root = Path(research_mod.ROOT_DIR)
    for bad in (root / "data" / "cache" / "x.parquet", root / "data" / "oos_cache" / "protocol_v1.0" / "x.parquet",
                root / "artifacts" / "x.parquet"):
        with pytest.raises(SnapshotPathError):
            check_location(bad)


def test_fatal_error_aborts_run_without_substitution(tmp_path):
    sess = [BY_DATE[date(2026, 7, 2)]]
    fake = FakeAlpaca(script=[Resp(403, {"message": "forbidden"})])
    run = capture(client=client(fake), env=ENV, root=tmp_path, sessions=sess, symbols=["AAPL"], snapshot_id="f")
    assert run["status"] == "ABORTED" and len(fake.calls) == 1
    assert run["unit_status_counts"] == {"MISSING": 1, "NOT_REQUESTED": 1}


def test_universe_is_frozen_25_and_subset_enforced(tmp_path):
    assert len(v11_universe()) == 25
    with pytest.raises(ValueError):
        capture(client=client(FakeAlpaca()), env=ENV, root=tmp_path, sessions=[BY_DATE[date(2026, 7, 2)]], symbols=["ZZZZ"])
