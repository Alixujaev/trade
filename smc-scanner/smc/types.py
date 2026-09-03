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


class ZoneType(Enum):
    """Retest qilinadigan zona turi."""

    FVG = auto()  # Fair Value Gap (imbalance)
    ORDER_BLOCK = auto()


@dataclass(frozen=True)
class Zone:
    """Bitta retest zonasi (FVG yoki Order Block).

    `created_index_pos` — zonani tug'diruvchi PATTERN'ning OXIRGI (tasdiqlovchi)
    bari, pattern boshlangan bar EMAS (masalan FVG'da bu 3-candle'ning oxirgisi,
    OB'da esa displacement candle'ning o'zi) — chunki zona shu bardan oldin
    hali "mavjud" deb bilib bo'lmaydi (lookahead bo'lardi).
    """

    zone_type: ZoneType
    direction: StructureState  # BULLISH / BEARISH
    top: float
    bottom: float
    created_ts: pd.Timestamp
    created_index_pos: int
    filled: bool = False
    filled_ts: pd.Timestamp | None = None
    filled_index_pos: int | None = None


@dataclass(frozen=True)
class TradeSetup:
    """Bitta LONG entry setup — struktura + zona retest'idan (yoki V1 breakout+retest'idan) hosil bo'lgan.

    Oxirgi to'rt maydon IXTIYORIY (default'li) — V1 breakout+retest strategiyasi
    (strategy/breakout_retest.py, strategy/scoring.py) uchun qo'shilgan. Eski
    smc/signal.py ularni to'ldirmaydi; backtest/engine.py va compute_planned_rr
    ular haqida bilmaydi va e'tiborsiz qoldiradi (moslik saqlanadi).
    """

    entry_ts: pd.Timestamp
    entry_price: float
    stop_price: float
    target_price: float
    direction: StructureState  # doim BULLISH (long-only scope) — sxema izchilligi uchun saqlanadi
    entry_index_pos: int
    reason: str  # trigger qilgan zona turi — "FVG" / "ORDER_BLOCK" / "BREAKOUT_RETEST@<band>"

    # --- V1 breakout+retest qo'shimchalari (ixtiyoriy) ---
    score: float | None = None  # 0..100 signal ball (strategy/scoring.py to'ldiradi)
    score_reasons: tuple[str, ...] = ()  # ball komponentlarining izohlari
    breakout_index_pos: int | None = None  # resistance breakout tasdiqlangan bar
    retest_index_pos: int | None = None  # eski resistance (endi support) retest qilingan bar
