"""risk/position_sizing.py uchun testlar (qo'lda hisoblangan qiymatlar)."""

from __future__ import annotations

import pytest

from risk.position_sizing import calculate_position_size


def test_standard_case_computes_shares_and_risk_dollars() -> None:
    # capital=10_000, risk_pct=0.01 -> risk_amount=100; per_share_risk=100-90=10 -> 10 shares
    result = calculate_position_size(capital=10_000, entry_price=100.0, stop_price=90.0, risk_pct=0.01)

    assert result.shares == 10
    assert result.risk_dollars == pytest.approx(100.0)  # 10 shares * 10 per-share risk
    assert result.risk_pct == pytest.approx(0.01)


def test_shares_rounded_down_to_whole_number() -> None:
    # capital=1_000, risk_pct=0.01 -> risk_amount=10; per_share_risk=3 -> 3.33 shares -> floor to 3
    result = calculate_position_size(capital=1_000, entry_price=50.0, stop_price=47.0, risk_pct=0.01)

    assert result.shares == 3
    assert result.risk_dollars == pytest.approx(9.0)  # 3 shares * 3 per-share risk (re-derived from rounded shares)


def test_position_value_capped_at_capital() -> None:
    # entry high relative to capital -> uncapped shares would cost more than capital
    result = calculate_position_size(capital=500, entry_price=100.0, stop_price=99.0, risk_pct=0.5)

    assert result.shares * 100.0 <= 500
    assert result.shares == 5  # floor(500/100)


def test_non_positive_per_share_risk_returns_zero_shares() -> None:
    result = calculate_position_size(capital=10_000, entry_price=100.0, stop_price=100.0, risk_pct=0.01)

    assert result.shares == 0
    assert result.risk_dollars == 0.0


def test_default_risk_pct_used_when_not_specified() -> None:
    from config.settings import DEFAULT_RISK_PCT

    result = calculate_position_size(capital=10_000, entry_price=100.0, stop_price=90.0)

    assert result.risk_pct == pytest.approx(DEFAULT_RISK_PCT)
