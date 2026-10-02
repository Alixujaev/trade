"""tests/test_day15a_acquisition.py: DAY-15A acquisition contract (no network, no OOS data).

yf.download is always faked; tests/conftest.py additionally blocks real network and cache writes.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from acquisition import provider_adapter
from acquisition.contract import (
    OOS_ROOT, OOS_SESSION_COUNT, RESEARCH_WINDOW_END, ROOT_DIR, STORED_COLUMNS, SUPPORTED_INTERVALS,
    ProviderConfig, oos_universe, validate_interval,
)
from acquisition.environment import capture_environment
from acquisition.provider_adapter import YFinanceAdapter, normalize_frame
from acquisition.sessions import resolve_oos_sessions
from acquisition.snapshot import (
    SnapshotPathError, build_metadata, compare_overlap, content_sha256, file_sha256, write_snapshot,
)
from acquisition.validation import structural_checks

ET = "America/New_York"
FORBIDDEN_PREFIXES = ("strategy", "signals", "backtest", "indicators", "smc", "levels", "journal", "risk",
                      "telegram_bot", "data")


def _raw(n=3, step=5, start="2026-06-01 09:30", tz=ET, adj_equal=True):
    idx = pd.date_range(start, periods=n, freq=f"{step}min", tz=tz)
    close = [100.0 + i for i in range(n)]
    return pd.DataFrame({
        "Open": [99.5 + i for i in range(n)], "High": [101.0 + i for i in range(n)],
        "Low": [99.0 + i for i in range(n)], "Close": close,
        "Adj Close": close if adj_equal else [c * 0.99 for c in close], "Volume": [1000 + i for i in range(n)],
    }, index=idx)


def _clean(**kw):
    return normalize_frame(_raw(**kw))


def _meta(df, sid="20261023_capture", sym="AAPL", iv="5m"):
    req = {"requested_start": "a", "requested_end": "b", "provider": "yfinance", "provider_version": "1.6.0",
           "provider_config": ProviderConfig().download_kwargs()}
    return build_metadata(df, symbol=sym, interval=iv, snapshot_id=sid, request=req,
                          checks=structural_checks(df, iv), environment_digest="x", acquisition_utc="2026-10-23T21:00:00+00:00")


# ---------------- contract / provider configuration ----------------

def test_contract_matches_day14_protocol():
    assert RESEARCH_WINDOW_END.isoformat() == "2026-09-25" and OOS_SESSION_COUNT == 60
    assert len(oos_universe()) == 25
    assert set(SUPPORTED_INTERVALS) == {"5m", "15m"}
    assert not OOS_ROOT.resolve().is_relative_to((ROOT_DIR / "data" / "cache").resolve())


@pytest.mark.parametrize("iv", ["5m", "15m"])
def test_supported_intervals_accepted(iv):
    assert validate_interval(iv) == SUPPORTED_INTERVALS[iv]


@pytest.mark.parametrize("iv", ["1m", "1h", "1d", "30m", ""])
def test_unsupported_interval_rejected(iv, monkeypatch):
    with pytest.raises(ValueError):
        validate_interval(iv)
    monkeypatch.setattr(provider_adapter.yf, "download", lambda *a, **k: pytest.fail("must not download"))
    with pytest.raises(ValueError):
        YFinanceAdapter().fetch("AAPL", iv, pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-06-02", tz="UTC"))


def test_all_provider_options_passed_explicitly(monkeypatch):
    seen = {}

    def fake(symbol, **kw):
        seen.update(kw, symbol=symbol)
        return _raw()

    monkeypatch.setattr(provider_adapter.yf, "download", fake)
    df, req = YFinanceAdapter().fetch("AAPL", "5m", pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-06-02", tz="UTC"))
    for k, v in {"auto_adjust": False, "back_adjust": False, "prepost": False, "actions": False, "repair": False,
                 "keepna": False, "ignore_tz": False, "threads": False, "progress": False}.items():
        assert k in seen and seen[k] is v, k
    assert "period" not in seen and "start" in seen and "end" in seen
    assert seen["interval"] == "5m"
    assert req["provider_config"]["auto_adjust"] is False and req["provider_config"]["prepost"] is False
    assert list(df.columns) == list(STORED_COLUMNS)


def test_adapter_does_not_clean_rows(monkeypatch):
    raw = _raw(n=4)
    raw = pd.concat([raw, raw.iloc[[1]]])  # duplicate row must survive to be detected, not silently dropped
    monkeypatch.setattr(provider_adapter.yf, "download", lambda s, **k: raw)
    df, _ = YFinanceAdapter().fetch("AAPL", "5m", pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-06-02", tz="UTC"))
    assert len(df) == 5 and structural_checks(df, "5m")["duplicate_timestamps"] == 1


# ---------------- timestamps ----------------

def test_timestamps_tz_aware_utc_and_bar_open_preserved():
    df = _clean()
    assert str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("2026-06-01 13:30", tz="UTC")  # 09:30 EDT bar OPEN stays 09:30
    assert df.index[0].tz_convert(ET).strftime("%H:%M") == "09:30"


def test_naive_index_refused():
    raw = _raw()
    raw.index = raw.index.tz_localize(None)
    with pytest.raises(ValueError):
        normalize_frame(raw)


@pytest.mark.parametrize("iv,step", [("5m", 5), ("15m", 15)])
def test_interval_grid_validated(iv, step):
    assert structural_checks(_clean(step=step), iv)["off_grid_bars"] == 0
    bad = _clean(step=step, start="2026-06-01 09:31")
    rep = structural_checks(bad, iv)
    assert rep["off_grid_bars"] > 0 and not rep["passed"]


def test_wrong_spacing_flagged_as_gap():
    df = _clean(step=5)
    rep = structural_checks(df.iloc[[0, 2]], "5m")
    assert rep["intra_session_gaps"] == 1


# ---------------- structural validation ----------------

def test_valid_frame_passes():
    rep = structural_checks(_clean(), "5m")
    assert rep["passed"], rep["errors"]
    assert rep["adj_close_equals_close_all_rows"] is True


def test_duplicate_detected():
    df = _clean()
    rep = structural_checks(pd.concat([df, df.iloc[[0]]]).sort_index(), "5m")
    assert rep["duplicate_timestamps"] == 1 and not rep["passed"]


def test_invalid_ohlc_rejected():
    df = _clean()
    df.iloc[1, df.columns.get_loc("high")] = df.iloc[1]["low"] - 1
    rep = structural_checks(df, "5m")
    assert rep["ohlc_inconsistent_rows"] == 1 and not rep["passed"]


def test_non_monotonic_rejected():
    df = _clean()
    rep = structural_checks(df.iloc[[1, 0, 2]], "5m")
    assert rep["monotonic_increasing"] is False and not rep["passed"]


def test_malformed_rejected():
    df = _clean()
    df.iloc[0, 0] = float("nan")
    assert not structural_checks(df, "5m")["passed"]
    assert not structural_checks(_clean().drop(columns=["volume"]), "5m")["passed"]
    neg = _clean()
    neg.iloc[0, neg.columns.get_loc("volume")] = -1
    assert structural_checks(neg, "5m")["negative_volume_rows"] == 1
    with pytest.raises(ValueError):
        normalize_frame(_raw().drop(columns=["Adj Close"]))


def test_non_rth_bar_flagged():
    rep = structural_checks(_clean(start="2026-06-01 09:20"), "5m")
    assert rep["non_rth_bars"] == 2 and not rep["passed"]


def test_adjustment_evidence_flag_and_no_price_statistics():
    rep = structural_checks(_clean(adj_equal=False), "5m")
    assert rep["adj_close_equals_close_all_rows"] is False and rep["adj_close_differs_rows"] == 3
    forbidden = ("return", "mean", "std", "pnl", "max_price", "min_price", "range", "vwap", "rsi", "signal")
    assert not [k for k in rep if any(f in k.lower() for f in forbidden)]


# ---------------- snapshot ----------------

def test_content_hash_deterministic_and_order_independent():
    df = _clean(n=5)
    assert content_sha256(df) == content_sha256(df.copy())
    assert content_sha256(df) == content_sha256(df.iloc[::-1])
    changed = df.copy()
    changed.iloc[2, 0] += 0.01
    assert content_sha256(changed) != content_sha256(df)


def test_metadata_deterministic_and_complete():
    df = _clean()
    m1, m2 = _meta(df), _meta(df)
    assert m1 == m2
    for k in ("schema_version", "protocol_version", "snapshot_id", "symbol", "interval", "acquisition_utc",
              "requested_start", "requested_end", "actual_first_timestamp", "actual_last_timestamp", "row_count",
              "timezone", "provider", "provider_version", "provider_config", "content_sha256", "structural_checks"):
        assert k in m1
    assert m1["provider_config"]["auto_adjust"] is False and m1["timezone"] == "UTC"


def test_write_snapshot_hashes_and_readonly(tmp_path):
    df = _clean()
    res = write_snapshot(tmp_path, "s1", "AAPL", "5m", df, _meta(df, sid="s1"))
    assert res["status"] == "WRITTEN"
    p = Path(res["data_path"])
    meta = json.loads(p.with_name("AAPL_5m.meta.json").read_text())
    assert meta["file_sha256"] == file_sha256(p)
    assert content_sha256(pd.read_parquet(p)) == meta["content_sha256"]
    assert not os.access(p, os.W_OK)


def test_existing_snapshot_never_overwritten_identical_recorded(tmp_path):
    df = _clean()
    first = write_snapshot(tmp_path, "s1", "AAPL", "5m", df, _meta(df, sid="s1"))
    before = Path(first["data_path"]).read_bytes()
    again = write_snapshot(tmp_path, "s1", "AAPL", "5m", df, _meta(df, sid="s1"))
    assert again["status"] == "IDENTICAL"
    assert Path(first["data_path"]).read_bytes() == before
    assert len(list((tmp_path / "snapshots" / "s1" / "attempts").glob("*.json"))) == 1


def test_changed_repeat_flagged_and_both_preserved(tmp_path):
    df = _clean()
    first = write_snapshot(tmp_path, "s1", "AAPL", "5m", df, _meta(df, sid="s1"))
    before = Path(first["data_path"]).read_bytes()
    revised = df.copy()
    revised.iloc[1, revised.columns.get_loc("close")] += 0.05
    rec = write_snapshot(tmp_path, "s1", "AAPL", "5m", revised, _meta(revised, sid="s1"))
    assert rec["status"] == "DISCREPANCY"
    assert Path(first["data_path"]).read_bytes() == before
    assert content_sha256(pd.read_parquet(rec["conflict_path"])) == content_sha256(revised)
    assert rec["overlap"]["differing_rows"] == 1 and rec["overlap"]["differing_cells_by_column"]["close"] == 1


def test_overlap_comparison_reports_differences_without_choosing():
    a = _clean(n=4)
    b = _clean(n=6)
    b.iloc[2, b.columns.get_loc("volume")] += 7
    r = compare_overlap(a, b)
    assert r["common_timestamps"] == 4 and r["only_in_a"] == 0 and r["only_in_b"] == 2
    assert r["differing_rows"] == 1 and r["identical_on_overlap"] is False
    assert compare_overlap(a, a)["identical_on_overlap"] is True


def test_metadata_hash_must_match_frame(tmp_path):
    df = _clean()
    m = _meta(df)
    other = _clean(n=4)
    with pytest.raises(ValueError):
        write_snapshot(tmp_path, "s1", "AAPL", "5m", other, m)


@pytest.mark.parametrize("target", ["data/cache", "artifacts/day15"])
def test_writes_into_research_cache_or_artifacts_refused(target):
    df = _clean()
    with pytest.raises(SnapshotPathError):
        write_snapshot(ROOT_DIR / target, "s1", "AAPL", "5m", df, _meta(df))
    assert not (ROOT_DIR / target / "snapshots").exists()


def test_pipeline_end_to_end_with_fake_provider(monkeypatch, tmp_path):
    from acquisition.pipeline import acquire_one

    monkeypatch.setattr(provider_adapter.yf, "download", lambda s, **k: _raw(n=4))
    env = {"environment_sha256": "e" * 64, "git_commit": "abc", "git_dirty": False, "distributions": []}
    start, end = pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-06-02", tz="UTC")
    res = acquire_one(YFinanceAdapter(), tmp_path, "s1", "AAPL", "5m", start, end, env)
    assert res["status"] == "WRITTEN" and res["structural_checks_passed"]
    meta = json.loads((tmp_path / "snapshots" / "s1" / "AAPL_5m.meta.json").read_text())
    assert meta["session_rule"].startswith("first 60 NYSE sessions") and meta["environment_sha256"] == "e" * 64
    assert (tmp_path / "snapshots" / "s1" / "environment.json").exists()
    assert acquire_one(YFinanceAdapter(), tmp_path, "s1", "AAPL", "5m", start, end, env)["status"] == "IDENTICAL"


# ---------------- separation ----------------

def _module_files():
    return sorted((ROOT_DIR / "acquisition").glob("*.py")) + [ROOT_DIR / "scripts" / "acquire_oos_data.py"]


def test_no_forbidden_imports_static():
    for f in _module_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        bad = [m for m in names if m.split(".")[0] in FORBIDDEN_PREFIXES]
        assert not bad, (f.name, bad)


def test_no_forbidden_modules_loaded_at_runtime():
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import acquisition.contract, acquisition.provider_adapter, acquisition.validation, acquisition.snapshot,"
        " acquisition.environment, acquisition.sessions, acquisition.pipeline, acquisition.capture_policy,"
        " acquisition.run, acquisition.report;"
        "print(sorted({m.split('.')[0] for m in sys.modules} & set(%r)))" % (ROOT_DIR, FORBIDDEN_PREFIXES)
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]", out


# ---------------- calendar / CLI / environment ----------------

def test_oos_sessions_resolved_by_pinned_calendar():
    # DAY-15A blocker resolved in finalization: exchange_calendars XNYS (see test_day15b_acquisition.py).
    assert len(resolve_oos_sessions()) == OOS_SESSION_COUNT


def test_cli_dry_run_no_network_and_mode_required(monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("acquire_oos_data", ROOT_DIR / "scripts" / "acquire_oos_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(provider_adapter.yf, "download", lambda *a, **k: pytest.fail("dry run must not download"))
    assert mod.main(["--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["oos_sessions"]) == 60 and plan["calendar"]["package"] == "exchange_calendars"
    assert len(plan["symbols"]) == 25 and plan["provider_config"]["auto_adjust"] is False
    with pytest.raises(SystemExit):  # a mode is mandatory; nothing runs implicitly
        mod.main([])


def test_environment_manifest_captures_exact_versions():
    env = capture_environment()
    assert any(d.lower().startswith("yfinance==") for d in env["distributions"])
    assert len(env["distributions_sha256"]) == 64 and env["python_version"]
