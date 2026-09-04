"""telegram_bot/formatting.py uchun testlar — setup va stats xabarlari to'g'ri formatlanishi."""

from __future__ import annotations

from datetime import date

from journal.types import JournalEntry
from risk.rules import RiskCheckResult
from config.core_watchlist import CoreHolding
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


def _active_setup_row() -> dict:
    return {
        "SYMBOL": "AMD",
        "SETUP_REASON": "FVG",
        "SETUP_ENTRY": 150.0,
        "SETUP_STOP": 140.0,
        "SETUP_TARGET": 175.0,
        "SETUP_RR": 2.5,
        "SETUP_REFERENCE_TARGET": 175.0,
        "SETUP_PLANNED_RR": 2.5,
        "SETUP_LOW_RR_WARNING": False,
        "SETUP_ENTRY_DATE": "2026-08-20",
        "HAS_ACTIVE_SETUP": True,
    }


def test_format_setup_message_contains_key_fields() -> None:
    row = _active_setup_row()

    msg = format_setup_message(row)

    assert "AMD" in msg
    assert "LONG" in msg
    assert "150" in msg  # entry
    assert "140" in msg  # stop
    assert "175" in msg  # target
    assert "2.5" in msg  # R:R
    assert "FVG" in msg
    assert "Paper" in msg or "paper" in msg


def test_format_setup_message_trailing_target_shows_readable_text_not_none() -> None:
    row = _active_setup_row()
    row["SETUP_TARGET"] = None

    msg = format_setup_message(row)

    assert "$None" not in msg
    assert "trailing" in msg.lower()


def test_format_scan_summary_trailing_target_shows_readable_text_not_none() -> None:
    row = _active_setup_row()
    row["SETUP_TARGET"] = None

    msg = format_scan_summary([row])

    assert "$None" not in msg


def _trailing_row_with_reference_target(low_rr: bool = False) -> dict:
    row = _active_setup_row()
    row["SETUP_TARGET"] = None
    row["SETUP_RR"] = "N/A (trailing — maqsad yo'q)"
    row["SETUP_REFERENCE_TARGET"] = 101.0 if low_rr else 175.0
    row["SETUP_PLANNED_RR"] = 1.1 if low_rr else 2.5
    row["SETUP_LOW_RR_WARNING"] = low_rr
    return row


def test_format_setup_message_trailing_shows_reference_target_and_planned_rr() -> None:
    row = _trailing_row_with_reference_target()

    msg = format_setup_message(row)

    assert "$None" not in msg
    assert "Ref.Target" in msg
    assert "175" in msg
    assert "Planned R:R" in msg
    assert "2.5" in msg


def test_format_setup_message_shows_exit_line_and_no_old_na_template() -> None:
    """Eski "R:R: N/A (trailing — maqsad yo'q)" shablon endi ko'rinmasligi kerak —
    Ref.Target/Planned R:R + Exit qatori bilan almashtirildi."""
    row = _trailing_row_with_reference_target()

    msg = format_setup_message(row)

    assert "Exit: trailing stop" in msg
    assert "N/A (trailing" not in msg


def test_format_setup_message_low_rr_warning_shown() -> None:
    row = _trailing_row_with_reference_target(low_rr=True)

    msg = format_setup_message(row)

    assert "⚠️" in msg


def test_format_setup_message_no_warning_when_rr_ok() -> None:
    row = _trailing_row_with_reference_target(low_rr=False)

    msg = format_setup_message(row)

    assert "⚠️ past R:R" not in msg


def test_format_scan_summary_trailing_shows_reference_target() -> None:
    row = _trailing_row_with_reference_target()

    msg = format_scan_summary([row])

    assert "Ref.Target" in msg
    assert "175" in msg


def test_format_add_confirmation_shows_reference_target_when_trailing() -> None:
    risk_result = RiskCheckResult(ok=True, warnings=[])

    msg = format_add_confirmation(
        symbol="AMD", entry_price=150.0, stop_price=140.0, target_price=None,
        reason="FVG", risk_result=risk_result, reference_target_price=175.0,
    )

    assert "Ref.Target" in msg
    assert "175" in msg


def test_format_add_confirmation_no_reference_target_when_fixed() -> None:
    risk_result = RiskCheckResult(ok=True, warnings=[])

    msg = format_add_confirmation(
        symbol="AAPL", entry_price=100.0, stop_price=90.0, target_price=130.0,
        reason="FVG", risk_result=risk_result,
    )

    assert "Ref.Target" not in msg


def test_format_scan_summary_counts_no_setup_symbols() -> None:
    rows = [
        {"SYMBOL": "AAPL", "STRUCTURE_STATE": "BULLISH", "HAS_ACTIVE_SETUP": False, "ERROR": None},
        {"SYMBOL": "MSFT", "STRUCTURE_STATE": "BEARISH", "HAS_ACTIVE_SETUP": False, "ERROR": None},
    ]

    msg = format_scan_summary(rows)

    assert "2 ta belgi tekshirildi" in msg
    assert "Faol setup topilmadi" in msg
    assert "Faol setupsiz: 2 ta" in msg


def test_format_scan_summary_lists_active_setups_with_details() -> None:
    rows = [_active_setup_row(), {"SYMBOL": "AAPL", "HAS_ACTIVE_SETUP": False, "ERROR": None}]

    msg = format_scan_summary(rows)

    assert "AMD" in msg
    assert "150" in msg  # entry
    assert "Faol setup topilgan (1 ta)" in msg
    assert "Faol setupsiz: 1 ta" in msg


def test_format_scan_summary_shows_last_close_and_below_entry_warning() -> None:
    row = _active_setup_row()
    row["LAST_BAR_DATE"] = "2026-08-27"
    row["LAST_CLOSE"] = 141.0  # entry 150 dan past

    msg = format_scan_summary([row])

    assert "Oxirgi close: $141.0 (2026-08-27)" in msg
    assert "narx entry'dan past" in msg


def test_format_scan_summary_lists_invalidated_setups() -> None:
    row = {
        "SYMBOL": "CSGP", "HAS_ACTIVE_SETUP": False, "SETUP_INVALIDATED": True,
        "SETUP_INVALIDATED_REASON": "stop_close", "SETUP_ENTRY": 32.3, "SETUP_STOP": 31.15,
        "SETUP_ENTRY_DATE": "2026-08-20", "LAST_CLOSE": 30.9, "ERROR": None,
    }

    msg = format_scan_summary([row])

    assert "Bekor bo'lgan setup (1 ta)" in msg
    assert "CSGP" in msg
    assert "stop'dan past yopildi" in msg
    assert "Faol setupsiz: 0 ta" in msg  # invalidated "faol setupsiz"ga sanalmaydi


def test_format_scan_summary_lists_missed_setups() -> None:
    """Entry o'tib ketgan (narx entry'dan yuqori) setup asosiy ro'yxatda EMAS,
    alohida "O'tib ketgan" bo'limida."""
    row = {
        "SYMBOL": "TPG", "HAS_ACTIVE_SETUP": False, "SETUP_INVALIDATED": False,
        "SETUP_ENTRY_STATE": "missed", "SETUP_ENTRY": 52.56, "SETUP_STOP": 50.0,
        "SETUP_ENTRY_DATE": "2026-08-20", "LAST_CLOSE": 53.94, "ERROR": None,
    }

    msg = format_scan_summary([row])

    assert "O'tib ketgan" in msg
    assert "TPG" in msg
    assert "Faol setup topilmadi" in msg  # asosiy ro'yxatda emas
    assert "Faol setupsiz: 0 ta" in msg   # missed "faol setupsiz"ga sanalmaydi


def test_format_scan_summary_lists_below_zone_setups() -> None:
    """Narx entry'dan past (lekin stop'dan yuqori) — alohida "Zona ichida" bo'limi."""
    row = {
        "SYMBOL": "CSGP", "HAS_ACTIVE_SETUP": False, "SETUP_INVALIDATED": False,
        "SETUP_ENTRY_STATE": "below", "SETUP_ENTRY": 32.3, "SETUP_STOP": 31.15,
        "SETUP_ENTRY_DATE": "2026-08-20", "LAST_CLOSE": 31.6, "ERROR": None,
    }

    msg = format_scan_summary([row])

    assert "Zona ichida" in msg
    assert "CSGP" in msg
    assert "Faol setup topilmadi" in msg
    assert "Faol setupsiz: 0 ta" in msg


def test_format_scan_summary_separates_all_four_entry_states() -> None:
    active = _active_setup_row()
    active["SYMBOL"] = "AAA"
    missed = {
        "SYMBOL": "TPG", "HAS_ACTIVE_SETUP": False, "SETUP_ENTRY_STATE": "missed",
        "SETUP_ENTRY": 52.5, "SETUP_STOP": 50.0, "SETUP_ENTRY_DATE": "2026-08-20",
        "LAST_CLOSE": 53.9, "ERROR": None,
    }
    below = {
        "SYMBOL": "CSGP", "HAS_ACTIVE_SETUP": False, "SETUP_ENTRY_STATE": "below",
        "SETUP_ENTRY": 32.3, "SETUP_STOP": 31.15, "SETUP_ENTRY_DATE": "2026-08-20",
        "LAST_CLOSE": 31.6, "ERROR": None,
    }
    invalid = {
        "SYMBOL": "DD", "HAS_ACTIVE_SETUP": False, "SETUP_INVALIDATED": True,
        "SETUP_INVALIDATED_REASON": "stop_close", "SETUP_ENTRY": 70.0, "SETUP_STOP": 68.0,
        "SETUP_ENTRY_DATE": "2026-08-20", "LAST_CLOSE": 67.0, "ERROR": None,
    }

    msg = format_scan_summary([active, missed, below, invalid])

    assert "Faol setup topilgan (1 ta)" in msg
    assert "🚂 O'tib ketgan — kirib bo'lmaydi (1 ta)" in msg
    assert "⚠️ Zona ichida — entry'dan past, momentum kuchsiz (1 ta)" in msg
    assert "Bekor bo'lgan setup (1 ta)" in msg
    assert "Faol setupsiz: 0 ta" in msg


def test_format_scan_summary_summarizes_errors() -> None:
    rows = [
        {"SYMBOL": "XXXX", "HAS_ACTIVE_SETUP": False, "ERROR": "bo'sh ma'lumot qaytdi"},
        {"SYMBOL": "AAPL", "HAS_ACTIVE_SETUP": False, "ERROR": None},
    ]

    msg = format_scan_summary(rows)

    assert "⚠️" in msg
    assert "1 ta" in msg
    assert "XXXX" in msg


def test_format_scan_summary_hides_low_rr_setups_by_default() -> None:
    good = _active_setup_row()
    good["SYMBOL"] = "CSGP"
    bad = _trailing_row_with_reference_target(low_rr=True)
    bad["SYMBOL"] = "BADCO"

    msg = format_scan_summary([good, bad])

    assert "CSGP" in msg
    assert "BADCO" not in msg
    assert "Faol setup topilgan (1 ta)" in msg
    assert "1 ta setup past R:R" in msg


def test_format_scan_summary_show_all_includes_low_rr_setups() -> None:
    good = _active_setup_row()
    good["SYMBOL"] = "CSGP"
    bad = _trailing_row_with_reference_target(low_rr=True)
    bad["SYMBOL"] = "BADCO"

    msg = format_scan_summary([good, bad], show_all=True)

    assert "CSGP" in msg
    assert "BADCO" in msg
    assert "Faol setup topilgan (2 ta)" in msg
    assert "sababli yashirildi" not in msg


def test_format_stats_message_contains_all_metrics() -> None:
    stats = {
        "num_entries": 10,
        "num_open": 2,
        "num_closed": 8,
        "avg_rr_planned": 2.5,
        "avg_r_realized": 0.3,
        "win_rate": 0.375,
        "avg_win_r": 1.2,
        "avg_loss_r": -0.8,
        "expectancy_r": 0.05,
        "profit_factor": 1.8,
    }

    msg = format_stats_message(stats)

    assert "10" in msg
    assert "37.5" in msg or "0.375" in msg  # win rate
    assert "2.5" in msg  # avg_rr_planned
    assert "1.8" in msg  # profit_factor
    assert "0.05" in msg  # expectancy_r


def test_format_stats_message_handles_none_profit_factor() -> None:
    stats = {
        "num_entries": 0, "num_open": 0, "num_closed": 0, "avg_rr_planned": None,
        "avg_r_realized": None, "win_rate": 0.0, "avg_win_r": None, "avg_loss_r": None,
        "expectancy_r": 0.0, "profit_factor": None,
    }

    msg = format_stats_message(stats)

    assert "N/A" in msg or "yo'q" in msg.lower()


def test_format_journal_entry_line_shows_symbol_and_prices() -> None:
    entry = JournalEntry(
        entry_id=1, symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0,
        stop_price=90.0, target_price=130.0, exit_mode="fixed", reason="FVG",
        rr_planned=3.0,
    )

    line = format_journal_entry_line(entry)

    assert "AAPL" in line
    assert "100" in line
    assert "90" in line


def test_format_add_confirmation_includes_risk_warning_when_breached() -> None:
    risk_result = RiskCheckResult(ok=False, warnings=["Ochiq pozitsiya soni (4) limitdan (3) oshib ketdi."])

    msg = format_add_confirmation(
        symbol="AAPL", entry_price=100.0, stop_price=90.0, target_price=130.0,
        reason="FVG", risk_result=risk_result,
    )

    assert "AAPL" in msg
    assert "⚠️" in msg
    assert "ochiq pozitsiya" in msg.lower()


def test_format_add_confirmation_no_warning_when_ok() -> None:
    risk_result = RiskCheckResult(ok=True, warnings=[])

    msg = format_add_confirmation(
        symbol="AAPL", entry_price=100.0, stop_price=90.0, target_price=130.0,
        reason="FVG", risk_result=risk_result,
    )

    assert "AAPL" in msg
    assert "⚠️" not in msg


def test_format_watchlist_message_lists_tickers() -> None:
    holdings = [
        CoreHolding("SPUS", "SP Funds S&P 500", "etf", "ETF holdings", None),
        CoreHolding("AAPL", "Apple Inc.", "stock", "TEKSHIRILISHI KERAK", None),
    ]

    msg = format_watchlist_message(holdings)

    assert "SPUS" in msg
    assert "AAPL" in msg


def test_format_watchlist_message_empty_shows_hint() -> None:
    msg = format_watchlist_message([])

    assert "bo'sh" in msg.lower()
    assert "/watchadd" in msg


def test_format_watchlist_message_large_list_stays_under_telegram_limit() -> None:
    holdings = [
        CoreHolding(f"SYM{i}", f"Company {i}", "stock", "TEKSHIRILISHI KERAK", None)
        for i in range(250)
    ]

    msg = format_watchlist_message(holdings)

    assert len(msg) <= 4096
    assert "250 ta belgi" in msg
    assert "SYM0" in msg
    assert "/watchremove" in msg


def test_help_text_mentions_paper_disclaimer() -> None:
    assert "paper" in HELP_TEXT.lower()
    assert "/scan" in HELP_TEXT
    assert "/add" in HELP_TEXT


def test_help_text_is_valid_legacy_markdown() -> None:
    """HELP_TEXT parse_mode="Markdown" bilan yuboriladi (handlers.start). Juftlanmagan
    `_`/`*` bo'lsa Telegram butun xabarni rad etadi va /start, /help hamda "❓ Yordam"
    tugmasi jimgina ishlamay qoladi — shu regressiyani ushlab turadi."""
    unescaped_underscores = HELP_TEXT.replace("\\_", "").count("_")
    unescaped_asterisks = HELP_TEXT.replace("\\*", "").count("*")
    assert unescaped_underscores % 2 == 0, "juftlanmagan `_` — legacy Markdown yiqiladi"
    assert unescaped_asterisks % 2 == 0, "juftlanmagan `*` — legacy Markdown yiqiladi"


# ======================================================================
# chunk_signal_messages — signals/swing kartalarini 4096-xavfsiz guruhlash
# ======================================================================


def test_chunk_signal_messages_empty_input() -> None:
    assert chunk_signal_messages([]) == []


def test_chunk_signal_messages_packs_multiple_short_cards_into_one_message() -> None:
    cards = ["karta A", "karta B", "karta C"]
    result = chunk_signal_messages(cards, max_length=4096)
    assert len(result) == 1
    assert "karta A" in result[0]
    assert "karta B" in result[0]
    assert "karta C" in result[0]


def test_chunk_signal_messages_splits_when_next_card_would_exceed_limit() -> None:
    # Har karta 30 belgi, max_length=50 -> bitta xabarga faqat 1 ta karta sig'adi
    # (30 + "\n\n"(2) + 30 = 62 > 50).
    cards = ["A" * 30, "B" * 30, "C" * 30]
    result = chunk_signal_messages(cards, max_length=50)

    assert len(result) == 3
    for message in result:
        assert len(message) <= 50
    # Hech biri yo'qolmagan/takrorlanmagan.
    joined = "".join(result)
    assert joined.count("A") == 30
    assert joined.count("B") == 30
    assert joined.count("C") == 30


def test_chunk_signal_messages_hard_splits_a_single_oversized_card() -> None:
    oversized = "X" * 130
    result = chunk_signal_messages([oversized], max_length=50)

    assert len(result) == 3  # 130 = 50 + 50 + 30
    for message in result:
        assert len(message) <= 50
    assert "".join(result) == oversized
