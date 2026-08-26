"""Telegram javoblarini o'zbek tilida, emoji/Markdown bilan formatlash.

Bu modul faqat MATN yasaydi — hisoblash yoki I/O yo'q (ma'lumot tactical_scan/journal/risk'dan
allaqachon tayyor holda keladi). CLI'ning scripts/tactical_scan.py::format_scan_block'dan
ATAYLAB alohida: taqdimot kanali (Telegram emoji/Markdown vs. terminal oddiy matn) farq qiladi,
lekin ma'lumot manbai (run_scan/build_scan_row) bitta — u yerda takrorlanmaydi.
"""

from __future__ import annotations

from journal.types import JournalEntry
from risk.position_sizing import PositionSize
from risk.rules import RiskCheckResult

PAPER_DISCLAIMER = (
    "⚠️ Bu paper/o'quv qatlami. Signallar buy&hold'dan past return beradi. Real kapital emas."
)

HELP_TEXT = (
    "🤖 *Halal SMC Swing Scanner — buyruqlar*\n\n"
    "/scan [SYMBOLS] — watchlist yoki berilgan ticker(lar)ni skan qiladi\n"
    "/status — ochiq savdolar + bugungi risk holati\n"
    "/add — yangi savdo qo'shish (interaktiv)\n"
    "/close — ochiq savdoni yopish\n"
    "/journal [N] — oxirgi N savdo (default 10)\n"
    "/stats — win rate, expectancy, R:R, profit factor\n"
    "/watchlist — taktik watchlist\n"
    "/capital [SUMMA] — paper kapitalni ko'rish/o'rnatish\n\n"
    f"{PAPER_DISCLAIMER}"
)


def format_setup_message(row: dict, sizing: PositionSize) -> str:
    """Faol setup uchun to'liq xabar — spec namunasidagi formatga mos."""
    lines = [
        f"📊 {row['SYMBOL']} — LONG setup",
        f"Entry: ${row['SETUP_ENTRY']} | Stop: ${row['SETUP_STOP']} | Target: ${row['SETUP_TARGET']}",
        f"R:R: {row['SETUP_RR']} | Shares: {sizing.shares} | Risk: ${sizing.risk_dollars:.2f} "
        f"({sizing.risk_pct * 100:.0f}%)",
        f"Sabab: {row['SETUP_REASON']} zonasi {row['SETUP_ENTRY_DATE']}'da retest qilindi",
        PAPER_DISCLAIMER,
    ]
    return "\n".join(lines)


def format_no_setup_line(row: dict) -> str:
    """Faol setup yo'q symbol uchun qisqa holat qatori."""
    return f"{row['SYMBOL']}: faol setup yo'q (joriy struktura: {row['STRUCTURE_STATE']})"


def format_stats_message(stats: dict) -> str:
    """journal.stats() dict'ini o'qiladigan xabarga aylantiradi."""
    profit_factor = f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "N/A"
    avg_rr_planned = f"{stats['avg_rr_planned']:.2f}" if stats["avg_rr_planned"] is not None else "N/A"

    return (
        "📈 *Statistika*\n"
        f"Jami: {stats['num_entries']} (ochiq: {stats['num_open']}, yopiq: {stats['num_closed']})\n"
        f"Win rate: {stats['win_rate'] * 100:.1f}%\n"
        f"O'rtacha rejalashtirilgan R:R: {avg_rr_planned}\n"
        f"Expectancy: {stats['expectancy_r']:.2f}R\n"
        f"Profit factor: {profit_factor}"
    )


def format_journal_entry_line(entry: JournalEntry) -> str:
    """/journal va /status uchun bitta yozuv qatori."""
    status = "OCHIQ" if entry.exit_price is None else f"YOPILDI (R={entry.r_multiple:.2f})"
    return f"#{entry.entry_id} {entry.symbol}: entry ${entry.entry_price} / stop ${entry.stop_price} — {status}"


def format_capital_message(capital: float) -> str:
    """/capital uchun joriy kapitalni ko'rsatish."""
    return f"💰 Joriy paper kapital: ${capital:,.2f}"


def format_add_confirmation(
    *,
    symbol: str,
    entry_price: float,
    stop_price: float,
    target_price: float | None,
    reason: str,
    sizing: PositionSize,
    risk_result: RiskCheckResult,
) -> str:
    """/add oqimida savdoni saqlashdan oldin ko'rsatiladigan tasdiqlash xabari."""
    lines = [
        f"📊 {symbol} — LONG",
        f"Entry: ${entry_price} | Stop: ${stop_price} | Target: {f'${target_price}' if target_price else 'yoʻq'}",
        f"Shares: {sizing.shares} | Risk: ${sizing.risk_dollars:.2f} ({sizing.risk_pct * 100:.0f}%)",
        f"Sabab: {reason}",
    ]
    if not risk_result.ok:
        lines.append("")
        for warning in risk_result.warnings:
            lines.append(f"⚠️ {warning}")
    return "\n".join(lines)


def format_watchlist_message(holdings: list) -> str:
    """/watchlist uchun CORE_WATCHLIST'ni ko'rsatish."""
    lines = ["📋 *Taktik watchlist*"]
    for h in holdings:
        lines.append(f"{h.ticker} — {h.name} ({h.category})")
    return "\n".join(lines)
