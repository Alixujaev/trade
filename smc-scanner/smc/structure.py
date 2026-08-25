"""Swing point aniqlash va HH/HL/LH/LL struktura labellash.

MUHIM (lookahead bias): bar faqat undan keyin kamida `lookback` ta bar
kelgandan so'ng swing sifatida TASDIQLANADI — chunki o'ng tomon barlarsiz
u haqiqatan eng yuqori/past nuqta ekanini bilib bo'lmaydi. Shu sabab oxirgi
`lookback` ta bar hech qachon swing sifatida qaytarilmaydi. Bu funksiya
faqat "hozircha tasdiqlangan" swing'larni beradi — live scanning uchun
xavfsiz, kelajakni ko'rib qo'ymaydi.

Eslatma: teng (equal) high/low'lar bu bosqichda swing DEB OLINMAYDI — qat'iy
`>`/`<` solishtiruv ishlatiladi. Teng high/low'lar liquidity tahlili
fazasida (keyingi faza) alohida ishlanadi.
"""

from __future__ import annotations

import pandas as pd

from config.settings import SWING_LOOKBACK
from smc.types import SwingKind, SwingLabel, SwingPoint


def detect_swings(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> list[SwingPoint]:
    """OHLCV DataFrame'dan tasdiqlangan, labellangan swing nuqtalarni topadi.

    Fractal/pivot usuli: bar high/low'i chap va o'ng `lookback` ta bardagi
    high/low'dan qat'iy katta/kichik bo'lsa, swing hisoblanadi. Natija
    xronologik tartibda, har bir swing o'sha turdagi oldingi swing bilan
    solishtirilib labellanadi (birinchisi uchun label — None).
    """
    n = len(df)
    if n < 2 * lookback + 1:
        return []

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    raw: list[tuple[int, SwingKind, float]] = []
    for i in range(lookback, n - lookback):
        left_high = highs[i - lookback:i]
        right_high = highs[i + 1:i + 1 + lookback]
        if highs[i] > left_high.max() and highs[i] > right_high.max():
            raw.append((i, SwingKind.HIGH, float(highs[i])))

        left_low = lows[i - lookback:i]
        right_low = lows[i + 1:i + 1 + lookback]
        if lows[i] < left_low.min() and lows[i] < right_low.min():
            raw.append((i, SwingKind.LOW, float(lows[i])))

    raw.sort(key=lambda item: item[0])

    result: list[SwingPoint] = []
    last_high: float | None = None
    last_low: float | None = None
    for idx, kind, price in raw:
        if kind is SwingKind.HIGH:
            label = None if last_high is None else (
                SwingLabel.HH if price > last_high else SwingLabel.LH
            )
            last_high = price
        else:
            label = None if last_low is None else (
                SwingLabel.HL if price > last_low else SwingLabel.LL
            )
            last_low = price

        result.append(
            SwingPoint(
                timestamp=df.index[idx],
                price=price,
                kind=kind,
                label=label,
                index_pos=idx,
            )
        )

    return result
