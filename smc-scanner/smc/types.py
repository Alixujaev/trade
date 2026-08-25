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
