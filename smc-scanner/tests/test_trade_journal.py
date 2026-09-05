"""journal/trade_journal.py uchun testlar (qo'lda hisoblangan qiymatlar, fayl tizimi tmp_path bilan)."""

from __future__ import annotations

from datetime import date

import pandas as pd
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


def test_add_entry_reference_target_price_computes_rr_planned_when_no_target(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AMD", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",
        reference_target_price=130.0,
    )

    assert entry.rr_planned == pytest.approx(3.0)  # (130-100)/(100-90)
    assert entry.reference_target_price == pytest.approx(130.0)
    assert entry.target_price is None


def test_add_entry_target_price_takes_priority_over_reference_target_price(tmp_path) -> None:
    """Ikkalasi ham berilgan chekka holat: rr_planned target_price'dan hisoblanadi,
    reference_target_price baribir saqlanadi (audit uchun), lekin hisobga olinmaydi."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
        reference_target_price=999.0,
    )

    assert entry.rr_planned == pytest.approx(3.0)  # (130-100)/(100-90), 999 EMAS
    assert entry.reference_target_price == pytest.approx(999.0)  # baribir saqlanadi


def test_stats_avg_rr_planned_includes_trailing_entries_with_reference_target(tmp_path) -> None:
    """reference_target_price berilgan trailing yozuv endi avg_rr_planned hisobiga kiradi —
    test_stats_avg_rr_planned_excludes_trailing_entries'ning "aksincha" holati."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=120.0, exit_mode="fixed", reason="FVG",  # rr_planned=2.0
    )
    journal.add_entry(
        symbol="AMD", entry_date=date(2026, 1, 1), entry_price=50.0, stop_price=45.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",
        reference_target_price=60.0,  # rr_planned=(60-50)/(50-45)=2.0
    )

    stats = journal.stats()

    assert stats["avg_rr_planned"] == pytest.approx(2.0)  # (2.0+2.0)/2, ikkalasi ham hisobga olindi


def test_csv_round_trip_preserves_reference_target_price(tmp_path) -> None:
    csv_path = tmp_path / "journal.csv"
    journal = TradeJournal(csv_path=csv_path)
    journal.add_entry(
        symbol="AMD", entry_date=date(2026, 2, 1), entry_price=50.0, stop_price=45.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",
        reference_target_price=60.0,
    )

    reloaded = TradeJournal(csv_path=csv_path)

    assert reloaded.entries[0].reference_target_price == pytest.approx(60.0)
    assert reloaded.entries[0].rr_planned == pytest.approx(2.0)


# ======================================================================
# Setup snapshot (TZ) — trade ochilgan paytdagi to'liq setup konteksti
# ======================================================================


def test_add_entry_stores_snapshot_fields(tmp_path) -> None:
    """Quickadd-from-signal oqimi kabi -- snapshot kwarg'lar berilsa, JournalEntry'da
    to'g'ri saqlanadi."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=150.0, stop_price=140.0,
        target_price=None, exit_mode="trailing", reason="breakout_retest",
        reference_target_price=170.0,
        setup_type="breakout_retest", score=84.0, score_label="STRONG SETUP",
        trend="BULLISH", structure="BOS", volume_confirmed=True,
        entry_zone_low=148.0, entry_zone_high=152.0, invalidation=140.0, target=170.0,
        risk_reward=2.5, target_source="resistance", status="ZONE_REACHED",
        score_reasons=("trend: kuchli", "hajm: tasdiqlangan"),
    )

    assert entry.setup_type == "breakout_retest"
    assert entry.score == pytest.approx(84.0)
    assert entry.score_label == "STRONG SETUP"
    assert entry.trend == "BULLISH"
    assert entry.structure == "BOS"
    assert entry.volume_confirmed is True
    assert entry.entry_zone_low == pytest.approx(148.0)
    assert entry.entry_zone_high == pytest.approx(152.0)
    assert entry.invalidation == pytest.approx(140.0)
    assert entry.target == pytest.approx(170.0)
    assert entry.risk_reward == pytest.approx(2.5)
    assert entry.target_source == "resistance"
    assert entry.status == "ZONE_REACHED"
    assert entry.score_reasons == ("trend: kuchli", "hajm: tasdiqlangan")


def test_add_entry_without_snapshot_defaults_to_none(tmp_path) -> None:
    """Qo'lda /add oqimi kabi -- snapshot kwarg'lar berilmasa, hammasi None/bo'sh
    (backward-compat, payload yo'q holat normal)."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")

    entry = journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="qo'lda kiritilgan",
    )

    assert entry.setup_type is None
    assert entry.score is None
    assert entry.score_label is None
    assert entry.trend is None
    assert entry.structure is None
    assert entry.volume_confirmed is None
    assert entry.entry_zone_low is None
    assert entry.entry_zone_high is None
    assert entry.invalidation is None
    assert entry.target is None
    assert entry.risk_reward is None
    assert entry.target_source is None
    assert entry.status is None
    assert entry.score_reasons == ()


def test_csv_round_trip_preserves_snapshot_fields(tmp_path) -> None:
    """Snapshot maydonlari (bool va score_reasons tuple'i ham) yozib-o'qishda
    to'g'ri saqlanishi kerak."""
    csv_path = tmp_path / "journal.csv"
    journal = TradeJournal(csv_path=csv_path)
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=150.0, stop_price=140.0,
        target_price=None, exit_mode="trailing", reason="breakout_retest",
        reference_target_price=170.0,
        setup_type="breakout_retest", score=84.0, score_label="STRONG SETUP",
        trend="BULLISH", structure="BOS", volume_confirmed=True,
        entry_zone_low=148.0, entry_zone_high=152.0, invalidation=140.0, target=170.0,
        risk_reward=2.5, target_source="resistance", status="ZONE_REACHED",
        score_reasons=("trend: kuchli", "hajm: tasdiqlangan"),
    )
    journal.add_entry(
        symbol="MSFT", entry_date=date(2026, 1, 1), entry_price=300.0, stop_price=290.0,
        target_price=None, exit_mode="trailing", reason="fvg",
        volume_confirmed=False,  # False ham True kabi to'g'ri saqlanishi kerak (NaN emas)
    )

    reloaded = TradeJournal(csv_path=csv_path)

    first = next(e for e in reloaded.entries if e.symbol == "AAPL")
    assert first.setup_type == "breakout_retest"
    assert first.score == pytest.approx(84.0)
    assert first.volume_confirmed is True
    assert first.entry_zone_low == pytest.approx(148.0)
    assert first.entry_zone_high == pytest.approx(152.0)
    assert first.status == "ZONE_REACHED"
    assert first.score_reasons == ("trend: kuchli", "hajm: tasdiqlangan")

    second = next(e for e in reloaded.entries if e.symbol == "MSFT")
    assert second.volume_confirmed is False
    assert second.setup_type is None
    assert second.score is None
    assert second.score_reasons == ()


def test_load_legacy_csv_without_snapshot_columns(tmp_path) -> None:
    """Snapshot maydonlari qo'shilishidan OLDINGI CSV (bu ustunlar UMUMAN yo'q) —
    to'liq bir qatorli haqiqiy yozuv bilan yuklansa, o'chib qolmasdan, snapshot
    maydonlari default (None/bo'sh)ga tushadi."""
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "entry_id,symbol,entry_date,entry_price,stop_price,target_price,"
        "reference_target_price,exit_mode,reason,rr_planned,notes,exit_date,"
        "exit_price,r_multiple\n"
        "1,AAPL,2026-01-01,100.0,90.0,130.0,,fixed,FVG,3.0,,,,\n"
    )

    journal = TradeJournal(csv_path=csv_path)

    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry.symbol == "AAPL"
    assert entry.entry_price == pytest.approx(100.0)
    assert entry.setup_type is None
    assert entry.score is None
    assert entry.volume_confirmed is None
    assert entry.entry_zone_low is None
    assert entry.score_reasons == ()


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


# ======================================================================
# stats(include_benchmark=True) -- buy&hold benchmark bloki (TZ: discretionary vs market)
# ======================================================================


def _make_df(dates: list[str], closes: list[float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(pd.to_datetime(dates), tz="UTC", name="datetime")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1000] * len(closes)},
        index=index,
    )


class _FakeProvider:
    """tests/test_scanner.py::_FakeProvider bilan bir xil konvensiya (mock provider)."""

    def __init__(self, dfs: dict[str, pd.DataFrame | Exception]) -> None:
        self._dfs = dfs

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        result = self._dfs[symbol]
        if isinstance(result, Exception):
            raise result
        return result


def test_stats_default_has_no_benchmark_key(tmp_path) -> None:
    """include_benchmark default False -- mavjud chaqiruvchilar (provider yo'q holatda ham)
    o'zgarishsiz ishlashda davom etadi, tarmoqqa chiqmaydi."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 10), exit_price=115.0)

    assert "benchmark" not in journal.stats()


def test_stats_benchmark_computes_avg_return_and_comparison(tmp_path) -> None:
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    # Savdo 1: entry=100 -> exit=115 (+15% price return). Benchmark (same-window,
    # 2026-01-01 -> 2026-01-10): 100 -> 108 (+8%) -- discretionary yaxshiroq.
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 10), exit_price=115.0)
    # Savdo 2: entry=50 -> exit=52 (+4% price return, R past bo'lsa ham baland ko'rinishi
    # mumkin edi -- lekin bu yerda R umuman ishlatilmaydi). Benchmark: 50 -> 60 (+20%) --
    # benchmark yaxshiroq.
    journal.add_entry(
        symbol="AMD", entry_date=date(2026, 2, 1), entry_price=50.0, stop_price=49.0,
        target_price=None, exit_mode="trailing", reason="ORDER_BLOCK",
    )
    journal.close_entry(2, exit_date=date(2026, 2, 20), exit_price=52.0)

    provider = _FakeProvider({
        "AAPL": _make_df(["2026-01-01", "2026-01-10"], [100.0, 108.0]),
        "AMD": _make_df(["2026-02-01", "2026-02-20"], [50.0, 60.0]),
    })

    stats = journal.stats(include_benchmark=True, provider=provider)
    benchmark = stats["benchmark"]

    assert benchmark["num_benchmarked"] == 2
    assert benchmark["num_benchmark_skipped"] == 0
    # avg((108-100)/100, (60-50)/50) = avg(0.08, 0.20) = 0.14 -> 14%
    assert benchmark["avg_benchmark_return_pct"] == pytest.approx(14.0)
    assert benchmark["benchmark_positive_count"] == 2  # ikkalasi ham musbat
    assert benchmark["discretionary_outperformed_count"] == 1  # faqat AAPL (0.15 > 0.08)


def test_stats_benchmark_open_entries_are_excluded(tmp_path) -> None:
    """Ochiq savdo (exit_date yo'q) benchmark'ga umuman kirmaydi."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )  # yopilmagan

    provider = _FakeProvider({"AAPL": _make_df(["2026-01-01"], [100.0])})
    stats = journal.stats(include_benchmark=True, provider=provider)

    assert stats["benchmark"]["num_benchmarked"] == 0
    assert stats["benchmark"]["avg_benchmark_return_pct"] is None


def test_stats_benchmark_provider_error_skips_gracefully(tmp_path) -> None:
    """Provider xatosi bitta savdoni SKIP qiladi, butun stats() yiqilmaydi."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=90.0,
        target_price=130.0, exit_mode="fixed", reason="FVG",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 10), exit_price=115.0)

    provider = _FakeProvider({"AAPL": ConnectionError("network down")})
    stats = journal.stats(include_benchmark=True, provider=provider)

    assert stats["benchmark"]["num_benchmarked"] == 0
    assert stats["benchmark"]["num_benchmark_skipped"] == 1
    assert stats["num_closed"] == 1  # discretionary blok o'zgarmagan, yiqilmadi


def test_stats_benchmark_r_and_price_return_not_conflated(tmp_path) -> None:
    """MUHIM metodologiya regressiyasi: R baland (tor stop) bo'lsa ham, price return
    benchmark'dan past bo'lsa outperform hisoblanmaydi."""
    journal = TradeJournal(csv_path=tmp_path / "journal.csv")
    # entry=100, stop=99 (tor) -> R=+2.0 lekin price return atigi +2%
    journal.add_entry(
        symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0, stop_price=99.0,
        target_price=102.0, exit_mode="fixed", reason="FVG",
    )
    journal.close_entry(1, exit_date=date(2026, 1, 10), exit_price=102.0)

    # Benchmark shu oynada +8% -- price return bo'yicha benchmark yutadi
    provider = _FakeProvider({"AAPL": _make_df(["2026-01-01", "2026-01-10"], [100.0, 108.0])})
    stats = journal.stats(include_benchmark=True, provider=provider)

    assert stats["avg_r_realized"] == pytest.approx(2.0)  # R o'zgarishsiz baland
    assert stats["benchmark"]["discretionary_outperformed_count"] == 0  # lekin outperform EMAS
