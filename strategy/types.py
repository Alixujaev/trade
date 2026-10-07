"""V1 breakout+retest strategiyasi uchun data modellari (trend rejimi, scoring)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TrendRegime(Enum):
    """EMA 20/50/200 asosidagi bozor rejimi (TZ 5) — yakuniy signal EMAS, FILTR."""

    BULLISH = auto()
    BEARISH = auto()
    NEUTRAL = auto()  # EMA'lar tartibsiz yoki yetarli tarix yo'q (warmup)


class BreakoutState(Enum):
    """Breakout+retest state machine holatlari (TZ 8.1-8.2).

    Kod ichida bar-walk holatini kuzatish uchun (natija TradeSetup'lar ro'yxati),
    tashqi API'da to'g'ridan-to'g'ri qaytarilmaydi — hujjatlash/o'qish uchun.
    """

    IDLE = auto()
    BREAKOUT_CONFIRMED = auto()
    WAITING_RETEST = auto()
    RETEST_CONFIRMED = auto()
    ENTRY_READY = auto()


@dataclass(frozen=True)
class ScoreComponent:
    """0-100 ball ichidagi bitta komponent (trend, structure, setup, volume, smc, risk)."""

    name: str
    weight: float  # 0..1
    sub_score: float  # 0..1
    reason: str  # o'zbekcha qisqa izoh (nega shu ball)


@dataclass(frozen=True)
class SignalScore:
    """Bitta setup uchun to'liq 0-100 ball natijasi (TZ 11)."""

    total: float  # 0..100
    label: str  # "STRONG_BUY" | "BUY" | "WATCH" | "NO_TRADE"
    components: tuple[ScoreComponent, ...]
    reasons: tuple[str, ...]  # komponent izohlari (tez ko'rish uchun tekislangan)
