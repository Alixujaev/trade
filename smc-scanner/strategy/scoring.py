"""Signal scoring 0-100 (TZ 11) — ENG MUHIM qism. Binary emas, vaznli ball.

Swing weighting (config.settings.SCORE_WEIGHTS): Trend 30%, Structure 20%, Setup 20%,
Volume 10%, SMC 10% (V1'da 0), Risk 10%. Chegaralar (SCORE_THRESHOLDS):
>=80 STRONG_BUY, 70-79 BUY, 60-69 WATCH, <60 NO_TRADE.

Har komponent 0..1 sub-ball beradi + o'zbekcha qisqa izoh; total = 100 * sum(weight*sub).
Bu qiymatlar backtest bilan qo'lda sozlanadi.

Lookahead bias YO'Q: barcha kirish setup.entry_index_pos ('i'), breakout bar
('b' < i) yoki orqaga qaragan seriya (EMA/ATR/volume). Struktura holati
detect_structure_events'dan 'i' bargacha bo'lgan oxirgi hodisa bo'yicha olinadi.
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from config.settings import (
    ATR_PERIOD,
    MIN_BREAKOUT_RR,
    RETEST_TOLERANCE_ATR_MULT,
    SCORE_RR_SATURATION,
    SCORE_THRESHOLDS,
    SCORE_WEIGHTS,
    SWING_LOOKBACK,
    VOLUME_MA_PERIOD,
    VOLUME_RATIO_SATURATION,
)
from indicators.ema import compute_ema_frame
from indicators.volume import volume_ratio
from levels.support_resistance import detect_sr_zones
from smc.market_structure import detect_structure_events
from smc.signal import compute_planned_rr
from smc.structure import detect_swings
from smc.types import StructureState, SwingKind, SwingLabel, TradeSetup
from smc.zones import compute_atr
from strategy.trend import compute_trend_regime
from strategy.types import ScoreComponent, SignalScore, TrendRegime

# Modul-lokal to'yinish konstantalari (sweep kerak bo'lsagina config.settings'ga ko'chiriladi).
EMA_SEP_SATURATION: float = 3.0  # (ema_fast-ema_slow)/ATR shu qiymatda trend "to'la kuchli"
BREAKOUT_STRENGTH_SAT: float = 2.0  # (close-Z.top)/ATR shu qiymatda breakout "to'la kuchli"


def _clip01(value: float) -> float:
    """[0, 1] oralig'iga qisadi; NaN -> 0.0."""
    if pd.isna(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def label_for_score(total: float, thresholds: dict[str, float] = SCORE_THRESHOLDS) -> str:
    """0..100 ball -> yorliq."""
    if total >= thresholds["strong_buy"]:
        return "STRONG_BUY"
    if total >= thresholds["buy"]:
        return "BUY"
    if total >= thresholds["watch"]:
        return "WATCH"
    return "NO_TRADE"


def _parse_zone_band(reason: str) -> tuple[float, float] | None:
    """"BREAKOUT_RETEST@<bottom>-<top>" -> (bottom, top). Format boshqa bo'lsa None."""
    if "@" not in reason:
        return None
    try:
        bottom_str, top_str = reason.split("@", 1)[1].split("-")
        return float(bottom_str), float(top_str)
    except (ValueError, IndexError):
        return None


def _structure_state_at(events, index_pos: int) -> StructureState | None:
    """`index_pos` bargacha bo'lgan oxirgi struktura hodisasining yo'nalishi."""
    state: StructureState | None = None
    for event in events:
        if event.index_pos <= index_pos:
            state = event.direction
        else:
            break
    return state


def _trend_sub_score(
    regime: pd.Series, ema_frame: pd.DataFrame, atr: pd.Series, i: int
) -> ScoreComponent:
    base = {TrendRegime.BULLISH: 1.0, TrendRegime.NEUTRAL: 0.4, TrendRegime.BEARISH: 0.0}.get(
        regime.iloc[i] if 0 <= i < len(regime) else TrendRegime.NEUTRAL, 0.4
    )
    atr_i = atr.iloc[i] if 0 <= i < len(atr) else float("nan")
    fast = ema_frame["ema_fast"].iloc[i] if 0 <= i < len(ema_frame) else float("nan")
    slow = ema_frame["ema_slow"].iloc[i] if 0 <= i < len(ema_frame) else float("nan")
    if pd.notna(atr_i) and atr_i > 0 and pd.notna(fast) and pd.notna(slow):
        factor = _clip01((fast - slow) / atr_i / EMA_SEP_SATURATION)
    else:
        factor = 0.0
    sub = _clip01(base * (0.5 + 0.5 * factor))
    return ScoreComponent(
        name="trend", weight=SCORE_WEIGHTS["trend"], sub_score=sub,
        reason=f"trend rejimi + EMA ajralishi (base={base:.2f}, factor={factor:.2f})",
    )


def _structure_sub_score(
    structure_state: StructureState | None, swings, i: int
) -> ScoreComponent:
    if structure_state is StructureState.BEARISH:
        sub, why = 0.0, "struktura BEARISH"
    elif structure_state is StructureState.BULLISH:
        sub, why = 0.7, "struktura BULLISH"
        last_high = next(
            (s for s in reversed(swings) if s.kind is SwingKind.HIGH and s.confirmed_index_pos <= i),
            None,
        )
        last_low = next(
            (s for s in reversed(swings) if s.kind is SwingKind.LOW and s.confirmed_index_pos <= i),
            None,
        )
        if (
            last_high is not None and last_high.label is SwingLabel.HH
            and last_low is not None and last_low.label is SwingLabel.HL
        ):
            sub, why = 1.0, "struktura BULLISH + HH/HL"
    else:
        sub, why = 0.3, "struktura holati noaniq"
    return ScoreComponent(
        name="structure", weight=SCORE_WEIGHTS["structure"], sub_score=sub, reason=why
    )


def _setup_sub_score(df: pd.DataFrame, setup: TradeSetup, atr: pd.Series) -> ScoreComponent:
    i = setup.entry_index_pos
    b = setup.breakout_index_pos if setup.breakout_index_pos is not None else i
    r = setup.retest_index_pos if setup.retest_index_pos is not None else i
    band = _parse_zone_band(setup.reason)
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()

    parts: list[float] = []
    if band is not None and 0 <= b < len(df):
        atr_b = atr.iloc[b]
        if pd.notna(atr_b) and atr_b > 0:
            parts.append(_clip01((closes[b] - band[1]) / atr_b / BREAKOUT_STRENGTH_SAT))
    if band is not None and 0 <= r < len(df):
        atr_r = atr.iloc[r]
        tol = RETEST_TOLERANCE_ATR_MULT * (atr_r if pd.notna(atr_r) else 0.0)
        if tol > 0:
            parts.append(_clip01(1.0 - (closes[r] - band[1]) / (2 * tol)))
        else:
            parts.append(1.0 if closes[r] <= band[1] else 0.5)
    if 0 <= i < len(df):
        atr_i = atr.iloc[i]
        if pd.notna(atr_i) and atr_i > 0:
            parts.append(_clip01((closes[i] - opens[i]) / atr_i))

    sub = sum(parts) / len(parts) if parts else 0.0
    return ScoreComponent(
        name="setup", weight=SCORE_WEIGHTS["setup"], sub_score=_clip01(sub),
        reason=f"breakout kuchi + retest tozaligi + tasdiq tanasi ({len(parts)} qism)",
    )


def _volume_sub_score(
    volume_ratio_series: pd.Series, setup: TradeSetup, volume_saturation: float
) -> ScoreComponent:
    b = setup.breakout_index_pos if setup.breakout_index_pos is not None else setup.entry_index_pos
    ratio = volume_ratio_series.iloc[b] if 0 <= b < len(volume_ratio_series) else float("nan")
    sub = _clip01((ratio / volume_saturation) if pd.notna(ratio) else 0.0)
    return ScoreComponent(
        name="volume", weight=SCORE_WEIGHTS["volume"], sub_score=sub,
        reason=f"breakout hajm nisbati ({ratio:.2f}x)" if pd.notna(ratio) else "hajm nisbati NaN",
    )


def _risk_sub_score(setup: TradeSetup, min_rr: float, rr_saturation: float) -> ScoreComponent:
    rr = compute_planned_rr(setup)
    if rr is None:
        sub, why = 0.0, "R:R hisoblab bo'lmadi"
    else:
        span = max(rr_saturation - min_rr, 1e-9)
        sub = _clip01((rr - min_rr) / span)
        why = f"rejalashtirilgan R:R = {rr:.2f}"
    return ScoreComponent(name="risk", weight=SCORE_WEIGHTS["risk"], sub_score=sub, reason=why)


def score_breakout_setup(
    df: pd.DataFrame,
    setup: TradeSetup,
    *,
    regime: pd.Series,
    ema_frame: pd.DataFrame,
    swings: list,
    structure_events: list,
    sr_zones: list,  # noqa: ARG001 — kelajakda S/R kontekst balli uchun, hozircha ishlatilmaydi
    atr: pd.Series,
    volume_ratio_series: pd.Series,
    weights: dict[str, float] = SCORE_WEIGHTS,
    thresholds: dict[str, float] = SCORE_THRESHOLDS,
    min_rr: float = MIN_BREAKOUT_RR,
    rr_saturation: float = SCORE_RR_SATURATION,
    volume_saturation: float = VOLUME_RATIO_SATURATION,
) -> SignalScore:
    """Bitta setup uchun 0..100 SignalScore (komponentlar + izohlar bilan)."""
    i = setup.entry_index_pos
    structure_state = _structure_state_at(structure_events, i)

    components = (
        _trend_sub_score(regime, ema_frame, atr, i),
        _structure_sub_score(structure_state, swings, i),
        _setup_sub_score(df, setup, atr),
        _volume_sub_score(volume_ratio_series, setup, volume_saturation),
        ScoreComponent(
            name="smc", weight=weights["smc"], sub_score=0.0, reason="SMC qatlami V1 da yo'q"
        ),
        _risk_sub_score(setup, min_rr, rr_saturation),
    )
    total = round(100.0 * sum(weights[c.name] * c.sub_score for c in components), 2)
    return SignalScore(
        total=total,
        label=label_for_score(total, thresholds),
        components=components,
        reasons=tuple(f"{c.name}: {c.reason}" for c in components),
    )


def apply_scores(
    df: pd.DataFrame,
    setups: list[TradeSetup],
    *,
    weights: dict[str, float] = SCORE_WEIGHTS,
    thresholds: dict[str, float] = SCORE_THRESHOLDS,
    lookback: int = SWING_LOOKBACK,
    atr_period: int = ATR_PERIOD,
    volume_ma_period: int = VOLUME_MA_PERIOD,
    min_rr: float = MIN_BREAKOUT_RR,
) -> list[TradeSetup]:
    """Har setup uchun ball hisoblab, `score`/`score_reasons` to'ldirilgan YANGI frozen
    nusxalar qaytaradi (originallarni O'ZGARTIRMAYDI). Ichki seriyalarni bir marta hisoblaydi.
    """
    if not setups:
        return []

    regime = compute_trend_regime(df)
    ema_frame = compute_ema_frame(df)
    swings = detect_swings(df, lookback=lookback)
    structure_events = detect_structure_events(df, swings)
    sr_zones = detect_sr_zones(df, lookback=lookback, atr_period=atr_period)
    atr = compute_atr(df, atr_period)
    vr = volume_ratio(df, period=volume_ma_period)

    scored: list[TradeSetup] = []
    for setup in setups:
        score = score_breakout_setup(
            df, setup,
            regime=regime, ema_frame=ema_frame, swings=swings, structure_events=structure_events,
            sr_zones=sr_zones, atr=atr, volume_ratio_series=vr,
            weights=weights, thresholds=thresholds, min_rr=min_rr,
        )
        scored.append(
            dataclasses.replace(setup, score=score.total, score_reasons=score.reasons)
        )
    return scored


def filter_by_score(
    setups: list[TradeSetup],
    min_total: float | None,
    *,
    thresholds: dict[str, float] = SCORE_THRESHOLDS,  # noqa: ARG001 — API izchilligi uchun
) -> list[TradeSetup]:
    """min_total=None -> o'zgarishsiz. Aks holda faqat score >= min_total bo'lgan setup'lar
    (faqat SUBSET tanlanadi, hech narsa qayta hisoblanmaydi — lookahead xavfi yo'q)."""
    if min_total is None:
        return setups
    return [s for s in setups if s.score is not None and s.score >= min_total]
