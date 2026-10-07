"""strategy/day/vwap_momentum.py: DAY-01 — VWAP Momentum / VWAP Reclaim strategiyasi.

METODOLOGIK QOIDA:
- Bu strategiya validated profitable strategy emas.
- Course'dagi VWAP Momentum konseptlari boshlang'ich trading hypotheses sifatida
  implement qilingan.
- Qat'iy NO OVERFITTING: threshold'lar optimallashtirilmagan.
- Non-directive: Hech qachon "BUY NOW", "ENTER LONG", "STRONG BUY" kabi direktiv
  tavsiyalar bermaydi.
- Long-only: Short tavsiyalari mutlaqo yo'q. Bearish holat faqat CONFLICT yoki AVOID
  sifatida aks ettiriladi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import numpy as np
import pandas as pd

from data.bars import filter_closed_bars
from data.session import (
    RTH_END,
    RTH_START,
    is_rth_series,
    to_eastern,
)
from indicators.rsi import compute_rsi
from indicators.rvol import compute_rvol
from indicators.vwap import (
    compute_vwap,
    compute_vwap_distance,
)
from levels.intraday_levels import compute_intraday_levels
from smc.market_structure import (
    current_structure_state,
    detect_structure_events,
)
from smc.structure import detect_swings
from smc.types import (
    StructureEventType,
    StructureState,
    SwingKind,
    SwingLabel,
    SwingPoint,
)
from strategy.day.scoring import aggregate_day_evidence
from strategy.day.types import (
    DaySetup,
    DaySetupStatus,
    MtfContext,
    TriggerType,
    VwapRelation,
)

# Course hypothesis bo'yicha konstanta chegaralar (optimallashtirilmagan gipotezalar)
RVOL_CONFIRMATION_THRESHOLD: float = 2.0
RSI_MOMENTUM_THRESHOLD: float = 50.0
VWAP_HOLD_MAX_DISTANCE_PCT: float = 0.005  # 0.5% ichida bo'lsa hold, undan uzoq bo'lsa extended
LEVEL_PROXIMITY_PCT: float = 0.003          # 0.3% masofada bo'lsa darajaga yaqin deb ogohlantiriladi


@dataclass(frozen=True)
class PrecomputedDayFeatures:
    """Intraday barlar uchun bir martalik hisoblangan sababiy (causal) indikatorlar to'plami.

    Barcha seriyalar strictly causal: T vaqtidagi qiymat faqat T gacha yoki T dagi
    ma'lumotlarga bog'liq.
    """

    vwap: pd.Series
    rsi: pd.Series
    rvol: pd.Series
    pdh: pd.Series
    pmh: pd.Series
    pre_states_5m: list[StructureState | None]
    events_by_pos_5m: dict[int, list[tuple[StructureEventType, StructureState]]]
    pre_states_15m: list[StructureState | None]
    end_15m_series: pd.DatetimeIndex | None


def precompute_day_features(
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame | None = None,
    *,
    df_extended_5m: pd.DataFrame | None = None,
) -> PrecomputedDayFeatures:
    """Tarixiy intraday dataset ustida barcha sababiy indikatorlar va tuzilmani bir marta oldindan hisoblaydi.

    Parameters
    ----------
    df_5m : pd.DataFrame
        5m OHLCV ma'lumotlari.
    df_15m : pd.DataFrame | None, optional
        15m OHLCV ma'lumotlari (MTF kontekst uchun).
    df_extended_5m : pd.DataFrame | None, optional
        Premarket va RTH ni o'z ichiga olgan 5m ma'lumotlar (darajalar uchun).

    Returns
    -------
    PrecomputedDayFeatures
        Oldindan hisoblangan sababiy xususiyatlar to'plami.
    """
    if df_5m.empty:
        empty_s = pd.Series(dtype=float, index=df_5m.index)
        return PrecomputedDayFeatures(
            vwap=empty_s,
            rsi=empty_s,
            rvol=empty_s,
            pdh=empty_s,
            pmh=empty_s,
            pre_states_5m=[],
            events_by_pos_5m={},
            pre_states_15m=[],
            end_15m_series=None,
        )

    # 1. VWAP, RSI, RVOL hisoblash
    vwap_s = compute_vwap(df_5m, rth_only=True)
    rsi_s = compute_rsi(df_5m, period=14)
    rvol_s = compute_rvol(df_5m, lookback_sessions=20, min_sessions=1)

    # 2. Intraday levels (PDH, PMH)
    if df_extended_5m is not None and not df_extended_5m.empty:
        levels_df = compute_intraday_levels(df_extended_5m)
        pdh_s = levels_df["pdh"].reindex(df_5m.index, method="ffill")
        pmh_s = levels_df["pmh"].reindex(df_5m.index, method="ffill")
    else:
        levels_df = compute_intraday_levels(df_5m)
        pdh_s = levels_df["pdh"]
        pmh_s = levels_df["pmh"]

    # 3. 5m SMC tuzilma (single-pass causal walk)
    lookback = 2
    all_swings_5m = detect_swings(df_5m, lookback=lookback)
    swings_by_conf_5m: dict[int, list[SwingPoint]] = {}
    for s in all_swings_5m:
        swings_by_conf_5m.setdefault(s.confirmed_index_pos, []).append(s)

    n_5m = len(df_5m)
    closes_5m = df_5m["close"].to_numpy()
    state_5m: StructureState | None = None
    active_high_5m: SwingPoint | None = None
    active_low_5m: SwingPoint | None = None
    events_by_pos_5m: dict[int, list[tuple[StructureEventType, StructureState]]] = {}
    swings_seen_5m = 0
    pre_states_5m: list[StructureState | None] = [None] * n_5m

    for i in range(n_5m):
        state_before = state_5m
        close = closes_5m[i]

        if active_high_5m is not None and close > active_high_5m.price:
            active_high_5m = None
            if state_before is None:
                state_5m = StructureState.BULLISH
            else:
                event_type = (
                    StructureEventType.BOS
                    if state_before is StructureState.BULLISH
                    else StructureEventType.CHOCH
                )
                state_5m = StructureState.BULLISH
                events_by_pos_5m.setdefault(i, []).append(
                    (event_type, StructureState.BULLISH)
                )

        if active_low_5m is not None and close < active_low_5m.price:
            active_low_5m = None
            if state_before is None:
                state_5m = StructureState.BEARISH
            else:
                event_type = (
                    StructureEventType.BOS
                    if state_before is StructureState.BEARISH
                    else StructureEventType.CHOCH
                )
                state_5m = StructureState.BEARISH
                events_by_pos_5m.setdefault(i, []).append(
                    (event_type, StructureState.BEARISH)
                )

        for swing in swings_by_conf_5m.get(i, []):
            swings_seen_5m += 1
            if swing.kind is SwingKind.HIGH:
                active_high_5m = swing
                if state_5m is None and swing.label is SwingLabel.HH:
                    state_5m = StructureState.BULLISH
            else:
                active_low_5m = swing
                if state_5m is None and swing.label is SwingLabel.LL:
                    state_5m = StructureState.BEARISH

        if swings_seen_5m < 2:
            pre_states_5m[i] = None
        else:
            pre_states_5m[i] = state_5m

    # 4. 15m SMC tuzilma (single-pass causal walk)
    pre_states_15m: list[StructureState | None] = []
    end_15m_series: pd.DatetimeIndex | None = None

    if df_15m is not None and not df_15m.empty:
        all_swings_15m = detect_swings(df_15m, lookback=lookback)
        swings_by_conf_15m: dict[int, list[SwingPoint]] = {}
        for s in all_swings_15m:
            swings_by_conf_15m.setdefault(s.confirmed_index_pos, []).append(s)

        n_15m = len(df_15m)
        closes_15m = df_15m["close"].to_numpy()
        state_15: StructureState | None = None
        active_high_15: SwingPoint | None = None
        active_low_15: SwingPoint | None = None
        swings_seen_15 = 0
        pre_states_15m = [None] * n_15m

        for i in range(n_15m):
            close = closes_15m[i]
            if active_high_15 is not None and close > active_high_15.price:
                active_high_15 = None
                state_15 = StructureState.BULLISH
            if active_low_15 is not None and close < active_low_15.price:
                active_low_15 = None
                state_15 = StructureState.BEARISH

            for swing in swings_by_conf_15m.get(i, []):
                swings_seen_15 += 1
                if swing.kind is SwingKind.HIGH:
                    active_high_15 = swing
                    if state_15 is None and swing.label is SwingLabel.HH:
                        state_15 = StructureState.BULLISH
                else:
                    active_low_15 = swing
                    if state_15 is None and swing.label is SwingLabel.LL:
                        state_15 = StructureState.BEARISH

            if swings_seen_15 < 2:
                pre_states_15m[i] = None
            else:
                pre_states_15m[i] = state_15

        end_15m_series = df_15m.index + pd.Timedelta(minutes=15)

    return PrecomputedDayFeatures(
        vwap=vwap_s,
        rsi=rsi_s,
        rvol=rvol_s,
        pdh=pdh_s,
        pmh=pmh_s,
        pre_states_5m=pre_states_5m,
        events_by_pos_5m=events_by_pos_5m,
        pre_states_15m=pre_states_15m,
        end_15m_series=end_15m_series,
    )


def evaluate_vwap_momentum_at_index(
    symbol: str,
    df_5m: pd.DataFrame,
    idx: int,
    features: PrecomputedDayFeatures,
) -> DaySetup:
    """Precomputed sababiy xususiyatlar asosida belgilangan bar indeksida (idx) DAY-01 VWAP Momentum holatini baholaydi.

    O(1) murakkablikda ishlaydi va qat'iy ravishda idx va undan oldingi ma'lumotlarga tayanadi.
    """
    last_ts = df_5m.index[idx]

    # 1. Ma'lumot yetarliligini tekshirish
    if idx < 14:
        return DaySetup(
            symbol=symbol,
            timestamp=last_ts,
            timeframe="5m",
            status=DaySetupStatus.DATA_INSUFFICIENT,
            warnings=("Data insufficient: fewer than 15 bars in 5m series",),
        )

    # 2. Sessiya tekshiruvi: faqat RTH (09:30 - 16:00 ET) oralig'ida signal chiqariladi
    rth_mask = is_rth_series(pd.DatetimeIndex([last_ts]))
    if not rth_mask.iloc[0]:
        return DaySetup(
            symbol=symbol,
            timestamp=last_ts,
            timeframe="5m",
            status=DaySetupStatus.NO_SETUP,
            price=float(df_5m["close"].iloc[idx]),
            warnings=("Outside RTH session (09:30–16:00 ET)",),
        )

    # 3. Indikatorlar
    curr_vwap = float(features.vwap.iloc[idx])
    curr_price = float(df_5m["close"].iloc[idx])

    if math.isnan(curr_vwap) or curr_vwap <= 0.0:
        return DaySetup(
            symbol=symbol,
            timestamp=last_ts,
            timeframe="5m",
            status=DaySetupStatus.DATA_INSUFFICIENT,
            price=curr_price,
            warnings=("VWAP calculation not available for current session",),
        )

    vwap_dist_pct = (curr_price - curr_vwap) / curr_vwap

    # 4. RSI(14)
    curr_rsi = float(features.rsi.iloc[idx])
    is_rsi_confirmed = not math.isnan(curr_rsi) and curr_rsi > RSI_MOMENTUM_THRESHOLD

    # 5. RVOL(20)
    curr_rvol = float(features.rvol.iloc[idx])
    is_rvol_confirmed = not math.isnan(curr_rvol) and curr_rvol >= RVOL_CONFIRMATION_THRESHOLD

    # 6. Point-in-time VWAP Reclaim vs Hold vs Above vs Below
    prev_close = float(df_5m["close"].iloc[idx - 1]) if idx >= 1 else float("nan")
    prev_vwap = float(features.vwap.iloc[idx - 1]) if idx >= 1 else float("nan")

    is_above_vwap = curr_price > curr_vwap
    is_reclaim = False
    vwap_rel = VwapRelation.NO_RECLAIM

    if is_above_vwap:
        if not math.isnan(prev_close) and not math.isnan(prev_vwap) and prev_close <= prev_vwap:
            vwap_rel = VwapRelation.VWAP_RECLAIM
            is_reclaim = True
        else:
            if vwap_dist_pct <= VWAP_HOLD_MAX_DISTANCE_PCT:
                vwap_rel = VwapRelation.VWAP_HOLD
            else:
                vwap_rel = VwapRelation.ABOVE_VWAP
    else:
        vwap_rel = VwapRelation.BELOW_VWAP

    # 7. 5m SMC tuzilma va Trigger
    st_5m = features.pre_states_5m[idx]
    structure_5m_str = st_5m.name if st_5m is not None else "NEUTRAL"

    recent_events: list[tuple[StructureEventType, StructureState]] = []
    for p in range(max(0, idx - 4), idx + 1):
        if p in features.events_by_pos_5m:
            recent_events.extend(features.events_by_pos_5m[p])

    choch_events = [
        e for e in recent_events
        if e[0] is StructureEventType.CHOCH and e[1] is StructureState.BULLISH
    ]
    bos_events = [
        e for e in recent_events
        if e[0] is StructureEventType.BOS and e[1] is StructureState.BULLISH
    ]

    trigger = TriggerType.NONE.value
    if choch_events:
        trigger = TriggerType.BULLISH_CHOCH.value
    elif bos_events:
        trigger = TriggerType.BULLISH_BOS.value
    elif idx >= 1 and curr_price > float(df_5m["high"].iloc[idx - 1]):
        trigger = TriggerType.PREV_HIGH_BREAK.value

    has_5m_trigger = trigger != TriggerType.NONE.value

    # 8. 15m MTF Konteksti (Qat'iy No-Lookahead)
    structure_15m_str = MtfContext.UNKNOWN.value
    is_15m_bullish = False
    is_15m_bearish = False

    if features.end_15m_series is not None and len(features.end_15m_series) > 0:
        curr_5m_end = last_ts + pd.Timedelta(minutes=5)
        k = features.end_15m_series.searchsorted(curr_5m_end, side="right") - 1
        if k >= 4:
            st_15m = features.pre_states_15m[k]
            if st_15m is StructureState.BULLISH:
                structure_15m_str = MtfContext.BULLISH.value
                is_15m_bullish = True
            elif st_15m is StructureState.BEARISH:
                structure_15m_str = MtfContext.BEARISH.value
                is_15m_bearish = True
            else:
                structure_15m_str = MtfContext.NEUTRAL.value
        else:
            structure_15m_str = MtfContext.UNKNOWN.value

    # 9. Intraday Darajalar va Qarshilik Tekshiruvi
    warnings: list[str] = []
    if idx >= 19:
        pdh = float(features.pdh.iloc[idx]) if not features.pdh.empty else float("nan")
        pmh = float(features.pmh.iloc[idx]) if not features.pmh.empty else float("nan")

        if not math.isnan(pdh) and pdh > 0:
            dist_pdh = (pdh - curr_price) / pdh
            if 0.0 <= dist_pdh <= LEVEL_PROXIMITY_PCT:
                warnings.append("Near previous day high (PDH resistance)")

        if not math.isnan(pmh) and pmh > 0:
            dist_pmh = (pmh - curr_price) / pmh
            if 0.0 <= dist_pmh <= LEVEL_PROXIMITY_PCT:
                warnings.append("Near premarket high (PMH resistance)")

    # 10. Kontekst ogohlantirishlari
    if is_15m_bearish:
        warnings.append("15m structure is BEARISH (MTF conflict)")

    if not is_rvol_confirmed:
        if math.isnan(curr_rvol):
            warnings.append("RVOL baseline not available (insufficient historical sessions)")
        else:
            warnings.append(f"Volume not confirmed (RVOL {curr_rvol:.1f}x < 2.0x)")

    if not is_rsi_confirmed:
        if math.isnan(curr_rsi):
            warnings.append("RSI(14) not available")
        else:
            warnings.append(f"RSI momentum {curr_rsi:.1f} <= 50 (lacks bullish momentum)")

    if vwap_rel is VwapRelation.ABOVE_VWAP:
        warnings.append("Price extended above VWAP (not a fresh reclaim)")

    # 11. Dalillarni yig'ish (Evidence Aggregation)
    evidence_agg = aggregate_day_evidence(
        is_vwap_reclaim=is_reclaim,
        is_above_vwap=is_above_vwap,
        is_rsi_confirmed=is_rsi_confirmed,
        is_rvol_confirmed=is_rvol_confirmed,
        has_5m_trigger=has_5m_trigger,
        is_15m_bullish=is_15m_bullish,
        trigger_desc=trigger if has_5m_trigger else "",
        rsi_val=curr_rsi if not math.isnan(curr_rsi) else None,
        rvol_val=curr_rvol if not math.isnan(curr_rvol) else None,
    )

    # 12. Non-Directive Status Aniqlash
    if not is_above_vwap:
        status = DaySetupStatus.NO_SETUP
    elif vwap_rel is VwapRelation.ABOVE_VWAP:
        status = DaySetupStatus.NO_SETUP
    elif is_15m_bearish:
        status = DaySetupStatus.CONFLICT
    elif is_reclaim or vwap_rel is VwapRelation.VWAP_HOLD:
        if is_rsi_confirmed and is_rvol_confirmed and has_5m_trigger and is_15m_bullish:
            status = DaySetupStatus.CONFIRMED
        else:
            status = DaySetupStatus.DETECTED
    else:
        status = DaySetupStatus.NO_SETUP

    return DaySetup(
        symbol=symbol,
        timestamp=last_ts,
        timeframe="5m",
        status=status,
        setup_type="VWAP_RECLAIM" if is_reclaim else "VWAP_MOMENTUM",
        price=curr_price,
        vwap=curr_vwap,
        vwap_distance=vwap_dist_pct,
        vwap_relation=vwap_rel,
        rsi=curr_rsi,
        rvol=curr_rvol,
        structure_5m=structure_5m_str,
        structure_15m=structure_15m_str,
        trigger=trigger,
        evidence=evidence_agg.evidence_list,
        warnings=tuple(warnings),
        evidence_score=evidence_agg.score,
        max_score=evidence_agg.max_score,
    )


def evaluate_vwap_momentum(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame | None = None,
    *,
    df_extended_5m: pd.DataFrame | None = None,
    as_of: datetime | pd.Timestamp | None = None,
    features: PrecomputedDayFeatures | None = None,
) -> DaySetup:
    """5m va 15m ma'lumotlar asosida VWAP Momentum holatini baholaydi.

    Parameters
    ----------
    symbol : str
        Ticker belgisi (masalan 'AAPL').
    df_5m : pd.DataFrame
        5m OHLCV ma'lumotlari.
    df_15m : pd.DataFrame | None, optional
        15m OHLCV ma'lumotlari (MTF kontekst uchun).
    df_extended_5m : pd.DataFrame | None, optional
        Premarket va RTH ni o'z ichiga olgan 5m ma'lumotlar (darajalar uchun).
    as_of : datetime | pd.Timestamp | None, optional
        Point-in-time baholash vaqti. Agar berilsa, barcha DataFrame'lar qat'iy
        ravishda as_of gacha yopilgan barlarga filtrlanadi.
    features : PrecomputedDayFeatures | None, optional
        Oldindan hisoblangan sababiy xususiyatlar to'plami. Berilgan bo'lsa,
        evaluator O(1) rejimida ishlaydi.

    Returns
    -------
    DaySetup
        Non-directive holat, kontekst, dalillar va ogohlantirishlar.
    """
    # Point-in-time hardening: agar as_of berilgan bo'lsa, kelajak barlarni qat'iy filtrlaymiz
    if as_of is not None:
        if not df_5m.empty:
            df_5m = filter_closed_bars(df_5m, "5m", as_of=as_of)
        if df_15m is not None and not df_15m.empty:
            df_15m = filter_closed_bars(df_15m, "15m", as_of=as_of)
        if df_extended_5m is not None and not df_extended_5m.empty:
            df_extended_5m = filter_closed_bars(df_extended_5m, "5m", as_of=as_of)

    if features is not None and not df_5m.empty:
        return evaluate_vwap_momentum_at_index(
            symbol=symbol,
            df_5m=df_5m,
            idx=len(df_5m) - 1,
            features=features,
        )

    now_ts = (
        pd.Timestamp(as_of)
        if as_of is not None
        else pd.Timestamp.now(tz=timezone.utc)
    )

    # 1. Ma'lumot mavjudligini tekshirish
    if df_5m.empty or len(df_5m) < 15:
        return DaySetup(
            symbol=symbol,
            timestamp=now_ts,
            timeframe="5m",
            status=DaySetupStatus.DATA_INSUFFICIENT,
            warnings=("Data insufficient: fewer than 15 bars in 5m series",),
        )

    required_cols = {"open", "high", "low", "close", "volume"}
    if not required_cols.issubset(df_5m.columns):
        return DaySetup(
            symbol=symbol,
            timestamp=now_ts,
            timeframe="5m",
            status=DaySetupStatus.DATA_INSUFFICIENT,
            warnings=(f"Missing required OHLCV columns: {required_cols - set(df_5m.columns)}",),
        )

    # Oxirgi yopilgan 5m bar
    last_idx = df_5m.index[-1]
    last_ts = pd.Timestamp(last_idx)
    bar_time_et = to_eastern(pd.DatetimeIndex([last_ts]))[0]

    # 2. Sessiya tekshiruvi: faqat RTH (09:30 - 16:00 ET) oralig'ida signal chiqariladi
    rth_mask = is_rth_series(df_5m.index)
    if not rth_mask.iloc[-1]:
        return DaySetup(
            symbol=symbol,
            timestamp=last_ts,
            timeframe="5m",
            status=DaySetupStatus.NO_SETUP,
            price=float(df_5m["close"].iloc[-1]),
            warnings=("Outside RTH session (09:30–16:00 ET)",),
        )

    # 3. Indikatorlar hisoblash: VWAP (faqat RTH reset)
    vwap_series = compute_vwap(df_5m, rth_only=True)
    curr_vwap = float(vwap_series.iloc[-1])
    curr_price = float(df_5m["close"].iloc[-1])

    if math.isnan(curr_vwap) or curr_vwap <= 0.0:
        return DaySetup(
            symbol=symbol,
            timestamp=last_ts,
            timeframe="5m",
            status=DaySetupStatus.DATA_INSUFFICIENT,
            price=curr_price,
            warnings=("VWAP calculation not available for current session",),
        )

    vwap_dist_pct = (curr_price - curr_vwap) / curr_vwap

    # 4. RSI(14)
    rsi_series = compute_rsi(df_5m, period=14)
    curr_rsi = float(rsi_series.iloc[-1])
    is_rsi_confirmed = not math.isnan(curr_rsi) and curr_rsi > RSI_MOMENTUM_THRESHOLD

    # 5. RVOL(20)
    rvol_series = compute_rvol(df_5m, lookback_sessions=20, min_sessions=1)
    curr_rvol = float(rvol_series.iloc[-1]) if not rvol_series.empty else float("nan")
    is_rvol_confirmed = not math.isnan(curr_rvol) and curr_rvol >= RVOL_CONFIRMATION_THRESHOLD

    # 6. Point-in-time VWAP Reclaim vs Hold vs Above vs Below
    prev_close = float(df_5m["close"].iloc[-2]) if len(df_5m) >= 2 else float("nan")
    prev_vwap = float(vwap_series.iloc[-2]) if len(vwap_series) >= 2 else float("nan")

    is_above_vwap = curr_price > curr_vwap
    is_reclaim = False
    vwap_rel = VwapRelation.NO_RECLAIM

    if is_above_vwap:
        if not math.isnan(prev_close) and not math.isnan(prev_vwap) and prev_close <= prev_vwap:
            # Oldingi bar VWAP ostida, joriy bar VWAP ustida yopildi => RECLAIM
            vwap_rel = VwapRelation.VWAP_RECLAIM
            is_reclaim = True
        else:
            # Oldingi bar ham VWAP ustida edi
            if vwap_dist_pct <= VWAP_HOLD_MAX_DISTANCE_PCT:
                vwap_rel = VwapRelation.VWAP_HOLD
            else:
                vwap_rel = VwapRelation.ABOVE_VWAP
    else:
        vwap_rel = VwapRelation.BELOW_VWAP

    # 7. 5m SMC tuzilma va Trigger
    swings_5m = detect_swings(df_5m, lookback=2)
    state_5m = current_structure_state(df_5m, swings_5m)
    structure_5m_str = (
        state_5m.name if state_5m is not None else "NEUTRAL"
    )

    events_5m = detect_structure_events(df_5m, swings_5m)
    trigger = TriggerType.NONE.value

    # So'nggi 5 bar ichidagi struktura hodisalari
    n_5m = len(df_5m)
    recent_events = [e for e in events_5m if e.index_pos >= max(0, n_5m - 5)]

    # CHoCH trigger
    choch_events = [
        e for e in recent_events
        if e.event_type is StructureEventType.CHOCH and e.direction is StructureState.BULLISH
    ]
    bos_events = [
        e for e in recent_events
        if e.event_type is StructureEventType.BOS and e.direction is StructureState.BULLISH
    ]

    if choch_events:
        trigger = TriggerType.BULLISH_CHOCH.value
    elif bos_events:
        trigger = TriggerType.BULLISH_BOS.value
    elif len(df_5m) >= 2 and curr_price > float(df_5m["high"].iloc[-2]):
        # Previous candle high break
        trigger = TriggerType.PREV_HIGH_BREAK.value

    has_5m_trigger = trigger != TriggerType.NONE.value

    # 8. 15m MTF Konteksti (Qat'iy No-Lookahead)
    structure_15m_str = MtfContext.UNKNOWN.value
    is_15m_bullish = False
    is_15m_bearish = False

    if df_15m is not None and not df_15m.empty:
        # 5m bar yopilish vaqti
        curr_5m_end = last_ts + pd.Timedelta(minutes=5)
        df_15m_closed = filter_closed_bars(df_15m, "15m", as_of=curr_5m_end)

        if len(df_15m_closed) >= 5:
            swings_15m = detect_swings(df_15m_closed, lookback=2)
            state_15m = current_structure_state(df_15m_closed, swings_15m)

            if state_15m is StructureState.BULLISH:
                structure_15m_str = MtfContext.BULLISH.value
                is_15m_bullish = True
            elif state_15m is StructureState.BEARISH:
                structure_15m_str = MtfContext.BEARISH.value
                is_15m_bearish = True
            else:
                structure_15m_str = MtfContext.NEUTRAL.value
        else:
            structure_15m_str = MtfContext.UNKNOWN.value

    # 9. Intraday Darajalar va Qarshilik Tekshiruvi
    warnings: list[str] = []
    levels_df = None
    if df_extended_5m is not None and not df_extended_5m.empty:
        levels_df = compute_intraday_levels(df_extended_5m)
    elif len(df_5m) >= 20:
        levels_df = compute_intraday_levels(df_5m)

    if levels_df is not None and not levels_df.empty:
        last_levels = levels_df.iloc[-1]
        pdh = last_levels.get("pdh")
        pmh = last_levels.get("pmh")

        if pdh is not None and not math.isnan(pdh) and pdh > 0:
            dist_pdh = (pdh - curr_price) / pdh
            if 0.0 <= dist_pdh <= LEVEL_PROXIMITY_PCT:
                warnings.append("Near previous day high (PDH resistance)")

        if pmh is not None and not math.isnan(pmh) and pmh > 0:
            dist_pmh = (pmh - curr_price) / pmh
            if 0.0 <= dist_pmh <= LEVEL_PROXIMITY_PCT:
                warnings.append("Near premarket high (PMH resistance)")

    # 10. Kontekst ogohlantirishlari
    if is_15m_bearish:
        warnings.append("15m structure is BEARISH (MTF conflict)")

    if not is_rvol_confirmed:
        if math.isnan(curr_rvol):
            warnings.append("RVOL baseline not available (insufficient historical sessions)")
        else:
            warnings.append(f"Volume not confirmed (RVOL {curr_rvol:.1f}x < 2.0x)")

    if not is_rsi_confirmed:
        if math.isnan(curr_rsi):
            warnings.append("RSI(14) not available")
        else:
            warnings.append(f"RSI momentum {curr_rsi:.1f} <= 50 (lacks bullish momentum)")

    if vwap_rel is VwapRelation.ABOVE_VWAP:
        warnings.append("Price extended above VWAP (not a fresh reclaim)")

    # 11. Dalillarni yig'ish (Evidence Aggregation)
    evidence_agg = aggregate_day_evidence(
        is_vwap_reclaim=is_reclaim,
        is_above_vwap=is_above_vwap,
        is_rsi_confirmed=is_rsi_confirmed,
        is_rvol_confirmed=is_rvol_confirmed,
        has_5m_trigger=has_5m_trigger,
        is_15m_bullish=is_15m_bullish,
        trigger_desc=trigger if has_5m_trigger else "",
        rsi_val=curr_rsi if not math.isnan(curr_rsi) else None,
        rvol_val=curr_rvol if not math.isnan(curr_rvol) else None,
    )

    # 12. Non-Directive Status Aniqlash
    # Shartlar:
    # - Agar 15m BEARISH bo'lsa -> CONFLICT (agar narx VWAP ustida/reclaim bo'lsa)
    # - Agar narx VWAP ostida bo'lsa -> NO_SETUP
    # - Agar narx juda uzoqda bo'lsa (ABOVE_VWAP) -> NO_SETUP
    # - Agar reclaim yoki hold bo'lsa va 15m bearish bo'lmasa:
    #     - barcha tasdiqlar (RSI, RVOL, trigger) bo'lsa -> CONFIRMED
    #     - aks holda -> DETECTED
    if not is_above_vwap:
        status = DaySetupStatus.NO_SETUP
    elif vwap_rel is VwapRelation.ABOVE_VWAP:
        status = DaySetupStatus.NO_SETUP
    elif is_15m_bearish:
        status = DaySetupStatus.CONFLICT
    elif is_reclaim or vwap_rel is VwapRelation.VWAP_HOLD:
        if is_rsi_confirmed and is_rvol_confirmed and has_5m_trigger and is_15m_bullish:
            status = DaySetupStatus.CONFIRMED
        else:
            status = DaySetupStatus.DETECTED
    else:
        status = DaySetupStatus.NO_SETUP

    return DaySetup(
        symbol=symbol,
        timestamp=last_ts,
        timeframe="5m",
        status=status,
        setup_type="VWAP_RECLAIM" if is_reclaim else "VWAP_MOMENTUM",
        price=curr_price,
        vwap=curr_vwap,
        vwap_distance=vwap_dist_pct,
        vwap_relation=vwap_rel,
        rsi=curr_rsi,
        rvol=curr_rvol,
        structure_5m=structure_5m_str,
        structure_15m=structure_15m_str,
        trigger=trigger,
        evidence=evidence_agg.evidence_list,
        warnings=tuple(warnings),
        evidence_score=evidence_agg.score,
        max_score=evidence_agg.max_score,
    )
