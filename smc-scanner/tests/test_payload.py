"""signals/payload.py uchun testlar (sof domain, I/O yo'q, tarmoqsiz)."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import pytest

from signals.payload import (
    HistoricalContext,
    SetupStatus,
    SignalContext,
    SignalMode,
    SignalPayload,
    contains_directive_language,
    distance_to_zone,
    format_payload,
    payload_from_setup,
    score_label_for,
    setup_status,
)
from smc.types import StructureState, TradeSetup


def _setup(
    *,
    entry: float = 100.0,
    stop: float = 90.0,
    target: float = 127.0,
    direction: StructureState = StructureState.BULLISH,
    reason: str = "BREAKOUT_RETEST@98.50-100.00",
    score: float | None = 84.0,
    score_reasons: tuple[str, ...] = ("trend: kuchli yuqori", "hajm: tasdiqlangan"),
    target_source: str | None = None,
) -> TradeSetup:
    return TradeSetup(
        entry_ts=pd_timestamp(), entry_price=entry, stop_price=stop, target_price=target,
        direction=direction, entry_index_pos=42, reason=reason, score=score,
        score_reasons=score_reasons, target_source=target_source,
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
    assert payload.score_reasons == ("trend: kuchli yuqori", "hajm: tasdiqlangan")
    assert payload.target_source is None


def test_payload_from_setup_maps_score_reasons() -> None:
    """setup.score_reasons (apply_scores allaqachon to'ldirgan) payload'ga ulanishi
    kerak -- audit topilmasi: ilgari bu ma'lumot payload_from_setup'da yo'qolar edi."""
    setup = _setup(score_reasons=("trend: kuchli yuqori", "risk: R:R 2.70"))
    payload = payload_from_setup(
        setup, symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert payload.score_reasons == ("trend: kuchli yuqori", "risk: R:R 2.70")


def test_payload_from_setup_maps_target_source() -> None:
    """setup.target_source (resistance | fallback) payload'ga ulanishi kerak — audit:
    R:R deyarli hamma joyda 2.0 bo'lishining manbasini ochiq qilish uchun."""
    setup = _setup(target_source="resistance")
    payload = payload_from_setup(
        setup, symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert payload.target_source == "resistance"


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
    text = "\n".join(_all_strings(payload) + [format_payload(payload)])

    assert not contains_directive_language(text)


def test_payload_no_directive_language_bearish() -> None:
    setup = _setup(direction=StructureState.BEARISH, reason="BREAKOUT_RETEST@98.50-100.00")
    payload = _payload(setup=setup, trend="BEARISH", structure="CHoCH")
    text = "\n".join(_all_strings(payload) + [format_payload(payload)])

    assert not contains_directive_language(text)


# ======================================================================
# format_payload snapshot
# ======================================================================


def test_format_payload_snapshot() -> None:
    # Degenerativ zona (100, 100); observed price 98.50 -> zona ostida -> DETECTED.
    payload = dataclasses.replace(_payload(), current_price=98.50)
    payload = dataclasses.replace(
        payload,
        distance_to_zone=distance_to_zone(98.50, 100.0, 100.0),
        status=setup_status(98.50, 100.0, 100.0),
    )
    text = format_payload(payload)

    expected = (
        "AAPL — SWING setup\n"
        "Setup: Breakout + Retest   |   Score: 84/100 (STRONG SETUP)\n"
        "Trend: BULLISH   Structure: BOS   Volume: Confirmed\n"
        "Observed price: $98.50 (zonagacha -1.50%)\n"
        "Status: DETECTED (zona ostida)\n"
        "Entry zone: $100.00 – $100.00\n"
        "Invalidation: $90.00\n"
        "Target: $127.00   R:R: 2.7\n"
        "Evidence:\n"
        "- trend: kuchli yuqori\n"
        "- hajm: tasdiqlangan\n"
        "---\n"
        "Backtest context: expectancy +0.27R, win-rate 41% (2020-2026). Bu kelajak natija kafolati emas.\n"
        "Generated: 2026-08-16 09:30   Data: 2026-08-15"
    )
    assert text == expected


# ======================================================================
# Evidence bloki (score_reasons) — audit topilmasi, mavjud ma'lumot endi ko'rsatiladi
# ======================================================================


def test_format_payload_shows_evidence_block_from_score_reasons() -> None:
    payload = _payload(setup=_setup(score_reasons=("setup: breakout+retest confirmed", "volume: tasdiqlandi")))
    text = format_payload(payload)

    assert "Evidence:" in text
    assert "- setup: breakout+retest confirmed" in text
    assert "- volume: tasdiqlandi" in text


def test_format_payload_omits_evidence_block_when_score_reasons_empty() -> None:
    payload = _payload(setup=_setup(score_reasons=()))
    text = format_payload(payload)

    assert "Evidence:" not in text


# ======================================================================
# Target manba yorlig'i (target_source) — audit: R:R deyarli hamma 2.0'ning sababi
# ======================================================================


def test_format_payload_shows_resistance_based_target_label() -> None:
    payload = _payload(setup=_setup(target_source="resistance"))
    text = format_payload(payload)

    assert "Target: $127.00   R:R: 2.7 (resistance-based)" in text


def test_format_payload_shows_fallback_target_label() -> None:
    payload = _payload(setup=_setup(target_source="fallback"))
    text = format_payload(payload)

    assert "Target: $127.00   R:R: 2.7 (fallback geometry)" in text


def test_format_payload_omits_target_source_label_when_none() -> None:
    payload = _payload(setup=_setup(target_source=None))
    text = format_payload(payload)

    assert "Target: $127.00   R:R: 2.7\n" in text
    assert "fallback geometry" not in text
    assert "resistance-based" not in text


# ======================================================================
# distance_to_zone — observed price'ning entry zonagacha % masofasi (sof funksiya)
# ======================================================================


def test_distance_to_zone_below_is_negative() -> None:
    d = distance_to_zone(57.51, 57.66, 58.60)
    assert d == pytest.approx((57.51 - 57.66) / 57.66 * 100)
    assert d < 0
    assert d == pytest.approx(-0.26, abs=0.01)


def test_distance_to_zone_inside_is_zero() -> None:
    assert distance_to_zone(58.00, 57.66, 58.60) == 0.0


def test_distance_to_zone_inside_at_boundaries_is_zero() -> None:
    assert distance_to_zone(57.66, 57.66, 58.60) == 0.0
    assert distance_to_zone(58.60, 57.66, 58.60) == 0.0


def test_distance_to_zone_above_is_positive() -> None:
    d = distance_to_zone(60.20, 57.66, 58.60)
    assert d == pytest.approx((60.20 - 58.60) / 58.60 * 100)
    assert d > 0


def test_distance_to_zone_is_pure() -> None:
    # Ikki marta chaqiruv bir xil natija (deterministik, global state yo'q).
    assert distance_to_zone(99.0, 100.0, 105.0) == distance_to_zone(99.0, 100.0, 105.0)


# ======================================================================
# setup_status — DETECTED / ZONE_REACHED / MOVED_PAST (sof funksiya)
# ======================================================================


def test_setup_status_below_zone_is_detected() -> None:
    assert setup_status(57.51, 57.66, 58.60) is SetupStatus.DETECTED


def test_setup_status_inside_zone_is_zone_reached() -> None:
    assert setup_status(58.00, 57.66, 58.60) is SetupStatus.ZONE_REACHED


def test_setup_status_at_low_boundary_is_zone_reached() -> None:
    assert setup_status(57.66, 57.66, 58.60) is SetupStatus.ZONE_REACHED


def test_setup_status_at_high_boundary_is_zone_reached() -> None:
    assert setup_status(58.60, 57.66, 58.60) is SetupStatus.ZONE_REACHED


def test_setup_status_above_zone_is_moved_past() -> None:
    assert setup_status(60.20, 57.66, 58.60) is SetupStatus.MOVED_PAST


# ======================================================================
# contains_directive_language — word-boundary asosidagi non-directive guard
# ======================================================================


def test_contains_directive_language_detects_action_words() -> None:
    for directive in ("BUY now", "sell", "🚀", "enter now", "strong buy", "kir!", "kirish kerak"):
        assert contains_directive_language(directive), directive


def test_contains_directive_language_allows_neutral_observation_text() -> None:
    for neutral in (
        "entry zone",
        "ZONE REACHED",
        "kuzatuv — kirish qarori sizniki",
        "struktura eskirgan bo'lishi mumkin",
        "MOVED PAST (o'tib ketgan, kirish kech)",
        "DETECTED (zona ostida)",
    ):
        assert not contains_directive_language(neutral), neutral


# ======================================================================
# payload_from_setup — current_price -> distance_to_zone + status propagation
# ======================================================================


def test_payload_from_setup_maps_current_price_distance_and_status() -> None:
    payload = payload_from_setup(
        _setup(entry=58.0), symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1), entry_zone=(57.66, 58.60), current_price=57.51,
    )
    assert payload.current_price == pytest.approx(57.51)
    assert payload.distance_to_zone == pytest.approx(-0.26, abs=0.01)
    assert payload.status is SetupStatus.DETECTED


def test_payload_from_setup_current_price_none_gives_none_distance_and_status() -> None:
    payload = payload_from_setup(
        _setup(), symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    assert payload.current_price is None
    assert payload.distance_to_zone is None
    assert payload.status is None


def test_payload_from_setup_does_not_recompute_score_target_rr_with_current_price() -> None:
    """current_price berilishi scoring/target/R:R'ga TEGMAYDI (observation-only)."""
    base = payload_from_setup(
        _setup(entry=100.0, stop=90.0, target=127.0, score=84.0),
        symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1),
    )
    with_price = payload_from_setup(
        _setup(entry=100.0, stop=90.0, target=127.0, score=84.0),
        symbol="AAPL", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.0, historical_win_rate_pct=0.0, historical_period_label="-",
        data_freshness=date(2026, 1, 1), current_price=95.0,
    )
    assert with_price.score == base.score
    assert with_price.potential_target == base.potential_target
    assert with_price.risk_reward == base.risk_reward
    assert with_price.invalidation == base.invalidation


# ======================================================================
# format_payload — Observed price + Status qatorlari (setup observation)
# ======================================================================


def _payload_with_price(current_price: float, entry_zone: tuple[float, float]) -> SignalPayload:
    p = dataclasses.replace(_payload(), entry_zone=entry_zone, current_price=current_price)
    return dataclasses.replace(
        p,
        distance_to_zone=distance_to_zone(current_price, *entry_zone),
        status=setup_status(current_price, *entry_zone),
    )


def test_format_payload_shows_observed_price_and_status_detected() -> None:
    text = format_payload(_payload_with_price(57.51, (57.66, 58.60)))

    assert "Observed price: $57.51 (zonagacha -0.26%)" in text
    assert "Status: DETECTED (zona ostida)" in text


def test_format_payload_status_zone_reached() -> None:
    text = format_payload(_payload_with_price(58.00, (57.66, 58.60)))

    assert "Status: ZONE REACHED (kuzatuv — kirish qarori sizniki)" in text


def test_format_payload_status_moved_past() -> None:
    text = format_payload(_payload_with_price(60.20, (57.66, 58.60)))

    assert "Status: MOVED PAST (o'tib ketgan, kirish kech)" in text


def test_format_payload_observed_price_placed_after_context_before_entry_zone() -> None:
    lines = format_payload(_payload_with_price(57.51, (57.66, 58.60))).splitlines()

    ctx_idx = next(i for i, l in enumerate(lines) if l.startswith("Trend:"))
    entry_idx = next(i for i, l in enumerate(lines) if l.startswith("Entry zone:"))
    assert lines[ctx_idx + 1].startswith("Observed price:")
    assert lines[ctx_idx + 2].startswith("Status:")
    assert entry_idx == ctx_idx + 3


def test_format_payload_omits_observed_price_and_status_when_no_current_price() -> None:
    text = format_payload(_payload())  # current_price default'i None

    assert "Observed price:" not in text
    assert "Status:" not in text


def test_format_payload_observed_status_no_directive_language() -> None:
    for cp in (57.51, 58.00, 60.20):
        text = format_payload(_payload_with_price(cp, (57.66, 58.60)))
        assert not contains_directive_language(text), cp


# ======================================================================
# format_payload — momentum_warning qatori (falling-knife ogohlantirishi)
# ======================================================================


def test_format_payload_shows_momentum_warning_line_when_true() -> None:
    payload = dataclasses.replace(_payload(), momentum_warning=True)
    text = format_payload(payload)

    assert "⚠️ So'nggi momentum pastga — struktura eskirgan bo'lishi mumkin, chartni tekshiring." in text


def test_format_payload_omits_momentum_warning_line_when_false() -> None:
    payload = _payload()  # momentum_warning default'i False

    assert "⚠️" not in format_payload(payload)


def test_format_payload_momentum_warning_placed_after_entry_zone() -> None:
    payload = dataclasses.replace(_payload(), current_price=58.00, momentum_warning=True)
    lines = format_payload(payload).splitlines()

    entry_zone_idx = next(i for i, l in enumerate(lines) if l.startswith("Entry zone:"))
    assert lines[entry_zone_idx + 1].startswith("⚠️")


def test_format_payload_momentum_warning_placed_after_entry_zone_when_no_current_price() -> None:
    payload = dataclasses.replace(_payload(), momentum_warning=True)  # current_price=None
    lines = format_payload(payload).splitlines()

    entry_zone_idx = next(i for i, l in enumerate(lines) if l.startswith("Entry zone:"))
    assert lines[entry_zone_idx + 1].startswith("⚠️")


def test_format_payload_momentum_warning_no_directive_language() -> None:
    """Word-boundary guard: "eskirgan"/"tekshiring" ichidagi "kir" — direktiv EMAS."""
    payload = dataclasses.replace(_payload(), momentum_warning=True)

    assert not contains_directive_language(format_payload(payload))


def test_momentum_warning_defaults_to_false() -> None:
    assert _payload().momentum_warning is False


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
