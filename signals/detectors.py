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
    "near_fvg": "near FVG",
}


def format_setup_alert_text(setup: Setup, bar_date: str) -> str:
    """Build the Telegram-visible alert body for a fired Setup.

    This is the single place that translates internal trigger/context keys
    (e.g. "liquidity_sweep") into reader-facing labels. The CSV journal
    (engine/scanner.py's _append_journal) deliberately keeps the raw keys —
    they're better for later filtering/grouping — so only the alert text
    goes through this mapping.
    """
    trigger_text = " + ".join(
        _TRIGGER_LABELS.get(t, t.replace("_", " ")) for t in setup.triggers
    )

    context_labels: list[str] = []
    for c in setup.context:
        if c == "near_round_number":
            nearest = round(setup.price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT
            context_labels.append(f"near ${nearest:,.0f}")
        else:
            context_labels.append(_CONTEXT_LABELS.get(c, c.replace("_", " ")))

    lines = [
        f"\U0001f50d <b>{setup.symbol}</b> — setup formed, go look",
        f"<b>Trigger:</b> {trigger_text}",
    ]
    if context_labels:
        lines.append(f"<b>Context:</b> {', '.join(context_labels)}")
    lines.append(f"<b>Price:</b> ${setup.price:,.2f}")
    lines.append(f"<b>Bar:</b> {bar_date}")
    lines.append("")
    lines.append("<i>Not a trade signal — open the chart and decide yourself.</i>")

    return "\n".join(lines)


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

    context: list[str] = []
    if is_uptrend:
        context.append("uptrend")
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
    )
