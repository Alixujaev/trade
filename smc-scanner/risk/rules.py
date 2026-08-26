"""Kunlik risk limiti va maksimal ochiq pozitsiya soni tekshiruvi — ogohlantirish
uchun (qat'iy bloklamaydi, /add shu natijani ko'rsatib foydalanuvchiga qaror qoldiradi)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from journal.trade_journal import TradeJournal


@dataclass(frozen=True)
class RiskCheckResult:
    """check_daily_risk() natijasi — ok=False bo'lsa ham savdo bloklanmaydi, faqat ogohlantiriladi."""

    ok: bool
    warnings: list[str] = field(default_factory=list)


def check_daily_risk(
    journal: TradeJournal,
    capital: float,
    max_daily_risk_pct: float,
    max_open_positions: int,
) -> RiskCheckResult:
    """Bugun ochilgan savdolarning jami $ risk'i va ochiq pozitsiyalar sonini limitlarga solishtiradi.

    Jami $ risk faqat `shares` saqlangan yozuvlar bo'yicha hisoblanadi — eski (shares=None)
    yozuvlar chetlab o'tiladi, ular haqiqiy risk qiymatini bilmaydi.
    """
    warnings: list[str] = []

    open_count = len(journal.open_entries())
    if open_count > max_open_positions:
        warnings.append(
            f"Ochiq pozitsiya soni ({open_count}) limitdan ({max_open_positions}) oshib ketdi."
        )

    today = date.today()
    today_risk = sum(
        e.shares * (e.entry_price - e.stop_price)
        for e in journal.entries
        if e.entry_date == today and e.shares is not None
    )
    max_daily_risk = max_daily_risk_pct * capital
    if today_risk > max_daily_risk:
        warnings.append(
            f"Bugungi kunlik risk (${today_risk:.2f}) limitdan (${max_daily_risk:.2f}) oshib ketdi."
        )

    return RiskCheckResult(ok=not warnings, warnings=warnings)
