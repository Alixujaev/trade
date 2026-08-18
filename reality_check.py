"""One-off reality check: does the existing strategy beat buy-and-hold, net of
costs, in-sample AND out-of-sample, on real historical data?

Not part of the production pipeline (backtest_main.py / live_main.py /
telegram_bot.py) and not imported by them. Reuses the existing, unmodified
engine (run_backtest, compute_metrics) and the same build_strategy() used by
backtest/live, so the strategy under test is provably the one that would run
live (INV-2/parity). No indicator or strategy math is reimplemented here.

Benchmark scope note (re: INV-5): SPY is fetched and buy-and-hold-backtested
purely as a passive reference point for this offline report. It is not part
of the sharia whitelist, is never scanned by the trading strategy, and never
produces a Signal/alert — it does not enter the live/backtest signal pipeline
at all. This is a deliberate, narrowly-scoped exception confined to this
script, per explicit instruction.

Per SPEC.md §0 ("ask a focused question rather than guessing" / "flag instead
of silently complying"): this script performs no parameter tuning and adds no
walk-forward/optimization tooling — that is explicitly Phase 2, not this.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from backtest_main import WHITELIST_PATH, build_strategy
from core.config import AppConfig, BacktestConfig
from data.yfinance_source import YFinanceSource
from engine.backtest import compute_metrics, run_backtest
from screening.sharia import ShariaFilter
from signals.base import Strategy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ~10 trading years. yfinance's period=Nd returns the N most recent daily
# bars available; younger symbols simply come back shorter (graceful
# fallback per the task, not an error).
LOOKBACK_DAYS = 2520
IS_FRACTION = 0.7
BENCHMARK_SYMBOL = "SPY"
MIN_BARS = 30  # below this, IS/OOS split metrics are not meaningful

REPORT_PATH = "REALITY_CHECK_REPORT.md"

_METRIC_KEYS = [
    "total_return_pct",
    "cagr_pct",
    "sharpe",
    "max_drawdown_pct",
    "num_trades",
    "expectancy_per_trade",
]


class BuyAndHoldStrategy(Strategy):
    """Benchmark only. Always long from the first tradable bar. Not used by
    backtest_main/live_main; INV-2 (parity) governs the production signal
    path, which this does not touch."""

    name = "BuyAndHold"

    def target_position(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=df.index)


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cut = int(len(df) * IS_FRACTION)
    return df.iloc[:cut], df.iloc[cut:]


def _evaluate(df: pd.DataFrame, strategy: Strategy, cfg: BacktestConfig, symbol: str) -> dict | None:
    if len(df) < MIN_BARS:
        return None
    result = run_backtest(df, strategy, cfg, symbol)
    return compute_metrics(result)


def _fetch(source: YFinanceSource, symbol: str, interval: str) -> pd.DataFrame | None:
    try:
        return source.get_history(symbol, LOOKBACK_DAYS, interval)
    except Exception:
        logger.exception("fetch failed for %s; skipping", symbol)
        return None


def run_reality_check(cfg: AppConfig) -> list[dict]:
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    strategy = build_strategy(cfg)
    benchmark_strategy = BuyAndHoldStrategy()
    source = YFinanceSource()

    targets = [(s, False) for s in symbols] + [(BENCHMARK_SYMBOL, True)]

    rows: list[dict] = []
    for symbol, benchmark_only in targets:
        df = _fetch(source, symbol, cfg.interval)
        if df is None:
            rows.append({"symbol": symbol, "benchmark_only": benchmark_only, "error": "fetch failed"})
            continue
        if len(df) < MIN_BARS:
            rows.append({"symbol": symbol, "benchmark_only": benchmark_only, "error": f"only {len(df)} bars"})
            continue

        is_df, oos_df = _split(df)

        row: dict = {
            "symbol": symbol,
            "benchmark_only": benchmark_only,
            "bars": len(df),
            "start": str(df.index[0].date()),
            "end": str(df.index[-1].date()),
            "is_bars": len(is_df),
            "oos_bars": len(oos_df),
        }

        if not benchmark_only:
            row["strategy_is"] = _evaluate(is_df, strategy, cfg.backtest, symbol)
            row["strategy_oos"] = _evaluate(oos_df, strategy, cfg.backtest, symbol)

        row["bh_is"] = _evaluate(is_df, benchmark_strategy, cfg.backtest, symbol)
        row["bh_oos"] = _evaluate(oos_df, benchmark_strategy, cfg.backtest, symbol)

        rows.append(row)

    return rows


def _fmt(metrics: dict | None, key: str) -> str:
    if metrics is None:
        return "n/a"
    v = metrics[key]
    return str(v) if key == "num_trades" else f"{v:.2f}"


def _mean(rows: list[dict], path: str, key: str) -> float | None:
    vals = []
    for r in rows:
        m = r
        for part in path.split("."):
            m = m.get(part) if isinstance(m, dict) else None
            if m is None:
                break
        if m is not None:
            vals.append(m[key])
    return sum(vals) / len(vals) if vals else None


def build_report(rows: list[dict], cfg: AppConfig) -> str:
    symbol_rows = [r for r in rows if not r.get("benchmark_only")]
    spy_rows = [r for r in rows if r.get("benchmark_only")]
    ok_rows = [r for r in symbol_rows if "error" not in r]
    failed_rows = [r for r in rows if "error" in r]

    lines: list[str] = []
    lines.append("# Reality Check — Strategy vs Buy-and-Hold, Real Data, IS/OOS")
    lines.append("")
    lines.append(f"Generated {date.today().isoformat()}. Strategy under test: "
                  f"`{build_strategy(cfg).name}` (the exact strategy backtest_main/live_main use — INV-2 parity).")
    lines.append("")
    lines.append(f"Data: yfinance daily bars, up to {LOOKBACK_DAYS} most recent trading days per symbol "
                  f"(~10y where available; shorter for younger listings — graceful fallback, not an error). "
                  f"Split: first {int(IS_FRACTION*100)}% = in-sample (IS), last {int((1-IS_FRACTION)*100)}% = "
                  "out-of-sample (OOS). No parameter tuning performed anywhere in this report.")
    lines.append("")
    lines.append("Costs: identical cost model in every backtest here (strategy and buy-and-hold alike) — "
                  f"commission {cfg.backtest.commission_bps} bps, slippage {cfg.backtest.slippage_bps} bps per "
                  "side, applied by the same unmodified `engine/backtest.py`. Buy-and-hold never exits, so it "
                  "pays one entry commission only, per instruction.")
    lines.append("")

    if failed_rows:
        lines.append("## Fetch failures / insufficient data")
        lines.append("")
        for r in failed_rows:
            lines.append(f"- **{r['symbol']}**: {r['error']}")
        lines.append("")

    lines.append("## Per-symbol results")
    lines.append("")
    header = ("| symbol | window | bars(IS/OOS) | split | return% | CAGR% | Sharpe | maxDD% | trades | expectancy |")
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    for r in ok_rows:
        lines.append("")
        lines.append(f"### {r['symbol']}  ({r['start']} → {r['end']}, {r['bars']} bars)")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        for split_name, strat_key, bh_key, bars in (
            ("IS", "strategy_is", "bh_is", r["is_bars"]),
            ("OOS", "strategy_oos", "bh_oos", r["oos_bars"]),
        ):
            s = r.get(strat_key)
            b = r.get(bh_key)
            lines.append(
                f"| {r['symbol']} | strategy | {bars} | {split_name} | "
                f"{_fmt(s,'total_return_pct')} | {_fmt(s,'cagr_pct')} | {_fmt(s,'sharpe')} | "
                f"{_fmt(s,'max_drawdown_pct')} | {_fmt(s,'num_trades')} | {_fmt(s,'expectancy_per_trade')} |"
            )
            lines.append(
                f"| {r['symbol']} | buy&hold | {bars} | {split_name} | "
                f"{_fmt(b,'total_return_pct')} | {_fmt(b,'cagr_pct')} | {_fmt(b,'sharpe')} | "
                f"{_fmt(b,'max_drawdown_pct')} | {_fmt(b,'num_trades')} | {_fmt(b,'expectancy_per_trade')} |"
            )

    if spy_rows and "error" not in spy_rows[0]:
        r = spy_rows[0]
        lines.append("")
        lines.append(f"### SPY (benchmark only, {r['start']} → {r['end']}, {r['bars']} bars)")
        lines.append("")
        lines.append("| window | split | return% | CAGR% | Sharpe | maxDD% |")
        lines.append("|---|---|---|---|---|---|")
        for split_name, bh_key, bars in (("IS", "bh_is", r["is_bars"]), ("OOS", "bh_oos", r["oos_bars"])):
            b = r.get(bh_key)
            lines.append(
                f"| buy&hold SPY | {split_name} | {_fmt(b,'total_return_pct')} | {_fmt(b,'cagr_pct')} | "
                f"{_fmt(b,'sharpe')} | {_fmt(b,'max_drawdown_pct')} |"
            )

    lines.append("")
    lines.append("## Aggregate (simple mean across symbols with data)")
    lines.append("")
    lines.append("| split | series | mean return% | mean CAGR% | mean Sharpe | mean maxDD% | mean trades | mean expectancy |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for split_name, strat_key, bh_key in (("IS", "strategy_is", "bh_is"), ("OOS", "strategy_oos", "bh_oos")):
        for series_name, key in (("strategy", strat_key), ("buy&hold", bh_key)):
            vals = {k: _mean(ok_rows, key, k) for k in _METRIC_KEYS}
            fmt = lambda k: (f"{vals[k]:.2f}" if vals[k] is not None else "n/a")
            lines.append(
                f"| {split_name} | {series_name} | {fmt('total_return_pct')} | {fmt('cagr_pct')} | "
                f"{fmt('sharpe')} | {fmt('max_drawdown_pct')} | {fmt('num_trades')} | {fmt('expectancy_per_trade')} |"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    cfg = AppConfig.from_env()
    rows = run_reality_check(cfg)
    report = build_report(rows, cfg)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nWritten to {REPORT_PATH}")


if __name__ == "__main__":
    main()
