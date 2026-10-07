"""acquisition/capture_policy.py: frozen post-close capture wait (DAY-15A finalization, DECIDED).

market_close = 16:00 ET; capture_not_before = 16:15 ET on the session date (America/New_York).
The same fixed 16:15 ET applies on early-close days (conservative; independent of observed data).
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from acquisition.contract import EXCHANGE_TZ
from acquisition.sessions import OOSSession

MARKET_CLOSE_ET = time(16, 0)
CAPTURE_NOT_BEFORE_ET = time(16, 15)
_TZ = ZoneInfo(EXCHANGE_TZ)


class CaptureTooEarlyError(RuntimeError):
    """Capture attempted before the frozen post-close wait."""


def capture_allowed_at(session: OOSSession) -> datetime:
    return datetime.combine(session.session, CAPTURE_NOT_BEFORE_ET, tzinfo=_TZ)


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now


def is_capturable(session: OOSSession, now: datetime) -> bool:
    return _aware(now) >= capture_allowed_at(session)


def assert_capture_allowed(session: OOSSession, now: datetime) -> None:
    if not is_capturable(session, now):
        raise CaptureTooEarlyError(
            f"session {session.session} may not be captured before {capture_allowed_at(session).isoformat()}")


def capturable_sessions(sessions: list[OOSSession], now: datetime) -> list[OOSSession]:
    """Completed sessions only, in order; stops at the first session not yet capturable."""
    out = []
    for s in sessions:
        if not is_capturable(s, now):
            break
        out.append(s)
    return out
