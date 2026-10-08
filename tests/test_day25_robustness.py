"""tests/test_day25_robustness.py — Governance and structural tests for DAY-25.

These tests verify:
  1. The DAY-25 report artifact exists and has the expected SHA-256.
  2. All 6 study files exist and are structurally valid.
  3. Zero forward data contamination (all sessions are <= 2026-10-07).
  4. Frozen V2-MOM config SHA-256 is unchanged.
  5. Sensitivity studies cover the expected grids.
  6. Universe-drop study has exactly 25 rows (one per symbol).
  7. All universe-drop variants beat B1 (active_return > 0).
  8. Rolling-persistence study has valid data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DAY25 = ROOT / "artifacts" / "day25"
FROZEN_MOM_SHA = "62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0"
LAST_ALLOWED = "2026-10-07"
REPORT_SHA = "5d80b61c41728e9b887e936686d11848a7a04ff3921d6e346e837f095df0f0ee"


@pytest.fixture(scope="module")
def report():
    path = DAY25 / "day25-robustness-report.json"
    assert path.exists(), f"DAY-25 report missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── 1. Report integrity ──────────────────────────────────────────────────────

def test_report_sha256():
    path = DAY25 / "day25-robustness-report.json"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha == REPORT_SHA, f"Report SHA-256 mismatch: {sha} != {REPORT_SHA}"


def test_report_schema_version(report):
    assert report["schema_version"] == "1.0"
    assert report["task"] == "DAY-25"


# ── 2. Governance flags ──────────────────────────────────────────────────────

def test_no_forward_data_accessed(report):
    assert report["governance"]["forward_data_accessed"] is False


def test_strategy_not_modified(report):
    assert report["governance"]["strategy_modified"] is False


def test_frozen_mom_sha_unchanged(report):
    assert report["governance"]["frozen_mom_config_sha256"] == FROZEN_MOM_SHA


# ── 3. All study files exist ─────────────────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "study1_lookback_sensitivity.json",
    "study2_skip_sensitivity.json",
    "study3_select_sensitivity.json",
    "study4_universe_drop_stability.json",
    "study5_rolling_persistence.json",
    "study6_cross_segment_summary.json",
])
def test_study_file_exists(filename):
    path = DAY25 / filename
    assert path.exists(), f"Study file missing: {filename}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ── 4. Study 1: Lookback grid ────────────────────────────────────────────────

def test_study1_lookback_grid():
    data = json.loads((DAY25 / "study1_lookback_sensitivity.json").read_text())
    rows = data["rows"]
    grid = data["grid"]
    assert set(grid) == {126, 189, 252, 315}
    assert len(rows) == 4
    frozen = [r for r in rows if r["is_frozen"]]
    assert len(frozen) == 1
    assert frozen[0]["lookback_sessions"] == 252
    # All variants beat B1
    for r in rows:
        assert r["active_return"] > 0, f"LB={r['lookback_sessions']} did not beat B1"


# ── 5. Study 2: Skip-lag grid ────────────────────────────────────────────────

def test_study2_skip_grid():
    data = json.loads((DAY25 / "study2_skip_sensitivity.json").read_text())
    rows = data["rows"]
    assert len(rows) >= 3   # at least 3 (skip=252 is excluded as degenerate)
    frozen = [r for r in rows if r["is_frozen"]]
    assert len(frozen) == 1
    assert frozen[0]["skip_sessions"] == 21
    for r in rows:
        assert r["active_return"] > 0, f"Skip={r['skip_sessions']} did not beat B1"


# ── 6. Study 3: Selection-size grid ─────────────────────────────────────────

def test_study3_select_grid():
    data = json.loads((DAY25 / "study3_select_sensitivity.json").read_text())
    rows = data["rows"]
    assert set(data["grid"]) == {3, 5, 7, 10}
    assert len(rows) == 4
    frozen = [r for r in rows if r["is_frozen"]]
    assert len(frozen) == 1
    assert frozen[0]["select_n"] == 5
    for r in rows:
        assert r["active_return"] > 0, f"N={r['select_n']} did not beat B1"


# ── 7. Study 4: Universe drop stability ─────────────────────────────────────

def test_study4_exactly_25_symbols():
    data = json.loads((DAY25 / "study4_universe_drop_stability.json").read_text())
    rows = [r for r in data["rows"] if "error" not in r]
    assert len(rows) == 25, f"Expected 25 drop rows, got {len(rows)}"


def test_study4_all_beat_b1():
    data = json.loads((DAY25 / "study4_universe_drop_stability.json").read_text())
    for row in data["rows"]:
        if "error" in row:
            continue
        assert row["active_return"] > 0, f"Drop {row['drop']}: did not beat B1 (active={row['active_return']:.4f})"


def test_study4_delta_bounded():
    """No single symbol drop should catastrophically destroy the signal (> 10 pp loss)."""
    data = json.loads((DAY25 / "study4_universe_drop_stability.json").read_text())
    for row in data["rows"]:
        if "error" in row:
            continue
        assert row["delta_vs_full_mom"] > -0.10, \
            f"Drop {row['drop']}: catastrophic loss {row['delta_vs_full_mom']:.4f}"


# ── 8. Study 5: Rolling persistence ─────────────────────────────────────────

def test_study5_rolling_windows():
    data = json.loads((DAY25 / "study5_rolling_persistence.json").read_text())
    assert data["n_windows"] > 0
    rows = data["rows"]
    assert len(rows) == data["n_windows"]
    # All sessions must be <= LAST_ALLOWED
    for r in rows:
        assert r["window_end_session"] <= LAST_ALLOWED, \
            f"Forward data contamination: {r['window_end_session']}"


def test_study5_beat_rate_reasonable():
    data = json.loads((DAY25 / "study5_rolling_persistence.json").read_text())
    beat_pct = data["pct_windows_beat_b1"]
    # Should be between 10% and 90% (not trivially perfect or broken)
    assert 10 <= beat_pct <= 90, f"Rolling beat rate implausible: {beat_pct}%"


# ── 9. Study 6: Cross-segment ────────────────────────────────────────────────

def test_study6_both_segments_beat_b1():
    data = json.loads((DAY25 / "study6_cross_segment_summary.json").read_text())
    combined = data["summary"]["combined_observation"]
    assert combined["both_segments_beat_b1"] is True


def test_study6_total_sessions():
    data = json.loads((DAY25 / "study6_cross_segment_summary.json").read_text())
    combined = data["summary"]["combined_observation"]
    # Research 1490 + Holdout 856 = 2346
    assert combined["total_sessions"] == 2346


# ── 10. Reference runs sanity check ─────────────────────────────────────────

def test_reference_runs_beat_b1(report):
    r_mom  = report["reference_runs"]["research_V2-MOM_5bps_cagr"]
    r_b1   = report["reference_runs"]["research_B1_5bps_cagr"]
    h_mom  = report["reference_runs"]["holdout_V2-MOM_5bps_cagr"]
    h_b1   = report["reference_runs"]["holdout_B1_5bps_cagr"]
    assert r_mom > r_b1, "Reference V2-MOM did not beat B1 on Stage R"
    assert h_mom > h_b1, "Reference V2-MOM did not beat B1 on Stage H"


def test_reference_cagrs_plausible(report):
    """Reference CAGRs must be in a plausible range (0–200%)."""
    for key, val in report["reference_runs"].items():
        assert 0.0 < val < 2.0, f"{key}: implausible CAGR {val}"
