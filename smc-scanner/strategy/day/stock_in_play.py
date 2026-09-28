"""strategy/day/stock_in_play.py: DAY-06 — Stock-in-Play Context Hypothesis Data Models and Evaluation.

QAT'IY METODOLOGIK QOIDALAR:
- Bu modul faqat STOCK-IN-PLAY kontekstini point-in-time aniqlash uchun xizmat qiladi.
- Muzlatilgan DAY-01 VWAP Momentum strategiyasi logikasi, indikatorlari va qoidalariga
  HECH QANDAY o'zgartirish kiritilmaydi.
- Sessiya konteksti faqat 09:30 ET gacha bo'lgan ma'lumotlar (oldingi RTH close, bugungi RTH open,
  va 04:00-09:30 premarket hajmi) asosida hisoblanadi va sessiya davomida O'ZGARMAS (immutable) bo'ladi.
- Bozor ochilgandan keyingi (09:30+) narx yoki hajm harakati sessiya muvofiqligiga aslo ta'sir qilmaydi (no lookahead).
- Agar katalizator (news/catalyst) ma'lumoti bo'lmasa, uni soxtalashtirish taqiqlanadi (catalyst_available=False).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, time
import math
from typing import Any
import numpy as np
import pandas as pd

from data.session import (
    PREMARKET_START,
    RTH_START,
    filter_premarket,
    filter_rth,
    get_session_date,
    get_session_dates,
    to_eastern,
)

# Tadqiqot farazlari (Research Assumptions — optimallashtirilmagan):
DEFAULT_GAP_THRESHOLD_PCT: float = 0.02          # 2.0% mutlaq gap (abs(gap_pct) >= 0.02)
DEFAULT_GAP_THRESHOLDS_PCT: tuple[float, ...] = (0.01, 0.02, 0.03, 0.04)  # DAY-06A qat'iy chegaralar to'plami
DEFAULT_PREMARKET_RVOL_THRESHOLD: float = 2.0    # 2.0x premarket RVOL
MIN_PREMARKET_LOOKBACK_SESSIONS: int = 5         # RVOL hisoblash uchun minimal o'tmish sessiyalar
MAX_PREMARKET_LOOKBACK_SESSIONS: int = 20        # RVOL lookback oynasi


@dataclass(frozen=True)
class StockInPlayContext:
    """Bitta aksiyaning belgilangan savdo sessiyasi uchun o'zgarmas Stock-in-Play konteksti."""

    symbol: str
    session_date: date

    previous_close: float
    rth_open: float
    gap_pct: float

    premarket_volume: float
    premarket_rvol: float | None

    catalyst_available: bool = False
    catalyst_present: bool | None = None

    gap_eligible: bool = False
    premarket_rvol_eligible: bool = False

    gap_only_eligible: bool = False
    premarket_only_eligible: bool = False
    combined_eligible: bool = False

    is_positive_gap: bool = False
    is_negative_gap: bool = False

    gap_data_sufficient: bool = True

    def is_gap_eligible_at(self, threshold_pct: float) -> bool:
        """abs(gap_pct) >= threshold_pct tekshiruvi (point-in-time)."""
        if not self.gap_data_sufficient or math.isnan(self.gap_pct):
            return False
        t = threshold_pct / 100.0 if threshold_pct >= 0.50 else threshold_pct
        return abs(self.gap_pct) >= t

    def is_positive_gap_at(self, threshold_pct: float) -> bool:
        """gap_pct >= threshold_pct tekshiruvi."""
        if not self.gap_data_sufficient or math.isnan(self.gap_pct):
            return False
        t = threshold_pct / 100.0 if threshold_pct >= 0.50 else threshold_pct
        return self.gap_pct >= t

    def is_negative_gap_at(self, threshold_pct: float) -> bool:
        """gap_pct <= -threshold_pct tekshiruvi."""
        if not self.gap_data_sufficient or math.isnan(self.gap_pct):
            return False
        t = threshold_pct / 100.0 if threshold_pct >= 0.50 else threshold_pct
        return self.gap_pct <= -t

    def to_dict(self) -> dict[str, Any]:
        """JSON serializatsiya uchun dict."""
        d = asdict(self)
        d["session_date"] = str(self.session_date)
        for k, v in d.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d


def compute_stock_in_play_contexts(
    symbol: str,
    df_5m: pd.DataFrame,
    df_extended_5m: pd.DataFrame | None = None,
    *,
    gap_threshold_pct: float = DEFAULT_GAP_THRESHOLD_PCT,
    premarket_rvol_threshold: float = DEFAULT_PREMARKET_RVOL_THRESHOLD,
    min_premarket_sessions: int = MIN_PREMARKET_LOOKBACK_SESSIONS,
    max_premarket_sessions: int = MAX_PREMARKET_LOOKBACK_SESSIONS,
) -> dict[date, StockInPlayContext]:
    """Belgilangan symbol uchun har bir savdo sessiyasining Stock-in-Play kontekstini hisoblaydi.

    POINT-IN-TIME QOIDASI:
    - Gap: bugungi birinchi RTH bar (09:30 ET) open narxi va oldingi RTH kunining
      oxirgi bar (16:00 ET) close narxi asosida o'lchanadi.
    - Premarket: faqat 04:00 <= t < 09:30 ET oralig'idagi barlar asosida hisoblanadi.
    - Sessiya boshlangandan keyingi (09:30+) barlar kontekstga aslo ta'sir qilmaydi.
    """
    if df_5m.empty:
        return {}

    # 1. RTH barlarini ajratish va sessiya sanalari bo'yicha guruhlash
    df_rth = filter_rth(df_5m)
    if df_rth.empty:
        return {}

    rth_session_dates = get_session_dates(df_rth.index)
    sorted_unique_dates: list[date] = sorted(rth_session_dates.unique())

    # Har bir sessiya uchun birinchi RTH open va oxirgi RTH close'ni aniqlash
    daily_rth_prices: dict[date, tuple[float, float]] = {}
    for d in sorted_unique_dates:
        mask = rth_session_dates == d
        session_slice = df_rth.loc[mask]
        if not session_slice.empty:
            open_p = float(session_slice["open"].iloc[0])
            close_p = float(session_slice["close"].iloc[-1])
            daily_rth_prices[d] = (open_p, close_p)

    # 2. Premarket hajm ma'lumotlarini hisoblash (agar mavjud bo'lsa)
    pm_volume_by_date: dict[date, float] = {}
    if df_extended_5m is not None and not df_extended_5m.empty:
        df_pm = filter_premarket(df_extended_5m)
        if not df_pm.empty:
            pm_dates = get_session_dates(df_pm.index)
            grouped = df_pm.groupby(pm_dates)["volume"].sum()
            for d, v in grouped.items():
                pm_volume_by_date[d] = float(v)

    # 3. Har bir sessiya uchun StockInPlayContext qurish
    contexts: dict[date, StockInPlayContext] = {}

    for i, curr_date in enumerate(sorted_unique_dates):
        curr_open, _ = daily_rth_prices[curr_date]

        # Oldingi RTH sessiyasi close narxi
        if i == 0:
            # Eng birinchi sessiya uchun oldingi close ma'lum emas
            prev_close = float("nan")
            gap_pct = float("nan")
            gap_eligible = False
            is_pos_gap = False
            is_neg_gap = False
            gap_data_sufficient = False
        else:
            prev_date = sorted_unique_dates[i - 1]
            _, prev_close = daily_rth_prices[prev_date]
            if not math.isnan(prev_close) and not math.isnan(curr_open) and prev_close > 0:
                gap_pct = (curr_open - prev_close) / prev_close
                gap_eligible = abs(gap_pct) >= gap_threshold_pct
                is_pos_gap = gap_pct > 0.0
                is_neg_gap = gap_pct < 0.0
                gap_data_sufficient = True
            else:
                gap_pct = float("nan")
                gap_eligible = False
                is_pos_gap = False
                is_neg_gap = False
                gap_data_sufficient = False

        # Premarket hajm va Premarket RVOL hisobi
        curr_pm_vol = pm_volume_by_date.get(curr_date, 0.0)

        # O'tmishdagi sessiyalarning premarket hajmlarini olish (lookback)
        past_dates = [d for d in sorted_unique_dates[:i] if d in pm_volume_by_date]
        relevant_past_dates = past_dates[-max_premarket_sessions:]
        past_vols = [pm_volume_by_date[d] for d in relevant_past_dates]

        # Faqat noldan katta hajmli premarket mavjud bo'lsa
        valid_past_vols = [v for v in past_vols if v > 0.0]

        if len(valid_past_vols) >= min_premarket_sessions:
            baseline_pm_vol = float(np.mean(valid_past_vols))
            if baseline_pm_vol > 0.0 and curr_pm_vol > 0.0:
                pm_rvol = curr_pm_vol / baseline_pm_vol
                pm_rvol_eligible = pm_rvol >= premarket_rvol_threshold
            else:
                pm_rvol = None
                pm_rvol_eligible = False
        else:
            # Ma'lumot yetarli emas yoki providerda premarket hajm 0
            pm_rvol = None
            pm_rvol_eligible = False

        # H1 Variantlari muvofiqligi
        gap_only_eligible = gap_eligible
        premarket_only_eligible = pm_rvol_eligible
        combined_eligible = gap_eligible and pm_rvol_eligible

        contexts[curr_date] = StockInPlayContext(
            symbol=symbol,
            session_date=curr_date,
            previous_close=prev_close,
            rth_open=curr_open,
            gap_pct=gap_pct,
            premarket_volume=curr_pm_vol,
            premarket_rvol=pm_rvol,
            catalyst_available=False,
            catalyst_present=None,
            gap_eligible=gap_eligible,
            premarket_rvol_eligible=pm_rvol_eligible,
            gap_only_eligible=gap_only_eligible,
            premarket_only_eligible=premarket_only_eligible,
            combined_eligible=combined_eligible,
            is_positive_gap=is_pos_gap,
            is_negative_gap=is_neg_gap,
            gap_data_sufficient=gap_data_sufficient,
        )

    return contexts
