"""scripts/backtest_orb.py --v11-sip-snapshot (Stage 5 step 3; synthetic snapshot only, network yo'q).

The real snapshot is never opened. main() runs only on synthetic tmp_path data, with SIP_OUT_ROOT redirected to
tmp_path so nothing is written under the repository's artifacts/orb/.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from backtest import orb_snapshot_input as osi
import scripts.backtest_orb as bo
from tests.test_backtest_orb_report_golden import FULL, FULL_REPORT
from tests.test_orb_snapshot_input import SYMS, build

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "backtest_orb.py"
DATES = ["--start", "2026-07-02", "--end", "2026-09-25"]
SIP_LABEL = ("Alpaca SIP raw (v1.1 research snapshot research_X, hash-pinned; "
             "research segment 2026-07-02..2026-09-25)")

SIP_HEAD = """\
# ORB SIP snapshot diagnostic (descriptive; not independent evidence)

- Range: 2026-07-02 → 2026-09-25 (60 sessions)
- Universe: 2 tickers; with trades: AAA, BBB
- Data: Alpaca SIP snapshot `research_X` (research segment 2026-07-02 → 2026-09-25, RTH only, no warmup; network blocked (socket connect refused)); earnings: `config/earnings_calendar.csv`
- Source: Alpaca SIP raw (v1.1 research snapshot research_X, hash-pinned; research segment 2026-07-02..2026-09-25)
- **Descriptive diagnostic only:** a re-run on the same 60 sessions previously examined with yfinance data. Not independent evidence and not strategy validation (ORB-SIP-D5).
- SIP results are reported on their own. Prior yfinance run: `artifacts/orb/smoke_test/report.md`, referenced by path only; no deltas or numeric comparison.
- SIP volume differs from yfinance volume and can change the 20-bar volume-confirmation outcomes.
- No warmup segment is supplied, so the first session (2026-07-02) has no prior close for any symbol.
- Corporate actions: prices are raw. Events for 2026-07-02 → 2026-09-25 are unknown (no event data was acquired) and could affect the rolling 20-bar volume filter and the raw prior-close $5 minimum-price filter (ORB-SIP-D4). Whether protocol v1.1 §18 governs ORB is not decided.
- Decision record: `artifacts/orb/sip_diagnostic_decision.md`.

"""


def _earnings(tmp_path: Path) -> Path:
    p = tmp_path / "earnings.csv"
    p.write_text("symbol,coverage_start,coverage_end,earnings_date\n"
                 + "".join(f"{s},2026-07-02,2026-09-25,\n" for s in SYMS), encoding="utf-8")
    return p


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return [*DATES, "--capital", "100000", "--earnings", str(_earnings(tmp_path)), "--symbols", *SYMS, *extra]


@pytest.fixture
def no_load(monkeypatch):
    """Any call into the snapshot loader fails the test: rejections must happen before data access."""
    def boom(*_a, **_k):
        raise AssertionError("load_research_frames must not be called")
    monkeypatch.setattr(osi, "load_research_frames", boom)


# ------------------------------------------------------------------ label / report / imports (no main)

def test_sip_label_exact():
    assert bo.data_source_label(None, None, sip_snapshot_id="research_X") == SIP_LABEL


def test_sip_report_golden():
    m = copy.deepcopy(FULL)
    m["inputs"]["data_source"] = SIP_LABEL
    m["inputs"]["sip_snapshot"] = {"snapshot_id": "research_X", "research_first": "2026-07-02",
                                   "research_last": "2026-09-25", "research_sessions": 60}
    tail = FULL_REPORT[FULL_REPORT.index("| Metric | ORB |"):]          # table/exits/checks: same format as default
    assert bo.render_report(m) == SIP_HEAD + tail
    assert "Smoke test" not in bo.render_report(m)


def test_snapshot_helper_is_not_imported_at_module_level():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    top = {node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.module}
    top |= {a.name for node in tree.body if isinstance(node, ast.Import) for a in node.names}
    assert not any(n == "backtest.orb_snapshot_input" or n.startswith("backtest.orb_snapshot_input.") for n in top)
    assert all(not (isinstance(n, ast.ImportFrom) and n.module == "backtest" and
                    any(a.name == "orb_snapshot_input" for a in n.names)) for n in tree.body)


# ------------------------------------------------------------------ main(): rejections before any data access

def test_cache_dir_and_snapshot_are_mutually_exclusive(tmp_path, no_load):
    with pytest.raises(SystemExit) as exc:
        bo.main(_argv(tmp_path, "--cache-dir", str(tmp_path), "--v11-sip-snapshot", str(tmp_path)))
    assert exc.value.code == 2


@pytest.mark.parametrize("dates", [["--start", "2026-07-06", "--end", "2026-09-25"],
                                   ["--start", "2026-07-02", "--end", "2026-09-24"]])
def test_wrong_dates_abort(tmp_path, monkeypatch, no_load, dates):
    monkeypatch.setattr(bo, "SIP_OUT_ROOT", tmp_path / "orb_root")
    argv = _argv(tmp_path, "--v11-sip-snapshot", str(tmp_path), "--out", str(tmp_path / "orb_root" / "run"))
    argv[0:4] = dates
    with pytest.raises(SystemExit, match="requires --start 2026-07-02 --end 2026-09-25"):
        bo.main(argv)


def test_out_must_be_strictly_inside_sip_out_root(tmp_path, monkeypatch, no_load):
    root = tmp_path / "orb_root"
    root.mkdir()
    monkeypatch.setattr(bo, "SIP_OUT_ROOT", root)
    for out in (None, root, tmp_path / "elsewhere", ROOT / "paper_state" / "sip_run"):
        extra = ["--v11-sip-snapshot", str(tmp_path)] + ([] if out is None else ["--out", str(out)])
        with pytest.raises(SystemExit, match="requires --out strictly inside"):
            bo.main(_argv(tmp_path, *extra))
    assert not (ROOT / "paper_state" / "sip_run").exists()


def test_default_out_root_is_artifacts_orb():
    assert bo.SIP_OUT_ROOT == ROOT / "artifacts" / "orb"


def test_non_pinned_snapshot_dir_aborts_without_reading_bars(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "SIP_OUT_ROOT", tmp_path / "orb_root")
    other = tmp_path / "research_other"
    other.mkdir()
    with pytest.raises(SystemExit, match="ABORT: snapshot 'research_other' != pinned"):
        bo.main(_argv(tmp_path, "--v11-sip-snapshot", str(other), "--out", str(tmp_path / "orb_root" / "run")))


# ------------------------------------------------------------------ main(): synthetic success path

def test_main_snapshot_mode_writes_disclosed_report_and_provenance(tmp_path, monkeypatch, capsys):
    snap, pins = build(tmp_path)
    monkeypatch.setattr(osi, "PINNED", pins)
    root = tmp_path / "orb_root"
    monkeypatch.setattr(bo, "SIP_OUT_ROOT", root)
    out = root / "sip_run"
    repo_orb = sorted(p.name for p in (ROOT / "artifacts" / "orb").iterdir())

    rc = bo.main(_argv(tmp_path, "--v11-sip-snapshot", str(snap), "--out", str(out)))
    capsys.readouterr()

    assert rc == 0
    assert sorted(p.name for p in (ROOT / "artifacts" / "orb").iterdir()) == repo_orb   # repo artifacts untouched
    report = (out / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# ORB SIP snapshot diagnostic (descriptive; not independent evidence)\n")
    for line in SIP_HEAD.replace("research_X", pins.snapshot_id).splitlines()[4:]:
        if line.startswith("- Data:"):
            line = line.replace("`config/earnings_calendar.csv`", f"`{_earnings(tmp_path)}`")
        assert line in report, line
    assert "Smoke test" not in report
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    inputs = metrics["inputs"]
    assert inputs["sip_snapshot"] == osi.load_research_frames(snap, SYMS, pins=pins).provenance
    assert inputs["network"] == "blocked (socket connect refused)"
    assert inputs["cache_dir"] is None
    assert inputs["data_source"] == SIP_LABEL.replace("research_X", pins.snapshot_id)
    assert metrics["trades"] == 1 and metrics["all_checks_passed"] is True
    assert metrics["range"]["sessions"] == 60 and metrics["range"]["first_session"] == "2026-07-02"
