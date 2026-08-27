"""Minimal LONG-ONLY signal engine: struktura + zona retest'idan entry setup topadi.

Entry shartlari (hammasi bajarilishi kerak):
    a) Yaqinda bullish CHoCH bo'lgan (struktura bullish'ga o'tgan)
    b) Struktura hali bullish (bearish CHoCH bilan bekor bo'lmagan)
    c) Narx ochiq (unfilled) BULLISH zonaga (FVG yoki OB) kirgan (retest)

(a)+(b) birgalikda: joriy struktura holati BULLISH va oxirgi CHoCH ham BULLISH
bo'lishi kerak (CHoCH doim yo'nalishni AG'DARADI, BOS esa yo'q — shuning uchun
agar joriy holat BULLISH bo'lsa va hech bo'lmaganda bitta CHoCH sodir bo'lgan
bo'lsa, oxirgi CHoCH albatta BULLISH bo'lishi SHART; shunga qaramay ikkalasini
alohida kuzatamiz — aniqlik va kelajakdagi o'zgarishlarga chidamlilik uchun).

Zona relevantligi: faqat JORIY bullish leg davomida (oxirgi CHoCH'dan keyin
yoki AYNAN o'sha barda) hosil bo'lgan zonalar hisobga olinadi — eski, tarixiy
bullish davrga tegishli zonalar (keyin bearish CHoCH bilan bekor qilingan)
qayta ishlatilmaydi. `>=` ishlatiladi (qat'iy `>` emas) — chunki Order Block'ning
`created_index_pos`'i (displacement candle) ba'zan AYNAN CHoCH'ni tasdiqlovchi
barning o'zi bo'lishi mumkin.

Retest trigger: zonaning O'ZINING oldindan hisoblangan `filled_index_pos`'i
ishlatiladi (qayta narx-skanerlash shart emas) — bu lookahead'siz, chunki
`filled_index_pos` konstruksiyasi bo'yicha faqat o'sha barga (yoki undan oldingi
barlarga) tegishli ma'lumot bilan aniqlanadi (smc/zones.py::_scan_fill birinchi
kesishuvda to'xtaydi).

Entry narxi: `min(zona.top, shu bar high)` — CHUNKI zona "to'ldi" sharti shunchaki
narx oralig'i kesishuvi (`high>=bottom va low<=top`), "narx top'ga yetdi" degani
EMAS. Agar bar zonaga PASTDAN kirib, top'gacha yetmagan bo'lsa (`high < top`),
`zona.top`da turgan limit order HECH QACHON to'lmagan bo'lardi — shu holatda
entry narxi shu barning haqiqiy high'i bilan cheklanadi (yanada konservativ,
haqiqatan erishilgan narx).

STOP: zona bottom'idan ozgina pastda (`bottom - STOP_BUFFER_ATR_MULT * ATR`).
TARGET: entry vaqtida MA'LUM bo'lgan (`confirmed_index_pos <= entry bar`) eng
yaqin (narx bo'yicha) swing HIGH; topilmasa — R-multiple fallback.

MUHIM: bu funksiya "bir vaqtda 1 pozitsiya" qoidasini QO'LLAMAYDI — u signal
qatorlari bir-biriga vaqt bo'yicha ustma-ust tushishi mumkin bo'lgan holatda ham
har bir potensial trigger'ni qaytaradi. Pozitsiya cheklovi backtest.engine.run_backtest
ichida amalga oshiriladi, chunki faqat u savdo natijalarini (stop/target qachon
tegishini) simulyatsiya qiladi va "ochiq savdo" nima ekanini biladi — bu yerda
takrorlashdan qochish uchun ataylab shunday ajratilgan.
"""

from __future__ import annotations

import pandas as pd

from config.settings import DEFAULT_TARGET_R_MULTIPLE, STOP_BUFFER_ATR_MULT, SWING_LOOKBACK
from smc.market_structure import detect_structure_events
from smc.structure import detect_swings
from smc.types import (
    StructureEvent,
    StructureEventType,
    StructureState,
    SwingKind,
    TradeSetup,
    Zone,
)
from smc.zones import compute_atr, detect_fvgs, detect_order_blocks


def generate_signals(
    df: pd.DataFrame, *, lookback: int = SWING_LOOKBACK, mult: float | None = None
) -> list[TradeSetup]:
    """Lookahead'siz LONG entry setup'lar ro'yxatini qaytaradi (xronologik tartibda)."""
    swings = detect_swings(df, lookback=lookback)
    events = detect_structure_events(df, swings)
    bullish_zones = [
        z
        for z in detect_fvgs(df, mult=mult) + detect_order_blocks(df, mult=mult)
        if z.direction is StructureState.BULLISH
    ]

    if not bullish_zones or len(df) == 0:
        return []

    atr = compute_atr(df)

    events_by_pos: dict[int, list[StructureEvent]] = {}
    for e in events:
        events_by_pos.setdefault(e.index_pos, []).append(e)

    zones_by_fill_pos: dict[int, list[Zone]] = {}
    for z in bullish_zones:
        if z.filled_index_pos is not None:
            zones_by_fill_pos.setdefault(z.filled_index_pos, []).append(z)

    highs = df["high"].to_numpy()

    state: StructureState | None = None
    last_choch_index_pos: int | None = None
    last_choch_direction: StructureState | None = None

    signals: list[TradeSetup] = []

    for i in range(len(df)):
        for event in events_by_pos.get(i, []):
            state = event.direction
            if event.event_type is StructureEventType.CHOCH:
                last_choch_index_pos = event.index_pos
                last_choch_direction = event.direction

        if state is not StructureState.BULLISH or last_choch_direction is not StructureState.BULLISH:
            continue

        for zone in zones_by_fill_pos.get(i, []):
            if zone.created_index_pos < last_choch_index_pos:
                continue  # joriy bullish leg'dan oldingi eski zona

            entry_price = min(zone.top, float(highs[i]))

            atr_i = atr.iloc[i]
            buffer = STOP_BUFFER_ATR_MULT * (0.0 if pd.isna(atr_i) else float(atr_i))
            stop_price = zone.bottom - buffer

            candidate_targets = [
                s.price
                for s in swings
                if s.kind is SwingKind.HIGH and s.confirmed_index_pos <= i and s.price > entry_price
            ]
            if candidate_targets:
                target_price = min(candidate_targets)
            else:
                target_price = entry_price + DEFAULT_TARGET_R_MULTIPLE * (entry_price - stop_price)

            signals.append(
                TradeSetup(
                    entry_ts=df.index[i],
                    entry_price=entry_price,
                    stop_price=stop_price,
                    target_price=target_price,
                    direction=StructureState.BULLISH,
                    entry_index_pos=i,
                    reason=zone.zone_type.name,
                )
            )

    return signals


def compute_planned_rr(setup: TradeSetup) -> float | None:
    """Rejalashtirilgan R:R: (target_price-entry_price)/(entry_price-stop_price).
    risk<=0 chekka holatida None. scripts/tactical_scan.py::build_scan_row VA
    backtest solishtiruvi (scripts/rr_filter_comparison.py) shu BITTA formuladan
    foydalanadi — takrorlanmaydi."""
    risk = setup.entry_price - setup.stop_price
    if risk <= 0:
        return None
    return (setup.target_price - setup.entry_price) / risk


def filter_by_planned_rr(signals: list[TradeSetup], min_rr: float | None) -> list[TradeSetup]:
    """min_rr=None -> signals o'zgarishsiz (hozirgi xatti-harakat). Aks holda faqat
    compute_planned_rr(s) >= min_rr bo'lgan setup'lar qoladi. Lookahead xavfi YO'Q —
    TradeSetup'lar allaqachon generate_signals() ichida lookahead'siz hisoblangan
    (bu funksiya faqat tayyor ro'yxatning SUBSET'ini tanlaydi, hech narsani qayta
    hisoblamaydi/o'zgartirmaydi)."""
    if min_rr is None:
        return signals
    return [s for s in signals if (rr := compute_planned_rr(s)) is not None and rr >= min_rr]
