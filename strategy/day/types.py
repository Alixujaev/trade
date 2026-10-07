"""strategy/day/types.py: Day trading strategiyalari uchun ma'lumot turlari va modellar.

MUHIM:
- Bu modellar hech qachon "BUY NOW", "ENTER LONG", "STRONG BUY" kabi direktiv
  tavsiyalar bermaydi.
- Faqat holatni (status), kontekstni, mavjud dalillarni (evidence) va
  xavflarni (warnings) xolisona ko'rsatadi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import pandas as pd


class DaySetupStatus(str, Enum):
    """Day trading setup holati (non-directive)."""

    DETECTED = "DETECTED"          # Boshlang'ich setup aniqlandi (masalan, VWAP reclaim)
    CONFIRMED = "CONFIRMED"        # Setup qo'shimcha tasdiqlar bilan (RSI, RVOL, structure)
    CONFLICT = "CONFLICT"          # Qarama-qarshi kontekst (masalan, 15m bearish yoki qarshilik)
    NO_SETUP = "NO_SETUP"          # Shartlar bajarilmadi
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"  # Ma'lumot yetarli emas


class VwapRelation(str, Enum):
    """Narxning VWAP'ga nisbatan point-in-time holati."""

    VWAP_RECLAIM = "VWAP_RECLAIM"    # Oldingi bar VWAP ostida, joriy bar VWAP ustida yopildi
    VWAP_HOLD = "VWAP_HOLD"          # VWAP ustida barqaror ushlab turibdi (yaqin masofada)
    ABOVE_VWAP = "ABOVE_VWAP"        # VWAP'dan ancha yuqorida (reclaim emas, kengaygan)
    BELOW_VWAP = "BELOW_VWAP"        # VWAP ostida
    NO_RECLAIM = "NO_RECLAIM"        # Reclaim holati yo'q
    NO_DATA = "NO_DATA"              # VWAP hisoblanmagan


class MtfContext(str, Enum):
    """Ko'p vaqt oralig'i (15m MTF) konteksti."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class TriggerType(str, Enum):
    """5m vaqt oralig'idagi trigger turi."""

    BULLISH_CHOCH = "bullish CHoCH"
    PREV_HIGH_BREAK = "previous candle high break"
    BULLISH_BOS = "bullish BOS"
    NONE = "none"


@dataclass(frozen=True)
class DaySetup:
    """Kunlik (intraday) setup modeli.

    Non-directive: Hech qanday to'g'ridan-to'g'ri savdo buyrug'ini bermaydi.
    """

    symbol: str
    timestamp: pd.Timestamp
    timeframe: str = "5m"
    status: DaySetupStatus = DaySetupStatus.NO_SETUP
    setup_type: str = "VWAP_RECLAIM"

    price: float = float("nan")
    vwap: float = float("nan")
    vwap_distance: float = float("nan")
    vwap_relation: VwapRelation = VwapRelation.NO_RECLAIM
    rsi: float = float("nan")
    rvol: float = float("nan")

    structure_5m: str = "UNKNOWN"
    structure_15m: str = "UNKNOWN"

    trigger: str = "none"
    evidence: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    evidence_score: int = 0
    max_score: int = 6

    def is_valid_price(self) -> bool:
        """Narx haqiqiy musbat son ekanini tekshiradi."""
        return not math.isnan(self.price) and self.price > 0.0

    def is_valid_vwap(self) -> bool:
        """VWAP haqiqiy musbat son ekanini tekshiradi."""
        return not math.isnan(self.vwap) and self.vwap > 0.0

    def is_valid_rsi(self) -> bool:
        """RSI hisoblanganini tekshiradi."""
        return not math.isnan(self.rsi)

    def is_valid_rvol(self) -> bool:
        """RVOL hisoblanganini tekshiradi."""
        return not math.isnan(self.rvol)
