"""scripts/backtest_day_index_regime.py: DAY-08 H6 Index Regime Confluence CLI.

Usage:
    python scripts/backtest_day_index_regime.py
    python scripts/backtest_day_index_regime.py --symbols AAPL,MSFT,NVDA
    python scripts/backtest_day_index_regime.py --json-out artifacts/day08/index-regime-results.json --txt-out artifacts/day08/index-regime-report.txt
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

from backtest.index_regime import (
    format_index_regime_report,
    run_day08_index_regime_experiment,
)
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-08: H6 Index Regime Confluence Research CLI",
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
        default="artifacts/day08/index-regime-results.json",
        help="JSON output path",
    )
    parser.add_argument(
        "--txt-out",
        type=str,
        default="artifacts/day08/index-regime-report.txt",
        help="TXT report output path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal report output",
    )

    args = parser.parse_args()

    symbols_list = (
        [s.strip().upper() for s in args.symbols.split(",")]
        if args.symbols
        else get_day_universe()
    )

    print("=" * 85)
    print("DAY-08: H6 INDEX REGIME CONFLUENCE RESEARCH EXPERIMENT")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print("Executing Frozen Baseline vs H6-A (SPY) vs H6-B (QQQ) vs H6-C (Both)...")

    start_time = time.perf_counter()
    prov = get_provider()

    exp_result = run_day08_index_regime_experiment(
        symbols=symbols_list,
        start_date=args.start,
        end_date=args.end,
        provider=prov,
    )

    elapsed = time.perf_counter() - start_time
    print(f"Simulation completed in {elapsed:.2f} seconds.")

    # Generate text report
    txt_report = format_index_regime_report(exp_result)

    if not args.quiet:
        print()
        print(txt_report)

    # Save artifacts
    if args.json_out:
        json_path = Path(args.json_out)
        if not json_path.is_absolute():
            json_path = ROOT_DIR / json_path
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(exp_result.to_dict(), f, indent=2)
        print(f"\n[OK] JSON artifact saved: {json_path}")

    if args.txt_out:
        txt_path = Path(args.txt_out)
        if not txt_path.is_absolute():
            txt_path = ROOT_DIR / txt_path
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_report)
        print(f"[OK] TXT report saved: {txt_path}")

    # Check baseline regression
    reg = exp_result.baseline_regression
    if not reg["regression_verified"]:
        print("\n[FAIL] Baseline regression failed! Results differ from expected frozen baseline.")
        return 1

    print("\n[PASS] Baseline regression verified successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
