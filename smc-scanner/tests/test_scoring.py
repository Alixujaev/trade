"""strategy/scoring.py uchun testlar (sintetik kontekst, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd
import pytest

from smc.types import StructureEvent, StructureEventType, StructureState, TradeSetup
from strategy.scoring import (
    _structure_event_at,
    apply_scores,
    filter_by_score,
    label_for_score,
    score_breakout_setup,
)
from strategy.types import TrendRegime

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _ctx_df() -> pd.DataFrame:
    rows = [
        {"open": 98, "high": 99, "low": 97, "close": 98},
        {"open": 98, "high": 100, "low": 97, "close": 99},
        {"open": 99, "high": 101, "low": 98, "close": 100},
        {"open": 100, "high": 104, "low": 99, "close": 103},   # 3 breakout
        {"open": 103, "high": 104, "low": 100, "close": 101},  # 4 retest
        {"open": 101, "high": 107, "low": 100, "close": 106},  # 5 tasdiq/entry
    ]
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[_COLUMNS]


def _setup(*, entry_price: float = 105.0, stop_price: float = 100.0, target_price: float = 115.0) -> TradeSetup:
    return TradeSetup(
        entry_ts=pd.Timestamp("2024-01-06", tz="UTC"),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        direction=StructureState.BULLISH,
        entry_index_pos=5,
        reason="BREAKOUT_RETEST@100.00-101.00",
        breakout_index_pos=3,
        retest_index_pos=4,
    )


def _regime(value: TrendRegime, n: int = 6) -> pd.Series:
    return pd.Series([value] * n, index=range(n), dtype=object)


def _ema_frame(fast: float, slow: float, n: int = 6) -> pd.DataFrame:
    return pd.DataFrame(
        {"ema_fast": [fast] * n, "ema_mid": [(fast + slow) / 2] * n, "ema_slow": [slow] * n}
    )


def _series(value: float, n: int = 6) -> pd.Series:
    return pd.Series([value] * n)


def _score(regime_value=TrendRegime.BULLISH, *, fast=106.0, slow=100.0, atr=2.0, vr=2.0, setup=None):
    return score_breakout_setup(
        _ctx_df(),
        setup or _setup(),
        regime=_regime(regime_value),
        ema_frame=_ema_frame(fast, slow),
        swings=[],
        structure_events=[],
        sr_zones=[],
        atr=_series(atr),
        volume_ratio_series=_series(vr),
    )


def test_weighted_sum_equals_total() -> None:
    score = _score()
    recomputed = round(100.0 * sum(c.weight * c.sub_score for c in score.components), 2)
    assert score.total == pytest.approx(recomputed)
    assert 0.0 <= score.total <= 100.0


@pytest.mark.parametrize(
    "total,expected",
    [(59, "NO_TRADE"), (60, "WATCH"), (69, "WATCH"), (70, "BUY"), (79, "BUY"),
     (80, "STRONG_BUY"), (81, "STRONG_BUY")],
)
def test_label_thresholds(total: float, expected: str) -> None:
    assert label_for_score(float(total)) == expected


def test_bullish_trend_full_when_emas_wide() -> None:
    # ema_fast-ema_slow = 6, atr = 2 -> sep = 3 -> /EMA_SEP_SATURATION(3) = 1 -> factor 1 -> sub 1.0
    trend = next(c for c in _score().components if c.name == "trend")
    assert trend.sub_score == pytest.approx(1.0)


def test_bearish_trend_zeroes_trend_component() -> None:
    trend = next(c for c in _score(TrendRegime.BEARISH).components if c.name == "trend")
    assert trend.sub_score == pytest.approx(0.0)


def test_smc_component_always_zero_in_v1() -> None:
    smc = next(c for c in _score().components if c.name == "smc")
    assert smc.sub_score == 0.0


def test_risk_component_scales_with_rr() -> None:
    low_rr = _score(setup=_setup(entry_price=105, stop_price=100, target_price=113))  # RR=1.6
    high_rr = _score(setup=_setup(entry_price=105, stop_price=100, target_price=120))  # RR=3.0
    low = next(c for c in low_rr.components if c.name == "risk").sub_score
    high = next(c for c in high_rr.components if c.name == "risk").sub_score
    assert high > low
    assert high == pytest.approx(1.0)  # RR=3.0 == SCORE_RR_SATURATION -> to'yingan


def test_volume_component_scales_with_ratio() -> None:
    vol = next(c for c in _score(vr=1.5).components if c.name == "volume").sub_score
    assert vol == pytest.approx(1.5 / 3.0)  # VOLUME_RATIO_SATURATION = 3.0


def test_apply_scores_returns_frozen_copies() -> None:
    df = _ctx_df()
    original = _setup()
    scored = apply_scores(df, [original])

    assert len(scored) == 1
    assert scored[0] is not original
    assert original.score is None  # original o'zgarmadi
    assert scored[0].score is not None
    assert isinstance(scored[0].score_reasons, tuple) and scored[0].score_reasons


def test_apply_scores_empty() -> None:
    assert apply_scores(_ctx_df(), []) == []


def test_filter_by_score_none_returns_all_unchanged() -> None:
    setups = apply_scores(_ctx_df(), [_setup()])
    assert filter_by_score(setups, None) is setups


def test_filter_by_score_threshold() -> None:
    scored = apply_scores(_ctx_df(), [_setup()])
    total = scored[0].score
    assert filter_by_score(scored, total - 0.01) == scored
    assert filter_by_score(scored, total + 0.01) == []


def test_score_no_lookahead_bias() -> None:
    """Setup ballini to'liq df'da va entry barigacha kesilgan df'da hisoblash bir xil bo'lishi kerak."""
    from tests.test_breakout_retest import _BASE_ROWS, _KW, _make_df
    from strategy.breakout_retest import generate_breakout_retest_signals

    df_full = _make_df(_BASE_ROWS)
    setup = generate_breakout_retest_signals(df_full, **_KW)[0]
    i = setup.entry_index_pos

    full = apply_scores(df_full, [setup])[0].score
    trunc = apply_scores(df_full.iloc[: i + 1], [setup])[0].score
    assert full == pytest.approx(trunc)


# ======================================================================
# _structure_event_at — to'liq StructureEvent (BOS/CHoCH turi + yo'nalish)
# ======================================================================


def _event(index_pos: int, event_type: StructureEventType, direction: StructureState) -> StructureEvent:
    return StructureEvent(
        timestamp=pd.Timestamp("2024-01-01", tz="UTC"), event_type=event_type, direction=direction,
        broken_level=100.0, broken_swing_ts=pd.Timestamp("2024-01-01", tz="UTC"),
        broken_swing_index_pos=0, index_pos=index_pos,
    )


def test_structure_event_at_returns_latest_qualifying_event() -> None:
    events = [
        _event(3, StructureEventType.BOS, StructureState.BULLISH),
        _event(7, StructureEventType.CHOCH, StructureState.BEARISH),
    ]
    assert _structure_event_at(events, 10) is events[1]


def test_structure_event_at_ignores_future_events() -> None:
    events = [_event(3, StructureEventType.BOS, StructureState.BULLISH), _event(20, StructureEventType.CHOCH, StructureState.BEARISH)]
    result = _structure_event_at(events, 10)
    assert result is events[0]  # 20-bardagi event hali "bo'lmagan" (kelajak)


def test_structure_event_at_none_when_no_events() -> None:
    assert _structure_event_at([], 10) is None


def test_structure_event_at_none_when_all_events_in_future() -> None:
    events = [_event(20, StructureEventType.BOS, StructureState.BULLISH)]
    assert _structure_event_at(events, 10) is None


def test_structure_state_at_still_returns_only_direction() -> None:
    """Scoring uchun ishlatiladigan mavjud funksiya (StructureState, BOS/CHoCH farqisiz)
    xatti-harakati O'ZGARMAYDI — _structure_event_at ustiga qurilgan bo'lsa ham."""
    from strategy.scoring import _structure_state_at

    events = [_event(3, StructureEventType.CHOCH, StructureState.BEARISH)]
    assert _structure_state_at(events, 10) is StructureState.BEARISH
