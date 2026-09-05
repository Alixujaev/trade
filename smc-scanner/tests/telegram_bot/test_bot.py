"""telegram_bot/bot.py uchun test — barcha handler'lar to'g'ri ro'yxatga olinganini tekshiradi
(run_polling chaqirilmaydi, tarmoqqa chiqilmaydi)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from telegram_bot import keyboards
from telegram_bot.bot import BOT_COMMANDS, _post_init, build_application


def test_build_application_registers_all_commands() -> None:
    app = build_application("123456:fake-token-for-tests")

    command_names: set[str] = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            command_names.update(handler.commands)

    expected = {
        "start", "help", "scan", "scan_all", "status", "journal", "stats", "stats_bench",
        "watchlist", "watchremove",
    }
    assert expected <= command_names


def test_stats_bench_registered_as_separate_command_from_stats() -> None:
    """/stats_bench (benchmark bilan, sekinroq) /stats'dan (tez, offline) ALOHIDA
    buyruq -- default /stats o'zgarishsiz qolishi kerak."""
    app = build_application("123456:fake-token-for-tests")

    command_names: set[str] = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            command_names.update(handler.commands)

    assert {"stats", "stats_bench"} <= command_names
    assert any(c.command == "stats_bench" for c in BOT_COMMANDS)


def test_build_application_registers_menu_command() -> None:
    app = build_application("123456:fake-token-for-tests")

    command_names: set[str] = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            command_names.update(handler.commands)

    assert "menu" in command_names


def test_signals_and_swing_commands_registered() -> None:
    """/scan (yuqorida allaqachon qamrab olingan) eski tactical_scan.py pipeline'iga
    tegishli — o'zgartirilmagan. Yangi non-directive signals/scanner.py oqimi /signals
    va /swing nomlari bilan ro'yxatga olinadi (naming conflict /scan bilan hal qilindi:
    foydalanuvchi tasdig'i bilan /scan o'zgarishsiz qoldirildi, yangisi boshqa nom oldi)."""
    app = build_application("123456:fake-token-for-tests")

    command_names: set[str] = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            command_names.update(handler.commands)

    assert {"signals", "swing"} <= command_names


def test_build_application_registers_add_and_close_conversations() -> None:
    app = build_application("123456:fake-token-for-tests")

    conversation_count = sum(1 for h in app.handlers[0] if isinstance(h, ConversationHandler))

    assert conversation_count == 3


def test_close_conversation_has_two_entry_points() -> None:
    app = build_application("123456:fake-token-for-tests")

    close_conversation = next(
        h
        for h in app.handlers[0]
        if isinstance(h, ConversationHandler)
        and any(isinstance(ep, CommandHandler) and "close" in ep.commands for ep in h.entry_points)
    )

    assert len(close_conversation.entry_points) == 2


def test_build_application_registers_quickadd_callback_handlers() -> None:
    app = build_application("123456:fake-token-for-tests")

    patterns = {
        h.pattern.pattern
        for h in app.handlers[0]
        if isinstance(h, CallbackQueryHandler) and h.pattern is not None
    }

    assert r"^add:" in patterns
    assert f"^{keyboards.CONFIRM_CALLBACK_DATA}$" in patterns
    assert f"^{keyboards.DISCARD_CALLBACK_DATA}$" in patterns


def test_build_application_registers_watchadd_command() -> None:
    app = build_application("123456:fake-token-for-tests")

    command_names: set[str] = set()
    for handler in app.handlers[0]:
        if isinstance(handler, CommandHandler):
            command_names.update(handler.commands)
        elif isinstance(handler, ConversationHandler):
            for entry_point in handler.entry_points:
                if isinstance(entry_point, CommandHandler):
                    command_names.update(entry_point.commands)

    assert "watchadd" in command_names


def test_build_application_registers_watchremove_callback_handlers() -> None:
    app = build_application("123456:fake-token-for-tests")

    patterns = {
        h.pattern.pattern
        for h in app.handlers[0]
        if isinstance(h, CallbackQueryHandler) and h.pattern is not None
    }

    assert r"^watchremove:" in patterns
    assert r"^watchremoveconfirm:" in patterns
    assert "^watchremovecancel$" in patterns


def test_post_init_calls_set_my_commands() -> None:
    fake_application = MagicMock()
    fake_application.bot.set_my_commands = AsyncMock()

    asyncio.run(_post_init(fake_application))

    fake_application.bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)


def test_post_init_swallows_errors() -> None:
    fake_application = MagicMock()
    fake_application.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("network down"))

    asyncio.run(_post_init(fake_application))  # should not raise
