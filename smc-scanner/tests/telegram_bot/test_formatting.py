"""telegram_bot/formatting.py uchun testlar — setup va stats xabarlari to'g'ri formatlanishi."""

from __future__ import annotations

from datetime import date

from journal.types import JournalEntry
from risk.rules import RiskCheckResult
from config.core_watchlist import CoreHolding
from telegram_bot.formatting import (
    HELP_TEXT,
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
