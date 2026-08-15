from __future__ import annotations

import logging

from alerts.telegram import TelegramAlertSink
from backtest_main import WHITELIST_PATH, build_strategy
from core.config import AppConfig
from core.models import Signal
from data.yfinance_source import YFinanceSource
from engine.live import LiveEngine
from screening.sharia import ShariaFilter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_live_engine(cfg: AppConfig) -> LiveEngine:
    source = YFinanceSource()
    alert = TelegramAlertSink(cfg.telegram_bot_token, cfg.telegram_chat_id)
    return LiveEngine(source, build_strategy(cfg), alert, cfg)


def format_signals(signals: list[Signal]) -> str:
    if not signals:
        return "Tekshirildi, o'zgarish yo'q."
    parts = ", ".join(f"{s.symbol} {s.action.value}" for s in signals)
    return f"Tekshirildi: {len(signals)} ta signal ({parts})."


def main() -> None:
    cfg = AppConfig.from_env()
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    engine = build_live_engine(cfg)
    signals = engine.run_once(symbols)
    print(format_signals(signals))


if __name__ == "__main__":
    main()
