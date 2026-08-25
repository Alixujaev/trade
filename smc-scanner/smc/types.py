"""SMC struktura tahlili uchun data modellari."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import pandas as pd


class SwingKind(Enum):
    """Swing turi: eng yuqori (HIGH) yoki eng past (LOW) nuqta."""

    HIGH = auto()
    LOW = auto()


class SwingLabel(Enum):
    """Struktura labeli — oldingi shu turdagi swing bilan solishtirish natijasi."""

    HH = auto()  # Higher High
    HL = auto()  # Higher Low
    LH = auto()  # Lower High
    LL = auto()  # Lower Low


@dataclass(frozen=True)
class SwingPoint:
    """Bitta tasdiqlangan (confirmed) swing nuqtasi."""

    timestamp: pd.Timestamp
    price: float
    kind: SwingKind
    label: SwingLabel | None  # o'sha turdagi birinchi swing uchun None
    index_pos: int  # DataFrame'dagi integer pozitsiya (downstream/iloc uchun)
    confirmed_index_pos: int  # index_pos + lookback — swing haqiqatan TANILADIGAN bar


class StructureState(Enum):
    """Market struktura trendi: yo'nalish holati."""

    BULLISH = auto()
    BEARISH = auto()


class StructureEventType(Enum):
    """Struktura hodisasi turi: trend davomi yoki o'zgarishi."""

    BOS = auto()  # Break of Structure — trend davomi
    CHOCH = auto()  # Change of Character — trend o'zgarishi


@dataclass(frozen=True)
class StructureEvent:
    """Bitta BOS yoki CHoCH hodisasi (candle CLOSE bilan tasdiqlangan)."""

    timestamp: pd.Timestamp  # break tasdiqlangan candle vaqti
    event_type: StructureEventType
    direction: StructureState  # break natijasidagi yo'nalish
    broken_level: float  # buzilgan swing narxi
    broken_swing_ts: pd.Timestamp  # buzilgan swing timestamp'i
    broken_swing_index_pos: int  # buzilgan swing'ning integer pozitsiyasi
    index_pos: int  # break candle'ning integer pozitsiyasi
