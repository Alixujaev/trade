"""strategy/day/orb.py: Opening Range Breakout (ORB) signal - long-only, point-in-time.

Qoidalar (owner-approved):
- Opening range (OR) = 09:30, 09:35, 09:40 ET da ochilgan uchta 5m barning high/low'i (09:45 da yopiladi).
- Signal: 09:45 <= bar open < 11:00 ET oralig'ida OR high ustida YOPILGAN birinchi 5m bar, agar shu barda
  close > VWAP va hajm tasdig'i (indicators/volume.is_volume_confirmed bilan aynan bir xil qoida) bo'lsa.
- Kirish signal baridan keyingi barning open'ida (bu modul faqat signalni beradi; ijro strategy/day/orb_rules.py).

Lookahead yo'q: signal bar i uchun faqat i gacha (i kiradi) bo'lgan barlar o'qiladi. VWAP sessiya bo'yicha
kumulyativ, volume MA orqaga qaragan rolling - ikkalasi ham kelajak barga bog'liq emas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

from config.settings import VOLUME_BREAKOUT_RATIO, VOLUME_MA_PERIOD
from data.session import get_session_dates, is_rth_series, to_eastern
from indicators.volume import volume_ratio
from indicators.vwap import compute_vwap

OR_BAR_OPENS: tuple[time, ...] = (time(9, 30), time(9, 35), time(9, 40))
ENTRY_WINDOW_START = time(9, 45)                   # birinchi mumkin bo'lgan signal bari (09:45-09:50)
ENTRY_WINDOW_END = time(11, 0)                     # signal bari open'i < 11:00 (oxirgisi 10:55-11:00)


@dataclass(frozen=True)
class OrbFeatures:
    """Butun df uchun oldindan hisoblangan, point-in-time ko'rsatkichlar."""

    vwap: pd.Series                                # sessiya VWAP (RTH), compute_vwap
    volume_ok: pd.Series                           # is_volume_confirmed bilan bir xil qoida (bool)


@dataclass(frozen=True)
class OrbSignal:
    symbol: str
    session: date
    signal_time: pd.Timestamp                      # signal barining open vaqti (UTC)
    entry_time: pd.Timestamp                       # keyingi bar open vaqti (UTC) - kirish shu bar open'ida
    or_high: float
    or_low: float
    signal_close: float
    signal_vwap: float


def session_bars(df: pd.DataFrame, session: date) -> pd.DataFrame:
    """`session` kunining RTH barlari (vaqt tartibida)."""
    if df.empty:
        return df
    mask = (get_session_dates(df.index) == session) & is_rth_series(df.index)
    return df.loc[mask.to_numpy()]


def opening_range(sdf: pd.DataFrame) -> tuple[float, float] | None:
    """OR (high, low). 09:30/09:35/09:40 barlaridan biri yo'q bo'lsa None (yetarli data yo'q = signal yo'q)."""
    if sdf.empty:
        return None
    et = to_eastern(sdf.index)
    sel = [i for i, t in enumerate(et.time) if t in OR_BAR_OPENS]
    if len(sel) != len(OR_BAR_OPENS):
        return None
    rows = sdf.iloc[sel]
    return float(rows["high"].max()), float(rows["low"].min())


def precompute(df: pd.DataFrame, *, period: int = VOLUME_MA_PERIOD,
               threshold: float = VOLUME_BREAKOUT_RATIO) -> OrbFeatures:
    """VWAP va hajm tasdig'i. Hajm qoidasi indicators/volume.is_volume_confirmed bilan aynan bir xil:
    ratio = volume / rolling_mean(volume, period); NaN yoki inf -> tasdiqlanmagan; aks holda ratio >= threshold."""
    ratio = volume_ratio(df, period=period)
    ok = ratio.notna() & ~np.isinf(ratio) & (ratio >= threshold)
    return OrbFeatures(vwap=compute_vwap(df, rth_only=True), volume_ok=ok.astype(bool))


def find_signal(symbol: str, df: pd.DataFrame, feats: OrbFeatures, session: date) -> OrbSignal | None:
    """`session` kunining birinchi ORB signali yoki None.

    Barlar vaqt tartibida tekshiriladi; birinchi shartlarni to'liq qanoatlantirgan bar signal bo'ladi.
    Kirish bari = shu sessiyadagi signal baridan keyingi bar; u yo'q bo'lsa (sessiya tugagan) signal yo'q.
    """
    sdf = session_bars(df, session)
    rng = opening_range(sdf)
    if rng is None:
        return None
    or_high, or_low = rng
    et_times = to_eastern(sdf.index).time
    for k in range(len(sdf)):
        t = et_times[k]
        if t < ENTRY_WINDOW_START:
            continue
        if t >= ENTRY_WINDOW_END:
            break
        ts = sdf.index[k]
        close = float(sdf["close"].iloc[k])
        vwap = feats.vwap.get(ts, np.nan)
        if not (close > or_high):
            continue
        if not (np.isfinite(vwap) and close > vwap):
            continue
        if not bool(feats.volume_ok.get(ts, False)):
            continue
        if k + 1 >= len(sdf):
            return None
        return OrbSignal(symbol=symbol, session=session, signal_time=ts, entry_time=sdf.index[k + 1],
                         or_high=or_high, or_low=or_low, signal_close=close, signal_vwap=float(vwap))
    return None
