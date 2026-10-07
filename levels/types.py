"""Support/Resistance zonalari uchun data modellari (TZ 7)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class SRZoneKind(Enum):
    """S/R zona turi: qo'llab-quvvatlash (support) yoki qarshilik (resistance)."""

    SUPPORT = auto()
    RESISTANCE = auto()


@dataclass(frozen=True)
class SRZone:
    """Bitta Support yoki Resistance zonasi — ANIQ narx emas, narx TASMASI (band).

    `confirmed_index_pos` — zonani tashkil qiluvchi eng SO'NGGI swing tasdiqlangan
    bar (= a'zolarning confirmed_index_pos'i maksimumi). Zona shu bardan oldin
    "mavjud" deb bilib bo'lmaydi (lookahead bo'lardi) — smc/market_structure.py
    level-gating konvensiyasi bilan bir xil.
    """

    kind: SRZoneKind
    top: float
    bottom: float
    touch_count: int
    first_touch_index_pos: int
    last_touch_index_pos: int
    confirmed_index_pos: int
    strength: float  # 0..1 — teginish soni (0.6) + recency (0.4)
    member_index_pos: tuple[int, ...]  # zonani tashkil qilgan swing'larning index_pos'lari
