"""Loyiha bo'ylab ishlatiladigan sozlamalar va konstantalar."""

from __future__ import annotations

from pathlib import Path

# Asosiy va kontekst timeframe'lar (4h yo'q — yfinance uni toza bermaydi)
PRIMARY_INTERVAL: str = "1d"
CONTEXT_INTERVAL: str = "1wk"
VALID_INTERVALS: set[str] = {"1d", "1wk", "1h"}

# Parquet kesh papkasi — CWD'ga emas, paket ildiziga nisbatan aniqlanadi
CACHE_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_TTL_HOURS: int = 12

# yf.download uchun davr (period) parametrlari
PERIOD_1H: str = "730d"
PERIOD_DEFAULT: str = "10y"

# Swing detection uchun default lookback — vizual tekshiruvda eng toza struktura berdi
SWING_LOOKBACK: int = 5
