"""data/hlal_holdings.csv -> config/tactical_watchlist.py generator.

MUHIM PRINSIP: bu skript halal/harom QARORINI HISOBLAMAYDI. U faqat HLAL
(Wahed FTSE USA Shariah ETF) rasmiy holdings eksportidagi OMMAVIY ma'lumotni
(ticker + kompaniya nomi) Python ro'yxatiga aylantiradi, shunda taktik watchlist
seed'i git bilan (va Railway deploy bilan) ketadi — core_watchlist.json
gitignore'da qolib, Railway'da yo'qolib qolmasin.

CSV'dagi qo'lda hal qilinishi kerak bo'lgan holatlar (CSV'ning o'zidan
kelib chiqmaydi, shuning uchun shu yerda aniq xarita):
  * "2602335D" (Bloomberg-uslub ID, ticker emas) -> "TPG"  (SecurityName: "TPG Inc")
  * "LEN/B" -> "LEN-B"  (yfinance sinf-aksiya konvensiyasi)
  * MoneyMarketFlag to'ldirilgan qatorlar ("Cash&Other") tashlab yuboriladi.

Ishlatish:
    python scripts/build_tactical_watchlist.py           # config/tactical_watchlist.py ni yozadi
    python scripts/build_tactical_watchlist.py --check    # farq bo'lsa xato bilan chiqadi (CI uchun)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = _ROOT / "data" / "hlal_holdings.csv"
OUT_PATH = _ROOT / "config" / "tactical_watchlist.py"

# CSV StockTicker -> haqiqiy bozor ticker'i (faqat CSV'dan kelib chiqmaydigan holatlar)
_TICKER_OVERRIDES = {
    "2602335D": "TPG",
    "LEN/B": "LEN-B",
}


def load_holdings(csv_path: Path = CSV_PATH) -> list[tuple[str, str]]:
    """(ticker, nom) ro'yxatini CSV tartibida qaytaradi. Cash&Other tashlanadi."""
    rows: list[tuple[str, str]] = []
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("MoneyMarketFlag", "").strip():
                continue  # "Cash&Other" — ticker emas
            raw = row["StockTicker"].strip()
            ticker = _TICKER_OVERRIDES.get(raw, raw)
            name = row["SecurityName"].strip()
            if not ticker or not name:
                continue
            rows.append((ticker, name))
    return rows


def render_module(holdings: list[tuple[str, str]]) -> str:
    body = "\n".join(
        f'    ("{tk}", "{nm.replace(chr(34), chr(92) + chr(34))}"),' for tk, nm in holdings
    )
    return (
        '"""HLAL (Wahed FTSE USA Shariah ETF) tarkibiy qismlari — taktik watchlist seed\'i.\n'
        "\n"
        "BU FAYL AVTOMATIK GENERATSIYA QILINGAN. Manba: data/hlal_holdings.csv\n"
        "(HLAL ETF rasmiy holdings eksporti). Qayta generatsiya: scripts/build_tactical_watchlist.py\n"
        "\n"
        "Faqat OMMAVIY ma'lumot: ticker + kompaniya nomi. Halal/harom QAROR shu yerda\n"
        "HISOBLANMAYDI — ro'yxat manbasi HLAL (o'zi sharia ETF) holdings, xuddi mavjud\n"
        "CORE_WATCHLIST seed'idagi ETF-holdings konvensiyasi kabi. last_reviewed=None\n"
        "qoladi (bu asbob orqali qayta tekshirilmagan — soxta sana qo'yilmaydi).\n"
        "\n"
        "Shaxsiy jurnal / runtime o'zgarishlar core_watchlist.json'da (gitignore) qoladi;\n"
        "bu seed esa deploy bilan ketadi, shunda Railway'da ham /scan va /watchlist to'liq\n"
        "ro'yxatni ko'radi (JSON fayli bo'lmasa).\n"
        '"""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "# (ticker, kompaniya nomi) — data/hlal_holdings.csv dan. Tartib: CSV tartibi.\n"
        "HLAL_HOLDINGS: list[tuple[str, str]] = [\n"
        f"{body}\n"
        "]\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Faylni yozmaydi; joriy fayl generatsiya natijasidan farq qilsa 1 qaytaradi.",
    )
    args = parser.parse_args()

    holdings = load_holdings()
    rendered = render_module(holdings)

    if args.check:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != rendered:
            print(f"{OUT_PATH} eskirgan — `python scripts/build_tactical_watchlist.py` ni ishga tushiring.")
            return 1
        print(f"{OUT_PATH} yangi ({len(holdings)} ta belgi).")
        return 0

    OUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"{OUT_PATH} yozildi — {len(holdings)} ta belgi.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT))
    raise SystemExit(main())
