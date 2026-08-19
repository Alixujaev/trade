"""Daily price-action scanner entry point.

Flags mechanical, unambiguous BULLISH price-action setups (liquidity sweeps,
bullish engulfing candles, bullish pin bars — see signals/detectors.py) on the
sharia whitelist. An alert means "a setup formed, go look" — it is NOT a trade
signal and makes no claim of predictive edge. All entry/exit/sizing decisions
remain fully discretionary (Smart Money Concepts price-action reading is not
mechanizable and is intentionally not automated here). This module places no
orders, paper or live, and never will (INV-D) — it only sends a Telegram alert
and appends a row to journal.csv for the user to later fill in with their
decision and outcome.

Swing needs no always-on process. Intended to run once per trading day after
the US close via cron, exactly like live_main.py, e.g. (Asia/Tashkent):
    30 2 * * 1-5 cd /path/to/trade && /usr/bin/python scan_main.py
"""
from __future__ import annotations

import logging

from alerts.telegram import TelegramAlertSink
from core.config import AppConfig
from data.yfinance_source import YFinanceSource
from engine.scanner import Scanner
from screening.sharia import ShariaFilter
from signals.detectors import Setup

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

WHITELIST_PATH = "whitelist.txt"


def build_scanner(cfg: AppConfig) -> Scanner:
    source = YFinanceSource()
    alert = TelegramAlertSink(cfg.telegram_bot_token, cfg.telegram_chat_id)
    return Scanner(source, alert, cfg)


def format_setups(setups: list[Setup]) -> str:
    """One-line Telegram-control-bot summary, matching live_main.format_signals'
    style. The setups themselves were already alerted individually (with their
    own Chart/decision buttons) by Scanner.run_once -- this is just the /scan
    command's ack that a run happened.
    """
    if not setups:
        return "Skanerlandi, yangi setup yo'q."
    parts = ", ".join(setup.symbol for setup in setups)
    return f"Skanerlandi: {len(setups)} ta setup topildi ({parts})."


def main() -> None:
    cfg = AppConfig.from_env()
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    scanner = build_scanner(cfg)
    setups = scanner.run_once(symbols)

    if not setups:
        print("Scanned, no setups.")
        return
    for setup in setups:
        print(
            f"{setup.symbol}: triggers={setup.triggers} "
            f"context={setup.context} confluence={setup.confluence}"
        )


if __name__ == "__main__":
    main()
