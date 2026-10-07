"""telegram_bot/keyboards.py uchun testlar."""

from __future__ import annotations

from datetime import date, datetime, timezone

from signals.payload import HistoricalContext, SignalContext, SignalMode, SignalPayload
from smc.types import StructureState
from telegram_bot import keyboards


def test_main_menu_keyboard_has_exactly_four_buttons() -> None:
    """Watchlist va Yordam tugmalari menyudan olib tashlangan (ular endi faqat
    buyruq: /watchlist, /help) -- pastki menyuda faqat 4 asosiy tugma qoladi."""
    button_texts = [btn.text for row in keyboards.MAIN_MENU_KEYBOARD.keyboard for btn in row]

    assert button_texts == [
        keyboards.BUTTON_SCAN, keyboards.BUTTON_STATUS,
        keyboards.BUTTON_JOURNAL, keyboards.BUTTON_STATS,
    ]


# ---- build_signals_summary_keyboard (TZ: quickadd-from-signal snapshot) ----


def _payload(symbol: str, direction: StructureState = StructureState.BULLISH) -> SignalPayload:
    return SignalPayload(
        symbol=symbol, mode=SignalMode.SWING, setup_type="breakout_retest", score=80.0,
        score_label="SETUP", direction=direction, entry_zone=(99.0, 101.0), invalidation=90.0,
        potential_target=120.0, risk_reward=2.0,
        context=SignalContext(trend="BULLISH", structure="BOS", volume_confirmed=True),
        historical_context=HistoricalContext(expectancy_r=0.6, win_rate_pct=52.8, period_label="2020-2026"),
        generated_at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc), timeframe="1d",
        data_freshness=date(2026, 1, 1),
    )


def test_build_signals_summary_keyboard_adds_button_per_bullish_symbol() -> None:
    keyboard = keyboards.build_signals_summary_keyboard([_payload("AAPL"), _payload("MSFT")])

    callback_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "sigadd:AAPL" in callback_data
    assert "sigadd:MSFT" in callback_data


def test_build_signals_summary_keyboard_excludes_bearish() -> None:
    """Bearish (AVOID/EXIT candidate) uchun tugma yo'q -- bot short taklif qilmaydi."""
    keyboard = keyboards.build_signals_summary_keyboard(
        [_payload("AAPL"), _payload("MSFT", direction=StructureState.BEARISH)],
    )

    callback_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "sigadd:AAPL" in callback_data
    assert not any(cd == "sigadd:MSFT" for cd in callback_data)


def test_build_signals_summary_keyboard_none_when_all_bearish() -> None:
    keyboard = keyboards.build_signals_summary_keyboard([_payload("MSFT", direction=StructureState.BEARISH)])

    assert keyboard is None


def test_build_signals_summary_keyboard_none_when_empty() -> None:
    assert keyboards.build_signals_summary_keyboard([]) is None
