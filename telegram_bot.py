from __future__ import annotations

from core.config import AppConfig

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
