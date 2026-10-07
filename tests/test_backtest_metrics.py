"""backtest/metrics.py uchun testlar (qo'lda hisoblangan qiymatlar)."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.metrics import (
    avg_hold_days,
    avg_r_multiple,
    buy_and_hold_return_pct,
    expectancy_r,
    max_drawdown_pct,
    profit_factor,
    win_rate,
)
from backtest.types import TradeResult


def _make_trade(r_multiple: float, pnl: float, hold_days: float = 3.0) -> TradeResult:
    """Faqat metrikalar uchun kerakli maydonlar bilan sodda TradeResult yasaydi."""
    ts = pd.Timestamp("2024-01-01", tz="UTC")
    return TradeResult(
        entry_ts=ts,
        exit_ts=ts + pd.Timedelta(days=hold_days),
        entry_price=100.0,
        exit_price=100.0 + r_multiple * 10.0,
        entry_index_pos=0,
        exit_index_pos=1,
        shares=1.0,
        exit_reason="target" if pnl > 0 else "stop",
        r_multiple=r_multiple,
        pnl=pnl,
        hold_duration_days=hold_days,
        mae_r=0.0,
        mfe_r=max(r_multiple, 0.0),
    )


# 3 g'olib (R=2,1,1.5) + 2 yutqazgan (R=-1,-1) — qo'lda hisoblangan kutilgan natijalar
_TRADES = [
    _make_trade(r_multiple=2.0, pnl=200.0, hold_days=2.0),
    _make_trade(r_multiple=1.0, pnl=100.0, hold_days=4.0),
    _make_trade(r_multiple=1.5, pnl=150.0, hold_days=3.0),
    _make_trade(r_multiple=-1.0, pnl=-100.0, hold_days=1.0),
    _make_trade(r_multiple=-1.0, pnl=-100.0, hold_days=5.0),
]


def test_win_rate() -> None:
    assert win_rate(_TRADES) == pytest.approx(3 / 5)


def test_avg_r_multiple() -> None:
    # (2.0+1.0+1.5-1.0-1.0)/5 = 2.5/5 = 0.5
    assert avg_r_multiple(_TRADES) == pytest.approx(0.5)


def test_expectancy_r_matches_avg_r_multiple_identity() -> None:
    """expectancy_r win/loss dekompozitsiyasi orqali hisoblanadi, lekin matematik
    jihatdan avg_r_multiple bilan bir xil bo'lishi SHART — bu regressiya himoyasi."""
    assert expectancy_r(_TRADES) == pytest.approx(avg_r_multiple(_TRADES))


def test_profit_factor() -> None:
    # gross_profit=200+100+150=450, gross_loss=100+100=200 -> 450/200=2.25
    assert profit_factor(_TRADES) == pytest.approx(2.25)


def test_profit_factor_no_losses_is_infinite() -> None:
    winners_only = [_make_trade(1.0, 100.0)]
    assert profit_factor(winners_only) == float("inf")


def test_max_drawdown_pct_hand_computed() -> None:
    # 10000 -> 11000 (peak) -> 9900 (10% pasayish 11000dan) -> 10500
    equity_curve = [10000.0, 11000.0, 9900.0, 10500.0]
    assert max_drawdown_pct(equity_curve) == pytest.approx(10.0)


def test_buy_and_hold_return_pct_hand_computed() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": [100, 105, 110], "high": [101, 106, 111], "low": [99, 104, 109],
         "close": [100, 105, 110], "volume": [1000] * 3},
        index=index,
    )
    # (110-100)/100*100 = 10%
    assert buy_and_hold_return_pct(df) == pytest.approx(10.0)


def test_avg_hold_days() -> None:
    # (2+4+3+1+5)/5 = 3.0
    assert avg_hold_days(_TRADES) == pytest.approx(3.0)


def test_empty_trades_returns_neutral_values_no_crash() -> None:
    assert win_rate([]) == 0.0
    assert avg_r_multiple([]) == 0.0
    assert expectancy_r([]) == 0.0
    assert profit_factor([]) == 0.0
    assert avg_hold_days([]) == 0.0
    assert max_drawdown_pct([]) == 0.0
    assert max_drawdown_pct([10000.0]) == 0.0
