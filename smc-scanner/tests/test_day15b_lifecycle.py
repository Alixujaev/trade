"""tests/test_day15b_lifecycle.py: incremental provider window, 60/60 guard, partial sessions, idempotency.

All provider calls are faked and recorded; tests/conftest.py blocks real network and cache writes.
The real OOS snapshot is only read through the metadata/hash ledger (no parquet content is parsed).
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from acquisition import provider_adapter
from acquisition.contract import OOS_ROOT, ROOT_DIR
from acquisition.ledger import capture_state, complete_units
from acquisition.provider_adapter import (
    INTRADAY_LOOKBACK_DAYS, LOOKBACK_SAFETY_MARGIN_DAYS, earliest_requestable_start,
)
from acquisition.report import ReportPathError, write_report
from acquisition.run import AcquisitionBlockedError, capture_run
from acquisition.sessions import resolve_oos_sessions
from acquisition.snapshot import SnapshotPathError
from acquisition.validation import expected_bar_opens

ET = ZoneInfo("America/New_York")
SESSIONS = resolve_oos_sessions()
BY_DATE = {s.session: s for s in SESSIONS}
ENV = {"environment_sha256": "e" * 64, "git_commit": "c0ffee", "git_dirty": False, "python_version": "3.12"}
SYMS = ["AAPL"]


def at(y, m, d, hh=17, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


class FakeProvider:
    """Serves calendar-grid bars for sessions inside [start, end); records every call."""

    def __init__(self, drop=None, bump=0.0):
        self.calls: list[dict] = []
        self.drop = drop or set()   # {(symbol, interval, session_date)} -> drop the 3rd bar of that session
        self.bump = bump

    def __call__(self, symbol, start=None, end=None, interval="5m", **kw):
        s0, s1 = pd.Timestamp(start).date(), pd.Timestamp(end).date()
        self.calls.append({"symbol": symbol, "interval": interval, "start": s0, "end": s1})
        frames = []
        for d, sess in BY_DATE.items():
            if s0 <= d < s1:
                idx = expected_bar_opens(sess, interval)
                if (symbol, interval, d) in self.drop:
                    idx = idx.delete(2)
                n = len(idx)
                v = 1.0 + self.bump
                frames.append(pd.DataFrame({"Open": [1.0] * n, "High": [v] * n, "Low": [1.0] * n, "Close": [v] * n,
                                            "Adj Close": [v] * n, "Volume": [10] * n}, index=idx))
        df = pd.concat(frames)
        df.index = df.index.tz_convert("America/New_York")
        return df


def _install(monkeypatch, fake):
    monkeypatch.setattr(provider_adapter.yf, "download", fake)
    return fake


def _forbid(monkeypatch):
    monkeypatch.setattr(provider_adapter.yf, "download", lambda *a, **k: pytest.fail("no provider request allowed"))


def _hash_tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


# ---------------- provider window ----------------

def test_early_capture_works(monkeypatch, tmp_path):
    fake = _install(monkeypatch, FakeProvider())
    run = capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    assert run["status"] == "CAPTURED"
    assert {c["start"] for c in fake.calls} == {date(2026, 9, 28)} and {c["end"] for c in fake.calls} == {date(2026, 10, 2)}
    st = capture_state(tmp_path, SESSIONS, at(2026, 10, 2, 6, 31), symbols=SYMS)
    assert st["progress"] == "4/60" and st["status"] == "UP_TO_DATE"


def test_later_capture_starts_at_first_missing_session_not_original_start(monkeypatch, tmp_path):
    _install(monkeypatch, FakeProvider())
    capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    fake = _install(monkeypatch, FakeProvider())
    capture_run(now=at(2026, 10, 23), env=ENV, root=tmp_path, symbols=SYMS)
    assert {c["start"] for c in fake.calls} == {date(2026, 10, 2)}           # session 5, not 2026-09-28
    assert {c["end"] for c in fake.calls} == {date(2026, 10, 24)}            # through session 20 only
    assert capture_state(tmp_path, SESSIONS, at(2026, 10, 23), symbols=SYMS)["progress"] == "20/60"


def test_provider_window_deterministic_and_relative_to_now():
    now = at(2026, 11, 20)
    assert earliest_requestable_start(now) == earliest_requestable_start(now)
    assert earliest_requestable_start(now) == pd.Timestamp(now).tz_convert("UTC") - pd.Timedelta(
        days=INTRADAY_LOOKBACK_DAYS - LOOKBACK_SAFETY_MARGIN_DAYS)
    with pytest.raises(ValueError):
        earliest_requestable_start(datetime(2026, 11, 20, 17, 0))


def test_blocked_when_earliest_missing_session_left_provider_window(monkeypatch, tmp_path):
    _forbid(monkeypatch)
    with pytest.raises(AcquisitionBlockedError, match="2026-09-28"):
        capture_run(now=at(2026, 12, 1), env=ENV, root=tmp_path, symbols=SYMS)
    assert not (tmp_path / "snapshots").exists() and not (tmp_path / "manifest.json").exists()
    st = capture_state(tmp_path, SESSIONS, at(2026, 12, 1), symbols=SYMS)
    assert st["status"] == "BLOCKED" and st["earliest_missing_capturable_session"] == "2026-09-28"


def test_no_replacement_session_and_dataset_definition_unchanged(monkeypatch, tmp_path):
    fake = _install(monkeypatch, FakeProvider())
    capture_run(now=at(2026, 10, 23), env=ENV, root=tmp_path, symbols=SYMS)
    calendar_days = {s.session for s in SESSIONS}
    assert all(c["start"] in calendar_days for c in fake.calls)
    assert all(c["start"] >= date(2026, 9, 28) and c["end"] <= date(2026, 12, 22) for c in fake.calls)
    assert len(resolve_oos_sessions()) == 60 and resolve_oos_sessions()[0].session == date(2026, 9, 28)


# ---------------- completion guard ----------------

def _fill_60(monkeypatch, root):
    for now in (at(2026, 10, 23), at(2026, 11, 20), at(2026, 12, 21)):
        _install(monkeypatch, FakeProvider())
        r = capture_run(now=now, env=ENV, root=root, symbols=SYMS)
        assert r["status"] == "CAPTURED"


def test_60_of_60_makes_zero_requests_and_is_idempotent(monkeypatch, tmp_path):
    _fill_60(monkeypatch, tmp_path)
    st = capture_state(tmp_path, SESSIONS, at(2026, 12, 22), symbols=SYMS)
    assert st["status"] == "COMPLETE" and st["progress"] == "60/60"
    _forbid(monkeypatch)
    before = _hash_tree(tmp_path)
    for now in (at(2026, 12, 22), at(2027, 1, 15), at(2027, 6, 1)):   # also long after the provider window
        r = capture_run(now=now, env=ENV, root=tmp_path, symbols=SYMS)
        assert r["status"] == "COMPLETE" and r["progress"] == "60/60" and r["results"] == []
    assert _hash_tree(tmp_path) == before          # no new snapshot, manifest byte-identical


def test_manifest_unchanged_on_completed_noop(monkeypatch, tmp_path):
    _fill_60(monkeypatch, tmp_path)
    m = (tmp_path / "manifest.json").read_bytes()
    _forbid(monkeypatch)
    capture_run(now=at(2026, 12, 23), env=ENV, root=tmp_path, symbols=SYMS)
    assert (tmp_path / "manifest.json").read_bytes() == m


# ---------------- partial sessions / idempotency ----------------

def test_partial_session_requests_only_missing_unit_and_overlap_identical(monkeypatch, tmp_path):
    _install(monkeypatch, FakeProvider(drop={("AAPL", "5m", date(2026, 9, 29))}))
    first = capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    st = capture_state(tmp_path, SESSIONS, at(2026, 10, 2, 6, 31), symbols=SYMS)
    assert st["partial_sessions"] == ["2026-09-29"] and st["planned_request_count"] == 1
    first_files = _hash_tree(tmp_path / "snapshots" / first["snapshot_id"])
    fake = _install(monkeypatch, FakeProvider())
    second = capture_run(now=at(2026, 10, 2, 7, 31), env=ENV, root=tmp_path, symbols=SYMS)
    assert fake.calls == [{"symbol": "AAPL", "interval": "5m", "start": date(2026, 9, 29), "end": date(2026, 9, 30)}]
    ov = second["results"][0]["overlap_with_previous"]
    assert ov and all(o["identical_on_overlap"] for o in ov)
    assert _hash_tree(tmp_path / "snapshots" / first["snapshot_id"]) == first_files   # never overwritten
    assert capture_state(tmp_path, SESSIONS, at(2026, 10, 2, 7, 31), symbols=SYMS)["progress"] == "4/60"


def test_partial_session_changed_content_flagged_discrepancy(monkeypatch, tmp_path):
    _install(monkeypatch, FakeProvider(drop={("AAPL", "15m", date(2026, 9, 30))}))
    first = capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    first_files = _hash_tree(tmp_path / "snapshots" / first["snapshot_id"])
    _install(monkeypatch, FakeProvider(bump=0.5))
    second = capture_run(now=at(2026, 10, 2, 7, 31), env=ENV, root=tmp_path, symbols=SYMS)
    rec = second["results"][0]
    assert rec["corporate_action_status"]["overlap_discrepancy"] is True
    assert _hash_tree(tmp_path / "snapshots" / first["snapshot_id"]) == first_files
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["snapshots"][-1]["discrepancies"]


def test_complete_sessions_not_requested_again(monkeypatch, tmp_path):
    _install(monkeypatch, FakeProvider())
    capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    fake = _install(monkeypatch, FakeProvider())
    capture_run(now=at(2026, 10, 9), env=ENV, root=tmp_path, symbols=SYMS)
    assert all(c["start"] >= date(2026, 10, 2) for c in fake.calls)


def test_tampered_snapshot_not_counted_complete(monkeypatch, tmp_path):
    _install(monkeypatch, FakeProvider())
    run = capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    f = tmp_path / "snapshots" / run["snapshot_id"] / run["results"][0]["data_file"]
    os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
    f.write_bytes(f.read_bytes() + b"x")
    st = capture_state(tmp_path, SESSIONS, at(2026, 10, 2, 6, 31), symbols=SYMS)
    assert st["progress"] == "0/60" and st["planned_request_count"] == 1


def test_missing_unit_reported_and_retried_not_substituted(monkeypatch, tmp_path):
    def flaky(symbol, start=None, end=None, interval="5m", **kw):
        if interval == "15m":
            raise ConnectionError("fake outage")
        return FakeProvider()(symbol, start=start, end=end, interval=interval)
    _install(monkeypatch, flaky)
    run = capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=tmp_path, symbols=SYMS)
    assert [r["status"] for r in run["results"] if r["interval"] == "15m"] == ["MISSING"]
    st = capture_state(tmp_path, SESSIONS, at(2026, 10, 2, 6, 31), symbols=SYMS)
    assert st["partial_sessions"] == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    assert [(p["symbol"], p["interval"]) for p in st["planned_requests"]] == [("AAPL", "15m")]


# ---------------- isolation ----------------

def test_isolation_runtime_includes_lifecycle_modules():
    code = ("import sys; sys.path.insert(0, r'%s');"
            "import acquisition.ledger, acquisition.run, acquisition.report;"
            "bad={'strategy','signals','backtest','indicators','smc','levels','journal','risk','telegram_bot','data'};"
            "print(sorted({m.split('.')[0] for m in sys.modules} & bad))" % ROOT_DIR)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"


# ---------------- protection ----------------

@pytest.mark.parametrize("target", ["data/cache", "artifacts/day04", "artifacts/day08b", "artifacts/day14", "artifacts/day15"])
def test_capture_refuses_research_cache_and_artifacts(monkeypatch, target):
    _forbid(monkeypatch)
    with pytest.raises(SnapshotPathError):
        capture_run(now=at(2026, 10, 2, 6, 31), env=ENV, root=ROOT_DIR / target, symbols=SYMS)
    assert not (ROOT_DIR / target / "snapshots").exists()


@pytest.mark.parametrize("name", ["day15a-finalization.md", "acquisition-design.md", "integrity-baseline.json",
                                  "../day14/research-protocol.md"])
def test_report_writer_refuses_protected_files(name):
    target = ROOT_DIR / "artifacts" / "day15" / name
    before = target.read_bytes() if target.exists() else None
    with pytest.raises(ReportPathError):
        write_report(target, "x")
    assert (target.read_bytes() if target.exists() else None) == before


# ---------------- real snapshot #1 (metadata + hashes only) ----------------

@pytest.mark.skipif(not (OOS_ROOT / "snapshots").exists(), reason="no OOS snapshot present")
def test_ledger_reads_existing_snapshot_read_only():
    before = _hash_tree(OOS_ROOT)
    st = capture_state(OOS_ROOT, SESSIONS, at(2026, 10, 2, 6, 31))
    assert st["progress"] == "4/60" and st["complete_sessions"] == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    assert st["status"] == "UP_TO_DATE"
    assert len(complete_units(OOS_ROOT)) == 4 * 25 * 2
    assert _hash_tree(OOS_ROOT) == before
