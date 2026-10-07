"""Bot faqat bitta foydalanuvchiga (TELEGRAM_ALLOWED_USER_ID) javob berishi uchun
markazlashgan decorator — har handler o'zi tekshiruv takrorlamaydi."""

from __future__ import annotations

import functools
import os
from collections.abc import Awaitable, Callable

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes

RUXSAT_YOQ_XABARI = "⛔ Ruxsat yo'q."

HandlerFunc = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


def _allowed_user_id() -> int | None:
    load_dotenv()
    raw = os.getenv("TELEGRAM_ALLOWED_USER_ID")
    return int(raw) if raw else None


def require_allowed_user(handler: HandlerFunc) -> HandlerFunc:
    """Chaqiruvchi Telegram user_id'sini TELEGRAM_ALLOWED_USER_ID bilan solishtiradi;
    mos kelmasa "Ruxsat yo'q" javobi qaytadi va asl handler chaqirilmaydi."""

    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        allowed_id = _allowed_user_id()
        user = update.effective_user
        if allowed_id is None or user is None or user.id != allowed_id:
            if update.effective_message is not None:
                await update.effective_message.reply_text(RUXSAT_YOQ_XABARI)
            return None
        return await handler(update, context)

    return wrapper
