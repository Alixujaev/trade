"""tests/test_orb_snapshot_input.py: backtest/orb_snapshot_input.py (synthetic snapshot in tmp_path, offline).

No real snapshot, no network, no main(). Fixture pins are computed from the fixture files; the production pins are
asserted separately against artifacts/orb/sip_diagnostic_decision.md.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from acquisition.v1_1.contract import AlpacaBarsConfig
from acquisition.v1_1.sessions import research_acquisition_sessions
from acquisition.validation import expected_bar_opens
from backtest import orb_snapshot_input as osi
from backtest.orb_engine import run_orb_backtest
from backtest.orb_snapshot_input import (PINNED, RESEARCH_FIRST, RESEARCH_LAST, SnapshotInputError, SnapshotPins,
                                         load_research_frames, validate_frame)
from data.earnings import load_earnings_calendar
from data.session import NY_TZ, get_session_dates
from data.v11_research_loader import load_v11_research
from strategy.day.orb_rules import OrbRules

ROOT = Path(__file__).resolve().parent.parent
SESS = research_acquisition_sessions()
RESEARCH = [s.session for s in SESS if s.segment == "research"]
SYMS = ["AAPL", "MSFT"]
STORED = ["open", "high", "low", "close", "volume", "trade_count", "provider_vwap"]
BREAKOUT_SESSION = RESEARCH[1]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _et(d: date, t: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(d, t), tz=NY_TZ).tz_convert("UTC")


def _bars(sym: str, iv: str) -> pd.DataFrame:
    idx = pd.DatetimeIndex([t for s in SESS for t in expected_bar_opens(s, iv)], name="datetime")
    df = pd.DataFrame({"open": 100.0, "high": 100.05, "low": 99.95, "close": 100.0, "volume": 1000.0,
                       "trade_count": 10.0, "provider_vwap": 100.0}, index=idx)[STORED]
    if sym == "AAPL" and iv == "5m":                       # one ORB breakout: signal 09:50, entry 09:55 (stops out)
        df.loc[_et(BREAKOUT_SESSION, time(9, 50)), ["high", "close", "volume"]] = [101.1, 101.0, 5000.0]
    return df


def build(tmp: Path, *, name: str = "research_test", frame_mutate=None, units_mutate=None, run_mutate=None,
          files_mutate=None) -> tuple[Path, SnapshotPins]:
    snap = tmp / "snapshots" / name
    snap.mkdir(parents=True)
    files: dict[str, dict] = {}
    for sym in SYMS:
        for iv in ("5m", "15m"):
            df = _bars(sym, iv)
            if frame_mutate:
                df = frame_mutate(sym, iv, df)
            p = snap / f"{sym}_{iv}.parquet"
            df.to_parquet(p)
            files[p.name] = {"file_sha256": _sha(p)}
    units = [{"session": s.session.isoformat(), "segment": s.segment, "symbol": sym, "interval": iv,
              "status": "COMPLETE", "request": {"params": {"feed": "sip", "adjustment": "raw"}}}
             for s in SESS for sym in SYMS for iv in ("5m", "15m")]
    run = {"provider_config": AlpacaBarsConfig().as_dict(), "symbols": list(SYMS), "git_commit": "fixture"}
    for hook, obj in ((files_mutate, files), (units_mutate, units), (run_mutate, run)):
        if hook:
            hook(obj)
    for fname, obj in (("files.json", files), ("units.json", units), ("run.json", run)):
        (snap / fname).write_text(json.dumps(obj), encoding="utf-8")
    pins = SnapshotPins(name, _sha(snap / "files.json"), _sha(snap / "units.json"), _sha(snap / "run.json"))
    return snap, pins


# ------------------------------------------------------------------ production constants

def test_production_pins_match_decision_record():
    assert PINNED == SnapshotPins(
        snapshot_id="research_20261006T095201Z",
        files_json_sha256="b43b8996d1e45a58c61aba74bc8bc83b173809e554f4c0c125c0f4f5f6b95139",
        units_json_sha256="6a0466192a87ce53cb27d8b5e55a4fb510f8e790d8cc75548b6e9987a3b76b74",
        run_json_sha256="8b57b2dad2c22b69dee25845ef6d4d3520811088124c35b3b668e6fb510a4278",
    )
    record = (ROOT / "artifacts" / "orb" / "sip_diagnostic_decision.md").read_text(encoding="utf-8")
    for value in (PINNED.snapshot_id, PINNED.files_json_sha256, PINNED.units_json_sha256, PINNED.run_json_sha256):
        assert value in record
    assert (RESEARCH_FIRST, RESEARCH_LAST, osi.RESEARCH_SESSIONS, osi.INTERVAL) == (
        date(2026, 7, 2), date(2026, 9, 25), 60, "5m")
    assert RESEARCH[0] == RESEARCH_FIRST and RESEARCH[-1] == RESEARCH_LAST and len(RESEARCH) == 60


# ------------------------------------------------------------------ happy path

def test_returns_research_only_frames_and_provenance(tmp_path):
    snap, pins = build(tmp_path)
    res = load_research_frames(snap, SYMS, pins=pins)
    assert sorted(res.bars) == SYMS
    for df in res.bars.values():
        assert list(df.columns) == osi.OHLCV
        assert str(df.index.tz) == "UTC"
        sessions = sorted(set(get_session_dates(df.index)))
        assert sessions == RESEARCH and len(df) == 60 * 78        # warmup and embargo bars are not returned
    p = res.provenance
    assert (p["snapshot_id"], p["files_json_sha256"], p["units_json_sha256"], p["run_json_sha256"]) == (
        pins.snapshot_id, pins.files_json_sha256, pins.units_json_sha256, pins.run_json_sha256)
    assert p["provider_config"] == AlpacaBarsConfig().as_dict()
    assert (p["research_first"], p["research_last"], p["research_sessions"]) == ("2026-07-02", "2026-09-25", 60)
    assert p["warmup_supplied"] is False and p["rth_only"] is True and p["symbols"] == SYMS


# ------------------------------------------------------------------ identity / request checks

def test_directory_must_exist_and_match_pinned_id(tmp_path):
    snap, pins = build(tmp_path)
    with pytest.raises(SnapshotInputError, match="not found"):
        load_research_frames(tmp_path / "absent", SYMS, pins=pins)
    with pytest.raises(SnapshotInputError, match="pinned"):
        load_research_frames(snap, SYMS, pins=replace(pins, snapshot_id="research_other"))


@pytest.mark.parametrize("symbols, match", [([], "no symbols"), (["AAPL", "AAPL"], "duplicate")])
def test_bad_symbol_requests_rejected(tmp_path, symbols, match):
    snap, pins = build(tmp_path)
    with pytest.raises(SnapshotInputError, match=match):
        load_research_frames(snap, symbols, pins=pins)


def test_symbol_missing_from_run_json_rejected(tmp_path):
    snap, pins = build(tmp_path, run_mutate=lambda r: r.update(symbols=["AAPL"]))
    with pytest.raises(SnapshotInputError, match="not in snapshot run.json"):
        load_research_frames(snap, SYMS, pins=pins)


@pytest.mark.parametrize("field", ["files_json_sha256", "units_json_sha256", "run_json_sha256"])
def test_each_pin_mismatch_rejected(tmp_path, field):
    snap, pins = build(tmp_path)
    with pytest.raises(SnapshotInputError, match=field):
        load_research_frames(snap, SYMS, pins=replace(pins, **{field: "0" * 64}))


def _set_cfg(key, value):
    def hook(run):
        cfg = dict(run["provider_config"])
        cfg[key] = value
        run["provider_config"] = cfg
    return hook


@pytest.mark.parametrize("hook", [_set_cfg("feed", "iex"), _set_cfg("adjustment", "all"),
                                  lambda r: r.pop("provider_config")])
def test_provider_config_rejected(tmp_path, hook):
    snap, pins = build(tmp_path, run_mutate=hook)
    with pytest.raises(SnapshotInputError, match="provider_config"):
        load_research_frames(snap, SYMS, pins=pins)


@pytest.mark.parametrize("hook, match", [
    (lambda u: u[0]["request"]["params"].update(feed="iex"), "feed='iex'"),
    (lambda u: u[-1]["request"]["params"].update(adjustment="all"), "adjustment='all'"),
    (lambda u: u[5].pop("request"), "no recorded request params"),
])
def test_unit_level_provenance_rejected(tmp_path, hook, match):
    snap, pins = build(tmp_path, units_mutate=hook)
    with pytest.raises(SnapshotInputError, match=match):
        load_research_frames(snap, SYMS, pins=pins)


# ------------------------------------------------------------------ loader failures are wrapped

def _add_oos_bar(sym, iv, df):
    if sym != "AAPL" or iv != "5m":
        return df
    extra = df.iloc[[-1]].copy()
    extra.index = pd.DatetimeIndex([pd.Timestamp("2026-09-29T13:30:00Z")], name="datetime")
    return pd.concat([df, extra])


@pytest.mark.parametrize("kwargs", [
    {"files_mutate": lambda f: f["AAPL_5m.parquet"].update(file_sha256="0" * 64)},
    {"units_mutate": lambda u: u[0].update(status="MISSING")},
    {"frame_mutate": _add_oos_bar},
])
def test_loader_rejections_are_wrapped(tmp_path, kwargs):
    snap, pins = build(tmp_path, **kwargs)
    with pytest.raises(SnapshotInputError, match="loader rejected") as exc:
        load_research_frames(snap, SYMS, pins=pins)
    assert exc.value.__cause__ is not None


def test_missing_parquet_is_wrapped(tmp_path):
    snap, pins = build(tmp_path)
    (snap / "MSFT_15m.parquet").unlink()
    with pytest.raises(SnapshotInputError, match="loader rejected"):
        load_research_frames(snap, SYMS, pins=pins)


# ------------------------------------------------------------------ validate_frame

def _good() -> tuple[pd.DataFrame, set[date]]:
    d = RESEARCH[0]
    s = next(x for x in SESS if x.session == d)
    df = pd.DataFrame({"open": 100.0, "high": 100.05, "low": 99.95, "close": 100.0, "volume": 1000.0},
                      index=pd.DatetimeIndex(expected_bar_opens(s, "5m"), name="datetime"))
    return df, {d}


def _replace_index(df, i, ts):
    idx = list(df.index)
    idx[i] = ts
    out = df.copy()
    out.index = pd.DatetimeIndex(idx, name="datetime")
    return out


def test_validate_frame_accepts_clean_frame():
    df, sessions = _good()
    before = df.copy()
    validate_frame("AAPL", df, sessions)
    pd.testing.assert_frame_equal(df, before)                           # never modifies its input


@pytest.mark.parametrize("make, match", [
    (lambda df: df.iloc[:0], "empty"),
    (lambda df: df.drop(columns="volume"), "columns"),
    (lambda df: df.assign(extra=1.0), "columns"),
    (lambda df: df.reset_index(drop=True), "DatetimeIndex"),
    (lambda df: df.tz_localize(None), "timezone"),
    (lambda df: df.tz_convert(NY_TZ), "timezone"),
    (lambda df: pd.concat([df, df.iloc[[0]]]), "duplicate"),
    (lambda df: df.iloc[::-1], "monotonic"),
    (lambda df: _replace_index(df, 0, pd.Timestamp("2026-07-02T13:00:00Z")), "outside RTH"),
    (lambda df: df.assign(close=df["close"].where(df.index != df.index[3], np.nan)), "NaN"),
])
def test_validate_frame_rejections(make, match):
    df, sessions = _good()
    with pytest.raises(SnapshotInputError, match=match):
        validate_frame("AAPL", make(df), sessions)


def test_validate_frame_rejects_non_research_session():
    df, _ = _good()
    with pytest.raises(SnapshotInputError, match="non-research"):
        validate_frame("AAPL", df, {RESEARCH[1]})


# ------------------------------------------------------------------ no network / no providers

def test_helper_imports_no_network_provider_or_paper_modules():
    tree = ast.parse((ROOT / "backtest" / "orb_snapshot_input.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    forbidden = ("requests", "socket", "urllib", "http", "yfinance", "alpaca", "data.factory", "data.provider",
                 "data.alpaca_provider", "data.yfinance_provider", "paper", "paper_orb")
    bad = sorted(n for n in names if any(n == f or n.startswith(f + ".") for f in forbidden))
    assert not bad, bad


# ------------------------------------------------------------------ bridge to the unchanged engine

def test_engine_ledger_identical_to_direct_frames_and_first_session_has_no_prior_close(tmp_path):
    snap, pins = build(tmp_path)
    via_helper = load_research_frames(snap, SYMS, pins=pins).bars
    direct_data = load_v11_research(snap, symbols=SYMS)
    direct = {s: direct_data.frame(s, "5m", ("research",)) for s in SYMS}
    cal_path = tmp_path / "earnings.csv"
    cal_path.write_text("symbol,coverage_start,coverage_end,earnings_date\n"
                        + "".join(f"{s},{RESEARCH_FIRST},{RESEARCH_LAST},\n" for s in SYMS), encoding="utf-8")
    cal = load_earnings_calendar(cal_path)
    rules = OrbRules(initial_capital=100_000.0)
    a = run_orb_backtest(via_helper, rules, cal, RESEARCH_FIRST, RESEARCH_LAST)
    b = run_orb_backtest(direct, rules, cal, RESEARCH_FIRST, RESEARCH_LAST)
    assert a.sessions == b.sessions == RESEARCH
    assert a.trades == b.trades and a.skips == b.skips and a.carry.to_dict() == b.carry.to_dict()
    assert len(a.trades) == 1 and a.trades[0]["symbol"] == "AAPL"
    assert a.trades[0]["session"] == BREAKOUT_SESSION.isoformat()
    npc = [k for k in a.skips if k["reason"] == "no_prior_close"]
    assert sorted(k["symbol"] for k in npc) == SYMS
    assert {k["session"] for k in npc} == {RESEARCH_FIRST.isoformat()}
