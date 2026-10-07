"""SignalPayload -> JournalEntry snapshot kwargs (TZ).

Trade ochilganda o'sha paytdagi BUTUN setup holati journalga tushishi kerak — oylar
o'tib "nega kirilgan edi, setup qanday edi" degan savolga bias'siz javob berish uchun
(2 oydan keyin "AAPL +2.1R" raqamining o'zi kontekstsiz hech narsa aytmaydi).

Bu modul SOF: I/O yo'q, scoring/strategy/scan'ga TEGMAYDI — faqat mavjud SignalPayload
maydonlarini TradeJournal.add_entry() kutgan snapshot kwarg nomlariga map qiladi.
Operatsion maydonlar (entry_price/stop_price/target_price/reason — haqiqiy savdo
parametrlari, foydalanuvchi tanlovi) BU YERDA YO'Q — ularni chaqiruvchi (masalan
telegram_bot/handlers.py::signal_quickadd_start) alohida, o'z siyosati bilan hosil
qiladi (masalan qaysi narxni entry_price sifatida olish — observed price yoki zona
o'rtachasi — bu UI/UX qarori, snapshot mapping'ning ishi emas).
"""

from __future__ import annotations

from signals.payload import SignalPayload


def snapshot_kwargs_from_payload(payload: SignalPayload) -> dict:
    """SignalPayload'dan `TradeJournal.add_entry(**kwargs)`ga to'g'ridan-to'g'ri
    uzatiladigan snapshot kwarg'lar lug'atini quradi (setup_type, score, ...).

    `payload.status=None` bo'lsa (masalan current_price berilmagan) -> "status": None
    (enum emas, JournalEntry.status oddiy string — `SetupStatus.name`)."""
    entry_zone_low, entry_zone_high = payload.entry_zone
    return {
        "setup_type": payload.setup_type,
        "score": payload.score,
        "score_label": payload.score_label,
        "trend": payload.context.trend,
        "structure": payload.context.structure,
        "volume_confirmed": payload.context.volume_confirmed,
        "entry_zone_low": entry_zone_low,
        "entry_zone_high": entry_zone_high,
        "invalidation": payload.invalidation,
        "target": payload.potential_target,
        "risk_reward": payload.risk_reward,
        "target_source": payload.target_source,
        "status": payload.status.name if payload.status is not None else None,
        "score_reasons": payload.score_reasons,
    }
