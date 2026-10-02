"""scripts/analyze_day_exit_decomposition.py: DAY-12A Exit Failure Decomposition CLI (diagnostic only).

Usage:
    python scripts/analyze_day_exit_decomposition.py
    python scripts/analyze_day_exit_decomposition.py --validation path/to/validation.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import time

# UTF-8 stdout configuration for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add smc-scanner root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.exit_decomposition import (
    dumps_results,
    format_exit_failure_report,
    rows_to_jsonable,
    run_day12a_exit_decomposition,
)
from config.day_universe import get_day_universe
from data.factory import get_provider

CSV_COLUMNS = [
    "trade_id", "symbol", "session", "signal_time", "entry_time", "exit_time", "entry_price", "stop_price",
    "target_price", "exit_price", "risk_per_share", "stop_distance_pct", "exit_reason", "exit_reason_raw",
    "outcome", "final_R", "holding_minutes", "MFE", "MFE_R", "MFE_price", "MFE_time", "time_to_MFE_minutes",
    "MAE", "MAE_R", "MAE_price", "MAE_time", "time_to_MAE_minutes", "MFE_R_upper_bound", "MAE_R_upper_bound",
    "bars_observed", "exit_bar_same_bar_ambiguous", "exit_bar_gap_through", "entry_tod_bin",
]


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT_DIR / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-12A: Exit Failure Decomposition (diagnostic only)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated tickers. Default: 25-stock universe.")
    parser.add_argument("--json-out", type=str, default="artifacts/day12a/exit-failure-results.json")
    parser.add_argument("--txt-out", type=str, default="artifacts/day12a/exit-failure-report.txt")
    parser.add_argument("--csv-out", type=str, default="artifacts/day12a/trade-excursions.csv")
    parser.add_argument("--validation", type=str, default=None,
                        help="Optional JSON with test/PIT/cache-hash verification to embed")
    parser.add_argument("--quiet", action="store_true", help="Suppress terminal report output")
    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 85)
    print("DAY-12A: EXIT FAILURE DECOMPOSITION (DIAGNOSTIC ONLY)")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")

    start_time = time.perf_counter()
    result, rows = run_day12a_exit_decomposition(symbols=symbols_list, provider=get_provider())
    print(f"Analysis completed in {time.perf_counter() - start_time:.2f} seconds.")

    if args.validation:
        result["validation"] = json.loads(Path(args.validation).read_text(encoding="utf-8"))

    report_text = format_exit_failure_report(result)

    json_path, txt_path, csv_path = _resolve(args.json_out), _resolve(args.txt_out), _resolve(args.csv_out)
    for path in (json_path, txt_path, csv_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(dumps_results(result), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows_to_jsonable(rows):
            w.writerow(r)

    for path in (json_path, txt_path, csv_path):
        print(f"Artifact saved : {path}")

    if not args.quiet:
        print("\n" + report_text)

    ok = (
        result["baseline_regression"]["regression_verified"]
        and result["integrity"]["all_trades_reconstructed"]
        and result["integrity"]["all_record_checks_pass"]
    )
    if not ok:
        print("\n[FAIL] Baseline regression or trade-record reconstruction failed — DAY-12A results NOT VALID.")
        return 1
    print(f"\n[PASS] Baseline verified, all trades reconstructed. Diagnostic: {result['mechanism']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
