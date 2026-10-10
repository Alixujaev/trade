"""tests/test_day26b_forward.py: protocol 2.1 forward-segment machinery (DAY-26B).

Synthetic / offline only. No forward data exists or is read: market data here is a seeded random walk on the XNYS
calendar (calendar facts only), every network connection is refused, and no Stage F client is ever constructed.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import shutil
import socket

import numpy as np
import pytest
from zoneinfo import ZoneInfo

from acquisition.contract import ROOT_DIR
from acquisition.v2 import stage_f as sf
from acquisition.v2.sessions import stage_f_sessions
from backtest.v2 import data as dt
from backtest.v2 import forward as fw
from backtest.v2 import metrics as mt
from backtest.v2 import run as rn
from config.day_universe import FROZEN_DAY_UNIVERSE
from scripts import day26b_forward_calendar as cal26b

NY = ZoneInfo("America/New_York")
AMENDMENT = json.loads((ROOT_DIR / "artifacts/day26b/protocol-v2.1-amendment.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("network access attempted in a DAY-26B test")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _iso(xs):
    return [x.isoformat() for x in xs]


# ------------------------------------------------------------------ schedule

def test_forward_split_is_21_plus_42_contiguous_without_overlap():
    split = fw.forward_split()
    d, g = split["fwd-diag"], split["fwd-gate"]
    assert (len(d), len(g)) == (21, 42) and not set(d) & set(g)
    window = [s for s in stage_f_sessions(date(2027, 1, 7)) if s >= date(2026, 10, 8)]
    assert d + g == window and len(window) == 63                       # no gap: every window session is in a segment
    assert (d[0], d[-1], g[0], g[-1]) == (date(2026, 10, 8), date(2026, 11, 5), date(2026, 11, 6), date(2027, 1, 7))
    c = cal26b.compute()
    assert _iso(d) == c["fwd_diag"]["sessions"] and _iso(g) == c["fwd_gate"]["sessions"]


def test_runner_segments_match_the_adopted_amendment():
    ids = AMENDMENT["ids"]["experiments"]
    for seg_id, key in (("fwd-diag", "fwd_diag"), ("fwd-gate", "fwd_gate")):
        seg, cal = rn.SEGMENTS[seg_id], AMENDMENT["calendar"][key]
        assert (seg["first"].isoformat(), seg["last"].isoformat(), seg["sessions"]) == (cal["first"], cal["last"], cal["count"])
        assert seg["inputs_before"] == cal["inputs_before_from_stage_f_start"]
        assert seg["families"] == ("V2-MOM",) and seg["experiment"] == ids[seg_id]
    assert rn.SEGMENTS["fwd-gate"]["status_prefix"] == "FORWARD42" and rn.SEGMENTS["fwd-diag"]["kind"] == "diagnostic"


# ------------------------------------------------------------------ access gates

@pytest.mark.parametrize("seg_id,day", [("fwd-diag", date(2026, 11, 5)), ("fwd-gate", date(2027, 1, 7))])
def test_time_gate_is_exact(seg_id, day):
    with pytest.raises(fw.ForwardAccessRefused):
        fw.check_time(seg_id, datetime(day.year, day.month, day.day, 16, 14, 59, tzinfo=NY))
    fw.check_time(seg_id, datetime(day.year, day.month, day.day, 16, 15, tzinfo=NY))


def test_gate_is_closed_when_the_diagnostic_opens():
    with pytest.raises(fw.ForwardAccessRefused):
        fw.check_time("fwd-gate", datetime(2026, 11, 5, 16, 15, tzinfo=NY))
    with pytest.raises(fw.ForwardAccessRefused):
        fw.check_time("fwd-gate", datetime(2027, 1, 7, 9, 30, tzinfo=NY))


def test_adoption_date_refuses_both_segments():
    adopted = datetime.fromisoformat(json.loads((ROOT_DIR / fw.ADOPTION_JSON).read_text(encoding="utf-8"))["decided_utc"])
    for seg_id in ("fwd-diag", "fwd-gate"):
        with pytest.raises(fw.ForwardAccessRefused):
            fw.check_forward_access(seg_id, adopted)


def test_adoption_requires_commit_and_pinned_content(tmp_path):
    with pytest.raises(fw.ForwardAccessRefused, match="committed"):
        fw.check_adoption(git_ok=lambda *_a: False)
    assert fw.check_adoption(git_ok=lambda *_a: True)["adopted_files_sha256_lf"]
    for p in (fw.ADOPTION_JSON, *fw.AMENDMENT_FILES, *fw.INCIDENT_FILES):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT_DIR / p, tmp_path / p)
    assert fw.check_adoption(tmp_path, git_ok=lambda *_a: True)
    md = tmp_path / fw.AMENDMENT_FILES[0]
    md.write_bytes(md.read_bytes() + b"\nedited after adoption\n")
    with pytest.raises(fw.ForwardAccessRefused, match="adopted SHA-256"):
        fw.check_adoption(tmp_path, git_ok=lambda *_a: True)


@pytest.mark.parametrize("seg_id", ["fwd-diag", "fwd-gate"])
def test_runner_refuses_before_loading_anything(seg_id, monkeypatch, tmp_path, capsys):
    def boom(*_a, **_k):
        raise AssertionError("forward data loader reached")
    monkeypatch.setattr(rn, "load_stage_f", boom)
    monkeypatch.setattr(fw, "check_adoption", lambda *a, **k: {})            # isolate the time gate
    real = fw.check_forward_access
    before_end = datetime(2027, 1, 7, 16, 14, tzinfo=NY)                     # each segment: one minute before its end
    monkeypatch.setattr(fw, "check_forward_access",
                        lambda s, now=None: real(s, before_end if s == "fwd-gate" else datetime(2026, 11, 5, 16, 14, tzinfo=NY)))
    out = tmp_path / "out"
    rc = rn.main(["--segment", seg_id, "--out", str(out), "--snapshot", "x", "--expect-manifest-sha256", "y",
                  "--authorization", "test"])
    assert rc == 2 and not out.exists() and "REFUSED" in capsys.readouterr().err


def test_runner_requires_authorization_for_forward(tmp_path, capsys):
    assert rn.main(["--segment", "fwd-diag", "--out", str(tmp_path / "o")]) == 2
    assert "authorization" in capsys.readouterr().err


def test_stage_f_capture_and_validate_refuse_before_any_client(monkeypatch, tmp_path):
    def no_client():
        raise AssertionError("HTTP client constructed")
    late = datetime(2027, 1, 8, tzinfo=NY)
    with pytest.raises(fw.ForwardAccessRefused):                     # too early
        sf.capture("fwd-gate", http_factory=no_client, env={}, root=tmp_path, now=datetime(2027, 1, 7, 16, 0, tzinfo=NY))

    def not_adopted(*_a, **_k):
        raise fw.ForwardAccessRefused("not committed")
    monkeypatch.setattr(fw, "check_adoption", not_adopted)
    with pytest.raises(fw.ForwardAccessRefused):                     # time ok, adoption not committed
        sf.capture("fwd-gate", http_factory=no_client, env={}, root=tmp_path, now=late)
    with pytest.raises(fw.ForwardAccessRefused):
        sf.validate("fwd-gate", "stage_f_fwd-gate_x", "sha", tmp_path / "v", root=tmp_path, now=late)
    monkeypatch.setattr(sf, "check_forward_access", lambda *_a, **_k: {})
    (tmp_path / "stage_f_fwd-gate_20270107T220000Z").mkdir()
    with pytest.raises(FileExistsError, match="acquired once"):     # write-once: one acquisition per segment
        sf.capture("fwd-gate", http_factory=no_client, env={}, root=tmp_path, now=late)


def test_stage_f_request_bounds():
    d, g = sf.params("fwd-diag"), sf.params("fwd-gate")
    assert d["range"] == (date(2025, 1, 2), date(2026, 11, 5)) and g["range"] == (date(2025, 1, 2), date(2027, 1, 7))
    assert d["event_max"] < g["segment_first"].isoformat() and d["ca_windows"]["Q1"][1] == "2026-11-05"
    assert (d["asof"], g["asof"]) == ("2026-11-05", "2027-01-07")


def test_loader_is_gated_and_requires_a_ready_validation(monkeypatch, tmp_path):
    with pytest.raises(fw.ForwardAccessRefused):
        dt.load_stage_f("fwd-diag", "stage_f_fwd-diag_x", "sha", root=tmp_path,
                        now=datetime(2026, 11, 5, 16, 0, tzinfo=NY))
    monkeypatch.setattr(dt, "check_forward_access", lambda *_a, **_k: {})
    with pytest.raises(Exception):                                   # no snapshot / validation: never loads
        dt.load_stage_f("fwd-diag", "stage_f_fwd-diag_x", "sha", root=tmp_path)


# ------------------------------------------------------------------ separation of samples (synthetic data)

def _synthetic(seed: int = 7) -> dt.MarketData:
    sessions = tuple(stage_f_sessions(date(2027, 1, 7)))
    tickers = tuple(sorted(FROZEN_DAY_UNIVERSE)) + ("SPY",)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, (len(sessions), len(tickers))), axis=0))
    opn = close * np.exp(rng.normal(0, 0.003, close.shape))
    return dt.MarketData(sessions, tickers, opn, close, np.ones(close.shape), np.zeros(close.shape))


def _runs(data, seg_id, cost=0.0005):
    st = rn.Setup(data, rn.SEGMENTS[seg_id])
    return st, {f: rn.run_family(st, f, cost) for f in ("V2-MOM", "B1", "B2")}


def test_each_segment_simulates_only_its_own_sessions():
    data = _synthetic()
    split = fw.forward_split()
    for seg_id in ("fwd-diag", "fwd-gate"):
        st, res = _runs(data, seg_id)
        seg = rn.SEGMENTS[seg_id]
        assert st.seg_first == seg["inputs_before"] and st.seg_last - st.seg_first + 1 == seg["sessions"]
        for r in res.values():
            assert r.sessions == _iso(split[seg_id])
            assert all(split[seg_id][0].isoformat() <= f["session"] <= split[seg_id][-1].isoformat() for f in r.fills)
        m = mt.compute(res["V2-MOM"], res["B1"], res["B2"])
        assert m["sessions"] == seg["sessions"]
    st, _ = _runs(data, "fwd-gate")
    assert _iso(data.sessions[i] for i in st.month) == ["2026-11-05", "2026-11-30", "2026-12-31"]
    st, _ = _runs(data, "fwd-diag")
    assert _iso(data.sessions[i] for i in st.month) == ["2026-10-07", "2026-10-30"]


def test_diagnostic_never_depends_on_gate_period_data():
    data = _synthetic()
    _, base = _runs(data, "fwd-diag")
    k = data.index_of(date(2026, 11, 6))
    op, cl = data.open.copy(), data.close.copy()
    op[k:] *= 3.0
    cl[k:] *= 0.2
    _, moved = _runs(dt.MarketData(data.sessions, data.tickers, op, cl, data.q, data.d), "fwd-diag")
    for f in base:
        assert base[f].equity == moved[f].equity and base[f].fills == moved[f].fills


def test_diagnostic_report_is_descriptive_and_can_only_report_the_breach():
    data = _synthetic()
    metrics = {}
    for c, s in rn.COSTS.items():
        _, res = _runs(data, "fwd-diag", s)
        metrics[c] = {"V2-MOM": mt.compute(res["V2-MOM"], res["B1"], res["B2"]),
                      "B1": mt.compute(res["B1"], None, None), "B2": mt.compute(res["B2"], None, None)}
    gate_a = {k: True for k in ("look_ahead_tests_pass", "data_integrity", "deterministic",
                                "reproducibility_block_complete", "execution_accounting_semantics", "complete_dataset")}
    rep = fw.diagnostic_report(metrics, gate_a, {"missing_bars": 0})
    assert rep["status"] == "FWD-DIAG-INVALID (protocol-breach)" and rep["thresholds"] is None and rep["descriptive_only"]
    need = {"total_return", "active_total_return_vs_b1", "active_total_return_vs_b2", "max_drawdown", "turnover_total",
            "executions", "mean_lambda", "total_costs", "cost_drag_total_return", "top2_concentration", "weight_hhi",
            "symbol_breadth", "exposure"}
    for c in rn.COSTS:
        assert need <= set(rep["per_cost"][c]) and not any("cagr" in k for k in rep["per_cost"][c])
    assert rep["per_cost"]["0bps"]["cost_drag_total_return"] == 0.0
    bad = fw.diagnostic_report(metrics, dict(gate_a, complete_dataset=False), {})
    assert bad["status"] == "FWD-DIAG-INVALID (protocol-breach)" and bad["other_failed_checks"]["data"] == ["complete_dataset"]
    bad = fw.diagnostic_report(metrics, dict(gate_a, deterministic=False), {})
    assert bad["other_failed_checks"]["methodological"] == ["deterministic"]
