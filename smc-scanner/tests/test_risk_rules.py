"""risk/rules.py uchun testlar (kunlik risk limiti + max ochiq pozisiya soni)."""

from __future__ import annotations

from datetime import date

import pytest

from journal.trade_journal import TradeJournal
from risk.rules import check_daily_risk


def _today() -> date:
    return date.today()


def test_ok_when_within_limits(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=_today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=10,
    )

    result = check_daily_risk(journal, capital=10_000, max_daily_risk_pct=0.02, max_open_positions=3)

    assert result.ok is True
    assert result.warnings == []


def test_warns_when_daily_dollar_risk_exceeded(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    # per-share risk = 10, shares=30 -> $300 risked today; capital=10_000, 2% limit = $200
    journal.add_entry(
        symbol="AAPL", entry_date=_today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=30,
    )

    result = check_daily_risk(journal, capital=10_000, max_daily_risk_pct=0.02, max_open_positions=3)

    assert result.ok is False
    assert any("kunlik" in w.lower() for w in result.warnings)


def test_warns_when_max_open_positions_exceeded(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for i in range(4):
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=_today(), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG", shares=1,
        )

    result = check_daily_risk(journal, capital=10_000, max_daily_risk_pct=0.02, max_open_positions=3)

    assert result.ok is False
    assert any("ochiq pozitsiya" in w.lower() for w in result.warnings)


def test_entries_from_other_days_excluded_from_daily_risk(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2020, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=100,
    )

    result = check_daily_risk(journal, capital=10_000, max_daily_risk_pct=0.02, max_open_positions=3)

    assert result.ok is True  # eski kun yozuvi bugungi risk hisobiga kirmaydi


def test_entries_missing_shares_skipped_not_crashed_on(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=_today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",  # shares yo'q
    )

    result = check_daily_risk(journal, capital=10_000, max_daily_risk_pct=0.02, max_open_positions=3)

    assert result.ok is True
