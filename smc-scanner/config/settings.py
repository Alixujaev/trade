"""Loyiha bo'ylab ishlatiladigan sozlamalar va konstantalar."""

from __future__ import annotations

from pathlib import Path

# Asosiy va kontekst timeframe'lar
PRIMARY_INTERVAL: str = "1d"
CONTEXT_INTERVAL: str = "1wk"
ENTRY_INTERVAL: str = "4h"  # entry-timing qatlami (Alpaca orqali — yfinance 4h bermaydi)

# Umumiy "tanish interval'lar" ro'yxati (typo-check uchun). MUHIM: bu HAR BIR
# provider shu interval'ni qo'llab-quvvatlashini KAFOLATLAMAYDI — masalan
# yfinance "4h"ni toza bermaydi. Har provider o'zining qo'llab-quvvatlaydigan
# subset'ini o'zida (masalan yfinance_provider.py/alpaca_provider.py) belgilaydi
# va shunga qarab validatsiya qiladi.
VALID_INTERVALS: set[str] = {"1d", "1wk", "1h", "4h"}

# Parquet kesh papkasi — CWD'ga emas, paket ildiziga nisbatan aniqlanadi
CACHE_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_TTL_HOURS: int = 12

# yf.download uchun davr (period) parametrlari
PERIOD_1H: str = "730d"
PERIOD_DEFAULT: str = "10y"

# Swing detection uchun default lookback — vizual tekshiruvda eng toza struktura berdi
SWING_LOOKBACK: int = 5

# Alpaca uchun tarixiy ma'lumot chuqurligi (kun hisobida, start=now-N kun)
ALPACA_LOOKBACK_DAYS_INTRADAY: int = 60  # 1h/4h uchun
ALPACA_LOOKBACK_DAYS_DEFAULT: int = 3650  # 1d/1wk uchun (~10 yil)

# Default data provider: "yfinance" yoki "alpaca". factory.get_provider() shu yerdan o'qiydi.
DATA_PROVIDER: str = "yfinance"

# Displacement (FVG/OB asosi) uchun ATR parametrlari
ATR_PERIOD: int = 14
DISPLACEMENT_ATR_MULT: float = 1.5

# Signal engine: stop = zona bottom - shu * ATR
STOP_BUFFER_ATR_MULT: float = 0.1
# Signal engine: mos swing high topilmasa, fallback target = entry + shu * risk
DEFAULT_TARGET_R_MULTIPLE: float = 2.0
# Backtest "atr" risk_model: bir aksiya uchun risk = shu * ATR[entry]
ATR_RISK_MULT: float = 1.0
