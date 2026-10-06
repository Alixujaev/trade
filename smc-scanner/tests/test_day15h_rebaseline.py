"""tests/test_day15h_rebaseline.py: v1.1 research loader + re-baseline helpers (synthetic data, offline)."""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pytest

from acquisition.validation import expected_bar_opens
from acquisition.v1_1.sessions import research_acquisition_sessions
from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.v11_rebaseline import cost_return, mutate_from, research_gate, trade_key, trade_session
from data.session import to_eastern
from data.v11_research_loader import V11DataError, load_v11_research

SESS = research_acquisition_sessions()
COLS = ["open", "high", "low", "close", "volume", "trade_count", "provider_vwap"]


def _frame(interval: str) -> pd.DataFrame:
    idx = pd.DatetimeIndex([t for s in SESS for t in expected_bar_opens(s, interval)], name="datetime")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
                       "trade_count": 10.0, "provider_vwap": 100.2}, index=idx)
    return df[COLS]


def _snapshot(tmp: Path, mutate=None) -> Path:
    snap = tmp / "snapshots" / "research_test"
    snap.mkdir(parents=True)
    files, units = {}, []
    for iv in ("5m", "15m"):
        df = _frame(iv)
        if mutate:
            df = mutate(iv, df)
        p = snap / f"AAPL_{iv}.parquet"
        df.to_parquet(p)
        files[p.name] = {"file_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        units += [{"session": s.session.isoformat(), "segment": s.segment, "symbol": "AAPL", "interval": iv,
                   "status": "COMPLETE"} for s in SESS]
    (snap / "files.json").write_text(json.dumps(files))
    (snap / "units.json").write_text(json.dumps(units))
    (snap / "run.json").write_text(json.dumps({"provider_config": {"feed": "sip", "adjustment": "raw"}, "git_commit": "x"}))
    return snap


def test_loader_excludes_embargo_and_provider_fields(tmp_path):
    d = load_v11_research(_snapshot(tmp_path), symbols=["AAPL"])
    assert (len(d.warmup_sessions), len(d.research_sessions), len(d.embargo_sessions)) == (20, 60, 1)
    df = d.frames["AAPL"]["5m"]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    sessions = set(to_eastern(df.index).date)
    assert date(2026, 9, 28) not in sessions and len(sessions) == 80
    assert len(d.frame("AAPL", "5m", ("research",))) == 60 * 78


def test_loader_rejects_oos_timestamp(tmp_path):
    def add_oos(iv, df):
        extra = df.iloc[[-1]].copy()
        extra.index = pd.DatetimeIndex([pd.Timestamp("2026-09-29T13:30:00Z")], name="datetime")
        return pd.concat([df, extra])
    with pytest.raises(V11DataError):
        load_v11_research(_snapshot(tmp_path, add_oos), symbols=["AAPL"])


def test_loader_rejects_hash_mismatch_and_adj_close(tmp_path):
    snap = _snapshot(tmp_path)
    files = json.loads((snap / "files.json").read_text())
    files["AAPL_5m.parquet"]["file_sha256"] = "0" * 64
    (snap / "files.json").write_text(json.dumps(files))
    with pytest.raises(V11DataError):
        load_v11_research(snap, symbols=["AAPL"])
    with pytest.raises(V11DataError):
        load_v11_research(_snapshot(tmp_path / "b", lambda iv, df: df.assign(adj_close=df["close"])), symbols=["AAPL"])


def test_loader_rejects_symbol_outside_universe(tmp_path):
    with pytest.raises(V11DataError):
        load_v11_research(_snapshot(tmp_path), symbols=["ZZZZ"])


def _trade(setup="2026-07-02T14:00:00Z", entry=100.0, exit_=101.0, **kw):
    ts = pd.Timestamp(setup)
    return DayBacktestTrade(symbol="AAPL", setup_time=ts, entry_time=ts + pd.Timedelta(minutes=5), entry_price=entry,
                            exit_time=ts + pd.Timedelta(minutes=30), exit_price=exit_, exit_reason="target",
                            net_return=(exit_ - entry) / entry, **kw)


def test_cost_formula_matches_protocol():
    t = _trade(entry=100.0, exit_=101.0)
    g, s = 0.01, 0.0005
    assert cost_return(t, 0.0, ExecutionConfig()) == pytest.approx(g)
    assert cost_return(t, 5.0, ExecutionConfig()) == pytest.approx((1 + g) * (1 - s) / (1 + s) - 1)


def test_trade_key_is_nan_safe_and_session_uses_et():
    a, b = _trade(), _trade()
    assert math.isnan(a.rsi_at_setup)   # NaN fields make dataclass equality unreliable; trade_key is not
    assert trade_key(a) == trade_key(b)
    assert trade_session(_trade(setup="2026-07-02T23:30:00Z")) == date(2026, 7, 2)


def test_mutate_from_only_touches_selected_sessions_and_keeps_ohlc_valid():
    df = _frame("5m")[["open", "high", "low", "close", "volume"]]
    m = mutate_from(df, date(2026, 9, 14))
    sess = pd.Series(to_eastern(df.index).date, index=df.index)
    before = (sess < date(2026, 9, 14)).to_numpy()
    assert m.loc[before].equals(df.loc[before]) and not m.loc[~before].equals(df.loc[~before])
    assert ((m["high"] >= m[["open", "close"]].max(axis=1)) & (m["low"] <= m[["open", "close"]].min(axis=1))).all()


@pytest.mark.parametrize("value,hard,expected", [
    (0.0, {"pit": True, "determinism": True}, "PASS"),
    (0.01, {"pit": True, "determinism": True}, "PASS"),
    (-0.0001, {"pit": True, "determinism": True}, "FAIL"),
    (0.5, {"pit": False, "determinism": True}, "FAIL"),
])
def test_research_gate_has_only_the_predeclared_condition(value, hard, expected):
    g = research_gate(value, hard)
    assert g["decision"] == expected and g["primary_condition"] == ">= 0"
