"""scripts/day26b_forward_calendar.py: deterministic XNYS calendar for the DAY-26B protocol 2.1 draft (offline).

    python -m scripts.day26b_forward_calendar

Derives, from the pinned `exchange_calendars` XNYS schedule only (calendar facts, no market data), the 63-session
forward window starting 2026-10-08: the 21-session diagnostic segment (fwd-diag), the 42-session blind gating segment
(fwd-gate), month-end decision closes, holidays and early closes inside the window, the Stage F lookback session counts
(§3.9: Stage F starts 2025-01-02) and the earliest permitted Stage F capture times (16:15 America/New_York,
`capture_policy`). Prints JSON. Nothing is read from or written to disk, and no network is used.
"""

from __future__ import annotations

from datetime import date, datetime, time
import json
import sys
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

CALENDAR_VERSION = "4.13.2"                     # protocol pin (DAY-16 §3.2 / DAY-22 §4)
FORWARD_START = date(2026, 10, 8)               # DAY-16 §3.6: first session after the freeze-commit date; DAY-22 §3.1
STAGE_F_FIRST = date(2025, 1, 2)                # DAY-16 §3.9 Stage F range start
TOTAL, DIAG = 63, 21                            # DAY-26B design: 63 sessions = 21 diagnostic + 42 gating
CAPTURE_LOCAL = time(16, 15)                    # capture_policy: no capture before 16:15 ET
MARKET_TZ = ZoneInfo("America/New_York")
_BOUNDS = ("2024-01-01", "2027-12-31")          # explicit: the default calendar horizon is "today + 1 year"


def _cal():
    if xcals.__version__ != CALENDAR_VERSION:
        raise SystemExit(f"exchange_calendars {xcals.__version__} != pinned {CALENDAR_VERSION}")
    return xcals.get_calendar("XNYS", start=_BOUNDS[0], end=_BOUNDS[1])


def _iso(ts) -> str:
    return pd.Timestamp(ts).date().isoformat()


def _capture(day: date) -> dict:
    local = datetime.combine(day, CAPTURE_LOCAL, tzinfo=MARKET_TZ)
    return {"local": local.isoformat(), "utc": local.astimezone(ZoneInfo("UTC")).isoformat(), "tz": "America/New_York",
            "utc_offset": local.strftime("%z")}


def compute() -> dict:
    cal = _cal()
    sessions = cal.sessions_in_range(pd.Timestamp(FORWARD_START), pd.Timestamp(_BOUNDS[1]))[:TOTAL]
    if len(sessions) != TOTAL or sessions[0].date() != FORWARD_START:
        raise SystemExit("forward window could not be resolved")
    diag, gate = sessions[:DIAG], sessions[DIAG:]

    def month_ends(seg) -> list[str]:          # last XNYS session of its calendar month (decision close, §4)
        return [_iso(d) for d in seg if cal.next_session(d).month != d.month]

    def segment(seg, first_no: int) -> dict:
        first, last = seg[0], seg[-1]
        lookback = cal.sessions_in_range(pd.Timestamp(STAGE_F_FIRST), cal.previous_session(first))
        return {"session_numbers": [first_no, first_no + len(seg) - 1], "count": len(seg),
                "first": _iso(first), "last": _iso(last), "sessions": [_iso(d) for d in seg],
                "initial_decision_close": _iso(cal.previous_session(first)),         # §8.14: session before the segment
                "month_end_decision_closes": [d for d in month_ends(seg) if d != _iso(last)],
                "rebalance_executions": [_iso(cal.next_session(d)) for d in month_ends(seg) if d != _iso(last)],
                "liquidation_close": _iso(last),
                "inputs_before_from_stage_f_start": len(lookback),
                "stage_f_range": [STAGE_F_FIRST.isoformat(), _iso(last)],
                "earliest_stage_f_capture": _capture(last.date())}

    weekdays = pd.bdate_range(sessions[0], sessions[-1])
    early = [_iso(d) for d in sessions if cal.closes[d].tz_convert(MARKET_TZ).time() < time(16, 0)]
    return {"calendar": f"exchange_calendars {CALENDAR_VERSION} XNYS", "forward_start": FORWARD_START.isoformat(),
            "total": {"count": TOTAL, "first": _iso(sessions[0]), "last": _iso(sessions[-1])},
            "fwd_diag": segment(diag, 1), "fwd_gate": segment(gate, DIAG + 1),
            "weekday_holidays_in_window": [_iso(d) for d in weekdays if d not in sessions],
            "early_closes_in_window": {d: cal.closes[pd.Timestamp(d)].tz_convert(MARKET_TZ).strftime("%H:%M")
                                       for d in early}}


def main() -> int:
    json.dump(compute(), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
