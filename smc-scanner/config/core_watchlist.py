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

from config.tactical_watchlist import HLAL_HOLDINGS

# Halal/harom qarorini bot HISOBLAMAYDI — manba berilmasa shu aniq belgi qo'yiladi
# (soxta manba nomi yozilmaydi), CORE_WATCHLIST seed'idagi konvensiyaga mos.
PLACEHOLDER_HALAL_SOURCE = "TEKSHIRILISHI KERAK — manba kiriting"

_VALID_CATEGORIES = {"stock", "etf"}

# Bazaviy ro'yxat DOIMO kod seed'idan (CORE_WATCHLIST) keladi. core_watchlist.json
# faqat DELTA saqlaydi: {"added": [...], "removed": [...]}. Shu sabab eskirgan yoki
# to'liq-snapshot JSON (masalan Railway persistent volume'da qolib ketgani) yangi
# seed'ni BOSIB KETA OLMAYDI — u faqat qo'lda qo'shilgan/o'chirilganlarni beradi.
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


# Foydalanuvchi qo'lda kiritgan boshlang'ich yozuvlar (sharia ETF'lar + bir nechta
# aksiya). Bular har doim seed'da birinchi turadi va HLAL ro'yxatidagi bir xil
# ticker'dan ustun (masalan AAPL/AMD/AVGO bu yerda ham, HLAL holdings'da ham bor).
_CURATED_SEED: list[CoreHolding] = [
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

# HLAL (Wahed FTSE USA Shariah ETF) tarkibiy qismlari — config/tactical_watchlist.py
# (data/hlal_holdings.csv'dan generatsiya, git'da). Bu ro'yxat DEPLOY bilan ketadi,
# shuning uchun core_watchlist.json bo'lmagan muhitda ham (masalan Railway, u
# gitignore'dagi JSON'ni olmaydi) /scan va /watchlist to'liq ro'yxatni ko'radi.
#
# halal_source — faqat PROVENANS (ro'yxat qayerdan olindi), mavjud ETF-holdings
# seed'lari bilan bir xil uslub. last_reviewed=None: bu asbob orqali qayta
# tekshirilmagan — soxta "tasdiqlangan" sana qo'yilmaydi.
_HLAL_HALAL_SOURCE = "HLAL ETF holdings (Wahed FTSE USA Shariah ETF)"


def _build_seed() -> list[CoreHolding]:
    seed = list(_CURATED_SEED)
    seen = {h.ticker for h in seed}
    for ticker, name in HLAL_HOLDINGS:
        if ticker in seen:
            continue
        seen.add(ticker)
        seed.append(
            CoreHolding(
                ticker=ticker, name=name, category="stock",
                halal_source=_HLAL_HALAL_SOURCE, last_reviewed=None,
            )
        )
    return seed


CORE_WATCHLIST: list[CoreHolding] = _build_seed()


def _ticker_of(row: dict) -> str:
    return str(row.get("ticker", "")).strip().upper()


def _empty_overlay() -> dict[str, list]:
    return {"added": [], "removed": []}


def _load_overlay(path: Path) -> dict[str, list]:
    """core_watchlist.json'ni delta ko'rinishida qaytaradi: {"added": [...], "removed": [...]}.

    Orqaga moslik: fayl eski ko'rinishda (holding dict'lar RO'YXATI, ya'ni to'liq
    snapshot) bo'lsa — seed'da BO'LMAGAN ticker'lar "added"ga migratsiya qilinadi,
    seed'dagilari e'tiborsiz qoladi (ular kod seed'ini bosib keta olmaydi). Fayl
    yo'q bo'lsa bo'sh overlay. Bu funksiya faylni YARATMAYDI/O'ZGARTIRMAYDI."""
    if not path.exists():
        return _empty_overlay()
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        return {
            "added": list(data.get("added", [])),
            "removed": [str(t).strip().upper() for t in data.get("removed", [])],
        }
    seed_tickers = {h.ticker for h in CORE_WATCHLIST}
    migrated = [d for d in data if isinstance(d, dict) and _ticker_of(d) not in seed_tickers]
    return {"added": migrated, "removed": []}


def _write_overlay(path: Path, overlay: dict[str, list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2))


def get_core_watchlist(path: Path | str = DEFAULT_WATCHLIST_PATH) -> list[CoreHolding]:
    """Kod seed'i (CORE_WATCHLIST) ustiga core_watchlist.json delta'sini qo'llab
    qaytaradi: seed minus "removed", plyus "added" (qo'lda qo'shilgan metadata
    seed'nikidan ustun). Fayl bo'lmasa — sof seed nusxasi. O'qish faylni
    YARATMAYDI (loyihaning boshqa fayl-asosli holatlari bilan bir xil konvensiya)."""
    overlay = _load_overlay(Path(path))
    removed = set(overlay["removed"])

    result: list[CoreHolding] = [h for h in CORE_WATCHLIST if h.ticker not in removed]
    index = {h.ticker: i for i, h in enumerate(result)}

    for row in overlay["added"]:
        holding = _holding_from_dict(row)
        if holding.ticker in removed:
            continue
        if holding.ticker in index:
            result[index[holding.ticker]] = holding
        else:
            index[holding.ticker] = len(result)
            result.append(holding)
    return result


def add_to_core_watchlist(
    ticker: str,
    name: str,
    category: str,
    *,
    halal_source: str | None = None,
    note: str = "",
    path: Path | str = DEFAULT_WATCHLIST_PATH,
) -> CoreHolding:
    """Watchlist'ga yangi holding qo'shadi va overlay'ga (core_watchlist.json) saqlaydi.

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

    if any(h.ticker == ticker for h in get_core_watchlist(path)):
        raise ValueError(f"{ticker} allaqachon watchlist'da bor.")

    if halal_source:
        resolved_source, last_reviewed = halal_source, date.today()
    else:
        resolved_source, last_reviewed = PLACEHOLDER_HALAL_SOURCE, None

    holding = CoreHolding(
        ticker=ticker, name=name, category=category,
        halal_source=resolved_source, last_reviewed=last_reviewed, note=note,
    )

    overlay = _load_overlay(Path(path))
    overlay["removed"] = [t for t in overlay["removed"] if t != ticker]
    overlay["added"] = [r for r in overlay["added"] if _ticker_of(r) != ticker]
    overlay["added"].append(_holding_to_dict(holding))
    _write_overlay(Path(path), overlay)
    return holding


def remove_from_core_watchlist(ticker: str, path: Path | str = DEFAULT_WATCHLIST_PATH) -> bool:
    """`ticker`ni watchlist'dan o'chiradi (overlay'ga yoziladi: seed ticker'i bo'lsa
    "removed"ga, qo'lda qo'shilgani bo'lsa "added"dan olib tashlanadi). Topilmasa
    xato tashlamaydi, False qaytaradi va faylga tegmaydi."""
    ticker = ticker.strip().upper()
    if not any(h.ticker == ticker for h in get_core_watchlist(path)):
        return False

    overlay = _load_overlay(Path(path))
    overlay["added"] = [r for r in overlay["added"] if _ticker_of(r) != ticker]
    is_seed = any(h.ticker == ticker for h in CORE_WATCHLIST)
    if is_seed and ticker not in overlay["removed"]:
        overlay["removed"].append(ticker)
    _write_overlay(Path(path), overlay)
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


def _holding_to_dict(h: CoreHolding) -> dict:
    row = asdict(h)
    row["last_reviewed"] = h.last_reviewed.isoformat() if h.last_reviewed else None
    return row
