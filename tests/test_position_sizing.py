"""strategy/position_sizing.py uchun testlar."""

from __future__ import annotations

import pandas as pd
import pytest

from smc.types import StructureState, TradeSetup
from strategy.position_sizing import rr_gate, size_position


def test_size_position_hand_verified() -> None:
    plan = size_position(10_000.0, entry=100.0, stop=95.0, risk_pct=0.01)

    assert plan.per_share_risk == pytest.approx(5.0)
    assert plan.dollar_risk == pytest.approx(100.0)
    assert plan.shares == pytest.approx(20.0)
    assert plan.acceptable is True
    assert plan.capped_to_equity is False


def test_spot_cap_when_position_exceeds_equity() -> None:
    # risk 1% = $100, per-share risk kichik (0.5) -> 200 aksiya -> 200*100 = $20k > $10k
    plan = size_position(10_000.0, entry=100.0, stop=99.5, risk_pct=0.01)

    assert plan.capped_to_equity is True
    assert plan.shares == pytest.approx(100.0)  # 10_000 / 100
    assert plan.acceptable is True


def test_non_positive_risk_rejected() -> None:
    plan = size_position(10_000.0, entry=100.0, stop=100.0)
    assert plan.acceptable is False
    assert plan.shares == 0.0

    plan2 = size_position(10_000.0, entry=100.0, stop=105.0)
    assert plan2.acceptable is False


def test_non_positive_equity_rejected() -> None:
    plan = size_position(0.0, entry=100.0, stop=95.0)
    assert plan.acceptable is False


def _setup(entry: float, stop: float, target: float) -> TradeSetup:
    return TradeSetup(
        entry_ts=pd.Timestamp("2024-01-01", tz="UTC"),
        entry_price=entry, stop_price=stop, target_price=target,
        direction=StructureState.BULLISH, entry_index_pos=0, reason="BREAKOUT_RETEST@1.00-2.00",
    )


def test_rr_gate_boundary() -> None:
    # entry=100, stop=90 -> risk 10 ; target 115 -> RR 1.5 ; target 114 -> RR 1.4
    assert rr_gate(_setup(100, 90, 115), min_rr=1.5) is True
    assert rr_gate(_setup(100, 90, 114), min_rr=1.5) is False


def test_rr_gate_none_when_risk_non_positive() -> None:
    assert rr_gate(_setup(100, 100, 120), min_rr=1.5) is False
