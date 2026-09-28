"""scripts/backtest_day_multi.py: DAY-04 Multi-Symbol Research Runner CLI.

Usage:
    python scripts/backtest_day_multi.py
    python scripts/backtest_day_multi.py --symbols AAPL,MSFT,NVDA
    python scripts/backtest_day_multi.py --symbols AAPL,MSFT --slippage 5.0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.day_types import ExecutionConfig
from backtest.multi_symbol import (
    format_multi_symbol_report,
    run_multi_symbol_day_backtest,
)
from config.day_universe import get_day_universe
from data.factory import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-04: Multi-Symbol Validation of the Frozen Day Strategy"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Vergul bilan ajratilgan belgilar ro'yxati (masalan 'AAPL,MSFT,NVDA'). Bo'sh bo'lsa muzlatilgan DAY_UNIVERSE ishlatiladi.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Boshlanish sanasi (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Tugash sanasi (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0,
        help="Bazaviy slippage (bps, standart: 0.0)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.0,
        help="Aksiya boshiga komissiya ($)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Data provider nomi ('yfinance' yoki 'alpaca')",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="artifacts/day04/multi-symbol-results.json",
        help="Mashina o'qiy oladigan JSON hisobot fayli manzili",
    )
    parser.add_argument(
        "--no-market-context",
        action="store_true",
        help="Diagnostik SPY/QQQ bozor kontekstini o'tkazib yuborish",
    )

    args = parser.parse_args()

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    config = ExecutionConfig(
        slippage_bps=args.slippage,
        commission_per_share=args.commission,
    )

    prov = get_provider(args.provider) if args.provider else None

    result = run_multi_symbol_day_backtest(
        symbols=symbols,
        start_date=args.start,
        end_date=args.end,
        config=config,
        provider=prov,
        include_market_context=not args.no_market_context,
    )

    # Hisobotni chop etish
    report_text = format_multi_symbol_report(result)
    print(report_text)

    # JSON natijani saqlash
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\n[INFO] Machine-readable JSON output saved to: {out_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
