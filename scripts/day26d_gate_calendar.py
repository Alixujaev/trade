"""scripts/day26d_gate_calendar.py: deterministic XNYS declaration of the protocol 2.2 gate fwd-gate2 (offline).

    python -m scripts.day26d_gate_calendar

Calendar facts only (pinned exchange_calendars XNYS; no market data, no network). Declares, before any gate data
exists: the 42 sessions (first session = first XNYS session after the DAY-26D commit day 2026-10-10), the decision
closes (§8.14 initial decision on the session before the segment, then the last session of each calendar month), the
fill sessions (market-on-open t+1), the closes each V2-MOM ranking reads (TR(t-21), TR(t-252); bar t itself is not
used), the final session, the Stage F range and lookback count, and the earliest capture / evaluation time
(16:15 America/New_York on the final session, capture_policy). The exposed sessions 2026-10-08/09 (DAY-26C) are
checked to lie outside the sample.
"""

from __future__ import annotations

from datetime import date, datetime, time
import json
import sys
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.day26b_forward_calendar import CALENDAR_VERSION, _cal, _capture, _iso

COMMIT_DAY = date(2026, 10, 10)                  # DAY-26D commit day (a Saturday)
SESSIONS = 42
STAGE_F_FIRST = date(2025, 1, 2)
EXPOSED = (date(2026, 10, 8), date(2026, 10, 9))
MOM_SKIP, MOM_LOOKBACK = 21, 252                 # frozen V2-MOM signal TR(t-21)/TR(t-252) - 1


def compute() -> dict:
    cal = _cal()
    first = cal.date_to_session(pd.Timestamp(COMMIT_DAY) + pd.Timedelta(days=1), "next")   # strictly after the commit day
    sample = cal.sessions_in_range(first, pd.Timestamp("2027-12-31"))[:SESSIONS]
    last = sample[-1]
    history = cal.sessions_in_range(pd.Timestamp(STAGE_F_FIRST), last)           # Stage F session index
    pos = {d: i for i, d in enumerate(history)}
    month_ends = [d for d in sample[:-1] if cal.next_session(d).month != d.month]
    decisions = [cal.previous_session(first)] + month_ends
    rows = []
    for t in decisions:
        i = pos[t]
        rows.append({"decision_close": _iso(t), "fill_open": _iso(cal.next_session(t)),
                     "ranking_reads_close_t_minus_21": _iso(history[i - MOM_SKIP]),
                     "ranking_reads_close_t_minus_252": _iso(history[i - MOM_LOOKBACK]),
                     "kind": "initial (§8.14)" if t == decisions[0] else "month-end rebalance"})
    sample_iso = [_iso(d) for d in sample]
    return {"calendar": f"exchange_calendars {CALENDAR_VERSION} XNYS", "segment": "fwd-gate2",
            "commit_day": COMMIT_DAY.isoformat(), "first_session": sample_iso[0], "last_session": _iso(last),
            "count": len(sample), "sessions": sample_iso,
            "exposed_sessions_excluded": [d.isoformat() for d in EXPOSED],
            "exposed_in_sample": sorted(set(sample_iso) & {d.isoformat() for d in EXPOSED}),
            "first_ranking_close": rows[0]["decision_close"], "first_fill_open": rows[0]["fill_open"],
            "decisions": rows, "liquidation_close": _iso(last),
            "stage_f_range": [STAGE_F_FIRST.isoformat(), _iso(last)], "stage_f_sessions": len(history),
            "inputs_before": len(history) - len(sample),
            "weekday_holidays_in_sample": [_iso(d) for d in pd.bdate_range(sample[0], last) if d not in sample],
            "early_closes_in_sample": {_iso(d): cal.closes[d].tz_convert(ZoneInfo("America/New_York")).strftime("%H:%M")
                                       for d in sample
                                       if cal.closes[d].tz_convert(ZoneInfo("America/New_York")).time() < time(16, 0)},
            "earliest_capture": _capture(last.date()),
            "earliest_final_evaluation": "after a successful Stage F capture and READY_FOR_FORWARD_EVALUATION validation, "
                                         "not before " + _capture(last.date())["local"]}


def main() -> int:
    json.dump(compute(), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
