"""risk/rules.py uchun testlar (max ochiq pozisiya soni)."""

from __future__ import annotations

from datetime import date

from journal.trade_journal import TradeJournal
from risk.rules import check_open_positions


def _today() -> date:
    return date.today()


def test_ok_when_within_limits(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=_today(), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )

    result = check_open_positions(journal, max_open_positions=3)

    assert result.ok is True
    assert result.warnings == []


def test_warns_when_max_open_positions_exceeded(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for i in range(4):
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=_today(), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )

    result = check_open_positions(journal, max_open_positions=3)

    assert result.ok is False
    assert any("ochiq pozitsiya" in w.lower() for w in result.warnings)


def test_closed_entries_not_counted_as_open(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for i in range(4):
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=_today(), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )
    for i in range(1, 4):
        journal.close_entry(i, exit_date=_today(), exit_price=110.0)

    result = check_open_positions(journal, max_open_positions=3)

    assert result.ok is True
