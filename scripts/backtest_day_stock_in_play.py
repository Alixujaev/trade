"""scripts/backtest_day_stock_in_play.py: DAY-06 Stock-in-Play Context Hypothesis Research CLI.

Usage:
    python scripts/backtest_day_stock_in_play.py
    python scripts/backtest_day_stock_in_play.py --symbols AAPL,MSFT,NVDA
"""

from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path
import sys
import time

# UTF-8 stdout sozlash (Windows console uchun)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Loyiha root papkasini sys.path ga qo'shish
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.stock_in_play import (
    format_stock_in_play_report,
    run_stock_in_play_backtest,
)
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-06: Stock-in-Play Context Hypothesis Backtest Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Vergul bilan ajratilgan tickerlar (masalan: AAPL,MSFT,NVDA). Default: 25 ta aksiyali universe.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Tadqiqot boshlanish sanasi (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Tadqiqot tugash sanasi (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="artifacts/day06/stock-in-play-results.json",
        help="Chiqariladigan JSON hisobot yo'li.",
    )
    parser.add_argument(
        "--txt-out",
        type=str,
        default="artifacts/day06/stock-in-play-report.txt",
        help="Chiqariladigan TXT hisobot yo'li.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Terminalga hisobot jadvalini chiqarmaslik.",
    )

    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 85)
    print("DAY-06: STOCK-IN-PLAY CONTEXT HYPOTHESIS BACKTEST")
    print("=" * 85)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print("Running Baseline vs Stock-in-Play Variants (Gap, Premarket RVOL, Combined)...")

    start_time = time.perf_counter()
    prov = get_provider()

    exp_result = run_stock_in_play_backtest(
        symbols=symbols_list,
        provider=prov,
    )
    elapsed = time.perf_counter() - start_time

    txt_report = format_stock_in_play_report(exp_result)

    if not args.quiet:
        print("\n" + txt_report)

    print("\n" + "=" * 85)
    print(f"Backtest completed in {elapsed:.2f} seconds.")
    print(f"Baseline trades:    {exp_result.baseline.total_trades:,}")
    print(f"H1 Gap-Only trades: {exp_result.h1_gap_only.total_trades:,} (-{exp_result.h1_gap_only.trade_reduction_pct:.1f}% reduction)")

    # JSON hisobotni saqlash
    json_path = ROOT_DIR / args.json_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(exp_result.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"JSON artifact saved to: {json_path}")

    # TXT hisobotni saqlash
    txt_path = ROOT_DIR / args.txt_out
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_report)
    print(f"TXT artifact saved to:  {txt_path}")
    print("=" * 85)

    return 0


if __name__ == "__main__":
    sys.exit(main())
