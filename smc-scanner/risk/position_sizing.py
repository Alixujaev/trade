"""Pozitsiya o'lchamini hisoblash — backtest/engine.py::run_backtest fixed_pct
sizing mantig'iga mos (engine.py:192-208), lekin bu yerda aksiyalar SONI butun
songa (floor) yaxlitlanadi — qo'lda TradingView'da to'ldiriladigan haqiqiy order
kasr aksiya bo'lolmaydi. risk_dollars shu yaxlitlangan son asosida qayta
hisoblanadi, shunda ko'rsatilgan risk haqiqatda xavf qilinadigan summaga mos keladi.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import DEFAULT_RISK_PCT


@dataclass(frozen=True)
class PositionSize:
    """Bitta setup uchun hisoblangan pozitsiya o'lchami."""

    shares: int
    risk_dollars: float
    risk_pct: float


def calculate_position_size(
    capital: float,
    entry_price: float,
    stop_price: float,
    risk_pct: float = DEFAULT_RISK_PCT,
) -> PositionSize:
    """capital, entry/stop narxlari va risk foizidan aksiyalar sonini hisoblaydi."""
    per_share_risk = entry_price - stop_price
    if per_share_risk <= 0:
        return PositionSize(shares=0, risk_dollars=0.0, risk_pct=risk_pct)

    risk_amount = risk_pct * capital
    raw_shares = risk_amount / per_share_risk

    if raw_shares * entry_price > capital:
        raw_shares = capital / entry_price

    shares = int(raw_shares)  # floor — qo'lda to'ldiriladigan haqiqiy order kasr bo'lolmaydi
    risk_dollars = shares * per_share_risk

    return PositionSize(shares=shares, risk_dollars=risk_dollars, risk_pct=risk_pct)
