"""telegram_bot/handlers.py uchun testlar.

Har handler faqat MAVJUD funksiyalarni (run_scan, TradeJournal, risk.*,
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
from config.core_watchlist import add_to_core_watchlist as _real_add_to_core_watchlist
from journal.trade_journal import TradeJournal
from telegram_bot import handlers, keyboards


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
    update, context = _make_update(), _make_context(args=["AMD"])

    _run(handlers.scan(update, context))

    mock_run_scan.assert_called_once()
    assert mock_run_scan.call_args.args[0] == ["AMD"]
    reply_text = update.effective_message.reply_text.call_args_list[1].args[0]
    assert "AMD" in reply_text
    assert "LONG" in reply_text


def test_scan_no_active_setup_shows_short_status(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {"SYMBOL": "AAPL", "HAS_ACTIVE_SETUP": False, "STRUCTURE_STATE": "BEARISH", "ERROR": None}
    monkeypatch.setattr(handlers, "run_scan", MagicMock(return_value=[row]))
    update, context = _make_update(), _make_context()

    _run(handlers.scan(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[1].args[0]
    assert "Faol setup topilmadi" in reply_text
    assert "Faol setupsiz: 1 ta" in reply_text


def test_scan_sends_exactly_one_message_per_call_regardless_of_symbol_count(monkeypatch) -> None:
    """Har belgi uchun alohida xabar yubormasligini tekshiradi — ko'p belgi
    bo'lsa ham jami 2 ta reply_text chaqiruvi (⏳ + yakuniy)."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    rows = [{"SYMBOL": f"SYM{i}", "HAS_ACTIVE_SETUP": False, "ERROR": None} for i in range(50)]
    monkeypatch.setattr(handlers, "run_scan", MagicMock(return_value=rows))
    update, context = _make_update(), _make_context()

    _run(handlers.scan(update, context))

    assert update.effective_message.reply_text.await_count == 2


def test_scan_sends_loading_message_first(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setattr(handlers, "run_scan", MagicMock(return_value=[]))
    update, context = _make_update(), _make_context(args=["AMD"])

    _run(handlers.scan(update, context))

    first_reply = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "⏳" in first_reply


def test_scan_defaults_to_core_watchlist_when_no_args(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    holdings = [CoreHolding("SPUS", "SP Funds", "etf", "ETF holdings", None)]
    monkeypatch.setattr(handlers, "get_core_watchlist", lambda: holdings)
    mock_run_scan = MagicMock(return_value=[])
    monkeypatch.setattr(handlers, "run_scan", mock_run_scan)
    update, context = _make_update(), _make_context()

    _run(handlers.scan(update, context))

    assert mock_run_scan.call_args.args[0] == ["SPUS"]


# ---- /status ----

def test_status_shows_open_entries_and_risk_warnings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for i in range(4):  # MAX_OPEN_POSITIONS=3'dan oshib ketishi uchun
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    update, context = _make_update(), _make_context()

    _run(handlers.status(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "SYM0" in reply_text
    assert "ochiq pozitsiya" in reply_text.lower()


def test_status_no_open_entries(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
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


def test_watchlist_includes_remove_button_per_holding(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    holdings = [CoreHolding("SPUS", "SP Funds", "etf", "ETF holdings", None)]
    monkeypatch.setattr(handlers, "get_core_watchlist", lambda: holdings)
    update, context = _make_update(), _make_context()

    _run(handlers.watchlist(update, context))

    kwargs = update.effective_message.reply_text.call_args_list[0].kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.callback_data == "watchremove:SPUS"


def test_watchlist_large_list_has_no_remove_keyboard(monkeypatch) -> None:
    """WATCHLIST_COMPACT_THRESHOLD'dan ko'p yozuvda 🗑 tugmali keyboard
    yubormaydi — yuzlab tugma amaliy emas, /watchremove TICKER ishlatiladi."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    holdings = [
        CoreHolding(f"SYM{i}", f"Company {i}", "stock", "TEKSHIRILISHI KERAK", None)
        for i in range(50)
    ]
    monkeypatch.setattr(handlers, "get_core_watchlist", lambda: holdings)
    update, context = _make_update(), _make_context()

    _run(handlers.watchlist(update, context))

    kwargs = update.effective_message.reply_text.call_args_list[0].kwargs
    assert kwargs["reply_markup"] is None


def test_watchremove_command_removes_existing(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setattr(handlers, "remove_from_core_watchlist", MagicMock(return_value=True))
    update, context = _make_update(), _make_context(args=["tsla"])

    _run(handlers.watchremove_command(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "TSLA" in reply_text
    assert "o'chirildi" in reply_text


def test_watchremove_command_missing_ticker_arg(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    update, context = _make_update(), _make_context()

    _run(handlers.watchremove_command(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "ticker" in reply_text.lower()


def test_watchremove_command_not_found(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setattr(handlers, "remove_from_core_watchlist", MagicMock(return_value=False))
    update, context = _make_update(), _make_context(args=["NOPE"])

    _run(handlers.watchremove_command(update, context))

    reply_text = update.effective_message.reply_text.call_args_list[0].args[0]
    assert "topilmadi" in reply_text


# ---- /watchadd ----

def test_watchadd_flow_saves_new_holding(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    watchlist_path = tmp_path / "core_watchlist.json"
    monkeypatch.setattr(
        handlers,
        "add_to_core_watchlist",
        lambda *a, **kw: _real_add_to_core_watchlist(*a, path=watchlist_path, **kw),
    )
    context = _make_context()

    state = _run(handlers.watchadd_start(_make_update(), context))
    assert state == handlers.WATCHADD_SYMBOL

    state = _run(handlers.watchadd_symbol(_make_update("tsla"), context))
    assert state == handlers.WATCHADD_NAME
    assert context.user_data["watch_ticker"] == "TSLA"

    state = _run(handlers.watchadd_name(_make_update("Tesla, Inc."), context))
    assert state == handlers.WATCHADD_CATEGORY

    category_update = _make_callback_update("watchcat:stock")
    state = _run(handlers.watchadd_category(category_update, context))

    assert state == ConversationHandler.END
    assert context.user_data == {}
    text = category_update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "TSLA" in text


def test_watchadd_category_rejects_duplicate_ticker(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")

    def _raise(*a, **kw):
        raise ValueError("TSLA allaqachon watchlist'da bor.")

    monkeypatch.setattr(handlers, "add_to_core_watchlist", _raise)
    context = _make_context()
    context.user_data["watch_ticker"] = "TSLA"
    context.user_data["watch_name"] = "Tesla, Inc."
    update = _make_callback_update("watchcat:stock")

    state = _run(handlers.watchadd_category(update, context))

    assert state == ConversationHandler.END
    text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "allaqachon" in text


# ---- /watchlist'dagi 🗑 orqali o'chirish ----

def test_watchremove_start_shows_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    update, context = _make_callback_update("watchremove:TSLA"), _make_context()

    _run(handlers.watchremove_start(update, context))

    text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "TSLA" in text
    kwargs = update.callback_query.edit_message_text.call_args_list[0].kwargs
    assert "reply_markup" in kwargs


def test_watchremove_confirm_removes_existing(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setattr(handlers, "remove_from_core_watchlist", MagicMock(return_value=True))
    update, context = _make_callback_update("watchremoveconfirm:TSLA"), _make_context()

    _run(handlers.watchremove_confirm(update, context))

    text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "TSLA" in text
    assert "o'chirildi" in text


def test_watchremove_confirm_missing_ticker(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.setattr(handlers, "remove_from_core_watchlist", MagicMock(return_value=False))
    update, context = _make_callback_update("watchremoveconfirm:NOPE"), _make_context()

    _run(handlers.watchremove_confirm(update, context))

    text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "topilmadi" in text


def test_watchremove_cancel_shows_message() -> None:
    update, context = _make_callback_update("watchremovecancel"), _make_context()

    _run(handlers.watchremove_cancel(update, context))

    update.callback_query.edit_message_text.assert_awaited_once()


# ---- /add flow ----

def test_add_flow_saves_entry_and_warns_on_risk_breach(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    # MAX_OPEN_POSITIONS=3 — 3 ta ochiq yozuv allaqachon bor, yangisi qo'shilgach
    # (4-chi) ogohlantirish chiqishi kerak
    for i in range(3):
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
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

    assert len(journal.entries) == 4
    added = journal.entries[3]
    assert added.symbol == "AAPL"
    reply_text = final_update.effective_message.reply_text.call_args_list[0].args[0]
    assert "AAPL" in reply_text
    assert "⚠️" in reply_text  # ochiq pozitsiya limiti (3) allaqachon buzilgan


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


def test_close_from_status_enters_close_price_state_directly(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    context = _make_context()
    update = MagicMock()
    update.effective_user.id = 111
    update.callback_query.data = "close:3"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()

    state = _run(handlers.close_from_status(update, context))

    assert state == handlers.CLOSE_PRICE
    assert context.user_data["close_entry_id"] == 3


def test_cancel_conversation_callback_ends_conversation_and_clears_user_data() -> None:
    context = _make_context()
    context.user_data["symbol"] = "AAPL"
    update = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()

    state = _run(handlers.cancel_conversation_callback(update, context))

    assert state == ConversationHandler.END
    assert context.user_data == {}
    update.callback_query.edit_message_text.assert_awaited_once()


# ---- /scan quick-add button ----

def test_scan_active_setup_includes_quickadd_button(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {
        "SYMBOL": "AMD", "SETUP_REASON": "FVG", "SETUP_ENTRY": 150.0, "SETUP_STOP": 140.0,
        "SETUP_TARGET": 175.0, "SETUP_RR": 2.5, "SETUP_ENTRY_DATE": "2026-08-20",
        "HAS_ACTIVE_SETUP": True, "STRUCTURE_STATE": "BULLISH", "ERROR": None,
    }
    monkeypatch.setattr(handlers, "run_scan", MagicMock(return_value=[row]))
    update, context = _make_update(), _make_context(args=["AMD"])

    _run(handlers.scan(update, context))

    kwargs = update.effective_message.reply_text.call_args_list[1].kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.callback_data == "add:AMD"


# ---- /status close button ----

def test_status_includes_close_button_for_open_entry(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    entry = journal.add_entry(
        symbol="AAPL", entry_date=date.today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    update, context = _make_update(), _make_context()

    _run(handlers.status(update, context))

    kwargs = update.effective_message.reply_text.call_args_list[0].kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.callback_data == f"close:{entry.entry_id}"


def test_status_no_open_entries_has_no_reply_markup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    update, context = _make_update(), _make_context()

    _run(handlers.status(update, context))

    kwargs = update.effective_message.reply_text.call_args_list[0].kwargs
    assert kwargs["reply_markup"] is None


# ---- Pastki menu tugmalari ----

def test_menu_button_routes_to_scan(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    mock_scan = AsyncMock()
    monkeypatch.setitem(handlers.MENU_BUTTON_HANDLERS, keyboards.BUTTON_SCAN, mock_scan)
    update, context = _make_update(keyboards.BUTTON_SCAN), _make_context()

    _run(handlers.menu_button(update, context))

    mock_scan.assert_awaited_once_with(update, context)


def test_menu_button_unknown_text_does_nothing(monkeypatch) -> None:
    update, context = _make_update("random text"), _make_context()

    _run(handlers.menu_button(update, context))

    update.effective_message.reply_text.assert_not_called()


# ---- /scan'dan tezkor-qo'shish ----

def _make_callback_update(data: str, user_id: int = 111) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


def test_quickadd_start_shows_confirmation_for_active_setup(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {
        "SYMBOL": "AMD", "SETUP_REASON": "FVG", "SETUP_ENTRY": 150.0, "SETUP_STOP": 140.0,
        "SETUP_TARGET": 175.0, "SETUP_RR": 2.5, "SETUP_ENTRY_DATE": "2026-08-20",
        "HAS_ACTIVE_SETUP": True, "STRUCTURE_STATE": "BULLISH", "ERROR": None,
    }
    monkeypatch.setattr(handlers, "scan_one_symbol", MagicMock(return_value=row))
    update, context = _make_callback_update("add:AMD"), _make_context()

    _run(handlers.quickadd_start(update, context))

    draft = context.user_data["pending_quickadd"]
    assert draft["symbol"] == "AMD"
    assert draft["entry_price"] == 150.0
    first_text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "⏳" in first_text
    kwargs = update.callback_query.edit_message_text.call_args_list[1].kwargs
    assert "reply_markup" in kwargs


def test_quickadd_start_setup_no_longer_active(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {"SYMBOL": "AMD", "HAS_ACTIVE_SETUP": False, "STRUCTURE_STATE": "BEARISH", "ERROR": None}
    monkeypatch.setattr(handlers, "scan_one_symbol", MagicMock(return_value=row))
    update, context = _make_callback_update("add:AMD"), _make_context()

    _run(handlers.quickadd_start(update, context))

    assert "pending_quickadd" not in context.user_data
    text = update.callback_query.edit_message_text.call_args_list[1].args[0]
    assert "tugagan" in text


def test_quickadd_confirm_saves_entry_to_journal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    context = _make_context()
    context.user_data["pending_quickadd"] = {
        "symbol": "AMD", "entry_price": 150.0, "stop_price": 140.0,
        "target_price": 175.0, "reason": "FVG",
    }
    update = _make_callback_update("addconfirm")

    _run(handlers.quickadd_confirm(update, context))

    assert len(journal.entries) == 1
    assert journal.entries[0].symbol == "AMD"
    assert "pending_quickadd" not in context.user_data
    text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "AMD" in text


def test_quickadd_trailing_setup_flows_reference_target_to_journal(monkeypatch, tmp_path) -> None:
    """/scan (trailing mode) -> quickadd -> confirm oqimida reference target jurnalga
    to'g'ri o'tishini va rr_planned hisoblanishini tekshiradi (Phase 11a)."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    row = {
        "SYMBOL": "AMD", "SETUP_REASON": "FVG", "SETUP_ENTRY": 150.0, "SETUP_STOP": 140.0,
        "SETUP_TARGET": None, "SETUP_RR": "N/A (trailing — maqsad yo'q)",
        "SETUP_REFERENCE_TARGET": 175.0, "SETUP_PLANNED_RR": 2.5, "SETUP_LOW_RR_WARNING": False,
        "SETUP_ENTRY_DATE": "2026-08-20", "HAS_ACTIVE_SETUP": True,
        "STRUCTURE_STATE": "BULLISH", "ERROR": None,
    }
    monkeypatch.setattr(handlers, "scan_one_symbol", MagicMock(return_value=row))
    start_update, context = _make_callback_update("add:AMD"), _make_context()

    _run(handlers.quickadd_start(start_update, context))

    draft = context.user_data["pending_quickadd"]
    assert draft["target_price"] is None
    assert draft["reference_target_price"] == 175.0

    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    monkeypatch.setattr(handlers, "TradeJournal", lambda: journal)
    confirm_update = _make_callback_update("addconfirm")

    _run(handlers.quickadd_confirm(confirm_update, context))

    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry.exit_mode == "trailing"
    assert entry.target_price is None
    assert entry.reference_target_price == 175.0
    assert entry.rr_planned == 2.5  # (175-150)/(150-140)


def test_quickadd_confirm_missing_draft_shows_expired_message(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    update, context = _make_callback_update("addconfirm"), _make_context()

    _run(handlers.quickadd_confirm(update, context))

    text = update.callback_query.edit_message_text.call_args_list[0].args[0]
    assert "eskirgan" in text


def test_quickadd_cancel_clears_pending_draft() -> None:
    context = _make_context()
    context.user_data["pending_quickadd"] = {"symbol": "AMD"}
    update = _make_callback_update("addcancel")

    _run(handlers.quickadd_cancel(update, context))

    assert "pending_quickadd" not in context.user_data
    update.callback_query.edit_message_text.assert_awaited_once()
