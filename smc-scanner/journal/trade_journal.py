"""Haqiqiy (paper/live) savdo jurnali — CSV asosida saqlanadi, foydalanuvchi qo'lda boshqaradi.

MUHIM: bu backtest/engine.py'ning simulyatsiyasi EMAS — foydalanuvchi o'zi HAQIQATDA
(yoki paper) olgan savdolarni yozib boradi. stats() faqat RAQAMLARNI ko'rsatadi
(masalan "rejalashtirilgan R:R yuqori-yu, expectancy manfiy") — hech qanday
sharh/xulosa CHIQARMAYDI, foydalanuvchi o'zi ko'rib xulosa qiladi (Phase 7'dagi
"halal qarorni o'zi hisoblama" printsipi bilan bir oilada: bu yerda "strategiya
yaxshi/yomon" degan qarorni ham kod o'zi chiqarmaydi).
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import pandas as pd

from journal.types import JournalEntry

DEFAULT_JOURNAL_PATH: Path = Path(__file__).resolve().parent.parent / "trade_journal.csv"

_COLUMNS = [
    "entry_id", "symbol", "entry_date", "entry_price", "stop_price", "target_price",
    "exit_mode", "reason", "rr_planned", "notes", "exit_date", "exit_price", "r_multiple",
]


def _none_if_nan(value: object) -> float | None:
    """CSV'dan o'qilgan bo'sh katak (NaN) qiymatini None'ga aylantiradi."""
    if pd.isna(value):
        return None
    return float(value)


class TradeJournal:
    """Foydalanuvchi qo'lda boshqaradigan haqiqiy savdo yozuvlari ro'yxati — CSV'da saqlanadi."""

    def __init__(self, csv_path: Path | str = DEFAULT_JOURNAL_PATH) -> None:
        self.csv_path = Path(csv_path)
        self.entries: list[JournalEntry] = self._load()

    def add_entry(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        stop_price: float,
        target_price: float | None,
        exit_mode: str,
        reason: str,
        notes: str = "",
    ) -> JournalEntry:
        """Yangi savdo yozuvini qo'shadi va CSV'ga saqlaydi. rr_planned avtomatik hisoblanadi
        (target_price berilgan va risk>0 bo'lsa; aks holda None — masalan trailing exit_mode'da)."""
        rr_planned = None
        if target_price is not None:
            risk = entry_price - stop_price
            if risk > 0:
                rr_planned = (target_price - entry_price) / risk

        next_id = max((e.entry_id for e in self.entries), default=0) + 1
        entry = JournalEntry(
            entry_id=next_id,
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            exit_mode=exit_mode,
            reason=reason,
            rr_planned=rr_planned,
            notes=notes,
        )
        self.entries.append(entry)
        self._save()
        return entry

    def close_entry(
        self, entry_id: int, exit_date: date, exit_price: float, notes: str | None = None,
    ) -> JournalEntry:
        """entry_id bo'yicha yozuvni yopadi (r_multiple hisoblanadi) va saqlaydi.

        Yozuv frozen dataclass bo'lgani uchun MUTATSIYA emas — dataclasses.replace
        bilan yangi (yopilgan) nusxa yaratilib, ro'yxatdagi eskisi bilan almashtiriladi
        (loyihaning boshqa barcha data modellari — SwingPoint, Zone, TradeSetup,
        TradeResult — ham frozen, shu konvensiyaga mos).
        """
        for i, entry in enumerate(self.entries):
            if entry.entry_id == entry_id:
                risk = entry.entry_price - entry.stop_price
                r_multiple = (exit_price - entry.entry_price) / risk if risk > 0 else None
                updated = replace(
                    entry,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    r_multiple=r_multiple,
                    notes=notes if notes is not None else entry.notes,
                )
                self.entries[i] = updated
                self._save()
                return updated
        raise ValueError(f"entry_id={entry_id} topilmadi")

    def stats(self) -> dict:
        """Rejalashtirilgan R:R vs amalga oshgan expectancy — raqamlar, sharh emas.

        avg_rr_planned barcha (ochiq+yopiq) rr_planned NOT None yozuvlar bo'yicha —
        bu REJALASHTIRILGAN qiymat, natijani bilish shart emas. Qolgan hammasi
        FAQAT yopilgan yozuvlar bo'yicha (hali natija yo'q ochiq savdolar
        statistikaga kiritilmaydi).
        """
        closed = [e for e in self.entries if e.exit_price is not None]
        rr_values = [e.rr_planned for e in self.entries if e.rr_planned is not None]
        avg_rr_planned = sum(rr_values) / len(rr_values) if rr_values else None

        if not closed:
            return {
                "num_entries": len(self.entries),
                "num_open": len(self.entries),
                "num_closed": 0,
                "avg_rr_planned": avg_rr_planned,
                "avg_r_realized": None,
                "win_rate": 0.0,
                "avg_win_r": None,
                "avg_loss_r": None,
                "expectancy_r": 0.0,
            }

        r_values = [e.r_multiple for e in closed]
        wins = [r for r in r_values if r > 0]
        losses = [r for r in r_values if r <= 0]

        win_rate = len(wins) / len(closed)
        avg_win_r = sum(wins) / len(wins) if wins else None
        avg_loss_r = sum(losses) / len(losses) if losses else None

        # expectancy_r = win_rate*avg_win_r + loss_rate*avg_loss_r — backtest/metrics.py::
        # expectancy_r bilan BIR XIL dekompozitsiya formulasi, shu yerda JournalEntry ustida.
        win_component = win_rate * (avg_win_r or 0.0)
        loss_component = (len(losses) / len(closed)) * (avg_loss_r or 0.0)
        expectancy_r = win_component + loss_component

        return {
            "num_entries": len(self.entries),
            "num_open": len(self.entries) - len(closed),
            "num_closed": len(closed),
            "avg_rr_planned": avg_rr_planned,
            "avg_r_realized": sum(r_values) / len(r_values),
            "win_rate": win_rate,
            "avg_win_r": avg_win_r,
            "avg_loss_r": avg_loss_r,
            "expectancy_r": expectancy_r,
        }

    def _load(self) -> list[JournalEntry]:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            return []
        df = pd.read_csv(self.csv_path)
        if df.empty:
            return []

        entries: list[JournalEntry] = []
        for _, row in df.iterrows():
            entries.append(
                JournalEntry(
                    entry_id=int(row["entry_id"]),
                    symbol=str(row["symbol"]),
                    entry_date=date.fromisoformat(row["entry_date"]),
                    entry_price=float(row["entry_price"]),
                    stop_price=float(row["stop_price"]),
                    target_price=_none_if_nan(row["target_price"]),
                    exit_mode=str(row["exit_mode"]),
                    reason="" if pd.isna(row["reason"]) else str(row["reason"]),
                    rr_planned=_none_if_nan(row["rr_planned"]),
                    notes="" if pd.isna(row["notes"]) else str(row["notes"]),
                    exit_date=None if pd.isna(row["exit_date"]) else date.fromisoformat(row["exit_date"]),
                    exit_price=_none_if_nan(row["exit_price"]),
                    r_multiple=_none_if_nan(row["r_multiple"]),
                )
            )
        return entries

    def _save(self) -> None:
        rows = []
        for e in self.entries:
            d = asdict(e)
            d["entry_date"] = e.entry_date.isoformat()
            d["exit_date"] = e.exit_date.isoformat() if e.exit_date else None
            rows.append(d)
        df = pd.DataFrame(rows, columns=_COLUMNS)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.csv_path, index=False)
