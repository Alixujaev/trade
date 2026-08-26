"""Backtest matritsasi: edge QAYERDA (bor bo'lsa) borligini tizimli aniqlash.

Bu skript YANGI strategiya logikasi QO'SHMAYDI — faqat mavjud generate_signals
va run_backtest'ni ko'p (symbol x interval x risk_model x mult) kombinatsiyada
chaqirib, natijalarni bitta jadvalda solishtiradi. "Yaxshi ko'rinishi uchun"
hech qanday parametr sozlanmaydi — biz o'lchayapmiz, sozlamayapmiz.

Ishlatish:
    python scripts/backtest_matrix.py [SYMBOLS...] [--intervals 1d,4h]
        [--providers yfinance,alpaca] [--risk-models fixed_pct,atr] [--mults 1.0,1.5]

Masalan: python scripts/backtest_matrix.py SPUS SPWO --intervals 1d
         python scripts/backtest_matrix.py --intervals 1d,4h --risk-models fixed_pct,atr

SYMBOLS berilmasa — watchlist. --providers berilmasa — interval'ga qarab avtomatik
tanlanadi (4h -> alpaca, qolganlari -> yfinance, chunki yfinance 4h bermaydi).
Chiqish: to'liq jadval + qisqa xulosa (eng yaxshi 5 EDGE, TF/symbol o'rtachasi)
+ backtest_results.csv.
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
from config.watchlist import get_watchlist  # noqa: E402
from data.factory import get_provider  # noqa: E402
from smc.signal import generate_signals  # noqa: E402

# Bu chegaradan kam savdoli kombinatsiya "statistik ma'nosiz" deb belgilanadi —
# kam savdoda "yuqori edge" ko'pincha shunchaki tasodif, strategiya sifati emas.
LOW_SAMPLE_THRESHOLD: int = 10


def _default_provider_for_interval(interval: str) -> str:
    """--providers berilmasa, interval'ga mos provayderni avtomatik tanlaydi.

    yfinance "4h"ni toza bermaydi (Phase 1'dan beri ma'lum cheklov) — shuning
    uchun 4h uchun alpaca, qolgan hamma interval uchun yfinance (chuqur tarix).
    """
    return "alpaca" if interval == "4h" else "yfinance"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest matritsasi — tizimli edge qidiruvi")
    parser.add_argument("symbols", nargs="*", help="Bo'sh bo'lsa watchlist ishlatiladi")
    parser.add_argument("--intervals", default="1d", help="Vergul bilan ajratilgan, masalan: 1d,4h")
    parser.add_argument(
        "--providers", default=None,
        help="Vergul bilan ajratilgan (masalan: yfinance,alpaca). Berilmasa interval'ga qarab avtomatik",
    )
    parser.add_argument("--risk-models", default="fixed_pct,atr")
    parser.add_argument("--mults", default="1.0,1.5")
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--low-sample-threshold", type=int, default=LOW_SAMPLE_THRESHOLD)
    parser.add_argument("--output-csv", default="backtest_results.csv")
    return parser.parse_args()


def _empty_metrics_row() -> dict:
    """Xato holatida raqamli ustunlarni None qilib to'ldiradi (CSV/jadvalda bo'sh ko'rinadi)."""
    return {
        "TRADES": None, "WIN%": None, "AVG_R": None, "EXPECTANCY": None,
        "PROFIT_FACTOR": None, "RETURN%": None, "MAXDD%": None,
        "BUY&HOLD%": None, "EDGE": None, "LOW_SAMPLE": None,
    }


def run_one_combination(
    symbol: str,
    interval: str,
    provider_name: str,
    risk_model: str,
    mult: float,
    *,
    lookback: int = SWING_LOOKBACK,
    low_sample_threshold: int = LOW_SAMPLE_THRESHOLD,
) -> dict:
    """Bitta (symbol, interval, provider, risk_model, mult) kombinatsiyasi uchun natija qatori.

    Xato bo'lsa (tarmoq, kredensial, yetarsiz data va h.k.) crash qilmasdan ERROR
    maydoni to'ldirilgan qator qaytaradi — chaqiruvchi (main loop) davom etadi.
    """
    base = {"SYMBOL": symbol, "INTERVAL": interval, "PROVIDER": provider_name,
            "RISK": risk_model, "MULT": mult}
    try:
        df = get_provider(provider_name).get_ohlcv(symbol, interval)
        signals = generate_signals(df, lookback=lookback, mult=mult)
        result = run_backtest(df, signals, risk_model=risk_model)
        m = result.metrics

        edge = m["total_return_pct"] - m["buy_hold_return_pct"]
        profit_factor = m["profit_factor"]

        return {
            **base,
            "TRADES": m["num_trades"],
            "WIN%": round(m["win_rate"] * 100, 2),
            "AVG_R": round(m["avg_r_multiple"], 3),
            "EXPECTANCY": round(m["expectancy_r"], 3),
            "PROFIT_FACTOR": profit_factor if profit_factor == float("inf") else round(profit_factor, 3),
            "RETURN%": round(m["total_return_pct"], 3),
            "MAXDD%": round(m["max_drawdown_pct"], 3),
            "BUY&HOLD%": round(m["buy_hold_return_pct"], 3),
            "EDGE": round(edge, 3),
            "LOW_SAMPLE": m["num_trades"] < low_sample_threshold,
            "ERROR": None,
        }
    except Exception as exc:
        return {**base, **_empty_metrics_row(), "ERROR": str(exc)}


def build_matrix(
    symbols: list[str],
    intervals: list[str],
    providers: list[str] | None,
    risk_models: list[str],
    mults: list[float],
    *,
    lookback: int = SWING_LOOKBACK,
    low_sample_threshold: int = LOW_SAMPLE_THRESHOLD,
) -> pd.DataFrame:
    """Barcha kombinatsiyalar bo'ylab yurib, to'liq natija DataFrame'ini qaytaradi."""
    rows: list[dict] = []
    for symbol in symbols:
        for interval in intervals:
            provider_candidates = providers if providers else [_default_provider_for_interval(interval)]
            for provider_name in provider_candidates:
                for risk_model in risk_models:
                    for mult in mults:
                        rows.append(
                            run_one_combination(
                                symbol, interval, provider_name, risk_model, mult,
                                lookback=lookback, low_sample_threshold=low_sample_threshold,
                            )
                        )
    return pd.DataFrame(rows)


def top_by_edge(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Xatosiz qatorlar orasida EDGE bo'yicha eng yaxshi n tasi (LOW_SAMPLE flag saqlanadi)."""
    valid = df[df["ERROR"].isna()]
    return valid.sort_values("EDGE", ascending=False).head(n)


def aggregate_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Xatosiz qatorlarni berilgan ustun bo'yicha guruhlab, raqamli ustunlar o'rtachasini beradi."""
    valid = df[df["ERROR"].isna()]
    if valid.empty:
        return pd.DataFrame()
    numeric_cols = valid.select_dtypes(include="number").columns
    return valid.groupby(column)[numeric_cols].mean(numeric_only=True)


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else get_watchlist()
    intervals = [i.strip() for i in args.intervals.split(",")]
    providers = [p.strip() for p in args.providers.split(",")] if args.providers else None
    risk_models = [r.strip() for r in args.risk_models.split(",")]
    mults = [float(m.strip()) for m in args.mults.split(",")]

    matrix = build_matrix(
        symbols, intervals, providers, risk_models, mults,
        lookback=args.lookback, low_sample_threshold=args.low_sample_threshold,
    )

    print(f"Jami kombinatsiya: {len(matrix)}")
    print(matrix.to_string(index=False))

    n_errors = matrix["ERROR"].notna().sum()
    if n_errors:
        print(f"\n{n_errors} kombinatsiya xato berdi (yuqoridagi jadvalda ERROR ustuniga qarang).")

    top5 = top_by_edge(matrix, args.top_n)
    print(f"\n--- EDGE bo'yicha eng yaxshi {args.top_n} ---")
    if top5.empty:
        print("Xatosiz natija yo'q.")
    else:
        print(top5.to_string(index=False))
        if top5["LOW_SAMPLE"].any():
            print(
                "\nOGOHLANTIRISH: yuqoridagi ba'zi natijalar LOW_SAMPLE=True "
                f"(savdolar soni < {args.low_sample_threshold}) — bunday 'yuqori edge'ga ishonmang, "
                "statistik ma'nosiz bo'lishi mumkin."
            )

    by_interval = aggregate_by(matrix, "INTERVAL")
    if not by_interval.empty:
        print("\n--- Timeframe bo'yicha o'rtacha ---")
        print(by_interval.to_string())

    by_symbol = aggregate_by(matrix, "SYMBOL")
    if not by_symbol.empty:
        print("\n--- Symbol bo'yicha o'rtacha ---")
        print(by_symbol.to_string())

    matrix.to_csv(args.output_csv, index=False)
    print(f"\nTo'liq natija saqlandi: {Path(args.output_csv).resolve()}")


if __name__ == "__main__":
    main()
