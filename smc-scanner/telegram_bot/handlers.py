"""Har buyruq uchun ingichka async handler — biznes-mantiq mavjud modullardan
(tactical_scan, journal, risk, config) chaqiriladi, bu yerda TAKRORLANMAYDI."""

from __future__ import annotations

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from config.capital_store import get_capital, set_capital
from config.core_watchlist import get_core_watchlist
from config.settings import DEFAULT_RISK_PCT, MAX_DAILY_RISK_PCT, MAX_OPEN_POSITIONS, PRIMARY_INTERVAL
from journal.trade_journal import TradeJournal
from risk.position_sizing import calculate_position_size
from risk.rules import check_daily_risk
from scripts.tactical_scan import DEFAULT_EXIT_MODE, run_scan
from telegram_bot.auth import require_allowed_user
from telegram_bot.formatting import (
    HELP_TEXT,
    format_add_confirmation,
    format_capital_message,
    format_journal_entry_line,
    format_no_setup_line,
    format_setup_message,
    format_stats_message,
    format_watchlist_message,
)

# /add konversatsiya holatlari
ADD_SYMBOL, ADD_ENTRY, ADD_STOP, ADD_TARGET, ADD_REASON = range(5)
# /close konversatsiya holatlari
CLOSE_SELECT, CLOSE_PRICE, CLOSE_REASON = range(5, 8)


# ---- /start, /help ----

@require_allowed_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")


help_command = start


# ---- /scan ----

@require_allowed_user
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    symbols = list(context.args) if context.args else [h.ticker for h in get_core_watchlist()]
    capital = get_capital()
    rows = run_scan(symbols, PRIMARY_INTERVAL, None, exit_mode=DEFAULT_EXIT_MODE)
    for row in rows:
        if row.get("ERROR"):
            await update.effective_message.reply_text(f"{row['SYMBOL']}: xato — {row['ERROR']}")
        elif row.get("HAS_ACTIVE_SETUP"):
            sizing = calculate_position_size(
                capital, row["SETUP_ENTRY"], row["SETUP_STOP"], risk_pct=DEFAULT_RISK_PCT
            )
            await update.effective_message.reply_text(format_setup_message(row, sizing))
        else:
            await update.effective_message.reply_text(format_no_setup_line(row))


# ---- /status ----

@require_allowed_user
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    journal = TradeJournal()
    capital = get_capital()
    open_entries = journal.open_entries()
    risk_result = check_daily_risk(journal, capital, MAX_DAILY_RISK_PCT, MAX_OPEN_POSITIONS)

    lines = ["📂 Ochiq savdolar yo'q."] if not open_entries else ["📂 Ochiq savdolar:"]
    for e in open_entries:
        lines.append(format_journal_entry_line(e))
    lines.append("")
    lines.append(f"Ochiq pozitsiyalar: {len(open_entries)}/{MAX_OPEN_POSITIONS}")
    for w in risk_result.warnings:
        lines.append(f"⚠️ {w}")

    await update.effective_message.reply_text("\n".join(lines))


# ---- /journal ----

@require_allowed_user
async def journal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = int(context.args[0]) if context.args else 10
    journal = TradeJournal()
    entries = journal.recent_entries(n)
    if not entries:
        await update.effective_message.reply_text("Jurnal bo'sh.")
        return
    lines = [format_journal_entry_line(e) for e in entries]
    await update.effective_message.reply_text("\n".join(lines))


# ---- /stats ----

@require_allowed_user
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    journal = TradeJournal()
    await update.effective_message.reply_text(
        format_stats_message(journal.stats()), parse_mode="Markdown"
    )


# ---- /watchlist ----

@require_allowed_user
async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        format_watchlist_message(get_core_watchlist()), parse_mode="Markdown"
    )


# ---- /capital ----

@require_allowed_user
async def capital_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        try:
            value = float(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("Noto'g'ri summa.")
            return
        set_capital(value)
        await update.effective_message.reply_text(format_capital_message(value))
    else:
        await update.effective_message.reply_text(format_capital_message(get_capital()))


# ---- /add ----

@require_allowed_user
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Symbol? (masalan AAPL)")
    return ADD_SYMBOL


async def add_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["symbol"] = update.effective_message.text.strip().upper()
    await update.effective_message.reply_text("Entry narxi?")
    return ADD_ENTRY


async def add_entry_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["entry_price"] = float(update.effective_message.text.strip())
    except ValueError:
        await update.effective_message.reply_text("Noto'g'ri raqam, qayta kiriting:")
        return ADD_ENTRY
    await update.effective_message.reply_text("Stop narxi?")
    return ADD_STOP


async def add_stop_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["stop_price"] = float(update.effective_message.text.strip())
    except ValueError:
        await update.effective_message.reply_text("Noto'g'ri raqam, qayta kiriting:")
        return ADD_STOP
    await update.effective_message.reply_text("Target narxi? (trailing bo'lsa '-' yozing)")
    return ADD_TARGET


async def add_target_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.effective_message.text.strip()
    if text == "-":
        context.user_data["target_price"] = None
    else:
        try:
            context.user_data["target_price"] = float(text)
        except ValueError:
            await update.effective_message.reply_text("Noto'g'ri raqam, qayta kiriting (yoki '-'):")
            return ADD_TARGET
    await update.effective_message.reply_text("Sabab? (masalan: bullish CHoCH + FVG retest)")
    return ADD_REASON


async def add_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["reason"] = update.effective_message.text.strip()
    data = context.user_data

    capital = get_capital()
    sizing = calculate_position_size(
        capital, data["entry_price"], data["stop_price"], risk_pct=DEFAULT_RISK_PCT
    )
    exit_mode = "fixed" if data["target_price"] is not None else "trailing"

    journal = TradeJournal()
    entry = journal.add_entry(
        symbol=data["symbol"],
        entry_date=date.today(),
        entry_price=data["entry_price"],
        stop_price=data["stop_price"],
        target_price=data["target_price"],
        exit_mode=exit_mode,
        reason=data["reason"],
        shares=sizing.shares,
    )
    risk_result = check_daily_risk(journal, capital, MAX_DAILY_RISK_PCT, MAX_OPEN_POSITIONS)

    confirmation = format_add_confirmation(
        symbol=entry.symbol,
        entry_price=entry.entry_price,
        stop_price=entry.stop_price,
        target_price=entry.target_price,
        reason=entry.reason,
        sizing=sizing,
        risk_result=risk_result,
    )
    await update.effective_message.reply_text(f"✅ Savdo qo'shildi (#{entry.entry_id})\n\n{confirmation}")
    context.user_data.clear()
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ---- /close ----

@require_allowed_user
async def close_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    journal = TradeJournal()
    open_entries = journal.open_entries()
    if not open_entries:
        await update.effective_message.reply_text("Ochiq savdolar yo'q.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"#{e.entry_id} {e.symbol}", callback_data=str(e.entry_id))]
        for e in open_entries
    ]
    await update.effective_message.reply_text(
        "Qaysi savdoni yopmoqchisiz?", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CLOSE_SELECT


async def close_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["close_entry_id"] = int(query.data)
    await query.edit_message_text("Chiqish narxini kiriting:")
    return CLOSE_PRICE


async def close_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["close_exit_price"] = float(update.effective_message.text.strip())
    except ValueError:
        await update.effective_message.reply_text("Noto'g'ri raqam, qayta kiriting:")
        return CLOSE_PRICE
    await update.effective_message.reply_text("Sabab/izoh? ('-' agar yo'q bo'lsa)")
    return CLOSE_REASON


async def close_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    notes_text = update.effective_message.text.strip()
    notes = None if notes_text == "-" else notes_text

    journal = TradeJournal()
    entry_id = context.user_data["close_entry_id"]
    exit_price = context.user_data["close_exit_price"]
    closed = journal.close_entry(entry_id, exit_date=date.today(), exit_price=exit_price, notes=notes)

    await update.effective_message.reply_text(
        f"✅ #{closed.entry_id} {closed.symbol} yopildi. R = {closed.r_multiple:.2f}"
    )
    context.user_data.clear()
    return ConversationHandler.END
