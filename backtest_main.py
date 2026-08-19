from __future__ import annotations

import logging
import math

from core.config import AppConfig
from data.yfinance_source import YFinanceSource
from engine.backtest import compute_metrics, run_backtest
from screening.sharia import ShariaFilter
from signals.base import Strategy
from signals.strategies import CombinedStrategy, EmaCrossStrategy, MacdStrategy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

WHITELIST_PATH = "whitelist.txt"

_METRIC_COLUMNS = [
    "total_return_pct",
    "cagr_pct",
    "sharpe",
    "max_drawdown_pct",
    "num_trades",
    "win_rate_pct",
    "expectancy_per_trade",
]


def build_strategy(cfg: AppConfig) -> Strategy:
    """The single strategy definition shared by backtest and live (INV-2/parity)."""
    return CombinedStrategy(
        [EmaCrossStrategy(cfg.indicators), MacdStrategy(cfg.indicators)],
        mode="all",
    )


def run_all_backtests(cfg: AppConfig) -> list[tuple[str, dict]]:
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    strategy = build_strategy(cfg)
    source = YFinanceSource()

    rows: list[tuple[str, dict]] = []
    for symbol in symbols:
        try:
            df = source.get_history(symbol, cfg.lookback_days, cfg.interval)
            # yfinance occasionally returns the most recent daily bar with
            # empty OHLC (not yet fully settled/back-filled); left in, its
            # NaN close poisons the last equity value and so total_return_pct.
            # LiveEngine/Scanner already guard against this (drop_forming_bar);
            # backtests need the same guard.
            df = df.iloc[:-1]
            result = run_backtest(df, strategy, cfg.backtest, symbol)
            rows.append((symbol, compute_metrics(result)))
        except Exception:
            logger.exception("backtest failed for %s", symbol)

    return rows


def format_metrics_table(rows: list[tuple[str, dict]]) -> str:
    if not rows:
        return "No results."

    lines = ["symbol\t" + "\t".join(_METRIC_COLUMNS)]
    for symbol, metrics in rows:
        values = [symbol]
        for col in _METRIC_COLUMNS:
            v = metrics[col]
            values.append(str(v) if col == "num_trades" else f"{v:.2f}")
        lines.append("\t".join(values))
    return "\n".join(lines)


def format_metrics_for_telegram(rows: list[tuple[str, dict]]) -> str:
    """Telegram-friendly backtest summary: one line per symbol, sorted by the
    headline metric (expectancy_per_trade, per README's "Metrics that matter")
    so the most/least promising results are immediately visible on a narrow
    screen, instead of format_metrics_table's wide tab-table which wraps
    unreadably on mobile. The CLI (main(), below) keeps using
    format_metrics_table -- a tab-separated table is fine, even preferable,
    in a terminal.
    """
    if not rows:
        return "Natija yo'q."

    def _sort_key(row: tuple[str, dict]) -> float:
        expectancy = row[1]["expectancy_per_trade"]
        return expectancy if not math.isnan(expectancy) else float("-inf")

    ordered = sorted(rows, key=_sort_key, reverse=True)

    lines = [f"\U0001f4ca <b>Backtest natijalari</b> ({len(ordered)} ta belgi)", ""]
    for symbol, m in ordered:
        expectancy = m["expectancy_per_trade"]
        if math.isnan(expectancy):
            lines.append(f"⚪ <b>{symbol}</b> — ma'lumot yetarli emas")
            continue

        emoji = "\U0001f7e2" if expectancy > 0 else ("\U0001f534" if expectancy < 0 else "⚪")
        total_return = m["total_return_pct"]
        return_text = "N/A" if math.isnan(total_return) else f"{total_return:+.2f}%"
        lines.append(
            f"{emoji} <b>{symbol}</b> — {expectancy:+.2f}$/savdo, {return_text}, "
            f"sharpe {m['sharpe']:.2f}, {m['num_trades']} savdo (win {m['win_rate_pct']:.1f}%)"
        )

    lines.append("")
    lines.append("<i>Bu tarixiy backtest — kelajakdagi natija kafolati emas.</i>")
    return "\n".join(lines)


def main() -> None:
    cfg = AppConfig.from_env()
    print(format_metrics_table(run_all_backtests(cfg)))


if __name__ == "__main__":
    main()
