from __future__ import annotations

import logging

import requests

from core.config import AppConfig

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
