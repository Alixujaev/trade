"""backtest/session_gate.py: DAY-10 H3 — per-session actual-entry frequency gate.

Semantics:
- One gate per symbol backtest run, so symbols never share a count.
- The count is keyed by RTH session date and starts at 0 for every new session (no overnight state).
- Only ACTUAL entries are recorded (record_entry after a trade is opened). Signals skipped by
  the existing engine (position open, insufficient data) never touch the count.
- allows() only looks at entries already recorded, i.e. entries executed before the current
  signal. It never knows how many trades a session will have in total (no look-ahead).
- max_trades_per_session=None means no cap (baseline behaviour).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import datetime

import pandas as pd

from data.session import to_eastern


@dataclass(frozen=True)
class EntryWindow:
    """DAY-11 H5: half-open ET window [start, end) for the ENTRY bar's open timestamp.

    The gate only decides whether a NEW position may open; it never closes or modifies an
    existing position. It depends only on the entry timestamp and this fixed configuration.
    """

    name: str
    start: datetime.time
    end: datetime.time

    def allows(self, entry_ts: pd.Timestamp) -> bool:
        t = to_eastern(pd.Timestamp(entry_ts)).time()
        return self.start <= t < self.end

    def describe(self) -> str:
        return f"[{self.start:%H:%M}, {self.end:%H:%M}) ET"


# Pre-declared DAY-11 variants (fixed before results). FULL = existing semantics (any RTH entry bar).
ENTRY_WINDOWS: tuple[EntryWindow, ...] = (
    EntryWindow("FULL", datetime.time(9, 30), datetime.time(16, 0)),
    EntryWindow("MORNING", datetime.time(9, 30), datetime.time(11, 0)),
    EntryWindow("MORNING_EXT", datetime.time(9, 30), datetime.time(12, 0)),
    EntryWindow("EARLY_DAY", datetime.time(9, 30), datetime.time(13, 0)),
    EntryWindow("NO_LATE", datetime.time(9, 30), datetime.time(14, 0)),
)


class SessionEntryGate:
    def __init__(self, max_trades_per_session: int | None = None) -> None:
        if max_trades_per_session is not None and max_trades_per_session < 1:
            raise ValueError(f"max_trades_per_session must be >= 1 or None, got {max_trades_per_session!r}")
        self.max_trades_per_session = max_trades_per_session
        self._entries: dict[datetime.date, int] = defaultdict(int)

    def allows(self, session: datetime.date) -> bool:
        if self.max_trades_per_session is None:
            return True
        return self._entries[session] < self.max_trades_per_session

    def record_entry(self, session: datetime.date) -> None:
        self._entries[session] += 1

    def entries(self, session: datetime.date) -> int:
        return self._entries[session]
