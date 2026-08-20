from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.config import AppConfig, IndicatorConfig
from indicators.indicators import atr, ema


def bullish_sweep(df: pd.DataFrame, lookback: int = 20, reclaim_frac: float = 0.5) -> bool:
    if len(df) < lookback + 1:
        return False

    prior = df.iloc[-(lookback + 1):-1]
    last = df.iloc[-1]
    prior_low = float(prior["low"].min())
    last_low = float(last["low"])
    last_high = float(last["high"])
    last_close = float(last["close"])

    if not (last_low < prior_low):
        return False
    if not (last_close > prior_low):
        return False

    bar_range = last_high - last_low
    if bar_range <= 0:
        return False

    recovery = (last_close - last_low) / bar_range
    return bool(recovery >= reclaim_frac)


def bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False

    prior = df.iloc[-2]
    last = df.iloc[-1]

    prior_bearish = prior["close"] < prior["open"]
    last_bullish = last["close"] > last["open"]
    if not (prior_bearish and last_bullish):
        return False

    prior_body_low = min(prior["open"], prior["close"])
    prior_body_high = max(prior["open"], prior["close"])
    last_body_low = min(last["open"], last["close"])
    last_body_high = max(last["open"], last["close"])

    engulfs = last_body_low <= prior_body_low and last_body_high >= prior_body_high
    return bool(engulfs)


def bullish_pin(df: pd.DataFrame, wick_frac: float = 0.6) -> bool:
    if len(df) < 1:
        return False

    last = df.iloc[-1]
    bar_range = float(last["high"] - last["low"])
    if bar_range <= 0:
        return False

    body = abs(float(last["close"] - last["open"]))
    lower_wick = float(min(last["open"], last["close"]) - last["low"])

    wick_ok = (lower_wick / bar_range) >= wick_frac
    body_ok = (body / bar_range) <= 0.3
    return bool(wick_ok and body_ok)


def uptrend(df: pd.DataFrame, cfg: IndicatorConfig) -> bool:
    fast = ema(df["close"], cfg.ema_fast)
    slow = ema(df["close"], cfg.ema_slow)
    if pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]):
        return False
    return bool(fast.iloc[-1] > slow.iloc[-1])


def near_fvg(df: pd.DataFrame, atr_frac: float = 0.3, lookback: int = 10) -> bool:
    if len(df) < 3:
        return False

    atr_series = atr(df, period=14)
    current_price = float(df["close"].iloc[-1])
    start = max(2, len(df) - lookback)

    for i in range(start, len(df)):
        gap_low = float(df["high"].iloc[i - 2])
        gap_high = float(df["low"].iloc[i])
        gap_size = gap_high - gap_low
        if gap_size <= 0:
            continue

        atr_i = atr_series.iloc[i]
        if pd.isna(atr_i) or gap_size <= atr_frac * atr_i:
            continue

        if gap_low <= current_price <= gap_high:
            return True

    return False


def range_position(df: pd.DataFrame, lookback: int = 20) -> float:
    """Where the last close sits within [min(low), max(high)] over the last
    `lookback` completed bars. 0.0 = bottom of the range (deep discount),
    1.0 = top of the range (deep premium).
    """
    window = df.iloc[-lookback:]
    range_low = float(window["low"].min())
    range_high = float(window["high"].max())
    last_close = float(df["close"].iloc[-1])

    span = range_high - range_low
    if span <= 0:
        return 0.5

    return (last_close - range_low) / span


def in_discount_zone(df: pd.DataFrame, lookback: int = 20) -> bool:
    return range_position(df, lookback=lookback) <= 0.5


_ROUND_NUMBER_UNIT = 5.0


def near_round_number(df: pd.DataFrame, tol_frac: float = 0.01) -> bool:
    if len(df) < 1:
        return False

    price = float(df["close"].iloc[-1])
    nearest = round(price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT
    # Cap the tolerance relative to the fixed unit spacing rather than letting
    # it scale unboundedly with price: tol_frac * price alone would make this
    # predicate trivially True for every bar once price >= UNIT / (2 * tol_frac)
    # (e.g. $250 at the default tol_frac=0.01), silently corrupting the
    # journal's confluence/context data for higher-priced symbols.
    tol = min(tol_frac * price, _ROUND_NUMBER_UNIT * 0.1)
    return bool(abs(price - nearest) <= tol)


@dataclass
class Setup:
    symbol: str
    triggers: list[str]
    context: list[str]
    price: float
    confluence: int
    # Where price sits in its recent range (0.0=range low, 1.0=range high).
    # Carried through to the journal so premium-vs-discount entry quality can
    # be analysed later; see scan_symbol's discount-zone gate below.
    range_pos: float = 0.5

    @property
    def is_actionable(self) -> bool:
        return len(self.triggers) > 0


_TRIGGER_LABELS: dict[str, str] = {
    "liquidity_sweep": "liquidity sweep",
    "bullish_engulfing": "bullish engulfing",
    "bullish_pin": "bullish pin",
}

_CONTEXT_LABELS: dict[str, str] = {
    "uptrend": "uptrend",
    "near_fvg": "FVG yaqinida",
    "discount": "discount zone",
}

_CHART_URL = "https://www.tradingview.com/chart/?symbol={symbol}"


def format_setup_alert_text(setup: Setup, bar_date: str) -> str:
    """Build the Telegram-visible alert body for a fired Setup.

    This is the single place that translates internal trigger/context keys
    (e.g. "liquidity_sweep") into reader-facing labels. Scaffold words are in
    Uzbek (matching the rest of the bot's user-facing text); trigger/context
    jargon (liquidity sweep, FVG, engulfing, ...) stays in English as that's
    the terms traders already use.
    """
    trigger_text = " + ".join(
        _TRIGGER_LABELS.get(t, t.replace("_", " ")) for t in setup.triggers
    )

    context_labels: list[str] = []
    for c in setup.context:
        if c == "near_round_number":
            nearest = round(setup.price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT
            context_labels.append(f"${nearest:,.0f} atrofida")
        else:
            context_labels.append(_CONTEXT_LABELS.get(c, c.replace("_", " ")))

    lines = [
        f"\U0001f50d <b>{setup.symbol}</b> — setup shakllandi, ko'rib chiq",
        f"<b>Belgi:</b> {trigger_text}",
    ]
    if context_labels:
        lines.append(f"<b>Kontekst:</b> {', '.join(context_labels)}")
    lines.append(f"<b>Narx:</b> ${setup.price:,.2f}")
    lines.append(f"<b>Sana:</b> {bar_date}")
    lines.append(f"<b>Kuchi:</b> {setup.confluence} ta belgi")
    lines.append("")
    lines.append("<i>Savdo signali emas — chartni oching va o'zingiz qaror qiling.</i>")

    return "\n".join(lines)


_JOURNAL_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/174WmNxdCmv_9DDGCRIIy952MCwxSyF5sEA0BbIOpVCE"
    "/edit?pli=1&gid=2119535500#gid=2119535500"
)


def build_setup_keyboard(symbol: str) -> dict:
    """Inline keyboard attached to a scanner alert: a chart link plus a link
    to the user's own Google Sheet journal, where they log their decision
    and outcome by hand -- nothing is written or tracked locally.
    """
    chart_url = _CHART_URL.format(symbol=symbol)
    return {
        "inline_keyboard": [
            [{"text": "\U0001f4c8 Chart", "url": chart_url}],
            [{"text": "\U0001f4dd Journalga yozish", "url": _JOURNAL_SHEET_URL}],
        ]
    }


def scan_symbol(
    df: pd.DataFrame, symbol: str, cfg: AppConfig, require_uptrend: bool = True
) -> Setup | None:
    if df.empty:
        return None

    scanner_cfg = cfg.scanner
    triggers: list[str] = []
    if bullish_sweep(
        df, lookback=scanner_cfg.sweep_lookback, reclaim_frac=scanner_cfg.sweep_reclaim_frac
    ):
        triggers.append("liquidity_sweep")
    if bullish_engulfing(df):
        triggers.append("bullish_engulfing")
    if bullish_pin(df, wick_frac=scanner_cfg.pin_wick_frac):
        triggers.append("bullish_pin")

    if not triggers:
        return None

    is_uptrend = uptrend(df, cfg.indicators)
    if require_uptrend and not is_uptrend:
        return None

    # Premium/discount gate: manual journaling of real alerts found 5/5 fired
    # while price was in the PREMIUM zone (top of its recent range) -- a poor
    # place to seek a long per the premium/discount concept. This is a GATE
    # only (can block, never fires on its own) -- see require_discount.
    pos = range_position(df, lookback=scanner_cfg.sweep_lookback)
    is_discount = pos <= 0.5
    if scanner_cfg.require_discount and not is_discount:
        return None

    context: list[str] = []
    if is_uptrend:
        context.append("uptrend")
    if is_discount:
        context.append("discount")
    if near_fvg(df, atr_frac=scanner_cfg.fvg_atr_frac, lookback=scanner_cfg.fvg_lookback):
        context.append("near_fvg")
    if near_round_number(df, tol_frac=scanner_cfg.round_number_tol_frac):
        context.append("near_round_number")

    price = float(df["close"].iloc[-1])
    return Setup(
        symbol=symbol,
        triggers=triggers,
        context=context,
        price=price,
        confluence=len(triggers) + len(context),
        range_pos=pos,
    )
