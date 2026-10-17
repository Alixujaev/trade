"""acquisition/akinda/normalize.py: one Akinda /compliance payload -> one proposed registry row (pure, no I/O).

Mapping (owner decision D13-A):
- HALAL with a usable, fresh last_scanned       -> COMPLIANT (methodology AKINDA_COMPLIANCE_API_V1)
- NOT HALAL with a usable, fresh last_scanned   -> NON_COMPLIANT
- DOUBTFUL / UNQUALIFIED / ERROR_DATA / INCOMPLETE_DATA, any unrecognised status, or HALAL / NOT HALAL whose
  last_scanned is null, unparseable, after retrieval or older than MAX_SOURCE_AGE_DAYS -> UNVERIFIED (not tradable)
- not a JSON object, a missing documented field, a wrong-type field or a ticker echo that differs from the request
  -> no record at all (diagnostic only).

source_date is the vendor's last_scanned (screening date), never the retrieval time and never last_updated.
valid_from = reviewed_on = the retrieval date (America/New_York), so no record covers a session before retrieval.
valid_until = valid_from + valid_days - 1, where valid_days is an explicit operator choice (1..MAX_VALIDITY_DAYS),
capped at source_date + MAX_SOURCE_AGE_DAYS so the record expires when the screening reaches the maximum age
(the registry rejects a record that outlives its source).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from acquisition.akinda.contract import (
    LAST_SCANNED_FORMAT,
    NO_VERDICT_STATUSES,
    REQUIRED_FIELDS,
    REVIEWER,
    SOURCE,
    STATUS_HALAL,
    STATUS_NOT_HALAL,
)
from screening.eligibility import AKINDA_COMPLIANCE_METHODOLOGY, MAX_SOURCE_AGE_DAYS, MAX_VALIDITY_DAYS


@dataclass(frozen=True)
class Normalized:
    ticker: str
    row: dict[str, str] | None                  # None -> no record for this ticker
    halal_status_raw: Any
    last_scanned_raw: Any
    last_updated_raw: Any
    diagnostic: str


def _safe(value: Any) -> str:
    """Short, single-line, comma-free rendering of a vendor value for notes."""
    s = repr(value)[:40]
    return "".join(c if c.isprintable() and c != "," else "?" for c in s)


def _screening_date(raw: Any, retrieved_on: date) -> tuple[date | None, str]:
    if raw is None:
        return None, "last_scanned is null (never audited)"
    try:
        scanned = datetime.strptime(raw, LAST_SCANNED_FORMAT).date()
    except ValueError:
        return None, f"unparseable last_scanned {_safe(raw)}"
    if scanned > retrieved_on:
        return None, f"last_scanned {scanned} is after retrieval {retrieved_on}"
    age = (retrieved_on - scanned).days
    if age > MAX_SOURCE_AGE_DAYS:
        return None, f"stale: last_scanned {scanned} is {age} days old (max {MAX_SOURCE_AGE_DAYS})"
    return scanned, ""


def normalize(ticker: str, payload: Any, *, retrieved_on: date, valid_days: int, source_ref: str) -> Normalized:
    if isinstance(valid_days, bool) or not isinstance(valid_days, int) or not 1 <= valid_days <= MAX_VALIDITY_DAYS:
        raise ValueError(f"valid_days must be an int in 1..{MAX_VALIDITY_DAYS}, got {valid_days!r}")

    def none(why: str) -> Normalized:
        get = payload.get if isinstance(payload, dict) else (lambda _k: None)
        return Normalized(ticker, None, get("halal_status"), get("last_scanned"), get("last_updated"), why)

    if not isinstance(payload, dict):
        return none("malformed: not a JSON object")
    for f in REQUIRED_FIELDS:
        if f not in payload:
            return none(f"malformed: missing field {f}")
    if payload["ticker"] != ticker:
        return none(f"contradictory: ticker echo {_safe(payload['ticker'])} != requested {ticker}")
    status, scanned_raw = payload["halal_status"], payload["last_scanned"]
    if not isinstance(status, str):
        return none("malformed: halal_status is not a string")
    if scanned_raw is not None and not isinstance(scanned_raw, str):
        return none("malformed: last_scanned is not a string or null")

    scanned, date_problem = _screening_date(scanned_raw, retrieved_on)
    if status in (STATUS_HALAL, STATUS_NOT_HALAL) and scanned is not None:
        rec_status = "COMPLIANT" if status == STATUS_HALAL else "NON_COMPLIANT"
        note, diagnostic = f"Akinda halal_status {status}", ""
    else:
        rec_status = "UNVERIFIED"
        if status in (STATUS_HALAL, STATUS_NOT_HALAL):
            diagnostic = f"Akinda {status} not usable: {date_problem}"
        elif status in NO_VERDICT_STATUSES:
            diagnostic = f"Akinda halal_status {status} (no tradable verdict)"
        else:
            diagnostic = f"unrecognised halal_status {_safe(status)}"
        note = diagnostic
        scanned = None                                   # an unusable date is never written as source_date

    valid_until = retrieved_on + timedelta(days=valid_days - 1)
    if scanned is not None:
        valid_until = min(valid_until, scanned + timedelta(days=MAX_SOURCE_AGE_DAYS))
    row = {"symbol": ticker, "status": rec_status, "valid_from": retrieved_on.isoformat(),
           "valid_until": valid_until.isoformat(),
           "methodology": AKINDA_COMPLIANCE_METHODOLOGY, "source": SOURCE, "source_ref": source_ref,
           "source_date": scanned.isoformat() if scanned else "", "reviewer": REVIEWER,
           "reviewed_on": retrieved_on.isoformat(), "note": note}
    return Normalized(ticker, row, status, scanned_raw, payload.get("last_updated"), diagnostic)
