"""Portfolio-darajali breakout+retest backtest — bitta umumiy kapital, konkurent pozitsiyalar.

`scripts/backtest_breakout_retest.py::portfolio_equity_curve` savdolarni bittalab
ketma-ket kompaundlaydi (norealistik ~22x equity, soxta ~4% DD). Bu skript
`backtest.portfolio.simulate_portfolio` ni ishga tushiradi: yagona kalendar, ko'pi
bilan `--max-concurrent` pozitsiya, ochiq risk `--max-portfolio-risk` bilan cheklangan,
leverage yo'q, har bar mark-to-market equity → haqiqiy max DD / CAGR / Sharpe / Sortino.
Oxirida ESKI (ketma-ket) vs YANGI (portfel) natijani yonma-yon ko'rsatadi.

Chiqishda Robot vs teng-vazn buy&hold vs bitta-ticker buy&hold bitta jadvalda,
bir xil ustunlar bilan (total_return%, cagr%, max_dd%, sharpe, sortino).
--oos-start berilsa TRAIN va OOS oynalar alohida jadval bilan chiqadi.

Ishlatish:
    python scripts/backtest_portfolio.py [SYMBOLS...] \
        [--start 2020-09-01] [--end 2025-09-01] [--oos-start 2023-09-01] \
        [--interval 1d] [--provider yfinance] \
        [--commission-pct 0.0005] [--slippage-pct 0.0005] [--min-score 60] \
        [--max-concurrent 10] [--max-portfolio-risk 0.10] \
        [--risk-model fixed_pct|atr] [--exit-mode fixed|trailing] \
        [--initial-capital 100000] [--benchmark-ticker SPUS] \
        [--capital-constrained-benchmark] [--output-csv portfolio_backtest_results.csv]

SYMBOLS bo'sh -> get_core_watchlist() (6 curated + 211 HLAL). --start bo'sh -> ~5 yil oldin.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.metrics import max_drawdown_pct  # noqa: E402
from backtest.portfolio import (  # noqa: E402
    PortfolioConfig,
    PortfolioResult,
    SymbolData,
    build_symbol_data,
    run_portfolio,
)
from backtest.window import slice_date_range  # noqa: E402
from config.core_watchlist import get_core_watchlist  # noqa: E402
from config.settings import (  # noqa: E402
    BREAKOUT_COMMISSION_PCT,
    BREAKOUT_SLIPPAGE_PCT,
    MAX_CONCURRENT_POSITIONS,
    MAX_PORTFOLIO_RISK_PCT,
    MIN_BREAKOUT_RR,
    SWING_LOOKBACK,
)
from data.factory import get_provider  # noqa: E402
from scripts.backtest_breakout_retest import five_years_ago_iso  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portfolio-darajali breakout+retest backtest")
    parser.add_argument("symbols", nargs="*", help="Bo'sh bo'lsa get_core_watchlist()")
    parser.add_argument("--start", default=None, help="ISO sana; bo'sh -> ~5 yil oldin")
    parser.add_argument("--end", default=None, help="ISO sana; bo'sh -> oxirigacha")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca")
    parser.add_argument("--commission-pct", type=float, default=BREAKOUT_COMMISSION_PCT)
    parser.add_argument("--slippage-pct", type=float, default=BREAKOUT_SLIPPAGE_PCT)
    parser.add_argument("--min-score", type=float, default=None,
                        help="berilsa: faqat 0-100 balli shu qiymatdan yuqori setup'lar")
    parser.add_argument("--max-concurrent", type=int, default=MAX_CONCURRENT_POSITIONS)
    parser.add_argument("--max-portfolio-risk", type=float, default=MAX_PORTFOLIO_RISK_PCT)
    parser.add_argument("--risk-model", default="fixed_pct", choices=["fixed_pct", "atr"])
    parser.add_argument("--exit-mode", default="fixed", choices=["fixed", "trailing"])
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--min-rr", type=float, default=MIN_BREAKOUT_RR)
    parser.add_argument("--require-trend", dest="require_trend", action="store_true", default=True)
    parser.add_argument("--no-require-trend", dest="require_trend", action="store_false")
    parser.add_argument("--benchmark-ticker", default="SPUS")
    parser.add_argument(
        "--oos-start", default=None,
        help="ISO sana: berilsa train=[--start, --oos-start) va OOS=[--oos-start, --end] "
             "alohida hisoblanadi (walk-forward)",
    )
    parser.add_argument(
        "--capital-constrained-benchmark", dest="capital_constrained_benchmark",
        action="store_true", default=False,
        help="4-benchmark qatori: robot signallari, max_concurrent slot, teng-vazn, chiqmasdan buy&hold",
    )
    parser.add_argument("--output-csv", default="portfolio_backtest_results.csv")
    return parser.parse_args()


def load_universe(
    symbols: list[str],
    *,
    interval: str,
    provider_name: str | None,
    start: str | None,
    end: str | None,
    lookback: int,
    min_rr: float,
    require_trend: bool,
    min_score: float | None,
) -> tuple[list[SymbolData], list[dict]]:
    """Har symbol uchun SymbolData quradi. HECH QACHON raise qilmaydi — xato qatorlari ajratiladi."""
    data: list[SymbolData] = []
    error_rows: list[dict] = []
    for symbol in symbols:
        try:
            df = get_provider(provider_name).get_ohlcv(symbol, interval)
            sd = build_symbol_data(
                symbol, df, start=start, end=end, lookback=lookback, min_rr=min_rr,
                require_trend=require_trend, min_score=min_score,
            )
            if sd is None:
                error_rows.append({"SYMBOL": symbol, "ERROR": "yetarsiz data"})
            else:
                data.append(sd)
        except Exception as exc:  # noqa: BLE001
            error_rows.append({"SYMBOL": symbol, "ERROR": str(exc)})
    return data, error_rows


def load_benchmark_df(
    ticker: str, *, interval: str, provider_name: str | None, start: str | None, end: str | None
) -> tuple[pd.DataFrame | None, str | None]:
    """Benchmark ticker OHLCV'sini yuklab, oynaga kesadi. Xato -> (None, xabar)."""
    try:
        df = get_provider(provider_name).get_ohlcv(ticker, interval)
        df = slice_date_range(df, start, end)
        if df is None or len(df) < 2:
            return None, f"{ticker}: yetarsiz data"
        return df, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def run_one_window(
    args: argparse.Namespace, *, start: str | None, end: str | None
) -> tuple[PortfolioResult, list[dict]]:
    """Bitta [start, end] oynasi uchun portfel natijasi (+ xato qatorlari)."""
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]

    data, error_rows = load_universe(
        symbols, interval=args.interval, provider_name=args.provider, start=start, end=end,
        lookback=args.lookback, min_rr=args.min_rr, require_trend=args.require_trend,
        min_score=args.min_score,
    )
    cfg = PortfolioConfig(
        initial_capital=args.initial_capital,
        max_concurrent_positions=args.max_concurrent,
        max_portfolio_risk_pct=args.max_portfolio_risk,
        risk_model=args.risk_model,
        exit_mode=args.exit_mode,
        commission_pct=args.commission_pct,
        slippage_pct=args.slippage_pct,
        interval=args.interval,
    )
    bench_df, _bench_err = load_benchmark_df(
        args.benchmark_ticker, interval=args.interval, provider_name=args.provider, start=start, end=end,
    )
    result = run_portfolio(
        data, cfg=cfg, benchmark_df=bench_df, benchmark_ticker=args.benchmark_ticker,
        include_constrained=args.capital_constrained_benchmark,
    )
    return result, error_rows


def run(args: argparse.Namespace) -> tuple[PortfolioResult, list[dict]]:
    """Bitta oynali (--oos-start'siz) qulaylik wrapper'i."""
    return run_one_window(args, start=args.start or five_years_ago_iso(), end=args.end)


def run_windows(
    args: argparse.Namespace,
) -> list[tuple[str, str, str | None, PortfolioResult, list[dict]]]:
    """--oos-start berilsa (TRAIN, OOS), aks holda (TO'LIQ) — har biri (label, start, end, result, errors)."""
    start = args.start or five_years_ago_iso()
    if not args.oos_start:
        result, errs = run_one_window(args, start=start, end=args.end)
        return [("TO'LIQ", start, args.end, result, errs)]

    train_end = (pd.Timestamp(args.oos_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    train_result, train_errs = run_one_window(args, start=start, end=train_end)
    oos_result, oos_errs = run_one_window(args, start=args.oos_start, end=args.end)
    return [
        ("TRAIN", start, train_end, train_result, train_errs),
        ("OOS", args.oos_start, args.end, oos_result, oos_errs),
    ]


_TABLE_COLS = ["strategy", "total_return%", "cagr%", "max_dd%", "sharpe", "sortino"]
_BENCH_LABELS = {
    "equal_weight_buy_hold": "Teng-vazn buy&hold",
    "capital_constrained_buy_hold": "Constrained buy&hold",
}


def unified_table(result: PortfolioResult) -> pd.DataFrame:
    """Robot vs har benchmark — bir xil ustunlar (total_return%, cagr%, max_dd%, sharpe, sortino)."""
    m = result.metrics
    rows = [{
        "strategy": "Robot (portfel)",
        "total_return%": m["total_return_pct"], "cagr%": m["cagr_pct"],
        "max_dd%": m["max_drawdown_pct"], "sharpe": m["sharpe"], "sortino": m["sortino"],
    }]
    for b in result.benchmarks:
        label = _BENCH_LABELS.get(b.name, b.name)
        if b.metrics:
            bm = b.metrics
            rows.append({
                "strategy": label,
                "total_return%": bm["return_pct"], "cagr%": bm["cagr_pct"],
                "max_dd%": bm["max_drawdown_pct"], "sharpe": bm["sharpe"], "sortino": bm["sortino"],
            })
        else:
            rows.append({
                "strategy": label, "total_return%": None, "cagr%": None,
                "max_dd%": None, "sharpe": None, "sortino": None,
            })
    df = pd.DataFrame(rows, columns=_TABLE_COLS)
    for c in ("total_return%", "cagr%", "max_dd%"):
        df[c] = df[c].astype(float).round(2)
    for c in ("sharpe", "sortino"):
        df[c] = df[c].astype(float).round(3)
    return df


def build_trade_rows(result: PortfolioResult, *, window: str = "TO'LIQ") -> pd.DataFrame:
    """Har yopilgan savdo -> bir CSV qator (sof funksiya, IO yo'q)."""
    rows = [
        {
            "WINDOW": window,
            "SYMBOL": sym,
            "ENTRY_TS": t.entry_ts,
            "EXIT_TS": t.exit_ts,
            "ENTRY_PRICE": round(t.entry_price, 4),
            "EXIT_PRICE": round(t.exit_price, 4),
            "SHARES": round(t.shares, 6),
            "EXIT_REASON": t.exit_reason,
            "R_MULTIPLE": round(t.r_multiple, 4),
            "PNL": round(t.pnl, 2),
            "HOLD_DAYS": round(t.hold_duration_days, 2),
            "MAE_R": round(t.mae_r, 4),
            "MFE_R": round(t.mfe_r, 4),
        }
        for sym, t in zip(result.trade_symbols, result.trades)
    ]
    return pd.DataFrame(rows, columns=[
        "WINDOW", "SYMBOL", "ENTRY_TS", "EXIT_TS", "ENTRY_PRICE", "EXIT_PRICE", "SHARES",
        "EXIT_REASON", "R_MULTIPLE", "PNL", "HOLD_DAYS", "MAE_R", "MFE_R",
    ])


def summarize(result: PortfolioResult, *, old_curve: list[float] | None = None) -> dict:
    """ESKI (barcha signal, cap'siz ketma-ket kompaund) vs YANGI (portfel) + 2 benchmark."""
    m = result.metrics
    curve = old_curve if old_curve is not None else result.naive_all_signals_curve
    old_final = curve[-1] if curve else 1.0
    old_dd = max_drawdown_pct(curve)
    old_n = max(len(curve) - 1, 0)
    out: dict = {
        "old_final_multiple": round(old_final, 3),
        "old_max_dd_pct": round(old_dd, 2),
        "old_num_signals": old_n,
        "new_return_pct": round(m["total_return_pct"], 2),
        "new_cagr_pct": round(m["cagr_pct"], 2),
        "new_max_dd_pct": round(m["max_drawdown_pct"], 2),
        "new_sharpe": round(m["sharpe"], 3),
        "new_sortino": round(m["sortino"], 3),
        "new_num_trades": m["num_trades"],
        "new_num_skipped": m["num_skipped"],
        "new_skipped_by_reason": m["skipped_by_reason"],
        "new_avg_concurrent": round(m["avg_concurrent_positions"], 2),
        "new_max_concurrent": m["max_concurrent_positions"],
    }
    for b in result.benchmarks:
        if b.metrics:
            out[b.name] = {k: round(v, 2) for k, v in b.metrics.items()}
        else:
            out[b.name] = {"error": b.error}
    out["explanation"] = (
        f"NEGA FARQ QILADI: ESKI usul universe'ning BARCHA {old_n} signalini (cheklovsiz) "
        f"entry sanasi bo'yicha QAT'IY KETMA-KET kompaundlaydi -> ustma-ust savdolarni "
        f"hisobga olmaydi, kapital norealni ~{old_final:.1f}x oshadi, DD ~{old_dd:.1f}%. "
        f"YANGI: bitta umumiy hisob, bir vaqtda ko'pi bilan {m['max_concurrent_positions']} "
        f"pozitsiya, portfel riski cheklangan (shu bois {m['num_skipped']} signal o'tkazib "
        f"yuborildi); DD har bar mark-to-market equity bo'yicha (ochiq pozitsiyalar ham "
        f"baholanadi). Natija: past return, lekin haqiqiy DD / Sharpe / Sortino."
    )
    return out


def print_window_report(
    label: str,
    start: str,
    end: str | None,
    result: PortfolioResult,
    error_rows: list[dict],
    *,
    show_explanation: bool,
) -> None:
    m = result.metrics
    print(f"\n=== {label}  ({start} .. {end or 'oxirigacha'}) ===")
    print(
        f"timeline_bars={len(result.timeline)}  savdolar={m['num_trades']}  "
        f"o'tkazilgan={m['num_skipped']}  o'rtacha_konkurent={round(m['avg_concurrent_positions'], 2)} "
        f"(cap={m['max_concurrent_positions']})"
    )
    if error_rows:
        print(f"{len(error_rows)} symbol yuklanmadi/yetarsiz.")

    print(unified_table(result).to_string(index=False))

    naive = result.naive_all_signals_curve
    if naive and len(naive) > 1:
        print(
            f"[ESKI ketma-ket kompaund, {len(naive) - 1} signal, 1.0 boshlanish]: "
            f"final={naive[-1]:.1f}x  max_dd={max_drawdown_pct(naive):.1f}%  "
            f"(portfel o'tkazgan: {m['skipped_by_reason']})"
        )

    if show_explanation:
        print("\n" + summarize(result)["explanation"])


def main() -> None:
    args = parse_args()
    windows = run_windows(args)

    all_rows: list[pd.DataFrame] = []
    for i, (label, start, end, result, error_rows) in enumerate(windows):
        print_window_report(label, start, end, result, error_rows, show_explanation=(i == 0))
        all_rows.append(build_trade_rows(result, window=label))

    pd.concat(all_rows, ignore_index=True).to_csv(args.output_csv, index=False)
    print(f"\nTo'liq savdolar saqlandi: {Path(args.output_csv).resolve()}")


if __name__ == "__main__":
    main()
