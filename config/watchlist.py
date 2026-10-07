"""Halal (shariatga mos) ETF watchlist."""

from __future__ import annotations

# Alohida aksiyalar hardcode QILINMAYDI — faqat sharia ETF'lar
HALAL_ETFS: list[str] = ["SPUS", "SPWO", "SPRE", "HLAL"]


def get_watchlist() -> list[str]:
    """Watchlist'ni qaytaradi: katta harfga o'tkazilgan, takrorlanishsiz, tartib saqlangan."""
    seen: set[str] = set()
    result: list[str] = []
    for symbol in HALAL_ETFS:
        upper = symbol.upper()
        if upper not in seen:
            seen.add(upper)
            result.append(upper)
    return result
