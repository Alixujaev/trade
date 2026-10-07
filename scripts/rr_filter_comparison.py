"""R:R filtrsiz vs filtrli backtest natijalarini yonma-yon solishtirish.

Bu skript YANGI strategiya logikasi QO'SHMAYDI — bir xil signal (entry)
ro'yxatini IKKI marta simulyatsiya qiladi: (1) filtrsiz — barcha signal, (2)
filtrli — faqat planned_rr >= MIN_PLANNED_RR bo'lgan signal (smc.signal
::filter_by_planned_rr bilan, backtest/engine.py'ga TEGILMAYDI). Maqsad:
live skanerdagi R:R filtri (telegram_bot/scan) HAQIQIY backtest expectancy/edge
ko'rsatkichlarini yaxshilaydimi, aniqlash — scripts/exit_comparison.py (Stage
1, fixed vs trailing solishtiruvi) bilan bir xil metodologiya/tuzilish.

Ishlatish:
    python scripts/rr_filter_comparison.py [SYMBOLS...] [--interval 1d]
        [--exit-mode fixed|trailing] [--min-rr 1.5]

SYMBOLS berilmasa — watchlist'dan birinchi DEFAULT_SAMPLE_SIZE ta (to'liq
watchlist 200+ belgidan iborat bo'lgani uchun sekin bo'lmasin, foydalanuvchi
xohlagan belgilarni CLI orqali bera oladi).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_backtest  # noqa: E402
from config.core_watchlist import get_core_watchlist  # noqa: E402
from config.settings import MIN_PLANNED_RR, SWING_LOOKBACK  # noqa: E402
from data.factory import get_provider  # noqa: E402
from scripts.tactical_scan import DEFAULT_EXIT_MODE  # noqa: E402
from smc.signal import filter_by_planned_rr, generate_signals  # noqa: E402

DEFAULT_SAMPLE_SIZE: int = 25

# Kam savdoli natijaga "yuqori expectancy" sifatida ishonmaslik uchun (Phase 6'dagi konvensiya)
LOW_SAMPLE_THRESHOLD: int = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="R:R filtr backtest solishtiruvi (expectancy ta'siri)")
    parser.add_argument(
        "symbols", nargs="*", help="Bo'sh bo'lsa watchlist'dan birinchi DEFAULT_SAMPLE_SIZE ta"
    )
    parser.add_argument("--interval", default="1d", help="Masalan: 1d")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)")
    parser.add_argument("--mult", type=float, default=None, help="Displacement ATR mult (default: settings)")
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--exit-mode", default=DEFAULT_EXIT_MODE, choices=["fixed", "trailing"])
    parser.add_argument("--risk-model", default="fixed_pct", choices=["fixed_pct", "atr"])
    parser.add_argument(
        "--min-rr", type=float, default=MIN_PLANNED_RR, help="Filtrli variant uchun chegara (default: settings.MIN_PLANNED_RR)"
    )
    return parser.parse_args()


def _metrics_row(symbol: str, label: str, metrics: dict) -> dict:
    edge = metrics["total_return_pct"] - metrics["buy_hold_return_pct"]
    pf = metrics["profit_factor"]
    return {
        "SYMBOL": symbol,
        "FILTER": label,
        "TRADES": metrics["num_trades"],
        "WIN%": round(metrics["win_rate"] * 100, 2),
        "AVG_R": round(metrics["avg_r_multiple"], 3),
        "EXPECTANCY": round(metrics["expectancy_r"], 3),
        "PROFIT_FACTOR": pf if pf == float("inf") else round(pf, 3),
        "RETURN%": round(metrics["total_return_pct"], 3),
        "MAXDD%": round(metrics["max_drawdown_pct"], 3),
        "BUY&HOLD%": round(metrics["buy_hold_return_pct"], 3),
        "EDGE": round(edge, 3),
        "AVG_HOLD_DAYS": round(metrics["avg_hold_days"], 2),
        "LOW_SAMPLE": metrics["num_trades"] < LOW_SAMPLE_THRESHOLD,
        "ERROR": None,
    }


def _error_row(symbol: str, label: str, exc: Exception) -> dict:
    return {
        "SYMBOL": symbol, "FILTER": label, "TRADES": None, "WIN%": None,
        "AVG_R": None, "EXPECTANCY": None, "PROFIT_FACTOR": None, "RETURN%": None,
        "MAXDD%": None, "BUY&HOLD%": None, "EDGE": None, "AVG_HOLD_DAYS": None,
        "LOW_SAMPLE": None, "ERROR": str(exc),
    }


def run_one_symbol_comparison(
    symbol: str, interval: str, provider_name: str | None, mult: float | None,
    lookback: int, exit_mode: str, risk_model: str, min_rr: float,
) -> list[dict]:
    """Bitta symbol uchun filtrsiz va filtrli natijalarini qaytaradi (bir xil signal'lar bilan)."""
    try:
        df = get_provider(provider_name).get_ohlcv(symbol, interval)
        signals = generate_signals(df, lookback=lookback, mult=mult)
    except Exception as exc:
        return [_error_row(symbol, "unfiltered", exc), _error_row(symbol, "filtered", exc)]

    rows = []
    for label, rr_threshold in (("unfiltered", None), ("filtered", min_rr)):
        try:
            filtered_signals = filter_by_planned_rr(signals, rr_threshold)
            result = run_backtest(df, filtered_signals, risk_model=risk_model, exit_mode=exit_mode)
            rows.append(_metrics_row(symbol, label, result.metrics))
        except Exception as exc:
            rows.append(_error_row(symbol, label, exc))
    return rows


def build_matrix(
    symbols: list[str], interval: str, provider_name: str | None, mult: float | None,
    lookback: int, exit_mode: str, risk_model: str, min_rr: float,
) -> pd.DataFrame:
    rows = [
        row
        for symbol in symbols
        for row in run_one_symbol_comparison(
            symbol, interval, provider_name, mult, lookback, exit_mode, risk_model, min_rr
        )
    ]
    return pd.DataFrame(rows)


def print_summary(matrix: pd.DataFrame, min_rr: float) -> None:
    valid = matrix[matrix["ERROR"].isna()]
    unfiltered = valid[valid["FILTER"] == "unfiltered"]
    filtered = valid[valid["FILTER"] == "filtered"]

    if unfiltered.empty or filtered.empty:
        print("Solishtirish uchun yetarli xatosiz natija yo'q.")
        return

    unf_exp, filt_exp = unfiltered["EXPECTANCY"].mean(), filtered["EXPECTANCY"].mean()
    unf_trades, filt_trades = unfiltered["TRADES"].mean(), filtered["TRADES"].mean()
    unf_edge, filt_edge = unfiltered["EDGE"].mean(), filtered["EDGE"].mean()

    print(f"FILTRSIZ: o'rtacha expectancy={unf_exp:.3f}R, o'rtacha savdolar={unf_trades:.1f}, o'rtacha EDGE={unf_edge:.2f}")
    print(f"FILTRLI (min_rr={min_rr}): o'rtacha expectancy={filt_exp:.3f}R, o'rtacha savdolar={filt_trades:.1f}, o'rtacha EDGE={filt_edge:.2f}")
    print()

    exp_diff = filt_exp - unf_exp
    print(f"1) Expectancy farqi (filtrli - filtrsiz): {exp_diff:+.3f}R")

    trades_diff = filt_trades - unf_trades
    print(f"2) Savdo soni farqi (exposure narxi, o'rtacha): {trades_diff:+.1f}")

    edge_diff = filt_edge - unf_edge
    verdict = "buy&hold'ga YAQINLASHDI" if edge_diff > 0 else "buy&hold'dan UZOQLASHDI (yoki farq yo'q)"
    print(f"3) EDGE farqi (buy&hold'ga nisbatan): {edge_diff:+.2f} -> filtrli versiya {verdict}")
    print()

    if exp_diff > 0 and filt_edge < 0:
        print(
            "XULOSA: filtr signal SIFATINI (expectancy) yaxshiladi, lekin EDGE hali manfiy — "
            "filtr signalni yaxshiladi, lekin buy&hold'ni yengmaydi."
        )
    elif exp_diff > 0 and filt_edge >= 0:
        print("XULOSA: filtr expectancy'ni yaxshiladi VA EDGE musbat — filtrli strategiya buy&hold'ni yengadi.")
    else:
        print("XULOSA: filtr expectancy'ni yaxshilamadi — past R:R setup'larni yashirish savdo SIFATINI oshirmadi.")

    if valid["LOW_SAMPLE"].any():
        print(
            f"\nOGOHLANTIRISH: ba'zi natijalar LOW_SAMPLE=True (savdolar soni < {LOW_SAMPLE_THRESHOLD}) — "
            "filtrlangandan keyin savdo soni keskin kamayishi mumkin, bunday 'yuqori expectancy'ga to'liq ishonmang."
        )


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()[:DEFAULT_SAMPLE_SIZE]]

    matrix = build_matrix(
        symbols, args.interval, args.provider, args.mult, args.lookback,
        args.exit_mode, args.risk_model, args.min_rr,
    )

    print(matrix.to_string(index=False))

    n_errors = matrix["ERROR"].notna().sum()
    if n_errors:
        print(f"\n{n_errors} kombinatsiya xato berdi:")
        print(matrix[matrix["ERROR"].notna()][["SYMBOL", "FILTER", "ERROR"]].to_string(index=False))

    print()
    print_summary(matrix, args.min_rr)


if __name__ == "__main__":
    main()
