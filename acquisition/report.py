"""acquisition/report.py: structural acquisition report writer (only artifacts/day15/ is permitted).

The report is generated from run records and contains counts/timestamps only — no prices, returns,
signals, rankings or any economic content of the OOS period.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from acquisition.contract import ROOT_DIR

REPORT_DIR = ROOT_DIR / "artifacts" / "day15"
REPORT_NAME = "day15b-acquisition.md"  # the only writable file (DAY-15A documents are protected)


class ReportPathError(ValueError):
    """Reports may only be written under artifacts/day15/."""


def write_report(path: Path, text: str) -> Path:
    rp = Path(path).resolve()
    if rp != (REPORT_DIR / REPORT_NAME).resolve():
        raise ReportPathError(f"report may only be written to {REPORT_DIR / REPORT_NAME}")
    rp.write_text(text, encoding="utf-8")
    return rp


def render_report(run: dict[str, Any], manifest: dict[str, Any], preflight: dict[str, Any]) -> str:
    res = run["results"]
    exp_syms = len(manifest["symbols"])
    got = [r for r in res if r["status"] != "MISSING"]
    missing = [r for r in res if r["status"] == "MISSING"]
    complete_pairs = [r for r in got if r["coverage"]["complete"] and r["structural_passed"]]
    sym_complete = sorted({r["symbol"] for r in res} - {r["symbol"] for r in res if r not in complete_pairs})
    sym_incomplete = sorted({r["symbol"] for r in res} - set(sym_complete))
    progress = manifest.get("progress", {})
    status = "PARTIAL"  # until the ledger shows every one of the 60 sessions complete
    if progress.get("progress") == f"{len(manifest['oos_sessions'])}/{len(manifest['oos_sessions'])}":
        status = "ACQUIRED"
    if not got:
        status = "FAILED"
    L = []
    p = L.append
    p("# DAY-15B — OOS Acquisition Report (structural only)\n")
    p("> No OOS signals, returns, performance metrics, setup counts, rankings, or trading outcomes were computed or inspected.\n")
    p("## Acquisition status\n")
    p(f"- **Status: {status}** — ledger progress {progress.get('progress', '?')} complete sessions "
      f"(complete session = every symbol x interval verified). Snapshot `{run['snapshot_id']}` requested "
      f"{len(run['captured_sessions'])} session(s) incrementally (provider window: "
      f"{run.get('provider_window', {}).get('earliest_requestable_start_utc', 'n/a')}, INFERRED).")
    p(f"- Run (UTC): {run['run_utc']}\n")
    p("## Session definition\n")
    cal = manifest["calendar"]
    p(f"- Boundary: {manifest['boundary_date']} (exclusive); rule: {manifest['oos_rule']}")
    p(f"- Calendar: {cal['package']} {cal['version']} `{cal['calendar']}` (bounds {cal['bounds']}, {cal['session_timezone']})")
    p(f"- Session count: {len(manifest['oos_sessions'])}; first {manifest['oos_sessions'][0]['session']}; "
      f"last {manifest['oos_sessions'][-1]['session']}; early closes: "
      f"{[s['session'] for s in manifest['oos_sessions'] if s['early_close']]}")
    p(f"- Captured in this snapshot: {run['captured_sessions']}")
    p(f"- Capture policy: close {run['capture_policy']['market_close_et']} ET, not before {run['capture_policy']['capture_not_before_et']} ET\n")
    p("## Universe\n")
    p(f"- Expected symbols: {exp_syms}; symbol×interval pairs acquired: {len(got)}/{len(res)}; missing pairs: {len(missing)}")
    p(f"- Symbols complete (both intervals, all captured sessions, structural pass): {len(sym_complete)}")
    p(f"- Symbols incomplete/missing: {len(sym_incomplete)} {sym_incomplete}")
    for r in missing:
        p(f"  - MISSING {r['symbol']} {r['interval']}: {r.get('error')}")
    p("")
    p("## Coverage (structural)\n")
    p("| Symbol | Interval | Part | Exp. sessions | Sessions w/ data | Exp. bars | Present bars | Missing bars | Outside grid | Structural |")
    p("|---|---|---|---|---|---|---|---|---|---|")
    for r in res:
        if r["status"] == "MISSING":
            p(f"| {r['symbol']} | {r['interval']} | {r.get('part', '-')} | {len(r.get('requested_sessions', run['captured_sessions']))} | 0 | - | 0 | - | - | MISSING |")
            continue
        c = r["coverage"]
        p(f"| {r['symbol']} | {r['interval']} | {r.get('part', '-')} | {c['expected_sessions']} | {c['sessions_with_data']} | {c['expected_bars']} | "
          f"{c['present_expected_bars']} | {c['missing_bars']} | {c['bars_outside_expected_grid']} | "
          f"{'PASS' if r['structural_passed'] else 'FAIL: ' + '; '.join(r['structural_errors'])} |")
    p("")
    def tot(k):
        return sum(int(r.get(k) or 0) for r in got)
    p("## Integrity\n")
    p(f"- Duplicate timestamps: {tot('duplicate_timestamps')}")
    p(f"- Missing bars (vs calendar grid): {sum(r['coverage']['missing_bars'] for r in got)}")
    p(f"- Bars outside expected grid: {sum(r['coverage']['bars_outside_expected_grid'] for r in got)}")
    p(f"- Off-grid bars: {tot('off_grid_bars')}; non-RTH bars: {tot('non_rth_bars')}")
    p(f"- Invalid OHLC rows: {tot('ohlc_inconsistent_rows')}; NaN cells: {tot('nan_cells')}")
    p(f"- Negative-volume rows: {tot('negative_volume_rows')}; zero-volume rows: {tot('zero_volume_rows')}")
    p(f"- Timezone: {sorted({r['tz'] for r in got})}")
    p(f"- Hash status: {sum(1 for r in got if r.get('content_sha256'))} snapshot files hashed (content + file SHA-256 in manifest)")
    p(f"- Re-acquisition status: {sorted({r['status'] for r in got})}")
    ov = [o for r in got for o in r["overlap_with_previous"]]
    p(f"- Overlap discrepancy status: {'no previous snapshot' if not ov else sum(1 for o in ov if not o['identical_on_overlap'])} "
      f"{'' if not ov else 'discrepant overlaps of ' + str(len(ov))}")
    p(f"- Adjustment status: pairs with adj_close == close on all rows: "
      f"{sum(1 for r in got if r['adj_close_equals_close_all_rows'])}/{len(got)}; rows with adj_close != close: {tot('adj_close_differs_rows')}\n")
    p("## Provenance\n")
    p(f"- Provider: {run['provider']} {run['provider_version']}; config: `{run['provider_config']}`")
    p(f"- Acquisition commit: {run['acquisition_commit']}")
    p(f"- Environment manifest: snapshot `environment.json` (sha256 {run['environment_sha256']}); "
      "reference copy artifacts/day15/environment-manifest-day15b.json")
    p(f"- Preflight: passed={preflight.get('passed')}; frozen dirs checked={preflight.get('frozen_dirs_checked')}; "
      f"git commit={preflight.get('git', {}).get('commit')}")
    p(f"- Manifest: data/oos_cache/protocol_v1.0/manifest.json\n")
    p("## Research boundary\n")
    p("No OOS signals, returns, performance metrics, setup counts, rankings, or trading outcomes were computed or inspected. "
      "OOS evaluation remains gated (DAY-14 research-protocol §11).")
    return "\n".join(L) + "\n"
