"""Klassik Support/Resistance zona aniqlash — swing narxlarini klasterlash (TZ 7).

Yondashuv: mavjud, alohida sinalgan `detect_swings` (fractal, lookahead'siz)
chiqishidan foydalaniladi. Bir necha marta yaqin narxda reaksiya bergan swing'lar
bitta narx TASMASIGA (band) birlashtiriladi. Zona kuchi = teginish soni + recency.

Lookahead bias YO'Q — klasterlash XRONOLOGIK (swing'lar `confirmed_index_pos`
tartibida qayta ishlanadi). Zona faqat `min_touches` ta teginish YIG'ILGANDA
tug'iladi va uning `confirmed_index_pos`'i aynan o'sha `min_touches`-chi teginish
tasdiqlangan bar bo'ladi — ya'ni zonaning butun BAND'i va touch_count'i shu
bargacha bo'lgan ma'lumotdan to'liq aniqlanadi. Keyingi (min_touches'dan ortiq)
teginishlar shu zonani O'ZGARTIRMAYDI — V1 uchun ataylab sodda (touch_count
`min_touches` bilan cheklangan).
"""

from __future__ import annotations

import pandas as pd

from config.settings import (
    ATR_PERIOD,
    SR_CLUSTER_ATR_MULT,
    SR_CLUSTER_PCT,
    SR_MIN_TOUCHES,
    SR_TOUCH_SATURATION,
    SWING_LOOKBACK,
)
from levels.types import SRZone, SRZoneKind
from smc.structure import detect_swings
from smc.types import SwingKind, SwingPoint
from smc.zones import compute_atr


def _tolerance_at(
    df: pd.DataFrame,
    atr: pd.Series,
    index_pos: int,
    *,
    tolerance_atr_mult: float,
    tolerance_pct: float,
) -> float:
    """`index_pos` barida klaster tasma yarim-kengligi = tolerance_atr_mult * ATR[index_pos].

    ATR NaN bo'lsa (warmup) fallback: tolerance_pct * close[index_pos]. Ikkalasi ham
    yo'q bo'lsa 0.0 (har swing alohida qoladi).
    """
    if 0 <= index_pos < len(atr):
        a = atr.iloc[index_pos]
        if pd.notna(a) and a > 0:
            return float(tolerance_atr_mult * a)
    if 0 <= index_pos < len(df):
        c = df["close"].iloc[index_pos]
        if pd.notna(c):
            return float(tolerance_pct * c)
    return 0.0


def _build_zone(members: list[SwingPoint], kind: SRZoneKind, touch_saturation: int) -> SRZone:
    """Zonani tashkil qilgan (birinchi `min_touches` ta) swing a'zolaridan SRZone yasaydi.

    `strength` — faqat teginish soniga asoslangan, LOOKAHEAD'SIZ (seriya uzunligiga
    bog'liq emas). "Recency" (zona qanchalik yaqinda teginilgan) scoring bosqichida,
    joriy barga nisbatan hisoblanadi — u yerda o'rinli.
    """
    prices = [m.price for m in members]
    index_positions = sorted(m.index_pos for m in members)
    touch_count = len(members)
    strength = round(min(touch_count / touch_saturation, 1.0), 4)

    return SRZone(
        kind=kind,
        top=float(max(prices)),
        bottom=float(min(prices)),
        touch_count=touch_count,
        first_touch_index_pos=index_positions[0],
        last_touch_index_pos=index_positions[-1],
        confirmed_index_pos=max(m.confirmed_index_pos for m in members),
        strength=strength,
        member_index_pos=tuple(index_positions),
    )


def _zones_for_group(
    group: list[SwingPoint],
    kind: SRZoneKind,
    *,
    df: pd.DataFrame,
    atr: pd.Series,
    min_touches: int,
    tolerance_atr_mult: float,
    tolerance_pct: float,
    touch_saturation: int,
) -> list[SRZone]:
    """Bir turdagi (HIGH yoki LOW) swing'lardan xronologik klasterlab zonalar yasaydi."""
    ordered = sorted(group, key=lambda s: (s.confirmed_index_pos, s.index_pos))
    open_levels: list[list[SwingPoint]] = []  # hali min_touches'ga yetmagan yig'ilayotgan darajalar
    zones: list[SRZone] = []

    for swing in ordered:
        tol = _tolerance_at(
            df, atr, swing.confirmed_index_pos,
            tolerance_atr_mult=tolerance_atr_mult, tolerance_pct=tolerance_pct,
        )
        # Narx bo'yicha eng yaqin ochiq darajani top (band + 2*tol ichida bo'lsa).
        best: list[SwingPoint] | None = None
        best_dist: float | None = None
        for level in open_levels:
            lo = min(m.price for m in level)
            hi = max(m.price for m in level)
            if lo - 2 * tol <= swing.price <= hi + 2 * tol:
                dist = abs(swing.price - (lo + hi) / 2)
                if best_dist is None or dist < best_dist:
                    best, best_dist = level, dist

        if best is None:
            open_levels.append([swing])
            continue

        best.append(swing)
        if len(best) == min_touches:
            zones.append(_build_zone(best, kind, touch_saturation))
            open_levels.remove(best)  # zona tug'ildi — daraja "yopiladi"

    return zones


def detect_sr_zones(
    df: pd.DataFrame,
    *,
    lookback: int = SWING_LOOKBACK,
    min_touches: int = SR_MIN_TOUCHES,
    tolerance_atr_mult: float = SR_CLUSTER_ATR_MULT,
    tolerance_pct: float = SR_CLUSTER_PCT,
    atr_period: int = ATR_PERIOD,
    touch_saturation: int = SR_TOUCH_SATURATION,
) -> list[SRZone]:
    """Swing narxlarini narx tasmalariga klasterlab S/R zonalari ro'yxatini qaytaradi.

    Natija `confirmed_index_pos` bo'yicha o'sish tartibida saralangan. Swing HIGH'lar
    -> RESISTANCE, swing LOW'lar -> SUPPORT. Yetarsiz data (`detect_swings` [] beradi
    yoki swing soni < min_touches) -> [] (TZ 23).
    """
    swings = detect_swings(df, lookback=lookback)
    if len(swings) < min_touches:
        return []

    atr = compute_atr(df, atr_period)
    highs = [s for s in swings if s.kind is SwingKind.HIGH]
    lows = [s for s in swings if s.kind is SwingKind.LOW]

    zones = _zones_for_group(
        highs, SRZoneKind.RESISTANCE, df=df, atr=atr, min_touches=min_touches,
        tolerance_atr_mult=tolerance_atr_mult, tolerance_pct=tolerance_pct,
        touch_saturation=touch_saturation,
    ) + _zones_for_group(
        lows, SRZoneKind.SUPPORT, df=df, atr=atr, min_touches=min_touches,
        tolerance_atr_mult=tolerance_atr_mult, tolerance_pct=tolerance_pct,
        touch_saturation=touch_saturation,
    )

    zones.sort(key=lambda z: z.confirmed_index_pos)
    return zones


def active_sr_zones_at(zones: list[SRZone], index_pos: int) -> list[SRZone]:
    """Faqat `index_pos` barida allaqachon TASDIQLANGAN zonalar (lookahead gating)."""
    return [z for z in zones if z.confirmed_index_pos <= index_pos]


def nearest_resistance_above(zones: list[SRZone], price: float, index_pos: int) -> SRZone | None:
    """`index_pos` da faol, `bottom > price` bo'lgan eng yaqin RESISTANCE zona (TP uchun).

    Topilmasa None (chaqiruvchi R-multiple fallback target ishlatadi).
    """
    candidates = [
        z
        for z in active_sr_zones_at(zones, index_pos)
        if z.kind is SRZoneKind.RESISTANCE and z.bottom > price
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda z: z.bottom)
