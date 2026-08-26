"""Bot ilovasini yig'ish va ishga tushirish.

Ishga tushirish: smc-scanner/ papkasidan `python -m telegram_bot.bot`
(TELEGRAM_BOT_TOKEN va TELEGRAM_ALLOWED_USER_ID .env faylda bo'lishi shart)."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from telegram_bot import handlers

_TEXT_NOT_COMMAND = filters.TEXT & ~filters.COMMAND


def build_application(token: str) -> Application:
    """Barcha handler'lar ro'yxatga olingan Application obyektini yaratadi (run_polling chaqirmaydi)."""
    application = ApplicationBuilder().token(token).build()

    add_conversation = ConversationHandler(
        entry_points=[CommandHandler("add", handlers.add_start)],
        states={
            handlers.ADD_SYMBOL: [MessageHandler(_TEXT_NOT_COMMAND, handlers.add_symbol)],
            handlers.ADD_ENTRY: [MessageHandler(_TEXT_NOT_COMMAND, handlers.add_entry_price)],
            handlers.ADD_STOP: [MessageHandler(_TEXT_NOT_COMMAND, handlers.add_stop_price)],
            handlers.ADD_TARGET: [MessageHandler(_TEXT_NOT_COMMAND, handlers.add_target_price)],
            handlers.ADD_REASON: [MessageHandler(_TEXT_NOT_COMMAND, handlers.add_reason)],
        },
        fallbacks=[CommandHandler("cancel", handlers.add_cancel)],
    )

    close_conversation = ConversationHandler(
        entry_points=[CommandHandler("close", handlers.close_start)],
        states={
            handlers.CLOSE_SELECT: [CallbackQueryHandler(handlers.close_select)],
            handlers.CLOSE_PRICE: [MessageHandler(_TEXT_NOT_COMMAND, handlers.close_price)],
            handlers.CLOSE_REASON: [MessageHandler(_TEXT_NOT_COMMAND, handlers.close_reason)],
        },
        fallbacks=[CommandHandler("cancel", handlers.add_cancel)],
    )

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("scan", handlers.scan))
    application.add_handler(CommandHandler("status", handlers.status))
    application.add_handler(CommandHandler("journal", handlers.journal_command))
    application.add_handler(CommandHandler("stats", handlers.stats_command))
    application.add_handler(CommandHandler("watchlist", handlers.watchlist))
    application.add_handler(CommandHandler("capital", handlers.capital_command))
    application.add_handler(add_conversation)
    application.add_handler(close_conversation)

    return application


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN .env faylda topilmadi.")
    application = build_application(token)
    application.run_polling()


if __name__ == "__main__":
    main()
