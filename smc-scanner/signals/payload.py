"""Setup'ni bir xil aniqlaydigan barqaror signal_id (TZ 18 — dedup uchun kalit).

Bir xil setup (symbol + setup turi + entry bar sanasi/narxi + exit mode) qayta
skan qilinganda AYNAN bir xil ID chiqishi kerak (idempotent) — shu orqali
signals/dedup.py bir xil setup allaqachon ko'rsatilganini biladi.

MUHIM: bu modul hech narsani filtrlamaydi/o'zgartirmaydi — faqat mavjud
tactical_scan.py qatoridan (yoki xom qiymatlardan) sof ID hisoblaydi.

Signal payload — "setup intelligence", "BUY signal" EMAS.

Bot endi trading robot emas, decision-support scanner: setup topadi, ma'lumot ustunligi
beradi, YAKUNIY QARORNI ODAM qiladi. Shu tufayli bu modul ATAYLAB hech qanday direktiv
(harakatga chorlovchi) til ishlatmaydi — "BUY"/"SELL"/"🚀"/"enter now" kabi so'zlar bu
faylning HECH BIR qismida (dataclass maydonlari, konstantalar, shablonlar) uchramasligi
kerak; `tests/test_payload.py::test_payload_no_directive_language` shu tamoyilni kod bilan
majburlaydi.

Bearish setup HECH QACHON short-entry taklifi emas (cash account, short yo'q) — faqat
"AVOID / EXIT candidate" sifatida ko'rsatiladi.

Bu modul sof domen ishi: I/O yo'q, tarmoq yo'q, hech narsani qayta hisoblamaydi.
`payload_from_setup` mavjud `smc.types.TradeSetup`dagi ma'lumotni to'g'ridan-to'g'ri map
qiladi; trend/structure/volume/tarixiy statistika kabi TradeSetup'da YO'Q kontekst
chaqiruvchidan (masalan kelajakdagi scanner integratsiyasi) tashqaridan uzatiladi.
"""

from __future__ import annotations

import hashlib


def compute_signal_id(
    *, symbol: str, setup_type: str, entry_ts: str, entry_price: float, mode: str
) -> str:
    """symbol+setup_type+entry_ts+entry_price+mode'dan barqaror hash (16 hex belgi).

    entry_price float sifatida keladi (masalan tactical_scan.py'da round(..., 2))
    — qat'iy formatlash (`:.6f`) turli float repr'laridan kelib chiqadigan
    nomuvofiqlikning oldini oladi.
    """
    key = f"{symbol}|{setup_type}|{entry_ts}|{entry_price:.6f}|{mode}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def signal_id_for_row(row: dict, *, mode: str) -> str | None:
    """tactical_scan.py::build_scan_row natijasi (qator)dan signal_id.

    Kerakli maydonlar (SYMBOL, SETUP_REASON, SETUP_ENTRY_DATE, SETUP_ENTRY) yo'q
    bo'lsa (masalan faol setup yo'q) — None. Chaqiruvchi None'ni dedup'siz
    o'tkazish kerakligi sifatida talqin qiladi.
    """
    symbol = row.get("SYMBOL")
    setup_type = row.get("SETUP_REASON")
    entry_ts = row.get("SETUP_ENTRY_DATE")
    entry_price = row.get("SETUP_ENTRY")
    if not symbol or not setup_type or entry_ts is None or entry_price is None:
        return None
    return compute_signal_id(
        symbol=symbol, setup_type=setup_type, entry_ts=entry_ts,
        entry_price=float(entry_price), mode=mode,
    )
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum, auto

from config.settings import SCORE_THRESHOLDS
from smc.types import StructureState, TradeSetup

# ======================================================================
# Neytral score yorliqlari — strategy/scoring.py::label_for_score bilan BIR XIL chegaralar
# (SCORE_THRESHOLDS), lekin matn NEYTRAL ("BUY" emas).
# ======================================================================

_SCORE_LABELS: dict[str, str] = {
    "strong_setup": "STRONG SETUP",
    "setup": "SETUP",
    "watch": "WATCH",
    "weak": "WEAK",
}


def score_label_for(score: float, thresholds: dict[str, float] = SCORE_THRESHOLDS) -> str:
    """0..100 ball -> neytral yorliq (STRONG SETUP/SETUP/WATCH/WEAK)."""
    if score >= thresholds["strong_buy"]:
        return _SCORE_LABELS["strong_setup"]
    if score >= thresholds["buy"]:
        return _SCORE_LABELS["setup"]
    if score >= thresholds["watch"]:
        return _SCORE_LABELS["watch"]
    return _SCORE_LABELS["weak"]


# ======================================================================
# Dataclass'lar
# ======================================================================


class SignalMode(Enum):
    """Signal rejimi — hozircha faqat SWING (V1 breakout+retest kunlik/haftalik ufqi)."""

    SWING = auto()


@dataclass(frozen=True)
class SignalContext:
    """Setup atrofidagi bozor konteksti — TradeSetup'da saqlanmaydi, tashqaridan uzatiladi
    (trend/structure/volume hisoblash strategy/ qatlamining ishi, bu yerda takrorlanmaydi)."""

    trend: str  # masalan "BULLISH"/"BEARISH"/"NEUTRAL"
    structure: str  # masalan "BOS"/"CHoCH"/"-"
    volume_confirmed: bool
    smc: str | None = None  # ixtiyoriy qo'shimcha SMC konteksti (masalan zona nomi)


_DEFAULT_HISTORICAL_DISCLAIMER = "Bu kelajak natija kafolati emas."


@dataclass(frozen=True)
class HistoricalContext:
    """Shu setup turining backtest statistikasi — NEYTRAL ma'lumot, "profit kafolati" EMAS.

    `disclaimer` doim to'ldirilgan (default bilan) — shu ogohlantirish payload'dan
    hech qachon ajralib qolmasligi kerak.
    """

    expectancy_r: float
    win_rate_pct: float
    period_label: str
    disclaimer: str = _DEFAULT_HISTORICAL_DISCLAIMER


@dataclass(frozen=True)
class SignalPayload:
    """Bitta setup uchun to'liq, o'z-o'zini tavsiflovchi ma'lumot.

    HECH QACHON direktiv emas — "BUY"/"SELL" emas, faqat neytral holat tavsifi. Yakuniy
    qarorni ODAM qabul qiladi; bu payload faqat shu qarorga kerakli ma'lumotni beradi.
    """

    symbol: str
    mode: SignalMode
    setup_type: str  # masalan "breakout_retest"
    score: float  # 0..100
    score_label: str  # STRONG SETUP / SETUP / WATCH / WEAK
    direction: StructureState  # BULLISH -> potentsial long setup; BEARISH -> AVOID/EXIT candidate
    entry_zone: tuple[float, float]  # (low, high) — aniq narx emas, zona
    invalidation: float  # strukturaviy stop darajasi
    potential_target: float
    risk_reward: float
    context: SignalContext
    historical_context: HistoricalContext
    generated_at: datetime
    timeframe: str
    data_freshness: date  # oxirgi mavjud bar sanasi
    entry_ts: date | None = None  # setup.entry_ts sanasi (TZ 18 dedup uchun — signal_id_for_payload)


# ======================================================================
# TradeSetup -> SignalPayload converter
# ======================================================================

_SETUP_TYPE_BY_REASON_PREFIX: dict[str, str] = {
    "BREAKOUT_RETEST": "breakout_retest",
    "FVG": "fvg",
    "ORDER_BLOCK": "order_block",
}


def setup_type_from_reason(reason: str) -> str:
    """TradeSetup.reason ("FVG"/"ORDER_BLOCK"/"BREAKOUT_RETEST@<band>") -> qisqa setup_type."""
    for prefix, setup_type in _SETUP_TYPE_BY_REASON_PREFIX.items():
        if reason.startswith(prefix):
            return setup_type
    return reason.lower()


def payload_from_setup(
    setup: TradeSetup,
    *,
    symbol: str,
    trend: str,
    structure: str,
    volume_confirmed: bool,
    historical_expectancy_r: float,
    historical_win_rate_pct: float,
    historical_period_label: str,
    data_freshness: date,
    timeframe: str = "1d",
    mode: SignalMode = SignalMode.SWING,
    smc: str | None = None,
    entry_zone: tuple[float, float] | None = None,
    generated_at: datetime | None = None,
) -> SignalPayload:
    """`TradeSetup`dan `SignalPayload` quradi — hech narsani QAYTA HISOBLAMAYDI, faqat
    mavjud maydonlarni map qiladi.

    `trend`/`structure`/`volume_confirmed`/`smc`/`historical_*` — TradeSetup'da YO'Q
    kontekst (strategy/scoring.py allaqachon hisoblab bergan bo'lardi); chaqiruvchi
    tashqaridan uzatadi. `entry_zone` berilmasa — TradeSetup bitta narx (entry_price)
    saqlagani uchun (low, high) = (entry_price, entry_price) sifatida qo'yiladi (haqiqiy
    zona kengligi keyingi scanner-integratsiya bosqichida qo'shiladi).
    """
    if entry_zone is None:
        entry_zone = (setup.entry_price, setup.entry_price)

    risk = setup.entry_price - setup.stop_price
    reward = setup.target_price - setup.entry_price
    risk_reward = reward / risk if risk > 0 else 0.0

    score = setup.score if setup.score is not None else 0.0

    return SignalPayload(
        symbol=symbol,
        mode=mode,
        setup_type=setup_type_from_reason(setup.reason),
        score=score,
        score_label=score_label_for(score),
        direction=setup.direction,
        entry_zone=entry_zone,
        invalidation=setup.stop_price,
        potential_target=setup.target_price,
        risk_reward=risk_reward,
        context=SignalContext(
            trend=trend, structure=structure, volume_confirmed=volume_confirmed, smc=smc,
        ),
        historical_context=HistoricalContext(
            expectancy_r=historical_expectancy_r, win_rate_pct=historical_win_rate_pct,
            period_label=historical_period_label,
        ),
        generated_at=generated_at or datetime.now(timezone.utc),
        timeframe=timeframe,
        data_freshness=data_freshness,
        entry_ts=setup.entry_ts.date(),
    )


def signal_id_for_payload(payload: SignalPayload) -> str | None:
    """`SignalPayload`dan barqaror signal_id (TZ 18) — `signal_id_for_row` (/scan,
    row-dict oqimi) bilan BIR XIL hash mexanizmi (`compute_signal_id`), lekin
    `signals/scanner.py`ning yangi, non-directive `SignalPayload` maydonlaridan:

    - entry_price `entry_zone`dan tiklanadi: `(low+high)/2` — `signals/scanner.py::
      _entry_zone` har doim `entry_price` atrofida SIMMETRIK kengaytiradi (yoki
      degenerativ holatda `(entry_price, entry_price)`), shu sabab bu qiymat ANIQ,
      qayta hisoblash emas.
    - mode sifatida `payload.mode.name` ("SWING") ishlatiladi — `SignalPayload`
      o'zining skan-rejimini allaqachon saqlaydi, tashqaridan uzatish shart emas
      (row-dict oqimidan farqli, u yerda exit_mode alohida uzatiladi).

    `payload.entry_ts=None` bo'lsa (masalan eski/test payload, `entry_ts` default'i)
    — None; chaqiruvchi (`signal_id_for_row` kabi) buni dedup'siz o'tkazish kerakligi
    sifatida talqin qiladi.
    """
    if payload.entry_ts is None:
        return None
    low, high = payload.entry_zone
    return compute_signal_id(
        symbol=payload.symbol, setup_type=payload.setup_type,
        entry_ts=payload.entry_ts.isoformat(), entry_price=(low + high) / 2,
        mode=payload.mode.name,
    )


# ======================================================================
# format_payload — Telegram-friendly matn (monospace-mos, emojisiz)
# ======================================================================

_SETUP_TYPE_DISPLAY: dict[str, str] = {
    "breakout_retest": "Breakout + Retest",
    "fvg": "Fair Value Gap",
    "order_block": "Order Block",
}

_LONG_HEADER_TEMPLATE = "{symbol} — {mode} setup"
_AVOID_HEADER_TEMPLATE = "{symbol} — {mode} setup — AVOID / EXIT candidate"
_SETUP_LINE_TEMPLATE = "Setup: {setup_type}   |   Score: {score:.0f}/100 ({score_label})"
_CONTEXT_LINE_TEMPLATE = "Trend: {trend}   Structure: {structure}   Volume: {volume}"
_ENTRY_ZONE_LINE_TEMPLATE = "Entry zone: ${low:.2f} – ${high:.2f}"
_INVALIDATION_LINE_TEMPLATE = "Invalidation: ${invalidation:.2f}"
_TARGET_LINE_TEMPLATE = "Target: ${target:.2f}   R:R: {rr:.1f}"
_AVOID_NOTE = (
    "Bearish bias — yangi LONG entry uchun mos emas; mavjud pozitsiya uchun "
    "kuzatish/chiqish signali."
)
_SEPARATOR_LINE = "---"
_BACKTEST_LINE_TEMPLATE = (
    "Backtest context: expectancy {expectancy:+.2f}R, win-rate {win_rate:.0f}% "
    "({period}). {disclaimer}"
)
_FOOTER_LINE_TEMPLATE = "Generated: {generated}   Data: {data}"

_VOLUME_DISPLAY = {True: "Confirmed", False: "Not confirmed"}


def _setup_type_display(setup_type: str) -> str:
    return _SETUP_TYPE_DISPLAY.get(setup_type, setup_type.replace("_", " ").title())


def format_payload(payload: SignalPayload) -> str:
    """`SignalPayload`ni Telegram-friendly, monospace-mos matnga aylantiradi.

    Emoji yo'q, hech qanday direktiv til ishlatilmaydi. Bearish (`direction=BEARISH`)
    setup'lar uchun entry/target ko'rsatilmaydi — faqat "AVOID / EXIT candidate" holati
    va invalidation darajasi.
    """
    is_bearish = payload.direction is StructureState.BEARISH
    header_template = _AVOID_HEADER_TEMPLATE if is_bearish else _LONG_HEADER_TEMPLATE
    lines = [header_template.format(symbol=payload.symbol, mode=payload.mode.name)]

    lines.append(_SETUP_LINE_TEMPLATE.format(
        setup_type=_setup_type_display(payload.setup_type),
        score=payload.score, score_label=payload.score_label,
    ))
    lines.append(_CONTEXT_LINE_TEMPLATE.format(
        trend=payload.context.trend, structure=payload.context.structure,
        volume=_VOLUME_DISPLAY[payload.context.volume_confirmed],
    ))

    if is_bearish:
        lines.append(_AVOID_NOTE)
        lines.append(_INVALIDATION_LINE_TEMPLATE.format(invalidation=payload.invalidation))
    else:
        low, high = payload.entry_zone
        lines.append(_ENTRY_ZONE_LINE_TEMPLATE.format(low=low, high=high))
        lines.append(_INVALIDATION_LINE_TEMPLATE.format(invalidation=payload.invalidation))
        lines.append(_TARGET_LINE_TEMPLATE.format(
            target=payload.potential_target, rr=payload.risk_reward,
        ))

    lines.append(_SEPARATOR_LINE)
    lines.append(_BACKTEST_LINE_TEMPLATE.format(
        expectancy=payload.historical_context.expectancy_r,
        win_rate=payload.historical_context.win_rate_pct,
        period=payload.historical_context.period_label,
        disclaimer=payload.historical_context.disclaimer,
    ))
    lines.append(_FOOTER_LINE_TEMPLATE.format(
        generated=payload.generated_at.strftime("%Y-%m-%d %H:%M"),
        data=payload.data_freshness.strftime("%Y-%m-%d"),
    ))

    return "\n".join(lines)
