"""scripts/backtest_day_dynamic_stop_robustness.py: DAY-07A H2 Stop Management Robustness CLI.

Usage:
    python scripts/backtest_day_dynamic_stop_robustness.py
    python scripts/backtest_day_dynamic_stop_robustness.py --symbols AAPL,MSFT,NVDA
    python scripts/backtest_day_dynamic_stop_robustness.py --json-out artifacts/day07a/dynamic-stop-robustness-results.json --txt-out artifacts/day07a/dynamic-stop-robustness-report.txt
"""

from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path
import sys
import time

# UTF-8 stdout configuration for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.dynamic_stop_robustness import (
    DAY07A_BE_THRESHOLDS_R,
    format_dynamic_stop_robustness_report,
    run_day07a_robustness_experiment,
)
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-07A: H2 Stop Management Robustness Experiment (0.75R, 1.00R, 1.25R)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated tickers (e.g. AAPL,MSFT,NVDA). Default: 25-stock universe.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="artifacts/day07a/dynamic-stop-robustness-results.json",
        help="JSON output path",
    )
    parser.add_argument(
        "--txt-out",
        type=str,
        default="artifacts/day07a/dynamic-stop-robustness-report.txt",
        help="TXT report output path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal report output",
    )

    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 95)
    print("DAY-07A: H2 STOP MANAGEMENT ROBUSTNESS EXPERIMENT")
    print(f"Pre-declared Thresholds: {', '.join(f'{k:.2f}R' for k in DAY07A_BE_THRESHOLDS_R)}")
    print("=" * 95)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print("Executing Frozen Baseline vs H2 Threshold Variants (0.75R, 1.00R, 1.25R)...")

    start_time = time.perf_counter()
    prov = get_provider()

    exp_result = run_day07a_robustness_experiment(
        symbols=symbols_list,
        start_date=args.start,
        end_date=args.end,
        provider=prov,
    )

    elapsed = time.perf_counter() - start_time
    print(f"Simulation completed in {elapsed:.2f} seconds.")

    # Generate text report
    report_text = format_dynamic_stop_robustness_report(exp_result)

    # Save artifacts
    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(exp_result.to_dict(), f, indent=2)
    print(f"JSON artifact saved : {json_path}")

    txt_path = Path(args.txt_out)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"TXT artifact saved  : {txt_path}")

    if not args.quiet:
        print("\n" + report_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
