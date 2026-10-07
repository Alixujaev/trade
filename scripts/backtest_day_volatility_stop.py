"""scripts/backtest_day_volatility_stop.py: DAY-09 H4 Volatility-Scaled (ATR) Stop Distance CLI.

Usage:
    python scripts/backtest_day_volatility_stop.py
    python scripts/backtest_day_volatility_stop.py --symbols AAPL,MSFT,NVDA
    python scripts/backtest_day_volatility_stop.py --json-out artifacts/day09/volatility-stop-results.json --txt-out artifacts/day09/volatility-stop-report.txt
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

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.volatility_stop import (
    H4_MULTIPLIERS,
    format_volatility_stop_report,
    run_day09_volatility_stop_experiment,
)
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-09: H4 Volatility-Scaled (ATR) Stop Distance Research CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated tickers (e.g. AAPL,MSFT,NVDA). Default: 25-stock universe.")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--json-out", type=str, default="artifacts/day09/volatility-stop-results.json",
                        help="JSON output path")
    parser.add_argument("--txt-out", type=str, default="artifacts/day09/volatility-stop-report.txt",
                        help="TXT report output path")
    parser.add_argument("--quiet", action="store_true", help="Suppress terminal report output")

    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 85)
    print("DAY-09: H4 VOLATILITY-SCALED (ATR) STOP DISTANCE RESEARCH EXPERIMENT")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print(f"Executing Frozen Baseline (SIGNAL_LOW) vs H4 ATR multipliers {list(H4_MULTIPLIERS)}...")

    start_time = time.perf_counter()
    prov = get_provider()

    exp_result = run_day09_volatility_stop_experiment(
        symbols=symbols_list,
        start_date=args.start,
        end_date=args.end,
        provider=prov,
    )

    elapsed = time.perf_counter() - start_time
    print(f"Simulation completed in {elapsed:.2f} seconds.")

    report_text = format_volatility_stop_report(exp_result)

    for out, writer in (
        (args.json_out, lambda f: json.dump(exp_result.to_dict(), f, indent=2, default=str)),
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

    if not exp_result.baseline_regression["regression_verified"]:
        print("\n[FAIL] Baseline regression failed — H4 results NOT VALIDATED.")
        return 1
    print("\n[PASS] Baseline regression verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
