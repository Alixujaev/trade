"""Signal dedup/cooldown store (TZ 18) — ko'rilgan signal_id'larni + ko'rsatilgan
vaqtni saqlaydi, bir xil setup cooldown o'tmasdan qayta yuborilmasin.

Journal (haqiqiy savdo yozuvlari, journal/trade_journal.py) KEYINGI qadam — bu
yerda saqlanadigan narsa jadval EMAS, oddiy id->vaqt xaritasi, shuning uchun
CSV o'rniga yengil JSON fayl ishlatiladi (DB migratsiya shart emas).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DEDUP_PATH: Path = Path(__file__).resolve().parent.parent / "signal_dedup.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DedupStore:
    """signal_id -> oxirgi ko'rsatilgan vaqt (ISO8601 UTC), JSON faylda saqlanadi.

    path=None bo'lsa DEFAULT_DEDUP_PATH ishlatiladi — bu bare-name lookup EMAS,
    __init__ ichida dinamik o'qiladi, shuning uchun testlar
    `signals.dedup.DEFAULT_DEDUP_PATH`ni monkeypatch qilib default yo'lni
    izolyatsiya qila oladi (default parametr qiymati import vaqtida "muzlab"
    qolmaydi).
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_DEDUP_PATH
        self._shown: dict[str, str] = self._load()

    def is_new(
        self, signal_id: str, *, cooldown_hours: float, now: datetime | None = None
    ) -> bool:
        """Signal avval ko'rsatilmagan, YOKI oxirgi ko'rsatilishdan beri
        cooldown_hours o'tgan bo'lsa True."""
        last_shown = self._shown.get(signal_id)
        if last_shown is None:
            return True
        elapsed = (now or _utcnow()) - datetime.fromisoformat(last_shown)
        return elapsed >= timedelta(hours=cooldown_hours)

    def mark_shown(self, signal_id: str, timestamp: datetime | None = None) -> None:
        """signal_id'ni "hozir ko'rsatildi" deb belgilaydi va darhol saqlaydi."""
        self._shown[signal_id] = (timestamp or _utcnow()).isoformat()
        self._save()

    def cleanup(self, *, older_than_hours: float, now: datetime | None = None) -> int:
        """older_than_hours'dan eski yozuvlarni o'chiradi (fayl cheksiz o'smasin
        — masalan invalidatsiya bo'lgan/eskirgan setup'lar). O'chirilgan son qaytadi."""
        cutoff = (now or _utcnow()) - timedelta(hours=older_than_hours)
        stale = [sid for sid, ts in self._shown.items() if datetime.fromisoformat(ts) < cutoff]
        for sid in stale:
            del self._shown[sid]
        if stale:
            self._save()
        return len(stale)

    def _load(self) -> dict[str, str]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return {}
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._shown, f)
