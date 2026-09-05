"""Har buyruq uchun ingichka async handler — biznes-mantiq mavjud modullardan
(tactical_scan, journal, risk, config) chaqiriladi, bu yerda TAKRORLANMAYDI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config.core_watchlist import add_to_core_watchlist, get_core_watchlist, remove_from_core_watchlist
from config.settings import (
    MAX_OPEN_POSITIONS,
    MAX_SIGNALS_PER_SCAN,
    PRIMARY_INTERVAL,
    SCORE_THRESHOLDS,
    SIGNAL_COOLDOWN_HOURS,
    SIGNAL_DEDUP_CLEANUP_MULT,
    WATCHLIST_COMPACT_THRESHOLD,
)
from data.factory import get_provider
from journal.trade_journal import TradeJournal
from journal.types import JournalEntry
from risk.rules import check_open_positions
from scripts.tactical_scan import DEFAULT_EXIT_MODE, filter_quality_setups, run_scan, scan_one_symbol
from signals.dedup import DedupStore
from signals.payload import SignalMode, SignalPayload, format_payload, signal_id_for_payload, signal_id_for_row
from signals.scanner import scan_universe
from telegram_bot import keyboards
from telegram_bot.auth import require_allowed_user
from telegram_bot.formatting import (
    HELP_TEXT,
    chunk_signal_messages,
    format_add_confirmation,
    format_journal_entry_line,
    format_scan_summary,
    format_setup_message,
    format_stats_message,
    format_watchlist_message,
)

logger = logging.getLogger(__name__)

# /add konversatsiya holatlari
ADD_SYMBOL, ADD_ENTRY, ADD_STOP, ADD_TARGET, ADD_REASON = range(5)
# /close konversatsiya holatlari
CLOSE_SELECT, CLOSE_PRICE, CLOSE_REASON = range(5, 8)
# /watchadd konversatsiya holatlari
WATCHADD_SYMBOL, WATCHADD_NAME, WATCHADD_CATEGORY = range(8, 11)


# ---- /start, /help ----

@require_allowed_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        HELP_TEXT, parse_mode="Markdown", reply_markup=keyboards.MAIN_MENU_KEYBOARD
    )


help_command = start


# ---- /menu ----

@require_allowed_user
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📋 Menu yangilandi.", reply_markup=keyboards.MAIN_MENU_KEYBOARD
    )


# ---- Pastki menu tugmalari -> mos komanda handler'iga yo'naltirish ----

MENU_BUTTON_HANDLERS: dict[str, Callable] = {}


async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har target handler allaqachon @require_allowed_user bilan himoyalangan —
    bu yerda qo'shimcha tekshiruv shart emas."""
    handler = MENU_BUTTON_HANDLERS.get((update.effective_message.text or "").strip())
    if handler is None:
        return
    context.args = []
    await handler(update, context)


# ---- /scan, /scan_all ----

def _dedup_filter_new_setups(visible: list[dict]) -> tuple[list[dict], int]:
    """Sifat-filtrdan o'tgan faol setup'larni dedup+cooldown (TZ 18) orqali
    filtrlaydi — SKAN MANTIG'INI O'ZGARTIRMAYDI (run_scan/filter_quality_setups
    allaqachon chaqirilgan), faqat YUBORISH bosqichida qaysi setup ko'rsatilishini
    tanlaydi. Yangi (is_new) setup'lar mark_shown qilinadi; eski (cooldown
    ichidagi) yozuvlar cleanup bilan tozalanadi — fayl cheksiz o'smasin."""
    store = DedupStore()
    new_rows: list[dict] = []
    skipped = 0
    for row in visible:
        signal_id = signal_id_for_row(row, mode=DEFAULT_EXIT_MODE)
        if signal_id is None or store.is_new(signal_id, cooldown_hours=SIGNAL_COOLDOWN_HOURS):
            new_rows.append(row)
            if signal_id is not None:
                store.mark_shown(signal_id)
        else:
            skipped += 1
    store.cleanup(older_than_hours=SIGNAL_COOLDOWN_HOURS * SIGNAL_DEDUP_CLEANUP_MULT)
    return new_rows, skipped


async def _run_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, *, show_all: bool) -> None:
    """Har belgi uchun alohida xabar YO'Q — bitta "ishlayapti" xabari, keyin
    skanerlash tugagach bitta yakuniy xabar. show_all=False (default /scan) bo'lsa
    past R:R (< MIN_PLANNED_RR) setup'lar yashiriladi — /scan_all (show_all=True)
    bilan hammasi ko'rsatiladi. Auth-decorator'siz — chaqiruvchi handler'lar
    (scan/scan_all) allaqachon himoyalangan (menu_button konvensiyasiga mos).

    Dedup+cooldown (TZ 18): sifatli faol setup'lar ORASIDAN oldin ko'rsatilgan
    (cooldown ichidagi) setup'lar bu yerda chiqarib tashlanadi — foydalanuvchi
    bir xil setup'ni har /scan'da qayta ko'rmaydi."""
    symbols = list(context.args) if context.args else [h.ticker for h in get_core_watchlist()]
    suffix = " (hammasi)" if show_all else ""
    await update.effective_message.reply_text(f"⏳ {len(symbols)} ta belgi skanerlanmoqda{suffix}...")
    rows = run_scan(symbols, PRIMARY_INTERVAL, None, exit_mode=DEFAULT_EXIT_MODE)
    visible, _ = filter_quality_setups(rows, show_all=show_all)
    new_visible, dedup_skipped_count = _dedup_filter_new_setups(visible)
    await update.effective_message.reply_text(
        format_scan_summary(
            rows, show_all=show_all, dedup_new=new_visible, dedup_skipped_count=dedup_skipped_count,
        ),
        reply_markup=keyboards.build_scan_summary_keyboard(new_visible),
    )


@require_allowed_user
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_scan(update, context, show_all=False)


@require_allowed_user
async def scan_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/scan'ning past R:R setup'larni HAM ko'rsatadigan varianti."""
    await _run_scan(update, context, show_all=True)


# ---- /signals, /swing ----
# Eski /scan (yuqorida) tactical_scan.py'ning direktiv ("LONG") pipeline'idan foydalanadi.
# Bular signals/scanner.py + signals/payload.py'ga asoslangan — YANGI, NON-DIRECTIVE
# "setup intelligence" oqimi (research phase yopilgan: market/selection/exit edge topilmadi,
# bot endi qaror odam qiladigan skaner). Trading/scoring/ATR/entry-zone/backtest-statistika
# hisoblanishi BU YERDA YO'Q — hammasi signals/scanner.py va signals/payload.py'da (mavjud,
# sinalgan); bu handler faqat chaqiradi, natijani cheklaydi/formatlaydi, yuboradi.

def _keep_highest_score_per_symbol(payloads: list[SignalPayload]) -> list[SignalPayload]:
    """Bir symboldan faqat ENG YUQORI score'li payload'ni qoldiradi — foydalanuvchi
    bir symbolni BIR MARTA, eng yaxshi setup bilan ko'rishi kerak. Bir nechta nomzod
    turli setup_type/entry_ts olishi mumkin (boshqa-boshqa signal_id — dedup ularni
    to'g'ri "boshqa signal" deb hisoblaydi, `signals/payload.py::signal_id_for_payload`
    o'zi TO'G'RI ishlaydi) — lekin bu FAQAT YUBORISH/UX filtri, dedup ID mantig'iga
    tegmaydi (guruhlash shu yerda, DedupStore tekshiruvidan OLDIN amalga oshadi).
    Kirish tartibidan qat'i nazar to'g'ri ishlaydi (score to'g'ridan-to'g'ri
    solishtiriladi)."""
    best: dict[str, SignalPayload] = {}
    for payload in payloads:
        current = best.get(payload.symbol)
        if current is None or payload.score > current.score:
            best[payload.symbol] = payload
    return list(best.values())


def _dedup_filter_new_payloads(payloads: list[SignalPayload]) -> tuple[list[SignalPayload], int]:
    """/signals, /swing uchun dedup+cooldown (TZ 18) — `_dedup_filter_new_setups` (/scan)
    bilan BIR XIL `DedupStore`/`SIGNAL_COOLDOWN_HOURS` mexanizmi, faqat `SignalPayload`
    ustida (`signal_id_for_payload`). SKAN MANTIG'INI O'ZGARTIRMAYDI (`scan_universe`
    allaqachon chaqirilgan) — faqat YUBORISH bosqichida qaysi payload ko'rsatilishini
    tanlaydi. Bitta umumiy `DedupStore` fayli (/scan bilan) — endi ikkala oqim ham
    BIR XIL `compute_signal_id` formulasiga tayanadi (izchil).

    Avval `_keep_highest_score_per_symbol` bilan bitta scan ichidagi bir symbolning
    barcha nomzodlari BITTAGA (eng yuqori score'li) kamaytiriladi, so'ng qolgan
    (bitta symbol = bitta nomzod) ro'yxat DedupStore/cooldown orqali filtrlanadi.
    Qaytarilgan `skipped` soni ikkalasini ham qamraydi (guruh-ichi kamaytirilganlar +
    cooldown'dagilar) — chaqiruvchi kod (xabar formatlash) o'zgarishsiz qoladi."""
    candidates = _keep_highest_score_per_symbol(payloads)
    collapsed_count = len(payloads) - len(candidates)

    store = DedupStore()
    new_payloads: list[SignalPayload] = []
    cooldown_skipped = 0
    for payload in candidates:
        signal_id = signal_id_for_payload(payload)
        if signal_id is None or store.is_new(signal_id, cooldown_hours=SIGNAL_COOLDOWN_HOURS):
            new_payloads.append(payload)
            if signal_id is not None:
                store.mark_shown(signal_id)
        else:
            cooldown_skipped += 1
    store.cleanup(older_than_hours=SIGNAL_COOLDOWN_HOURS * SIGNAL_DEDUP_CLEANUP_MULT)
    return new_payloads, collapsed_count + cooldown_skipped


async def _run_signal_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, *, mode: SignalMode) -> None:
    symbols = [h.ticker for h in get_core_watchlist()]
    min_score = SCORE_THRESHOLDS["watch"]
    await update.effective_message.reply_text(f"⏳ {len(symbols)} ta belgi skanerlanmoqda...")

    try:
        results, skipped = scan_universe(
            symbols, get_provider(), interval=PRIMARY_INTERVAL, mode=mode, min_score=min_score,
        )
    except Exception:
        logger.warning("scan_universe xatosi", exc_info=True)
        await update.effective_message.reply_text("Skanerlashda xatolik, qayta urinib ko'ring.")
        return

    all_payloads = sorted(
        (p for payloads in results.values() for p in payloads),
        key=lambda p: p.score, reverse=True,
    )
    total_found = len(all_payloads)

    if not all_payloads:
        text = f"Skan tugadi. Hozircha setup yo'q (min-score {min_score:.0f})."
        if skipped:
            text += f"\nSkipped: {len(skipped)}"
        await update.effective_message.reply_text(text)
        return

    new_payloads, dedup_skipped_count = _dedup_filter_new_payloads(all_payloads)
    shown = new_payloads[:MAX_SIGNALS_PER_SCAN]

    if not shown:
        await update.effective_message.reply_text(
            "Yangi setup yo'q — barchasi oldin yuborilgan (cooldown ichida).\n"
            f"🔁 Dedup: {total_found} ta topildi, {dedup_skipped_count} ta o'tkazib yuborildi."
        )
        return

    cards = [format_payload(p) for p in shown]
    for message in chunk_signal_messages(cards):
        await update.effective_message.reply_text(message)

    count_line = f"Setups: {total_found}"
    if total_found > len(shown):
        count_line += f" (ko'rsatildi: {len(shown)})"
    dedup_line = (
        f"🔁 Dedup: {total_found} ta topildi, {len(new_payloads)} ta yangi, "
        f"{dedup_skipped_count} ta o'tkazib yuborildi."
    )
    await update.effective_message.reply_text(
        f"Scan complete.\n{count_line}\nSkipped: {len(skipped)}\n{dedup_line}"
    )


@require_allowed_user
async def signals_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_signal_scan(update, context, mode=SignalMode.SWING)


@require_allowed_user
async def swing_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_signal_scan(update, context, mode=SignalMode.SWING)


# ---- /status ----

@require_allowed_user
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    journal = TradeJournal()
    open_entries = journal.open_entries()
    risk_result = check_open_positions(journal, MAX_OPEN_POSITIONS)

    lines = ["📂 Ochiq savdolar yo'q."] if not open_entries else ["📂 Ochiq savdolar:"]
    for e in open_entries:
        lines.append(format_journal_entry_line(e))
    lines.append("")
    lines.append(f"Ochiq pozitsiyalar: {len(open_entries)}/{MAX_OPEN_POSITIONS}")
    for w in risk_result.warnings:
        lines.append(f"⚠️ {w}")

    reply_markup = keyboards.build_status_close_keyboard(open_entries) if open_entries else None
    await update.effective_message.reply_text("\n".join(lines), reply_markup=reply_markup)


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


# ---- /stats_bench ----

@require_allowed_user
async def stats_bench_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats kabi, lekin discretionary vs buy&hold benchmark bilan (uch blok:
    discretionary | buy&hold | comparison — journal.trade_journal.TradeJournal.stats
    (include_benchmark=True)). Har YOPIQ savdo uchun alohida provider so'rovi kerak
    bo'lgani uchun /stats'dan SEKINROQ — shu sabab ATAYLAB alohida buyruq (oddiy /stats
    tez/offline qolishi kerak, default include_benchmark=False o'zgarishsiz)."""
    journal = TradeJournal()
    await update.effective_message.reply_text("⏳ Benchmark hisoblanmoqda...")

    try:
        stats = journal.stats(include_benchmark=True, provider=get_provider())
    except Exception:
        logger.warning("Benchmark stats xatosi", exc_info=True)
        await update.effective_message.reply_text(
            "Benchmark hisoblashda xatolik, qayta urinib ko'ring."
        )
        return

    await update.effective_message.reply_text(
        format_stats_message(stats), parse_mode="Markdown"
    )


# ---- /watchlist ----

@require_allowed_user
async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    holdings = get_core_watchlist()
    # Katta ro'yxatda (WATCHLIST_COMPACT_THRESHOLD'dan ko'p) 🗑 tugmali keyboard
    # qo'shilmaydi -- yuzlab tugma keyboard'ni ishlatib bo'lmas holga keltiradi;
    # o'sha holatda o'chirish /watchremove TICKER orqali (format_watchlist_message'da
    # ko'rsatilgan).
    reply_markup = (
        keyboards.build_watchlist_remove_keyboard(holdings)
        if holdings and len(holdings) <= WATCHLIST_COMPACT_THRESHOLD
        else None
    )
    await update.effective_message.reply_text(
        format_watchlist_message(holdings), parse_mode="Markdown", reply_markup=reply_markup
    )


@require_allowed_user
async def watchremove_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Katta watchlist'larda (🗑 tugma yo'q holatda) yagona o'chirish yo'li."""
    if not context.args:
        await update.effective_message.reply_text("Ticker kiriting. Masalan: /watchremove TSLA")
        return
    ticker = context.args[0].strip().upper()
    if remove_from_core_watchlist(ticker):
        await update.effective_message.reply_text(f"🗑 {ticker} watchlist'dan o'chirildi.")
    else:
        await update.effective_message.reply_text(f"{ticker} watchlist'da topilmadi.")


# ---- /watchadd ----

@require_allowed_user
async def watchadd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text(
        "Ticker? (masalan TSLA)", reply_markup=keyboards.build_cancel_keyboard()
    )
    return WATCHADD_SYMBOL


async def watchadd_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["watch_ticker"] = update.effective_message.text.strip().upper()
    await update.effective_message.reply_text(
        "Kompaniya/fond nomi? (masalan Tesla, Inc.)", reply_markup=keyboards.build_cancel_keyboard()
    )
    return WATCHADD_NAME


async def watchadd_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["watch_name"] = update.effective_message.text.strip()
    await update.effective_message.reply_text(
        "Turi?", reply_markup=keyboards.build_category_keyboard()
    )
    return WATCHADD_CATEGORY


async def watchadd_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data.split(":", 1)[1]
    ticker = context.user_data["watch_ticker"]
    name = context.user_data["watch_name"]

    try:
        holding = add_to_core_watchlist(ticker, name, category)
    except ValueError as exc:
        await query.edit_message_text(str(exc))
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        f"✅ {holding.ticker} watchlist'ga qo'shildi.\n"
        "⚠️ Eslatma: shariat muvofiqligini o'zingiz tekshirib ko'rgan bo'lishingiz "
        "kerak — bu bot hech qanday skrining qilmaydi."
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---- /watchlist'dagi 🗑 tugmasi orqali o'chirish ----

@require_allowed_user
async def watchremove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    ticker = query.data.split(":", 1)[1]
    await query.edit_message_text(
        f"{ticker}'ni watchlist'dan o'chirilsinmi?",
        reply_markup=keyboards.build_watchremove_confirm_keyboard(ticker),
    )


@require_allowed_user
async def watchremove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    ticker = query.data.split(":", 1)[1]
    removed = remove_from_core_watchlist(ticker)
    if removed:
        await query.edit_message_text(f"🗑 {ticker} watchlist'dan o'chirildi.")
    else:
        await query.edit_message_text(f"{ticker} watchlist'da topilmadi.")


async def watchremove_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Bekor qilindi.")


# ---- /add ----

def _finalize_trade(
    *, symbol: str, entry_price: float, stop_price: float, target_price: float | None, reason: str,
    reference_target_price: float | None = None,
) -> tuple[JournalEntry, str]:
    """Jurnalga yozish + risk tekshiruvi + tasdiqlash matni — /add (qo'lda kiritish,
    add_reason) va tezkor-qo'shish (quickadd_confirm, /scan'dan) ikkalasi ham shu
    orqali saqlaydi, saqlash mantig'i bir joyda takrorlanmaydi. Pozitsiya
    hajmi/kapital bu yerda hisoblanmaydi — savdo boshqa platformada (masalan
    TradingView) qilinadi, bot faqat narx/sabab ma'lumotini saqlaydi."""
    exit_mode = "fixed" if target_price is not None else "trailing"

    journal = TradeJournal()
    entry = journal.add_entry(
        symbol=symbol,
        entry_date=date.today(),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        exit_mode=exit_mode,
        reason=reason,
        reference_target_price=reference_target_price,
    )
    risk_result = check_open_positions(journal, MAX_OPEN_POSITIONS)

    confirmation = format_add_confirmation(
        symbol=entry.symbol,
        entry_price=entry.entry_price,
        stop_price=entry.stop_price,
        target_price=entry.target_price,
        reason=entry.reason,
        risk_result=risk_result,
        reference_target_price=entry.reference_target_price,
    )
    return entry, confirmation


@require_allowed_user
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text(
        "Symbol? (masalan AAPL)", reply_markup=keyboards.build_cancel_keyboard()
    )
    return ADD_SYMBOL


async def add_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["symbol"] = update.effective_message.text.strip().upper()
    await update.effective_message.reply_text(
        "Entry narxi?", reply_markup=keyboards.build_cancel_keyboard()
    )
    return ADD_ENTRY


async def add_entry_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["entry_price"] = float(update.effective_message.text.strip())
    except ValueError:
        await update.effective_message.reply_text(
            "Noto'g'ri raqam, qayta kiriting:", reply_markup=keyboards.build_cancel_keyboard()
        )
        return ADD_ENTRY
    await update.effective_message.reply_text(
        "Stop narxi?", reply_markup=keyboards.build_cancel_keyboard()
    )
    return ADD_STOP


async def add_stop_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["stop_price"] = float(update.effective_message.text.strip())
    except ValueError:
        await update.effective_message.reply_text(
            "Noto'g'ri raqam, qayta kiriting:", reply_markup=keyboards.build_cancel_keyboard()
        )
        return ADD_STOP
    await update.effective_message.reply_text(
        "Target narxi? (trailing bo'lsa '-' yozing)", reply_markup=keyboards.build_cancel_keyboard()
    )
    return ADD_TARGET


async def add_target_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.effective_message.text.strip()
    if text == "-":
        context.user_data["target_price"] = None
    else:
        try:
            context.user_data["target_price"] = float(text)
        except ValueError:
            await update.effective_message.reply_text(
                "Noto'g'ri raqam, qayta kiriting (yoki '-'):",
                reply_markup=keyboards.build_cancel_keyboard(),
            )
            return ADD_TARGET
    await update.effective_message.reply_text(
        "Sabab? (masalan: bullish CHoCH + FVG retest)", reply_markup=keyboards.build_cancel_keyboard()
    )
    return ADD_REASON


async def add_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["reason"] = update.effective_message.text.strip()
    data = context.user_data

    entry, confirmation = _finalize_trade(
        symbol=data["symbol"],
        entry_price=data["entry_price"],
        stop_price=data["stop_price"],
        target_price=data["target_price"],
        reason=data["reason"],
    )
    await update.effective_message.reply_text(f"✅ Savdo qo'shildi (#{entry.entry_id})\n\n{confirmation}")
    context.user_data.clear()
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


async def cancel_conversation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inline "❌ Bekor qilish" tugmasi orqali /add yoki /close oqimini to'xtatadi
    (add_cancel'ning callback-query varianti — xuddi shunday auth-decorator'siz,
    bekor qilish past-xavfli amal)."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("Bekor qilindi.")
    return ConversationHandler.END


# ---- /close ----

@require_allowed_user
async def close_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    journal = TradeJournal()
    open_entries = journal.open_entries()
    if not open_entries:
        await update.effective_message.reply_text("Ochiq savdolar yo'q.")
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "Qaysi savdoni yopmoqchisiz?",
        reply_markup=keyboards.build_close_select_keyboard(open_entries),
    )
    return CLOSE_SELECT


async def close_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["close_entry_id"] = int(query.data)
    await query.edit_message_text(
        "Chiqish narxini kiriting:", reply_markup=keyboards.build_cancel_keyboard()
    )
    return CLOSE_PRICE


@require_allowed_user
async def close_from_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/status'dagi "Yopish #id SYMBOL" tugmasi — tanlash bosqichini o'tkazib
    yuborib, to'g'ridan-to'g'ri narx so'raladi (savdo allaqachon tanlangan)."""
    query = update.callback_query
    await query.answer()
    entry_id = int(query.data.split(":", 1)[1])
    context.user_data["close_entry_id"] = entry_id
    await query.edit_message_text(
        f"#{entry_id} tanlandi. Chiqish narxini kiriting:",
        reply_markup=keyboards.build_cancel_keyboard(),
    )
    return CLOSE_PRICE


async def close_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["close_exit_price"] = float(update.effective_message.text.strip())
    except ValueError:
        await update.effective_message.reply_text(
            "Noto'g'ri raqam, qayta kiriting:", reply_markup=keyboards.build_cancel_keyboard()
        )
        return CLOSE_PRICE
    await update.effective_message.reply_text(
        "Sabab/izoh? ('-' agar yo'q bo'lsa)", reply_markup=keyboards.build_cancel_keyboard()
    )
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


# ---- /scan'dan tezkor-qo'shish (inline "➕ Jurnalga qo'shish") ----

@require_allowed_user
async def quickadd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback_data 64-bayt limitidan qochish uchun raqamlarni o'zida saqlamaydi —
    faqat symbol'ni oladi va setup'ni qayta hisoblaydi (bir kun ichida deterministik)."""
    query = update.callback_query
    await query.answer()
    symbol = query.data.split(":", 1)[1]
    await query.edit_message_text(f"⏳ {symbol} tekshirilmoqda...")

    try:
        row = scan_one_symbol(symbol, PRIMARY_INTERVAL, None, exit_mode=DEFAULT_EXIT_MODE)
    except Exception as exc:
        await query.edit_message_text(f"{symbol}: xato — {exc}")
        return

    if not row.get("HAS_ACTIVE_SETUP"):
        await query.edit_message_text(f"{symbol}: bu orada faol setup tugagan.")
        return

    context.user_data["pending_quickadd"] = {
        "symbol": row["SYMBOL"],
        "entry_price": row["SETUP_ENTRY"],
        "stop_price": row["SETUP_STOP"],
        "target_price": row["SETUP_TARGET"],
        "reason": row["SETUP_REASON"],
        "reference_target_price": row.get("SETUP_REFERENCE_TARGET"),
    }
    await query.edit_message_text(
        f"{format_setup_message(row)}\n\nJurnalga qo'shilsinmi?",
        reply_markup=keyboards.build_confirm_keyboard(row["SYMBOL"]),
    )


@require_allowed_user
async def quickadd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    draft = context.user_data.pop("pending_quickadd", None)
    if draft is None:
        await query.edit_message_text("Bu so'rov eskirgan, qayta /scan qiling.")
        return

    entry, confirmation = _finalize_trade(**draft)
    await query.edit_message_text(f"✅ Savdo qo'shildi (#{entry.entry_id})\n\n{confirmation}")


async def quickadd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_quickadd", None)
    await query.edit_message_text("Bekor qilindi.")


MENU_BUTTON_HANDLERS.update(
    {
        keyboards.BUTTON_SCAN: signals_scan,
        keyboards.BUTTON_STATUS: status,
        keyboards.BUTTON_JOURNAL: journal_command,
        keyboards.BUTTON_STATS: stats_command,
    }
)
