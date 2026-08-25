"""config/watchlist.py uchun testlar."""

from __future__ import annotations

import config.watchlist as watchlist_module
from config.watchlist import get_watchlist


def test_get_watchlist_dedup_case_insensitive(monkeypatch) -> None:
    """Katta-kichik harf farqli takrorlanishlar birlashtirilib, birinchi tartib saqlanishi kerak."""
    monkeypatch.setattr(watchlist_module, "HALAL_ETFS", ["SPUS", "spus", "HLAL"])

    result = get_watchlist()

    assert result == ["SPUS", "HLAL"]


def test_get_watchlist_returns_uppercase() -> None:
    """Standart watchlist barcha simvollar katta harfda qaytishi kerak."""
    result = get_watchlist()

    assert all(symbol == symbol.upper() for symbol in result)
    assert "SPUS" in result
    assert "HLAL" in result
