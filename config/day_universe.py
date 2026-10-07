"""config/day_universe.py: DAY-04 — Frozen Multi-Symbol Research Universe.

QAT'IY METODOLOGIK QOIDALAR:
1. Ushbu universe TADQIQOT NAMUNASI (research sample) hisoblanadi.
2. Backtest natijalariga qarab "yaxshi" yoki "yomon" aksiyalar tanlanmagan (no cherry-picking).
3. Barcha 25 aksiya likvidligi eng yuqori bo'lgan, turli iqtisodiy sektorlarni ifodalovchi
   US mega/large-cap aksiyalari orasidan tadqiqot boshlanishidan oldin belgilab qo'yilgan.
4. Survivorship bias va data-snooping'dan xoli bo'lishi uchun universe kodda muzlatilgan.
"""

from __future__ import annotations

from typing import Final, Sequence


# Muzlatilgan 25 ta likvid US aksiyalari
FROZEN_DAY_UNIVERSE: Final[tuple[str, ...]] = (
    # Mega-cap Tech & Information
    "AAPL",   # Apple Inc. (Technology - Consumer Hardware / Ecosystem)
    "MSFT",   # Microsoft Corp. (Technology - Enterprise Software / Cloud)
    "NVDA",   # NVIDIA Corp. (Semiconductors - GPU / AI Computing)
    "AMZN",   # Amazon.com Inc. (Consumer Discretionary - E-Commerce / Cloud)
    "META",   # Meta Platforms Inc. (Communication Services - Digital Ads / Social)
    "GOOGL",  # Alphabet Inc. (Communication Services - Search / Cloud)
    "TSLA",   # Tesla Inc. (Consumer Discretionary - Electric Vehicles / Energy)
    # Semiconductors & Hardware
    "AVGO",   # Broadcom Inc. (Semiconductors - Networking / Wireless)
    "AMD",    # Advanced Micro Devices Inc. (Semiconductors - CPU / GPU)
    "QCOM",   # Qualcomm Inc. (Semiconductors - Mobile Communications)
    "INTC",   # Intel Corp. (Semiconductors - Processors / Foundry)
    "MU",     # Micron Technology Inc. (Semiconductors - Memory DRAM / NAND)
    "AMAT",   # Applied Materials Inc. (Semiconductor Capital Equipment)
    # Enterprise Software & Networking
    "ADBE",   # Adobe Inc. (Technology - Creative & Document Software)
    "CRM",    # Salesforce Inc. (Technology - CRM / Enterprise Cloud)
    "ORCL",   # Oracle Corp. (Technology - Enterprise Database / Infrastructure)
    "CSCO",   # Cisco Systems Inc. (Technology - Networking Infrastructure)
    # Consumer & Retail
    "COST",   # Costco Wholesale Corp. (Consumer Staples - Wholesale Retail)
    "WMT",    # Walmart Inc. (Consumer Staples - Hypermarket Retail)
    "KO",     # The Coca-Cola Co. (Consumer Staples - Non-Alcoholic Beverages)
    "PEP",    # PepsiCo Inc. (Consumer Staples - Beverages & Snacks)
    # Communication & Media
    "NFLX",   # Netflix Inc. (Communication Services - Streaming Entertainment)
    # Healthcare
    "JNJ",    # Johnson & Johnson (Healthcare - Pharmaceuticals & Medical Tech)
    # Financials & Energy
    "JPM",    # JPMorgan Chase & Co. (Financials - Diversified Banking)
    "XOM",    # Exxon Mobil Corp. (Energy - Integrated Oil & Gas)
)

# Diagnostik bozor konteksti uchun indeks ETF'lar (strategiya filtri EMAS)
MARKET_BENCHMARK_SYMBOLS: Final[tuple[str, ...]] = ("SPY", "QQQ")


def get_day_universe() -> list[str]:
    """Muzlatilgan universe nusxasini qaytaradi: normalizatsiya qilingan, tartiblangan, takrorlanishsiz."""
    return list(FROZEN_DAY_UNIVERSE)


def normalize_symbol(symbol: str) -> str:
    """Ticker belgisini standart formatga keltiradi."""
    return symbol.strip().upper()


def validate_universe_symbols(symbols: Sequence[str]) -> list[str]:
    """Berilgan belgilar ro'yxatini normalizatsiya qiladi, dublikatlarni olib tashlaydi."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for s in symbols:
        norm = normalize_symbol(s)
        if norm and norm not in seen:
            seen.add(norm)
            cleaned.append(norm)
    return cleaned
