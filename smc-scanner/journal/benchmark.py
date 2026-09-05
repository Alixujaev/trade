"""Discretionary savdolarni market benchmark bilan solishtiruvchi SOF (I/O'siz) qatlam.

Framing: bu "robotni baholash" EMAS -- bot decision-support scanner, YAKUNIY savdo
qarorini odam qiladi (signals/payload.py'dagi tamoyil bilan bir oilada). Bu yerda faqat
"men (odam) tanlagan savdolar shu vaqt oynasida oddiy buy&hold'dan yaxshiroqmi?" degan
RAQAM chiqariladi -- journal/trade_journal.py'dagi kabi "yaxshi/yomon" degan XULOSA
kod tomonidan HECH QACHON chiqarilmaydi.

MUHIM METODOLOGIYA (buzilmasin):
- R-multiple (risk-adjusted, entry-stop masofasiga nisbatan normallashtirilgan) va
  buy&hold PRICE return ((exit-entry)/entry) -- ikkita MUSTAQIL birlik, hech qachon
  bitta raqamga aralashtirilmaydi, har doim alohida ko'rsatiladi.
- Benchmark oynasi har doim AYNAN savdoning o'zi (entry_date -> exit_date, "same-window") --
  boshqa davr bilan solishtirish METODOLOGIK XATO (timing/rejim farqi noto'g'ri xulosaga
  olib keladi).

Haqiqiy narx bilan ishlaydigan integratsiya qatlami (provider/kesh) ATAYLAB shu fayldan
TASHQARIDA -- `journal/benchmark_provider.py`ga qarang.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BenchmarkResult:
    """Bitta yopilgan savdo uchun "agar shu AYNAN oynada (entry_date->exit_date) symbolni
    sotib olib oxirigacha ushlab tursam" natijasi.

    entry_price -- savdoning HAQIQIY entry narxi (buy&hold ham shu narxdan "sotib olingan"
    deb hisoblanadi: aks holda farq faqat ikkita boshlang'ich narx orasidagi tasodifiy
    tafovutdan kelib chiqqan bo'lardi, savdo sifatidan emas).
    """

    symbol: str
    start_date: date  # savdoning entry_date'i -- benchmark oynasi shu yerdan boshlanadi
    end_date: date  # savdoning exit_date'i -- SAME-WINDOW, boshqa sana EMAS
    entry_price: float
    benchmark_exit_price: float  # symbol'ning end_date'dagi close narxi
    benchmark_return: float  # (benchmark_exit_price-entry_price)/entry_price -- PRICE return, R EMAS


def calculate_buy_hold_return(entry_price: float, benchmark_exit_price: float) -> float:
    """Pure price return: (benchmark_exit_price - entry_price) / entry_price.

    entry_price <= 0 -- degenerativ/mavjud bo'lmagan narx (ma'lumot xato bo'lsa ham
    yuz berishi mumkin) -- ZeroDivisionError o'rniga xavfsiz 0.0 qaytaradi."""
    if entry_price <= 0:
        return 0.0
    return (benchmark_exit_price - entry_price) / entry_price


def discretionary_price_return(entry_price: float, exit_price: float) -> float:
    """Savdoning HAQIQIY price return'i -- (exit_price-entry_price)/entry_price.

    R-multiple'dan ATAYLAB farqli birlik: R stop-risk masofasiga nisbatan
    normallashtirilgan (masalan tor stop bilan kichik narx harakati R=+2.0 berishi
    mumkin), buy&hold esa xom narx harakatiga qaraydi -- solishtirish uchun ikkalasi
    BIR XIL birlikda kerak (`calculate_buy_hold_return` bilan bir xil formula, faqat
    exit narxi boshqa: savdoning HAQIQIY chiqishi, benchmark chiqishi emas)."""
    if entry_price <= 0:
        return 0.0
    return (exit_price - entry_price) / entry_price


def outperformed_benchmark(
    entry_price: float, exit_price: float, benchmark: BenchmarkResult,
) -> bool:
    """"Discretionary savdo buy&hold'dan yaxshiroqmi?" ning ANIQ ta'rifi -- METODOLOGIK YURAK.

    Solishtirish FAQAT bir xil birlikda (price return) qilinadi: savdoning haqiqiy
    price return'i (`discretionary_price_return`) benchmark'ning price return'idan
    (`benchmark.benchmark_return`) qat'iy KATTA bo'lsa -> True (teng bo'lsa False).
    R-multiple bu yerda HECH QACHON ishlatilmaydi: R risk-normallashtirilgan (masalan
    tor stop bilan R=+2.0 bo'lgan savdo narxda atigi +1% ko'tarilgan bo'lishi mumkin),
    buy&hold esa xom price return -- ikkalasini to'g'ridan-to'g'ri solishtirish
    noto'g'ri xulosaga olib keladi.
    """
    return discretionary_price_return(entry_price, exit_price) > benchmark.benchmark_return
