"""telegram_bot/handlers.py uchun testlar.

Har handler faqat MAVJUD funksiyalarni (run_scan, TradeJournal, risk.*, capital_store,
get_core_watchlist) chaqirishi kerak — bu yerda ular monkeypatch bilan almashtirilib,
handler to'g'ri chaqirayotgani va javob matni kutilganidek ekanligi tekshiriladi.
python-telegram-bot ConversationHandler'ning o'zi ishga tushirilmaydi — har holat
funksiyasi to'g'ridan-to'g'ri chaqiriladi (asyncio.run bilan, pytest-asyncio yo'q)."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import ConversationHandler

from config.core_watchlist import CoreHolding
from journal.trade_journal import TradeJournal
from risk.position_sizing import PositionSize
from telegram_bot import handlers


def _make_update(text: str = "", user_id: int = 111) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message.text = text
    update.effective_message.reply_text = AsyncMock()
    return update


def _make_context(args: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(args=args or [], user_data={})


def _run(coro):
    return asyncio.run(coro)


# ---- /scan ----

def test_scan_active_setup_calls_run_scan_and_formats_message(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {
        "SYMBOL": "AMD", "SETUP_REASON": "FVG", "SETUP_ENTRY": 150.0, "SETUP_STOP": 140.0,
        "SETUP_TARGET": 175.0, "SETUP_RR": 2.5, "SETUP_ENTRY_DATE": "2026-08-20",
        "HAS_ACTIVE_SETUP": True, "STRUCTURE_STATE": "BULLISH", "ERROR": None,
    }
    mock_run_scan = MagicMock(return_value=[row])
    monkeypatch.setattr(handlers, "run_scan", mock_run_scan)
    monkeypatch.setattr(handlers, "get_capital", lambda: 10_000.0)
    update, context = _make_update(), _make_context(args=["AMD"])

    _run(handlers.scan(update, context))

    mock_run_scan.assert_called_once()
    assert mock_run_scan.call_args.args[0] == ["AMD"]
    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AMD" in reply_text
    assert "LONG" in reply_text


def test_scan_no_active_setup_shows_short_status(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {"SYMBOL": "AAPL", "HAS_ACTIVE_SETUP": False, "STRUCTURE_STATE": "BEARISH", "ERROR": None}
    monkeypatch.setattr(handlers, "run_scan", MagicMock(return_value=[row]))
    monkeypatch.setattr(handlers, "get_capital", lambda: 10_000.0)
    update, context = _make_update(), _make_context()

    _run(handlers.scan(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AAPL" in reply_text
    assert "BEARISH" in reply_text


def test_scan_defaults_to_core_watchlist_when_no_args(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    holdings = [CoreHolding("SPUS", "SP Funds", "etf", "ETF holdings", None)]
    monkeypatch.setattr(handlers, "get_core_watchlist", lambda: holdings)
    mock_run_scan = MagicMock(return_value=[])
    monkeypatch.setattr(handlers, "run_scan", mock_run_scan)
    monkeypatch.setattr(handlers, "get_capital", lambda: 10_000.0)
    update, context = _make_update(), _make_context()

    _run(handlers.scan(update, context))

    assert mock_run_scan.call_args.args[0] == ["SPUS"]


# ---- /status ----

def test_status_shows_open_entries_and_risk_warnings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=100,
    )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    monkeypatch.setattr(handlers, "get_capital", lambda: 10_000.0)
    update, context = _make_update(), _make_context()

    _run(handlers.status(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AAPL" in reply_text
    assert "kunlik" in reply_text.lower()  # 100 shares * $10 risk = $1000 > 2% of 10000 ($200)


def test_status_no_open_entries(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    monkeypatch.setattr(handlers, "get_capital", lambda: 10_000.0)
    update, context = _make_update(), _make_context()

    _run(handlers.status(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "yo'q" in reply_text.lower()


# ---- /journal ----

def test_journal_shows_recent_entries(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    update, context = _make_update(), _make_context()

    _run(handlers.journal_command(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AAPL" in reply_text


# ---- /stats ----

def test_stats_calls_journal_stats(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    update, context = _make_update(), _make_context()

    _run(handlers.stats_command(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "Profit factor" in reply_text


# ---- /watchlist ----

def test_watchlist_lists_holdings(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    holdings = [CoreHolding("SPUS", "SP Funds", "etf", "ETF holdings", None)]
    monkeypatch.setattr(handlers, "get_core_watchlist", lambda: holdings)
    update, context = _make_update(), _make_context()

    _run(handlers.watchlist(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "SPUS" in reply_text


# ---- /capital ----

def test_capital_view_shows_current(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setattr(handlers, "get_capital", lambda: 7_500.0)
    update, context = _make_update(), _make_context()

    _run(handlers.capital_command(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "7" in reply_text and "500" in reply_text


def test_capital_set_calls_set_capital(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    mock_set = MagicMock()
    monkeypatch.setattr(handlers, "set_capital", mock_set)
    update, context = _make_update(), _make_context(args=["5000"])

    _run(handlers.capital_command(update, context))

    mock_set.assert_called_once_with(5000.0)


# ---- /add flow ----

def test_add_flow_saves_entry_and_warns_on_risk_breach(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    # capital=1000, 2% daily limit=$20 — bugungi mavjud yozuv ($500 risk) allaqachon buzadi,
    # shu holatda yangi savdo qo'shilgandan keyin ham ogohlantirish chiqishi kerak
    journal.add_entry(
        symbol="MSFT", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=50,
    )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    monkeypatch.setattr(handlers, "get_capital", lambda: 1_000.0)
    context = _make_context()

    state = _run(handlers.add_start(_make_update(), context))
    assert state == handlers.ADD_SYMBOL

    state = _run(handlers.add_symbol(_make_update("AAPL"), context))
    assert state == handlers.ADD_ENTRY
    assert context.user_data["symbol"] == "AAPL"

    state = _run(handlers.add_entry_price(_make_update("100"), context))
    assert state == handlers.ADD_STOP

    state = _run(handlers.add_stop_price(_make_update("90"), context))
    assert state == handlers.ADD_TARGET

    state = _run(handlers.add_target_price(_make_update("130"), context))
    assert state == handlers.ADD_REASON

    final_update = _make_update("bullish CHoCH + FVG retest")
    state = _run(handlers.add_reason(final_update, context))
    assert state == ConversationHandler.END

    assert len(journal.entries) == 2
    added = journal.entries[1]
    assert added.symbol == "AAPL"
    assert added.shares is not None
    reply_text = final_update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AAPL" in reply_text
    assert "⚠️" in reply_text  # kunlik limit MSFT yozuvi bilan allaqachon buzilgan


def test_add_entry_price_invalid_number_reprompts_same_state(monkeypatch) -> None:
    context = _make_context()
    update = _make_update("not-a-number")

    state = _run(handlers.add_entry_price(update, context))

    assert state == handlers.ADD_ENTRY
    update.effective_message.reply_text.assert_awaited_once()


def test_add_target_price_dash_means_no_target(monkeypatch) -> None:
    context = _make_context()
    update = _make_update("-")

    state = _run(handlers.add_target_price(update, context))

    assert state == handlers.ADD_REASON
    assert context.user_data["target_price"] is None


# ---- /close flow ----

def test_close_start_shows_buttons_for_open_entries(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    update, context = _make_update(), _make_context()

    state = _run(handlers.close_start(update, context))

    assert state == handlers.CLOSE_SELECT
    kwargs = update.effective_message.reply_text.call_args_list[0].kwargs
    assert "reply_markup" in kwargs


def test_close_select_stores_entry_id_from_callback(monkeypatch, tmp_path) -> None:
    context = _make_context()
    update = MagicMock()
    update.callback_query.data = "1"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()

    state = _run(handlers.close_select(update, context))

    assert state == handlers.CLOSE_PRICE
    assert context.user_data["close_entry_id"] == 1


def test_close_price_then_reason_closes_entry(monkeypatch, tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    context = _make_context()
    context.user_data["close_entry_id"] = 1

    price_update = _make_update("115")
    state = _run(handlers.close_price(price_update, context))
    assert state == handlers.CLOSE_REASON

    reason_update = _make_update("-")
    state = _run(handlers.close_reason(reason_update, context))
    assert state == ConversationHandler.END

    assert journal.entries[0].exit_price == 115.0
    reply_text = reason_update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AAPL" in reply_text
