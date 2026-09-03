"""Portfolio-darajali breakout+retest backtest — bitta umumiy kapital, konkurent pozitsiyalar.

`scripts/backtest_breakout_retest.py::portfolio_equity_curve` savdolarni bittalab
ketma-ket kompaundlaydi (norealistik ~22x equity, soxta ~4% DD). Bu skript
`backtest.portfolio.simulate_portfolio` ni ishga tushiradi: yagona kalendar, ko'pi
bilan `--max-concurrent` pozitsiya, ochiq risk `--max-portfolio-risk` bilan cheklangan,
leverage yo'q, har bar mark-to-market equity → haqiqiy max DD / CAGR / Sharpe / Sortino.
Oxirida ESKI (ketma-ket) vs YANGI (portfel) natijani yonma-yon ko'rsatadi.

Ishlatish:
    python scripts/backtest_portfolio.py [SYMBOLS...] \
        [--start 2020-09-01] [--end 2025-09-01] [--interval 1d] [--provider yfinance] \
        [--commission-pct 0.0005] [--slippage-pct 0.0005] [--min-score 60] \
        [--max-concurrent 10] [--max-portfolio-risk 0.10] \
        [--risk-model fixed_pct|atr] [--exit-mode fixed|trailing] \
        [--initial-capital 100000] [--benchmark-ticker SPUS] \
        [--output-csv portfolio_backtest_results.csv]

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


def run(args: argparse.Namespace) -> tuple[PortfolioResult, list[dict]]:
    """CLI argumentlaridan to'liq portfel natijasini (+ xato qatorlari) qaytaradi."""
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]
    start = args.start or five_years_ago_iso()

    data, error_rows = load_universe(
        symbols, interval=args.interval, provider_name=args.provider, start=start, end=args.end,
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
        args.benchmark_ticker, interval=args.interval, provider_name=args.provider,
        start=start, end=args.end,
    )
    result = run_portfolio(data, cfg=cfg, benchmark_df=bench_df, benchmark_ticker=args.benchmark_ticker)
    return result, error_rows


def build_trade_rows(result: PortfolioResult) -> pd.DataFrame:
    """Har yopilgan savdo -> bir CSV qator (sof funksiya, IO yo'q)."""
    rows = [
        {
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
        "SYMBOL", "ENTRY_TS", "EXIT_TS", "ENTRY_PRICE", "EXIT_PRICE", "SHARES",
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


def print_report(result: PortfolioResult, summary: dict, error_rows: list[dict]) -> None:
    m = result.metrics
    print(
        f"initial_capital={result.initial_capital} trades={m['num_trades']} "
        f"skipped={m['num_skipped']} timeline_bars={len(result.timeline)}"
    )
    if error_rows:
        print(f"{len(error_rows)} symbol yuklanmadi/yetarsiz (ERROR).")

    print("\n--- ESKI ketma-ket-kompaund  vs  YANGI portfel simulyatori ---")
    print(
        f"ESKI (barcha signal, cap'siz ketma-ket kompaund, 1.0 boshlanish): "
        f"final={summary['old_final_multiple']}x  max_dd={summary['old_max_dd_pct']}%  "
        f"signallar={summary['old_num_signals']}"
    )
    print(
        f"YANGI (portfel): return={summary['new_return_pct']}%  CAGR={summary['new_cagr_pct']}%  "
        f"max_dd={summary['new_max_dd_pct']}%  Sharpe={summary['new_sharpe']}  "
        f"Sortino={summary['new_sortino']}"
    )
    print(
        f"                 o'rtacha konkurent poz={summary['new_avg_concurrent']} "
        f"(cap={summary['new_max_concurrent']})  o'tkazilgan={summary['new_skipped_by_reason']}"
    )
    for b in result.benchmarks:
        if b.metrics:
            mm = b.metrics
            print(
                f"Benchmark {b.name}: return={mm['return_pct']:.2f}%  CAGR={mm['cagr_pct']:.2f}%  "
                f"maxDD={mm['max_drawdown_pct']:.2f}%  Sharpe={mm['sharpe']:.3f}  Sortino={mm['sortino']:.3f}"
            )
        else:
            print(f"Benchmark {b.name}: XATO - {b.error}")
    print("\n" + summary["explanation"])


def main() -> None:
    args = parse_args()
    result, error_rows = run(args)
    summary = summarize(result)  # ESKI egri chizig'i result.naive_all_signals_curve dan
    print_report(result, summary, error_rows)

    build_trade_rows(result).to_csv(args.output_csv, index=False)
    print(f"\nTo'liq savdolar saqlandi: {Path(args.output_csv).resolve()}")


if __name__ == "__main__":
    main()
