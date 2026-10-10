"""tests/test_day25b_robustness.py: DAY-25B implementation (scripts/day25b_robustness.py), synthetic data only.

No snapshot or market data is read and no DAY-25B diagnostic is run on real data (sockets blocked by conftest).
The only real files read are the committed frozen DAY-25B documents and the frozen protocol JSON (gate tests).
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import numpy as np
import pytest

from acquisition.v2.sessions import stage_r_sessions
from backtest.v2 import metrics as mt
from backtest.v2.data import MarketData
from backtest.v2.run import Setup, _dump, environment, run_family
from scripts import day25b_robustness as d25

SESS = tuple(stage_r_sessions())
TICK = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH")
SEGS = {"syn_a": (260, 339), "syn_b": (440, 559)}             # syn_a: one calendar year; syn_b spans 2017/2018


def make_data(n=560, seed=7, nan_open=None):
    rs = np.random.default_rng(seed)            # fixture generation only; the engine uses no randomness
    m = len(TICK) + 1
    c = np.cumprod(1 + rs.normal(0.0005, 0.015, (n, m)), axis=0) * 50
    o = c * (1 + rs.normal(0, 0.003, (n, m)))
    if nan_open is not None:
        o[nan_open[0], nan_open[1]] = np.nan
    return MarketData(SESS[:n], TICK + ("SPY",), o, c, np.ones((n, m)), np.zeros((n, m)))


def make_contexts(data=None):
    data = data or make_data()
    return {sid: Setup(data, {"id": sid, "first": SESS[a], "last": SESS[b]}) for sid, (a, b) in SEGS.items()}


def make_spec(ref_env="0" * 64):
    labels = {sid: {y: ("synthetic", n) for y, n in Counter(s.isoformat()[:4] for s in SESS[a:b + 1]).items()}
              for sid, (a, b) in SEGS.items()}
    refs = {sid: {f: f"ref/{sid}/{f}" for f in d25.PORTFOLIOS} for sid in SEGS}
    return d25.Spec(universe=TICK, subset_size=6, subset_count=5, window=20, step=7,
                    year_labels=labels, references=refs, reference_env_sha256=ref_env)


def write_references(root: Path, contexts, spec):
    """Reference metrics.json written exactly like backtest/v2/run.py (run_family + metrics.compute + _dump)."""
    for sid, st in contexts.items():
        for c, s in spec.d6_frozen.items():
            res = {f: run_family(st, f, s) for f in d25.PORTFOLIOS}
            m = {"V2-MOM": mt.compute(res["V2-MOM"], res["B1"], res["B2"]),
                 "B1": mt.compute(res["B1"], None, None), "B2": mt.compute(res["B2"], None, None)}
            for f in d25.PORTFOLIOS:
                _dump(root / spec.references[sid][f] / c / "metrics.json", m[f])


@pytest.fixture
def env(tmp_path):
    contexts, spec = make_contexts(), make_spec()
    write_references(tmp_path, contexts, spec)
    return SimpleNamespace(root=tmp_path, contexts=contexts, spec=spec,
                           record=tmp_path / "preflight" / "preflight_record.json", out=tmp_path / "run")


def _perturb(root: Path, rel: str, field: str):
    p = root / rel
    m = json.loads(p.read_text(encoding="utf-8"))
    m[field] = float(np.nextafter(m[field], np.inf))          # one ULP: exact equality must catch it
    _dump(p, m)


# ================================================================ gates on the committed frozen documents

def test_frozen_documents_json_parameters_and_config_sha():
    got = d25.verify_frozen_docs()
    assert got == d25.FROZEN_DOC_SHA256
    d25.verify_frozen_json()
    assert d25.assert_config_sha() == "62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0"
    assert d25.FROZEN_SPEC.universe == tuple(sorted(d25.FROZEN_SPEC.universe)) and len(d25.FROZEN_SPEC.universe) == 25


def test_doc_sha_is_line_ending_invariant(tmp_path):
    lf, crlf = tmp_path / "lf.md", tmp_path / "crlf.md"
    lf.write_bytes(b"a\nb\n")
    crlf.write_bytes(b"a\r\nb\r\n")
    assert d25.doc_sha256(lf) == d25.doc_sha256(crlf)


# ================================================================ D3 subset generator

def test_subsets_frozen_algorithm_is_reproducible_and_matches_independent_reimplementation():
    u = d25.FROZEN_SPEC.universe
    subs, disc = d25.generate_subsets(u, 20261008, 20, 300)
    assert (subs, disc) == d25.generate_subsets(u, 20261008, 20, 300)
    assert len(subs) == 300 and len({frozenset(s) for s in subs}) == 300
    assert all(len(s) == 20 and list(s) == sorted(s, key=u.index) for s in subs)
    bg = np.random.PCG64(20261008)                              # independent: vectorised uint64 draws
    ref, seen = [], set()
    while len(ref) < 300:
        keys = [int(x) for x in bg.random_raw(25)]
        sub = tuple(u[i] for i in sorted(sorted(range(25), key=lambda i: (keys[i], i))[:20]))
        if frozenset(sub) not in seen:
            seen.add(frozenset(sub))
            ref.append(sub)
    assert ref == subs


def test_subset_keys_are_compared_unsigned_not_signed():
    u = d25.FROZEN_SPEC.universe
    subs, _ = d25.generate_subsets(u, 20261008, 20, 50)
    bg = np.random.PCG64(20261008)
    signed_subs, high_key_seen = [], False
    for _ in range(50):
        raw = bg.random_raw(25)
        high_key_seen |= bool((raw >= np.uint64(2 ** 63)).any())
        sk = raw.astype(np.int64)                                # the forbidden signed interpretation
        signed_subs.append(tuple(u[i] for i in sorted(sorted(range(25), key=lambda i: (int(sk[i]), i))[:20])))
    assert high_key_seen
    assert signed_subs != subs                                   # a signed cast would change the frozen subsets


def test_impossible_subset_spec_is_rejected():
    with pytest.raises(d25.Day25bError):
        d25.generate_subsets(TICK, 1, 9, 1)
    with pytest.raises(d25.Day25bError):
        d25.generate_subsets(TICK, 1, 7, 9)                      # C(8,7) = 8 < 9


# ================================================================ benchmark / primitive equivalence

def test_full_universe_primitives_equal_frozen_run_family():
    st = make_contexts()["syn_a"]
    for s in (0.0, 0.0005, 0.001):
        b1, b1s = run_family(st, "B1", s), d25.run_b1_sub(st, TICK, s)
        assert b1s.equity == b1.equity and b1s.fills == b1.fills
        mom, momf = d25.run_mom(st, TICK, s), run_family(st, "V2-MOM", s)
        assert mom.equity == momf.equity and mom.fills == momf.fills and mom.decisions == momf.decisions
        spy, b2 = d25.run_single(st, "SPY", s), run_family(st, "B2", s)
        assert spy.equity == b2.equity and spy.fills == b2.fills


def test_missing_first_open_single_is_undefined_and_b1_sub_still_matches_b1():
    data = make_data(nan_open=(260, 2))                          # CCC has no bar at syn_a's first open
    st = make_contexts(data)["syn_a"]
    assert d25.run_single(st, "CCC", 0.0005) is None
    assert d25.run_b1_sub(st, TICK, 0.0005).equity == run_family(st, "B1", 0.0005).equity


# ================================================================ D6 preflight gate

def test_preflight_pass_records_all_comparisons_and_fingerprint(env):
    runs = d25.preflight(env.contexts, env.spec, env.record, env.root)
    rec = json.loads(env.record.read_text(encoding="utf-8"))
    assert rec["status"] == "PASSED" and rec["comparisons_total"] == 2 * 3 * 3 * 2 and rec["mismatch_count"] == 0
    assert all(c["equal"] and c["reference"] == c["recomputed"] for c in rec["comparisons"])
    assert rec["environment"]["distributions_sha256"] == environment()["distributions_sha256"]
    assert rec["fingerprint_matches_reference"] is False and rec["fingerprint_relaxes_equality"] is False
    assert rec["authorizes_diagnostics"] is False and rec["run_status"] is None
    assert set(runs) == set(SEGS) and set(runs["syn_a"]) == {"0bps", "5bps", "10bps"}


def test_preflight_matching_fingerprint_is_recorded(env, tmp_path):
    spec = make_spec(ref_env=environment()["distributions_sha256"])
    d25.preflight(env.contexts, spec, tmp_path / "rec2.json", env.root)
    assert json.loads((tmp_path / "rec2.json").read_text(encoding="utf-8"))["fingerprint_matches_reference"] is True


@pytest.mark.parametrize("field", ["cagr", "ending_equity"])
@pytest.mark.parametrize("ref_env", ["0" * 64, None])           # None: fingerprint matches; still no relaxation
def test_preflight_mismatch_aborts_run_and_creates_no_diagnostics(env, field, ref_env):
    spec = make_spec(ref_env=ref_env or environment()["distributions_sha256"])
    _perturb(env.root, "ref/syn_b/B1/10bps/metrics.json", field)
    with pytest.raises(d25.PreflightMismatch):
        d25.run(env.contexts, spec, env.out, env.record, "test-authorization", env.root)
    assert not env.out.exists()
    assert not list(env.root.glob(".run.tmp-*"))
    rec = json.loads(env.record.read_text(encoding="utf-8"))
    assert rec["status"] == "FAILED" and rec["run_status"] == "ABORTED_PREFLIGHT_MISMATCH" and rec["mismatch_count"] == 1
    mm = rec["mismatches"][0]
    assert (mm["segment"], mm["cost"], mm["portfolio"], mm["field"]) == ("syn_b", "10bps", "B1", field)
    assert mm["reference"] != mm["recomputed"] and rec["fingerprint_relaxes_equality"] is False
    assert "distributions_sha256" in rec["environment"]


def test_preflight_record_is_write_once(env):
    d25.preflight(env.contexts, env.spec, env.record, env.root)
    with pytest.raises(d25.Day25bError, match="refusing to overwrite"):
        d25.preflight(env.contexts, env.spec, env.record, env.root)


@pytest.mark.parametrize("damage,cause", [("missing", FileNotFoundError), ("corrupt", json.JSONDecodeError)])
def test_preflight_exception_writes_failed_record_and_no_outputs(env, damage, cause):
    ref = env.root / "ref/syn_b/B2/10bps/metrics.json"           # the last reference read: 34 comparisons precede it
    if damage == "missing":
        ref.unlink()
    else:
        ref.write_text("{not json", encoding="utf-8")
    with pytest.raises(d25.PreflightMismatch) as ei:
        d25.run(env.contexts, env.spec, env.out, env.record, "test-authorization", env.root)
    assert isinstance(ei.value.__cause__, cause)
    rec = json.loads(env.record.read_text(encoding="utf-8"))
    assert rec["status"] == "FAILED" and rec["run_status"] == "ABORTED_PREFLIGHT_MISMATCH"
    assert rec["error"]["type"] == cause.__name__ and rec["error"]["message"]
    assert rec["comparisons_total"] == 34 and all(c["equal"] for c in rec["comparisons"])
    assert rec["environment"]["distributions_sha256"] == environment()["distributions_sha256"]
    assert rec["authorizes_diagnostics"] is False and rec["fingerprint_relaxes_equality"] is False
    assert not env.out.exists() and not list(env.root.glob(".run.tmp-*"))


def test_existing_record_not_overwritten_even_when_preflight_would_fail(env):
    env.record.parent.mkdir(parents=True)
    env.record.write_bytes(b'{"sentinel": true}\n')
    (env.root / "ref/syn_a/V2-MOM/0bps/metrics.json").unlink()
    with pytest.raises(d25.Day25bError, match="refusing to overwrite"):
        d25.run(env.contexts, env.spec, env.out, env.record, "test-authorization", env.root)
    assert env.record.read_bytes() == b'{"sentinel": true}\n'
    assert not env.out.exists()


# ================================================================ orchestration

def test_run_end_to_end_synthetic_writes_descriptive_outputs(env):
    summary = d25.run(env.contexts, env.spec, env.out, env.record, "test-authorization", env.root)
    names = sorted(p.name for p in env.out.iterdir())
    assert names == ["d1.json", "d2.json", "d3.json", "d4.json", "d5.json", "d6.json", "d7.json",
                     "run_summary.json", "subsets.json"]
    assert summary["status"] == "COMPLETED" and summary["descriptive_only"] and summary["determinism_in_process"]
    assert summary["preflight_record"]["path"] == str(env.record)
    for k in ("d1", "d2", "d3", "d4", "d5", "d6", "d7"):
        doc = json.loads((env.out / f"{k}.json").read_text(encoding="utf-8"))
        assert doc["evidence_label"] == d25.EVIDENCE_LABEL and doc["descriptive_only"] is True
        assert set(doc["results"]) == set(SEGS)
    d1 = json.loads((env.out / "d1.json").read_text(encoding="utf-8"))["results"]["syn_a"]
    assert set(d1) == {"5bps", "10bps"} and [r["dropped"] for r in d1["5bps"]["rows"]] == list(TICK)
    d3 = json.loads((env.out / "d3.json").read_text(encoding="utf-8"))["results"]["syn_b"]
    assert all(len(d3[c]["rows"]) == 5 for c in ("5bps", "10bps"))
    d6 = json.loads((env.out / "d6.json").read_text(encoding="utf-8"))["results"]["syn_a"]
    assert set(d6) == {"0bps", "5bps", "10bps", "15bps", "20bps"} and d6["0bps"]["cost_drag_vs_0bps"] == 0.0
    assert d6["15bps"]["role"] == d6["20bps"]["role"] == "diagnostic override"
    blob = "".join(p.read_text(encoding="utf-8") for p in env.out.iterdir()).lower()
    assert '"pass"' not in blob and '"fail"' not in blob and "threshold" not in blob


def test_run_refuses_existing_output_and_missing_authorization(env):
    env.out.mkdir()
    with pytest.raises(d25.Day25bError, match="already exists"):
        d25.run(env.contexts, env.spec, env.out, env.record, "auth", env.root)
    with pytest.raises(d25.Day25bError, match="authorization"):
        d25.run(env.contexts, env.spec, env.root / "other", env.record, "", env.root)
    assert not env.record.exists()                               # refused before the preflight


def test_determinism_failure_writes_no_output(env, monkeypatch):
    real, calls = d25.compute_diagnostics, []

    def flaky(*a, **k):
        calls.append(1)
        out = real(*a, **k)
        if len(calls) == 2:
            out["D5"]["syn_a"]["5bps"]["symbol_breadth"] = -1.0
        return out

    monkeypatch.setattr(d25, "compute_diagnostics", flaky)
    with pytest.raises(d25.Day25bError, match="determinism"):
        d25.run(env.contexts, env.spec, env.out, env.record, "auth", env.root)
    assert not env.out.exists()


def test_cli_without_authorization_refuses_before_loading_data(monkeypatch, tmp_path):
    def boom():
        raise AssertionError("data must not be loaded")
    monkeypatch.setattr(d25, "load_contexts", boom)
    assert d25.main(["--out", str(tmp_path / "x")]) == 2
    assert d25.main(["--preflight-only"]) == 2


@pytest.mark.parametrize("args", [
    ["--out", "{tmp}/x"],
    ["--preflight-record", "{tmp}/r.json"],
    ["--out", "artifacts/day25b/run/../elsewhere"],                # relative, resolves outside artifacts/day25b/run
    ["--preflight-only", "--preflight-record", "{tmp}/r.json"],
])
def test_cli_rejects_non_frozen_output_paths(monkeypatch, tmp_path, args):
    def boom(*_a, **_k):
        raise AssertionError("no gate or data loading may run for a rejected path")
    monkeypatch.setattr(d25, "load_contexts", boom)
    monkeypatch.setattr(d25, "verify_frozen_docs", boom)
    argv = [a.replace("{tmp}", str(tmp_path)) for a in args] + ["--authorization", "test-authorization"]
    assert d25.main(argv) == 2
    assert not (tmp_path / "x").exists() and not (tmp_path / "r.json").exists()
    assert not (d25.ROOT_DIR / "artifacts" / "day25b" / "elsewhere").exists()


def test_cli_accepts_frozen_default_paths_before_gates(monkeypatch):
    def stop(*_a, **_k):
        raise d25.Day25bError("stop after the path gate")

    def boom(*_a, **_k):
        raise AssertionError("data must not be loaded")
    monkeypatch.setattr(socket.socket, "connect", socket.socket.connect)    # main() patches it; restore at teardown
    monkeypatch.setattr(d25, "verify_frozen_docs", stop)
    monkeypatch.setattr(d25, "load_contexts", boom)
    assert d25.main(["--authorization", "test-authorization"]) == 1          # passed the path gate, stopped at gate 1
    assert d25.main(["--out", "artifacts/day25b/run", "--preflight-record",
                     "artifacts/day25b/preflight/preflight_record.json", "--authorization", "x"]) == 1


# ================================================================ diagnostic formulas

def test_d2_ranking_uses_abs_flows_ties_by_universe_order_and_absent_as_zero():
    spec = d25.Spec(universe=TICK)
    base = {"5bps": {"V2-MOM": SimpleNamespace(flows={"CCC": 10.0, "BBB": -10.0, "AAA": 3.0})}}
    top = d25.d2_ranking(spec, base)
    assert [(r["ticker"], r["signed_contribution"]) for r in top] == [("BBB", -10.0), ("CCC", 10.0)]
    assert top[0]["share_of_abs_pnl"] == pytest.approx(10 / 23)


def test_d2_removes_same_symbols_at_both_costs(env):
    runs = d25.preflight(env.contexts, env.spec, env.record, env.root)
    st = env.contexts["syn_a"]
    base = {c: runs["syn_a"][c] for c in env.spec.costs}
    out = d25.d2(st, env.spec, base)
    removed = [r["ticker"] for r in out["removed"]]
    u = [t for t in TICK if t not in removed]
    for c, s in env.spec.costs.items():
        assert out["per_cost"][c]["cagr"] == d25.cagr_of(d25.run_mom(st, u, s))


def test_d4_windows_splice_and_labels(env):
    runs = d25.preflight(env.contexts, env.spec, env.record, env.root)
    st = env.contexts["syn_b"]
    base = {c: runs["syn_b"][c] for c in env.spec.costs}
    d4 = d25.d4(st, env.spec, base)["5bps"]
    r, rb = mt.returns(base["5bps"]["V2-MOM"]), mt.returns(base["5bps"]["B1"])
    starts = list(range(0, len(r) - 20 + 1, 7))
    manual = [float(np.prod(1 + r[i:i + 20]) - np.prod(1 + rb[i:i + 20])) for i in starts]
    assert [w["active_total_return_diff"] for w in d4["D4b_rolling_window"]["windows"]] == manual
    assert d4["D4b_rolling_window"]["count"] == len(starts)
    assert sorted(d4["D4c_leave_one_year_out"]) == ["2017", "2018"]
    y = "2017"
    keep = np.array([not s.startswith(y) for s in base["5bps"]["V2-MOM"].sessions])
    one_year = d25.d4(env.contexts["syn_a"], env.spec, {c: runs["syn_a"][c] for c in env.spec.costs})
    assert one_year["5bps"]["D4c_leave_one_year_out"]["2017"]["cagr_excl"] == {"undefined": "no session remains"}
    assert d4["D4c_leave_one_year_out"][y]["cagr_excl"] == float(np.prod(1 + r[keep]) ** (252 / keep.sum()) - 1)
    bad = d25.Spec(universe=TICK, window=20, step=7, references=env.spec.references,
                   year_labels={"syn_b": {k: (v[0], v[1] + 1) for k, v in env.spec.year_labels["syn_b"].items()}})
    with pytest.raises(d25.Day25bError, match="sessions != frozen"):
        d25.d4(st, bad, base)
    wrong_count = d25.Spec(universe=TICK, window=20, step=7, year_labels=env.spec.year_labels,
                           expected_windows={"syn_b": len(starts) + 1})
    with pytest.raises(d25.Day25bError, match="windows != frozen"):
        d25.d4(st, wrong_count, base)


def test_argmin_ties_resolve_to_earliest():
    assert d25._argmin_first([1.0, 0.0, 0.0, 2.0]) == 1


def test_d5_and_d7_and_stats(env):
    runs = d25.preflight(env.contexts, env.spec, env.record, env.root)
    st = env.contexts["syn_a"]
    base = {c: runs["syn_a"][c] for c in env.spec.costs}
    d5 = d25.d5(st, env.spec, base)["5bps"]
    flows = base["5bps"]["V2-MOM"].flows
    tot = sum(abs(v) for v in flows.values())
    assert d5["top_k_share_of_abs_pnl"]["2"] == pytest.approx(d5["top2_concentration"])
    assert d5["top_k_share_of_abs_pnl"]["1"] == max(abs(v) for v in flows.values()) / tot
    d7 = d25.d7(st, env.spec, base)["5bps"]
    singles = [r["cagr"] for r in d7["rows"]]
    others = singles + [d25.cagr_of(base["5bps"]["B1"]), d25.cagr_of(base["5bps"]["B2"])]
    assert d7["v2mom_rank_among_singles_b1_b2"] == 1 + sum(x > d7["v2mom_cagr"] for x in others)
    assert d7["count_single_stocks_above_v2mom"] == sum(x > d7["v2mom_cagr"] for x in singles)
    xs = [0.3, -0.1, 0.2, 0.0, 0.5]
    s = d25._stats(xs)
    assert s["p5"] == float(np.percentile(xs, 5, method="linear")) and s["fraction_gt_0"] == 0.6 and s["n"] == 5


# ================================================================ continuation: reuse of an existing PASSED record

@pytest.fixture
def reuse_env(tmp_path):
    contexts, spec = make_contexts(), make_spec(ref_env=environment()["distributions_sha256"])
    write_references(tmp_path, contexts, spec)
    record = tmp_path / "preflight" / "preflight_record.json"
    d25.preflight(contexts, spec, record, tmp_path)                      # synthetic fixture record (PASSED)
    sha = hashlib.sha256(record.read_bytes()).hexdigest()
    return SimpleNamespace(root=tmp_path, contexts=contexts, spec=spec, record=record, sha=sha, out=tmp_path / "run")


def _forbid(monkeypatch, *names):
    for name in names:
        def boom(*_a, _n=name, **_k):
            raise AssertionError(f"{_n} must not run")
        monkeypatch.setattr(d25, name, boom)


def test_reuse_valid_record_completes_without_rerunning_preflight(reuse_env, monkeypatch):
    before = reuse_env.record.read_bytes()
    _forbid(monkeypatch, "preflight")
    summary = d25.run(reuse_env.contexts, reuse_env.spec, reuse_env.out, reuse_env.record, "test-authorization",
                      reuse_env.root, reuse_preflight_sha256=reuse_env.sha, expected_record_path=reuse_env.record)
    assert summary["status"] == "COMPLETED"
    assert summary["preflight_record"] == {"path": str(reuse_env.record), "sha256": reuse_env.sha,
                                           "reused": True, "validated": True}
    assert reuse_env.record.read_bytes() == before


def test_record_hash_is_line_ending_invariant(reuse_env):
    """validate_preflight_record's SHA-256 check must be CRLF-invariant, like doc_sha256 (test above), since a
    Windows checkout (core.autocrlf=true) rewrites the real record's line endings without changing its content."""
    lf_bytes = reuse_env.record.read_bytes()
    assert b"\r\n" not in lf_bytes                                        # the fixture record is written LF-only
    crlf_path = reuse_env.root / "crlf" / "preflight_record.json"
    crlf_path.parent.mkdir(parents=True)
    crlf_path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
    out_lf = d25.validate_preflight_record(reuse_env.record, reuse_env.sha, reuse_env.spec,
                                           expected_path=reuse_env.record, ref_root=reuse_env.root)
    out_crlf = d25.validate_preflight_record(crlf_path, reuse_env.sha, reuse_env.spec,
                                             expected_path=crlf_path, ref_root=reuse_env.root)
    assert out_lf["sha256"] == out_crlf["sha256"] == reuse_env.sha
    assert crlf_path.read_bytes() == lf_bytes.replace(b"\n", b"\r\n")     # the CRLF copy itself is never rewritten


def _tamper(rec: dict, case: str) -> dict:
    c0 = rec["comparisons"][0]
    if case == "status":
        rec["status"] = "FAILED"
    elif case == "run_status":
        rec["run_status"] = "ABORTED_PREFLIGHT_MISMATCH"
    elif case == "error":
        rec["error"] = {"type": "X", "message": "y"}
    elif case == "comparisons_total":
        rec["comparisons_total"] = 35
    elif case == "comparison_removed":
        rec["comparisons"].pop()
    elif case == "mismatch_count":
        rec["mismatch_count"] = 1
    elif case == "comparison_not_equal":
        c0["equal"] = False
    elif case == "authorizes_diagnostics":
        rec["authorizes_diagnostics"] = True
    elif case == "frozen_commit":
        rec["frozen_commit"] = "0" * 40
    elif case == "record_environment":
        rec["environment"]["distributions_sha256"] = "1" * 64
    elif case == "reference_changed":
        c0["reference"] = c0["recomputed"] = c0["reference"] + 1.0
    return rec


@pytest.mark.parametrize("case", ["wrong_hash", "missing", "path", "spec_environment", "status", "run_status", "error",
                                  "comparisons_total", "comparison_removed", "mismatch_count", "comparison_not_equal",
                                  "authorizes_diagnostics", "frozen_commit", "record_environment", "reference_changed"])
def test_reuse_invalid_record_aborts_before_any_computation_or_output(reuse_env, monkeypatch, case):
    spec, rec_path, expected, sha = reuse_env.spec, reuse_env.record, reuse_env.record, reuse_env.sha
    if case == "wrong_hash":
        sha = "0" * 64
    elif case == "missing":
        rec_path = expected = reuse_env.root / "absent" / "preflight_record.json"
    elif case == "path":
        expected = reuse_env.root / "elsewhere" / "preflight_record.json"
    elif case == "spec_environment":
        spec = make_spec(ref_env="0" * 64)
    else:                                                        # tampered copy, re-hashed so the target check fires
        rec_path = expected = reuse_env.root / "tampered" / "preflight_record.json"
        _dump(rec_path, _tamper(json.loads(reuse_env.record.read_text(encoding="utf-8")), case))
        sha = hashlib.sha256(rec_path.read_bytes()).hexdigest()
    snapshot = {p: p.read_bytes() for p in reuse_env.root.rglob("*.json") if "preflight" in p.parts or "tampered" in p.parts}
    _forbid(monkeypatch, "preflight", "preflight_runs_again", "compute_diagnostics")
    with pytest.raises(d25.Day25bError):
        d25.run(reuse_env.contexts, spec, reuse_env.out, rec_path, "test-authorization", reuse_env.root,
                reuse_preflight_sha256=sha, expected_record_path=expected)
    assert not reuse_env.out.exists() and not list(reuse_env.root.glob(".run.tmp-*"))
    assert {p: p.read_bytes() for p in snapshot} == snapshot


def test_reuse_base_run_inconsistency_aborts_before_diagnostics(reuse_env, monkeypatch):
    def shifted(contexts, spec):                                  # base runs that cannot reproduce the record
        return {sid: {c: {f: run_family(st, f, s + 0.0001) for f in d25.PORTFOLIOS} for c, s in spec.d6_frozen.items()}
                for sid, st in contexts.items()}
    monkeypatch.setattr(d25, "preflight_runs_again", shifted)
    _forbid(monkeypatch, "preflight", "compute_diagnostics")
    before = reuse_env.record.read_bytes()
    with pytest.raises(d25.Day25bError, match="differs from the preflight record"):
        d25.run(reuse_env.contexts, reuse_env.spec, reuse_env.out, reuse_env.record, "test-authorization",
                reuse_env.root, reuse_preflight_sha256=reuse_env.sha, expected_record_path=reuse_env.record)
    assert not reuse_env.out.exists() and reuse_env.record.read_bytes() == before


def test_reuse_still_requires_authorization_before_reading_the_record(reuse_env, monkeypatch):
    _forbid(monkeypatch, "validate_preflight_record", "preflight", "preflight_runs_again", "compute_diagnostics")
    with pytest.raises(d25.Day25bError, match="authorization"):
        d25.run(reuse_env.contexts, reuse_env.spec, reuse_env.out, reuse_env.record, "", reuse_env.root,
                reuse_preflight_sha256=reuse_env.sha, expected_record_path=reuse_env.record)
    assert d25.main(["--out", "artifacts/day25b/run"]) == 2


def test_cli_full_run_requires_the_exact_frozen_record_path(monkeypatch):
    _forbid(monkeypatch, "load_contexts", "verify_frozen_docs")
    other = d25.DEFAULT_PREFLIGHT_RECORD.parent / "other.json"
    out_existed = d25.DEFAULT_OUT.exists()                                 # the real D1-D7 run may already exist
    assert d25.main(["--preflight-record", str(other), "--authorization", "test-authorization"]) == 2
    assert not other.exists() and d25.DEFAULT_OUT.exists() == out_existed


@pytest.mark.skipif(not d25.DEFAULT_PREFLIGHT_RECORD.exists(), reason="real preflight record not present")
def test_real_preflight_record_validates_read_only():
    before = d25.DEFAULT_PREFLIGHT_RECORD.read_bytes()
    assert hashlib.sha256(before.replace(b"\r\n", b"\n")).hexdigest() == d25.PREFLIGHT_RECORD_SHA256     # CRLF-invariant, as validate_preflight_record now checks
    out = d25.validate_preflight_record(d25.DEFAULT_PREFLIGHT_RECORD, d25.PREFLIGHT_RECORD_SHA256, d25.FROZEN_SPEC)
    assert out["sha256"] == d25.PREFLIGHT_RECORD_SHA256 and out["record"]["comparisons_total"] == 36
    assert d25.DEFAULT_PREFLIGHT_RECORD.read_bytes() == before
