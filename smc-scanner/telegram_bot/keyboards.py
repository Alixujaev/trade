"""Barcha reply/inline keyboard va callback_data formatlarini markazlashtiradi.

Bu modul faqat MARKUP quradi — matn yasamaydi (formatting.py'ning ishi) va
hech qanday biznes-mantiq/I/O chaqirmaydi (handlers.py'ning ishi)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from config.core_watchlist import CoreHolding
from journal.types import JournalEntry
from signals.payload import SignalPayload
from smc.types import StructureState

BUTTON_SCAN = "🔍 Skanerlash"
BUTTON_STATUS = "📂 Holat"
BUTTON_JOURNAL = "📒 Jurnal"
BUTTON_STATS = "📈 Statistika"

# Watchlist va Yordam menyu tugmasi sifatida YO'Q (menyuni ixcham saqlash uchun) —
# lekin buyruq sifatida hamon ishlaydi: /watchlist, /watchadd, /watchremove, /help.
MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BUTTON_SCAN, BUTTON_STATUS],
        [BUTTON_JOURNAL, BUTTON_STATS],
    ],
    resize_keyboard=True,
)

CANCEL_CALLBACK_DATA = "convcancel"
CONFIRM_CALLBACK_DATA = "addconfirm"
DISCARD_CALLBACK_DATA = "addcancel"


def _tradingview_url(symbol: str) -> str:
    return f"https://www.tradingview.com/chart/?symbol={symbol}"


def _tradingview_button(symbol: str) -> InlineKeyboardButton:
    """Savdoni bevosita botda emas, TradingView'da (paper trading) amalga
    oshirish uchun grafikka o'tish tugmasi."""
    return InlineKeyboardButton("📈 TradingView'da ochish", url=_tradingview_url(symbol))


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    """Conversation davomidagi matn-so'rovlarga qo'shiladigan bekor qilish tugmasi."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data=CANCEL_CALLBACK_DATA)]]
    )


def build_scan_summary_keyboard(rows: list[dict]) -> InlineKeyboardMarkup | None:
    """/scan'ning YAKUNIY (yagona) xabariga qo'shiladigan tugmalar — har faol
    setup uchun bitta qator: jurnalga tezkor qo'shish + TradingView havolasi.
    Faol setup bo'lmasa None (reply_markup shart emas)."""
    active_symbols = [row["SYMBOL"] for row in rows if row.get("HAS_ACTIVE_SETUP")]
    if not active_symbols:
        return None
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"➕ {symbol}", callback_data=f"add:{symbol}"), _tradingview_button(symbol)]
            for symbol in active_symbols
        ]
    )


def build_signals_summary_keyboard(payloads: list[SignalPayload]) -> InlineKeyboardMarkup | None:
    """/signals'ning YAKUNIY xabariga qo'shiladigan tugmalar — har BULLISH (yangi LONG
    kuzatuv kandidati) setup uchun bitta qator: jurnalga tezkor qo'shish (snapshot
    bilan, TZ) + TradingView havolasi. Bearish (AVOID/EXIT candidate) payload'lar
    uchun tugma YO'Q — bot short taklif qilmaydi (signals/payload.py tamoyili),
    "jurnalga qo'shish" faqat yangi LONG kuzatuvi uchun ma'noli. Bullish setup
    bo'lmasa None (`build_scan_summary_keyboard`ning /signals varianti)."""
    bullish_symbols = [p.symbol for p in payloads if p.direction is StructureState.BULLISH]
    if not bullish_symbols:
        return None
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"➕ {symbol}", callback_data=f"sigadd:{symbol}"), _tradingview_button(symbol)]
            for symbol in bullish_symbols
        ]
    )


def build_confirm_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """Tezkor-qo'shish oldidan ko'rsatiladigan grafik havolasi + tasdiqlash/bekor
    qilish tugmalari."""
    return InlineKeyboardMarkup(
        [
            [_tradingview_button(symbol)],
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=CONFIRM_CALLBACK_DATA),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=DISCARD_CALLBACK_DATA),
            ],
        ]
    )


def build_status_close_keyboard(open_entries: list[JournalEntry]) -> InlineKeyboardMarkup:
    """/status'dagi har ochiq savdo uchun to'g'ridan-to'g'ri yopish tugmasi + TradingView havolasi."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"Yopish #{e.entry_id} {e.symbol}", callback_data=f"close:{e.entry_id}"),
                _tradingview_button(e.symbol),
            ]
            for e in open_entries
        ]
    )


def build_close_select_keyboard(open_entries: list[JournalEntry]) -> InlineKeyboardMarkup:
    """/close boshlanganda ochiq savdolardan birini tanlash uchun tugmalar."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"#{e.entry_id} {e.symbol}", callback_data=str(e.entry_id))]
            for e in open_entries
        ]
    )


def build_category_keyboard() -> InlineKeyboardMarkup:
    """/watchadd oqimida stock/etf toifasini bosib tanlash uchun tugmalar."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📈 Stock", callback_data="watchcat:stock"),
                InlineKeyboardButton("📊 ETF", callback_data="watchcat:etf"),
            ]
        ]
    )


def build_watchlist_remove_keyboard(holdings: list[CoreHolding]) -> InlineKeyboardMarkup:
    """/watchlist'dagi har holding uchun to'g'ridan-to'g'ri o'chirish tugmasi."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🗑 {h.ticker}", callback_data=f"watchremove:{h.ticker}")] for h in holdings]
    )


def build_watchremove_confirm_keyboard(ticker: str) -> InlineKeyboardMarkup:
    """Watchlist'dan o'chirishdan oldin tasdiqlash/bekor qilish tugmalari."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ O'chirish", callback_data=f"watchremoveconfirm:{ticker}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="watchremovecancel"),
            ]
        ]
    )
