"""signals/payload.py uchun testlar (sof domain, I/O yo'q, tarmoqsiz)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from signals.payload import (
    HistoricalContext,
    SignalContext,
    SignalMode,
    SignalPayload,
    format_payload,
    payload_from_setup,
    score_label_for,
)
from smc.types import StructureState, TradeSetup

_BANNED_SUBSTRINGS = ["buy", "sell", "short", "🚀", "enter now"]


def _setup(
    *,
    entry: float = 100.0,
    stop: float = 90.0,
    target: float = 127.0,
    direction: StructureState = StructureState.BULLISH,
    reason: str = "BREAKOUT_RETEST@98.50-100.00",
    score: float | None = 84.0,
    score_reasons: tuple[str, ...] = ("trend: kuchli yuqori", "hajm: tasdiqlangan"),
) -> TradeSetup:
    return TradeSetup(
        entry_ts=pd_timestamp(), entry_price=entry, stop_price=stop, target_price=target,
        direction=direction, entry_index_pos=42, reason=reason, score=score,
        score_reasons=score_reasons,
    )


def pd_timestamp():
    import pandas as pd
    return pd.Timestamp("2026-08-15", tz="UTC")


def _payload(
    *,
    setup: TradeSetup | None = None,
    trend: str = "BULLISH",
    structure: str = "BOS",
    volume_confirmed: bool = True,
) -> SignalPayload:
    return payload_from_setup(
        setup or _setup(),
        symbol="AAPL",
        trend=trend,
        structure=structure,
        volume_confirmed=volume_confirmed,
        historical_expectancy_r=0.27,
        historical_win_rate_pct=41.0,
        historical_period_label="2020-2026",
        data_freshness=date(2026, 8, 15),
        generated_at=datetime(2026, 8, 16, 9, 30, tzinfo=timezone.utc),
    )


def _all_strings(obj) -> list[str]:
    """Payload'dagi (nested dataclass'lar ichidagi) barcha string qiymatlarni yig'adi."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif hasattr(obj, "__dataclass_fields__"):
        for f in obj.__dataclass_fields__:
            out.extend(_all_strings(getattr(obj, f)))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            out.extend(_all_strings(item))
    return out


# ======================================================================
# score_label_for
# ======================================================================


def test_score_label_for_neutral_thresholds() -> None:
    assert score_label_for(84.0) == "STRONG SETUP"
    assert score_label_for(75.0) == "SETUP"
    assert score_label_for(65.0) == "WATCH"
    assert score_label_for(40.0) == "WEAK"
    # Hech qanday label "BUY" so'zini o'z ichiga olmasligi kerak.
    for score in (95.0, 75.0, 65.0, 10.0):
        assert "BUY" not in score_label_for(score)


# ======================================================================
# payload_from_setup
# ======================================================================


def test_payload_from_setup() -> None:
    setup = _setup(entry=100.0, stop=90.0, target=127.0, score=84.0)
    payload = payload_from_setup(
        setup, symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.27, historical_win_rate_pct=41.0,
        historical_period_label="2020-2026", data_freshness=date(2026, 8, 15),
        generated_at=datetime(2026, 8, 16, 9, 30, tzinfo=timezone.utc),
    )

    assert payload.symbol == "AAPL"
    assert payload.mode is SignalMode.SWING
    assert payload.setup_type == "breakout_retest"
    assert payload.score == pytest.approx(84.0)
    assert payload.score_label == "STRONG SETUP"
    assert payload.direction is StructureState.BULLISH
    assert payload.entry_zone == (100.0, 100.0)  # TradeSetup bitta narx saqlaydi -> degenerativ zona
    assert payload.invalidation == pytest.approx(90.0)  # setup.stop_price
    assert payload.potential_target == pytest.approx(127.0)  # setup.target_price
    assert payload.risk_reward == pytest.approx(2.7)  # (127-100)/(100-90)
    assert payload.context == SignalContext(trend="BULLISH", structure="BOS", volume_confirmed=True, smc=None)
    assert payload.historical_context.expectancy_r == pytest.approx(0.27)
    assert payload.historical_context.win_rate_pct == pytest.approx(41.0)
    assert payload.historical_context.period_label == "2020-2026"
    assert payload.historical_context.disclaimer  # doim mavjud, bo'sh emas
    assert payload.timeframe == "1d"
    assert payload.data_freshness == date(2026, 8, 15)
    assert payload.generated_at == datetime(2026, 8, 16, 9, 30, tzinfo=timezone.utc)


def test_payload_from_setup_maps_reason_variants() -> None:
    fvg = payload_from_setup(
        _setup(reason="FVG"), symbol="X", trend="BULLISH", structure="-", volume_confirmed=False,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert fvg.setup_type == "fvg"

    ob = payload_from_setup(
        _setup(reason="ORDER_BLOCK"), symbol="X", trend="BULLISH", structure="-", volume_confirmed=False,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert ob.setup_type == "order_block"


def test_payload_from_setup_explicit_entry_zone_override() -> None:
    payload = payload_from_setup(
        _setup(entry=100.0), symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.27, historical_win_rate_pct=41.0, historical_period_label="2020-2026",
        data_freshness=date(2026, 8, 15), entry_zone=(99.0, 101.0),
    )
    assert payload.entry_zone == (99.0, 101.0)


def test_payload_from_setup_degenerate_risk_gives_zero_rr() -> None:
    setup = _setup(entry=100.0, stop=100.0, target=110.0)  # risk=0 -- edge case
    payload = payload_from_setup(
        setup, symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert payload.risk_reward == pytest.approx(0.0)


def test_payload_from_setup_none_score_defaults_to_zero() -> None:
    payload = payload_from_setup(
        _setup(score=None), symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert payload.score == pytest.approx(0.0)
    assert payload.score_label == "WEAK"


# ======================================================================
# No-directive-language principle (kod bilan majburlanadi)
# ======================================================================


def test_payload_no_directive_language() -> None:
    payload = _payload()
    formatted = format_payload(payload)

    haystacks = _all_strings(payload) + [formatted]
    lowered = "\n".join(haystacks).lower()
    for banned in _BANNED_SUBSTRINGS:
        assert banned.lower() not in lowered, f"'{banned}' formatlangan/payload matnida topildi"


def test_payload_no_directive_language_bearish() -> None:
    setup = _setup(direction=StructureState.BEARISH, reason="BREAKOUT_RETEST@98.50-100.00")
    payload = _payload(setup=setup, trend="BEARISH", structure="CHoCH")
    formatted = format_payload(payload)

    haystacks = _all_strings(payload) + [formatted]
    lowered = "\n".join(haystacks).lower()
    for banned in _BANNED_SUBSTRINGS:
        assert banned.lower() not in lowered, f"'{banned}' bearish payload/matnida topildi"


# ======================================================================
# format_payload snapshot
# ======================================================================


def test_format_payload_snapshot() -> None:
    payload = _payload()
    text = format_payload(payload)

    expected = (
        "AAPL — SWING setup\n"
        "Setup: Breakout + Retest   |   Score: 84/100 (STRONG SETUP)\n"
        "Trend: BULLISH   Structure: BOS   Volume: Confirmed\n"
        "Entry zone: $100.00 – $100.00\n"
        "Invalidation: $90.00\n"
        "Target: $127.00   R:R: 2.7\n"
        "---\n"
        "Backtest context: expectancy +0.27R, win-rate 41% (2020-2026). Bu kelajak natija kafolati emas.\n"
        "Generated: 2026-08-16 09:30   Data: 2026-08-15"
    )
    assert text == expected


# ======================================================================
# Bearish -> AVOID/EXIT, hech qachon short EMAS
# ======================================================================


def test_bearish_is_avoid_not_short() -> None:
    setup = _setup(direction=StructureState.BEARISH, entry=100.0, stop=110.0, target=80.0)
    payload = _payload(setup=setup, trend="BEARISH", structure="CHoCH")
    text = format_payload(payload)

    assert "AVOID" in text or "EXIT" in text
    assert "short" not in text.lower()
    assert "sell" not in text.lower()
    assert payload.direction is StructureState.BEARISH
