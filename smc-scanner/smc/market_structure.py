"""BOS (Break of Structure) va CHoCH (Change of Character) aniqlash.

Ta'riflar (retail SMC standarti):
- BOS = trend DAVOMI tasdig'i: bullish trendda oxirgi swing HIGH, bearish
  trendda oxirgi swing LOW yo'nalish bo'yicha buziladi.
- CHoCH = trend O'ZGARISHI birinchi belgisi: bullish trendda oxirgi swing
  LOW (Higher Low), bearish trendda oxirgi swing HIGH (Lower High)
  teskari tomonga buziladi — bu trend holatini AG'DARADI.

Break tasdig'i FAQAT candle CLOSE bilan — wick teginish break EMAS. Har bir
swing level buzilgach FAQAT BIR MARTA ishlatiladi ("iste'mol qilinadi"),
qayta trigger bermaydi.

Lookahead bias yo'q: level faqat swing'ning `confirmed_index_pos`'idan
boshlab "faol" hisoblanadi (`index_pos` emas) — chunki swing haqiqatan
o'sha yerda tasdiqlanadi (fractal detection lookback lag'i sababli).

Bootstrap (boshlang'ich trend): state ikki mustaqil, JIM (event chiqarmaydigan)
yo'l bilan o'rnatiladi — (1) HH/LL labelli swing tasdiqlansa, yoki (2) narx
birinchi faol level'ni close bilan buzsa. Aniqlanmaguncha state=None va hech
qanday BOS/CHoCH chiqarilmaydi.
"""

from __future__ import annotations

import pandas as pd

from smc.types import (
    StructureEvent,
    StructureEventType,
    StructureState,
    SwingKind,
    SwingLabel,
    SwingPoint,
)


def _walk_structure(
    df: pd.DataFrame, swings: list[SwingPoint]
) -> tuple[list[StructureEvent], StructureState | None]:
    """Swing'lar va narx bo'ylab yurib, BOS/CHoCH event'larni va oxirgi trend holatini hisoblaydi."""
    if len(swings) < 2:
        return [], None

    swings_sorted = sorted(swings, key=lambda s: s.confirmed_index_pos)
    closes = df["close"].to_numpy()
    n = len(df)

    state: StructureState | None = None
    active_high: SwingPoint | None = None
    active_low: SwingPoint | None = None
    events: list[StructureEvent] = []
    swing_idx = 0
    start = swings_sorted[0].confirmed_index_pos

    for i in range(start, n):
        state_before = state  # shu candle ichida ikkala break ham SHU holatga nisbatan baholanadi
        close = closes[i]

        if active_high is not None and close > active_high.price:
            broken = active_high
            active_high = None
            if state_before is None:
                state = StructureState.BULLISH  # bootstrap: birinchi break, event yo'q
            else:
                event_type = (
                    StructureEventType.BOS
                    if state_before is StructureState.BULLISH
                    else StructureEventType.CHOCH
                )
                state = StructureState.BULLISH
                events.append(
                    StructureEvent(
                        timestamp=df.index[i],
                        event_type=event_type,
                        direction=StructureState.BULLISH,
                        broken_level=broken.price,
                        broken_swing_ts=broken.timestamp,
                        broken_swing_index_pos=broken.index_pos,
                        index_pos=i,
                    )
                )

        # Alohida `if` (elif EMAS) — eski buzilmagan high va yangi low
        # bir vaqtda (bir candle'da) buzilishi mumkin (ikkalasi mustaqil narx darajalari)
        if active_low is not None and close < active_low.price:
            broken = active_low
            active_low = None
            if state_before is None:
                state = StructureState.BEARISH
            else:
                event_type = (
                    StructureEventType.BOS
                    if state_before is StructureState.BEARISH
                    else StructureEventType.CHOCH
                )
                state = StructureState.BEARISH
                events.append(
                    StructureEvent(
                        timestamp=df.index[i],
                        event_type=event_type,
                        direction=StructureState.BEARISH,
                        broken_level=broken.price,
                        broken_swing_ts=broken.timestamp,
                        broken_swing_index_pos=broken.index_pos,
                        index_pos=i,
                    )
                )

        # Shu candle'da yangi tasdiqlangan (confirmed_index_pos == i) swing'larni qabul qilamiz.
        # Eslatma: bir xil i'da HIGH va LOW ikkalasi ham bootstrap shartini qanoatlantirsa,
        # HIGH birinchi qayta ishlanadi (ro'yxat tartibi bo'yicha) — shu holatda HIGH g'olib chiqadi.
        while swing_idx < len(swings_sorted) and swings_sorted[swing_idx].confirmed_index_pos == i:
            swing = swings_sorted[swing_idx]
            if swing.kind is SwingKind.HIGH:
                active_high = swing
                if state is None and swing.label is SwingLabel.HH:
                    state = StructureState.BULLISH
            else:
                active_low = swing
                if state is None and swing.label is SwingLabel.LL:
                    state = StructureState.BEARISH
            swing_idx += 1

    return events, state


def detect_structure_events(df: pd.DataFrame, swings: list[SwingPoint]) -> list[StructureEvent]:
    """Xronologik BOS/CHoCH event ro'yxatini qaytaradi."""
    events, _ = _walk_structure(df, swings)
    return events


def current_structure_state(df: pd.DataFrame, swings: list[SwingPoint]) -> StructureState | None:
    """Ma'lumot oxiridagi joriy trend holatini qaytaradi (hali event chiqmagan bo'lsa ham)."""
    _, state = _walk_structure(df, swings)
    return state
