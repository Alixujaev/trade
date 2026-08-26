"""journal/trade_journal.py uchun testlar (qo'lda hisoblangan qiymatlar, fayl tizimi tmp_path bilan)."""

from __future__ import annotations

from datetime import date

import pytest

from journal.trade_journal import TradeJournal


def test_add_entry_computes_rr_planned_fixed_mode(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )

    assert entry.rr_planned == pytest.approx(3.0)  # (130-100)/(100-90)
    assert entry.entry_id == 1


def test_add_entry_trailing_mode_has_no_rr_planned(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",
    )

    assert entry.rr_planned is None


def test_close_entry_hand_verified(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )

    closed = journal.close_entry(entry.entry_id, exit_date=date(2026, 1, 10), exit_price=115.0)

    assert closed.r_multiple == pytest.approx(1.5)  # (115-100)/(100-90)
    assert closed.exit_price == pytest.approx(115.0)


def test_close_entry_nonexistent_id_raises(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    with pytest.raises(ValueError):
        journal.close_entry(999, exit_date=date(2026, 1, 1), exit_price=100.0)


def test_stats_high_planned_rr_but_low_win_rate_shows_negative_expectancy(tmp_path) -> None:
    """Bu — butun funksiyaning asosiy sababi: rr_planned=3.0 (yuqori) bo'lsa ham,
    win rate past bo'lsa expectancy_r MANFIY chiqishi kerak — kattaroq R:R avtomatik
    ko'proq foyda degani EMASLIGINI foydalanuvchi o'z ma'lumotida ko'rishi uchun."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    for _ in range(3):
        journal.add_entry(
            symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",  # rr_planned=3.0 har birida
        )

    # 1-savdo: kichik g'alaba (target'ga yetmadi, R=1.0). 2,3-savdo: to'liq stop-out (R=-1.0)
    journal.close_entry(1, exit_date=date(2026, 1, 5), exit_price=110.0)
    journal.close_entry(2, exit_date=date(2026, 1, 5), exit_price=90.0)
    journal.close_entry(3, exit_date=date(2026, 1, 5), exit_price=90.0)

    stats = journal.stats()

    assert stats["avg_rr_planned"] == pytest.approx(3.0)  # "yaxshi ko'rinadi"
    assert stats["win_rate"] == pytest.approx(1 / 3)
    assert stats["avg_win_r"] == pytest.approx(1.0)
    assert stats["avg_loss_r"] == pytest.approx(-1.0)
    # expectancy = (1/3)*1.0 + (2/3)*(-1.0) = -1/3
    assert stats["expectancy_r"] == pytest.approx(-1 / 3)
    assert stats["expectancy_r"] < 0  # yuqori rr_planned'ga qaramay, manfiy
    # avg_r_realized va expectancy_r matematik jihatdan bir xil bo'lishi kerak (regressiya himoyasi)
    assert stats["avg_r_realized"] == pytest.approx(stats["expectancy_r"])


def test_stats_avg_rr_planned_excludes_trailing_entries(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=120.0, exit_mode="fixed", reason="FVG",  # rr_planned=2.0
    )
    journal.add_entry(
        symbol="AMD", entry_date=date(2026, 1, 1), entry_price=50.0, stop_price=45.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",  # rr_planned=None
    )

    stats = journal.stats()

    assert stats["avg_rr_planned"] == pytest.approx(2.0)  # faqat fixed yozuv hisobga olinadi


def test_csv_round_trip(tmp_path) -> None:
    csv_path = tmp_path / "journal.csv"
    journal = TradeJournal(csv_path=csv_path)
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", notes="birinchi",
    )
    journal.add_entry(
        symbol="AMD", entry_date=date(2026, 2, 1), entry_price=50.0, stop_price=45.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 10), exit_price=115.0, notes="yopildi")

    reloaded = TradeJournal(csv_path=csv_path)

    assert len(reloaded.entries) == 2
    first = next(e for e in reloaded.entries if e.entry_id == 1)
    second = next(e for e in reloaded.entries if e.entry_id == 2)
    assert first.symbol == "AAPL"
    assert first.exit_price == pytest.approx(115.0)
    assert first.r_multiple == pytest.approx(1.5)
    assert first.notes == "yopildi"
    assert second.symbol == "AMD"
    assert second.target_price is None
    assert second.rr_planned is None
    assert second.exit_date is None


def test_empty_journal_no_file(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "does_not_exist.csv")

    assert journal.entries == []
    stats = journal.stats()
    assert stats["num_entries"] == 0
    assert stats["expectancy_r"] == 0.0
    assert stats["win_rate"] == 0.0


def test_empty_journal_zero_byte_file(tmp_path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("")

    journal = TradeJournal(csv_path=csv_path)

    assert journal.entries == []
    assert journal.stats()["num_entries"] == 0


def test_empty_journal_header_only_file(tmp_path) -> None:
    csv_path = tmp_path / "header_only.csv"
    csv_path.write_text(
        "entry_id,symbol,entry_date,entry_price,stop_price,target_price,exit_mode,"
        "reason,rr_planned,notes,exit_date,exit_price,r_multiple\n"
    )

    journal = TradeJournal(csv_path=csv_path)

    assert journal.entries == []
    assert journal.stats()["num_entries"] == 0


def test_add_entry_stores_shares(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=10,
    )

    assert entry.shares == 10


def test_add_entry_shares_defaults_to_none(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )

    assert entry.shares is None


def test_shares_round_trips_through_csv(tmp_path) -> None:
    csv_path = tmp_path / "journal.csv"
    journal = TradeJournal(csv_path=csv_path)
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG", shares=10,
    )

    reloaded = TradeJournal(csv_path=csv_path)

    assert reloaded.entries[0].shares == pytest.approx(10)


def test_old_format_csv_without_shares_column_still_loads(tmp_path) -> None:
    csv_path = tmp_path / "old.csv"
    csv_path.write_text(
        "entry_id,symbol,entry_date,entry_price,stop_price,target_price,exit_mode,"
        "reason,rr_planned,notes,exit_date,exit_price,r_multiple\n"
        "1,AAPL,2026-01-01,100.0,90.0,130.0,fixed,FVG,3.0,,,,\n"
    )

    journal = TradeJournal(csv_path=csv_path)

    assert len(journal.entries) == 1
    assert journal.entries[0].shares is None


def test_open_entries_returns_only_unclosed(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    journal.add_entry(
        symbol="AMD", entry_date=date(2026, 1, 1), entry_price=50.0, stop_price=45.0,
        target_price=60.0, exit_mode="fixed", reason="FVG",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 5), exit_price=110.0)

    open_entries = journal.open_entries()

    assert [e.entry_id for e in open_entries] == [2]


def test_recent_entries_returns_last_n_in_order(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for i in range(5):
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )

    recent = journal.recent_entries(2)

    assert [e.symbol for e in recent] == ["SYM3", "SYM4"]


def test_recent_entries_default_is_ten(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for i in range(15):
        journal.add_entry(
            symbol=f"SYM{i}", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )

    assert len(journal.recent_entries()) == 10


def test_stats_profit_factor_computed_from_r_multiples(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    for _ in range(2):
        journal.add_entry(
            symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
            target_price=130.0, exit_mode="fixed", reason="FVG",
        )
    journal.close_entry(1, exit_date=date(2026, 1, 5), exit_price=120.0)  # R = +2.0
    journal.close_entry(2, exit_date=date(2026, 1, 5), exit_price=90.0)  # R = -1.0

    stats = journal.stats()

    assert stats["profit_factor"] == pytest.approx(2.0)  # sum(wins)=2.0 / abs(sum(losses))=1.0


def test_stats_profit_factor_none_when_no_losses(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 5), exit_price=120.0)

    stats = journal.stats()

    assert stats["profit_factor"] is None


def test_stats_profit_factor_none_when_no_closed_trades(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    assert journal.stats()["profit_factor"] is None
