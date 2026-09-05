"""Savdo jurnali yozuvi uchun data modeli."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class JournalEntry:
    """Bitta HAQIQIY (paper yoki live) savdo yozuvi.

    backtest/types.py::TradeResult'dan farqi: bu SIMULYATSIYA emas — foydalanuvchi
    o'zi qo'lda kiritgan haqiqiy qaror va (yopilgach) haqiqiy natija. Yopilmagan
    (exit_date=None) yozuvlar ochiq pozitsiyani anglatadi.
    """

    entry_id: int
    symbol: str
    entry_date: date
    entry_price: float
    stop_price: float
    target_price: float | None  # None — exit_mode="trailing" (maqsad yo'q)
    exit_mode: str  # "fixed" | "trailing"
    reason: str  # masalan "FVG", "ORDER_BLOCK" yoki foydalanuvchi o'z izohi
    rr_planned: float | None  # (target-entry)/(entry-stop); target_price=None bo'lsa None
    reference_target_price: float | None = None  # generate_signals'ning "reference" target'i
    # (swing-high yoki R-multiple fallback) — target_price=None (trailing) bo'lsa ham
    # mavjud bo'lishi mumkin, FAQAT rr_planned hisoblash uchun, HAQIQIY chiqish narxi
    # EMAS (backtest'da ishlatilmaydi).
    notes: str = ""
    exit_date: date | None = None
    exit_price: float | None = None
    r_multiple: float | None = None  # yopilgach: (exit-entry)/(entry-stop)

    # ------------------------------------------------------------------
    # Setup snapshot (TZ) — trade ochilgan PAYTDAGI to'liq setup konteksti
    # (signals.payload.SignalPayload'dan, mavjud bo'lsa). Barchasi Optional/
    # default'li — /add (qo'lda, payload'siz) yozuvlarda bo'sh qoladi, ESKI
    # (bu maydonlar qo'shilishidan oldingi) yozuvlar buzilmaydi. Bu — TAHLIL
    # uchun muzlatilgan tarixiy yozuv: keyinchalik stop/target ko'chsa ham
    # (savdo boshqaruvi), shu yerdagi qiymatlar entry paytidagi holatni
    # saqlaydi ("nega kirilgan edi" degan savolga bias'siz javob).
    # ------------------------------------------------------------------
    setup_type: str | None = None  # masalan "breakout_retest", "fvg"
    score: float | None = None  # 0..100
    score_label: str | None = None  # STRONG SETUP / SETUP / WATCH / WEAK
    trend: str | None = None
    structure: str | None = None
    volume_confirmed: bool | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    invalidation: float | None = None  # setup'ning structural stop darajasi (entry paytida)
    target: float | None = None  # setup'ning potential_target'i (entry paytida, target_price'dan MUSTAQIL)
    risk_reward: float | None = None  # setup'ning o'z R:R'i (entry paytida)
    target_source: str | None = None  # "resistance" | "fallback" | None
    status: str | None = None  # SetupStatus.name (masalan "ZONE_REACHED") — entry paytida
    score_reasons: tuple[str, ...] = ()  # scanner ko'rgan faktlar (audit)
