"""Displacement, FVG (Fair Value Gap) va Order Block aniqlash.

Displacement — ATR'ga nisbatan kuchli, tez harakat qiluvchi candle. FVG va
Order Block ikkalasi ham shu tushunchaga asoslanadi: faqat displacement bilan
tasdiqlangan pattern'lar zona hisoblanadi (oddiy shovqin gap yoki tasodifiy
qarama-qarshi candle emas).

Tizim LONG-ONLY, lekin bu modul ikkala yo'nalishni ham aniqlaydi (bearish
zonalar keyingi fazalarda exit/filtr uchun kerak bo'ladi).

Lookahead bias yo'q: har bir zona faqat uni tug'diruvchi candle'lar
yopilgandan KEYIN "mavjud" deb hisoblanadi (`created_index_pos` — pattern
boshlangan bar emas, uni TASDIQLOVCHI oxirgi bar). Fill holati ham faqat
o'sha nuqtadan keyingi barlar bo'ylab, oldinga yurib hisoblanadi.
"""

from __future__ import annotations

import pandas as pd

from config.settings import ATR_PERIOD, DISPLACEMENT_ATR_MULT
from smc.types import StructureState, Zone, ZoneType


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Sodda ATR — True Range'ning rolling mean'i (Wilder smoothing EMAS).

    Sodda variant tanlandi: tushunarli, hisoblash oson, va bu loyihaning
    qisqa-swing maqsadlari uchun Wilder smoothing keltiradigan farq muhim emas.
    Birinchi `period-1` bar uchun NaN (yetarli tarix yo'q — sun'iy to'ldirilmaydi,
    aks holda lookahead/soxta signal xavfi bo'lardi). 0-bar'da prev_close yo'qligi
    sababli True Range high-low'ga tushadi (NaN'li had'lar .max()da avtomatik
    tashlab ketiladi) — bu standart konvensiya, faqat shu sabab ATR birinchi
    tasdiqlangan qiymatida (bar `period-1`da) ozgina past baholanishi mumkin;
    keyingi bar'da bu ta'sir oynadan chiqib ketadi.
    """
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean().rename("atr")


def detect_displacement(
    df: pd.DataFrame, atr_period: int = ATR_PERIOD, mult: float | None = None
) -> pd.Series:
    """Har bar uchun 0 (yo'q) / +1 (bullish) / -1 (bearish) displacement signali.

    ATR NaN bo'lgan (warmup) barlarda maxsus if shart kerak emas — NaN bilan
    solishtiruv har doim False beradi, shuning uchun displacement avtomatik 0.
    """
    mult = DISPLACEMENT_ATR_MULT if mult is None else mult
    atr = compute_atr(df, atr_period)
    body = (df["close"] - df["open"]).abs()
    strong = body >= mult * atr

    result = pd.Series(0, index=df.index, dtype=int)
    result[strong & (df["close"] > df["open"])] = 1
    result[strong & (df["close"] < df["open"])] = -1
    return result


def _scan_fill(
    df: pd.DataFrame, top: float, bottom: float, created_index_pos: int
) -> tuple[bool, pd.Timestamp | None, int | None]:
    """`created_index_pos`dan KEYINGI birinchi kesishuvni qidiradi (o'zidan emas).

    Zona shu candle'ning o'ziga tegishli chegara qiymatidan tuzilgan (masalan
    bullish FVG'da top == low[created_index_pos]), shuning uchun shu candle'ning
    o'zi har doim zonasini "to'ldiradi" — buni skanerlashdan chiqarib tashlash shart.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    for j in range(created_index_pos + 1, len(df)):
        if highs[j] >= bottom and lows[j] <= top:
            return True, df.index[j], j
    return False, None, None


def detect_fvgs(df: pd.DataFrame, atr_period: int = ATR_PERIOD, mult: float | None = None) -> list[Zone]:
    """3-candle Fair Value Gap'larni topadi — faqat displacement bilan tasdiqlangan."""
    if len(df) < 3:
        return []

    displacement = detect_displacement(df, atr_period, mult).to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    zones: list[Zone] = []
    for i in range(1, len(df) - 1):
        if displacement[i] == 1 and lows[i + 1] > highs[i - 1]:
            top, bottom = float(lows[i + 1]), float(highs[i - 1])
            filled, filled_ts, filled_pos = _scan_fill(df, top, bottom, i + 1)
            zones.append(
                Zone(
                    zone_type=ZoneType.FVG,
                    direction=StructureState.BULLISH,
                    top=top,
                    bottom=bottom,
                    created_ts=df.index[i + 1],
                    created_index_pos=i + 1,
                    filled=filled,
                    filled_ts=filled_ts,
                    filled_index_pos=filled_pos,
                )
            )
        elif displacement[i] == -1 and lows[i - 1] > highs[i + 1]:
            top, bottom = float(lows[i - 1]), float(highs[i + 1])
            filled, filled_ts, filled_pos = _scan_fill(df, top, bottom, i + 1)
            zones.append(
                Zone(
                    zone_type=ZoneType.FVG,
                    direction=StructureState.BEARISH,
                    top=top,
                    bottom=bottom,
                    created_ts=df.index[i + 1],
                    created_index_pos=i + 1,
                    filled=filled,
                    filled_ts=filled_ts,
                    filled_index_pos=filled_pos,
                )
            )
    return zones


def detect_order_blocks(
    df: pd.DataFrame, atr_period: int = ATR_PERIOD, mult: float | None = None
) -> list[Zone]:
    """Displacement'dan oldingi oxirgi qarama-qarshi rangli candle'ni Order Block deb topadi.

    Orqaga qarab qidiruv MASOFA CHEGARASISIZ — mos rangdagi candle qancha uzoqda
    bo'lmasin, birinchi (eng yaqin) topilgani ishlatiladi. Bu spec'ning aniq
    talabi ("oxirgi qarama-qarshi candle"); sun'iy chegara qo'yish over-engineering
    bo'lardi. Uzoq bir xil rangdagi ketma-ketlikda bu zonani "eskirgan" (stale)
    qilishi mumkin — bu bilib turilgan xususiyat, xato emas.
    """
    displacement = detect_displacement(df, atr_period, mult).to_numpy()
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    zones: list[Zone] = []
    for i in range(len(df)):
        if displacement[i] == 0:
            continue

        wants_bearish_ob = displacement[i] == 1  # bullish displacement -> oldingi BEARISH candle
        j = i - 1
        while j >= 0:
            is_bearish = closes[j] < opens[j]
            is_bullish = closes[j] > opens[j]
            if (wants_bearish_ob and is_bearish) or (not wants_bearish_ob and is_bullish):
                break
            j -= 1

        if j < 0:
            continue  # mos rangdagi candle topilmadi (masalan seriya boshigacha bir xil rang)

        top, bottom = float(highs[j]), float(lows[j])
        direction = StructureState.BULLISH if displacement[i] == 1 else StructureState.BEARISH
        filled, filled_ts, filled_pos = _scan_fill(df, top, bottom, i)
        zones.append(
            Zone(
                zone_type=ZoneType.ORDER_BLOCK,
                direction=direction,
                top=top,
                bottom=bottom,
                created_ts=df.index[i],
                created_index_pos=i,
                filled=filled,
                filled_ts=filled_ts,
                filled_index_pos=filled_pos,
            )
        )
    return zones
