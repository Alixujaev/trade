"""scripts/backtest_day_breakeven_05.py: DAY-12B +0.5R -> Breakeven counterfactual CLI.

Usage:
    python scripts/backtest_day_breakeven_05.py
    python scripts/backtest_day_breakeven_05.py --validation path/to/validation.json
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

from backtest.breakeven_05 import format_day12b_report, run_day12b_experiment
from backtest.exit_decomposition import dumps_results, rows_to_jsonable
from config.day_universe import get_day_universe
from data.factory import get_provider


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT_DIR / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-12B: +0.5R -> Breakeven counterfactual (single hypothesis)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated tickers. Default: 25-stock universe.")
    parser.add_argument("--json-out", type=str, default="artifacts/day12b/day12b-results.json")
    parser.add_argument("--txt-out", type=str, default="artifacts/day12b/day12b-report.txt")
    parser.add_argument("--csv-out", type=str, default="artifacts/day12b/day12b-trades.csv")
    parser.add_argument("--validation", type=str, default=None,
                        help="Optional JSON with test/PIT/cache-hash verification to embed")
    parser.add_argument("--quiet", action="store_true", help="Suppress terminal report output")
    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 85)
    print("DAY-12B: +0.5R -> BREAKEVEN COUNTERFACTUAL")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")

    start_time = time.perf_counter()
    result, rows = run_day12b_experiment(symbols=symbols_list, provider=get_provider())
    print(f"Simulation completed in {time.perf_counter() - start_time:.2f} seconds.")

    if args.validation:
        result["validation"] = json.loads(Path(args.validation).read_text(encoding="utf-8"))

    report_text = format_day12b_report(result)

    json_path, txt_path, csv_path = _resolve(args.json_out), _resolve(args.txt_out), _resolve(args.csv_out)
    for path in (json_path, txt_path, csv_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(dumps_results(result), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")
    jrows = rows_to_jsonable(rows)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        if jrows:
            w = csv.DictWriter(f, fieldnames=list(jrows[0].keys()))
            w.writeheader()
            w.writerows(jrows)

    for path in (json_path, txt_path, csv_path):
        print(f"Artifact saved : {path}")

    if not args.quiet:
        print("\n" + report_text)

    a = result["accounting"]
    ok = result["baseline_regression"]["regression_verified"] and a["same_population"] and a["reconciles"]
    if not ok:
        print("\n[FAIL] Baseline regression / paired population / reconciliation failed — DAY-12B NOT EVALUATED.")
        return 1
    print(f"\n[PASS] Baseline verified, paired population identical. DAY-12B status: {result['evaluation']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
