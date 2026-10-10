"""tests/test_day26c_incident.py: DAY-26C forward-data incident containment (offline; no market data read).

- The market-data guard is active before module-scoped fixtures run (root cause of the incident). Checked by
  identity and by a local write attempt only; no download function is ever called here.
- fwd-diag is FWD-DIAG-INVALID (protocol-breach) and refused by every forward entry point.
- Quarantined incident files cannot re-enter any project data path unnoticed.
- The incident disclosure is append-only and pinned; fwd-gate stays PENDING and unchanged.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

import tests.conftest as guard
from acquisition.contract import ROOT_DIR
from acquisition.v2 import stage_f as sf
from backtest.v2 import data as dt
from backtest.v2 import forward as fw
from backtest.v2 import run as rn
from config.settings import CACHE_DIR
from data import alpaca_provider as alpaca_module
from data import yfinance_provider as yfp_module

NY = ZoneInfo("America/New_York")
LATE = datetime(2027, 1, 8, 12, 0, tzinfo=NY)
INCIDENT = json.loads((ROOT_DIR / fw.INCIDENT_FILES[1]).read_text(encoding="utf-8"))
ADOPTION = json.loads((ROOT_DIR / fw.ADOPTION_JSON).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ root cause: guard before module-scoped fixtures

@pytest.fixture(scope="module")
def guards_seen_by_a_module_fixture():
    """Runs before every function-scoped fixture of this module, exactly like tests/test_day08_backtest.py:42."""
    seen = {"download": yfp_module.yf.download is guard._network_disabled,
            "ticker_history": yfp_module.yf.Ticker.history is guard._network_disabled,
            "alpaca_fetch": alpaca_module.AlpacaProvider._fetch_raw is guard._network_disabled}
    try:
        yfp_module.YFinanceProvider._write_cache(pd.DataFrame({"close": [1.0]}), CACHE_DIR / "probe_5m.parquet")
        seen["real_cache_write"] = "ALLOWED"
    except guard.CacheMutationError:
        seen["real_cache_write"] = "refused"
    return seen


def test_market_data_guard_is_active_inside_module_scoped_fixtures(guards_seen_by_a_module_fixture):
    assert guards_seen_by_a_module_fixture == {"download": True, "ticker_history": True, "alpaca_fetch": True,
                                                "real_cache_write": "refused"}
    assert not (CACHE_DIR / "probe_5m.parquet").exists()


# ------------------------------------------------------------------ fwd-diag invalid everywhere

def test_fwd_diag_is_refused_even_when_time_and_adoption_pass(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fw, "check_adoption", lambda *a, **k: {})
    monkeypatch.setattr(fw, "check_time", lambda *a, **k: None)
    with pytest.raises(fw.ForwardAccessRefused, match="protocol-breach"):
        fw.check_forward_access("fwd-diag", LATE)

    def boom(*_a, **_k):
        raise AssertionError("fwd-diag data path reached")
    monkeypatch.setattr(rn, "load_stage_f", boom)
    out = tmp_path / "out"
    assert rn.main(["--segment", "fwd-diag", "--out", str(out), "--snapshot", "x", "--expect-manifest-sha256", "y",
                    "--authorization", "test"]) == 2
    assert not out.exists() and "protocol-breach" in capsys.readouterr().err
    with pytest.raises(fw.ForwardAccessRefused, match="protocol-breach"):
        sf.capture("fwd-diag", http_factory=boom, env={}, root=tmp_path, now=LATE)
    with pytest.raises(fw.ForwardAccessRefused, match="protocol-breach"):
        sf.validate("fwd-diag", "stage_f_fwd-diag_x", "sha", tmp_path / "v", root=tmp_path, now=LATE)
    with pytest.raises(fw.ForwardAccessRefused, match="protocol-breach"):
        dt.load_stage_f("fwd-diag", "stage_f_fwd-diag_x", "sha", root=tmp_path, now=LATE)


def test_fwd_gate_stays_closed_until_its_end_and_unchanged():
    with pytest.raises(fw.ForwardAccessRefused):
        fw.check_forward_access("fwd-gate", datetime(2027, 1, 7, 16, 14, 59, tzinfo=NY))
    g = rn.SEGMENTS["fwd-gate"]
    assert (g["first"], g["last"], g["sessions"], g["status_prefix"]) == (date(2026, 11, 6), date(2027, 1, 7), 42, "FORWARD42")
    st = fw.segment_status()                       # protocol 2.2 (DAY-26D): old gate superseded by the clean fwd-gate2
    assert st["fwd-gate"].startswith("SUPERSEDED") and st["fwd-gate2"].startswith("PENDING")
    assert st["fwd-diag"] == "FWD-DIAG-INVALID (protocol-breach)"


# ------------------------------------------------------------------ quarantine

def test_no_incident_file_in_any_project_data_path():
    assert fw.check_quarantine() >= 0                                  # raises if any inventoried SHA-256 is present
    q = Path(INCIDENT["quarantine"]["path"]).resolve()
    assert not q.is_relative_to(ROOT_DIR.resolve()) and not q.is_relative_to(CACHE_DIR.resolve())
    assert INCIDENT["inventory"]["count"] == len(INCIDENT["inventory"]["files"]) == 54


def test_quarantine_check_cannot_be_bypassed(tmp_path):
    probe = b"stand-in bytes for an inventoried incident file"
    import hashlib
    rec = {"inventory": {"files": [{"file": "AAPL_5m.parquet", "sha256": hashlib.sha256(probe).hexdigest()}]}}
    (tmp_path / fw.INCIDENT_FILES[1]).parent.mkdir(parents=True)
    (tmp_path / fw.INCIDENT_FILES[1]).write_text(json.dumps(rec), encoding="utf-8")
    hidden = tmp_path / "data" / "cache" / "renamed_anything.parquet"   # any name, any data sub-folder
    hidden.parent.mkdir(parents=True)
    hidden.write_bytes(probe)
    with pytest.raises(fw.ForwardAccessRefused, match="quarantined"):
        fw.check_quarantine(tmp_path)
    hidden.unlink()
    assert fw.check_quarantine(tmp_path) == 0


# ------------------------------------------------------------------ append-only records and pins

def test_disclosure_is_append_only_and_pinned():
    assert ADOPTION["decided_utc"] == "2026-10-10T12:52:51Z" and ADOPTION["final_status"] == "ADOPTED"
    assert ADOPTION["integrity_at_adoption"]["forward_data_accessed"] is False      # historical value kept as written
    assert ADOPTION["adopted_files_sha256_lf_history"][0]["adopted_files_sha256_lf"] == {
        "artifacts/day26b/protocol-v2.1-amendment.md": "1a1b0b0bb1e8a4a4eb093e5789a4f9d8cd010fe368439d0d8c8e950053d34b78",
        "artifacts/day26b/protocol-v2.1-amendment.json": "b4aa78cd8c6649a4bbfc67e73dc93597e22398e1debe8660fd2394da786fe20e"}
    for p in fw.AMENDMENT_FILES:
        assert ADOPTION["adopted_files_sha256_lf"][p] == fw.lf_sha256(ROOT_DIR / p)
    for p in fw.INCIDENT_FILES:
        assert ADOPTION["incident_records_sha256_lf"][p] == fw.lf_sha256(ROOT_DIR / p)
    status = {"fwd-diag": "FWD-DIAG-INVALID (protocol-breach)", "fwd-gate": "PENDING — blind, not evaluated"}
    amend = json.loads((ROOT_DIR / fw.AMENDMENT_FILES[1]).read_text(encoding="utf-8"))
    assert ADOPTION["segment_status"] == amend["segment_status"] == status
    md = (ROOT_DIR / fw.AMENDMENT_FILES[0]).read_text(encoding="utf-8")
    assert "STATUS: ADOPTED — 2026-10-10T12:52:51Z" in md and md.index("## 18.") < md.index("## 19. Incident disclosure")
