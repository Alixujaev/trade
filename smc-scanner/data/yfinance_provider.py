"""yfinance orqali OHLCV ma'lumot olib beruvchi konkret provayder.

Qo'llab-quvvatlanadigan intervallar:
- '1d', '1wk': Kunlik va haftalik uzoq muddatli barlar (~10 yil)
- '1h': 1 soatlik barlar (~730 kun)
- '5m', '15m': Intraday tezkor barlar (yfinance limiti: maksimal 60 kun)

Eslatma: '1m' qo'llab-quvvatlanmaydi (yfinance 1m ni faqat 7 kun beradi, bu yetarsiz).
'4h' yfinance tomonidan toza berilmaydi (AlpacaProvider ishlatiladi).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.settings import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    CACHE_TTL_INTRADAY_MINUTES,
    PERIOD_1H,
    PERIOD_DEFAULT,
    PERIOD_INTRADAY_FAST,
)
from data.bars import filter_closed_bars
from data.provider import DataProvider
from data.validation import validate_ohlcv

logger = logging.getLogger(__name__)

# Bar-sana tekshiruvi shu interval'larga qo'llanadi (kunlik — bir kunlik lag ham sezilarli)
_DATE_STALE_INTERVALS: set[str] = {"1d"}

# 5m va 15m tezkor intraday intervallar (qisqa kesh muddati qo'llanadi)
_INTRADAY_FAST_INTERVALS: set[str] = {"5m", "15m"}

# US savdo sessiyasi ~20:00 UTC (yozda) / 21:00 UTC (qishda) yopiladi.
_SESSION_CLOSE_HOUR_UTC = 21


def _latest_expected_session_date(now: datetime | None = None) -> date:
    """Oxirgi 'yopilgan bo'lishi kutiladigan' US savdo kuni (UTC bo'yicha)."""
    now = now or datetime.now(timezone.utc)
    d = now.date()
    if now.hour < _SESSION_CLOSE_HOUR_UTC:
        d -= timedelta(days=1)
    while d.weekday() >= 5:  # 5=shanba, 6=yakshanba
        d -= timedelta(days=1)
    return d


SUPPORTED_INTERVALS: set[str] = {"1d", "1wk", "1h", "5m", "15m"}


class YFinanceProvider(DataProvider):
    """yfinance kutubxonasiga asoslangan DataProvider implementatsiyasi."""

    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        *,
        use_cache: bool = True,
        include_extended_hours: bool = False,
        closed_only: bool = False,
        as_of: datetime | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"YFinanceProvider '{interval!r}'ni qo'llab-quvvatlamaydi. "
                f"Qo'llab-quvvatlanadiganlar: {sorted(SUPPORTED_INTERVALS)}"
            )

        cache_path = self._cache_path(
            symbol, interval, include_extended_hours=include_extended_hours
        )
        ignore_cache_expiry = kwargs.get("ignore_cache_expiry", False)
        if use_cache and cache_path.exists():
            cached = pd.read_parquet(cache_path)
            if ignore_cache_expiry or self._is_cache_fresh(cache_path, cached, interval):
                if closed_only:
                    return filter_closed_bars(cached, interval, as_of=as_of)
                return cached

        if interval in _INTRADAY_FAST_INTERVALS:
            period = PERIOD_INTRADAY_FAST
        elif interval == "1h":
            period = PERIOD_1H
        else:
            period = PERIOD_DEFAULT

        try:
            raw = yf.download(
                symbol,
                period=period,
                interval=interval,
                prepost=include_extended_hours,
                auto_adjust=True,
                progress=False,
            )
        except Exception as exc:
            if cache_path.exists():
                logger.warning(
                    "%s (%s) yuklab olishda xatolik yuz berdi: %s. Keshdagi fayldan foydalanilmoqda.",
                    symbol,
                    interval,
                    exc,
                )
                cached = pd.read_parquet(cache_path)
                if closed_only:
                    return filter_closed_bars(cached, interval, as_of=as_of)
                return cached
            raise

        if raw is None or raw.empty:
            if cache_path.exists():
                logger.warning(
                    "%s (%s) uchun bo'sh ma'lumot qaytdi, keshdagi fayldan foydalanilmoqda.",
                    symbol,
                    interval,
                )
                cached = pd.read_parquet(cache_path)
                if closed_only:
                    return filter_closed_bars(cached, interval, as_of=as_of)
                return cached
            raise ValueError(
                f"{symbol} ({interval}) uchun yfinance'dan bo'sh ma'lumot qaytdi"
            )

        clean = self._clean(raw, symbol=symbol)
        self._write_cache(clean, cache_path)

        if closed_only:
            return filter_closed_bars(clean, interval, as_of=as_of)
        return clean

    @staticmethod
    def _clean(df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
        """Xom yfinance DataFrame'ni standart OHLCV formatiga keltiradi va validatsiya qiladi."""
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        return validate_ohlcv(df, symbol=symbol)

    @staticmethod
    def _cache_path(
        symbol: str, interval: str, include_extended_hours: bool = False
    ) -> Path:
        suffix = "_ext" if include_extended_hours else ""
        return CACHE_DIR / f"{symbol}_{interval}{suffix}.parquet"

    @staticmethod
    def _is_cache_fresh(
        path: Path, df: pd.DataFrame | None = None, interval: str = "1d"
    ) -> bool:
        """Kesh yangiligini tekshiradi."""
        if not path.exists():
            return False

        # Kunlik bar sanasi bo'yicha tekshirish
        if interval in _DATE_STALE_INTERVALS:
            if df is None or not len(df):
                return False
            last_bar_date = pd.Timestamp(df.index[-1]).date()
            return last_bar_date >= _latest_expected_session_date()

        # 5m va 15m uchun daqiqa hisobidagi qisqa TTL
        if interval in _INTRADAY_FAST_INTERVALS:
            age_minutes = (time.time() - path.stat().st_mtime) / 60
            return age_minutes < CACHE_TTL_INTRADAY_MINUTES

        # Intraday 1h uchun soatlik TTL
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours < CACHE_TTL_HOURS

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as exc:
            logger.warning("Keshga yozib bo'lmadi: %s", exc)
