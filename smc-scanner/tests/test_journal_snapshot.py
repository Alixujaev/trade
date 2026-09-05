"""journal/snapshot.py uchun testlar — SignalPayload -> JournalEntry snapshot kwargs (sof map)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from journal.snapshot import snapshot_kwargs_from_payload
from signals.payload import (
    HistoricalContext,
    SetupStatus,
    SignalContext,
    SignalMode,
    SignalPayload,
)
from smc.types import StructureState


def _payload(**overrides) -> SignalPayload:
    fields = dict(
        symbol="AAPL", mode=SignalMode.SWING, setup_type="breakout_retest", score=84.0,
        score_label="STRONG SETUP", direction=StructureState.BULLISH, entry_zone=(148.0, 152.0),
        invalidation=140.0, potential_target=170.0, risk_reward=2.5,
        context=SignalContext(trend="BULLISH", structure="BOS", volume_confirmed=True),
        historical_context=HistoricalContext(expectancy_r=0.6, win_rate_pct=52.8, period_label="2020-2026"),
        generated_at=datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc), timeframe="1d",
        data_freshness=date(2026, 9, 5), entry_ts=date(2026, 9, 5),
        target_source="resistance", score_reasons=("trend: kuchli", "hajm: tasdiqlangan"),
        current_price=150.0, distance_to_zone=0.0, status=SetupStatus.ZONE_REACHED,
    )
    fields.update(overrides)
    return SignalPayload(**fields)


def test_snapshot_maps_all_fields() -> None:
    payload = _payload()

    kwargs = snapshot_kwargs_from_payload(payload)

    assert kwargs == {
        "setup_type": "breakout_retest",
        "score": 84.0,
        "score_label": "STRONG SETUP",
        "trend": "BULLISH",
        "structure": "BOS",
        "volume_confirmed": True,
        "entry_zone_low": 148.0,
        "entry_zone_high": 152.0,
        "invalidation": 140.0,
        "target": 170.0,
        "risk_reward": 2.5,
        "target_source": "resistance",
        "status": "ZONE_REACHED",
        "score_reasons": ("trend: kuchli", "hajm: tasdiqlangan"),
    }


def test_snapshot_status_none_when_payload_status_none() -> None:
    """status hisoblanmagan (current_price berilmagan) payload -- snapshot'da
    None (enum emas, oddiy string/None)."""
    payload = _payload(status=None, current_price=None, distance_to_zone=None)

    kwargs = snapshot_kwargs_from_payload(payload)

    assert kwargs["status"] is None


def test_snapshot_status_is_plain_string_not_enum() -> None:
    payload = _payload(status=SetupStatus.MOVED_PAST)

    kwargs = snapshot_kwargs_from_payload(payload)

    assert kwargs["status"] == "MOVED_PAST"
    assert isinstance(kwargs["status"], str)


def test_snapshot_empty_score_reasons_stays_empty_tuple() -> None:
    payload = _payload(score_reasons=())

    kwargs = snapshot_kwargs_from_payload(payload)

    assert kwargs["score_reasons"] == ()


def test_snapshot_bearish_payload_maps_same_fields() -> None:
    """Bearish (AVOID/EXIT candidate) payload ham xuddi shu maydonlar bilan
    map qilinadi -- bu funksiya direction'ga qarab hech narsani filtrlamaydi
    (bu UI qarori, mapping'ning ishi emas)."""
    payload = _payload(
        direction=StructureState.BEARISH,
        context=SignalContext(trend="BEARISH", structure="CHoCH", volume_confirmed=True),
    )
    kwargs = snapshot_kwargs_from_payload(payload)
    assert kwargs["trend"] == "BEARISH"
    assert kwargs["structure"] == "CHoCH"
