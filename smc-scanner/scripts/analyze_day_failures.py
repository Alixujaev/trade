"""scripts/analyze_day_failures.py: DAY-05 — Failure Analysis of the Frozen Day Strategy.

Foydalanish:
    python scripts/analyze_day_failures.py
    python scripts/analyze_day_failures.py --symbols AAPL,MSFT,NVDA
    python scripts/analyze_day_failures.py --json-out artifacts/day05/failure-analysis.json --txt-out artifacts/day05/failure-analysis.txt
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

# UTF-8 stdout sozlash (Windows console uchun)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# smc-scanner root papkasini sys.path ga qo'shish
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.failure_analysis import (
    format_failure_analysis_report,
    run_day_failure_analysis,
)
from backtest.multi_symbol import run_multi_symbol_day_backtest
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-05: Failure Analysis of the Frozen Day Strategy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Vergul bilan ajratilgan tickerlar (masalan: AAPL,MSFT,NVDA). Default: 25 ta aksiyali universe.",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="artifacts/day05/failure-analysis.json",
        help="Chiqariladigan JSON hisobot yo'li.",
    )
    parser.add_argument(
        "--txt-out",
        type=str,
        default="artifacts/day05/failure-analysis.txt",
        help="Chiqariladigan TXT hisobot yo'li.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Terminalga to'liq matnli hisobotni chiqarmaslik.",
    )

    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 80)
    print("DAY-05: FAILURE ANALYSIS OF THE FROZEN DAY STRATEGY")
    print("=" * 80)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print("Executing frozen multi-symbol backtest and post-hoc excursion analysis...")

    start_time = time.perf_counter()
    prov = get_provider()

    # Multi-symbol orqali 25 ta aksiya bo'yicha savdolarni yig'ish
    multi_res = run_multi_symbol_day_backtest(
        symbols=symbols_list,
        provider=prov,
    )

    # Xatolik tahlilini yuritish
    analysis_res = run_day_failure_analysis(
        multi_result=multi_res,
        provider=prov,
    )
    elapsed = time.perf_counter() - start_time

    # Hisobot matnini formatlash
    txt_report = format_failure_analysis_report(analysis_res)

    if not args.quiet:
        print("\n" + txt_report)

    print("\n" + "=" * 80)
    print(f"Analysis completed in {elapsed:.2f} seconds.")
    print(f"Total trades analyzed: {analysis_res.total_trades_analyzed:,}")
    print(f"Symbols analyzed:      {len(analysis_res.universe)}")

    # JSON hisobotni saqlash
    json_path = ROOT_DIR / args.json_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis_res.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"JSON artifact saved to: {json_path}")

    # TXT hisobotni saqlash
    txt_path = ROOT_DIR / args.txt_out
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_report)
    print(f"TXT artifact saved to:  {txt_path}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
