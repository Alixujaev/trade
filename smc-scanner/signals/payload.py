"""Setup'ni bir xil aniqlaydigan barqaror signal_id (TZ 18 — dedup uchun kalit).

Bir xil setup (symbol + setup turi + entry bar sanasi/narxi + exit mode) qayta
skan qilinganda AYNAN bir xil ID chiqishi kerak (idempotent) — shu orqali
signals/dedup.py bir xil setup allaqachon ko'rsatilganini biladi.

MUHIM: bu modul hech narsani filtrlamaydi/o'zgartirmaydi — faqat mavjud
tactical_scan.py qatoridan (yoki xom qiymatlardan) sof ID hisoblaydi.
"""

from __future__ import annotations

import hashlib


def compute_signal_id(
    *, symbol: str, setup_type: str, entry_ts: str, entry_price: float, mode: str
) -> str:
    """symbol+setup_type+entry_ts+entry_price+mode'dan barqaror hash (16 hex belgi).

    entry_price float sifatida keladi (masalan tactical_scan.py'da round(..., 2))
    — qat'iy formatlash (`:.6f`) turli float repr'laridan kelib chiqadigan
    nomuvofiqlikning oldini oladi.
    """
    key = f"{symbol}|{setup_type}|{entry_ts}|{entry_price:.6f}|{mode}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def signal_id_for_row(row: dict, *, mode: str) -> str | None:
    """tactical_scan.py::build_scan_row natijasi (qator)dan signal_id.

    Kerakli maydonlar (SYMBOL, SETUP_REASON, SETUP_ENTRY_DATE, SETUP_ENTRY) yo'q
    bo'lsa (masalan faol setup yo'q) — None. Chaqiruvchi None'ni dedup'siz
    o'tkazish kerakligi sifatida talqin qiladi.
    """
    symbol = row.get("SYMBOL")
    setup_type = row.get("SETUP_REASON")
    entry_ts = row.get("SETUP_ENTRY_DATE")
    entry_price = row.get("SETUP_ENTRY")
    if not symbol or not setup_type or entry_ts is None or entry_price is None:
        return None
    return compute_signal_id(
        symbol=symbol, setup_type=setup_type, entry_ts=entry_ts,
        entry_price=float(entry_price), mode=mode,
    )
