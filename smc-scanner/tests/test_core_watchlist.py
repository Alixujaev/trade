"""config/core_watchlist.py uchun testlar."""

from __future__ import annotations

from config.core_watchlist import get_core_watchlist


def test_get_core_watchlist_returns_expected_entries() -> None:
    watchlist = get_core_watchlist()

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


def test_seed_entries_have_no_fabricated_review_date() -> None:
    """Hech qanday seed yozuv soxta 'tekshirilgan' sanaga ega bo'lmasligi kerak —
    bu asbob halal statusni o'zi hisoblamaydi, shuning uchun 'tasdiqlangan' degan
    taassurot soxta sana bilan berilmasligi kerak."""
    for holding in get_core_watchlist():
        assert holding.last_reviewed is None


def test_get_core_watchlist_returns_independent_copy() -> None:
    first_call = get_core_watchlist()
    first_call.clear()

    second_call = get_core_watchlist()

    assert len(second_call) > 0
