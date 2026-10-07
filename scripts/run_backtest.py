"""Minimal signal + backtest runner: har symbol uchun metrikalar va buy&hold solishtiruvini chop etadi.

FALSAFA: backtest yashil chiqmasa ham OK — maqsad strategiyaning haqiqatan edge
bor-yo'qligini o'lchash, taxmin qilish emas.

Ishlatish:
    python scripts/run_backtest.py [SYMBOLS...] [--interval 1d] [--provider yfinance|alpaca]
        [--mult 1.5] [--risk-model fixed_pct|atr] [--risk-pct 0.01] [--capital 10000]

Masalan: python scripts/run_backtest.py SPUS --interval 1d
         python scripts/run_backtest.py --interval 1d --risk-model atr

SYMBOLS berilmasa — config/watchlist.py'dagi halal ETF ro'yxati ishlatiladi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_backtest  # noqa: E402
from config.settings import PRIMARY_INTERVAL, SWING_LOOKBACK  # noqa: E402
from config.watchlist import get_watchlist  # noqa: E402
from data.factory import get_provider  # noqa: E402
from smc.signal import generate_signals  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal signal + backtest runner")
    parser.add_argument("symbols", nargs="*", help="Masalan: SPUS HLAL. Bo'sh bo'lsa watchlist ishlatiladi")
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d")
    parser.add_argument(
        "--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)"
    )
    parser.add_argument("--mult", type=float, default=None, help="Displacement ATR mult (default: settings)")
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--risk-model", default="fixed_pct", choices=["fixed_pct", "atr"])
    parser.add_argument("--risk-pct", type=float, default=0.01)
    parser.add_argument("--capital", type=float, default=10_000.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else get_watchlist()
    provider = get_provider(args.provider)

    rows: list[dict] = []

    for symbol in symbols:
        try:
            df = provider.get_ohlcv(symbol, args.interval)
        except Exception as exc:
            print(f"{symbol}: xato - {exc}")
            continue

        signals = generate_signals(df, lookback=args.lookback, mult=args.mult)
        result = run_backtest(
            df,
            signals,
            initial_capital=args.capital,
            risk_model=args.risk_model,
            risk_pct=args.risk_pct,
        )

        row = {"SYMBOL": symbol, "BARS": len(df), "SIGNALS": len(signals)}
        row.update({k: round(v, 3) if isinstance(v, float) else v for k, v in result.metrics.items()})
        rows.append(row)

    if not rows:
        print("Hech qanday natija yo'q — barcha symbol'lar xato berdi.")
        return

    result_df = pd.DataFrame(rows)
    print(f"risk_model={args.risk_model}, risk_pct={args.risk_pct}, interval={args.interval}")
    print(result_df.to_string(index=False))

    if len(result_df) > 1:
        numeric_cols = result_df.select_dtypes(include="number").columns
        aggregate = result_df[numeric_cols].mean(numeric_only=True)
        print("\nO'rtacha (barcha symbol'lar bo'yicha):")
        print(aggregate.to_string())


if __name__ == "__main__":
    main()
