"""data/earnings.py: qo'lda yuritiladigan earnings kalendari (ORB filtri uchun), fail-closed.

CSV ustunlari: symbol,coverage_start,coverage_end,earnings_date
- Har bir symbol uchun coverage [coverage_start, coverage_end] - shu oraliqdagi barcha earnings sanalari ro'yxatda
  ekanligini bildiradi. earnings_date bo'sh bo'lishi mumkin (oraliqda earnings yo'q).
- Bitta symbol uchun barcha qatorlarda coverage bir xil bo'lishi shart.

Fail closed: fayl yo'q, ustun yo'q, sana xato, coverage nomuvofiq, symbol yo'q yoki so'ralgan oraliq qamrab
olinmagan bo'lsa EarningsCoverageError. "Earnings yo'q" hech qachon jimgina taxmin qilinmaydi.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

REQUIRED_COLUMNS = ("symbol", "coverage_start", "coverage_end", "earnings_date")


class EarningsCoverageError(RuntimeError):
    """Earnings ma'lumoti yo'q, noto'g'ri yoki so'ralgan sana/symbol'ni qamrab olmaydi."""


@dataclass(frozen=True)
class EarningsCalendar:
    coverage: dict[str, tuple[date, date]]
    dates: dict[str, frozenset[date]]

    def check_coverage(self, symbols: Iterable[str], start: date, end: date) -> None:
        for s in symbols:
            if s not in self.coverage:
                raise EarningsCoverageError(f"earnings calendar has no coverage for {s}")
            lo, hi = self.coverage[s]
            if start < lo or end > hi:
                raise EarningsCoverageError(
                    f"earnings coverage for {s} is {lo}..{hi}; required {start}..{end}")

    def is_earnings_day(self, symbol: str, day: date) -> bool:
        self.check_coverage([symbol], day, day)
        return day in self.dates.get(symbol, frozenset())


def _d(value: str, what: str, line: int) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise EarningsCoverageError(f"line {line}: invalid {what} {value!r}") from None


def load_earnings_calendar(path: str | Path) -> EarningsCalendar:
    p = Path(path)
    if not p.is_file():
        raise EarningsCoverageError(f"earnings calendar not found: {p}")
    coverage: dict[str, tuple[date, date]] = {}
    dates: dict[str, set[date]] = {}
    with p.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise EarningsCoverageError(f"earnings calendar is missing columns {missing}")
        for line, row in enumerate(reader, start=2):
            sym = (row["symbol"] or "").strip().upper()
            if not sym:
                raise EarningsCoverageError(f"line {line}: empty symbol")
            cov = (_d(row["coverage_start"] or "", "coverage_start", line),
                   _d(row["coverage_end"] or "", "coverage_end", line))
            if cov[0] > cov[1]:
                raise EarningsCoverageError(f"line {line}: coverage_start after coverage_end")
            if coverage.setdefault(sym, cov) != cov:
                raise EarningsCoverageError(f"line {line}: inconsistent coverage for {sym}")
            raw = (row["earnings_date"] or "").strip()
            dates.setdefault(sym, set())
            if raw:
                d = _d(raw, "earnings_date", line)
                if not cov[0] <= d <= cov[1]:
                    raise EarningsCoverageError(f"line {line}: earnings_date {d} outside coverage for {sym}")
                dates[sym].add(d)
    if not coverage:
        raise EarningsCoverageError(f"earnings calendar is empty: {p}")
    return EarningsCalendar(coverage=coverage, dates={k: frozenset(v) for k, v in dates.items()})
