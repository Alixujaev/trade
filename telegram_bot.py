from __future__ import annotations

import logging
import time

import requests

from backtest_main import WHITELIST_PATH, format_metrics_table, run_all_backtests
from core.config import AppConfig
from live_main import build_live_engine, format_signals
from screening.sharia import ShariaFilter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/{method}"

COMMANDS = [
    ("run", "Bugungi signalni tekshirish"),
    ("backtest", "Whitelist bo'yicha backtest ishga tushirish"),
    ("status", "Joriy pozitsiyalarni ko'rish"),
    ("help", "Yordam"),
]


def _is_authorized(update: dict, cfg: AppConfig) -> bool:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    return chat_id is not None and str(chat_id) == str(cfg.telegram_chat_id)


def _command_text(update: dict) -> str | None:
    message = update.get("message") or {}
    text = message.get("text")
    if not text:
        return None
    return text.split()[0].split("@")[0]


def handle_help() -> str:
    return "\n".join(f"/{c} — {d}" for c, d in COMMANDS)


def _api_url(cfg: AppConfig, method: str) -> str:
    return API_URL.format(token=cfg.telegram_bot_token, method=method)


def register_commands(cfg: AppConfig) -> None:
    try:
        response = requests.post(
            _api_url(cfg, "setMyCommands"),
            json={"commands": [{"command": c, "description": d} for c, d in COMMANDS]},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logger.warning("failed to register telegram command menu", exc_info=True)


def fetch_updates(cfg: AppConfig, offset: int, timeout: int = 30) -> list[dict]:
    response = requests.get(
        _api_url(cfg, "getUpdates"),
        params={"offset": offset, "timeout": timeout},
        timeout=timeout + 10,
    )
    response.raise_for_status()
    return response.json().get("result", [])


def next_offset(updates: list[dict], current_offset: int) -> int:
    if not updates:
        return current_offset
    return max(u["update_id"] for u in updates) + 1


def send_reply(cfg: AppConfig, chat_id: int | str, text: str) -> None:
    try:
        response = requests.post(
            _api_url(cfg, "sendMessage"),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logger.warning("failed to send telegram reply", exc_info=True)


def _load_symbols() -> list[str]:
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    return whitelist.filter(sorted(whitelist.whitelist))


def handle_run(cfg: AppConfig) -> str:
    engine = build_live_engine(cfg)
    signals = engine.run_once(_load_symbols())
    return format_signals(signals)


def handle_backtest(cfg: AppConfig) -> str:
    return format_metrics_table(run_all_backtests(cfg))


def handle_status(cfg: AppConfig) -> str:
    symbols = _load_symbols()
    if not symbols:
        return "Whitelist bo'sh."
    engine = build_live_engine(cfg)
    lines = [
        f"{symbol}: {'long' if engine.state.get(symbol, 0) == 1 else 'flat'}"
        for symbol in symbols
    ]
    return "\n".join(lines)


_HANDLERS = {
    "/run": handle_run,
    "/backtest": handle_backtest,
    "/status": handle_status,
}


def dispatch(update: dict, cfg: AppConfig) -> None:
    if not _is_authorized(update, cfg):
        return

    command = _command_text(update)
    if command is None:
        return

    chat_id = update["message"]["chat"]["id"]

    if command == "/help":
        send_reply(cfg, chat_id, handle_help())
        return

    handler = _HANDLERS.get(command)
    if handler is None:
        send_reply(cfg, chat_id, "Noma'lum buyruq. /help")
        return

    try:
        reply = handler(cfg)
    except Exception as exc:
        logger.exception("command %s failed", command)
        send_reply(cfg, chat_id, f"Xatolik yuz berdi: {exc}")
        return

    send_reply(cfg, chat_id, reply)


def run_forever(cfg: AppConfig) -> None:
    register_commands(cfg)
    offset = 0
    while True:
        try:
            updates = fetch_updates(cfg, offset)
        except requests.exceptions.RequestException:
            logger.warning("failed to fetch telegram updates; retrying", exc_info=True)
            time.sleep(5)
            continue

        for update in updates:
            dispatch(update, cfg)
        offset = next_offset(updates, offset)


if __name__ == "__main__":
    run_forever(AppConfig.from_env())
