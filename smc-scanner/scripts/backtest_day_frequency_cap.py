"""scripts/backtest_day_frequency_cap.py: DAY-10 H3 Session Trade Frequency Cap CLI.

Usage:
    python scripts/backtest_day_frequency_cap.py
    python scripts/backtest_day_frequency_cap.py --test-summary path/to/pytest-summary.json
"""

from __future__ import annotations

import argparse
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

from backtest.frequency_cap import (
    H3_CAPS,
    format_frequency_cap_report,
    run_day10_frequency_cap_experiment,
)
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-10: H3 Session Trade Frequency Cap Research CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated tickers. Default: 25-stock universe.")
    parser.add_argument("--json-out", type=str, default="artifacts/day10/frequency-cap-results.json")
    parser.add_argument("--txt-out", type=str, default="artifacts/day10/frequency-cap-report.txt")
    parser.add_argument("--test-summary", type=str, default=None,
                        help="Optional JSON file with the pytest summary to embed in the results")
    parser.add_argument("--quiet", action="store_true", help="Suppress terminal report output")
    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 85)
    print("DAY-10: H3 SESSION TRADE FREQUENCY CAP RESEARCH EXPERIMENT")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print(f"Variants          : {['NO CAP' if c is None else f'CAP {c}' for c in H3_CAPS]}")

    start_time = time.perf_counter()
    result = run_day10_frequency_cap_experiment(symbols=symbols_list, provider=get_provider())
    print(f"Simulation completed in {time.perf_counter() - start_time:.2f} seconds.")

    if args.test_summary:
        result["test_summary"] = json.loads(Path(args.test_summary).read_text(encoding="utf-8"))

    report_text = format_frequency_cap_report(result)

    for out, writer in (
        (args.json_out, lambda f: json.dump(result, f, indent=2, default=str)),
        (args.txt_out, lambda f: f.write(report_text)),
    ):
        path = Path(out)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            writer(f)
        print(f"Artifact saved : {path}")

    if not args.quiet:
        print("\n" + report_text)

    if not result["baseline_regression"]["regression_verified"]:
        print("\n[FAIL] Baseline regression failed — H3 results NOT VALIDATED.")
        return 1
    print(f"\n[PASS] Baseline regression verified. H3 status: {result['h3_evaluation']['h3_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
