"""yfinance orqali OHLCV ma'lumot olib beruvchi konkret provayder."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.settings import CACHE_DIR, CACHE_TTL_HOURS, PERIOD_1H, PERIOD_DEFAULT
from data.provider import DataProvider

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

# Bar-sana tekshiruvi shu interval'larga qo'llanadi (kunlik/haftalik — bir kunlik
# lag ham sezilarli). Intraday interval'lar faqat TTL bilan boshqariladi.
_DATE_STALE_INTERVALS: set[str] = {"1d"}

# US savdo sessiyasi ~20:00 UTC (yozda) / 21:00 UTC (qishda) yopiladi. 21:00 UTC dan
# keyin shu kunning kunlik bari yopilgan deb hisoblanadi (yfinance yetkazib berish
# kechikishiga ham marja).
_SESSION_CLOSE_HOUR_UTC = 21


def _latest_expected_session_date(now: datetime | None = None) -> date:
    """Oxirgi 'yopilgan bo'lishi kutiladigan' US savdo kuni (UTC bo'yicha).

    Bugungi sessiya hali yopilmagan bo'lsa (yoki hafta oxiri) -> oldingi savdo kuni.
    BAYRAMLAR hisobga OLINMAYDI — bayram kunlarida kesh bir marta ortiqcha
    yangilanadi (yfinance o'sha bar'ni bermaydi), natija to'g'ri qoladi."""
    now = now or datetime.now(timezone.utc)
    d = now.date()
    if now.hour < _SESSION_CLOSE_HOUR_UTC:
        d -= timedelta(days=1)
    while d.weekday() >= 5:  # 5=shanba, 6=yakshanba
        d -= timedelta(days=1)
    return d

# yfinance "4h"ni toza bermaydi (abstraksiya oqadigan joy — shuning uchun
# umumiy VALID_INTERVALS emas, shu provider O'ZI qo'llab-quvvatlaydigan
# subset'ga qarab validatsiya qilamiz)
SUPPORTED_INTERVALS: set[str] = {"1d", "1wk", "1h"}


class YFinanceProvider(DataProvider):
    """yfinance kutubxonasiga asoslangan DataProvider implementatsiyasi."""

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        symbol = symbol.upper()
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"YFinanceProvider '{interval!r}'ni qo'llab-quvvatlamaydi. "
                f"Qo'llab-quvvatlanadiganlar: {sorted(SUPPORTED_INTERVALS)}"
            )

        cache_path = self._cache_path(symbol, interval)
        if use_cache and cache_path.exists():
            cached = pd.read_parquet(cache_path)
            if self._is_cache_fresh(cache_path, cached, interval):
                return cached

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
    def _is_cache_fresh(path: Path, df: pd.DataFrame | None = None, interval: str = "1d") -> bool:
        """Kesh 'yangi'mi:

        1) fayl yoshi < CACHE_TTL_HOURS BO'LISHI SHART; VA
        2) kunlik (`_DATE_STALE_INTERVALS`) uchun qo'shimcha: keshdagi oxirgi bar
           o'tgan oxirgi savdo kunidan (`_latest_expected_session_date`) eski
           BO'LMASLIGI kerak — aks holda yoshi qancha yosh bo'lsa ham "eski"
           (masalan: skan ertalab ishlagan, kunlik bar kechqurun yopilgan)."""
        if not path.exists():
            return False
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours >= CACHE_TTL_HOURS:
            return False
        if interval in _DATE_STALE_INTERVALS and df is not None and len(df):
            last_bar_date = pd.Timestamp(df.index[-1]).date()
            if last_bar_date < _latest_expected_session_date():
                return False
        return True

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        # Kesh yozib bo'lmasa ham dastur ishlashda davom etishi kerak
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as exc:
            logger.warning("Keshga yozib bo'lmadi: %s", exc)
