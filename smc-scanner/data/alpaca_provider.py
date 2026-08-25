"""Alpaca Market Data API orqali OHLCV ma'lumot olib beruvchi konkret provayder.

FREE tier (IEX feed) ishlatiladi — paper trading uchun yetarli. Kredensiallar
.env fayldan (ALPACA_API_KEY, ALPACA_SECRET_KEY) o'qiladi, hech qachon kodda
hardcode qilinmaydi.
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
)
from data.provider import DataProvider

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

# Bizning standart interval string -> Alpaca TimeFrame mapping.
# Alpaca 4H'ni ham to'g'ri beradi (yfinance esa yo'q) — shu provider'ning
# asosiy sababi ham shu.
_INTERVAL_TO_TIMEFRAME: dict[str, TimeFrame] = {
    "1d": TimeFrame.Day,
    "4h": TimeFrame(4, TimeFrameUnit.Hour),
    "1h": TimeFrame.Hour,
    "1wk": TimeFrame.Week,
}

SUPPORTED_INTERVALS: set[str] = set(_INTERVAL_TO_TIMEFRAME)
_INTRADAY_INTERVALS = {"1h", "4h"}


class AlpacaProvider(DataProvider):
    """Alpaca Market Data API (IEX feed, free tier) asosidagi DataProvider implementatsiyasi."""

    def __init__(self) -> None:
        load_dotenv()
        self._client: StockHistoricalDataClient | None = None  # kerak bo'lgandagina yaratiladi

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        symbol = symbol.upper()
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"AlpacaProvider '{interval!r}'ni qo'llab-quvvatlamaydi. "
                f"Qo'llab-quvvatlanadiganlar: {sorted(SUPPORTED_INTERVALS)}"
            )

        cache_path = self._cache_path(symbol, interval)
        if use_cache and self._is_cache_fresh(cache_path):
            return pd.read_parquet(cache_path)

        lookback_days = (
            ALPACA_LOOKBACK_DAYS_INTRADAY if interval in _INTRADAY_INTERVALS else ALPACA_LOOKBACK_DAYS_DEFAULT
        )
        raw = self._fetch_raw(symbol, interval, lookback_days)
        if raw is None or raw.empty:
            raise ValueError(f"{symbol} ({interval}) uchun Alpaca'dan bo'sh ma'lumot qaytdi")

        clean = self._clean(raw, symbol)
        self._write_cache(clean, cache_path)
        return clean

    def _fetch_raw(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        """Alpaca API'ga murojaat qilib xom bars DataFrame'ni qaytaradi.

        Bu metod tarmoqqa chiqadigan yagona joy — testlarda monkeypatch qilinadi.
        """
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
        """Alpaca client'ni faqat haqiqatan kerak bo'lganda (birinchi tarmoq chaqiruvida) yaratadi."""
        if self._client is None:
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")
            if not api_key or not secret_key:
                raise ValueError(
                    "ALPACA_API_KEY va ALPACA_SECRET_KEY .env faylida topilmadi. "
                    ".env.example'ga qarab smc-scanner/.env yarating."
                )
            self._client = StockHistoricalDataClient(api_key, secret_key)
        return self._client

    @staticmethod
    def _clean(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Xom Alpaca DataFrame'ni standart OHLCV formatiga keltiradi."""
        df = df.copy()

        # Alpaca ko'p-symbol so'ralganda (symbol, timestamp) MultiIndex qaytaradi —
        # bitta symbol'ni ajratib, faqat timestamp'ni index qilib qoldiramiz
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        df.columns = [str(c).lower() for c in df.columns]
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Kerakli ustunlar yo'q: {missing}")
        df = df[REQUIRED_COLUMNS]  # trade_count/vwap kabi qo'shimcha ustunlar tashlanadi

        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.index.name = "datetime"

        df = df.dropna()
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()
        return df

    @staticmethod
    def _cache_path(symbol: str, interval: str) -> Path:
        # "alpaca_" prefiksi — yfinance kesh fayllari bilan aralashmasligi uchun
        return CACHE_DIR / f"alpaca_{symbol}_{interval}.parquet"

    @staticmethod
    def _is_cache_fresh(path: Path) -> bool:
        if not path.exists():
            return False
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours < CACHE_TTL_HOURS

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as exc:
            logger.warning("Keshga yozib bo'lmadi: %s", exc)
