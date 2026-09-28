"""strategy/day/scoring.py: Evidence aggregation moduli.

MUHIM METODOLOGIK QOIDA:
- Bu modul BUY/SELL tavsiyasi yoki savdo ehtimolligi reytingi EMAS.
- Faqatgina kursdagi gipotezaga asoslangan dalillar (evidence checklist)
  yig'indisini hisoblaydi (masalan, 4/6 yoki 5/6).
- Hech qanday "BUY SCORE", "STRONG BUY", "PROFITABLE" kabi baholashlar qo'llanilmaydi.
"""

from __future__ import annotations

from typing import NamedTuple


class EvidenceAggregation(NamedTuple):
    """Dalillar yig'indisi natijasi."""

    score: int
    max_score: int
    evidence_list: tuple[str, ...]


def aggregate_day_evidence(
    *,
    is_vwap_reclaim: bool,
    is_above_vwap: bool,
    is_rsi_confirmed: bool,
    is_rvol_confirmed: bool,
    has_5m_trigger: bool,
    is_15m_bullish: bool,
    trigger_desc: str = "",
    rsi_val: float | None = None,
    rvol_val: float | None = None,
) -> EvidenceAggregation:
    """Gipotezaviy komponentlar bo'yicha dalillarni yig'adi.

    Mavjud 6 ta tekshiruv komponenti:
    1. VWAP reclaim
    2. Price above VWAP
    3. RSI > 50 (momentum confirmation)
    4. RVOL >= 2.0 (volume participation)
    5. 5m bullish trigger (CHoCH / previous high break)
    6. 15m structure bullish (MTF alignment)
    """
    evidence: list[str] = []
    score = 0
    max_score = 6

    if is_vwap_reclaim:
        evidence.append("VWAP reclaim")
        score += 1
    elif is_above_vwap:
        evidence.append("VWAP hold / above VWAP")

    if is_above_vwap and not is_vwap_reclaim:
        # Agar reclaim bo'lsa, reclaimning o'zi price above VWAP'ni o'z ichiga oladi
        # lekin ikkala shart mustaqil sanalganda:
        pass

    if is_above_vwap:
        evidence.append("Price above VWAP")
        score += 1

    if is_rsi_confirmed:
        rsi_str = f" ({rsi_val:.1f})" if rsi_val is not None else ""
        evidence.append(f"RSI > 50 momentum{rsi_str}")
        score += 1

    if is_rvol_confirmed:
        rvol_str = f" ({rvol_val:.1f}x)" if rvol_val is not None else ""
        evidence.append(f"RVOL elevated{rvol_str}")
        score += 1

    if has_5m_trigger:
        trig_str = f": {trigger_desc}" if trigger_desc else ""
        evidence.append(f"5m bullish trigger{trig_str}")
        score += 1

    if is_15m_bullish:
        evidence.append("15m bullish structure context")
        score += 1

    return EvidenceAggregation(
        score=score,
        max_score=max_score,
        evidence_list=tuple(evidence),
    )
