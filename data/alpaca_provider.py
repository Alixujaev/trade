"""Alpaca Market Data API orqali OHLCV ma'lumot olib beruvchi konkret provayder.

Qo'llab-quvvatlanadigan intervallar:
- '1d', '1wk': Kunlik va haftalik barlar (~10 yil)
- '1h', '4h': Soatlik va 4-soatlik swing barlar (60 kun)
- '5m', '15m': 5 daqiqalik va 15 daqiqalik intraday barlar (60 kun)

MUHIM CHEKLOV (Alpaca Free Tier):
- FREE tier (DataFeed.IEX) ishlatiladi: bu faqat bitta birja (IEX) savdolarini
  qamrab oladi (umumiy AQSH birjalari hajmining ~2-3% qismi).
- Bepul IEX feed'i consolidated tape (SIP) hajmini bermaydi — shuning uchun Day Trading
  uchun RVOL va hajm tasdig'i bu provayderda to'liq ishonchli bo'lmasligi mumkin.
- Bepul tierda oxirgi 15 daqiqalik barlar kechikish bilan yetib kelishi mumkin.
- Kredensiallar .env fayldan (ALPACA_API_KEY, ALPACA_SECRET_KEY) o'qiladi.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

from config.settings import (
    ALPACA_LOOKBACK_DAYS_DEFAULT,
    ALPACA_LOOKBACK_DAYS_INTRADAY,
    CACHE_DIR,
    CACHE_TTL_HOURS,
    CACHE_TTL_INTRADAY_MINUTES,
)
from data.bars import filter_closed_bars
from data.provider import DataProvider
from data.session import filter_rth
from data.validation import validate_ohlcv

logger = logging.getLogger(__name__)

# Standart interval string -> Alpaca TimeFrame mapping.
_INTERVAL_TO_TIMEFRAME: dict[str, TimeFrame] = {
    "1d": TimeFrame.Day,
    "4h": TimeFrame(4, TimeFrameUnit.Hour),
    "1h": TimeFrame.Hour,
    "1wk": TimeFrame.Week,
    "5m": TimeFrame(5, TimeFrameUnit.Minute),
    "15m": TimeFrame(15, TimeFrameUnit.Minute),
}

SUPPORTED_INTERVALS: set[str] = set(_INTERVAL_TO_TIMEFRAME)
_INTRADAY_INTERVALS: set[str] = {"1h", "4h", "5m", "15m"}
_INTRADAY_FAST_INTERVALS: set[str] = {"5m", "15m"}


class AlpacaProvider(DataProvider):
    """Alpaca Market Data API (IEX feed, free tier) asosidagi DataProvider implementatsiyasi."""

    def __init__(self) -> None:
        load_dotenv()
        self._client: StockHistoricalDataClient | None = None

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
                f"AlpacaProvider '{interval!r}'ni qo'llab-quvvatlamaydi. "
                f"Qo'llab-quvvatlanadiganlar: {sorted(SUPPORTED_INTERVALS)}"
            )

        cache_path = self._cache_path(
            symbol, interval, include_extended_hours=include_extended_hours
        )
        if use_cache and self._is_cache_fresh(cache_path, interval):
            cached = pd.read_parquet(cache_path)
            if closed_only:
                return filter_closed_bars(cached, interval, as_of=as_of)
            return cached

        lookback_days = (
            ALPACA_LOOKBACK_DAYS_INTRADAY
            if interval in _INTRADAY_INTERVALS
            else ALPACA_LOOKBACK_DAYS_DEFAULT
        )
        raw = self._fetch_raw(symbol, interval, lookback_days)
        if raw is None or raw.empty:
            raise ValueError(f"{symbol} ({interval}) uchun Alpaca'dan bo'sh ma'lumot qaytdi")

        clean = self._clean(raw, symbol)

        # Standart holatda (include_extended_hours=False) intraday ma'lumotlardan faqat RTH barlari saqlanadi
        if not include_extended_hours and interval in _INTRADAY_INTERVALS:
            clean = filter_rth(clean)

        self._write_cache(clean, cache_path)

        if closed_only:
            return filter_closed_bars(clean, interval, as_of=as_of)
        return clean

    def _fetch_raw(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        """Alpaca API'ga murojaat qilib xom bars DataFrame'ni qaytaradi."""
        client = self._get_client()
        start = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=_INTERVAL_TO_TIMEFRAME[interval],
            start=start,
            feed=DataFeed.IEX,
        )
        bars = client.get_stock_bars(request)
        return bars.df

    def _get_client(self) -> StockHistoricalDataClient:
        """Alpaca client'ni faqat kerak bo'lganda (birinchi tarmoq chaqiruvida) yaratadi."""
        if self._client is None:
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")
            if not api_key or not secret_key:
                raise ValueError(
                    "ALPACA_API_KEY va ALPACA_SECRET_KEY .env faylida topilmadi. "
                    ".env.example'ga qarab .env (loyiha ildizi) yarating."
                )
            self._client = StockHistoricalDataClient(api_key, secret_key)
        return self._client

    @staticmethod
    def _clean(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Xom Alpaca DataFrame'ni standart OHLCV formatiga keltiradi va validatsiya qiladi."""
        df = df.copy()

        # Ko'p symbolli MultiIndex holatida bitta symbolni ajratish
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        return validate_ohlcv(df, symbol=symbol)

    @staticmethod
    def _cache_path(
        symbol: str, interval: str, include_extended_hours: bool = False
    ) -> Path:
        suffix = "_ext" if include_extended_hours else ""
        return CACHE_DIR / f"alpaca_{symbol}_{interval}{suffix}.parquet"

    @staticmethod
    def _is_cache_fresh(path: Path, interval: str = "1d") -> bool:
        if not path.exists():
            return False

        if interval in _INTRADAY_FAST_INTERVALS:
            age_minutes = (time.time() - path.stat().st_mtime) / 60
            return age_minutes < CACHE_TTL_INTRADAY_MINUTES

        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours < CACHE_TTL_HOURS

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as exc:
            logger.warning("Keshga yozib bo'lmadi: %s", exc)
