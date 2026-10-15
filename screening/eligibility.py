"""screening/eligibility.py: fail-closed Sharia eligibility registry - human-decided records, no screening logic.

The code never decides whether a stock is Sharia-compliant. It only loads records that a human entered in
config/sharia_eligibility.csv, each with its methodology and a citable source, and answers per (symbol, session date):

- COMPLIANT: an in-date record whose methodology is in `accepted_methodologies`. The ONLY tradable outcome.
- NON_COMPLIANT / UNVERIFIED: an in-date record with that status. Never tradable.
- UNKNOWN: no record for the symbol, or no record covering the day (before the first, in a gap, after the last).

CSV columns (exact set, order free): symbol,status,valid_from,valid_until,methodology,source,source_ref,source_date,
reviewer,reviewed_on,note
- Dates are ISO YYYY-MM-DD calendar dates (America/New_York sessions); [valid_from, valid_until] is inclusive and
  spans at most MAX_VALIDITY_DAYS days.
- COMPLIANT and NON_COMPLIANT rows need methodology, source, source_ref and source_date. COMPLIANT rows also need a
  methodology in `accepted_methodologies`, which is empty by default, so no COMPLIANT row loads until the owner adopts
  one. HLAL/SPUS ETF membership is not evidence of individual-stock compliance. A methodology whose name contains
  "DRAFT" (e.g. AAOIFI_SS21_V1_DRAFT) can never be accepted; it may still label NON_COMPLIANT/UNVERIFIED rows.
- UNVERIFIED rows need a non-empty note giving the reason (e.g. which input is missing or stale).
- Point in time: source_date <= valid_from (a status starts only once its source was public), and
  reviewed_on >= source_date.
- Freshness: valid_from - source_date <= MAX_SOURCE_AGE_DAYS calendar days, so an old screen cannot be chained into
  new windows. This is separate from the validity-window limit. The point-in-time and freshness rules apply to every
  row that supplies a source_date, UNVERIFIED rows included.
- Overlapping records for one symbol are contradictory, whatever their statuses.

Fail closed: any structural, provenance, contradiction or CSV parse problem raises EligibilityError and the whole
registry is unusable (no partial load). An invalid `accepted_methodologies` argument (a bare string, a non-string or
an empty/padded entry) is refused before the file is read. The loader never reads the wall clock. Purification,
dividend cleansing and short/derivative rules are out of scope.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import io
from pathlib import Path
import re
from types import MappingProxyType
from typing import Final, Iterable, Mapping

from config.day_universe import normalize_symbol

DEFAULT_REGISTRY_PATH: Final[Path] = Path(__file__).resolve().parent.parent / "config" / "sharia_eligibility.csv"
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "symbol", "status", "valid_from", "valid_until", "methodology", "source", "source_ref", "source_date",
    "reviewer", "reviewed_on", "note",
)
MAX_VALIDITY_DAYS: Final[int] = 92                 # inclusive calendar days covered by one record (quarterly re-screen)
MAX_SOURCE_AGE_DAYS: Final[int] = 92               # max (valid_from - source_date).days; stale screens are rejected
ACCEPTED_METHODOLOGIES: Final[frozenset[str]] = frozenset()   # owner-adopted; empty => no COMPLIANT row can load

_PROVENANCE = ("methodology", "source", "source_ref", "source_date")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BOM = b"\xef\xbb\xbf"


class EligibilityError(RuntimeError):
    """Registry missing, malformed, unsourced or contradictory, or an invalid query."""


class RecordStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    UNVERIFIED = "UNVERIFIED"


class Eligibility(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"


_DECIDED = {RecordStatus.COMPLIANT: (Eligibility.COMPLIANT, "recorded_compliant"),
            RecordStatus.NON_COMPLIANT: (Eligibility.NON_COMPLIANT, "recorded_non_compliant"),
            RecordStatus.UNVERIFIED: (Eligibility.UNVERIFIED, "recorded_unverified")}


@dataclass(frozen=True)
class EligibilityRecord:
    symbol: str
    status: RecordStatus
    valid_from: date
    valid_until: date
    methodology: str
    source: str
    source_ref: str
    source_date: date | None
    reviewer: str
    reviewed_on: date
    note: str
    line: int


@dataclass(frozen=True)
class EligibilityDecision:
    symbol: str
    day: date
    status: Eligibility
    reason: str
    record: EligibilityRecord | None

    @property
    def tradable(self) -> bool:
        return self.status is Eligibility.COMPLIANT


def _query_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be str, got {type(symbol).__name__}")
    sym = normalize_symbol(symbol)
    if not sym:
        raise EligibilityError("empty symbol")
    return sym


def _query_day(day: date) -> date:
    if isinstance(day, datetime) or not isinstance(day, date):
        raise TypeError(f"day must be a datetime.date (not datetime), got {type(day).__name__}")
    return day


@dataclass(frozen=True)
class EligibilityRegistry:
    records: Mapping[str, tuple[EligibilityRecord, ...]]      # per symbol, sorted by valid_from, non-overlapping
    source_path: str
    source_sha256: str                                         # SHA-256 of the CSV, BOM stripped, CRLF -> LF

    def decide(self, symbol: str, day: date) -> EligibilityDecision:
        sym, d = _query_symbol(symbol), _query_day(day)
        recs = self.records.get(sym, ())
        if not recs:
            return EligibilityDecision(sym, d, Eligibility.UNKNOWN, "no_record", None)
        for r in recs:
            if r.valid_from <= d <= r.valid_until:
                status, reason = _DECIDED[r.status]
                return EligibilityDecision(sym, d, status, reason, r)
        reason = "not_yet_valid" if d < recs[0].valid_from else "expired"
        return EligibilityDecision(sym, d, Eligibility.UNKNOWN, reason, None)

    def is_tradable(self, symbol: str, day: date) -> bool:
        return self.decide(symbol, day).tradable

    def filter_universe(self, symbols: Iterable[str], day: date
                        ) -> tuple[tuple[str, ...], dict[str, EligibilityDecision]]:
        """(tradable symbols in input order, decision for every input symbol). Duplicates are an error."""
        if isinstance(symbols, str):
            raise TypeError("symbols must be an iterable of str, not a single str")
        d = _query_day(day)
        decisions: dict[str, EligibilityDecision] = {}
        for s in symbols:
            sym = _query_symbol(s)
            if sym in decisions:
                raise EligibilityError(f"duplicate symbol in universe: {sym}")
            decisions[sym] = self.decide(sym, d)
        return tuple(s for s, dec in decisions.items() if dec.tradable), decisions


def _date(value: str, what: str, line: int) -> date:
    if not _ISO_DATE.match(value):
        raise EligibilityError(f"line {line}: invalid {what} {value!r} (expected YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise EligibilityError(f"line {line}: invalid {what} {value!r}") from None


def _record(row: dict[str, str], line: int, accepted: frozenset[str]) -> EligibilityRecord:
    raw_sym = row["symbol"]
    if not raw_sym.strip():
        raise EligibilityError(f"line {line}: empty symbol")
    if raw_sym != normalize_symbol(raw_sym):
        raise EligibilityError(f"line {line}: symbol {raw_sym!r} is not normalised (expected "
                               f"{normalize_symbol(raw_sym)!r})")
    v = {k: row[k].strip() for k in REQUIRED_COLUMNS if k != "symbol"}
    try:
        status = RecordStatus(v["status"])
    except ValueError:
        raise EligibilityError(f"line {line}: invalid status {v['status']!r}") from None
    valid_from = _date(v["valid_from"], "valid_from", line)
    valid_until = _date(v["valid_until"], "valid_until", line)
    if valid_from > valid_until:
        raise EligibilityError(f"line {line}: valid_from after valid_until")
    span = (valid_until - valid_from).days + 1
    if span > MAX_VALIDITY_DAYS:
        raise EligibilityError(f"line {line}: validity of {span} days exceeds {MAX_VALIDITY_DAYS}")
    if not v["reviewer"]:
        raise EligibilityError(f"line {line}: empty reviewer")
    reviewed_on = _date(v["reviewed_on"], "reviewed_on", line)
    if status is RecordStatus.UNVERIFIED and not v["note"]:
        raise EligibilityError(f"line {line}: UNVERIFIED row requires a note giving the reason")
    if status is not RecordStatus.UNVERIFIED:
        for k in _PROVENANCE:
            if not v[k]:
                raise EligibilityError(f"line {line}: {status.value} row requires {k}")
    source_date = _date(v["source_date"], "source_date", line) if v["source_date"] else None
    if source_date is not None:
        if source_date > valid_from:
            raise EligibilityError(f"line {line}: source_date {source_date} after valid_from {valid_from} "
                                   "(look-ahead)")
        age = (valid_from - source_date).days
        if age > MAX_SOURCE_AGE_DAYS:
            raise EligibilityError(f"line {line}: stale source: source_date {source_date} is {age} days before "
                                   f"valid_from {valid_from} (max {MAX_SOURCE_AGE_DAYS})")
        if reviewed_on < source_date:
            raise EligibilityError(f"line {line}: reviewed_on {reviewed_on} before source_date {source_date}")
    if status is RecordStatus.COMPLIANT and v["methodology"] not in accepted:
        raise EligibilityError(f"line {line}: methodology {v['methodology']!r} is not an accepted methodology")
    return EligibilityRecord(symbol=raw_sym, status=status, valid_from=valid_from, valid_until=valid_until,
                             methodology=v["methodology"], source=v["source"], source_ref=v["source_ref"],
                             source_date=source_date, reviewer=v["reviewer"], reviewed_on=reviewed_on,
                             note=v["note"], line=line)


def _accepted(methodologies: Iterable[str]) -> frozenset[str]:
    """Validated allowlist. A bare str would otherwise become a set of single letters (fail open)."""
    if isinstance(methodologies, (str, bytes)):
        raise TypeError("accepted_methodologies must be an iterable of methodology names, not a single string")
    try:
        items = list(methodologies)
    except TypeError:
        raise TypeError("accepted_methodologies must be an iterable of methodology names") from None
    for m in items:
        if not isinstance(m, str):
            raise TypeError(f"accepted methodology must be str, got {type(m).__name__}")
        if not m or m != m.strip():
            raise EligibilityError(f"invalid accepted methodology {m!r} (empty or padded)")
        if "DRAFT" in m.upper():
            raise EligibilityError(f"draft methodology {m!r} cannot be accepted (adopt a non-draft version first)")
    return frozenset(items)


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH, *,
                  accepted_methodologies: frozenset[str] = ACCEPTED_METHODOLOGIES) -> EligibilityRegistry:
    accepted = _accepted(accepted_methodologies)
    p = Path(path)
    if not p.is_file():
        raise EligibilityError(f"registry not found: {p}")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise EligibilityError(f"registry unreadable: {p}: {exc}") from None
    body = raw[len(_BOM):] if raw.startswith(_BOM) else raw
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise EligibilityError(f"registry is not valid UTF-8: {p}") from None
    sha = hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader, None)
        rows = [(reader.line_num, cells) for cells in reader]
    except csv.Error as exc:
        raise EligibilityError(f"line {reader.line_num}: CSV parse error in {p}: {exc}") from exc
    if header is None:
        raise EligibilityError(f"registry has no header: {p}")
    if len(set(header)) != len(header):
        raise EligibilityError(f"duplicate column in header: {header}")
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise EligibilityError(f"registry is missing columns {missing}")
    extra = [c for c in header if c not in REQUIRED_COLUMNS]
    if extra:
        raise EligibilityError(f"registry has unknown columns {extra}")

    by_symbol: dict[str, list[EligibilityRecord]] = {}
    for line, cells in rows:
        if len(cells) != len(header):
            raise EligibilityError(f"line {line}: expected {len(header)} fields, got {len(cells)}")
        rec = _record(dict(zip(header, cells)), line, accepted)
        by_symbol.setdefault(rec.symbol, []).append(rec)

    records: dict[str, tuple[EligibilityRecord, ...]] = {}
    for sym, recs in by_symbol.items():
        recs.sort(key=lambda r: (r.valid_from, r.line))
        for a, b in zip(recs, recs[1:]):
            if b.valid_from <= a.valid_until:
                raise EligibilityError(f"overlapping records for {sym}: lines {a.line}, {b.line}")
        records[sym] = tuple(recs)
    return EligibilityRegistry(records=MappingProxyType(records), source_path=str(p), source_sha256=sha)
