"""V1 ASOSIY setup: breakout + retest state machine (TZ 8.1-8.2). LONG-ONLY.

Holatlar: IDLE -> BREAKOUT_CONFIRMED -> WAITING_RETEST -> RETEST_CONFIRMED ->
ENTRY_READY. Har resistance zonasi uchun:
    1. Narx resistance'ni CLOSE bilan buzadi + volume tasdig'i (+ ixtiyoriy trend filtri)
    2. Eski resistance'ga (endi support) retest
    3. Bullish tasdiq shamchasi (breakout darajasidan yuqorida yopilish)
    4. Tasdiq shamchasi close'ida entry

smc/signal.py tuzilishini ko'zgu qiladi: seriyalar bir marta oldindan hisoblanadi,
keyin har zona uchun pure "birinchi hit" forward-scan helper'lari bilan oldinga
skanerlash (lookahead'siz — smc/zones.py::_scan_fill konvensiyasi).

MUHIM: bu funksiya "bir vaqtda 1 pozitsiya" qoidasini QO'LLAMAYDI — pozitsiya
cheklovi backtest.engine.run_backtest ichida (smc/signal.py bilan bir xil ajratish).
"""

from __future__ import annotations

import pandas as pd

from config.settings import (
    ATR_PERIOD,
    BREAKOUT_SL_ATR_MULT,
    BREAKOUT_STOP_MODE,
    BREAKOUT_TP_R_MULTIPLE,
    CONFIRMATION_MAX_BARS,
    MIN_BREAKOUT_RR,
    RETEST_MAX_BARS,
    RETEST_TOLERANCE_ATR_MULT,
    SWING_LOOKBACK,
    VOLUME_BREAKOUT_RATIO,
    VOLUME_MA_PERIOD,
)
from indicators.volume import volume_ratio
from levels.support_resistance import detect_sr_zones, nearest_resistance_above
from levels.types import SRZone, SRZoneKind
from smc.signal import compute_planned_rr
from smc.types import StructureState, TradeSetup
from smc.zones import compute_atr
from strategy.trend import compute_trend_regime, trend_regime_at
from strategy.types import TrendRegime


def _atr_at(atr: pd.Series, index_pos: int) -> float:
    """ATR[index_pos] — NaN yoki chegaradan tashqari bo'lsa 0.0."""
    if 0 <= index_pos < len(atr):
        value = atr.iloc[index_pos]
        if pd.notna(value):
            return float(value)
    return 0.0


def _first_breakout(
    closes,
    vr: pd.Series,
    regime: pd.Series,
    zone: SRZone,
    *,
    start: int,
    volume_ratio_min: float,
    require_trend: bool,
) -> int | None:
    """`start`dan boshlab birinchi bar `b`: close > zone.top + volume tasdig'i (+ trend)."""
    n = len(closes)
    for b in range(max(start, 0), n):
        if closes[b] <= zone.top:
            continue
        ratio = vr.iloc[b]
        if pd.isna(ratio) or ratio < volume_ratio_min:
            continue
        if require_trend and trend_regime_at(regime, b) is not TrendRegime.BULLISH:
            continue
        return b
    return None


def _first_retest(
    lows,
    closes,
    atr: pd.Series,
    zone: SRZone,
    *,
    breakout_pos: int,
    tolerance_atr_mult: float,
    max_bars: int,
) -> tuple[int | None, int | None]:
    """Breakout'dan keyin retest barini qidiradi.

    Qaytaradi (retest_pos, invalidation_pos). Ikkalasi ham None -> oyna ichida
    retest ham, bekor bo'lish ham yo'q (chaqiruvchi oynadan keyin qayta boshlaydi).
    """
    n = len(lows)
    last = min(breakout_pos + max_bars, n - 1)
    for j in range(breakout_pos + 1, last + 1):
        tol = tolerance_atr_mult * _atr_at(atr, j)
        if closes[j] < zone.bottom - tol:
            return None, j  # breakout close bilan bekor bo'ldi
        touched_from_above = zone.bottom - tol <= lows[j] <= zone.top + tol
        held_on_close = closes[j] >= zone.bottom - tol
        if touched_from_above and held_on_close:
            return j, None
    return None, None


def _first_confirmation(
    opens,
    closes,
    zone: SRZone,
    *,
    retest_pos: int,
    max_bars: int,
) -> int | None:
    """Retest'dan keyin birinchi bullish tasdiq shamchasi: close > open VA close > zone.top."""
    n = len(closes)
    last = min(retest_pos + max_bars, n - 1)
    for k in range(retest_pos, last + 1):
        if closes[k] > opens[k] and closes[k] > zone.top:
            return k
    return None


def _build_setup(
    df: pd.DataFrame,
    zone: SRZone,
    *,
    breakout_pos: int,
    retest_pos: int,
    entry_pos: int,
    atr: pd.Series,
    sr_zones: list[SRZone],
    sl_atr_mult: float,
    stop_mode: str,
    tp_r_multiple: float,
    min_rr: float,
) -> TradeSetup | None:
    """Tasdiq shamchasi close'ida entry/SL/TP hisoblab TradeSetup yasaydi (R:R gate bilan)."""
    entry_price = float(df["close"].iloc[entry_pos])
    atr_k = _atr_at(atr, entry_pos)

    structure_stop = zone.bottom - sl_atr_mult * atr_k
    atr_stop = entry_price - sl_atr_mult * atr_k
    if stop_mode == "atr":
        stop_price = atr_stop
    elif stop_mode == "widest":
        stop_price = min(structure_stop, atr_stop)
    else:  # "structure" (default)
        stop_price = structure_stop

    risk = entry_price - stop_price
    if risk <= 0:
        return None

    res = nearest_resistance_above(sr_zones, entry_price, entry_pos)
    if res is not None and (res.bottom - entry_price) / risk >= min_rr:
        target_price = res.bottom
        target_source = "resistance"
    else:
        target_price = entry_price + tp_r_multiple * risk
        target_source = "fallback"

    setup = TradeSetup(
        entry_ts=df.index[entry_pos],
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        direction=StructureState.BULLISH,
        entry_index_pos=entry_pos,
        reason=f"BREAKOUT_RETEST@{zone.bottom:.2f}-{zone.top:.2f}",
        breakout_index_pos=breakout_pos,
        retest_index_pos=retest_pos,
        target_source=target_source,
    )

    rr = compute_planned_rr(setup)
    if rr is None or rr < min_rr:
        return None
    return setup


def generate_breakout_retest_signals(
    df: pd.DataFrame,
    *,
    lookback: int = SWING_LOOKBACK,
    atr_period: int = ATR_PERIOD,
    volume_ma_period: int = VOLUME_MA_PERIOD,
    volume_ratio_min: float = VOLUME_BREAKOUT_RATIO,
    retest_tolerance_atr_mult: float = RETEST_TOLERANCE_ATR_MULT,
    retest_max_bars: int = RETEST_MAX_BARS,
    confirmation_max_bars: int = CONFIRMATION_MAX_BARS,
    sl_atr_mult: float = BREAKOUT_SL_ATR_MULT,
    stop_mode: str = BREAKOUT_STOP_MODE,
    tp_r_multiple: float = BREAKOUT_TP_R_MULTIPLE,
    min_rr: float = MIN_BREAKOUT_RR,
    require_trend: bool = True,
) -> list[TradeSetup]:
    """Lookahead'siz LONG breakout+retest setup'lar (entry_index_pos bo'yicha saralangan).

    Yetarsiz data yoki resistance zonasi yo'q -> [] (TZ 23).
    """
    if len(df) < 2 * lookback + 1:
        return []

    sr_zones = detect_sr_zones(df, lookback=lookback, atr_period=atr_period)
    resistance_zones = [z for z in sr_zones if z.kind is SRZoneKind.RESISTANCE]
    if not resistance_zones:
        return []

    regime = compute_trend_regime(df)
    atr = compute_atr(df, atr_period)
    vr = volume_ratio(df, period=volume_ma_period)

    opens = df["open"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    raw: list[TradeSetup] = []
    for zone in resistance_zones:
        cursor = zone.confirmed_index_pos
        while cursor < len(df):
            b = _first_breakout(
                closes, vr, regime, zone,
                start=cursor, volume_ratio_min=volume_ratio_min, require_trend=require_trend,
            )
            if b is None:
                break

            retest_pos, invalidation_pos = _first_retest(
                lows, closes, atr, zone,
                breakout_pos=b, tolerance_atr_mult=retest_tolerance_atr_mult, max_bars=retest_max_bars,
            )
            if retest_pos is None:
                cursor = (invalidation_pos + 1) if invalidation_pos is not None else (b + retest_max_bars + 1)
                continue

            k = _first_confirmation(
                opens, closes, zone, retest_pos=retest_pos, max_bars=confirmation_max_bars
            )
            if k is None:
                cursor = retest_pos + 1
                continue

            setup = _build_setup(
                df, zone,
                breakout_pos=b, retest_pos=retest_pos, entry_pos=k, atr=atr, sr_zones=sr_zones,
                sl_atr_mult=sl_atr_mult, stop_mode=stop_mode, tp_r_multiple=tp_r_multiple, min_rr=min_rr,
            )
            if setup is not None:
                raw.append(setup)
            cursor = k + 1

    # Bir xil entry barida bir nechta zona -> eng yaqin (eng kech) breakout'ni saqlab, bittaga tushiramiz.
    raw.sort(key=lambda s: (s.entry_index_pos, -(s.breakout_index_pos or 0)))
    deduped: list[TradeSetup] = []
    seen: set[int] = set()
    for setup in raw:
        if setup.entry_index_pos not in seen:
            seen.add(setup.entry_index_pos)
            deduped.append(setup)

    deduped.sort(key=lambda s: s.entry_index_pos)
    return deduped
