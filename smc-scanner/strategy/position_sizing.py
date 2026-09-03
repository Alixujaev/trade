"""Risk position sizing va R:R gate (TZ 12, 14).

1% risk sizing: bir savdoda hisob kapitalining `risk_pct` ulushi risk qilinadi,
aksiyalar soni = (risk_pct * equity) / (entry - stop). Spot/leveragesiz — agar
pozitsiya qiymati kapitaldan oshsa, kapital/entry gacha KICHRAYTIRILADI
(backtest/engine.py sizing mantig'i bilan bir xil).

R:R gate: rejalashtirilgan R:R min chegaradan past bo'lsa savdo QILINMAYDI.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import MIN_BREAKOUT_RR, RISK_PCT_PER_TRADE
from smc.signal import compute_planned_rr
from smc.types import TradeSetup


@dataclass(frozen=True)
class PositionPlan:
    """Bitta savdoning hajmi va maqbulligi."""

    shares: float
    dollar_risk: float
    per_share_risk: float
    capped_to_equity: bool  # pozitsiya kapital/entry gacha kichraytirilganmi
    acceptable: bool  # savdoni qilsa bo'ladimi (shares > 0)
    reason: str


def size_position(
    account_equity: float,
    entry: float,
    stop: float,
    *,
    risk_pct: float = RISK_PCT_PER_TRADE,
) -> PositionPlan:
    """`account_equity` va entry/stop'dan pozitsiya rejasi (aksiya soni bilan)."""
    per_share_risk = entry - stop
    if per_share_risk <= 0:
        return PositionPlan(
            shares=0.0, dollar_risk=0.0, per_share_risk=per_share_risk,
            capped_to_equity=False, acceptable=False, reason="stop entry'dan past emas",
        )
    if account_equity <= 0:
        return PositionPlan(
            shares=0.0, dollar_risk=0.0, per_share_risk=per_share_risk,
            capped_to_equity=False, acceptable=False, reason="kapital <= 0",
        )

    dollar_risk = risk_pct * account_equity
    shares = dollar_risk / per_share_risk

    capped = False
    if shares * entry > account_equity:
        shares = account_equity / entry
        capped = True

    return PositionPlan(
        shares=shares,
        dollar_risk=dollar_risk,
        per_share_risk=per_share_risk,
        capped_to_equity=capped,
        acceptable=shares > 0,
        reason="kapital cheklovi bilan kichraytirildi" if capped else "ok",
    )


def rr_gate(setup: TradeSetup, *, min_rr: float = MIN_BREAKOUT_RR) -> bool:
    """Setup'ning rejalashtirilgan R:R'i `min_rr`dan katta-tengmi (None -> False)."""
    rr = compute_planned_rr(setup)
    return rr is not None and rr >= min_rr
