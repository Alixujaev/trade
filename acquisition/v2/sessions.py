"""acquisition/v2/sessions.py: Stage R XNYS sessions and 1Day bar labels (protocol §3.3, DAY-17 Q1).

A 1Day bar is labelled 00:00 America/New_York of its session date (05:00Z in EST, 04:00Z in EDT).
No market data is read.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from acquisition.contract import EXCHANGE_TZ
from acquisition.sessions import CALENDAR_NAME, CalendarUnavailableError
from acquisition.v2.contract import STAGE_R_EXPECTED_SESSIONS, STAGE_R_FIRST_SESSION, STAGE_R_LAST_SESSION

CALENDAR_START = "2015-12-01"
CALENDAR_END = "2023-12-31"


class SessionResolutionError(RuntimeError):
    """The calendar did not resolve the frozen Stage R session set."""


def stage_r_sessions() -> list[date]:
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise CalendarUnavailableError("exchange_calendars is not installed") from exc
    cal = xcals.get_calendar(CALENDAR_NAME, start=CALENDAR_START, end=CALENDAR_END)
    days = cal.sessions_in_range(pd.Timestamp(STAGE_R_FIRST_SESSION), pd.Timestamp(STAGE_R_LAST_SESSION))
    out = [d.date() for d in days]
    if len(out) != STAGE_R_EXPECTED_SESSIONS or out[0] != STAGE_R_FIRST_SESSION or out[-1] != STAGE_R_LAST_SESSION:
        raise SessionResolutionError(f"Stage R resolved {len(out)} sessions ({out[:1]}..{out[-1:]}); "
                                     f"expected {STAGE_R_EXPECTED_SESSIONS} from {STAGE_R_FIRST_SESSION}")
    return out


def label_for(session: date) -> pd.Timestamp:
    """UTC timestamp of the 1Day bar label: 00:00 America/New_York on the session date."""
    return pd.Timestamp(session.isoformat()).tz_localize(EXCHANGE_TZ).tz_convert("UTC")


def session_of_label(ts: pd.Timestamp) -> tuple[date, bool]:
    """(New York calendar date of a bar label, whether the label is exactly 00:00 New York)."""
    ny = pd.Timestamp(ts).tz_convert(EXCHANGE_TZ)
    return ny.date(), (ny.hour, ny.minute, ny.second, ny.microsecond, ny.nanosecond) == (0, 0, 0, 0, 0)
