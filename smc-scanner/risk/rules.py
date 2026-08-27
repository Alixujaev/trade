"""Maksimal ochiq pozitsiya soni tekshiruvi — ogohlantirish uchun (qat'iy
bloklamaydi, /add shu natijani ko'rsatib foydalanuvchiga qaror qoldiradi).

Kapital/pozitsiya-hajmiga bog'liq $ risk tekshiruvi ATAYLAB yo'q — savdoga
kirish/chiqish bu botda emas, boshqa platformada (masalan TradingView paper
trading) qilinadi, shuning uchun bot haqiqiy pozitsiya hajmini bilmaydi."""

from __future__ import annotations

from dataclasses import dataclass, field

from journal.trade_journal import TradeJournal


@dataclass(frozen=True)
class RiskCheckResult:
    """check_open_positions() natijasi — ok=False bo'lsa ham savdo bloklanmaydi, faqat ogohlantiriladi."""

    ok: bool
    warnings: list[str] = field(default_factory=list)


def check_open_positions(journal: TradeJournal, max_open_positions: int) -> RiskCheckResult:
    """Ochiq pozitsiyalar sonini limitga solishtiradi."""
    open_count = len(journal.open_entries())
    if open_count > max_open_positions:
        return RiskCheckResult(
            ok=False,
            warnings=[f"Ochiq pozitsiya soni ({open_count}) limitdan ({max_open_positions}) oshib ketdi."],
        )
    return RiskCheckResult(ok=True, warnings=[])
