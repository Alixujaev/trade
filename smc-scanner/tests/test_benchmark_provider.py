"""journal/benchmark_provider.py (I/O qatlami -- provider orqali, mock bilan) uchun testlar."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from journal.benchmark import BenchmarkResult
from journal.benchmark_provider import benchmark_result_for_entry
from journal.types import JournalEntry


def _make_df(dates: list[str], closes: list[float]) -> pd.DataFrame:
    """YFinanceProvider.get_ohlcv bilan bir xil format: tz-aware UTC DatetimeIndex,
    o'sish tartibida, ['open','high','low','close','volume'] ustunlari."""
    index = pd.DatetimeIndex(pd.to_datetime(dates), tz="UTC", name="datetime")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1000] * len(closes)},
        index=index,
    )


class _FakeProvider:
    """tests/test_scanner.py::_FakeProvider bilan bir xil konvensiya."""

    def __init__(self, dfs: dict[str, pd.DataFrame | Exception]) -> None:
        self._dfs = dfs

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        result = self._dfs[symbol]
        if isinstance(result, Exception):
            raise result
        return result


def _closed_entry(**overrides) -> JournalEntry:
    defaults = dict(
        entry_id=1, symbol="AAPL", entry_date=date(2026, 1, 1), entry_price=100.0,
        stop_price=90.0, target_price=130.0, exit_mode="fixed", reason="FVG",
        rr_planned=3.0, exit_date=date(2026, 1, 10), exit_price=115.0, r_multiple=1.5,
    )
    defaults.update(overrides)
    return JournalEntry(**defaults)


# ======================================================================
# benchmark_result_for_entry -- happy path
# ======================================================================


def test_benchmark_result_for_entry_uses_close_on_exit_date() -> None:
    entry = _closed_entry()
    provider = _FakeProvider({
        "AAPL": _make_df(
            ["2026-01-01", "2026-01-05", "2026-01-10", "2026-01-15"],
            [100.0, 105.0, 108.0, 120.0],
        ),
    })

    result = benchmark_result_for_entry(entry, provider=provider)

    assert result == BenchmarkResult(
        symbol="AAPL", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
        entry_price=100.0, benchmark_exit_price=108.0,
        benchmark_return=pytest.approx(0.08),
    )


def test_benchmark_result_for_entry_same_window_dates() -> None:
    """Benchmark oynasi AYNAN entry_date -> exit_date (test_benchmark_result_for_entry_
    uses_close_on_exit_date bilan bir xil ma'lumot, sana maydonlarini alohida tekshiradi)."""
    entry = _closed_entry(entry_date=date(2026, 2, 1), exit_date=date(2026, 2, 20))
    provider = _FakeProvider({
        "AAPL": _make_df(["2026-02-01", "2026-02-20"], [100.0, 130.0]),
    })

    result = benchmark_result_for_entry(entry, provider=provider)

    assert result.start_date == date(2026, 2, 1)
    assert result.end_date == date(2026, 2, 20)


# ======================================================================
# graceful skip -- xato/data yo'q holatlarida None, exception YO'Q
# ======================================================================


def test_benchmark_result_for_entry_none_when_entry_still_open() -> None:
    entry = _closed_entry(exit_date=None, exit_price=None, r_multiple=None)
    provider = _FakeProvider({"AAPL": _make_df(["2026-01-01"], [100.0])})

    assert benchmark_result_for_entry(entry, provider=provider) is None


def test_benchmark_result_for_entry_none_on_provider_error() -> None:
    entry = _closed_entry()
    provider = _FakeProvider({"AAPL": ConnectionError("network down")})

    assert benchmark_result_for_entry(entry, provider=provider) is None


def test_benchmark_result_for_entry_none_when_exit_date_bar_missing() -> None:
    """exit_date=2026-01-10 lekin provider ma'lumotida shu kun uchun bar yo'q (masalan
    dam olish kuni yoki tarixiy chegaradan tashqarida) -- None, exception EMAS."""
    entry = _closed_entry()
    provider = _FakeProvider({
        "AAPL": _make_df(["2026-01-01", "2026-01-05"], [100.0, 105.0]),
    })

    assert benchmark_result_for_entry(entry, provider=provider) is None
