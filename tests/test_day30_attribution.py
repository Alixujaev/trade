"""tests/test_day30_attribution.py: DAY-30 implementation (scripts/day30_attribution.py), synthetic data only.

Synthetic input trees are built in tmp_path with the frozen engine on random prices that include splits and dividends,
and are written byte-for-byte like backtest/v2/run.py. Snapshot loaders, git HEAD blobs and the calendar version are
injected. No DAY-19/DAY-21 input, snapshot or market data is read and no DAY-30 result is computed on real data. The only
real file read is the committed frozen DAY-30 predeclaration (document gate).
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from acquisition.v2.sessions import stage_r_sessions
from backtest.v2 import engine as en
from backtest.v2 import metrics as mt
from backtest.v2.data import MarketData
from backtest.v2.run import Setup, _csv, _dump, run_family
from scripts import day30_attribution as d30

SESS = tuple(stage_r_sessions())
TICK = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH")
SEGS = {"syn_a": (300, 379, ("AAA", "BBB")), "syn_b": (440, 559, ("CCC", "DDD"))}
COSTS = {"5bps": 0.0005, "10bps": 0.0010}
U = Fraction(1, 2 ** 53)


def make_data(n=560, seed=7):
    rs = np.random.default_rng(seed)            # fixture generation only
    m = len(TICK) + 1
    c = np.cumprod(1 + rs.normal(0.0006, 0.015, (n, m)), axis=0) * 50
    o = c * (1 + rs.normal(0, 0.003, (n, m)))
    q, d = np.ones((n, m)), np.zeros((n, m))
    for k, js in ((330, range(m - 1)), (470, (0, 2, 4, 6)), (520, (1, 3, 5, 7))):
        for j in js:                            # raw prices on and after a split ex-date are in post-split units
            q[k, j] = 2.0
            o[k:, j] /= 2.0
            c[k:, j] /= 2.0
    for k in (310, 341, 365, 452, 489, 533, 555):
        d[k, :m - 1] = 0.21
    return MarketData(SESS[:n], TICK + ("SPY",), o, c, q, d)


def _write_run(d: Path, res, met) -> dict:
    return {
        "episodes.json": _dump(d / "episodes.json", res.episodes),
        "fills.csv": _csv(d / "fills.csv", ["session", "ticker", "side", "shares", "price", "notional", "cost", "lambda",
                                            "slot"],
                          [[f["session"], f["ticker"], f["side"], f["shares"], f["price"], f["notional"], f["cost"],
                            f.get("lambda"), f.get("slot")] for f in res.fills]),
        "equity.csv": _csv(d / "equity.csv", ["session", "equity", "exposure", "n_held"],
                           [[s, e, x, n] for s, e, x, n in zip(res.sessions, res.equity, res.exposure, res.n_held)]),
        "metrics.json": _dump(d / "metrics.json", met),
    }


def build_tree(root: Path, data: MarketData):
    segs, t1 = [], {c: {"results": {}} for c in COSTS}
    for sid, (a, b, d2) in SEGS.items():
        st = Setup(data, {"id": sid, "first": SESS[a], "last": SESS[b]})
        run_dir, mom, b1 = f"syn/{sid}/v2", f"MOM-{sid}", f"B1-{sid}"
        files = {}
        for c, s in COSTS.items():
            rm, rb = run_family(st, "V2-MOM", s), run_family(st, "B1", s)
            for exp, res, met in ((mom, rm, mt.compute(rm, rb, None)), (b1, rb, mt.compute(rb, None, None))):
                for name, sha in _write_run(root / run_dir / exp / c, res, met).items():
                    files[f"{exp}/{c}/{name}"] = sha
            sess = [x.isoformat() for x in SESS[a:b + 1]]
            t1[c]["results"][sid] = {"by_k": {str(k): {"best": {"sessions": sess[1:1 + 2 * k:2]},
                                                       "worst": {"sessions": sess[2:2 + 2 * k:2]}}
                                              for k in (5, 10, 20)}}
        n = b - a + 1
        summary = {"segment": {"id": sid, "first": SESS[a].isoformat(), "last": SESS[b].isoformat(), "sessions": n},
                   "result_files_sha256": files,
                   "reproducibility": {"data": {"manifest_sha256": f"m-{sid}", "tree_sha256": f"t-{sid}"}}}
        sha = _dump(root / run_dir / "run_summary.json", summary)
        _dump(root / run_dir / "run_provenance.json", {"run_summary_sha256": sha})
        segs.append(d30.Segment(sid, run_dir, SESS[a].isoformat(), SESS[b].isoformat(), n, mom, b1, d2))
    t1_files, pins29 = [], {}
    for c in COSTS:
        sha = _dump(root / "d29" / c / "t1.json", t1[c])
        t1_files.append((c, f"d29/{c}/t1.json", sha))
        pins29[f"{c}/t1.json"] = sha
    s29 = _dump(root / "d29" / "run_summary.json", {"result_files_sha256": pins29})
    d2 = {"results": {sid: {"removed": [{"ticker": t} for t in v[2]], "same_symbols_at_all_costs": True}
                      for sid, v in SEGS.items()}}
    d2sha = _dump(root / "d25b" / "d2.json", d2)
    _dump(root / "d25b" / "run_summary.json", {"result_files_sha256": {"d2.json": d2sha}})
    return d30.Spec(segments=tuple(segs), t1_files=tuple(t1_files), day29_summary=("d29/run_summary.json", s29),
                    d2_file=("d25b/d2.json", d2sha), d2_pins="d25b/run_summary.json")


def loaders_for(data):
    return {sid: (lambda sid=sid: (data, {"manifest_sha256": f"m-{sid}", "tree_sha256": f"t-{sid}",
                                         "snapshot_id": f"syn-{sid}", "missing_bars": 0})) for sid in SEGS}


def head_blob_working(root, rel):
    return (Path(root) / rel).read_bytes()


@pytest.fixture(scope="module")
def base_data():
    return make_data()


@pytest.fixture
def env(tmp_path, base_data):
    spec = build_tree(tmp_path, base_data)
    return SimpleNamespace(root=tmp_path, spec=spec, data=base_data, out=tmp_path / "out" / "run",
                           record=tmp_path / "out" / "preflight" / "gate_record.json")


def go(env, loaders=None, head_blob=head_blob_working, cal=lambda: "4.13.2", spec=None, out=None, record=None):
    return d30.run(env.root, spec or env.spec, out or env.out, record or env.record, d30.AUTH_TOKEN,
                   loaders=loaders or loaders_for(env.data), head_blob=head_blob, cal_version=cal)


def repin(env, rel: str):
    """After a deliberate edit of an I1 file, refresh its run_summary pin and provenance so only the targeted gate fails."""
    seg = next(s for s in env.spec.segments if rel.startswith(s.run_dir + "/"))
    sp = env.root / seg.run_dir / "run_summary.json"
    summary = json.loads(sp.read_bytes())
    summary["result_files_sha256"][rel[len(seg.run_dir) + 1:]] = hashlib.sha256((env.root / rel).read_bytes()).hexdigest()
    _dump(env.root / seg.run_dir / "run_provenance.json", {"run_summary_sha256": _dump(sp, summary)})


def rel_of(env, sid, series, cost, name):
    seg = next(s for s in env.spec.segments if s.id == sid)
    return f"{seg.run_dir}/{seg.mom if series == 'mom' else seg.b1}/{cost}/{name}"


def expect_abort(env, gate, **kw):
    with pytest.raises(d30.GateAbort, match=f"^{gate}"):
        go(env, **kw)
    rec = json.loads(env.record.read_bytes())
    assert rec["status"] == "ABORTED" and rec["failed_gate"] == gate
    assert not env.out.exists()
    return rec


# ================================================================ frozen document and refusals

def test_frozen_document_gate_and_spec_match_the_document():
    assert d30.verify_frozen_doc() == d30.FROZEN_DOC_LF_SHA256
    text = (d30.ROOT_DIR / d30.FROZEN_MD).read_text(encoding="utf-8")
    assert "`.venv/Scripts/python.exe -m scripts.day30_attribution --authorization DAY30-ATTRIBUTION-RUN`" in text
    from scripts.day29_stability import FROZEN_SPEC as D29     # the frozen §1 segments are the DAY-19/21 runs
    for seg, s29 in zip(d30.FROZEN_SPEC.segments, D29.segments):
        assert f"{seg.run_dir}/{{{seg.mom},{seg.b1}}}" in text
        assert (seg.id, seg.run_dir, seg.first, seg.last, seg.sessions, seg.mom, seg.b1) == \
            (s29.id, s29.run_dir, s29.first, s29.last, s29.sessions, s29.mom, s29.b1)
    assert "research {TSLA, NVDA}, holdout {MU, AMD}" in text
    for _, path, sha in d30.FROZEN_SPEC.t1_files:
        assert path in text and sha[:8] in text
    assert d30.FROZEN_SPEC.d2_file[1] in text and d30.FROZEN_SPEC.day29_summary[1] in text
    assert "k ∈ {5, 10, 20}" in text and d30.FROZEN_SPEC.ks == (5, 10, 20)
    assert "`exchange_calendars==4.13.2`" in text
    assert d30.EVIDENCE_LABEL in text and d30.CONDITIONAL_LABEL in text and d30.COST_LABELS["10bps"] in text


def test_document_gate_rejects_a_changed_document(tmp_path):
    p = tmp_path / d30.FROZEN_MD
    p.parent.mkdir(parents=True)
    p.write_bytes((d30.ROOT_DIR / d30.FROZEN_MD).read_bytes() + b" ")
    with pytest.raises(d30.Day30Error, match="changed"):
        d30.verify_frozen_doc(tmp_path)


@pytest.mark.parametrize("token", ["", "DAY30-ATTRIBUTION-RUN ", "day30-attribution-run", "owner-authorized"])
def test_main_rejects_any_other_token_before_reading_inputs(token, monkeypatch, capsys):
    monkeypatch.setattr(d30, "run", lambda *a, **k: pytest.fail("run() must not be reached"))
    monkeypatch.setattr(d30, "verify_frozen_doc", lambda *a, **k: pytest.fail("no input may be read"))
    assert d30.main(["--authorization", token]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_run_rejects_wrong_token_and_existing_outputs(env):
    with pytest.raises(d30.Day30Error, match="exactly"):
        d30.run(env.root, env.spec, env.out, env.record, "other", loaders=loaders_for(env.data),
                head_blob=head_blob_working, cal_version=lambda: "4.13.2")
    assert not env.record.exists()
    env.out.mkdir(parents=True)
    with pytest.raises(d30.Day30Error, match="overwrite"):
        go(env)


# ================================================================ end to end (synthetic)

def test_end_to_end_outputs_labels_hashes_and_determinism(env, tmp_path):
    summary = go(env)
    assert summary["status"] == "COMPLETED" and summary["authorization"] == d30.AUTH_TOKEN
    assert set(summary["gates"]) == {f"G{i}" for i in range(1, 9)}
    names = sorted(str(p.relative_to(env.out)).replace("\\", "/") for p in env.out.rglob("*") if p.is_file())
    exp = sorted([f"{c}/{o}.json" for c in COSTS for o in ("o1", "o2", "o3")]
                 + [f"{c}/o3_sessions_{sid}.csv" for c in COSTS for sid in SEGS] + ["run_summary.json"])
    assert names == exp
    for rel, sha in summary["result_files_sha256"].items():
        assert hashlib.sha256((env.out / rel).read_bytes()).hexdigest() == sha
    for c in COSTS:
        for o in ("o1", "o2", "o3"):
            body = json.loads((env.out / f"{c}/{o}.json").read_bytes())
            assert body["conditional_label"] == d30.CONDITIONAL_LABEL and body["evidence_label"] == d30.EVIDENCE_LABEL
            assert body["descriptive_only"] is True and body["cost_label"] == d30.COST_LABELS[c]
    assert summary["conditional_premises"]["A4"].startswith("premise; not proven")
    rec = json.loads(env.record.read_bytes())
    assert rec["status"] == "PASSED" and "G7" in rec["gates"] and rec["gates"]["G7"]["conditional"] == d30.CONDITIONAL_LABEL
    o1 = json.loads((env.out / "5bps/o1.json").read_bytes())["results"]["syn_a"]["5"]["best"]
    assert o1["d2_tickers"] == ["AAA", "BBB"] and len(o1["day_set_sessions"]) == 5
    cells = [v["sum"] for r in o1["cells"].values() for v in r.values()]
    assert math.isclose(math.fsum(cells), o1["total"], rel_tol=1e-12, abs_tol=1e-15)
    o2 = json.loads((env.out / "5bps/o2.json").read_bytes())["results"]["syn_a"]["5"]["best"]["rows"]
    assert [r["ticker"] for r in o2] == sorted(TICK)
    # a second, independent run produces byte-identical outputs
    out2, rec2 = tmp_path / "o2" / "run", tmp_path / "o2" / "pre" / "gate_record.json"
    go(env, out=out2, record=rec2)
    for rel in summary["result_files_sha256"]:
        assert (env.out / rel).read_bytes() == (out2 / rel).read_bytes()


def test_fixture_exercises_every_bound_path(env):
    """The synthetic fixture covers splits, dividends, partial sells, add-on buys, full sells, λ < 1 and liquidation."""
    res = d30.compute(env.root, env.spec, loaders_for(env.data), head_blob_working, lambda: "4.13.2", {})
    days = [d for v in res["recs"].values() for d in v["rec"]["days"]]
    assert any(d["splits"] for d in days) and any(d["divs"] for d in days)
    assert any(s[5] for d in days for s in d["sells"]) and any(not s[5] for d in days for s in d["sells"])
    assert any(b[5] != 0 for d in days for b in d["buys"])
    assert any(b[6] < 1.0 for d in days for b in d["buys"])
    assert all(v["rec"]["final"] for v in res["recs"].values())


# ================================================================ gate failures (fail closed)

def test_G1_pin_mismatch_aborts(env):
    p = env.root / rel_of(env, "syn_a", "mom", "5bps", "fills.csv")
    p.write_bytes(p.read_bytes() + b"\n")
    expect_abort(env, "G1")


def test_G1_malformed_float_cell_aborts(env):
    rel = rel_of(env, "syn_b", "b1", "10bps", "equity.csv")
    p = env.root / rel
    lines = p.read_bytes().decode().split("\n")
    parts = lines[3].split(",")
    parts[1] = "nan"
    lines[3] = ",".join(parts)
    p.write_bytes("\n".join(lines).encode())
    repin(env, rel)
    expect_abort(env, "G1")


def test_G2_snapshot_identity_and_calendar(env):
    bad = loaders_for(env.data)
    bad["syn_b"] = lambda: (env.data, {"manifest_sha256": "other", "tree_sha256": "t-syn_b"})
    expect_abort(env, "G2", loaders=bad)


def test_G2_calendar_version(env):
    expect_abort(env, "G2", cal=lambda: "4.13.1")


def test_G2_loader_failure_fails_closed(env):
    def boom():
        raise RuntimeError("snapshot manifest mismatch")
    bad = loaders_for(env.data)
    bad["syn_a"] = boom
    expect_abort(env, "G2", loaders=bad)


def test_G3_day_set_file_changed(env):
    p = env.root / "d29" / "5bps" / "t1.json"
    obj = json.loads(p.read_bytes())
    obj["results"]["syn_a"]["by_k"]["5"]["best"]["sessions"][0] = obj["results"]["syn_a"]["by_k"]["5"]["worst"]["sessions"][0]
    _dump(p, obj)
    expect_abort(env, "G3")


def test_G3_untracked_or_differing_head_blob(env):
    expect_abort(env, "G3", head_blob=lambda root, rel: None)


def test_G3_fixed_ticker_set_enforced(env):
    spec = replace(env.spec, segments=(replace(env.spec.segments[0], d2=("AAA", "CCC")), env.spec.segments[1]))
    expect_abort(env, "G3", spec=spec)


def _first_fill(env, sid, series, cost, side):
    rel = rel_of(env, sid, series, cost, "fills.csv")
    return d30.parse_fills((env.root / rel).read_bytes()), rel


def test_G4_fill_price_differs_from_open(env):
    fills, _ = _first_fill(env, "syn_a", "mom", "5bps", "buy")
    f = fills[0]
    data = env.data
    o = data.open.copy()
    o[[s.isoformat() for s in data.sessions].index(f.session), data.tickers.index(f.ticker)] *= 1.0000001
    expect_abort(env, "G4", loaders=loaders_for(MarketData(data.sessions, data.tickers, o, data.close, data.q, data.d)))


def test_G4_nan_open_where_held(env):
    data = env.data
    o = data.open.copy()
    k = SEGS["syn_b"][0] + 30                       # B1 holds every universe ticker on every segment session
    o[k, 0] = np.nan
    expect_abort(env, "G4", loaders=loaders_for(MarketData(data.sessions, data.tickers, o, data.close, data.q, data.d)))


def test_G5_n_held_mismatch(env):
    rel = rel_of(env, "syn_a", "mom", "10bps", "equity.csv")
    p = env.root / rel
    lines = p.read_bytes().decode().split("\n")
    parts = lines[7].split(",")
    parts[3] = str(int(parts[3]) + 1)
    lines[7] = ",".join(parts)
    p.write_bytes("\n".join(lines).encode())
    repin(env, rel)
    expect_abort(env, "G5")


def test_G5d_swapped_contribution_aborts(env):
    rel = rel_of(env, "syn_b", "b1", "5bps", "metrics.json")
    p = env.root / rel
    m = json.loads(p.read_bytes())
    c = m["symbol_pnl_contribution"]
    c["AAA"], c["BBB"] = c["BBB"], c["AAA"]
    _dump(p, m)
    repin(env, rel)
    rec = expect_abort(env, "G5")
    assert rec["detail"]["check"] == "G5d"


def test_G5b_buy_shares_altered(env):
    rel = rel_of(env, "syn_a", "mom", "5bps", "fills.csv")
    p = env.root / rel
    lines = p.read_bytes().decode().split("\n")
    parts = lines[1].split(",")
    v = float(parts[3][len("np.float64("):-1])
    parts[3] = f"np.float64({repr(float(np.nextafter(v, np.inf)))})"
    lines[1] = ",".join(parts)
    p.write_bytes("\n".join(lines).encode())
    repin(env, rel)
    rec = expect_abort(env, "G5")
    assert rec["detail"]["check"] == "G5b"


def test_G7_equity_discrepancy_aborts(env):
    rel = rel_of(env, "syn_a", "b1", "5bps", "equity.csv")
    p = env.root / rel
    lines = p.read_bytes().decode().split("\n")
    parts = lines[11].split(",")
    v = float(parts[1][len("np.float64("):-1])
    parts[1] = f"np.float64({repr(v + 1e-6)})"
    lines[11] = ",".join(parts)
    p.write_bytes("\n".join(lines).encode())
    repin(env, rel)
    rec = expect_abort(env, "G7")
    assert rec["detail"]["conditional"] == d30.CONDITIONAL_LABEL


def test_G8_catches_mis_assignment_between_tickers(env):
    """G8 sees a swap of two tickers' totals that G7 (daily sums over tickers) cannot see."""
    res = d30.compute(env.root, env.spec, loaders_for(env.data), head_blob_working, lambda: "4.13.2", {})
    r = res["recs"][("syn_b", "5bps", "B1")]["rec"]
    contrib = dict(res["art"]["series"][("syn_b", "5bps", "B1")]["contrib"])
    d30.g8_check(r, contrib, 0.0005, env.data.universe, ["syn_b", "5bps", "B1"])       # unmodified: passes
    contrib["AAA"], contrib["BBB"] = contrib["BBB"], contrib["AAA"]
    with pytest.raises(d30._GateFailed) as e:
        d30.g8_check(r, contrib, 0.0005, env.data.universe, ["syn_b", "5bps", "B1"])
    assert e.value.gate == "G8"


def test_reads_outside_allow_list_are_refused(env):
    rd = d30.Reader(env.root, env.spec)
    with pytest.raises(d30._GateFailed) as e:
        rd.read("syn/syn_a/v2/MOM-syn_a/5bps/decisions.json")
    assert e.value.gate == "G6"


# ================================================================ §4 arithmetic and §6A identities

def test_hand_checked_pnl_split_dividend_resize_missing_open_and_liquidation():
    # S_prev=10 @ M=50, split q=2 -> S'=20, M'=25; dividend 0.5 on pre-split shares = 5; open 26; sell 5 -> S=15;
    # close 27; cost 0.1: 5 + 20·(26−25) + 15·(27−26) − 0.1 = 39.9
    assert d30.pnl_function(10, 50, 2, 0.5, 26, 15, 27, 0.1, 0.0005, False) == Fraction(5) + 20 + 15 - Fraction(0.1)
    # missing open: V = M' (25), so the open term is 0 and the close term carries the move from M'
    assert d30.pnl_function(10, 50, 2, 0, 25, 20, 27, 0, 0.0005, False) == 20 * 2
    # last session: liquidation s·S·M is deducted
    assert d30.pnl_function(10, 50, 1, 0, 50, 10, 51, 0, 0.0005, True) == 10 - Fraction(0.0005) * 10 * 51


def test_gamma_and_sigma_bar_exact():
    assert d30.gamma(0) == 0 and d30.gamma(-1) == 0
    assert d30.gamma(3) == 3 * U / (1 - 3 * U)
    assert d30.sigma_bar(Fraction(100), 1) == U * 100
    assert d30.sigma_bar(Fraction(100), 4) == (U + (1 + U) * d30.gamma(3)) * 100


def _instrumented_run(monkeypatch, data, decide, decision_idx, s, a, b):
    """Run the frozen engine on synthetic data while logging its unrecorded intermediates (test only)."""
    log = {"close_cash": {}, "buy": {}}
    orig_close, orig_buy = en._close_phase, en._buy_all

    def close_phase(book, k, *rest):
        log["close_cash"][k] = book.cash
        return orig_close(book, k, *rest)

    def buy_all(book, k, buys, s_):
        K = book.cash
        lam = orig_buy(book, k, buys, s_)
        log["buy"][k] = {"K": K, "n": [n for _, n in buys], "lam": lam, "cash_after": book.cash}
        return lam
    monkeypatch.setattr(en, "_close_phase", close_phase)
    monkeypatch.setattr(en, "_buy_all", buy_all)
    res = en.simulate_targets(data, decide, decision_idx, s, a, b, "syn")
    return res, log


def _ser_from_result(tmp, res, met):
    d = Path(tmp)
    _write_run(d, res, met)
    sess, eq, nh = d30._parse_equity((d / "equity.csv").read_bytes())
    return {"sessions": sess, "equity": eq, "n_held": nh, "fills": d30.parse_fills((d / "fills.csv").read_bytes()),
            "episodes": d30.parse_episodes((d / "episodes.json").read_bytes()),
            "contrib": json.loads((d / "metrics.json").read_bytes())["symbol_pnl_contribution"]}


@pytest.mark.parametrize("weights", [0.6, 1.0])          # 0.6: rebalances at λ = 1; 1.0: λ < 1
def test_section_6A_exact_identities_with_engine_intermediates(tmp_path, monkeypatch, base_data, weights):
    """Frozen §10: with the engine's unrecorded intermediates logged, (i) ε_k equals the §6A.4 decomposition exactly,
    (ii) the buy-step Λ identity holds exactly for λ = 1 and λ < 1, (iii) the G8 identity holds exactly, and every
    piece is within its §6A bound."""
    data, s, a, b = base_data, 0.0005, 300, 400
    uni = list(range(len(TICK)))
    months = sorted({k for k in range(a, b) if SESS[k].month != SESS[k + 1].month} | {a - 1})
    rot = {k: i for i, k in enumerate(months)}

    def decide(k):
        i = rot[k]
        pick = [uni[(i + x) % len(uni)] for x in range(4)]
        w = [0.4, 0.3, 0.2, 0.1] if i % 2 else [0.25, 0.25, 0.25, 0.25]
        return {j: weights * wv for j, wv in zip(pick, w)}
    res, log = _instrumented_run(monkeypatch, data, decide, months, s, a, b)
    ser = _ser_from_result(tmp_path, res, {"symbol_pnl_contribution": dict(sorted(res.flows.items()))})
    sessions = [x.isoformat() for x in data.sessions[a:b + 1]]
    mk = {"data": data, "k0": a, "kT": b, "sessions": sessions}
    rec = d30.reconstruct(mk, ser, s, ["syn"])
    eq = [Fraction(en.E0)] + [Fraction(e) for e in ser["equity"]]
    eps = [(eq[i + 1] - eq[i]) - d30.tree_sum(d["pnl"].values()) for i, d in enumerate(rec["days"])]
    tau = d30.daily_tau(rec["days"], eq, s)
    sf, T = Fraction(s), len(rec["days"]) - 1
    lam_seen = set()
    prev_bracket, prev_cash = Fraction(0), Fraction(en.E0)
    for i, d in enumerate(rec["days"]):
        k = a + i
        cash = Fraction(log["close_cash"][k])
        bracket = eq[i + 1] - cash - d["sum_sm"] + (sf * d["sum_sm"] if i == T else 0)    # ρ + σ (+ liquidation)
        flow = Fraction(0)
        for j, (S0, Sp, Sk, M0, Mp, Mk) in d["state"].items():
            V = Fraction(data.open[k, j])
            if j in d["div_by_j"]:
                Sv, dv = d["div_by_j"][j]
                flow += Sv * dv
            flow -= (Fraction(Sk) - Fraction(Sp)) * V
        flow -= sum((x[4] for x in d["sells"]), Fraction(0)) + sum((x[2] for x in d["buys"]), Fraction(0))
        cash_bracket = (cash - prev_cash) - flow
        split = sum((Fraction(d["state"][j][1]) * Fraction(d["state"][j][4])
                     - Fraction(d["state"][j][0]) * Fraction(d["state"][j][3]) for j, _ in d["splits"]), Fraction(0))
        assert eps[i] == bracket - prev_bracket + cash_bracket + split                    # (i) exact identity
        assert abs(eps[i]) <= tau[i]
        if k in log["buy"] and d["buys"]:                                                 # (ii) Λ identity
            lg = log["buy"][k]
            K, ns, lam = Fraction(lg["K"]), [Fraction(n) for n in lg["n"]], lg["lam"]
            lam_seen.add(lam == 1.0)
            B = sum(ns, Fraction(0))
            Bh = Fraction(sum(np.float64(n) for n in lg["n"]))
            sh_ = Fraction(np.float64(1 + s))
            Ph = Fraction(np.float64(Bh) * (1 + s))
            om_s, om_B, om_P = sh_ - (1 + sf), Bh - B, Ph - Bh * sh_
            phi = sum((sh * px - N for _, N, C, sh, px, pre, _l in d["buys"]), Fraction(0))
            pi = sum(((Fraction(d["state"][j][2]) - (pre + sh)) * px for j, N, C, sh, px, pre, _l in d["buys"]),
                     Fraction(0))
            buy_exact = -sum(((Fraction(d["state"][j][2]) - pre) * px + C for j, N, C, sh, px, pre, _l in d["buys"]),
                             Fraction(0))
            engine = Fraction(lg["cash_after"]) - K
            if lam == 1.0:
                kappa = sum((C - N * sf for _, N, C, *_r in d["buys"]), Fraction(0))
                beta_b = Fraction(lg["cash_after"]) - (K - Ph)
                Lam = -B * om_s - sh_ * om_B - om_P + beta_b + phi + pi + kappa
            else:
                lf = Fraction(lam)
                om_l = lf - K / Ph
                om_i = sum((N - lf * n for (_, N, *_r), n in zip(d["buys"], ns)), Fraction(0))
                kappa = sum((C - N * sf for _, N, C, *_r in d["buys"]), Fraction(0))
                Lam = -lf * (B * om_s + sh_ * om_B + om_P) + Ph * om_l + (1 + sf) * om_i + kappa + phi + pi
            assert Lam == engine - buy_exact
        prev_bracket, prev_cash = eq[i + 1] - cash - d["sum_sm"], cash
    assert lam_seen == {weights < 1.0}
    # (iii) G8 identity: flows_j − Σ pnl_j equals the sum of the §6A.5 local errors, exactly
    tick = rec["tickers"]
    for j in range(len(TICK)):
        F, errs = np.float64(0.0), Fraction(0)
        for i, d in enumerate(rec["days"]):
            k = a + i
            px = Fraction(data.open[k, j])
            if j in d["div_by_j"]:
                S0 = d["state"][j][0]
                amt = S0 * data.d[k, j]
                errs += Fraction(amt) - Fraction(S0) * Fraction(data.d[k, j])
                Fn = F + amt
                errs += Fraction(Fn) - (Fraction(F) + Fraction(amt))
                F = Fn
            for jj, sm in d["splits"]:
                if jj == j:
                    errs += Fraction(d["state"][j][1]) * Fraction(d["state"][j][4]) - sm
            for jj, qty, _px, N, C, partial, pre in d["sells"]:
                if jj == j:
                    net = np.float64(float(N)) - np.float64(float(C))
                    errs += (N - qty * px) + (Fraction(net) - (N - C))
                    if partial:
                        errs += (Fraction(d["state"][j][2]) - (pre - qty)) * px
                    Fn = F + net
                    errs += Fraction(Fn) - (Fraction(F) + Fraction(net))
                    F = Fn
            for jj, N, C, sh, _px, pre, _l in d["buys"]:
                if jj == j:
                    errs += (sh * px - N) + (Fraction(d["state"][j][2]) - (pre + sh)) * px
                    G = F - np.float64(float(N))
                    errs += Fraction(G) - (Fraction(F) - N)
                    Fn = G - np.float64(float(C))
                    errs += Fraction(Fn) - (Fraction(G) - C)
                    F = Fn
        if j in rec["final"]:
            Sv, Mv = rec["final"][j]
            net_l = np.float64(float(Sv)) * np.float64(float(Mv)) * (1 - s)
            errs += Fraction(net_l) - (1 - sf) * Sv * Mv
            Fn = F + net_l
            errs += Fraction(Fn) - (Fraction(F) + Fraction(net_l))
            F = Fn
        flows = Fraction(ser["contrib"].get(tick[j], 0.0))
        assert Fraction(F) == flows
        total = d30.tree_sum(d["pnl"].get(j, Fraction(0)) for d in rec["days"])
        assert flows - total == errs
    d30.g8_check(rec, ser["contrib"], s, data.universe, ["syn"])
