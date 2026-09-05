"""Bot ilovasini yig'ish va ishga tushirish.

Ishga tushirish: smc-scanner/ papkasidan `python -m telegram_bot.bot`
(TELEGRAM_BOT_TOKEN va TELEGRAM_ALLOWED_USER_ID .env faylda bo'lishi shart)."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from telegram_bot import handlers, keyboards

logger = logging.getLogger(__name__)

_TEXT_NOT_COMMAND = filters.TEXT & ~filters.COMMAND

BOT_COMMANDS: list[BotCommand] = [
    BotCommand("scan", "Watchlist yoki ticker(lar)ni skanerlash (past R:R yashirilgan)"),
    BotCommand("scan_all", "Barcha setup'larni ko'rsatish (past R:R bilan)"),
    BotCommand("signals", "Setup skaneri (non-directive setup intelligence)"),
    BotCommand("swing", "Swing rejimida setup skaneri"),
    BotCommand("status", "Ochiq savdolar + risk holati"),
    BotCommand("add", "Yangi savdo qo'shish"),
    BotCommand("close", "Ochiq savdoni yopish"),
    BotCommand("journal", "Oxirgi savdolar"),
    BotCommand("stats", "Statistika"),
    BotCommand("stats_bench", "Statistika + buy&hold benchmark (sekinroq)"),
    BotCommand("watchlist", "Taktik watchlist"),
    BotCommand("watchadd", "Watchlistga yangi aksiya/ETF qo'shish"),
    BotCommand("watchremove", "Watchlistdan belgi o'chirish"),
    BotCommand("menu", "Pastki menyuni qayta ko'rsatish"),
    BotCommand("help", "Yordam"),
]


async def _post_init(application: Application) -> None:
    """Telegram native "/" buyruqlar menyusini o'rnatadi — best-effort, tarmoq
    xatosi bo'lsa botni to'xtatmaydi (root loyihadagi register_commands'ga mos)."""
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception:
        logger.warning("set_my_commands muvaffaqiyatsiz bo'ldi", exc_info=True)


def build_application(token: str) -> Application:
    """Barcha handler'lar ro'yxatga olingan Application obyektini yaratadi (run_polling chaqirmaydi)."""
    application = ApplicationBuilder().token(token).post_init(_post_init).build()

    cancel_button = CallbackQueryHandler(
        handlers.cancel_conversation_callback, pattern=f"^{keyboards.CANCEL_CALLBACK_DATA}$"
    )

    add_conversation = ConversationHandler(
        entry_points=[CommandHandler("add", handlers.add_start)],
        states={
            handlers.ADD_SYMBOL: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.add_symbol)],
            handlers.ADD_ENTRY: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.add_entry_price)],
            handlers.ADD_STOP: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.add_stop_price)],
            handlers.ADD_TARGET: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.add_target_price)],
            handlers.ADD_REASON: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.add_reason)],
        },
        fallbacks=[CommandHandler("cancel", handlers.add_cancel)],
    )

    close_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("close", handlers.close_start),
            CallbackQueryHandler(handlers.close_from_status, pattern=r"^close:\d+$"),
        ],
        states={
            handlers.CLOSE_SELECT: [
                cancel_button,
                CallbackQueryHandler(handlers.close_select, pattern=r"^\d+$"),
            ],
            handlers.CLOSE_PRICE: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.close_price)],
            handlers.CLOSE_REASON: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.close_reason)],
        },
        fallbacks=[CommandHandler("cancel", handlers.add_cancel)],
    )

    watchadd_conversation = ConversationHandler(
        entry_points=[CommandHandler("watchadd", handlers.watchadd_start)],
        states={
            handlers.WATCHADD_SYMBOL: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.watchadd_symbol)],
            handlers.WATCHADD_NAME: [cancel_button, MessageHandler(_TEXT_NOT_COMMAND, handlers.watchadd_name)],
            handlers.WATCHADD_CATEGORY: [
                cancel_button,
                CallbackQueryHandler(handlers.watchadd_category, pattern=r"^watchcat:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", handlers.add_cancel)],
    )

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("menu", handlers.menu_command))
    application.add_handler(CommandHandler("scan", handlers.scan))
    application.add_handler(CommandHandler("scan_all", handlers.scan_all))
    application.add_handler(CommandHandler("signals", handlers.signals_scan))
    application.add_handler(CommandHandler("swing", handlers.swing_scan))
    application.add_handler(CommandHandler("status", handlers.status))
    application.add_handler(CommandHandler("journal", handlers.journal_command))
    application.add_handler(CommandHandler("stats", handlers.stats_command))
    application.add_handler(CommandHandler("stats_bench", handlers.stats_bench_command))
    application.add_handler(CommandHandler("watchlist", handlers.watchlist))
    application.add_handler(CommandHandler("watchremove", handlers.watchremove_command))
    application.add_handler(add_conversation)
    application.add_handler(close_conversation)
    application.add_handler(watchadd_conversation)
    application.add_handler(
        MessageHandler(filters.Text(list(handlers.MENU_BUTTON_HANDLERS)), handlers.menu_button)
    )
    application.add_handler(CallbackQueryHandler(handlers.quickadd_start, pattern=r"^add:"))
    application.add_handler(CallbackQueryHandler(handlers.signal_quickadd_start, pattern=r"^sigadd:"))
    application.add_handler(
        CallbackQueryHandler(handlers.quickadd_confirm, pattern=f"^{keyboards.CONFIRM_CALLBACK_DATA}$")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.quickadd_cancel, pattern=f"^{keyboards.DISCARD_CALLBACK_DATA}$")
    )
    application.add_handler(CallbackQueryHandler(handlers.watchremove_confirm, pattern=r"^watchremoveconfirm:"))
    application.add_handler(CallbackQueryHandler(handlers.watchremove_cancel, pattern="^watchremovecancel$"))
    application.add_handler(CallbackQueryHandler(handlers.watchremove_start, pattern=r"^watchremove:"))

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
