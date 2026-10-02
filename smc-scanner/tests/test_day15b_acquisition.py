"""tests/test_day15b_acquisition.py: DAY-15A finalization + DAY-15B capture run (fake provider, no network)."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from acquisition import provider_adapter
from acquisition.capture_policy import (
    CaptureTooEarlyError, assert_capture_allowed, capturable_sessions, capture_allowed_at,
)
from acquisition.contract import ROOT_DIR, oos_universe
from acquisition.report import ReportPathError, render_report, write_report
from acquisition.run import PreflightError, build_manifest, capture_run, preflight
from acquisition.sessions import calendar_info, resolve_oos_sessions
from acquisition.validation import calendar_coverage, expected_bar_opens

ET = ZoneInfo("America/New_York")
SESSIONS = resolve_oos_sessions()
ENV = {"environment_sha256": "e" * 64, "git_commit": "c0ffee", "git_dirty": False, "python_version": "3.12"}


# ---------------- calendar ----------------

def test_exactly_60_sessions_deterministic():
    assert len(SESSIONS) == 60
    assert resolve_oos_sessions() == SESSIONS


def test_boundary_exclusive_and_projected_range():
    assert SESSIONS[0].session > date(2026, 9, 25)
    assert SESSIONS[0].session == date(2026, 9, 28) and SESSIONS[-1].session == date(2026, 12, 21)


def test_valid_nyse_sessions_no_weekends_no_holidays():
    days = [s.session for s in SESSIONS]
    assert all(d.weekday() < 5 for d in days)
    assert date(2026, 11, 26) not in days          # Thanksgiving (calendar-derived, not hand-coded here)
    assert days == sorted(set(days))
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS", start="2026-01-02", end="2027-12-31")
    assert all(cal.is_session(pd.Timestamp(d)) for d in days)


def test_early_close_from_calendar():
    early = [s.session for s in SESSIONS if s.early_close]
    assert early == [date(2026, 11, 27)]
    s = next(x for x in SESSIONS if x.session == date(2026, 11, 27))
    assert len(expected_bar_opens(s, "5m")) == 42 and len(expected_bar_opens(s, "15m")) == 14
    assert len(expected_bar_opens(SESSIONS[0], "5m")) == 78 and len(expected_bar_opens(SESSIONS[0], "15m")) == 26


def test_calendar_version_recorded():
    info = calendar_info()
    assert info["package"] == "exchange_calendars" and info["version"] == "4.13.2" and info["calendar"] == "XNYS"


def test_requirements_pins_calendar():
    req = (ROOT_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "exchange_calendars==4.13.2" in [r.strip() for r in req]


# ---------------- capture policy ----------------

def test_capture_before_1615_rejected_at_or_after_accepted():
    s = SESSIONS[0]
    with pytest.raises(CaptureTooEarlyError):
        assert_capture_allowed(s, datetime(2026, 9, 28, 16, 14, tzinfo=ET))
    assert_capture_allowed(s, datetime(2026, 9, 28, 16, 15, tzinfo=ET))
    assert capture_allowed_at(s) == datetime(2026, 9, 28, 16, 15, tzinfo=ET)


def test_capturable_sessions_prefix_and_dst():
    now = datetime(2026, 10, 2, 6, 31, tzinfo=ET)
    assert [s.session for s in capturable_sessions(SESSIONS, now)] == [
        date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]
    # after DST ends (2026-11-01) the rule stays 16:15 local time
    nov = next(s for s in SESSIONS if s.session == date(2026, 11, 2))
    assert capture_allowed_at(nov).utcoffset().total_seconds() == -5 * 3600
    with pytest.raises(ValueError):
        capturable_sessions(SESSIONS, datetime(2026, 10, 2, 12, 0))  # naive time refused


# ---------------- coverage (structural) ----------------

def _bars(sessions, interval="5m", drop=0, extra_offgrid=False):
    frames = []
    for s in sessions:
        idx = expected_bar_opens(s, interval)
        n = len(idx)
        frames.append(pd.DataFrame({"open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n, "close": [1.0] * n,
                                    "adj_close": [1.0] * n, "volume": [1] * n}, index=idx))
    df = pd.concat(frames)
    if drop:
        df = df.drop(df.index[5:5 + drop])
    if extra_offgrid:
        t = df.index[0] + pd.Timedelta(minutes=2)
        df = pd.concat([df, df.iloc[[0]].set_axis([t])]).sort_index()
    return df


def test_coverage_complete_missing_bar_missing_session_offgrid():
    cap = SESSIONS[:3]
    assert calendar_coverage(_bars(cap), "5m", cap)["complete"]
    r = calendar_coverage(_bars(cap, drop=2), "5m", cap)
    assert r["missing_bars"] == 2 and r["sessions_incomplete"] == [str(cap[0].session)] and not r["complete"]
    r = calendar_coverage(_bars(cap[:2]), "5m", cap)
    assert r["sessions_missing"] == [str(cap[2].session)] and r["missing_bars"] == 78
    r = calendar_coverage(_bars(cap, extra_offgrid=True), "5m", cap)
    assert r["bars_outside_expected_grid"] == 1 and not r["complete"]


def test_coverage_reports_no_prices():
    rep = calendar_coverage(_bars(SESSIONS[:1]), "15m", SESSIONS[:1])
    blob = json.dumps(rep).lower()
    assert not any(k in blob for k in ("return", "price", "mean", "pnl", "signal"))


# ---------------- capture run (fake provider) ----------------

NOW = datetime(2026, 10, 2, 6, 31, tzinfo=ET)


def _fake_download_factory(fail_symbol=None, bump=0.0):
    def fake(symbol, start=None, end=None, interval="5m", **kw):
        if symbol == fail_symbol:
            raise ConnectionError("provider failure (fake)")
        cap = capturable_sessions(SESSIONS, NOW)
        df = _bars(cap, interval)
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close",
                                "adj_close": "Adj Close", "volume": "Volume"})
        df["Close"] = df["Close"] + bump
        df["High"] = df["High"] + bump
        df["Adj Close"] = df["Adj Close"] + bump
        df.index = df.index.tz_convert("America/New_York")
        return df
    return fake


def test_capture_run_universe_missing_reported_not_substituted(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_adapter.yf, "download", _fake_download_factory(fail_symbol="MSFT"))
    syms = ["AAPL", "MSFT", "NVDA"]
    run = capture_run(now=NOW, env=ENV, root=tmp_path, symbols=syms, acquisition_commit="c0ffee")
    got = {(r["symbol"], r["interval"]): r["status"] for r in run["results"]}
    assert got[("MSFT", "5m")] == "MISSING" and got[("MSFT", "15m")] == "MISSING"
    assert {r["symbol"] for r in run["results"]} == set(syms)       # no substitute symbol appears
    assert run["captured_sessions"] == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    assert all(r["coverage"]["complete"] for r in run["results"] if r["status"] != "MISSING")
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert len(man["oos_sessions"]) == 60 and man["calendar"]["version"] == "4.13.2"
    assert man["snapshots"][0]["missing"] == [{"symbol": "MSFT", "interval": "15m", "error": "ConnectionError: provider failure (fake)"},
                                              {"symbol": "MSFT", "interval": "5m", "error": "ConnectionError: provider failure (fake)"}]
    report = render_report(run, man, {"passed": True})
    assert "PARTIAL" in report and "No OOS signals, returns" in report


def test_symbols_outside_universe_refused(tmp_path):
    with pytest.raises(ValueError):
        capture_run(now=NOW, env=ENV, root=tmp_path, symbols=["AAPL", "SPY"])
    assert set(oos_universe()) and len(oos_universe()) == 25


def test_capture_before_first_session_wait_refused(tmp_path):
    with pytest.raises(PreflightError):
        capture_run(now=datetime(2026, 9, 28, 16, 0, tzinfo=ET), env=ENV, root=tmp_path, symbols=["AAPL"])


def test_second_capture_overlap_identical_then_discrepancy(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_adapter.yf, "download", _fake_download_factory())
    first = capture_run(now=NOW, env=ENV, root=tmp_path, symbols=["AAPL"])
    later = datetime(2026, 10, 2, 7, 31, tzinfo=ET)
    second = capture_run(now=later, env=ENV, root=tmp_path, symbols=["AAPL"])
    assert second["snapshot_id"] != first["snapshot_id"]
    assert all(o["identical_on_overlap"] for r in second["results"] for o in r["overlap_with_previous"])
    monkeypatch.setattr(provider_adapter.yf, "download", _fake_download_factory(bump=0.5))
    third = capture_run(now=datetime(2026, 10, 2, 8, 31, tzinfo=ET), env=ENV, root=tmp_path, symbols=["AAPL"])
    discrep = [o for r in third["results"] for o in r["overlap_with_previous"] if not o["identical_on_overlap"]]
    assert discrep and all(r["corporate_action_status"]["overlap_discrepancy"] for r in third["results"])
    first_file = tmp_path / "snapshots" / first["snapshot_id"] / "AAPL_5m.parquet"
    assert first_file.exists()  # original preserved
    man = build_manifest(tmp_path)
    assert len(man["snapshots"]) == 3 and man["snapshots"][-1]["discrepancies"]


# ---------------- preflight ----------------

def _clean_git():
    return {"commit": "c0ffee", "tracked_changes": [], "untracked": [], "unexpected_untracked": []}


def test_preflight_passes_and_fails(tmp_path):
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps({"hashes": {"d": {"f": "1"}}}))
    assert preflight(baseline_path=base, hasher=lambda: {"d": {"f": "1"}}, git=_clean_git)["passed"]
    with pytest.raises(PreflightError, match="changed"):
        preflight(baseline_path=base, hasher=lambda: {"d": {"f": "2"}}, git=_clean_git)
    dirty = dict(_clean_git(), tracked_changes=[" M strategy/day/vwap_momentum.py"])
    with pytest.raises(PreflightError, match="not clean"):
        preflight(baseline_path=base, hasher=lambda: {"d": {"f": "1"}}, git=lambda: dirty)
    with pytest.raises(PreflightError, match="baseline missing"):
        preflight(baseline_path=tmp_path / "nope.json", hasher=lambda: {}, git=_clean_git)


def test_preflight_fails_on_wrong_session_count(monkeypatch, tmp_path):
    import acquisition.run as run_mod
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps({"hashes": {}}))
    monkeypatch.setattr(run_mod, "resolve_oos_sessions", lambda: SESSIONS[:59])
    with pytest.raises(PreflightError, match="60"):
        preflight(baseline_path=base, hasher=lambda: {}, git=_clean_git)


# ---------------- write guards ----------------

def test_report_writer_only_day15(tmp_path):
    with pytest.raises(ReportPathError):
        write_report(ROOT_DIR / "artifacts" / "day14" / "x.md", "x")
    with pytest.raises(ReportPathError):
        write_report(tmp_path / "x.md", "x")
    assert not (ROOT_DIR / "artifacts" / "day14" / "x.md").exists()


@pytest.mark.parametrize("target", ["data/cache", "artifacts/day15"])
def test_capture_refuses_research_cache_and_artifacts(target):
    with pytest.raises(ValueError):
        capture_run(now=NOW, env=ENV, root=ROOT_DIR / target, symbols=["AAPL"])
    assert not (ROOT_DIR / target / "snapshots").exists()
