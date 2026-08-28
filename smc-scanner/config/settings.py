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
# Kesh yoshi chegarasi (soat). Kunlik (1d) kesh uchun BUNDAN tashqari bar-sana
# tekshiruvi ham bor (data/yfinance_provider.py::_is_cache_fresh): oxirgi bar
# o'tgan oxirgi savdo kunidan eski bo'lsa, yoshi ne bo'lishidan qat'i nazar
# kesh "eski" hisoblanadi. TTL bu yerda faqat "bugungi to'lmagan barni qayta
# tortish" oralig'i (kunlik bot uchun 12h juda katta edi -> 4h).
CACHE_TTL_HOURS: int = 4

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
# Trailing (va fixed) setup'larda rejalashtirilgan R:R shu qiymatdan past bo'lsa,
# ko'rsatish qatlamida ⚠️ bilan belgilanadi (FAQAT belgilash — yashirish YO'Q).
MIN_PLANNED_RR: float = 1.5
# Backtest "atr" risk_model: bir aksiya uchun risk = shu * ATR[entry]
ATR_RISK_MULT: float = 1.0

# Core watchlist: shu kundan ko'p vaqt o'tsa, halal statusni qayta tekshirish kerak deb belgilanadi
REVIEW_INTERVAL_DAYS: int = 90

# Trailing exit: stop = running_high - shu * ATR. Sodda (ATR-asosli) variant tanlandi —
# swing-low-asosli trailing savdo davomida yangi tasdiqlangan swing'larni kuzatishni
# talab qilardi (backtest/engine.py::_simulate_trailing_exit'ga qarang).
TRAIL_ATR_MULT: float = 2.0

# Taktik/paper qatlam risk boshqaruvi (telegram_bot/risk uchun) — maksimal ochiq
# pozisiya soni. Kapital/pozitsiya-hajmi bu botda hisoblanmaydi — savdoga
# kirish/chiqish boshqa platformada (masalan TradingView paper trading) qilinadi.
MAX_OPEN_POSITIONS: int = 3

# /watchlist: shu sondan ko'p bo'lsa, har yozuv uchun to'liq matn+🗑 tugma o'rniga
# qisqa (kompakt) ro'yxat ko'rsatiladi — aks holda Telegram'ning 4096 belgili
# xabar limitidan va yuzlab tugmali keyboard'dan oshib ketishi mumkin.
WATCHLIST_COMPACT_THRESHOLD: int = 40
