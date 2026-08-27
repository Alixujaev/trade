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

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

# Halal/harom qarorini bot HISOBLAMAYDI — manba berilmasa shu aniq belgi qo'yiladi
# (soxta manba nomi yozilmaydi), CORE_WATCHLIST seed'idagi konvensiyaga mos.
PLACEHOLDER_HALAL_SOURCE = "TEKSHIRILISHI KERAK — manba kiriting"

_VALID_CATEGORIES = {"stock", "etf"}

# Runtime'da qo'shilgan/o'chirilgan yozuvlar shu faylda saqlanadi (paper_capital.json/
# trade_journal.csv bilan bir xil fayl-asosli holat konvensiyasi). Fayl mavjud
# bo'lmasa (hali hech narsa o'zgartirilmagan) — pastdagi CORE_WATCHLIST seed'i ishlatiladi.
DEFAULT_WATCHLIST_PATH: Path = Path(__file__).resolve().parent.parent / "core_watchlist.json"


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


def get_core_watchlist(path: Path | str = DEFAULT_WATCHLIST_PATH) -> list[CoreHolding]:
    """Saqlangan watchlist'ni qaytaradi; fayl mavjud bo'lmasa (hali hech narsa
    o'zgartirilmagan) CORE_WATCHLIST seed'ining nusxasini qaytaradi — fayl
    yaratmasdan (loyihaning boshqa fayl-asosli holatlari bilan bir xil konvensiya)."""
    path = Path(path)
    if not path.exists():
        return list(CORE_WATCHLIST)
    data = json.loads(path.read_text())
    return [_holding_from_dict(d) for d in data]


def add_to_core_watchlist(
    ticker: str,
    name: str,
    category: str,
    *,
    halal_source: str | None = None,
    note: str = "",
    path: Path | str = DEFAULT_WATCHLIST_PATH,
) -> CoreHolding:
    """Watchlist'ga yangi holding qo'shadi va saqlaydi.

    MUHIM: bu funksiya halal/harom QARORINI HISOBLAMAYDI. `halal_source`
    berilmasa, haqiqiy manba topilguncha aniq PLACEHOLDER_HALAL_SOURCE belgisi
    qo'yiladi (soxta manba yozilmaydi) va `last_reviewed=None` qoladi.
    `halal_source` berilsa, bu foydalanuvchi ONGLI TARZDA shu vosita orqali
    tasdiqlagani hisoblanadi va `last_reviewed=bugun` bo'ladi.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker bo'sh bo'lishi mumkin emas.")
    if category not in _VALID_CATEGORIES:
        raise ValueError(f"Noto'g'ri toifa: {category} (stock yoki etf bo'lishi kerak)")

    watchlist = get_core_watchlist(path)
    if any(h.ticker == ticker for h in watchlist):
        raise ValueError(f"{ticker} allaqachon watchlist'da bor.")

    if halal_source:
        resolved_source, last_reviewed = halal_source, date.today()
    else:
        resolved_source, last_reviewed = PLACEHOLDER_HALAL_SOURCE, None

    holding = CoreHolding(
        ticker=ticker, name=name, category=category,
        halal_source=resolved_source, last_reviewed=last_reviewed, note=note,
    )
    watchlist.append(holding)
    _save_core_watchlist(watchlist, path)
    return holding


def remove_from_core_watchlist(ticker: str, path: Path | str = DEFAULT_WATCHLIST_PATH) -> bool:
    """`ticker`ni watchlist'dan o'chiradi. Topilmasa xato tashlamaydi, False qaytaradi."""
    ticker = ticker.strip().upper()
    watchlist = get_core_watchlist(path)
    filtered = [h for h in watchlist if h.ticker != ticker]
    if len(filtered) == len(watchlist):
        return False
    _save_core_watchlist(filtered, path)
    return True


def _holding_from_dict(d: dict) -> CoreHolding:
    return CoreHolding(
        ticker=d["ticker"],
        name=d["name"],
        category=d["category"],
        halal_source=d["halal_source"],
        last_reviewed=date.fromisoformat(d["last_reviewed"]) if d.get("last_reviewed") else None,
        note=d.get("note", ""),
    )


def _save_core_watchlist(watchlist: list[CoreHolding], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for h in watchlist:
        row = asdict(h)
        row["last_reviewed"] = h.last_reviewed.isoformat() if h.last_reviewed else None
        rows.append(row)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
