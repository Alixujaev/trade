"""acquisition/v1_1/sessions.py: deterministic v1.1 calendar segments (protocol-v1.1.md §3).

S = XNYS sessions; research = S in [2026-07-02, 2026-09-25]; warmup = the 20 sessions before it;
P = S strictly after 2026-09-25; embargo = P[0]; stage1 = P[1:21]; stage2 = P[21:61].
No market data is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from acquisition.contract import EXCHANGE_TZ
from acquisition.sessions import CALENDAR_END, CALENDAR_NAME, CALENDAR_START, CalendarUnavailableError
from acquisition.v1_1.contract import (
    DAY15G_LAST_SESSION, EMBARGO_SESSIONS, FIRST_OOS_SESSION, RESEARCH_FIRST_SESSION, RESEARCH_LAST_SESSION,
    STAGE1_SESSIONS, STAGE2_SESSIONS, WARMUP_SESSIONS,
)

SEGMENTS = ("warmup", "research", "embargo", "stage1", "stage2")
RESEARCH_ACQUISITION_SEGMENTS = ("warmup", "research", "embargo")


class OOSRequestRejected(RuntimeError):
    """DAY-15G may not request any session on or after the first OOS session."""


@dataclass(frozen=True)
class V11Session:
    index: int               # 1-based position over all v1.1 segments, chronological
    session: date
    open_et: datetime
    close_et: datetime
    segment: str

    @property
    def early_close(self) -> bool:
        return (self.close_et.hour, self.close_et.minute) != (16, 0)


def resolve_v11_sessions() -> list[V11Session]:
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise CalendarUnavailableError("exchange_calendars is not installed") from exc
    cal = xcals.get_calendar(CALENDAR_NAME, start=CALENDAR_START, end=CALENDAR_END)
    sessions = cal.sessions
    before = sessions[sessions < pd.Timestamp(RESEARCH_FIRST_SESSION)]
    research = sessions[(sessions >= pd.Timestamp(RESEARCH_FIRST_SESSION)) & (sessions <= pd.Timestamp(RESEARCH_LAST_SESSION))]
    after = sessions[sessions > pd.Timestamp(RESEARCH_LAST_SESSION)]
    e, s1 = EMBARGO_SESSIONS, EMBARGO_SESSIONS + STAGE1_SESSIONS
    s2 = s1 + STAGE2_SESSIONS
    parts = [("warmup", before[-WARMUP_SESSIONS:]), ("research", research), ("embargo", after[:e]),
             ("stage1", after[e:s1]), ("stage2", after[s1:s2])]
    expected = {"warmup": WARMUP_SESSIONS, "research": 60, "embargo": EMBARGO_SESSIONS,
                "stage1": STAGE1_SESSIONS, "stage2": STAGE2_SESSIONS}
    out: list[V11Session] = []
    for name, days in parts:
        if len(days) != expected[name]:
            raise CalendarUnavailableError(f"segment {name}: {len(days)} sessions, expected {expected[name]}")
        for d in days:
            out.append(V11Session(
                index=len(out) + 1, session=d.date(), segment=name,
                open_et=cal.session_open(d).tz_convert(EXCHANGE_TZ).to_pydatetime(),
                close_et=cal.session_close(d).tz_convert(EXCHANGE_TZ).to_pydatetime(),
            ))
    return out


def segment(sessions: list[V11Session], name: str) -> list[V11Session]:
    if name not in SEGMENTS:
        raise ValueError(f"unknown segment {name!r}")
    return [s for s in sessions if s.segment == name]


def assert_not_oos(session_date: date) -> None:
    """Hard DAY-15G guard: reject any session on or after the first OOS session."""
    if session_date >= FIRST_OOS_SESSION or session_date > DAY15G_LAST_SESSION:
        raise OOSRequestRejected(
            f"session {session_date} is OOS (>= {FIRST_OOS_SESSION}); DAY-15G may not request it")


def research_acquisition_sessions(sessions: list[V11Session] | None = None) -> list[V11Session]:
    """Warmup + research + embargo (81 sessions), chronological. Every session passes the OOS guard."""
    if sessions is None:
        sessions = [s for s in resolve_v11_sessions() if s.segment in RESEARCH_ACQUISITION_SEGMENTS]
    for s in sessions:   # an explicitly passed OOS session is rejected, never silently dropped
        assert_not_oos(s.session)
        if s.segment not in RESEARCH_ACQUISITION_SEGMENTS:
            raise OOSRequestRejected(f"session {s.session} has segment {s.segment!r}; DAY-15G may not request it")
    return list(sessions)
