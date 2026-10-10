"""tests/test_day27_paper.py: sealed paper-trading runner V2-MOM-P001 (DAY-27). Network-free and synthetic.

Prices are a seeded random walk on the real XNYS calendar (no market data); the fetcher is injected; every socket
connection is refused; the adoption check is stubbed where the uncommitted working tree would otherwise refuse.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import socket

import numpy as np
import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from acquisition.v2.contract import BAR_COLUMNS
from acquisition.v2.http import AlpacaRequestError
from acquisition.v2.sessions import label_for
from backtest.v2 import run as rn
from backtest.v2.data import MarketData
from config.day_universe import FROZEN_DAY_UNIVERSE
from paper import data as pdata
from paper import ledger as pl
from paper import runner as pr
from paper import seal as ps
from paper.config import FIRST_SESSION, HISTORY_START, SEAL_UNTIL

NY = ZoneInfo("America/New_York")
KEY = bytes(range(32))
TICKERS = tuple(sorted(FROZEN_DAY_UNIVERSE)) + ("SPY",)
PERF_KEYS = {"equity", "equity_close", "daily_pnl", "daily_return", "weights", "positions_value", "cash", "fills",
             "fills_today", "decisions_today", "pending_orders_next_open", "total_return", "cagr"}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("network access attempted in a DAY-27 test")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _synthetic(last=date(2026, 12, 31), seed=5) -> MarketData:
    sessions = tuple(pdata.sessions_between(HISTORY_START, last))
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, (len(sessions), len(TICKERS))), axis=0))
    opn = close * np.exp(rng.normal(0, 0.004, close.shape))
    return MarketData(sessions, TICKERS, opn, close, np.ones(close.shape), np.zeros(close.shape))


DATA = _synthetic()


def _fetcher(data=DATA, calls=None):
    def fetch(session: date):
        if calls is not None:
            calls.append(session)
        k = data.index_of(session)
        return data.truncate(k), {"input_manifest_sha256": f"synthetic-{session}", "sessions": k + 1, "missing_bars": 0,
                                  "events_used": 0, "review_pending": []}
    return fetch


def _run(tmp_path, now, **kw):
    kw.setdefault("fetch", _fetcher())
    return pr.run(now, state=pr.State(tmp_path), adoption_check=lambda: {}, key=KEY, **kw)


def _et(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=NY)


# ------------------------------------------------------------------ frozen engine reuse, timing, sizing

def test_replay_is_the_frozen_engine():
    first, upto = DATA.index_of(FIRST_SESSION), DATA.index_of(date(2026, 11, 10))
    res = pl.replay(DATA, first, upto)
    st = rn.Setup(DATA, {"id": "x", "first": FIRST_SESSION, "last": date(2026, 12, 31), "families": ("V2-MOM",)})
    for fam in ("V2-MOM", "B1", "B2"):
        ref = rn.run_family(st, fam, 0.0005, upto=upto)
        assert res[fam].fills == ref.fills and res[fam].equity == ref.equity and res[fam].decisions == ref.decisions


def test_signal_timing_and_sizing():
    res = pl.replay(DATA, DATA.index_of(FIRST_SESSION), DATA.index_of(date(2026, 11, 3)))["V2-MOM"]
    assert [d["close"] for d in res.decisions] == ["2026-10-09", "2026-10-30"]      # §8.14 initial + month end
    assert {f["session"] for f in res.fills} == {"2026-10-12", "2026-11-02"}         # next session's open only
    first = res.decisions[0]["targets"]
    assert len(first) == 5 and all(w == 0.2 for w in first.values())
    k = DATA.index_of(date(2026, 10, 12))
    for f in res.fills:
        if f["session"] == "2026-10-12":
            assert f["price"] == DATA.open[k, DATA.col(f["ticker"])]
            assert f["cost"] == pytest.approx(abs(f["notional"]) * 0.0005)
    assert res.executions[0]["lambda"] is not None and res.executions[0]["lambda"] <= 1.0


def test_decision_never_uses_the_decision_bar():
    """Changing the 2026-10-30 close (bar t) cannot change the 10-30 decision (frozen §4: TR(t-21)/TR(t-252))."""
    k = DATA.index_of(date(2026, 10, 30))
    cl = DATA.close.copy()
    cl[k] *= 5.0
    moved = MarketData(DATA.sessions, DATA.tickers, DATA.open, cl, DATA.q, DATA.d)
    a = pl.replay(DATA, DATA.index_of(FIRST_SESSION), k)["V2-MOM"].decisions
    b = pl.replay(moved, DATA.index_of(FIRST_SESSION), k)["V2-MOM"].decisions
    assert a == b


# ------------------------------------------------------------------ runner: persistence, idempotency, catch-up

def test_run_catch_up_idempotent_and_health_only(tmp_path):
    out = _run(tmp_path, _et(2026, 10, 14, 17))
    assert out["processed_now"] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    st = pr.State(tmp_path)
    recs = st.processed()
    assert [recs[s]["late"] for s in sorted(recs)] == [True, True, False]
    for r in recs.values():
        assert not PERF_KEYS & set(r) and (tmp_path / "sealed" / f"{r['session']}.bin").is_file()
    before = {p.name: p.read_bytes() for p in (tmp_path / "runs").iterdir()}
    calls = []
    assert _run(tmp_path, _et(2026, 10, 14, 18), fetch=_fetcher(calls=calls))["status"] == "NOOP"
    assert calls == [] and before == {p.name: p.read_bytes() for p in (tmp_path / "runs").iterdir()}
    out = _run(tmp_path, _et(2026, 10, 15, 17))
    assert out["processed_now"] == ["2026-10-15"] and out["processed_total"] == 4
    s = pr.status(st)
    assert s["processed_sessions"] == 4 and not PERF_KEYS & set(json.dumps(s).replace('"', " ").split())
    assert pr.check_health(_et(2026, 10, 15, 17), st) == (True, "healthy through 2026-10-15")


def test_crash_before_commit_point_is_redone_identically(tmp_path, monkeypatch):
    clean = tmp_path / "clean"
    _run(clean, _et(2026, 10, 14, 17))
    crashed = tmp_path / "crash"
    real = pr.State.write_atomic
    n = {"runs": 0}

    def flaky(self, rel, payload):
        if rel.startswith("runs/") and rel != "runs/2026-10-12.json":
            n["runs"] += 1
            if n["runs"] == 1:
                raise OSError("simulated crash")
        return real(self, rel, payload)
    monkeypatch.setattr(pr.State, "write_atomic", flaky)
    with pytest.raises(OSError):
        _run(crashed, _et(2026, 10, 14, 17))
    assert set(pr.State(crashed).processed()) == {"2026-10-12"}
    assert not (crashed / "run.lock").exists()
    _run(crashed, _et(2026, 10, 14, 17))
    a, b = pr.State(clean).processed(), pr.State(crashed).processed()
    assert {s: r["ledger_sha256"] for s, r in a.items()} == {s: r["ledger_sha256"] for s, r in b.items()}


def test_lock_prevents_concurrent_runs_and_stale_lock_is_reclaimed(tmp_path):
    st = pr.State(tmp_path)
    st.acquire_lock()
    with pytest.raises(pr.Busy):
        _run(tmp_path, _et(2026, 10, 14, 17))
    import os
    old = 1_000_000_000
    os.utime(tmp_path / "run.lock", (old, old))
    assert _run(tmp_path, _et(2026, 10, 14, 17))["status"] == "OK"


# ------------------------------------------------------------------ fail closed

def test_not_ready_before_close_and_on_early_close():
    assert pr.latest_completed_session(_et(2026, 10, 12, 16, 14)) == date(2026, 10, 9)
    assert pr.latest_completed_session(_et(2026, 10, 12, 16, 15)) == date(2026, 10, 12)
    assert pr.latest_completed_session(_et(2026, 11, 27, 13, 14)) == date(2026, 11, 25)     # early close 13:00
    assert pr.latest_completed_session(_et(2026, 11, 27, 13, 15)) == date(2026, 11, 27)


def test_not_ready_writes_nothing(tmp_path):
    with pytest.raises(pr.NotReady):
        _run(tmp_path, _et(2026, 10, 12, 15))
    assert not list((tmp_path / "runs").iterdir()) and not (tmp_path / "last_error.json").exists()


def test_stale_data_and_auth_errors_fail_closed_and_are_redacted(tmp_path, monkeypatch):
    def stale(session):
        k = DATA.index_of(session) - 1
        return DATA.truncate(k), {"input_manifest_sha256": "x"}
    with pytest.raises(pdata.DataFailClosed, match="stale"):
        _run(tmp_path, _et(2026, 10, 14, 17), fetch=stale)
    assert not pr.State(tmp_path).processed()
    monkeypatch.setenv("ALPACA_API_KEY", "PKSECRETVALUE123")

    def auth(_s):
        raise AlpacaRequestError("401 unauthorized for key PKSECRETVALUE123", status=401, fatal=True)
    with pytest.raises(AlpacaRequestError):
        _run(tmp_path, _et(2026, 10, 14, 17), fetch=auth)
    err = json.loads((tmp_path / "last_error.json").read_text())
    assert "PKSECRETVALUE123" not in json.dumps(err) and "***" in err["message"]
    assert not pr.State(tmp_path).processed()
    assert pr.check_health(_et(2026, 10, 14, 17), pr.State(tmp_path))[0] is False


def test_inconsistent_state_is_refused(tmp_path):
    _run(tmp_path, _et(2026, 10, 13, 17))
    p = tmp_path / "runs" / "2026-10-12.json"
    rec = json.loads(p.read_text())
    rec["ledger_sha256"] = "0" * 64
    p.write_text(json.dumps(rec))
    with pytest.raises(pr.InconsistentState):
        _run(tmp_path, _et(2026, 10, 14, 17))
    assert "2026-10-14" not in pr.State(tmp_path).processed()


def test_risk_violation_is_refused():
    res = pl.replay(DATA, DATA.index_of(FIRST_SESSION), DATA.index_of(date(2026, 10, 14)))
    pl.check_risk(DATA, res)
    bad = res["V2-MOM"]
    import dataclasses
    lev = dataclasses.replace(bad, exposure=[1.2] * len(bad.exposure))
    with pytest.raises(pl.RiskViolation, match="leverage"):
        pl.check_risk(DATA, {**res, "V2-MOM": lev})
    over = dataclasses.replace(bad, decisions=[{"close": "2026-10-09", "targets": {t: 0.25 for t in TICKERS[:4]}}])
    with pytest.raises(pl.RiskViolation, match="target weight"):
        pl.check_risk(DATA, {**res, "V2-MOM": over})


def test_only_market_data_endpoints_are_reachable():
    pdata.check_endpoints()
    guarded = pdata.GuardedHttp(inner=None)
    for url in ("https://paper-api.alpaca.markets/v2/orders", "https://api.alpaca.markets/v2/orders"):
        with pytest.raises(pdata.EndpointGuardError):
            guarded.get_json(url, {})
    import pathlib
    src = " ".join(p.read_text(encoding="utf-8") for p in pathlib.Path(pdata.__file__).parent.glob("*.py"))
    assert "/v2/orders" not in src and "submit_order" not in src and "paper-api" not in src.replace("paper-api.alpaca.markets/v2/orders", "")


def test_runner_refuses_without_committed_v23_adoption(tmp_path):
    with pytest.raises(pr.RunnerError):
        pr.run(_et(2026, 10, 14, 17), state=pr.State(tmp_path), fetch=_fetcher(), key=KEY,
               adoption_check=lambda: pr.check_adoption_23(git_ok=lambda *_a: False))


# ------------------------------------------------------------------ seal

def test_seal_is_time_locked_and_authenticated(tmp_path):
    plain = b'{"equity_close": 123456.789, "weights": {"NVDA": 0.2}}'
    blob = ps.seal(plain, KEY)
    assert b"equity_close" not in blob and b"NVDA" not in blob
    with pytest.raises(ps.SealError, match="sealed until"):
        ps.unseal(blob, KEY, datetime(2026, 12, 9, 16, 14, tzinfo=NY))
    assert ps.unseal(blob, KEY, SEAL_UNTIL) == plain
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(ps.SealError, match="tag"):
        ps.unseal(tampered, KEY, SEAL_UNTIL)
    _run(tmp_path, _et(2026, 10, 13, 17))
    with pytest.raises(ps.SealError):
        pr.reveal(now=_et(2026, 12, 1, 12), state=pr.State(tmp_path), key=KEY)
    led = pr.reveal(date(2026, 10, 12), now=SEAL_UNTIL, state=pr.State(tmp_path), key=KEY)
    assert led["experiment"] == "V2-MOM-P001" and set(led["ledgers"]) == {"V2-MOM", "B1", "B2"}
    assert led["ledgers"]["V2-MOM"]["fills_today"] and led["strategy_config_sha256"].startswith("62827d70")


def test_cli_refuses_now_override_for_reveal_and_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PAPER_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(pr, "load_env", lambda *_a: None)
    for cmd in ("reveal", "run"):
        assert pr.main([cmd, "--now", "2027-01-01T00:00:00+00:00"]) == 2
        assert "--now is not accepted" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())                                    # refused before any state is touched


def test_seal_key_is_loaded_from_dotenv(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items() if k != "PAPER_SEAL_KEY"})
    env = tmp_path / ".env"
    env.write_text(f"PAPER_SEAL_KEY={KEY.hex()}\n", encoding="utf-8")
    pr.load_env(env)
    assert ps.load_key() == KEY


def test_successful_run_after_error_restores_health(tmp_path):
    _run(tmp_path, _et(2026, 10, 14, 17))
    with pytest.raises(pdata.DataFailClosed):
        _run(tmp_path, _et(2026, 10, 15, 17), fetch=lambda s: (DATA.truncate(DATA.index_of(s) - 1), {}))
    assert pr.check_health(_et(2026, 10, 15, 17, 1), pr.State(tmp_path))[0] is False
    _run(tmp_path, _et(2026, 10, 15, 18))                                    # recovered: processes 10-15
    assert pr.check_health(_et(2026, 10, 15, 18, 1), pr.State(tmp_path))[0] is True
    with pytest.raises(pr.RunnerError):                                     # preflight failure, then a NOOP run
        pr.run(_et(2026, 10, 15, 19), state=pr.State(tmp_path), fetch=_fetcher(), key=KEY,
               adoption_check=lambda: pr.check_adoption_23(git_ok=lambda *_a: False))
    assert pr.check_health(_et(2026, 10, 15, 19, 1), pr.State(tmp_path))[0] is False
    assert _run(tmp_path, _et(2026, 10, 15, 20))["status"] == "NOOP"
    assert pr.check_health(_et(2026, 10, 15, 20, 1), pr.State(tmp_path))[0] is True


def test_no_secret_in_any_state_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_SECRET_KEY", "SKVERYSECRET987")
    _run(tmp_path, _et(2026, 10, 14, 17))
    for p in tmp_path.rglob("*"):
        if p.is_file():
            b = p.read_bytes()
            assert b"SKVERYSECRET987" not in b and KEY.hex().encode() not in b


# ------------------------------------------------------------------ real data path (synthetic bars through derive)

def _frames(last: date, drop_last_for: str | None = None):
    sessions = pdata.sessions_between(HISTORY_START, last)
    idx = pd.DatetimeIndex([label_for(s) for s in sessions], name="datetime")
    rng = np.random.default_rng(3)
    frames = {"raw": {}, "all": {}}
    for t in TICKERS:
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(sessions))))
        df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6,
                           "trade_count": 1000.0, "provider_vwap": c}, index=idx)[list(BAR_COLUMNS)]
        if t == drop_last_for:
            df = df.iloc[:-1]
        frames["raw"][t], frames["all"][t] = df, df.copy()
    return {"session": last, "frames": frames, "ca": {"complete": [], "all": []},
            "ca_counts": {"Q1_complete": {}, "Q1_all": {}}, "q_syms": sorted(set(TICKERS) | {"FB"})}


def test_build_market_data_through_stage_h_derive(tmp_path):
    data, extra = pdata.build_market_data(_frames(date(2026, 10, 14)), FIRST_SESSION)
    assert data.sessions[-1] == date(2026, 10, 14) and data.tickers == TICKERS and extra["info"]["missing_bars"] == 0
    ref = pdata.snapshot(tmp_path, _frames(date(2026, 10, 14)), extra["events"])
    snap = tmp_path / "data" / f"2026-10-14-{ref[:12]}"
    assert len(ref) == 64 and (snap / "manifest.json").is_file()
    before = (snap / "manifest.json").read_bytes()
    assert pdata.snapshot(tmp_path, _frames(date(2026, 10, 14)), extra["events"]) == ref     # write-once
    corrected = _frames(date(2026, 10, 14))
    corrected["frames"]["raw"]["SPY"].iloc[-1, 0] *= 1.001                                  # vendor-corrected retry
    ref2 = pdata.snapshot(tmp_path, corrected, extra["events"])
    assert ref2 != ref and (tmp_path / "data" / f"2026-10-14-{ref2[:12]}" / "manifest.json").is_file()
    assert (snap / "manifest.json").read_bytes() == before                                 # old snapshot untouched
    with pytest.raises(pdata.DataFailClosed, match="structural|incomplete or stale"):   # §3.8 check trips first
        pdata.build_market_data(_frames(date(2026, 10, 14), drop_last_for="NVDA"), FIRST_SESSION)
