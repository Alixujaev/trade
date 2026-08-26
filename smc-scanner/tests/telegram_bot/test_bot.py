"""telegram_bot/bot.py uchun test — barcha handler'lar to'g'ri ro'yxatga olinganini tekshiradi
(run_polling chaqirilmaydi, tarmoqqa chiqilmaydi)."""

from __future__ import annotations

from telegram.ext import CommandHandler, ConversationHandler

from telegram_bot.bot import build_application


def test_build_application_registers_all_commands() -> None:
    app = build_application("123456:fake-token-for-tests")

    command_names: set[str] = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            command_names.update(handler.commands)

    expected = {"start", "help", "scan", "status", "journal", "stats", "watchlist", "capital"}
    assert expected <= command_names


def test_build_application_registers_add_and_close_conversations() -> None:
    app = build_application("123456:fake-token-for-tests")

    conversation_count = sum(1 for h in app.handlers[0] if isinstance(h, ConversationHandler))

    assert conversation_count == 2
