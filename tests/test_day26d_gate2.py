"""tests/test_day26d_gate2.py: protocol 2.2 clean gate fwd-gate2 and the retired legacy-cache preflight (DAY-26D).

Offline and network-free: calendar facts, synthetic prices, temporary directories. No market data is read and no
Stage F client is ever constructed.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import os
import shutil
import stat

import numpy as np
import pytest
from zoneinfo import ZoneInfo

from acquisition.contract import ROOT_DIR
from acquisition.v2 import stage_f as sf
from acquisition.v2 import stage_r as sr
from acquisition.v2.sessions import stage_f_sessions
from backtest.v2 import data as dt
from backtest.v2 import forward as fw
from backtest.v2 import metrics as mt
from backtest.v2 import run as rn
from config.day_universe import FROZEN_DAY_UNIVERSE
from scripts import day26d_gate_calendar as cal26d

NY = ZoneInfo("America/New_York")
AMEND = json.loads((ROOT_DIR / fw.AMENDMENT_FILES_22[1]).read_text(encoding="utf-8"))
ADOPT = json.loads((ROOT_DIR / fw.ADOPTION_JSON_22).read_text(encoding="utf-8"))
END = datetime(2026, 12, 9, 16, 15, tzinfo=NY)


# ------------------------------------------------------------------ declaration

def test_declared_calendar_matches_the_pinned_xnys_calendar():
    c = cal26d.compute()
    assert AMEND["calendar"] == c
    assert (c["first_session"], c["last_session"], c["count"]) == ("2026-10-12", "2026-12-09", 42)
    assert c["exposed_in_sample"] == [] and not {"2026-10-08", "2026-10-09"} & set(c["sessions"])
    assert (c["first_ranking_close"], c["first_fill_open"]) == ("2026-10-09", "2026-10-12")
    assert [d["decision_close"] for d in c["decisions"]] == ["2026-10-09", "2026-10-30", "2026-11-30"]
    reads = {d[k] for d in c["decisions"] for k in ("ranking_reads_close_t_minus_21", "ranking_reads_close_t_minus_252")}
    assert not reads & {"2026-10-08", "2026-10-09"}                 # no ranking reads an exposed close
    assert (c["inputs_before"], c["stage_f_sessions"]) == (444, 486)
    assert c["earliest_capture"]["utc"] == "2026-12-09T21:15:00+00:00"
    assert fw.check_segment_calendar("fwd-gate2") == [date.fromisoformat(s) for s in c["sessions"]]


def test_runner_segment_and_adoption_record_match_the_amendment():
    g = rn.SEGMENTS["fwd-gate2"]
    assert (g["first"], g["last"], g["sessions"], g["inputs_before"]) == (date(2026, 10, 12), date(2026, 12, 9), 42, 444)
    assert g["experiment"] == {"V2-MOM": "V2-MOM-F003", "B1": "V2-B1-fwd-gate2", "B2": "V2-B2-fwd-gate2"}
    assert g["status_prefix"] == "FORWARD42" and g["protocol_version"].endswith("+ 2.2")
    assert ADOPT["decided_utc"] == AMEND["drafted_and_adopted_utc"] == "2026-10-10T14:56:30Z"
    for p in fw.AMENDMENT_FILES_22:
        assert ADOPT["adopted_files_sha256_lf"][p] == fw.lf_sha256(ROOT_DIR / p)
    assert ADOPT["segment_status"] == AMEND["segment_status"]


# ------------------------------------------------------------------ access gates (fail-closed)

@pytest.mark.parametrize("seg_id", ["fwd-diag", "fwd-gate"])
def test_invalid_and_superseded_segments_are_refused_even_when_everything_else_passes(seg_id, monkeypatch):
    monkeypatch.setattr(fw, "check_time", lambda *a, **k: None)
    monkeypatch.setattr(fw, "check_adoption", lambda *a, **k: {})
    with pytest.raises(fw.ForwardAccessRefused):
        fw.check_forward_access(seg_id, datetime(2027, 6, 1, tzinfo=NY))


def test_gate2_time_gate_is_exact(monkeypatch):
    with pytest.raises(fw.ForwardAccessRefused, match="may not be acquired"):
        fw.check_forward_access("fwd-gate2", datetime(2026, 12, 9, 16, 14, 59, tzinfo=NY))
    fw.check_time("fwd-gate2", END)


def test_gate2_requires_the_committed_v22_and_v21_chain(tmp_path):
    with pytest.raises(fw.ForwardAccessRefused, match="committed"):
        fw.check_adoption_22(git_ok=lambda *_a: False)
    assert fw.check_adoption_22(git_ok=lambda *_a: True)["adopted_utc_22"] == "2026-10-10T14:56:30Z"
    for p in (fw.ADOPTION_JSON, *fw.AMENDMENT_FILES, *fw.INCIDENT_FILES, fw.ADOPTION_JSON_22, *fw.AMENDMENT_FILES_22):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT_DIR / p, tmp_path / p)
    assert fw.check_adoption_22(tmp_path, git_ok=lambda *_a: True)
    md = tmp_path / fw.AMENDMENT_FILES_22[0]
    md.write_bytes(md.read_bytes() + b"\nedited after adoption\n")
    with pytest.raises(fw.ForwardAccessRefused, match="adopted SHA-256"):
        fw.check_adoption_22(tmp_path, git_ok=lambda *_a: True)
    (tmp_path / fw.ADOPTION_JSON_22).unlink()
    with pytest.raises(fw.ForwardAccessRefused, match="missing"):
        fw.check_adoption_22(tmp_path, git_ok=lambda *_a: True)


def test_config_sha_guard(tmp_path):
    assert fw.check_config_sha() == fw.V2_MOM_CONFIG_SHA256
    p = tmp_path / fw.PROTOCOL_JSON
    p.parent.mkdir(parents=True)
    proto = json.loads((ROOT_DIR / fw.PROTOCOL_JSON).read_text(encoding="utf-8"))
    proto["costs"] = dict(proto["costs"], tuned=True)
    p.write_text(json.dumps(proto), encoding="utf-8")
    with pytest.raises(fw.ForwardAccessRefused, match="config SHA-256"):
        fw.check_config_sha(tmp_path)


def test_all_non_time_guards_pass_at_the_declared_time_when_committed(monkeypatch):
    """Readiness: with the records treated as committed, gate2 access passes at 16:15 New York on 2026-12-09."""
    monkeypatch.setattr(fw, "_git_ok", lambda *_a: True)                # stands in for "committed unchanged"
    out = fw.check_forward_access("fwd-gate2", END)                     # real v2.2 + v2.1 chain, pins, quarantine
    assert out["sessions"] == 42 and out["config_sha256"] == fw.V2_MOM_CONFIG_SHA256


def test_capture_refuses_before_any_client(monkeypatch, tmp_path):
    def no_client():
        raise AssertionError("HTTP client constructed")
    with pytest.raises(fw.ForwardAccessRefused):
        sf.capture("fwd-gate2", http_factory=no_client, env={}, root=tmp_path,
                   now=datetime(2026, 12, 9, 16, 0, tzinfo=NY))
    with pytest.raises(fw.ForwardAccessRefused):
        sf.preflight("fwd-gate2", datetime(2026, 12, 9, 16, 0, tzinfo=NY))


# ------------------------------------------------------------------ D1 preflight: legacy cache retired, rest enforced

def test_eol_equivalence_accepts_line_endings_only(tmp_path):
    import hashlib
    lf = b"a\nb\nc\n"
    p = tmp_path / "f.md"
    for variant in (lf, lf.replace(b"\n", b"\r\n")):
        p.write_bytes(variant)
        assert sf.eol_equivalent_sha(p, hashlib.sha256(lf).hexdigest())
        assert sf.eol_equivalent_sha(p, hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest())
    p.write_bytes(b"a\nB\nc\n")
    assert not sf.eol_equivalent_sha(p, hashlib.sha256(lf).hexdigest())


def test_frozen_baseline_check_retires_only_the_legacy_cache(tmp_path, monkeypatch):
    out = sf.frozen_baseline_check()                     # real tree: data/cache absent, artifacts day04-day14 intact
    assert out["files_checked"] > 0 and "data/cache" in out["retired"]
    import acquisition.run as ar
    base = json.loads(ar.INTEGRITY_BASELINE.read_text(encoding="utf-8"))["hashes"]
    rel = sorted(base["artifacts/day13"])[0]
    target = tmp_path / rel
    for d in base:
        if d == "data/cache":
            continue
        for f in base[d]:
            (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT_DIR / f, tmp_path / f)
    assert sf.frozen_baseline_check(tmp_path)["files_checked"] == out["files_checked"]
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(sr.PreflightError, match="content differs"):
        sf.frozen_baseline_check(tmp_path)


# ------------------------------------------------------------------ D4 immutable snapshot

def test_snapshot_must_be_read_only(tmp_path):
    with pytest.raises(fw.ForwardAccessRefused, match="empty"):
        fw.check_snapshot_immutable(tmp_path / "missing")
    f = tmp_path / "snap" / "manifest.json"
    f.parent.mkdir()
    f.write_text("{}")
    with pytest.raises(fw.ForwardAccessRefused, match="writable"):
        fw.check_snapshot_immutable(f.parent)
    os.chmod(f, stat.S_IREAD)
    try:
        assert fw.check_snapshot_immutable(f.parent) == 1
    finally:
        os.chmod(f, stat.S_IWRITE | stat.S_IREAD)


def test_loader_refuses_gate2_now():
    with pytest.raises(fw.ForwardAccessRefused):
        dt.load_stage_f("fwd-gate2", "stage_f_fwd-gate2_x", "sha", now=datetime(2026, 10, 10, 15, tzinfo=NY))


# ------------------------------------------------------------------ D3 sample separation (synthetic)

def test_gate2_sample_is_exactly_its_42_sessions():
    sessions = tuple(stage_f_sessions(date(2026, 12, 9)))
    tickers = tuple(sorted(FROZEN_DAY_UNIVERSE)) + ("SPY",)
    rng = np.random.default_rng(11)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, (len(sessions), len(tickers))), axis=0))
    data = dt.MarketData(sessions, tickers, close * 1.001, close, np.ones(close.shape), np.zeros(close.shape))
    st = rn.Setup(data, rn.SEGMENTS["fwd-gate2"])
    assert st.seg_first == 444 and st.seg_last - st.seg_first + 1 == 42
    assert [data.sessions[i].isoformat() for i in st.month] == ["2026-10-09", "2026-10-30", "2026-11-30"]
    expected = cal26d.compute()["sessions"]
    for f in ("V2-MOM", "B1", "B2"):
        r = rn.run_family(st, f, 0.0005)
        assert r.sessions == expected and not {"2026-10-08", "2026-10-09"} & set(r.sessions)
        assert all("2026-10-12" <= x["session"] <= "2026-12-09" for x in r.fills)
        assert mt.compute(r, None, None)["sessions"] == 42
