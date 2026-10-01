"""scripts/backtest_day_time_window.py: DAY-11 H5 Time-of-Day Execution Window CLI.

Usage:
    python scripts/backtest_day_time_window.py
    python scripts/backtest_day_time_window.py --validation path/to/validation.json
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

from backtest.session_gate import ENTRY_WINDOWS
from backtest.time_window import format_time_window_report, run_day11_time_window_experiment
from config.day_universe import get_day_universe
from data.factory import get_provider


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT_DIR / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-11: H5 Time-of-Day Execution Window Research CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated tickers. Default: 25-stock universe.")
    parser.add_argument("--json-out", type=str, default="artifacts/day11/time-of-day-results.json")
    parser.add_argument("--txt-out", type=str, default="artifacts/day11/time-of-day-report.txt")
    parser.add_argument("--csv-out", type=str, default="artifacts/day11/time-of-day-variants.csv")
    parser.add_argument("--validation", type=str, default=None,
                        help="Optional JSON with test/PIT/boundary/cache-hash verification to embed")
    parser.add_argument("--quiet", action="store_true", help="Suppress terminal report output")
    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 85)
    print("DAY-11: H5 TIME-OF-DAY EXECUTION WINDOW RESEARCH EXPERIMENT")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print(f"Windows           : {[f'{w.name} {w.describe()}' for w in ENTRY_WINDOWS]}")

    start_time = time.perf_counter()
    result = run_day11_time_window_experiment(symbols=symbols_list, provider=get_provider())
    print(f"Simulation completed in {time.perf_counter() - start_time:.2f} seconds.")

    if args.validation:
        result["validation"] = json.loads(Path(args.validation).read_text(encoding="utf-8"))

    report_text = format_time_window_report(result)

    json_path, txt_path, csv_path = _resolve(args.json_out), _resolve(args.txt_out), _resolve(args.csv_out)
    for path in (json_path, txt_path, csv_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")

    cols = ["total_trades", "win_rate", "profit_factor", "total_R", "avg_R", "median_R", "r_std",
            "max_drawdown_pct", "avg_hold_duration_mins", "slippage_0bps", "slippage_5bps", "slippage_10bps"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "window", "candidate_signals", "window_rejected", "position_open_skips",
                     "simulation_none", *cols, "median_hold_minutes"])
        for name, desc in result["metadata"]["windows"].items():
            a, m = result["accounting"][name], result["metrics"][name]
            w.writerow([name, desc, a["candidate_signals"], a["window_rejected"], a["position_open_skips"],
                        a["simulation_none"], *[m[c] for c in cols], result["extra_metrics"][name]["median_hold_minutes"]])

    for path in (json_path, txt_path, csv_path):
        print(f"Artifact saved : {path}")

    if not args.quiet:
        print("\n" + report_text)

    if not result["baseline_regression"]["regression_verified"]:
        print("\n[FAIL] FULL / no-gate baseline regression failed — H5 results NOT VALIDATED.")
        return 1
    print(f"\n[PASS] Baseline regression verified. H5 status: {result['h5_evaluation']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
