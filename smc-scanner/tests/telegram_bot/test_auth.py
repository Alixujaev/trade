"""telegram_bot/auth.py uchun testlar — noto'g'ri user_id bloklanishi, to'g'risi o'tishi.

Loyihada pytest-asyncio yo'q, shuning uchun har test o'z ichida asyncio.run() bilan
async wrapper'ni chaqiradi (qo'shimcha test-only dependency qo'shmaslik uchun)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.auth import require_allowed_user


def _make_update(user_id: int) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message.reply_text = AsyncMock()
    return update


def test_wrong_user_id_is_blocked(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    inner = AsyncMock()
    wrapped = require_allowed_user(inner)
    update = _make_update(user_id=999)

    asyncio.run(wrapped(update, MagicMock()))

    inner.assert_not_called()
    update.effective_message.reply_text.assert_awaited_once()


def test_correct_user_id_passes_through(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    inner = AsyncMock()
    wrapped = require_allowed_user(inner)
    update = _make_update(user_id=111)
    context = MagicMock()

    asyncio.run(wrapped(update, context))

    inner.assert_awaited_once_with(update, context)
    update.effective_message.reply_text.assert_not_called()


def test_correct_user_id_return_value_is_propagated(monkeypatch) -> None:
    """ConversationHandler navbatdagi holatni handler'ning return qiymatidan oladi —
    decorator shu qiymatni yutib qo'ymasligi kerak."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    inner = AsyncMock(return_value=42)
    wrapped = require_allowed_user(inner)
    update = _make_update(user_id=111)

    result = asyncio.run(wrapped(update, MagicMock()))

    assert result == 42


def test_missing_allowed_user_id_env_blocks_everyone(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)
    inner = AsyncMock()
    wrapped = require_allowed_user(inner)
    update = _make_update(user_id=111)

    asyncio.run(wrapped(update, MagicMock()))

    inner.assert_not_called()
