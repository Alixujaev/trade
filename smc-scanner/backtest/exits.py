"""Chiqish (exit) modellari — Exit Research v0.

Umumiy g'oya: entry generation FAQAT bir marta bajariladi (strategy/breakout_retest.py +
strategy/scoring.py); shu list o'zgarmasdan turib, har xil ExitModel orqali backtest/portfolio.py
yordamida backtest qilinadi (bitta sozlanadigan qism — `PortfolioConfig.exit_model`). Bu modul
I/O'siz (sof funksiyalar/dataclass'lar) — portfolio.py bilan bir xil konvensiya.

Adaptatsiya eslatmasi: boshlang'ich taklif qilingan interfeys
`find_exit(entry_index, entry_price, bars: list[Bar])` edi. Bu repo'da `Bar`/`list[Bar]` turi
UMUMAN yo'q — barcha lookahead-xavfsiz kod pandas DataFrame + numpy massivlar ustida
`.iloc`/pozitsiya orqali ishlaydi (backtest/engine.py, backtest/portfolio.py bilan bir xil).
Shuning uchun bu yerda `find_exit(setup, df, *, closes, highs, lows, atr)` ishlatiladi —
modellarga TradeSetup.stop_price/target_price va oldindan hisoblangan (lookahead-xavfsiz) ATR
seriyasiga to'g'ridan-to'g'ri kirish beradi, har chaqiriqda qimmat Bar-list konversiyasini
oldini oladi.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from backtest.engine import _simulate_fixed_exit
from config.settings import ATR_PERIOD, SWING_LOOKBACK, TRAIL_ATR_MULT
from smc.market_structure import detect_structure_events
from smc.structure import detect_swings
from smc.types import StructureState, TradeSetup

# ======================================================================
# Umumiy turlar
# ======================================================================


@dataclass(frozen=True)
class PartialLeg:
    """Ixtiyoriy qisman (partial) chiqish — faqat Model E (partial_tp_trailing) foydalanadi."""

    index_pos: int
    price: float
    fraction: float  # asl pozitsiyaning ulushi (masalan 0.5)
    reason: str = "partial_tp"


@dataclass(frozen=True)
class ExitResult:
    """ExitModel.find_exit natijasi.

    engine.py'ning mavjud besh-tuple'iga (exit_index_pos, exit_price, exit_reason, min_low,
    running_high) ixtiyoriy `partial` maydonini qo'shadi (default None -> A/B/C/D/F uchun mavjud
    besh-tuple bilan bir xil ma'lumot).
    """

    exit_index_pos: int
    exit_price: float
    exit_reason: str
    min_low: float
    running_high: float
    partial: PartialLeg | None = None


class ExitModel(Protocol):
    """Barcha exit modellari uchun umumiy interfeys."""

    name: str

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        """Pozitsiya uchun birinchi valid chiqishni aniqlaydi (lookahead'siz)."""
        ...


# ======================================================================
# Config dataclass'lar (frozen, config/settings.py default'laridan)
# ======================================================================


@dataclass(frozen=True)
class FixedExitConfig:
    """Model A — parametrsiz, TradeSetup.stop_price/target_price'ni o'zgartirmasdan ishlatadi."""


@dataclass(frozen=True)
class AtrExitConfig:
    """Model B — ATR-asosli SL/TP."""

    atr_period: int = ATR_PERIOD
    sl_atr_multiplier: float = 1.0  # yangi default — repo'da presedent yo'q
    tp_atr_multiplier: float = 2.0  # yangi default — repo'da presedent yo'q


@dataclass(frozen=True)
class TrailingExitConfig:
    """Model C — ATR-asosli trailing stop."""

    atr_period: int = ATR_PERIOD
    trail_atr_multiplier: float = TRAIL_ATR_MULT
    activation_r: float = 0.0  # 0.0 -> _simulate_trailing_exit bilan bit-parity


@dataclass(frozen=True)
class StructureExitConfig:
    """Model D — struktura buzilishi (BOS/CHoCH) asosidagi chiqish."""

    lookback: int = SWING_LOOKBACK


@dataclass(frozen=True)
class PartialTpTrailingExitConfig:
    """Model E — +1R'da 50% qisman TP, qolgani trailing stop."""

    partial_tp_r: float = 1.0  # yangi default — repo'da presedent yo'q
    partial_size: float = 0.5  # yangi default — repo'da presedent yo'q
    trail_atr_multiplier: float = TRAIL_ATR_MULT
    atr_period: int = ATR_PERIOD


@dataclass(frozen=True)
class TimeExitConfig:
    """Model F — vaqt asosidagi chiqish."""

    max_hold_bars: int = 20  # yangi default — repo'da presedent yo'q


@dataclass(frozen=True)
class NoExitConfig:
    """NoExit (Signal-BH) — parametrsiz. Stop yo'q, target yo'q; faqat exit qoidasini
    o'chirib, boshqa hamma narsani (risk-based sizing, concurrency, capital recycling,
    komissiya, slippage) A-F bilan bir xil ushlab turish uchun control group."""


# ======================================================================
# Model A — Fixed SL/TP (mavjud _simulate_fixed_exit'ga adapter, qayta yozilmagan)
# ======================================================================


@dataclass(frozen=True)
class FixedSLTPExit:
    """Model A: TradeSetup.stop_price/target_price'ni o'zgarishsiz ishlatadi."""

    name: str = "fixed_sl_tp"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        exit_index_pos, exit_price, exit_reason, min_low, running_high = _simulate_fixed_exit(
            df, setup, closes, highs, lows, len(df)
        )
        return ExitResult(exit_index_pos, exit_price, exit_reason, min_low, running_high)


# ======================================================================
# Model B — ATR-asosli SL/TP (stop/target ATR[entry]'dan qayta hisoblanadi, so'ng
# _simulate_fixed_exit reuse qilinadi — konservativ stop-target tie-break saqlanadi)
# ======================================================================


@dataclass(frozen=True)
class AtrSLTPExit(AtrExitConfig):
    """Model B."""

    name: str = "atr_sl_tp"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        entry_pos = setup.entry_index_pos
        atr_entry = atr.iloc[entry_pos] if 0 <= entry_pos < len(atr) else float("nan")
        if pd.isna(atr_entry):
            # ATR hali warmup'da — asl (setup'dagi) stop/target o'zgarishsiz qoladi.
            adj_setup = setup
        else:
            adj_setup = dataclasses.replace(
                setup,
                stop_price=setup.entry_price - self.sl_atr_multiplier * float(atr_entry),
                target_price=setup.entry_price + self.tp_atr_multiplier * float(atr_entry),
            )
        exit_index_pos, exit_price, exit_reason, min_low, running_high = _simulate_fixed_exit(
            df, adj_setup, closes, highs, lows, len(df)
        )
        return ExitResult(exit_index_pos, exit_price, exit_reason, min_low, running_high)


# ======================================================================
# Model C — ATR-asosli trailing stop, activation_r bilan (aktivatsiyagacha stop
# setup.stop_price'da qotib turadi; faqat kuzatilgan narx harakati asosida)
# ======================================================================


@dataclass(frozen=True)
class TrailingStopExit(TrailingExitConfig):
    """Model C."""

    name: str = "trailing_stop"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        current_stop = setup.stop_price
        running_high = setup.entry_price
        min_low = setup.entry_price
        actual_risk = setup.entry_price - setup.stop_price
        activated = False
        exit_index_pos: int | None = None
        exit_price: float | None = None
        exit_reason: str | None = None
        n = len(df)

        for j in range(setup.entry_index_pos + 1, n):
            min_low = min(min_low, float(lows[j]))

            if lows[j] <= current_stop:
                exit_index_pos, exit_price, exit_reason = j, current_stop, "trailing_stop"
                break

            if highs[j] > running_high:
                running_high = float(highs[j])
                if not activated and actual_risk > 0:
                    r = (running_high - setup.entry_price) / actual_risk
                    if r >= self.activation_r:
                        activated = True
                if activated:
                    atr_j = atr.iloc[j]
                    if not pd.isna(atr_j):  # ATR hali warmup'da -> shu bar stop o'zgarmaydi
                        candidate_stop = running_high - self.trail_atr_multiplier * float(atr_j)
                        current_stop = max(current_stop, candidate_stop)

        if exit_index_pos is None:
            exit_index_pos = n - 1
            exit_price = float(closes[-1])
            exit_reason = "end_of_data"

        return ExitResult(exit_index_pos, exit_price, exit_reason, min_low, running_high)


# ======================================================================
# Model D — struktura buzilishi (BOS/CHoCH) asosidagi chiqish
# ======================================================================


@dataclass(frozen=True)
class StructureBreakExit(StructureExitConfig):
    """Model D: long trend/struktura invalid bo'lguncha ushlab turadi.

    KRITIK (lookahead xavfi shu yerda): exit FAQAT struktura event CONFIRM bo'lgan
    barda (`StructureEvent.index_pos`) ijro etiladi — `broken_swing_index_pos`da
    (o'tmishdagi, buzilgan swing bari) EMAS. `detect_swings`/`detect_structure_events`
    o'zlari `confirmed_index_pos` konvensiyasi orqali lookahead-xavfsiz (smc/structure.py,
    smc/market_structure.py) — bu model faqat ularning natijasini iste'mol qiladi.
    """

    name: str = "structure_break"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        n = len(df)
        swings = detect_swings(df, lookback=self.lookback)
        events = detect_structure_events(df, swings)

        chosen = None
        for event in sorted(events, key=lambda e: e.index_pos):
            if event.direction is StructureState.BEARISH and event.index_pos > setup.entry_index_pos:
                chosen = event
                break

        if chosen is not None:
            exit_index_pos = chosen.index_pos
            exit_price = float(closes[exit_index_pos])
            exit_reason = "structure_break"
        else:
            exit_index_pos = n - 1
            exit_price = float(closes[-1])
            exit_reason = "end_of_data"

        min_low = setup.entry_price
        running_high = setup.entry_price
        for j in range(setup.entry_index_pos + 1, exit_index_pos + 1):
            min_low = min(min_low, float(lows[j]))
            running_high = max(running_high, float(highs[j]))

        return ExitResult(exit_index_pos, exit_price, exit_reason, min_low, running_high)


# ======================================================================
# Model E — Partial TP (+1R'da qisman yopish) + qolgan qismi uchun trailing stop
# ======================================================================


@dataclass(frozen=True)
class PartialTpTrailingExit(PartialTpTrailingExitConfig):
    """Model E: boshlang'ich 100% pozitsiya; +partial_tp_r'da partial_size ulush yopiladi;
    qolgan ulush trailing stop bilan kuzatiladi.

    ExitResult.partial (agar mavjud bo'lsa) HAR DOIM birinchi (qisman) leg; ExitResult'ning
    o'z exit_index_pos/exit_price/exit_reason maydonlari HAR DOIM oxirgi (qolgan) leg.
    Stop partial'dan OLDIN buzilsa — partial umuman yo'q (butun pozitsiya "stop" bilan
    yopiladi, boshqa modellar bilan bir xil).
    """

    name: str = "partial_tp_trailing"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        n = len(df)
        current_stop = setup.stop_price
        running_high = setup.entry_price
        min_low = setup.entry_price
        actual_risk = setup.entry_price - setup.stop_price
        partial_level = setup.entry_price + self.partial_tp_r * actual_risk

        partial_taken = False
        partial_index_pos: int | None = None
        partial_price: float | None = None

        exit_index_pos: int | None = None
        exit_price: float | None = None
        exit_reason: str | None = None

        for j in range(setup.entry_index_pos + 1, n):
            min_low = min(min_low, float(lows[j]))

            if lows[j] <= current_stop:  # konservativ: stop birinchi tekshiriladi
                exit_index_pos, exit_price = j, current_stop
                exit_reason = "trailing_stop" if partial_taken else "stop"
                break

            if not partial_taken and highs[j] >= partial_level:
                partial_taken = True
                partial_index_pos, partial_price = j, partial_level
                running_high = max(running_high, partial_level)

            if partial_taken:
                if highs[j] > running_high:
                    running_high = float(highs[j])
                atr_j = atr.iloc[j]
                if not pd.isna(atr_j):  # ATR hali warmup'da -> shu bar stop o'zgarmaydi
                    candidate_stop = running_high - self.trail_atr_multiplier * float(atr_j)
                    current_stop = max(current_stop, candidate_stop)

        partial = (
            PartialLeg(partial_index_pos, partial_price, self.partial_size)
            if partial_taken
            else None
        )

        if exit_index_pos is None:
            exit_index_pos = n - 1
            exit_price = float(closes[-1])
            exit_reason = "end_of_data"

        return ExitResult(exit_index_pos, exit_price, exit_reason, min_low, running_high, partial=partial)


# ======================================================================
# Model F — vaqt asosidagi chiqish (stop/target TEKSHIRILMAYDI — ataylab, faqat
# "vaqtning o'zi" boshqa exit modellarga nisbatan qanday ishlashini o'lchash uchun)
# ======================================================================


@dataclass(frozen=True)
class TimeBasedExit(TimeExitConfig):
    """Model F."""

    name: str = "time_exit"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        n = len(df)
        target_pos = setup.entry_index_pos + self.max_hold_bars
        exit_index_pos = min(target_pos, n - 1)
        exit_price = float(closes[exit_index_pos])
        exit_reason = "time_exit" if target_pos < n else "end_of_data"

        min_low = setup.entry_price
        running_high = setup.entry_price
        for j in range(setup.entry_index_pos + 1, exit_index_pos + 1):
            min_low = min(min_low, float(lows[j]))
            running_high = max(running_high, float(highs[j]))

        return ExitResult(exit_index_pos, exit_price, exit_reason, min_low, running_high)


# ======================================================================
# NoExit — control group (Signal-BH). Har pozitsiya oyna oxirigacha (mavjud data
# oxirigacha) ushlab turiladi. Stop/target/struktura/vaqt — hech qanday exit qoidasi yo'q.
# ======================================================================


@dataclass(frozen=True)
class NoExitExit(NoExitConfig):
    """Control group: pozitsiya OYNA OXIRIGACHA (mavjud data oxirigacha) ushlab turiladi.

    Exit modellari A-F'dan farqli, lekin constrained-BH'dan HAM farqli: bu model
    portfolio.py orqali A-F BILAN AYNAN BIR XIL yo'ldan o'tadi — xuddi shu risk-based
    sizing (_plan_entry), xuddi shu max_concurrent/max_portfolio_risk, xuddi shu
    komissiya/slippage. Bitta farq: exit qoidasi yo'q. Shu tufayli A-F vs NoExit
    solishtiruvi FAQAT exit-timing'ni izolyatsiya qiladi — constrained BH'dagi kabi
    sizing/capital-recycling confound'i yo'q (constrained BH fixed-$ sizing ishlatadi va
    hech qachon exit qilib capital recycle qilmaydi — ikkalasi ham exit qoidasidan
    mustaqil o'zgaruvchilar).
    """

    name: str = "no_exit_capped"

    def find_exit(
        self,
        setup: TradeSetup,
        df: pd.DataFrame,
        *,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        atr: pd.Series,
    ) -> ExitResult:
        n = len(df)
        exit_index_pos = n - 1
        exit_price = float(closes[-1])

        min_low = setup.entry_price
        running_high = setup.entry_price
        for j in range(setup.entry_index_pos + 1, exit_index_pos + 1):
            min_low = min(min_low, float(lows[j]))
            running_high = max(running_high, float(highs[j]))

        return ExitResult(exit_index_pos, exit_price, "NO_EXIT", min_low, running_high)


# ======================================================================
# Registry / factory
# ======================================================================

EXIT_MODEL_KEYS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "NOEXIT")

_REGISTRY: dict[str, type] = {
    "A": FixedSLTPExit,
    "B": AtrSLTPExit,
    "C": TrailingStopExit,
    "D": StructureBreakExit,
    "E": PartialTpTrailingExit,
    "F": TimeBasedExit,
    "NOEXIT": NoExitExit,
}


def build_exit_model(key: str, **overrides: object) -> ExitModel:
    """'A'..'F' -> ExitModel instance, config default'lari + ixtiyoriy overrides bilan."""
    try:
        cls = _REGISTRY[key.upper()]
    except KeyError as exc:
        raise ValueError(f"Noma'lum exit model kaliti: {key!r} (kutilgan: {EXIT_MODEL_KEYS})") from exc
    return cls(**overrides)
