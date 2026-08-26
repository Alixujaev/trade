"""telegram_bot/formatting.py uchun testlar — setup va stats xabarlari to'g'ri formatlanishi."""

from __future__ import annotations

from datetime import date

from journal.types import JournalEntry
from risk.position_sizing import PositionSize
from risk.rules import RiskCheckResult
from config.core_watchlist import CoreHolding
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


def _active_setup_row() -> dict:
    return {
        "SYMBOL": "AMD",
        "SETUP_REASON": "FVG",
        "SETUP_ENTRY": 150.0,
        "SETUP_STOP": 140.0,
        "SETUP_TARGET": 175.0,
        "SETUP_RR": 2.5,
        "SETUP_ENTRY_DATE": "2026-08-20",
        "HAS_ACTIVE_SETUP": True,
    }


def test_format_setup_message_contains_key_fields() -> None:
    row = _active_setup_row()
    sizing = PositionSize(shares=12, risk_dollars=120.0, risk_pct=0.01)

    msg = format_setup_message(row, sizing)

    assert "AMD" in msg
    assert "LONG" in msg
    assert "150" in msg  # entry
    assert "140" in msg  # stop
    assert "175" in msg  # target
    assert "2.5" in msg  # R:R
    assert "12" in msg  # shares
    assert "120" in msg  # risk $
    assert "FVG" in msg
    assert "Paper" in msg or "paper" in msg


def test_format_no_setup_line_shows_symbol_and_structure() -> None:
    row = {"SYMBOL": "AAPL", "STRUCTURE_STATE": "BULLISH", "HAS_ACTIVE_SETUP": False}

    line = format_no_setup_line(row)

    assert "AAPL" in line
    assert "BULLISH" in line


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


def test_format_capital_message_shows_amount() -> None:
    msg = format_capital_message(10_000.0)

    assert "10" in msg and "000" in msg


def test_format_add_confirmation_includes_risk_warning_when_breached() -> None:
    sizing = PositionSize(shares=30, risk_dollars=300.0, risk_pct=0.01)
    risk_result = RiskCheckResult(ok=False, warnings=["Bugungi kunlik risk ($300.00) limitdan ($200.00) oshib ketdi."])

    msg = format_add_confirmation(
        symbol="AAPL", entry_price=100.0, stop_price=90.0, target_price=130.0,
        reason="FVG", sizing=sizing, risk_result=risk_result,
    )

    assert "AAPL" in msg
    assert "⚠️" in msg
    assert "kunlik risk" in msg


def test_format_add_confirmation_no_warning_when_ok() -> None:
    sizing = PositionSize(shares=10, risk_dollars=100.0, risk_pct=0.01)
    risk_result = RiskCheckResult(ok=True, warnings=[])

    msg = format_add_confirmation(
        symbol="AAPL", entry_price=100.0, stop_price=90.0, target_price=130.0,
        reason="FVG", sizing=sizing, risk_result=risk_result,
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


def test_help_text_mentions_paper_disclaimer() -> None:
    assert "paper" in HELP_TEXT.lower()
    assert "/scan" in HELP_TEXT
    assert "/add" in HELP_TEXT
