"""Fixed vs trailing exit rejimlarini yonma-yon solishtirish.

Bu skript YANGI strategiya logikasi QO'SHMAYDI — bir xil signal (entry) ro'yxatini
IKKI marta simulyatsiya qiladi (exit_mode="fixed" va "trailing"), shuning uchun
solishtiruv "bir xil entry, boshqa exit" printsipiga to'g'ri keladi.

Ishlatish:
    python scripts/exit_comparison.py [SYMBOLS...] [--interval 1d] [--mult 1.5]

Masalan: python scripts/exit_comparison.py --interval 1d
         python scripts/exit_comparison.py SPUS AAPL --mult 1.0

SYMBOLS berilmasa — DEFAULT_SYMBOLS (Phase 6/6b'dagi tekshiruv to'plami) ishlatiladi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_backtest  # noqa: E402
from config.settings import SWING_LOOKBACK  # noqa: E402
from data.factory import get_provider  # noqa: E402
from smc.signal import generate_signals  # noqa: E402

DEFAULT_SYMBOLS: list[str] = ["SPUS", "HLAL", "AAPL", "AMD", "AVGO", "FSLR"]

# Kam savdoli natijaga "yuqori edge" sifatida ishonmaslik uchun (Phase 6'dagi konvensiya)
LOW_SAMPLE_THRESHOLD: int = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fixed vs trailing exit solishtiruvi")
    parser.add_argument("symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Bo'sh bo'lsa DEFAULT_SYMBOLS")
    parser.add_argument("--interval", default="1d", help="Masalan: 1d")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)")
    parser.add_argument("--mult", type=float, default=None, help="Displacement ATR mult (default: settings)")
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--risk-model", default="fixed_pct", choices=["fixed_pct", "atr"])
    return parser.parse_args()


def _metrics_row(symbol: str, exit_mode: str, metrics: dict) -> dict:
    edge = metrics["total_return_pct"] - metrics["buy_hold_return_pct"]
    profit_factor = metrics["profit_factor"]
    return {
        "SYMBOL": symbol,
        "EXIT_MODE": exit_mode,
        "TRADES": metrics["num_trades"],
        "WIN%": round(metrics["win_rate"] * 100, 2),
        "AVG_R": round(metrics["avg_r_multiple"], 3),
        "EXPECTANCY": round(metrics["expectancy_r"], 3),
        "PROFIT_FACTOR": profit_factor if profit_factor == float("inf") else round(profit_factor, 3),
        "RETURN%": round(metrics["total_return_pct"], 3),
        "MAXDD%": round(metrics["max_drawdown_pct"], 3),
        "BUY&HOLD%": round(metrics["buy_hold_return_pct"], 3),
        "EDGE": round(edge, 3),
        "AVG_HOLD_DAYS": round(metrics["avg_hold_days"], 2),
        "LOW_SAMPLE": metrics["num_trades"] < LOW_SAMPLE_THRESHOLD,
        "ERROR": None,
    }


def _error_row(symbol: str, exit_mode: str, exc: Exception) -> dict:
    return {
        "SYMBOL": symbol, "EXIT_MODE": exit_mode, "TRADES": None, "WIN%": None,
        "AVG_R": None, "EXPECTANCY": None, "PROFIT_FACTOR": None, "RETURN%": None,
        "MAXDD%": None, "BUY&HOLD%": None, "EDGE": None, "AVG_HOLD_DAYS": None,
        "LOW_SAMPLE": None, "ERROR": str(exc),
    }


def run_one_symbol_comparison(
    symbol: str, interval: str, provider_name: str | None, mult: float | None,
    lookback: int, risk_model: str,
) -> list[dict]:
    """Bitta symbol uchun fixed va trailing natijalarini qaytaradi (bir xil signal'lar bilan)."""
    try:
        df = get_provider(provider_name).get_ohlcv(symbol, interval)
        signals = generate_signals(df, lookback=lookback, mult=mult)
    except Exception as exc:
        return [_error_row(symbol, "fixed", exc), _error_row(symbol, "trailing", exc)]

    rows = []
    for exit_mode in ("fixed", "trailing"):
        try:
            result = run_backtest(df, signals, risk_model=risk_model, exit_mode=exit_mode)
            rows.append(_metrics_row(symbol, exit_mode, result.metrics))
        except Exception as exc:
            rows.append(_error_row(symbol, exit_mode, exc))
    return rows


def build_matrix(
    symbols: list[str], interval: str, provider_name: str | None, mult: float | None,
    lookback: int, risk_model: str,
) -> pd.DataFrame:
    rows = [
        row
        for symbol in symbols
        for row in run_one_symbol_comparison(symbol, interval, provider_name, mult, lookback, risk_model)
    ]
    return pd.DataFrame(rows)


def print_summary(matrix: pd.DataFrame) -> None:
    valid = matrix[matrix["ERROR"].isna()]
    fixed = valid[valid["EXIT_MODE"] == "fixed"]
    trailing = valid[valid["EXIT_MODE"] == "trailing"]

    if fixed.empty or trailing.empty:
        print("Solishtirish uchun yetarli xatosiz natija yo'q.")
        return

    fixed_edge, trailing_edge = fixed["EDGE"].mean(), trailing["EDGE"].mean()
    fixed_exp, trailing_exp = fixed["EXPECTANCY"].mean(), trailing["EXPECTANCY"].mean()
    fixed_hold, trailing_hold = fixed["AVG_HOLD_DAYS"].mean(), trailing["AVG_HOLD_DAYS"].mean()

    print(f"FIXED:    o'rtacha EDGE={fixed_edge:.2f}, expectancy={fixed_exp:.3f}R, avg_hold={fixed_hold:.1f} kun")
    print(f"TRAILING: o'rtacha EDGE={trailing_edge:.2f}, expectancy={trailing_exp:.3f}R, avg_hold={trailing_hold:.1f} kun")

    edge_diff = trailing_edge - fixed_edge
    if edge_diff > 0:
        verdict = "TRAILING yaxshiroq"
    elif edge_diff < 0:
        verdict = "FIXED yaxshiroq"
    else:
        verdict = "farq yo'q"
    print(f"Farq (trailing - fixed) EDGE bo'yicha: {edge_diff:+.2f} -> {verdict}")

    if valid["LOW_SAMPLE"].any():
        print(
            "\nOGOHLANTIRISH: ba'zi natijalar LOW_SAMPLE=True "
            f"(savdolar soni < {LOW_SAMPLE_THRESHOLD}) — bunday natijalarga to'liq ishonmang."
        )


def main() -> None:
    args = parse_args()
    matrix = build_matrix(args.symbols, args.interval, args.provider, args.mult, args.lookback, args.risk_model)

    print(matrix.to_string(index=False))

    n_errors = matrix["ERROR"].notna().sum()
    if n_errors:
        print(f"\n{n_errors} kombinatsiya xato berdi:")
        print(matrix[matrix["ERROR"].notna()][["SYMBOL", "EXIT_MODE", "ERROR"]].to_string(index=False))

    print()
    print_summary(matrix)


if __name__ == "__main__":
    main()
