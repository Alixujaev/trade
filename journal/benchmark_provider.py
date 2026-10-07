"""JournalEntry'lar uchun buy&hold benchmark'ni HAQIQIY narx ma'lumoti bilan hisoblovchi
I/O qatlami -- `journal/benchmark.py` (sof, I/O'siz) dan ATAYLAB alohida fayl: bu yerda
tarmoq/kesh (mavjud `data.factory.get_provider` + `DataProvider.get_ohlcv`ning o'z keshi)
bor, sof qatlamda yo'q -- backtest'dagi pure-simulator vs I/O-loader ajratilishi bilan
bir xil konvensiya.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from data.factory import get_provider
from data.provider import DataProvider
from journal.benchmark import BenchmarkResult, calculate_buy_hold_return
from journal.types import JournalEntry

logger = logging.getLogger(__name__)


def _close_price_on(df: pd.DataFrame, target_date: date) -> float | None:
    """df'dan (tz-aware UTC DatetimeIndex) target_date kunidagi close narxini topadi.

    Shu kunga mos bar topilmasa (dam olish kuni, tarixiy chegaradan tashqarida va h.k.)
    -- None (chaqiruvchi SKIP qiladi, xato ko'tarilmaydi)."""
    matches = df.index[df.index.date == target_date]
    if len(matches) == 0:
        return None
    return float(df.loc[matches[-1], "close"])


def benchmark_result_for_entry(
    entry: JournalEntry, *, provider: DataProvider | None = None,
) -> BenchmarkResult | None:
    """Yopilgan `JournalEntry` uchun `BenchmarkResult` hisoblaydi: symbol'ning
    `exit_date`dagi close narxini `provider` (kesh bilan) orqali olib, `entry.entry_price`
    bilan solishtiradi (same-window: entry_date -> exit_date).

    Ochiq savdo (`exit_date`/`exit_price`=None), provider xatosi yoki `exit_date`da bar
    topilmasa -- None. Chaqiruvchi (masalan `TradeJournal.stats()`) None'ni "shu savdo
    benchmark'ga kiritilmadi" deb SKIP qiladi -- butun hisoblash yiqilmaydi."""
    if entry.exit_date is None or entry.exit_price is None:
        return None

    provider = provider or get_provider()
    try:
        df = provider.get_ohlcv(entry.symbol, "1d")
    except Exception as exc:  # noqa: BLE001 -- provider xatosi butun jurnalni yiqitmasligi kerak
        logger.warning("Benchmark uchun %s ma'lumoti olinmadi: %s", entry.symbol, exc)
        return None

    exit_close = _close_price_on(df, entry.exit_date)
    if exit_close is None:
        logger.warning(
            "Benchmark: %s uchun %s kunida bar topilmadi", entry.symbol, entry.exit_date,
        )
        return None

    return BenchmarkResult(
        symbol=entry.symbol,
        start_date=entry.entry_date,
        end_date=entry.exit_date,
        entry_price=entry.entry_price,
        benchmark_exit_price=exit_close,
        benchmark_return=calculate_buy_hold_return(entry.entry_price, exit_close),
    )
