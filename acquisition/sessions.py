"""acquisition/sessions.py: deterministic OOS session resolution (DAY-15A finalization).

Rule (DAY-14): first 60 NYSE sessions strictly after 2026-09-25.
Source: exchange_calendars XNYS (pinned in requirements.txt). Explicit calendar bounds are passed so
the result does not depend on the date the code runs. No market data is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from importlib import metadata

import pandas as pd

from acquisition.contract import EXCHANGE_TZ, OOS_RULE, OOS_SESSION_COUNT, RESEARCH_WINDOW_END

CALENDAR_PACKAGE = "exchange_calendars"
CALENDAR_NAME = "XNYS"
CALENDAR_START = "2026-01-02"
CALENDAR_END = "2027-12-31"


class CalendarUnavailableError(RuntimeError):
    """The approved NYSE calendar source cannot be loaded."""


@dataclass(frozen=True)
class OOSSession:
    index: int                 # 1-based position in the OOS session list
    session: date
    open_et: datetime
    close_et: datetime

    @property
    def early_close(self) -> bool:
        return (self.close_et.hour, self.close_et.minute) != (16, 0)


def calendar_info() -> dict[str, str]:
    try:
        version = metadata.version(CALENDAR_PACKAGE)
    except metadata.PackageNotFoundError as exc:
        raise CalendarUnavailableError(f"{CALENDAR_PACKAGE} is not installed") from exc
    return {"package": CALENDAR_PACKAGE, "version": version, "calendar": CALENDAR_NAME,
            "bounds": f"{CALENDAR_START}..{CALENDAR_END}", "session_timezone": EXCHANGE_TZ, "rule": OOS_RULE}


def resolve_oos_sessions(boundary: date = RESEARCH_WINDOW_END, count: int = OOS_SESSION_COUNT) -> list[OOSSession]:
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise CalendarUnavailableError(f"{CALENDAR_PACKAGE} is not installed") from exc
    cal = xcals.get_calendar(CALENDAR_NAME, start=CALENDAR_START, end=CALENDAR_END)
    after = pd.Timestamp(boundary) + pd.Timedelta(days=1)   # strictly after the boundary
    days = cal.sessions_in_range(after, pd.Timestamp(CALENDAR_END))[:count]
    if len(days) != count:
        raise CalendarUnavailableError(f"calendar returned {len(days)} sessions, expected {count}")
    out = []
    for i, d in enumerate(days, start=1):
        out.append(OOSSession(
            index=i, session=d.date(),
            open_et=cal.session_open(d).tz_convert(EXCHANGE_TZ).to_pydatetime(),
            close_et=cal.session_close(d).tz_convert(EXCHANGE_TZ).to_pydatetime(),
        ))
    return out
