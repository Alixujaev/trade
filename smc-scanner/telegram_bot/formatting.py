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
from scripts.tactical_scan import (
    ENTRY_STATE_BELOW,
    ENTRY_STATE_MISSED,
    filter_quality_setups,
    invalidation_text,
)

PAPER_DISCLAIMER = (
    "⚠️ Bu paper/o'quv qatlami. Signallar buy&hold'dan past return beradi. "
    "Savdoga kirish/chiqish bu botda emas — TradingView (yoki boshqa) platformada qiling."
)

HELP_TEXT = (
    "🤖 *Halal SMC Swing Scanner — buyruqlar*\n\n"
    "/scan [SYMBOLS] — watchlist yoki berilgan ticker(lar)ni skan qiladi (past R:R yashirilgan)\n"
    # `_` legacy Markdown'da kursiv boshlaydi — juftlanmagan `_` butun xabarni
    # "Can't parse entities" bilan yiqitadi (start/help/❓ tugma hammasi jim qoladi).
    "/scan\\_all [SYMBOLS] — /scan kabi, lekin past R:R setup'larni ham ko'rsatadi\n"
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
    dedup_new: list[dict] | None = None, dedup_skipped_count: int = 0,
) -> str:
    """/scan uchun BITTA yakuniy xabar — har belgi alohida xabar EMAS. Sifatli
    (planned_rr >= min_rr) faol setup'lar to'liq ko'rsatiladi (harakat kerak),
    past R:R setup'lar default holatda YASHIRILADI (soni alohida qatorda —
    show_all=True bilan hammasi ko'rinadi), setup yo'q belgilar shunchaki
    sonda hisoblanadi (ro'yxati emas — katta watchlist'da matn hajmi cheksiz
    o'smasin), xatolar qisqa qatorga yig'iladi.

    dedup_new/dedup_skipped_count — ixtiyoriy (TZ 18): handler dedup+cooldown
    (signals/dedup.py) qo'llagandan keyin beradi. dedup_new = sifat-filtrdan
    o'tgan setup'lar ichidan YANGI (cooldown o'tgan yoki birinchi marta ko'rilgan)
    bo'lganlari — shular ko'rsatiladi/tugmaga chiqadi, qolganlari (dedup_skipped_count)
    faqat sonda hisoblanadi. dedup_new=None (default) — ESKI xatti-harakat: bu
    funksiya o'zi dedup HAQIDA HECH NARSA bilmaydi, filter_quality_setups
    natijasi to'liq ko'rsatiladi (CLI va eski chaqiruvlar uchun backward-compat)."""
    errors = [r for r in rows if r.get("ERROR")]
    visible, hidden = filter_quality_setups(rows, min_rr=min_rr, show_all=show_all)
    shown = visible if dedup_new is None else dedup_new
    active_total = len([r for r in rows if r.get("HAS_ACTIVE_SETUP")])
    invalidated = [r for r in rows if r.get("SETUP_INVALIDATED")]
    missed = [r for r in rows if r.get("SETUP_ENTRY_STATE") == ENTRY_STATE_MISSED]
    below = [r for r in rows if r.get("SETUP_ENTRY_STATE") == ENTRY_STATE_BELOW]
    no_setup_count = (
        len(rows) - active_total - len(errors) - len(invalidated) - len(missed) - len(below)
    )

    lines = [f"✅ Skanerlash yakunlandi: {len(rows)} ta belgi tekshirildi."]

    if shown:
        lines.append("")
        lines.append(f"📊 Faol setup topilgan ({len(shown)} ta):")
        for row in shown:
            lines.append("")
            lines.append(f"{row['SYMBOL']} — LONG")
            lines.append(f"Entry: ${row['SETUP_ENTRY']} | Stop: ${row['SETUP_STOP']}")
            lines.append(_format_reference_rr_line(row))
            last_close = row.get("LAST_CLOSE")
            if last_close is not None:
                note = " ⚠️ narx entry'dan past" if (
                    row.get("SETUP_ENTRY") is not None and last_close < row["SETUP_ENTRY"]
                ) else ""
                lines.append(f"Oxirgi close: ${last_close} ({row.get('LAST_BAR_DATE')}){note}")
            if row.get("SETUP_LOW_RR_WARNING"):
                lines.append("⚠️ Past R:R — ehtiyot")
            lines.append(f"Sabab: {row['SETUP_REASON']} zonasi {row['SETUP_ENTRY_DATE']}'da retest qilindi")
            lines.append(_format_exit_line(row))
    elif dedup_new is not None and visible:
        lines.append("")
        lines.append("Yangi faol setup yo'q — barchasi oldin yuborilgan (cooldown ichida).")
    else:
        lines.append("")
        lines.append("Faol setup topilmadi.")

    if missed:
        lines.append("")
        lines.append(f"🚂 O'tib ketgan — kirib bo'lmaydi ({len(missed)} ta):")
        for row in missed:
            close_part = (
                f", oxirgi close ${row['LAST_CLOSE']}" if row.get("LAST_CLOSE") is not None else ""
            )
            lines.append(
                f"{row['SYMBOL']} — narx entry ${row.get('SETUP_ENTRY')}'dan yuqori"
                f"{close_part} ({row.get('SETUP_ENTRY_DATE')})"
            )

    if below:
        lines.append("")
        lines.append(f"⚠️ Zona ichida — entry'dan past, momentum kuchsiz ({len(below)} ta):")
        for row in below:
            close_part = (
                f", oxirgi close ${row['LAST_CLOSE']}" if row.get("LAST_CLOSE") is not None else ""
            )
            lines.append(
                f"{row['SYMBOL']} — entry ${row.get('SETUP_ENTRY')}, stop ${row.get('SETUP_STOP')}"
                f"{close_part} ({row.get('SETUP_ENTRY_DATE')})"
            )

    if invalidated:
        lines.append("")
        lines.append(f"❌ Bekor bo'lgan setup ({len(invalidated)} ta):")
        for row in invalidated:
            close_part = f", oxirgi close ${row['LAST_CLOSE']}" if row.get("LAST_CLOSE") is not None else ""
            lines.append(
                f"{row['SYMBOL']} — {invalidation_text(row)} "
                f"(entry ${row['SETUP_ENTRY']}, stop ${row['SETUP_STOP']}{close_part}, {row['SETUP_ENTRY_DATE']})"
            )

    lines.append("")
    lines.append(f"Faol setupsiz: {no_setup_count} ta")
    if hidden:
        lines.append(f"🔒 {len(hidden)} ta setup past R:R (< {min_rr}) sababli yashirildi.")
    if dedup_new is not None:
        lines.append(
            f"🔁 Dedup: {len(visible)} ta topildi, {len(shown)} ta yangi yuborildi, "
            f"{dedup_skipped_count} ta oldin yuborilgani uchun o'tkazib yuborildi."
        )
    if errors:
        symbols = ", ".join(r["SYMBOL"] for r in errors[:10])
        more = f" (+{len(errors) - 10} yana)" if len(errors) > 10 else ""
        lines.append(f"⚠️ Xato: {len(errors)} ta ({symbols}{more})")

    lines.append("")
    lines.append(PAPER_DISCLAIMER)
    return "\n".join(lines)


def format_stats_message(stats: dict) -> str:
    """journal.stats() dict'ini o'qiladigan xabarga aylantiradi.

    `stats["benchmark"]` mavjud bo'lsa (journal.TradeJournal.stats(include_benchmark=True)
    bilan chaqirilgan) — uchta ALOHIDA bo'lim ko'rsatiladi: discretionary (mavjud, R
    birligida) | buy&hold (price-return %, journal/benchmark.py) | comparison (raqam,
    xulossiz). R va buy&hold % HECH QACHON bitta qatorga aralashtirilmaydi — framing
    "discretionary performance vs market benchmark", "robot g'olib/mag'lub" EMAS."""
    profit_factor = f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "N/A"
    avg_rr_planned = f"{stats['avg_rr_planned']:.2f}" if stats["avg_rr_planned"] is not None else "N/A"

    lines = [
        "📈 *Statistika*",
        f"Jami: {stats['num_entries']} (ochiq: {stats['num_open']}, yopiq: {stats['num_closed']})",
        f"Win rate: {stats['win_rate'] * 100:.1f}%",
        f"O'rtacha rejalashtirilgan R:R: {avg_rr_planned}",
        f"Expectancy: {stats['expectancy_r']:.2f}R",
        f"Profit factor: {profit_factor}",
    ]

    benchmark = stats.get("benchmark")
    if benchmark is not None:
        lines.append("")
        lines.append("📊 *Buy&hold benchmark* (discretionary performance vs market benchmark)")
        if benchmark["num_benchmarked"] > 0:
            lines.append(
                f"O'rtacha buy&hold return: {benchmark['avg_benchmark_return_pct']:.2f}% "
                f"({benchmark['num_benchmarked']} ta savdo, same-window: entry->exit sana)"
            )
        else:
            lines.append("Buy&hold hisoblab bo'lmadi (ma'lumot yo'q).")
        if benchmark["num_benchmark_skipped"]:
            lines.append(
                f"O'tkazib yuborildi (narx ma'lumoti yo'q): {benchmark['num_benchmark_skipped']} ta"
            )

        lines.append("")
        lines.append("🔍 *Solishtirish* (raqam, xulosa emas)")
        lines.append(f"Buy&hold musbat bo'lgan savdolar: {benchmark['benchmark_positive_count']}")
        lines.append(
            "Discretionary buy&hold'dan yaxshiroq (price-return bo'yicha, R emas): "
            f"{benchmark['discretionary_outperformed_count']}"
        )

    return "\n".join(lines)


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


# ======================================================================
# /signals, /swing — setup kartalarini xavfsiz Telegram xabarlariga guruhlash
# ======================================================================

TELEGRAM_MESSAGE_LIMIT = 4096  # Telegram platforma qattiq limiti (bitta xabar uchun)


def chunk_signal_messages(cards: list[str], *, max_length: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """`format_payload` natijalarini (bitta setup = bitta karta) xavfsiz Telegram
    xabarlariga guruhlaydi — hech bir chiquvchi xabar `max_length`dan oshmaydi.

    Kartalar bo'sh qatordan ("\n\n") ajratilib bir xabarga sig'gancha guruhlanadi;
    keyingi karta sig'masa yangi xabar boshlanadi. Bitta kartaning O'ZI limitdan katta
    bo'lib qolsa (nazariy holat — payload formatining o'zi HECH QACHON o'zgartirilmaydi,
    faqat qanday guruhlanishi boshqariladi) — xavfsizlik uchun qattiq bo'laklanadi.
    """
    if not cards:
        return []

    messages: list[str] = []
    current: list[str] = []
    current_len = 0

    for card in cards:
        if len(card) > max_length:
            if current:
                messages.append("\n\n".join(current))
                current, current_len = [], 0
            for i in range(0, len(card), max_length):
                messages.append(card[i : i + max_length])
            continue

        piece_len = len(card) if not current else len(card) + 2  # +2 == "\n\n" ajratuvchi
        if current and current_len + piece_len > max_length:
            messages.append("\n\n".join(current))
            current, current_len = [], 0
            piece_len = len(card)

        current.append(card)
        current_len += piece_len

    if current:
        messages.append("\n\n".join(current))

    return messages
