"""Savdo jurnali yozuvi uchun data modeli."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class JournalEntry:
    """Bitta HAQIQIY (paper yoki live) savdo yozuvi.

    backtest/types.py::TradeResult'dan farqi: bu SIMULYATSIYA emas — foydalanuvchi
    o'zi qo'lda kiritgan haqiqiy qaror va (yopilgach) haqiqiy natija. Yopilmagan
    (exit_date=None) yozuvlar ochiq pozitsiyani anglatadi.
    """

    entry_id: int
    symbol: str
    entry_date: date
    entry_price: float
    stop_price: float
    target_price: float | None  # None — exit_mode="trailing" (maqsad yo'q)
    exit_mode: str  # "fixed" | "trailing"
    reason: str  # masalan "FVG", "ORDER_BLOCK" yoki foydalanuvchi o'z izohi
    rr_planned: float | None  # (target-entry)/(entry-stop); target_price=None bo'lsa None
    notes: str = ""
    exit_date: date | None = None
    exit_price: float | None = None
    r_multiple: float | None = None  # yopilgach: (exit-entry)/(entry-stop)
