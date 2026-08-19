from __future__ import annotations

import logging
import time

import requests

from backtest_main import WHITELIST_PATH, format_metrics_for_telegram, run_all_backtests
from core.config import AppConfig
from live_main import build_live_engine, format_signals
from scan_main import build_scanner, format_setups
from screening.sharia import ShariaFilter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/{method}"

COMMANDS = [
    ("run", "Bugungi signalni tekshirish"),
    ("backtest", "Whitelist bo'yicha backtest ishga tushirish"),
    ("scan", "Price-action setuplarni skanerlash"),
    ("status", "Joriy pozitsiyalarni ko'rish"),
    ("help", "Yordam"),
]

# Persistent reply keyboard shown under the chat input, mirroring COMMANDS
# one-to-one -- tapping a button sends its label as plain text, which
# _command_text maps back to the matching "/command" below.
MAIN_KEYBOARD = {
    "keyboard": [
        ["▶️ Run", "\U0001f4ca Backtest"],
        ["\U0001f50d Scan", "\U0001f4cc Status"],
        ["❓ Yordam"],
    ],
    "resize_keyboard": True,
}

_BUTTON_LABELS: dict[str, str] = {
    "▶️ Run": "/run",
    "\U0001f4ca Backtest": "/backtest",
    "\U0001f50d Scan": "/scan",
    "\U0001f4cc Status": "/status",
    "❓ Yordam": "/help",
}


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
    button_command = _BUTTON_LABELS.get(text.strip())
    if button_command is not None:
        return button_command
    parts = text.split()
    if not parts:
        return None
    return parts[0].split("@")[0]


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


MAX_MESSAGE_LENGTH = 3900


def _chunk_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into pieces <= limit chars, preferring to split on newlines."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # a single line longer than the limit must be hard-split
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks


def send_reply(cfg: AppConfig, chat_id: int | str, text: str) -> None:
    for chunk in _chunk_text(text):
        try:
            response = requests.post(
                _api_url(cfg, "sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "reply_markup": MAIN_KEYBOARD,
                },
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
    return format_metrics_for_telegram(run_all_backtests(cfg))


def handle_scan(cfg: AppConfig) -> str:
    scanner = build_scanner(cfg)
    setups = scanner.run_once(_load_symbols())
    return format_setups(setups)


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
    "/scan": handle_scan,
    "/status": handle_status,
}

# Commands that can take a long time (network calls per symbol) get an
# immediate acknowledgment so the user isn't left wondering / resending.
_SLOW_COMMANDS = {"/run", "/backtest", "/scan"}


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

    if command in _SLOW_COMMANDS:
        send_reply(cfg, chat_id, "Ishlayapti...")

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
    try:
        # Throwaway fetch to discover any already-pending updates without
        # processing them, so a restart doesn't replay the whole backlog
        # (up to 24h of unconfirmed updates, e.g. several /backtest runs).
        pending = fetch_updates(cfg, offset=-1, timeout=0)
        offset = next_offset(pending, offset)
    except requests.exceptions.RequestException:
        logger.warning("failed to drain pending telegram updates on startup", exc_info=True)

    while True:
        try:
            updates = fetch_updates(cfg, offset)
        except requests.exceptions.RequestException:
            logger.warning("failed to fetch telegram updates; retrying", exc_info=True)
            time.sleep(5)
            continue

        for update in updates:
            try:
                dispatch(update, cfg)
            except Exception:
                logger.exception("failed dispatching update")
        offset = next_offset(updates, offset)


if __name__ == "__main__":
    run_forever(AppConfig.from_env())
