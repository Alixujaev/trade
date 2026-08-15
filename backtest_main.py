from __future__ import annotations

import logging

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


def main() -> None:
    cfg = AppConfig.from_env()
    print(format_metrics_table(run_all_backtests(cfg)))


if __name__ == "__main__":
    main()
