from __future__ import annotations

import logging

from alerts.telegram import TelegramAlertSink
from backtest_main import WHITELIST_PATH, build_strategy
from core.config import AppConfig
from data.yfinance_source import YFinanceSource
from engine.live import LiveEngine
from screening.sharia import ShariaFilter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    cfg = AppConfig.from_env()
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    strategy = build_strategy(cfg)
    source = YFinanceSource()
    alert = TelegramAlertSink(cfg.telegram_bot_token, cfg.telegram_chat_id)

    engine = LiveEngine(source, strategy, alert, cfg)
    signals = engine.run_once(symbols)

    for signal in signals:
        logger.info("signal: %s", signal)


if __name__ == "__main__":
    main()
