"""telegram_bot/keyboards.py uchun testlar."""

from __future__ import annotations

from telegram_bot import keyboards


def test_main_menu_keyboard_has_exactly_four_buttons() -> None:
    """Watchlist va Yordam tugmalari menyudan olib tashlangan (ular endi faqat
    buyruq: /watchlist, /help) -- pastki menyuda faqat 4 asosiy tugma qoladi."""
    button_texts = [btn.text for row in keyboards.MAIN_MENU_KEYBOARD.keyboard for btn in row]

    assert button_texts == [
        keyboards.BUTTON_SCAN, keyboards.BUTTON_STATUS,
        keyboards.BUTTON_JOURNAL, keyboards.BUTTON_STATS,
    ]
