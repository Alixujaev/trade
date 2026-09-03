"""V1 breakout+retest strategiyasi backtest — YANGI vs ESKI (smc.signal) vs BUY&HOLD.

FALSAFA (TZ 15): backtest yashil chiqmasa ham OK — maqsad strategiyaning haqiqatan
EDGE bor-yo'qligini o'lchash. "Chiroyli ko'rinishi uchun" hech narsa sozlanmaydi.
Look-ahead YO'Q: slice_date_range() generate_...'dan OLDIN chaqiriladi (struktura,
S/R, EMA, volume MA — hammasi oyna ichida noldan quriladi). Commission/slippage
hisobga olinadi.

ASOSIY SAVOL: breakout+retest + trend filtri + volume + scoring eski SMC signalidan
yaxshiroqmi? Buy&hold'ga yaqinlashadimi?

Ishlatish:
    python scripts/backtest_breakout_retest.py [SYMBOLS...] \
        [--interval 1d] [--provider yfinance] [--start 2020-09-01] [--end 2025-09-01] \
        [--risk-model fixed_pct|atr] [--exit-mode fixed|trailing] \
        [--commission-pct 0.0005] [--slippage-pct 0.0005] \
        [--min-rr 1.5] [--require-trend | --no-require-trend] \
        [--compare-old] [--output-csv breakout_retest_results.csv]

SYMBOLS bo'sh -> get_core_watchlist() (6 curated + 211 HLAL). --start bo'sh ->
bugundan ~5 yil oldin.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_backtest  # noqa: E402
from backtest.types import TradeResult  # noqa: E402
from backtest.window import slice_date_range  # noqa: E402
from config.core_watchlist import get_core_watchlist  # noqa: E402
from config.settings import (  # noqa: E402
    BREAKOUT_COMMISSION_PCT,
    BREAKOUT_SLIPPAGE_PCT,
    MIN_BREAKOUT_RR,
    RISK_PCT_PER_TRADE,
    SWING_LOOKBACK,
)
from data.factory import get_provider  # noqa: E402
from smc.signal import generate_signals  # noqa: E402
from strategy.breakout_retest import generate_breakout_retest_signals  # noqa: E402
from strategy.scoring import apply_scores, filter_by_score  # noqa: E402

# Kam savdoli natijaga ishonmaslik uchun (loyihaning boshqa backtest skriptlaridagi konvensiya)
LOW_SAMPLE_THRESHOLD: int = 10


def five_years_ago_iso() -> str:
    """Bugundan ~5 yil oldingi sana (ISO) — --start berilmagandagi default."""
    today = date.today()
    return (today - timedelta(days=365 * 5)).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V1 breakout+retest backtest (yangi vs eski vs buy&hold)")
    parser.add_argument("symbols", nargs="*", help="Bo'sh bo'lsa get_core_watchlist()")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca")
    parser.add_argument("--start", default=None, help="ISO sana; bo'sh -> ~5 yil oldin")
    parser.add_argument("--end", default=None, help="ISO sana; bo'sh -> oxirigacha")
    parser.add_argument("--risk-model", default="fixed_pct", choices=["fixed_pct", "atr"])
    parser.add_argument("--exit-mode", default="fixed", choices=["fixed", "trailing"])
    parser.add_argument("--commission-pct", type=float, default=BREAKOUT_COMMISSION_PCT)
    parser.add_argument("--slippage-pct", type=float, default=BREAKOUT_SLIPPAGE_PCT)
    parser.add_argument("--min-rr", type=float, default=MIN_BREAKOUT_RR)
    parser.add_argument(
        "--min-score", type=float, default=None,
        help="berilsa: faqat 0-100 balli shu qiymatdan yuqori setup'lar (strategy.scoring)",
    )
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--require-trend", dest="require_trend", action="store_true", default=True)
    parser.add_argument("--no-require-trend", dest="require_trend", action="store_false")
    parser.add_argument("--compare-old", action="store_true", help="eski smc.signal bilan yonma-yon")
    parser.add_argument("--output-csv", default="breakout_retest_results.csv")
    return parser.parse_args()


def _metrics_block(prefix: str, metrics: dict, buy_hold: float) -> dict:
    """run_backtest metrikalaridan prefiksli (NEW_/OLD_) natija ustunlari."""
    pf = metrics["profit_factor"]
    return {
        f"{prefix}_TRADES": metrics["num_trades"],
        f"{prefix}_WIN%": round(metrics["win_rate"] * 100, 2),
        f"{prefix}_AVG_R": round(metrics["avg_r_multiple"], 3),
        f"{prefix}_EXP": round(metrics["expectancy_r"], 3),
        f"{prefix}_PF": pf if pf == float("inf") else round(pf, 3),
        f"{prefix}_RETURN%": round(metrics["total_return_pct"], 3),
        f"{prefix}_MAXDD%": round(metrics["max_drawdown_pct"], 3),
        f"{prefix}_EDGE": round(metrics["total_return_pct"] - buy_hold, 3),
    }


def run_one_symbol(
    symbol: str,
    *,
    interval: str = "1d",
    provider_name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    risk_model: str = "fixed_pct",
    exit_mode: str = "fixed",
    commission_pct: float = BREAKOUT_COMMISSION_PCT,
    slippage_pct: float = BREAKOUT_SLIPPAGE_PCT,
    min_rr: float = MIN_BREAKOUT_RR,
    min_score: float | None = None,
    lookback: int = SWING_LOOKBACK,
    require_trend: bool = True,
    compare_old: bool = False,
    collect_trades: bool = False,
) -> dict:
    """Bitta symbol uchun natija qatori. Xato bo'lsa ERROR to'ldirilgan qator (crash yo'q)."""
    base: dict = {"SYMBOL": symbol}
    try:
        df = get_provider(provider_name).get_ohlcv(symbol, interval)
        df = slice_date_range(df, start, end)

        bt_kw = dict(
            risk_model=risk_model,
            risk_pct=RISK_PCT_PER_TRADE,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            exit_mode=exit_mode,
        )

        new_signals = generate_breakout_retest_signals(
            df, lookback=lookback, min_rr=min_rr, require_trend=require_trend
        )
        if min_score is not None:
            new_signals = filter_by_score(
                apply_scores(df, new_signals, lookback=lookback, min_rr=min_rr), min_score
            )
        res_new = run_backtest(df, new_signals, **bt_kw)
        buy_hold = round(res_new.metrics["buy_hold_return_pct"], 3)

        row: dict = {
            **base,
            "BARS": len(df),
            **_metrics_block("NEW", res_new.metrics, buy_hold),
            "BUY&HOLD%": buy_hold,
        }

        if compare_old:
            old_signals = generate_signals(df, lookback=lookback)
            res_old = run_backtest(df, old_signals, **bt_kw)
            row.update(_metrics_block("OLD", res_old.metrics, buy_hold))

        row["ERROR"] = None
        if collect_trades:
            row["_new_trades"] = res_new.trades
        return row
    except Exception as exc:  # noqa: BLE001 — har qanday xatoni qatorga aylantiramiz
        return {**base, "BARS": None, "ERROR": str(exc)}


def build_results(symbols: list[str], **kw) -> pd.DataFrame:
    """Barcha symbol'lar bo'ylab yurib natija DataFrame'ini qaytaradi (bitta yiqilsa davom etadi)."""
    rows = [run_one_symbol(symbol, **kw) for symbol in symbols]
    display_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    return pd.DataFrame(display_rows)


def summarize(results: pd.DataFrame) -> dict:
    """Xatosiz qatorlar bo'yicha YANGI vs ESKI vs BUY&HOLD agregati + verdikt."""
    valid = results[results["ERROR"].isna()] if "ERROR" in results.columns else results
    if valid.empty:
        return {"symbols": 0, "verdict": "Xatosiz natija yo'q — xulosa chiqarib bo'lmaydi."}

    def mean(col: str) -> float | None:
        return round(float(valid[col].mean()), 3) if col in valid.columns else None

    out: dict = {
        "symbols": int(len(valid)),
        "new_trades_total": int(valid["NEW_TRADES"].sum()) if "NEW_TRADES" in valid else 0,
        "new_return_pct_mean": mean("NEW_RETURN%"),
        "new_expectancy_mean": mean("NEW_EXP"),
        "new_win_pct_mean": mean("NEW_WIN%"),
        "new_maxdd_pct_mean": mean("NEW_MAXDD%"),
        "new_edge_mean": mean("NEW_EDGE"),
        "buy_hold_pct_mean": mean("BUY&HOLD%"),
    }
    if "OLD_RETURN%" in valid.columns:
        out.update(
            {
                "old_trades_total": int(valid["OLD_TRADES"].sum()),
                "old_return_pct_mean": mean("OLD_RETURN%"),
                "old_expectancy_mean": mean("OLD_EXP"),
                "old_edge_mean": mean("OLD_EDGE"),
            }
        )

    new_edge = out["new_edge_mean"] or 0.0
    beats_bh = "HA" if new_edge > 0 else "YO'Q"
    lines = [f"Breakout+retest buy&hold'ni yengdimi (o'rtacha EDGE > 0)? {beats_bh} (EDGE={new_edge})"]
    if "old_edge_mean" in out:
        old_edge = out["old_edge_mean"] or 0.0
        better = "HA" if new_edge > old_edge else "YO'Q"
        lines.append(
            f"Eski SMC signalidan ustunmi (EDGE_new > EDGE_old)? {better} "
            f"(new={new_edge} vs old={old_edge})"
        )
    out["verdict"] = " | ".join(lines)
    return out


def portfolio_equity_curve(
    trades: list[TradeResult], *, risk_pct: float = RISK_PCT_PER_TRADE
) -> list[float]:
    """Barcha savdolarni entry_ts bo'yicha saralab, bitta kapitalga qat'iy fraksion
    risk bilan qayta simulyatsiya (taxminiy, lookahead'siz — faqat yopilgan r_multiple).

    1.0 dan boshlanadi; har savdo: equity *= (1 + risk_pct * r_multiple).
    """
    equity = 1.0
    curve = [equity]
    for trade in sorted(trades, key=lambda t: t.entry_ts):
        equity *= 1.0 + risk_pct * trade.r_multiple
        curve.append(equity)
    return curve


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]
    start = args.start or five_years_ago_iso()

    kw = dict(
        interval=args.interval,
        provider_name=args.provider,
        start=start,
        end=args.end,
        risk_model=args.risk_model,
        exit_mode=args.exit_mode,
        commission_pct=args.commission_pct,
        slippage_pct=args.slippage_pct,
        min_rr=args.min_rr,
        min_score=args.min_score,
        lookback=args.lookback,
        require_trend=args.require_trend,
        compare_old=args.compare_old,
    )

    rows = [run_one_symbol(symbol, collect_trades=True, **kw) for symbol in symbols]
    all_new_trades: list[TradeResult] = []
    for row in rows:
        all_new_trades.extend(row.pop("_new_trades", []))

    results = pd.DataFrame(rows)

    print(
        f"interval={args.interval} start={start} end={args.end or 'oxirigacha'} "
        f"risk_model={args.risk_model} exit_mode={args.exit_mode} "
        f"commission={args.commission_pct} slippage={args.slippage_pct} "
        f"require_trend={args.require_trend}"
    )
    print(results.to_string(index=False))

    n_errors = results["ERROR"].notna().sum() if "ERROR" in results.columns else 0
    if n_errors:
        print(f"\n{n_errors} symbol xato berdi (ERROR ustuniga qarang).")

    print("\n--- XULOSA (breakout+retest vs eski SMC vs buy&hold) ---")
    summary = summarize(results)
    for key, value in summary.items():
        if key != "verdict":
            print(f"{key}: {value}")
    print("\n" + summary.get("verdict", ""))

    curve = portfolio_equity_curve(all_new_trades)
    if len(curve) > 1:
        peak = max(curve)
        trough_after_peak = min(curve[curve.index(peak):]) if peak in curve else min(curve)
        print(
            f"\nPortfolio equity curve (1.0 boshlanish, {len(all_new_trades)} savdo): "
            f"final={curve[-1]:.4f} peak={peak:.4f} min={min(curve):.4f} "
            f"trough_after_peak={trough_after_peak:.4f}"
        )

    results.to_csv(args.output_csv, index=False)
    print(f"\nTo'liq natija saqlandi: {Path(args.output_csv).resolve()}")


if __name__ == "__main__":
    main()
