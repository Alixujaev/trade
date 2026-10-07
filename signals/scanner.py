"""Scanner — universe'ni skanerlab, real kontekst bilan to'ldirilgan SignalPayload'lar hosil qiladi.

Bu modul sof domen ishi: `scan_symbol` faqat allaqachon yuklangan `pd.DataFrame` bilan ishlaydi
(tarmoq/IO yo'q). `scan_universe` esa `DataProvider` orqali ma'lumot oladi va har symbol uchun
`scan_symbol`ni chaqiradi — bitta symbol yiqilsa (provider xatosi yoki yetarsiz data) BUTUN skan
TO'XTAMAYDI, o'sha symbol SKIP qilinadi va sababi log qilinadi (hech qachon to'liqsiz data
ustida signal ko'rsatilmaydi).

Mavjud, sinalgan pipeline qayta ishlatiladi (hech narsa qayta yozilmaydi):
`strategy.breakout_retest.generate_breakout_retest_signals`, `strategy.scoring.apply_scores`/
`filter_by_score`, `strategy.trend.compute_trend_regime`/`trend_regime_at`,
`smc.structure.detect_swings`, `smc.market_structure.detect_structure_events`,
`smc.zones.compute_atr`, `indicators.volume.is_volume_confirmed`.
"""

from __future__ import annotations

import logging

import pandas as pd

from config.settings import (
    ATR_PERIOD,
    ENTRY_ZONE_ATR_MULT,
    MIN_BREAKOUT_RR,
    MOMENTUM_WARNING_BARS,
    SIGNAL_RECENCY_BARS,
    SWING_LOOKBACK,
    VOLUME_MA_PERIOD,
)
from data.provider import DataProvider
from indicators.volume import is_volume_confirmed
from signals.payload import SignalMode, SignalPayload, payload_from_setup, setup_type_from_reason
from smc.market_structure import detect_structure_events
from smc.structure import detect_swings
from smc.types import StructureEvent, TradeSetup
from smc.zones import compute_atr
from strategy.breakout_retest import generate_breakout_retest_signals
from strategy.scoring import _structure_event_at, apply_scores, filter_by_score
from strategy.trend import compute_trend_regime, trend_regime_at

logger = logging.getLogger(__name__)

# Setup turining backtest'dagi statik statistikasi — NEYTRAL ma'lumot, kelajak kafolati EMAS
# (signals/payload.py::HistoricalContext.disclaimer buni har doim ta'kidlaydi). Manba:
# `python scripts/backtest_breakout_retest.py AAPL MSFT AMD ADBE AVGO --start 2020-01-01`
# XULOSA bloki — 5 ta symbol, 43 ta savdo, 2020-01-01 dan oxirgi mavjud bar (2026-09-03)gacha.
# Kichik namuna (5 symbol) — kengroq universe bilan qayta kalibrlash keyingi qadam.
HISTORICAL_STATS: dict[str, tuple[float, float, str]] = {
    "breakout_retest": (0.60, 52.8, "2020-2026"),
}
_DEFAULT_HISTORICAL_STAT: tuple[float, float, str] = (0.0, 0.0, "N/A")


_STRUCTURE_EVENT_TYPE_DISPLAY: dict[str, str] = {"BOS": "BOS", "CHOCH": "CHoCH"}


def _structure_display(event: StructureEvent | None) -> str:
    """`StructureEvent`dan Telegram-friendly yorliq: "BOS (BULLISH)"/"CHoCH (BEARISH)".

    Audit topilmasi: ilgari faqat `event.direction` (BULLISH/BEARISH) ko'rsatilar
    edi — `event.event_type` (BOS/CHoCH, aynan foydalanuvchi kutgan ma'lumot)
    yo'qolar edi. Event yo'q bo'lsa (masalan hali hech qanday struktura buzilishi
    ro'y bermagan) — "-"."""
    if event is None:
        return "-"
    type_label = _STRUCTURE_EVENT_TYPE_DISPLAY.get(event.event_type.name, event.event_type.name)
    return f"{type_label} ({event.direction.name})"


def _entry_zone(setup: TradeSetup, atr: pd.Series, *, mult: float) -> tuple[float, float]:
    """(entry - mult*ATR[entry], entry + mult*ATR[entry]).

    ATR entry barida NaN (warmup) bo'lsa — degenerativ (entry, entry) zonaga qaytadi,
    `payload_from_setup`ning o'z no-data fallback'i bilan bir xil konvensiya.
    """
    n = len(atr)
    a = atr.iloc[setup.entry_index_pos] if 0 <= setup.entry_index_pos < n else float("nan")
    if pd.isna(a):
        return (setup.entry_price, setup.entry_price)
    width = mult * float(a)
    return (setup.entry_price - width, setup.entry_price + width)


def recent_momentum_warning(
    df: pd.DataFrame, entry_low: float, *, bars: int = MOMENTUM_WARNING_BARS,
) -> bool:
    """Falling-knife ogohlantirishi: oxirgi (joriy) close entry zonasi ostida VA
    so'nggi `bars` ta bar ketma-ket pastroq yopilgan bo'lsa -- True.

    ATAYLAB `setup.entry_index_pos`ga emas, df'ning ENG SO'NGGI barlariga qaraydi
    (trend/structure/ATR/hajm konvensiyasidan farqli, ular determinizm uchun entry
    barida muzlatiladi) -- chunki bu ogohlantirishning butun maqsadi aynan shu: entry
    konteksti eski bo'lib, narx keyin ham tushishda davom etgan holatni ushlash.
    Lookahead yo'q -- faqat mavjud (o'tgan/joriy) barlar o'qiladi, df chegarasidan
    tashqariga hech qachon chiqilmaydi. FAQAT ogohlantirish (bool bayroq) -- filtr
    EMAS, score/setup'ga ta'sir qilmaydi.
    """
    if len(df) < bars + 1:
        return False
    closes = df["close"].iloc[-(bars + 1):]
    if closes.iloc[-1] >= entry_low:
        return False
    return bool((closes.diff().iloc[1:] < 0).all())


def scan_symbol(
    df: pd.DataFrame,
    symbol: str,
    *,
    mode: SignalMode = SignalMode.SWING,
    min_score: float | None = None,
    lookback: int = SWING_LOOKBACK,
    min_rr: float = MIN_BREAKOUT_RR,
    require_trend: bool = True,
    atr_period: int = ATR_PERIOD,
    volume_ma_period: int = VOLUME_MA_PERIOD,
    entry_zone_atr_mult: float = ENTRY_ZONE_ATR_MULT,
    interval: str = "1d",
    recency_bars: int | None = SIGNAL_RECENCY_BARS,
    momentum_warning_bars: int = MOMENTUM_WARNING_BARS,
) -> list[SignalPayload]:
    """Bitta symbol uchun: setup topish -> ball berish -> filtrlash -> to'liq kontekstli
    `SignalPayload`larga aylantirish. Tarmoq/IO yo'q — `df` allaqachon yuklangan.

    Lookahead yo'q: trend/structure/ATR/hajm seriyalari orqaga qarovchi (backward-looking)
    bo'lib, faqat `setup.entry_index_pos`da o'qiladi — kelajak barlarga hech qachon
    murojaat qilinmaydi (bu kafolat strategy/smc qatlamlarining o'zida allaqachon bor).

    `recency_bars`: entry bari oxirgi bardan shu sondan ko'p bar OLDIN bo'lgan
    setup'lar chiqarib tashlanadi (LIVE skaner faqat SO'NGGI setuplarni ko'rsatishi
    uchun — butun tarixdagi eski setup'lar emas, TZ). `None` — filtrsiz (masalan
    tadqiqot kontekstida to'liq ro'yxat kerak bo'lsa).
    """
    setups = generate_breakout_retest_signals(
        df, lookback=lookback, min_rr=min_rr, require_trend=require_trend,
    )
    setups = apply_scores(df, setups, lookback=lookback, min_rr=min_rr)
    setups = filter_by_score(setups, min_score)
    if recency_bars is not None:
        cutoff = len(df) - 1 - recency_bars
        setups = [s for s in setups if s.entry_index_pos >= cutoff]
    if not setups:
        return []

    regime = compute_trend_regime(df)
    swings = detect_swings(df, lookback=lookback)
    events = detect_structure_events(df, swings)
    atr = compute_atr(df, atr_period)
    data_freshness = df.index[-1].date()
    # "Observed price" — oxirgi mavjud (tasdiqlangan) bar close'i (data_freshness bilan
    # bir bar). Lookahead yo'q. payload_from_setup undan distance_to_zone + status
    # hisoblaydi (observation-only, scoring/target/R:R'ga tegmaydi).
    current_price = float(df["close"].iloc[-1])

    payloads: list[SignalPayload] = []
    for setup in setups:
        trend = trend_regime_at(regime, setup.entry_index_pos).name

        structure_event = _structure_event_at(events, setup.entry_index_pos)
        structure = _structure_display(structure_event)

        breakout_pos = (
            setup.breakout_index_pos if setup.breakout_index_pos is not None
            else setup.entry_index_pos
        )
        volume_confirmed = is_volume_confirmed(df, breakout_pos, period=volume_ma_period)

        entry_zone = _entry_zone(setup, atr, mult=entry_zone_atr_mult)
        momentum_warning = recent_momentum_warning(df, entry_zone[0], bars=momentum_warning_bars)

        setup_type = setup_type_from_reason(setup.reason)
        expectancy_r, win_rate_pct, period_label = HISTORICAL_STATS.get(
            setup_type, _DEFAULT_HISTORICAL_STAT,
        )

        payloads.append(payload_from_setup(
            setup,
            symbol=symbol,
            trend=trend,
            structure=structure,
            volume_confirmed=volume_confirmed,
            historical_expectancy_r=expectancy_r,
            historical_win_rate_pct=win_rate_pct,
            historical_period_label=period_label,
            data_freshness=data_freshness,
            timeframe=interval,
            mode=mode,
            entry_zone=entry_zone,
            current_price=current_price,
            momentum_warning=momentum_warning,
        ))
    return payloads


def scan_universe(
    symbols: list[str],
    provider: DataProvider,
    *,
    interval: str = "1d",
    mode: SignalMode = SignalMode.SWING,
    min_score: float | None = None,
    lookback: int = SWING_LOOKBACK,
    min_rr: float = MIN_BREAKOUT_RR,
    require_trend: bool = True,
    atr_period: int = ATR_PERIOD,
    volume_ma_period: int = VOLUME_MA_PERIOD,
    entry_zone_atr_mult: float = ENTRY_ZONE_ATR_MULT,
    recency_bars: int | None = SIGNAL_RECENCY_BARS,
    momentum_warning_bars: int = MOMENTUM_WARNING_BARS,
) -> tuple[dict[str, list[SignalPayload]], list[dict[str, str]]]:
    """Har symbol uchun ma'lumotni `provider` orqali oladi va `scan_symbol`ni chaqiradi.

    Provider xatosi, yetarsiz data (`len(df) < 2*lookback+1`) yoki skan xatosi — symbol
    SKIP qilinadi (log + sabab bilan qaytariladi), BUTUN skan TO'XTAMAYDI. Bitta symbolda
    setup topilmasligi (yetarli data bilan skan qilingan, shunchaki hech narsa yo'q) SKIP
    EMAS — bu normal holat, natijada ham, skip ro'yxatida ham ko'rinmaydi.

    Qaytaradi: (results, skipped) — `scripts/backtest_portfolio.py::load_universe`ning
    (data, error_rows) konvensiyasiga mos. `results` faqat >=1 payload topilgan symbol'larni
    o'z ichiga oladi, har birining ro'yxati score bo'yicha KAMAYISH tartibida saralangan.
    """
    results: dict[str, list[SignalPayload]] = {}
    skipped: list[dict[str, str]] = []

    for symbol in symbols:
        try:
            df = provider.get_ohlcv(symbol, interval)
        except Exception as exc:  # noqa: BLE001
            reason = f"provider xatosi: {exc}"
            logger.warning("SKIP %s: %s", symbol, reason)
            skipped.append({"symbol": symbol, "reason": reason})
            continue

        if df is None or df.empty or len(df) < 2 * lookback + 1:
            reason = "yetarsiz data"
            logger.warning("SKIP %s: %s", symbol, reason)
            skipped.append({"symbol": symbol, "reason": reason})
            continue

        try:
            payloads = scan_symbol(
                df, symbol, mode=mode, min_score=min_score, lookback=lookback, min_rr=min_rr,
                require_trend=require_trend, atr_period=atr_period,
                volume_ma_period=volume_ma_period, entry_zone_atr_mult=entry_zone_atr_mult,
                interval=interval, recency_bars=recency_bars,
                momentum_warning_bars=momentum_warning_bars,
            )
        except Exception as exc:  # noqa: BLE001
            reason = f"skan xatosi: {exc}"
            logger.warning("SKIP %s: %s", symbol, reason)
            skipped.append({"symbol": symbol, "reason": reason})
            continue

        if payloads:
            results[symbol] = sorted(payloads, key=lambda p: p.score, reverse=True)

    return results, skipped
