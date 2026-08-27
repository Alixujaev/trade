"""config/core_watchlist.py uchun testlar (fayl tizimi tmp_path bilan izolyatsiya qilingan)."""

from __future__ import annotations

import pytest

from config.core_watchlist import (
    PLACEHOLDER_HALAL_SOURCE,
    add_to_core_watchlist,
    get_core_watchlist,
    remove_from_core_watchlist,
)


def test_get_core_watchlist_returns_expected_entries(tmp_path) -> None:
    # tmp_path'dagi mavjud bo'lmagan fayl -> seed'ga tushadi; haqiqiy loyiha
    # faylidan (foydalanuvchi runtime'da o'zgartirgan bo'lishi mumkin) izolyatsiya.
    path = tmp_path / "core_watchlist.json"
    watchlist = get_core_watchlist(path=path)

    tickers = [h.ticker for h in watchlist]
    assert "SPUS" in tickers
    assert "HLAL" in tickers
    assert "AAPL" in tickers
    assert "AMD" in tickers
    assert "AVGO" in tickers
    assert "FSLR" in tickers

    by_ticker = {h.ticker: h for h in watchlist}
    assert by_ticker["SPUS"].category == "etf"
    assert by_ticker["HLAL"].category == "etf"
    assert by_ticker["AAPL"].category == "stock"


def test_seed_entries_have_no_fabricated_review_date(tmp_path) -> None:
    """Hech qanday seed yozuv soxta 'tekshirilgan' sanaga ega bo'lmasligi kerak —
    bu asbob halal statusni o'zi hisoblamaydi, shuning uchun 'tasdiqlangan' degan
    taassurot soxta sana bilan berilmasligi kerak."""
    path = tmp_path / "core_watchlist.json"
    for holding in get_core_watchlist(path=path):
        assert holding.last_reviewed is None


def test_get_core_watchlist_returns_independent_copy(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    first_call = get_core_watchlist(path=path)
    first_call.clear()

    second_call = get_core_watchlist(path=path)

    assert len(second_call) > 0


def test_get_core_watchlist_returns_seed_when_file_absent(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    watchlist = get_core_watchlist(path=path)

    assert not path.exists()  # default o'qish fayl yaratmasligi kerak
    assert any(h.ticker == "AAPL" for h in watchlist)


def test_add_to_core_watchlist_without_halal_source_uses_placeholder(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    holding = add_to_core_watchlist("tsla", "Tesla, Inc.", "stock", path=path)

    assert holding.ticker == "TSLA"
    assert holding.halal_source == PLACEHOLDER_HALAL_SOURCE
    assert holding.last_reviewed is None

    reloaded = get_core_watchlist(path=path)
    assert any(h.ticker == "TSLA" for h in reloaded)


def test_add_to_core_watchlist_with_halal_source_sets_review_date(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    holding = add_to_core_watchlist(
        "MSFT", "Microsoft Corp.", "stock", halal_source="Musaffa", path=path
    )

    assert holding.halal_source == "Musaffa"
    assert holding.last_reviewed is not None


def test_add_to_core_watchlist_persists_seed_plus_new_entry(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    add_to_core_watchlist("TSLA", "Tesla, Inc.", "stock", path=path)
    reloaded = get_core_watchlist(path=path)

    tickers = {h.ticker for h in reloaded}
    assert "TSLA" in tickers
    assert "AAPL" in tickers  # seed entries carried over into the new file


def test_add_to_core_watchlist_rejects_duplicate_ticker(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    add_to_core_watchlist("TSLA", "Tesla, Inc.", "stock", path=path)

    with pytest.raises(ValueError):
        add_to_core_watchlist("tsla", "Tesla again", "stock", path=path)


def test_add_to_core_watchlist_rejects_invalid_category(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    with pytest.raises(ValueError):
        add_to_core_watchlist("TSLA", "Tesla, Inc.", "bond", path=path)


def test_remove_from_core_watchlist_removes_existing(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    add_to_core_watchlist("TSLA", "Tesla, Inc.", "stock", path=path)

    removed = remove_from_core_watchlist("tsla", path=path)

    assert removed is True
    assert not any(h.ticker == "TSLA" for h in get_core_watchlist(path=path))


def test_remove_from_core_watchlist_missing_ticker_returns_false(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    removed = remove_from_core_watchlist("NOPE", path=path)

    assert removed is False
    assert not path.exists()  # hech narsa o'zgarmagani uchun fayl yaratilmaydi
