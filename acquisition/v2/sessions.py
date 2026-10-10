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


def stage_h_sessions() -> list[date]:
    """Stage H XNYS sessions 2021-01-04 .. 2026-06-02 (frozen §3.9); calendar rule only, no market data."""
    from acquisition.v2.contract import STAGE_H_EXPECTED_SESSIONS, STAGE_H_FIRST_SESSION, STAGE_H_LAST_SESSION
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise CalendarUnavailableError("exchange_calendars is not installed") from exc
    cal = xcals.get_calendar(CALENDAR_NAME, start="2020-12-01", end="2026-12-31")
    days = cal.sessions_in_range(pd.Timestamp(STAGE_H_FIRST_SESSION), pd.Timestamp(STAGE_H_LAST_SESSION))
    out = [d.date() for d in days]
    if len(out) != STAGE_H_EXPECTED_SESSIONS or out[0] != STAGE_H_FIRST_SESSION or out[-1] != STAGE_H_LAST_SESSION:
        raise SessionResolutionError(f"Stage H resolved {len(out)} sessions; expected {STAGE_H_EXPECTED_SESSIONS}")
    return out


def stage_f_sessions(last: date) -> list[date]:
    """Stage F XNYS sessions 2025-01-02 .. `last` (a protocol-2.1 forward segment's last session); calendar rule only."""
    from acquisition.v2.contract import FORWARD_SEGMENTS, STAGE_F_EXPECTED_SESSIONS, STAGE_F_FIRST_SESSION
    seg = next((k for k, v in FORWARD_SEGMENTS.items() if v[1] == last), None)
    if seg is None:
        raise SessionResolutionError(f"{last} is not the last session of a protocol-2.1 forward segment")
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise CalendarUnavailableError("exchange_calendars is not installed") from exc
    cal = xcals.get_calendar(CALENDAR_NAME, start="2024-12-01", end="2027-12-31")
    out = [d.date() for d in cal.sessions_in_range(pd.Timestamp(STAGE_F_FIRST_SESSION), pd.Timestamp(last))]
    if len(out) != STAGE_F_EXPECTED_SESSIONS[seg] or out[0] != STAGE_F_FIRST_SESSION or out[-1] != last:
        raise SessionResolutionError(f"Stage F ({seg}) resolved {len(out)} sessions; expected {STAGE_F_EXPECTED_SESSIONS[seg]}")
    return out


def label_for(session: date) -> pd.Timestamp:
    """UTC timestamp of the 1Day bar label: 00:00 America/New_York on the session date."""
    return pd.Timestamp(session.isoformat()).tz_localize(EXCHANGE_TZ).tz_convert("UTC")


def session_of_label(ts: pd.Timestamp) -> tuple[date, bool]:
    """(New York calendar date of a bar label, whether the label is exactly 00:00 New York)."""
    ny = pd.Timestamp(ts).tz_convert(EXCHANGE_TZ)
    return ny.date(), (ny.hour, ny.minute, ny.second, ny.microsecond, ny.nanosecond) == (0, 0, 0, 0, 0)
