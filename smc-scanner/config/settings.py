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
# Taktik skaner: "hozir kirsa bo'ladigan" oynasi = entry ± shu * ATR. ATR-asosli
# (har ticker uchun moslashuvchan), qat'iy % emas. Oxirgi close shu oynadan yuqori
# bo'lsa "o'tib ketgan" (kirib bo'lmaydi), past bo'lsa "zona ichida" (momentum kuchsiz).
ENTRY_TOLERANCE_ATR_MULT: float = 0.5
# signals/scanner.py: SignalPayload.entry_zone kengligi = entry ± shu * ATR. MUHIM:
# ENTRY_TOLERANCE_ATR_MULT'dan ALOHIDA — u "narx hali kirish oynasidami" degan TAKTIK
# qayta-tekshiruv, bu esa payload'da KO'RSATILADIGAN zonaning KENGLIGI (display concern).
ENTRY_ZONE_ATR_MULT: float = 0.25
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


# ======================================================================
# V1 breakout+retest strategiyasi (TZ 5-15). Barcha qiymat backtest bilan
# qo'lda sozlanadi — bu yerda "chiroyli ko'rinishi uchun" hech narsa tanlanmagan,
# TZ'dagi standart qiymatlardan boshlanadi.
# ======================================================================

# --- Trend rejimi (EMA regime filter, TZ 5) ---
EMA_FAST_PERIOD: int = 20
EMA_MID_PERIOD: int = 50
EMA_SLOW_PERIOD: int = 200

# --- Volume tasdig'i (TZ 10) ---
# Breakout barida current_volume / volume_MA shu qiymatdan katta bo'lishi kerak.
VOLUME_MA_PERIOD: int = 20
VOLUME_BREAKOUT_RATIO: float = 1.5
# Scoring: volume nisbati shu qiymatga yetganda volume sub-ball = 1.0 (to'yinish).
VOLUME_RATIO_SATURATION: float = 3.0

# --- Support/Resistance zonalari (TZ 7) ---
# Klaster tasma yarim-kengligi = shu * ATR (median). Swing narxlari shu tasmaga
# sig'sa bitta zona (band) deb birlashtiriladi.
SR_CLUSTER_ATR_MULT: float = 0.5
# ATR butunlay NaN bo'lsa (juda qisqa data) fallback: narxning shu ulushi.
SR_CLUSTER_PCT: float = 0.01
# Zona bo'lishi uchun minimal reaksiya (teginish) soni.
SR_MIN_TOUCHES: int = 3
# strength: shu ta teginishda touch sub-ball = 1.0 (to'yinish).
SR_TOUCH_SATURATION: int = 5

# --- Breakout + retest state machine (TZ 8.1-8.2) ---
# Breakout'dan keyin retest shu bar ichida sodir bo'lishi kerak, aks holda setup bekor.
RETEST_MAX_BARS: int = 15
# Retest "tegdi" deb hisoblash uchun zona chegarasiga yaqinlik dopuski = shu * ATR.
RETEST_TOLERANCE_ATR_MULT: float = 0.25
# Retest'dan keyin bullish tasdiq shamchasi shu bar ichida kelishi kerak.
CONFIRMATION_MAX_BARS: int = 5

# --- Risk / stop / target (TZ 12, 14) ---
BREAKOUT_SL_ATR_MULT: float = 1.0
# "structure" = zona bottom - k*ATR | "atr" = entry - k*ATR | "widest" = ikkisidan pasti.
BREAKOUT_STOP_MODE: str = "structure"
# Keyingi qarshilik zonasi topilmasa (yoki R:R past bo'lsa) fallback target = entry + shu * risk.
BREAKOUT_TP_R_MULTIPLE: float = 2.0
# Rejalashtirilgan R:R shu qiymatdan past bo'lsa, setup UMUMAN emit qilinmaydi (TZ 14).
MIN_BREAKOUT_RR: float = 1.5
# Position sizing: bir savdoda hisob kapitalining shu ulushi risk qilinadi (TZ 12).
RISK_PCT_PER_TRADE: float = 0.01

# Portfel-darajali backtest (backtest/portfolio.py). MAX_OPEN_POSITIONS (telegram
# qatlami) dan ALOHIDA — bu FAQAT portfel simulyatoriga tegishli.
MAX_CONCURRENT_POSITIONS: int = 10
# Ochiq pozitsiyalar rejalashtirilgan riski (stop-out zarari) yig'indisi joriy
# realized kapitalning shu ulushidan oshmasligi kerak — aks holda yangi pozitsiya yo'q.
MAX_PORTFOLIO_RISK_PCT: float = 0.10

# --- Signal scoring 0-100 (TZ 11) ---
# Swing weighting. V1'da SMC qatlami yo'q -> "smc" doim 0, amaliy maksimal ~90.
SCORE_WEIGHTS: dict[str, float] = {
    "trend": 0.30,
    "structure": 0.20,
    "setup": 0.20,
    "volume": 0.10,
    "smc": 0.10,
    "risk": 0.10,
}
# >=strong_buy -> STRONG_BUY, >=buy -> BUY, >=watch -> WATCH, aks holda NO_TRADE.
SCORE_THRESHOLDS: dict[str, float] = {"strong_buy": 80.0, "buy": 70.0, "watch": 60.0}
# risk sub-ball: R:R shu qiymatga yetganda sub-ball = 1.0.
SCORE_RR_SATURATION: float = 3.0

# --- Backtest xarajatlari (TZ 15) — brokerga qarab moslanadi ---
BREAKOUT_COMMISSION_PCT: float = 0.0005
BREAKOUT_SLIPPAGE_PCT: float = 0.0005
