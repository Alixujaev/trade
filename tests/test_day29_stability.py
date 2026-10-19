"""tests/test_day29_stability.py: DAY-29 implementation (scripts/day29_stability.py), synthetic data only.

Synthetic input trees are built in tmp_path with the frozen engine on random prices and written byte-for-byte like
backtest/v2/run.py (equity.csv, fills.csv, decisions/episodes/executions/metrics.json, run_summary pins, provenance).
No DAY-19/DAY-21 input, snapshot or market data is read and no DAY-29 diagnostic is computed on real data. The only real
file read is the committed frozen DAY-29 predeclaration (document gate).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from acquisition.v2.sessions import stage_r_sessions
from backtest.v2 import metrics as mt
from backtest.v2.data import MarketData
from backtest.v2.run import Setup, _csv, _dump, run_family
from scripts import day29_stability as d29

SESS = tuple(stage_r_sessions())
TICK = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH")
SEGS = {"syn_a": (300, 379), "syn_b": (440, 559)}             # syn_a starts mid-month (partial first month)
COSTS = {"5bps": 0.0005, "10bps": 0.0010}


def make_data(n=560, seed=11):
    rs = np.random.default_rng(seed)            # fixture generation only
    m = len(TICK) + 1
    c = np.cumprod(1 + rs.normal(0.0005, 0.015, (n, m)), axis=0) * 50
    o = c * (1 + rs.normal(0, 0.003, (n, m)))
    return MarketData(SESS[:n], TICK + ("SPY",), o, c, np.ones((n, m)), np.zeros((n, m)))


def _write_run(d: Path, res) -> dict:
    """The six result files exactly as backtest/v2/run.py:359-373 writes them; returns {name: raw sha}."""
    return {
        "decisions.json": _dump(d / "decisions.json", res.decisions),
        "executions.json": _dump(d / "executions.json", res.executions),
        "episodes.json": _dump(d / "episodes.json", res.episodes),
        "fills.csv": _csv(d / "fills.csv", ["session", "ticker", "side", "shares", "price", "notional", "cost", "lambda",
                                            "slot"],
                          [[f["session"], f["ticker"], f["side"], f["shares"], f["price"], f["notional"], f["cost"],
                            f.get("lambda"), f.get("slot")] for f in res.fills]),
        "equity.csv": _csv(d / "equity.csv", ["session", "equity", "exposure", "n_held"],
                           [[s, e, x, n] for s, e, x, n in zip(res.sessions, res.equity, res.exposure, res.n_held)]),
    }


def build_tree(root: Path) -> d29.Spec:
    data = make_data()
    segs = []
    for sid, (a, b) in SEGS.items():
        st = Setup(data, {"id": sid, "first": SESS[a], "last": SESS[b]})
        run_dir, mom, b1 = f"syn/{sid}/v2", f"MOM-{sid}", f"B1-{sid}"
        files = {}
        for c, s in COSTS.items():
            rm, rb = run_family(st, "V2-MOM", s), run_family(st, "B1", s)
            for exp, res, met in ((mom, rm, mt.compute(rm, rb, None)), (b1, rb, mt.compute(rb, None, None))):
                d = root / run_dir / exp / c
                for name, sha in _write_run(d, res).items():
                    files[f"{exp}/{c}/{name}"] = sha
                files[f"{exp}/{c}/metrics.json"] = _dump(d / "metrics.json", met)
        n = b - a + 1
        summary = {"segment": {"id": sid, "first": SESS[a].isoformat(), "last": SESS[b].isoformat(), "sessions": n},
                   "decision_counts": {"V2-MOM": len(st.month)}, "result_files_sha256": files}
        sha = _dump(root / run_dir / "run_summary.json", summary)
        _dump(root / run_dir / "run_provenance.json", {"run_summary_sha256": sha})
        segs.append(d29.Segment(sid, run_dir, SESS[a].isoformat(), SESS[b].isoformat(), n, mom, b1))
    k1 = []
    pins = {}
    for name in ("d1.json", "d2.json", "d5.json"):
        sha = _dump(root / "k1" / name, {"synthetic": name})
        k1.append((f"k1/{name}", sha))
        pins[name] = sha
    _dump(root / "k1" / "run_summary.json", {"result_files_sha256": pins})
    return d29.Spec(segments=tuple(segs), k1_files=tuple(k1), k1_pins="k1/run_summary.json")


@pytest.fixture
def env(tmp_path):
    spec = build_tree(tmp_path)
    return SimpleNamespace(root=tmp_path, spec=spec, out=tmp_path / "out" / "run",
                           record=tmp_path / "out" / "preflight" / "shared_integrity_record.json")


def repin(root: Path, spec: d29.Spec, rel: str):
    """After a deliberate edit, refresh the run_summary pin and provenance so only the targeted check can fail."""
    seg = next(s for s in spec.segments if rel.startswith(s.run_dir + "/"))
    sp = root / seg.run_dir / "run_summary.json"
    summary = json.loads(sp.read_bytes())
    summary["result_files_sha256"][rel[len(seg.run_dir) + 1:]] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    sha = _dump(sp, summary)
    _dump(root / seg.run_dir / "run_provenance.json", {"run_summary_sha256": sha})


def _rel(spec, sid, which, cost, name):
    seg = next(s for s in spec.segments if s.id == sid)
    return f"{seg.run_dir}/{seg.mom if which == 'mom' else seg.b1}/{cost}/{name}"


def _load(out: Path, rel: str) -> dict:
    return json.loads((out / rel).read_bytes())


# ================================================================ frozen document gate

def test_frozen_document_hash_and_frozen_spec_match_the_document():
    assert d29.verify_frozen_doc() == d29.FROZEN_DOC_LF_SHA256
    text = (d29.ROOT_DIR / d29.FROZEN_MD).read_text(encoding="utf-8")
    for seg in d29.FROZEN_SPEC.segments:
        for e in (seg.mom, seg.b1):
            assert f"{seg.run_dir}/{e}/5bps/" in text and f"{seg.run_dir}/{e}/10bps/" in text
        assert seg.first in text and seg.last in text and f"{seg.sessions:,}" in text
    for path, sha in d29.FROZEN_SPEC.k1_files:
        assert path in text and sha in text
    assert "`k ∈ {5, 10, 20}`" in text and d29.FROZEN_SPEC.ks == (5, 10, 20)
    assert "`exchange_calendars==4.13.2`" in text and d29.FROZEN_SPEC.calendar_version == "4.13.2"
    assert d29.EVIDENCE_LABEL in text and d29.COST_LABELS["10bps"] in text


def test_doc_gate_rejects_a_changed_document(tmp_path):
    (tmp_path / d29.FROZEN_MD).parent.mkdir(parents=True)
    (tmp_path / d29.FROZEN_MD).write_bytes((d29.ROOT_DIR / d29.FROZEN_MD).read_bytes() + b" ")
    with pytest.raises(d29.Day29Error, match="changed"):
        d29.verify_frozen_doc(tmp_path)


# ================================================================ end to end (synthetic)

def test_end_to_end_synthetic_outputs_labels_and_pins(env):
    summary = d29.run(env.root, env.spec, env.out, env.record, "test-authorization")
    assert summary["status"] == "COMPLETED" and summary["blocked_diagnostics"] == []
    names = sorted(str(p.relative_to(env.out)).replace("\\", "/") for p in env.out.rglob("*.json"))
    assert names == ["10bps/k2.json", "10bps/k3.json", "10bps/t0.json", "10bps/t1.json", "10bps/t2.json", "10bps/t3.json",
                     "5bps/k2.json", "5bps/k3.json", "5bps/t0.json", "5bps/t1.json", "5bps/t2.json", "5bps/t3.json",
                     "k1.json", "run_summary.json"]
    for rel, sha in summary["result_files_sha256"].items():
        assert hashlib.sha256((env.out / rel).read_bytes()).hexdigest() == sha
    assert _load(env.out, "5bps/t0.json")["cost_label"] == "primary analysis (5 bps)"
    assert _load(env.out, "10bps/t1.json")["cost_label"] == "secondary cost sensitivity (10 bps) — not primary evidence"
    assert _load(env.out, "5bps/k2.json")["family_scope"] == "V2-MOM only"
    assert all(r["matches"] for r in _load(env.out, "k1.json")["results"]["citations"])
    rec = json.loads(env.record.read_bytes())
    assert rec["status"] == "PASSED" and rec["authorizes_diagnostics"] is False and set(rec["checks"]) == {
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"}
    blob = "".join(p.read_text(encoding="utf-8") for p in env.out.rglob("*.json")).lower()
    assert '"pass"' not in blob and '"fail"' not in blob and "threshold" not in blob and "p_value" not in blob


def test_t0_copies_cagr_from_metrics_and_t3_keeps_partial_months(env):
    d29.run(env.root, env.spec, env.out, env.record, "auth")
    t0 = _load(env.out, "5bps/t0.json")["results"]["syn_a"]
    met = json.loads((env.root / _rel(env.spec, "syn_a", "mom", "5bps", "metrics.json")).read_bytes())
    assert t0["cagr_copied"]["V2-MOM"]["value"] == met["cagr"] and t0["N"] == 80
    t3 = _load(env.out, "5bps/t3.json")["results"]["syn_a"]
    assert sum(r["n_sessions"] for r in t3["rows"]) == 80
    assert t3["rows"][0]["label"].startswith("partial (")                  # syn_a starts mid-month
    assert all(r["active"] == r["r_mom"] - r["r_b1"] for r in t3["rows"])


# ================================================================ calculation units

def test_float_cells_are_read_exactly_in_both_run_py_forms():
    x = float(np.float64(99774.33089973251) * 1.0000001)
    assert d29._float_cell(repr(np.float64(x))) == x and d29._float_cell(repr(x)) == x   # np.float64(...) and plain
    for good in ("-0.0", "1e-05", "1.5e+20", "np.float64(100000.0)", "np.float64(-3.25e-07)"):
        assert d29._float_cell(good) == float(good.removeprefix("np.float64(").removesuffix(")"))
    for bad in ("", " 1.0", "nan", "inf", "-inf", "np.float64(nan)", "np.float64(nan", "np.float64( 1.0)",
                "float(1.0)", "1_000.5", "+1.0", "1.", ".5", "1E5", "np.float32(1.0)"):
        with pytest.raises(ValueError):
            d29._float_cell(bad)


def test_t1_ties_break_by_ascending_date_and_insufficient_observations():
    sessions = [f"2020-01-{d:02d}" for d in range(2, 12)]
    l = np.array([0.0, 0.3, -0.2, 0.3, 0.1, -0.2, 0.0, 0.05, -0.1, 0.3])
    best, worst = d29.tail_sets(l, sessions, 3)
    assert [sessions[i] for i in best] == ["2020-01-03", "2020-01-05", "2020-01-11"]
    assert [sessions[i] for i in worst] == ["2020-01-04", "2020-01-07", "2020-01-10"]
    out = d29.t1(l, sessions, (3, 5, 6))
    assert out["counts"] == {"N": 10, "n_pos": 5, "n_zero": 2, "n_neg": 3, "share_positive_days": 0.5,
                             "share_denominator": "N (all aligned sessions, zero-active days included)",
                             "L_context_only": out["counts"]["L_context_only"]}
    assert out["by_k"]["6"] == {"undefined": "insufficient observations: N < 2k"}
    assert out["by_k"]["5"]["best"]["sum_l"] == pytest.approx(0.3 * 3 + 0.1 + 0.05)


def test_t2_is_the_day25b_d4c_formula_on_the_remaining_sessions():
    rs = np.random.default_rng(3)
    r_m, r_b = rs.normal(0, 0.01, 50), rs.normal(0, 0.01, 50)
    sessions = [f"S{i:03d}" for i in range(50)]
    l = np.log(1 + r_m) - np.log(1 + r_b)
    out = d29.t2(l, sessions, r_m, r_b, (5,), {"V2-MOM": {"value": 0.1}, "B1": {"value": 0.2}})
    best = d29.tail_sets(l, sessions, 5)[0]
    keep = np.ones(50, dtype=bool)
    keep[best] = False
    exp_m = float(np.prod(1 + r_m[keep]) ** (252 / 45) - 1)              # scripts/day25b_robustness.py:458
    got = out["by_k"]["5"]["best_removed"]
    assert got["sessions_remaining"] == 45 and got["cagr_excl"]["V2-MOM"] == exp_m
    assert got["active_cagr"] == got["cagr_excl"]["V2-MOM"] - got["cagr_excl"]["B1"]
    assert out["unremoved_t0_cagr_copied"] == {"V2-MOM": 0.1, "B1": 0.2} and len(out["disclosures"]) == 4


def test_k2_interval_convention_normal_and_segment_end():
    sessions = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    eps = [{"ticker": "AAA", "start": "2020-01-02", "end": "2020-01-06", "seg_end": False},
           {"ticker": "BBB", "start": "2020-01-06", "end": "2020-01-07", "seg_end": True}]
    held = d29.held_sets(eps, sessions)
    assert held["2020-01-03"] == {"AAA"} and held["2020-01-06"] == {"BBB"}      # sold at the open of its end session
    assert held["2020-01-07"] == {"BBB"}                                         # segment end: open at the last close


def test_k3_uses_only_decisions_dated_strictly_before_the_session():
    dec = [{"close": "2020-01-02", "targets": {"AAA": 0.5, "BBB": 0.5}},
           {"close": "2020-01-06", "targets": {"CCC": 1.0, "DDD": 0.0}}]
    assert d29.target_holdings(dec, "2020-01-06") == {"AAA", "BBB"}            # same-day decision not yet executed
    assert d29.target_holdings(dec, "2020-01-07") == {"CCC"}                   # weight 0 is not a selection
    assert d29.target_holdings(dec, "2020-01-02") == {"undefined": "no prior decision"}


def test_reporting_sessions_are_the_scheduled_execution_sessions(env):
    cal = d29.Calendar("4.13.2")
    seg = env.spec.segments[1]
    sessions = cal.sessions(seg.first, seg.last)
    picked = d29.reporting_sessions(sessions, cal)
    dec = json.loads((env.root / _rel(env.spec, seg.id, "mom", "5bps", "decisions.json")).read_bytes())
    executions_after_decisions = {cal.next_session(d["close"]) for d in dec}
    assert set(picked) == executions_after_decisions | {sessions[-1]}         # calendar rule = engine schedule


# ================================================================ shared stage: whole-run abort (frozen §4, §7)

def _tamper_byte(env):
    p = env.root / _rel(env.spec, "syn_b", "b1", "10bps", "fills.csv")
    b = bytearray(p.read_bytes())
    b[-2] ^= 1
    p.write_bytes(bytes(b))


def _crlf(env):
    p = env.root / _rel(env.spec, "syn_a", "mom", "5bps", "equity.csv")
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))


def _provenance(env):
    p = env.root / env.spec.segments[0].run_dir / "run_provenance.json"
    _dump(p, {"run_summary_sha256": "0" * 64})


def _segment_def(env):
    seg = env.spec.segments[0]
    sp = env.root / seg.run_dir / "run_summary.json"
    s = json.loads(sp.read_bytes())
    s["segment"]["sessions"] += 1
    _dump(env.root / seg.run_dir / "run_provenance.json", {"run_summary_sha256": _dump(sp, s)})


def _duplicate_date(env):
    rel = _rel(env.spec, "syn_a", "b1", "5bps", "equity.csv")
    lines = (env.root / rel).read_bytes().split(b"\n")
    lines[3] = lines[2].split(b",")[0] + b"," + b",".join(lines[3].split(b",")[1:])
    (env.root / rel).write_bytes(b"\n".join(lines))
    repin(env.root, env.spec, rel)


def _ending_equity(env):
    rel = _rel(env.spec, "syn_b", "mom", "10bps", "metrics.json")
    m = json.loads((env.root / rel).read_bytes())
    m["ending_equity"] = float(np.nextafter(m["ending_equity"], np.inf))     # one ULP: exact equality must catch it
    _dump(env.root / rel, m)
    repin(env.root, env.spec, rel)


@pytest.mark.parametrize("damage,check", [(_tamper_byte, "S1"), (_crlf, "S1"), (_provenance, "S2"),
                                          (_segment_def, "S3"), (_duplicate_date, "S4"), (_ending_equity, "S8")])
def test_shared_failure_aborts_whole_run_and_writes_only_the_record(env, damage, check):
    damage(env)
    with pytest.raises(d29.SharedIntegrityAbort, match=check):
        d29.run(env.root, env.spec, env.out, env.record, "auth")
    assert not env.out.exists() and not list(env.out.parent.glob(".run.tmp-*"))
    rec = json.loads(env.record.read_bytes())
    assert rec["status"] == "ABORTED_SHARED_INTEGRITY" and rec["failed_check"] == check


@pytest.mark.parametrize("module", [SimpleNamespace(__version__="4.14.0"), None])
def test_calendar_version_other_than_4_13_2_or_missing_aborts(env, monkeypatch, module):
    def fake():
        if module is None:
            raise ImportError("No module named 'exchange_calendars'")
        return module
    monkeypatch.setattr(d29, "_import_calendar", fake)
    with pytest.raises(d29.SharedIntegrityAbort, match="S6"):
        d29.run(env.root, env.spec, env.out, env.record, "auth")
    rec = json.loads(env.record.read_bytes())
    assert rec["failed_check"] == "S6" and not env.out.exists()


def test_reads_outside_the_allow_list_are_refused(env):
    with pytest.raises(d29._CheckFailed) as e:
        d29.Reader(env.root, env.spec).read("syn/syn_a/v2/MOM-syn_a/0bps/equity.csv")
    assert e.value.check == "S9"


def test_determinism_failure_aborts_with_no_output(env, monkeypatch):
    real, calls = d29.compute_diagnostics, []

    def flaky(*a, **k):
        calls.append(1)
        out, blocked = real(*a, **k)
        if len(calls) == 2:
            out["5bps"]["t1"]["syn_a"]["counts"]["n_pos"] += 1
        return out, blocked
    monkeypatch.setattr(d29, "compute_diagnostics", flaky)
    with pytest.raises(d29.SharedIntegrityAbort, match="S10"):
        d29.run(env.root, env.spec, env.out, env.record, "auth")
    assert not env.out.exists() and json.loads(env.record.read_bytes())["failed_check"] == "S10"


# ================================================================ K2/K3 blocking scope (frozen §6, §7)

def test_k2_c3_failure_blocks_k2_only_and_only_that_unit(env):
    rel = _rel(env.spec, "syn_a", "mom", "10bps", "metrics.json")
    m = json.loads((env.root / rel).read_bytes())
    m["position_episodes"] += 1
    _dump(env.root / rel, m)
    repin(env.root, env.spec, rel)
    s = d29.run(env.root, env.spec, env.out, env.record, "auth")
    assert s["status"] == "COMPLETED_WITH_BLOCKED_DIAGNOSTICS"
    assert s["blocked_diagnostics"] == [{"diagnostic": "K2", "segment": "syn_a", "cost": "10bps", "failed": ["K2-C3"]}]
    assert _load(env.out, "10bps/k2.json")["results"]["syn_a"]["status"] == "BLOCKED"
    assert _load(env.out, "10bps/k3.json")["results"]["syn_a"]["status"] == "COMPLETED"   # no automatic cascade
    assert _load(env.out, "5bps/k2.json")["results"]["syn_a"]["status"] == "COMPLETED"
    assert "by_k" in _load(env.out, "10bps/t1.json")["results"]["syn_a"]


def test_k2_c2_failure_blocks_k2_and_k3_because_k3_reads_the_same_episodes(env):
    rel = _rel(env.spec, "syn_b", "mom", "5bps", "equity.csv")
    lines = (env.root / rel).read_bytes().split(b"\n")
    parts = lines[5].split(b",")
    parts[3] = str(int(parts[3]) + 1).encode()
    lines[5] = b",".join(parts)
    (env.root / rel).write_bytes(b"\n".join(lines))
    repin(env.root, env.spec, rel)
    s = d29.run(env.root, env.spec, env.out, env.record, "auth")
    assert {(b["diagnostic"], b["failed"][0]) for b in s["blocked_diagnostics"]} == {("K2", "K2-C2"), ("K3", "K2-C2")}
    assert _load(env.out, "5bps/t0.json")["results"]["syn_b"]["N"] == 120


def test_k3_mismatch_blocks_k3_only_and_lists_the_mismatch(env):
    rel = _rel(env.spec, "syn_b", "mom", "5bps", "decisions.json")
    dec = json.loads((env.root / rel).read_bytes())
    held_now = set(dec[1]["targets"])
    extra = next(t for t in TICK if t not in held_now)
    dec[1]["targets"][extra] = 0.01                                              # target never executed
    _dump(env.root / rel, dec)
    repin(env.root, env.spec, rel)
    s = d29.run(env.root, env.spec, env.out, env.record, "auth")
    assert s["blocked_diagnostics"] == [{"diagnostic": "K3", "segment": "syn_b", "cost": "5bps",
                                         "failed": ["K3 T(s)=H(s)"]}]
    k3 = _load(env.out, "5bps/k3.json")["results"]["syn_b"]
    assert k3["status"] == "BLOCKED" and k3["mismatch_count"] > 0 and "reporting_sessions" not in k3
    assert {m["ticker"] for m in k3["mismatches"]} == {extra} and k3["mismatches"][0]["direction"] == "in T only"
    assert _load(env.out, "5bps/k2.json")["results"]["syn_b"]["status"] == "COMPLETED"


# ================================================================ refusals

def test_run_refuses_missing_authorization_existing_output_and_existing_record(env):
    with pytest.raises(d29.Day29Error, match="authorization"):
        d29.run(env.root, env.spec, env.out, env.record, " ")
    env.out.mkdir(parents=True)
    with pytest.raises(d29.Day29Error, match="already exists"):
        d29.run(env.root, env.spec, env.out, env.record, "auth")
    env.out.rmdir()
    env.record.parent.mkdir(parents=True)
    env.record.write_text("{}", encoding="utf-8")
    with pytest.raises(d29.Day29Error, match="write-once"):
        d29.run(env.root, env.spec, env.out, env.record, "auth")


def test_cli_without_authorization_refuses_before_reading_anything(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("nothing may be read")
    monkeypatch.setattr(d29, "run", boom)
    monkeypatch.setattr(d29, "verify_frozen_doc", boom)
    assert d29.main([]) == 2 and d29.main(["--authorization", "  "]) == 2
