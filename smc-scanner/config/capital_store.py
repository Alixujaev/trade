"""Paper savdo kapitalini saqlash — JSON fayl (trade_journal.csv'ga o'xshash
oddiy fayl-asosli holat, ma'lumotlar bazasi shart emas)."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CAPITAL: float = 10_000.0
DEFAULT_CAPITAL_PATH: Path = Path(__file__).resolve().parent.parent / "paper_capital.json"


def get_capital(path: Path | str = DEFAULT_CAPITAL_PATH) -> float:
    """Saqlangan kapitalni qaytaradi; fayl mavjud bo'lmasa DEFAULT_CAPITAL (fayl yaratmasdan)."""
    path = Path(path)
    if not path.exists():
        return DEFAULT_CAPITAL
    return float(json.loads(path.read_text())["capital"])


def set_capital(value: float, path: Path | str = DEFAULT_CAPITAL_PATH) -> None:
    """Kapital qiymatini JSON faylga yozadi (mavjud qiymatni almashtiradi)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"capital": value}))
