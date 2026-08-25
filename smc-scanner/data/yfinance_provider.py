"""yfinance orqali OHLCV ma'lumot olib beruvchi konkret provayder."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.settings import CACHE_DIR, CACHE_TTL_HOURS, PERIOD_1H, PERIOD_DEFAULT, VALID_INTERVALS
from data.provider import DataProvider

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


class YFinanceProvider(DataProvider):
    """yfinance kutubxonasiga asoslangan DataProvider implementatsiyasi."""

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        symbol = symbol.upper()
        if interval not in VALID_INTERVALS:
            raise ValueError(
                f"Noto'g'ri interval: {interval!r}. Ruxsat etilganlar: {sorted(VALID_INTERVALS)}"
            )

        cache_path = self._cache_path(symbol, interval)
        if use_cache and self._is_cache_fresh(cache_path):
            return pd.read_parquet(cache_path)

        period = PERIOD_1H if interval == "1h" else PERIOD_DEFAULT
        raw = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            raise ValueError(f"{symbol} ({interval}) uchun yfinance'dan bo'sh ma'lumot qaytdi")

        clean = self._clean(raw)
        self._write_cache(clean, cache_path)
        return clean

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        """Xom yfinance DataFrame'ni standart OHLCV formatiga keltiradi."""
        df = df.copy()

        # MultiIndex ustunlarni tekislash, masalan ('Close','SPUS') -> 'Close'
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Kerakli ustunlar yo'q: {missing}")
        df = df[REQUIRED_COLUMNS]

        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.index.name = "datetime"

        df = df.dropna()
        # Dublikat timestamp'lardan oxirgisi saqlanadi (yangi olingan qator ishonchliroq)
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()
        return df

    @staticmethod
    def _cache_path(symbol: str, interval: str) -> Path:
        return CACHE_DIR / f"{symbol}_{interval}.parquet"

    @staticmethod
    def _is_cache_fresh(path: Path) -> bool:
        if not path.exists():
            return False
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours < CACHE_TTL_HOURS

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        # Kesh yozib bo'lmasa ham dastur ishlashda davom etishi kerak
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as exc:
            logger.warning("Keshga yozib bo'lmadi: %s", exc)
