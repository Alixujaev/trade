"""strategy/day/index_regime.py: DAY-08 — H6 Index Regime Confluence Context Module.

QAT'IY METODOLOGIK QOIDALAR:
- H6 bu KONTEKST FILTRI / ANNOTATSIYA tadqiqot tajribasi (research experiment).
- DAY-01 signallari logikasi, indikatorlari, 5m triggeri, 15m strukturasi, stop (SIGNAL_LOW),
  target (2R) va execution qoidalariga HECH QANDAY o'zgartirish kiritilmaydi.
- Stock signali vaqti T da SPY va QQQ ning faqat to'liq yopilgan (closed) barlari olinadi:
  bar_end_time <= T.
- Shakllanayotgan (forming) 5m yoki 15m shamlar QAT'IYAN ishlatilmaydi (no lookahead).
- Agar indeks ma'lumoti yetarli bo'lmasa, uni bullish ham, bearish ham deb hisoblash taqiqlanadi:
  UNKNOWN / DATA_INSUFFICIENT deb belgilanadi.
- Hech qanday threshold optimizatsiyasi yoki graded score yaratilmaydi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
from typing import Any

import numpy as np
import pandas as pd

from data.bars import filter_closed_bars
from data.factory import get_provider
from data.provider import DataProvider
from smc.types import StructureState
from strategy.day.vwap_momentum import precompute_day_features


class IndexVwapRelation(str, Enum):
    """Indeks narxining 5m VWAP'ga nisbatan point-in-time holati."""

    ABOVE_VWAP = "ABOVE_VWAP"
    BELOW_VWAP = "BELOW_VWAP"
    UNKNOWN = "UNKNOWN"


class IndexStructureContext(str, Enum):
    """Indeks 15m tasdiqlangan SMC strukturasi holati."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IndexRegimeContext:
    """Stock signali vaqti T dagi o'zgarmas indeks rejimi konteksti."""

    timestamp: pd.Timestamp

    spy_5m_relation: str
    spy_15m_structure: str
    spy_vwap_relation: str

    qqq_5m_relation: str
    qqq_15m_structure: str
    qqq_vwap_relation: str

    spy_bullish: bool | None
    qqq_bullish: bool | None

    aligned_bullish: bool
    mixed: bool
    aligned_bearish: bool

    data_sufficient: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert context to serializable dictionary."""
        d = asdict(self)
        d["timestamp"] = str(self.timestamp)
        return d


class IndexRegimeDetector:
    """Point-in-time xavfsiz indeks rejimi detektori (SPY va QQQ).

    Precompute qilingan sababiy xususiyatlardan foydalanadi (O(1) / O(log N) lookup).
    """

    def __init__(
        self,
        spy_5m: pd.DataFrame,
        spy_15m: pd.DataFrame,
        qqq_5m: pd.DataFrame,
        qqq_15m: pd.DataFrame,
    ) -> None:
        self.spy_5m = spy_5m
        self.spy_15m = spy_15m
        self.qqq_5m = qqq_5m
        self.qqq_15m = qqq_15m

        # Precompute SPY features
        if not spy_5m.empty:
            self.feat_spy = precompute_day_features(spy_5m, df_15m=spy_15m)
            self.end_5m_spy = spy_5m.index + pd.Timedelta(minutes=5)
            self.end_15m_spy = (
                spy_15m.index + pd.Timedelta(minutes=15)
                if not spy_15m.empty
                else pd.DatetimeIndex([])
            )
        else:
            self.feat_spy = None
            self.end_5m_spy = pd.DatetimeIndex([])
            self.end_15m_spy = pd.DatetimeIndex([])

        # Precompute QQQ features
        if not qqq_5m.empty:
            self.feat_qqq = precompute_day_features(qqq_5m, df_15m=qqq_15m)
            self.end_5m_qqq = qqq_5m.index + pd.Timedelta(minutes=5)
            self.end_15m_qqq = (
                qqq_15m.index + pd.Timedelta(minutes=15)
                if not qqq_15m.empty
                else pd.DatetimeIndex([])
            )
        else:
            self.feat_qqq = None
            self.end_5m_qqq = pd.DatetimeIndex([])
            self.end_15m_qqq = pd.DatetimeIndex([])

    def _normalize_timestamp(self, ts: pd.Timestamp) -> pd.Timestamp:
        """Indeks DatetimeIndex vaqt mintaqasiga moslashtirish."""
        if len(self.end_5m_spy) > 0:
            target_tz = self.end_5m_spy.tz
            if target_tz is not None:
                if ts.tz is None:
                    return ts.tz_localize("UTC").tz_convert(target_tz)
                return ts.tz_convert(target_tz)
            else:
                if ts.tz is not None:
                    return ts.tz_localize(None)
        return ts

    def _evaluate_single_index(
        self,
        df_5m: pd.DataFrame,
        end_5m: pd.DatetimeIndex,
        end_15m: pd.DatetimeIndex,
        feat: Any,
        as_of: pd.Timestamp,
    ) -> tuple[str, str, bool | None]:
        """Bitta indeks (SPY yoki QQQ) uchun 5m VWAP va 15m strukturani baholaydi.

        Returns
        -------
        tuple[str, str, bool | None]
            (vwap_relation, structure_15m, is_bullish)
        """
        if df_5m.empty or feat is None or len(end_5m) == 0:
            return (
                IndexVwapRelation.UNKNOWN.value,
                IndexStructureContext.UNKNOWN.value,
                None,
            )

        # 1. Latest CLOSED 5m bar where bar_end_time <= as_of
        k5 = end_5m.searchsorted(as_of, side="right") - 1
        if k5 < 0:
            return (
                IndexVwapRelation.UNKNOWN.value,
                IndexStructureContext.UNKNOWN.value,
                None,
            )

        c = float(df_5m["close"].iloc[k5])
        v = float(feat.vwap.iloc[k5])
        if math.isnan(c) or math.isnan(v) or v <= 0.0:
            vwap_rel = IndexVwapRelation.UNKNOWN.value
        elif c > v:
            vwap_rel = IndexVwapRelation.ABOVE_VWAP.value
        else:
            vwap_rel = IndexVwapRelation.BELOW_VWAP.value

        # 2. Latest CLOSED 15m bar where bar_end_time <= as_of
        if len(end_15m) == 0:
            return vwap_rel, IndexStructureContext.UNKNOWN.value, None

        k15 = end_15m.searchsorted(as_of, side="right") - 1
        # Need at least 5 bars (lookback=2 swings requirement) for causal structure
        if k15 < 4:
            return vwap_rel, IndexStructureContext.UNKNOWN.value, None

        st = feat.pre_states_15m[k15]
        if st is StructureState.BULLISH:
            st_str = IndexStructureContext.BULLISH.value
        elif st is StructureState.BEARISH:
            st_str = IndexStructureContext.BEARISH.value
        else:
            st_str = IndexStructureContext.NEUTRAL.value

        # Bullish index context: 5m close > 5m VWAP AND 15m structure is bullish
        if vwap_rel == IndexVwapRelation.UNKNOWN.value:
            is_bullish = None
        else:
            is_bullish = (
                vwap_rel == IndexVwapRelation.ABOVE_VWAP.value
                and st_str == IndexStructureContext.BULLISH.value
            )

        return vwap_rel, st_str, is_bullish

    def get_context_at(self, timestamp: pd.Timestamp) -> IndexRegimeContext:
        """Berilgan vaqt nuqtasi T dagi SPY va QQQ indeks rejimi kontekstini qaytaradi.

        Point-in-time safe:
        Faqat bar_end_time <= T bo'lgan yopilgan shamlar ishlatiladi.
        Forming shamlar qat'iyan chiqarib tashlanadi.
        """
        as_of = self._normalize_timestamp(timestamp)

        spy_rel, spy_st, spy_bull = self._evaluate_single_index(
            self.spy_5m, self.end_5m_spy, self.end_15m_spy, self.feat_spy, as_of
        )
        qqq_rel, qqq_st, qqq_bull = self._evaluate_single_index(
            self.qqq_5m, self.end_5m_qqq, self.end_15m_qqq, self.feat_qqq, as_of
        )

        # Missing-data handling:
        # If either index is UNKNOWN or insufficient, data_sufficient = False
        spy_sufficient = spy_bull is not None
        qqq_sufficient = qqq_bull is not None
        data_sufficient = spy_sufficient and qqq_sufficient

        if not data_sufficient:
            return IndexRegimeContext(
                timestamp=timestamp,
                spy_5m_relation=spy_rel,
                spy_15m_structure=spy_st,
                spy_vwap_relation=spy_rel,
                qqq_5m_relation=qqq_rel,
                qqq_15m_structure=qqq_st,
                qqq_vwap_relation=qqq_rel,
                spy_bullish=spy_bull,
                qqq_bullish=qqq_bull,
                aligned_bullish=False,
                mixed=False,
                aligned_bearish=False,
                data_sufficient=False,
            )

        aligned_bullish = bool(spy_bull and qqq_bull)

        spy_bear = (
            spy_rel == IndexVwapRelation.BELOW_VWAP.value
            and spy_st == IndexStructureContext.BEARISH.value
        )
        qqq_bear = (
            qqq_rel == IndexVwapRelation.BELOW_VWAP.value
            and qqq_st == IndexStructureContext.BEARISH.value
        )
        aligned_bearish = bool(spy_bear and qqq_bear)

        mixed = not (aligned_bullish or aligned_bearish)

        return IndexRegimeContext(
            timestamp=timestamp,
            spy_5m_relation=spy_rel,
            spy_15m_structure=spy_st,
            spy_vwap_relation=spy_rel,
            qqq_5m_relation=qqq_rel,
            qqq_15m_structure=qqq_st,
            qqq_vwap_relation=qqq_rel,
            spy_bullish=spy_bull,
            qqq_bullish=qqq_bull,
            aligned_bullish=aligned_bullish,
            mixed=mixed,
            aligned_bearish=aligned_bearish,
            data_sufficient=True,
        )


def build_index_regime_detector(
    provider: DataProvider | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> IndexRegimeDetector:
    """Mavjud intraday provayderdan SPY va QQQ ma'lumotlarini yuklab detektorni quradi."""
    prov = provider or get_provider()

    spy_5m = prov.get_ohlcv(
        "SPY",
        "5m",
        include_extended_hours=False,
        closed_only=False,
        ignore_cache_expiry=True,
    )
    spy_15m = prov.get_ohlcv(
        "SPY",
        "15m",
        include_extended_hours=False,
        closed_only=False,
        ignore_cache_expiry=True,
    )

    qqq_5m = prov.get_ohlcv(
        "QQQ",
        "5m",
        include_extended_hours=False,
        closed_only=False,
        ignore_cache_expiry=True,
    )
    qqq_15m = prov.get_ohlcv(
        "QQQ",
        "15m",
        include_extended_hours=False,
        closed_only=False,
        ignore_cache_expiry=True,
    )

    return IndexRegimeDetector(
        spy_5m=spy_5m,
        spy_15m=spy_15m,
        qqq_5m=qqq_5m,
        qqq_15m=qqq_15m,
    )
