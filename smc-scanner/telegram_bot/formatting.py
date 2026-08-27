"""Telegram javoblarini o'zbek tilida, emoji/Markdown bilan formatlash.

Bu modul faqat MATN yasaydi — hisoblash yoki I/O yo'q (ma'lumot tactical_scan/journal/risk'dan
allaqachon tayyor holda keladi). CLI'ning scripts/tactical_scan.py::format_scan_block'dan
ATAYLAB alohida: taqdimot kanali (Telegram emoji/Markdown vs. terminal oddiy matn) farq qiladi,
lekin ma'lumot manbai (run_scan/build_scan_row) bitta — u yerda takrorlanmaydi. Istisno:
filter_quality_setups() — sof filtrlash (I/O'siz), CLI va bot BIR XIL sifat-filtr siyosatini
qo'llashi uchun tactical_scan.py'dan import qilinadi (takrorlanmasin).
"""

from __future__ import annotations

from config.settings import MIN_PLANNED_RR, WATCHLIST_COMPACT_THRESHOLD
from journal.types import JournalEntry
from risk.rules import RiskCheckResult
from scripts.tactical_scan import filter_quality_setups

PAPER_DISCLAIMER = (
    "⚠️ Bu paper/o'quv qatlami. Signallar buy&hold'dan past return beradi. "
    "Savdoga kirish/chiqish bu botda emas — TradingView (yoki boshqa) platformada qiling."
)

HELP_TEXT = (
    "🤖 *Halal SMC Swing Scanner — buyruqlar*\n\n"
    "/scan [SYMBOLS] — watchlist yoki berilgan ticker(lar)ni skan qiladi (past R:R yashirilgan)\n"
    "/scan_all [SYMBOLS] — /scan kabi, lekin past R:R setup'larni ham ko'rsatadi\n"
    "/status — ochiq savdolar + ochiq pozitsiyalar holati\n"
    "/add — yangi savdo qo'shish (interaktiv)\n"
    "/close — ochiq savdoni yopish\n"
    "/journal [N] — oxirgi N savdo (default 10)\n"
    "/stats — win rate, expectancy, R:R, profit factor\n"
    "/watchlist — taktik watchlist\n"
    "/watchadd — watchlistga yangi aksiya/ETF qo'shish (interaktiv)\n"
    "/watchremove TICKER — watchlistdan belgi o'chirish\n"
    "/menu — pastki menyuni qayta ko'rsatish\n\n"
    f"{PAPER_DISCLAIMER}"
)


def _format_reference_rr_line(row: dict) -> str:
    """"Ref.Target | Planned R:R" qatori — fixed va trailing ikkalasida ham bir xil
    manbadan (SETUP_REFERENCE_TARGET/SETUP_PLANNED_RR, tactical_scan.py::build_scan_row
    hisoblagan). Signal umuman topilmagan yoki risk<=0 chekka holatlarida "N/A" o'rniga
    qisqa sababi ko'rsatiladi."""
    ref_target = row.get("SETUP_REFERENCE_TARGET")
    if ref_target is None:
        return "Ref.Target: N/A (signal topilmadi)"
    planned_rr = row.get("SETUP_PLANNED_RR")
    rr_text = f"{planned_rr}" if planned_rr is not None else "N/A (risk<=0)"
    return f"Ref.Target: ${ref_target} | Planned R:R: {rr_text}"


def _format_exit_line(row: dict) -> str:
    """Haqiqiy chiqish qanday bo'lishini aniq ko'rsatadi — Ref.Target FAQAT baholash
    uchun, chalkashtirmaslik uchun har doim eslatiladi."""
    if row["SETUP_TARGET"] is None:
        return "Exit: trailing stop (real chiqish trailing bilan)"
    return f"Exit: fixed target ${row['SETUP_TARGET']}"


def format_setup_message(row: dict) -> str:
    """Faol setup uchun to'liq xabar — kirish/chiqish narxlari, faqat AXBOROT
    uchun. Savdoning o'zi TradingView'da (yoki boshqa platformada) qilinadi."""
    lines = [
        f"📊 {row['SYMBOL']} — LONG setup",
        f"Entry: ${row['SETUP_ENTRY']} | Stop: ${row['SETUP_STOP']}",
        _format_reference_rr_line(row),
    ]
    if row.get("SETUP_LOW_RR_WARNING"):
        lines.append("⚠️ Past R:R — ehtiyot")
    lines.append(f"Sabab: {row['SETUP_REASON']} zonasi {row['SETUP_ENTRY_DATE']}'da retest qilindi")
    lines.append(_format_exit_line(row))
    lines.append(PAPER_DISCLAIMER)
    return "\n".join(lines)


def format_scan_summary(
    rows: list[dict], *, min_rr: float = MIN_PLANNED_RR, show_all: bool = False,
) -> str:
    """/scan uchun BITTA yakuniy xabar — har belgi alohida xabar EMAS. Sifatli
    (planned_rr >= min_rr) faol setup'lar to'liq ko'rsatiladi (harakat kerak),
    past R:R setup'lar default holatda YASHIRILADI (soni alohida qatorda —
    show_all=True bilan hammasi ko'rinadi), setup yo'q belgilar shunchaki
    sonda hisoblanadi (ro'yxati emas — katta watchlist'da matn hajmi cheksiz
    o'smasin), xatolar qisqa qatorga yig'iladi."""
    errors = [r for r in rows if r.get("ERROR")]
    visible, hidden = filter_quality_setups(rows, min_rr=min_rr, show_all=show_all)
    active_total = len([r for r in rows if r.get("HAS_ACTIVE_SETUP")])
    no_setup_count = len(rows) - active_total - len(errors)

    lines = [f"✅ Skanerlash yakunlandi: {len(rows)} ta belgi tekshirildi."]

    if visible:
        lines.append("")
        lines.append(f"📊 Faol setup topilgan ({len(visible)} ta):")
        for row in visible:
            lines.append("")
            lines.append(f"{row['SYMBOL']} — LONG")
            lines.append(f"Entry: ${row['SETUP_ENTRY']} | Stop: ${row['SETUP_STOP']}")
            lines.append(_format_reference_rr_line(row))
            if row.get("SETUP_LOW_RR_WARNING"):
                lines.append("⚠️ Past R:R — ehtiyot")
            lines.append(f"Sabab: {row['SETUP_REASON']} zonasi {row['SETUP_ENTRY_DATE']}'da retest qilindi")
            lines.append(_format_exit_line(row))
    else:
        lines.append("")
        lines.append("Faol setup topilmadi.")

    lines.append("")
    lines.append(f"Faol setupsiz: {no_setup_count} ta")
    if hidden:
        lines.append(f"🔒 {len(hidden)} ta setup past R:R (< {min_rr}) sababli yashirildi.")
    if errors:
        symbols = ", ".join(r["SYMBOL"] for r in errors[:10])
        more = f" (+{len(errors) - 10} yana)" if len(errors) > 10 else ""
        lines.append(f"⚠️ Xato: {len(errors)} ta ({symbols}{more})")

    lines.append("")
    lines.append(PAPER_DISCLAIMER)
    return "\n".join(lines)


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


def format_add_confirmation(
    *,
    symbol: str,
    entry_price: float,
    stop_price: float,
    target_price: float | None,
    reason: str,
    risk_result: RiskCheckResult,
    reference_target_price: float | None = None,
) -> str:
    """/add oqimida savdoni saqlashdan oldin ko'rsatiladigan tasdiqlash xabari."""
    lines = [
        f"📊 {symbol} — LONG",
        f"Entry: ${entry_price} | Stop: ${stop_price} | Target: {f'${target_price}' if target_price else 'yoʻq'}",
        f"Sabab: {reason}",
    ]
    if target_price is None and reference_target_price is not None:
        risk = entry_price - stop_price
        planned_rr = round((reference_target_price - entry_price) / risk, 2) if risk > 0 else None
        rr_text = f" | Planned R:R: {planned_rr}" if planned_rr is not None else ""
        lines.append(f"Ref.Target (trailing, statik): ${reference_target_price}{rr_text}")
    if not risk_result.ok:
        lines.append("")
        for warning in risk_result.warnings:
            lines.append(f"⚠️ {warning}")
    return "\n".join(lines)


def format_watchlist_message(holdings: list) -> str:
    """/watchlist uchun CORE_WATCHLIST'ni ko'rsatish.

    WATCHLIST_COMPACT_THRESHOLD'dan ko'p yozuv bo'lsa (masalan ETF'ning butun
    portfeli import qilingan bo'lsa — 200+ belgi), har biri uchun to'liq
    nom/toifa qatori o'rniga faqat ticker'lar ro'yxati ko'rsatiladi — aks holda
    xabar Telegram'ning 4096 belgili limitidan oshib ketadi."""
    if not holdings:
        return "📋 *Taktik watchlist*\n\nWatchlist bo'sh. Qo'shish: /watchadd"

    if len(holdings) > WATCHLIST_COMPACT_THRESHOLD:
        lines = [f"📋 *Taktik watchlist* — {len(holdings)} ta belgi"]
        lines.append("")
        tickers = [h.ticker for h in holdings]
        for i in range(0, len(tickers), 10):
            lines.append(", ".join(tickers[i : i + 10]))
        lines.append("")
        lines.append("Bitta belgini o'chirish: /watchremove TICKER. Qo'shish: /watchadd")
        return "\n".join(lines)

    lines = ["📋 *Taktik watchlist*"]
    for h in holdings:
        lines.append(f"{h.ticker} — {h.name} ({h.category})")
    lines.append("")
    lines.append("O'chirish uchun pastdagi 🗑 tugmani bosing. Qo'shish: /watchadd")
    return "\n".join(lines)
