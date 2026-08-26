"""CORE (buy&hold) qatlami uchun foydalanuvchi tomonidan tasdiqlangan halal ro'yxat.

MUHIM PRINSIP: bu fayl halal/harom QARORINI O'ZI HISOBLAMAYDI. Screening —
tashqi, ishonchli manbalar ishi (Musaffa/Zoya/akinda yoki ETF holdings/prospectus).
Bu yerda faqat FOYDALANUVCHI qo'lda tasdiqlagan ro'yxat va uning metadata'si
saqlanadi. Kod bu ro'yxatni avtomatik o'zgartirmaydi.

Boshlang'ich (seed) ma'lumot: `last_reviewed=None` — chunki hech biri hali bu
asbob orqali qayta tekshirilmagan (bu haqiqat, soxta sana qo'yilmadi). Aksiyalar
uchun `halal_source` ham "TEKSHIRILISHI KERAK" — men qaysi ekran (Musaffa/Zoya/...)
orqali tasdiqlanganini bilmayman, shuning uchun soxta manba nomi yozmadim.
Foydalanuvchi bu maydonlarni haqiqiy tekshiruvdan so'ng to'ldirishi kerak.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CoreHolding:
    """Bitta CORE watchlist yozuvi — narx/kontekst kuzatuv uchun, halal QAROR EMAS."""

    ticker: str
    name: str
    category: str  # "etf" | "stock"
    halal_source: str  # masalan "ETF holdings (prospectus)", "Musaffa" — foydalanuvchi to'ldiradi/yangilaydi
    last_reviewed: date | None  # None = hali bu asbob orqali tekshirilmagan
    note: str = ""


CORE_WATCHLIST: list[CoreHolding] = [
    CoreHolding(
        "SPUS", "SP Funds S&P 500 Sharia Industry Exclusions ETF", "etf",
        "ETF holdings (prospectus)", None,
    ),
    CoreHolding(
        "HLAL", "Wahed FTSE USA Shariah ETF", "etf",
        "ETF holdings (prospectus)", None,
    ),
    CoreHolding(
        "AAPL", "Apple Inc.", "stock",
        "TEKSHIRILISHI KERAK — manba kiriting", None,
    ),
    CoreHolding(
        "AMD", "Advanced Micro Devices, Inc.", "stock",
        "TEKSHIRILISHI KERAK — manba kiriting", None,
    ),
    CoreHolding(
        "AVGO", "Broadcom Inc.", "stock",
        "TEKSHIRILISHI KERAK — manba kiriting", None,
    ),
    CoreHolding(
        "FSLR", "First Solar, Inc.", "stock",
        "TEKSHIRILISHI KERAK — manba kiriting", None,
    ),
]


def get_core_watchlist() -> list[CoreHolding]:
    """CORE_WATCHLIST'ning nusxasini qaytaradi (chaqiruvchi uni o'zgartirsa, asl ro'yxat buzilmasin)."""
    return list(CORE_WATCHLIST)
