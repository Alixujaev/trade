"""scripts/backtest_day_stock_in_play_thresholds.py: DAY-06A Gap Threshold Robustness Research CLI.

QAT'IY METODOLOGIK QOIDALAR:
- Thresholdlar oldindan qat'iy belgilangan: 1.0%, 2.0%, 3.0%, 4.0%.
- Hech qanday threshold tuning yoki optimizatsiya qilinmaydi.
- Parametrlarni qidirish (grid search / hunt) flaglari QAT'IYAN TAQIQLANGAN.

Usage:
    python scripts/backtest_day_stock_in_play_thresholds.py
    python scripts/backtest_day_stock_in_play_thresholds.py --symbols AAPL,MSFT,NVDA
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
    GapThresholdSensitivityResult,
    format_gap_threshold_report,
    run_gap_threshold_sensitivity_backtest,
)
from config.day_universe import get_day_universe
from data.factory import get_provider

# Qat'iy oldindan belgilangan thresholdlar to'plami (Pre-declared fixed set)
GAP_THRESHOLDS_PCT: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DAY-06A: Gap Threshold Robustness / Stability Test Runner",
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
        "--provider",
        type=str,
        default="yfinance",
        help="Ma'lumotlar provayderi (yfinance yoki alpaca)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="artifacts/day06a/gap-threshold-results.json",
        help="Chiqariladigan JSON hisobot yo'li.",
    )
    parser.add_argument(
        "--txt-out",
        type=str,
        default="artifacts/day06a/gap-threshold-report.txt",
        help="Chiqariladigan TXT hisobot yo'li.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Terminalga to'liq hisobot jadvalini chiqarmaslik.",
    )

    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_day_universe()

    print("=" * 95)
    print("DAY-06A: GAP THRESHOLD ROBUSTNESS / STABILITY TEST")
    print("=" * 95)
    print(f"Symbols requested : {len(symbols_list)} ({', '.join(symbols_list[:5])}...)")
    print(f"Fixed thresholds  : {', '.join(f'{t:.1f}%' for t in GAP_THRESHOLDS_PCT)} (Pre-declared, zero optimization)")
    print("Running Baseline vs Fixed Gap Thresholds...")

    start_time = time.perf_counter()
    prov = get_provider(args.provider) if hasattr(get_provider, "__call__") else get_provider()

    result = run_gap_threshold_sensitivity_backtest(
        symbols=symbols_list,
        thresholds=GAP_THRESHOLDS_PCT,
        provider=prov,
    )
    elapsed = time.perf_counter() - start_time

    txt_report = format_gap_threshold_report(result)

    if not args.quiet:
        print("\n" + txt_report)

    print("\n" + "=" * 95)
    print(f"Sensitivity run completed in {elapsed:.2f} seconds.")
    print(f"Baseline trades : {result.baseline.total_trades:,}")
    for t_str, vm in result.threshold_variants.items():
        print(f"Gap >= {t_str:<6} : {vm.total_trades:,} trades (-{vm.trade_reduction_pct:.1f}% reduction) | WR: {vm.win_rate:.1f}% | Total R: {vm.total_R:.1f}R | Gross 0bps: {vm.slippage_0bps:+.1f}%")

    # JSON hisobotni saqlash
    json_path = ROOT_DIR / args.json_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"JSON artifact saved to: {json_path}")

    # TXT hisobotni saqlash
    txt_path = ROOT_DIR / args.txt_out
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_report)
    print(f"TXT artifact saved to:  {txt_path}")
    print("=" * 95)

    return 0


if __name__ == "__main__":
    sys.exit(main())
