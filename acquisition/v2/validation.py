"""acquisition/v2/validation.py: Stage R daily-bar structural checks (protocol §3.8, DAY-17 §9.4).

HARD_FAIL: bad label (not 00:00 New York), off-calendar / pre-start / post-end row, duplicate session,
non-monotonic or naive index, OHLC inconsistency, non-positive price, NaN, negative volume, raw/all session-set
mismatch. BLOCKING: first bar later than 2016-01-04 + 5 sessions; missing > 2 % of research-segment sessions.
Missing sessions are listed, never imputed. Values are never reported, only counts/dates/flags.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from acquisition.v2.contract import FIRST_BAR_MAX_LAG_SESSIONS, MISSING_SESSION_REVIEW_FRACTION
from acquisition.v2.sessions import session_of_label

RESEARCH_FIRST_SESSION = date(2017, 2, 1)   # protocol §3.6 (evaluated segment inside Stage R)


def check_series(df: pd.DataFrame, sessions: list[date], segment_first: date = RESEARCH_FIRST_SESSION) -> dict[str, Any]:
    """segment_first: first session of the evaluated segment for the 2 % rule (Research by default; Stage H passes
    the holdout's first session)."""
    hard: list[str] = []
    blocking: list[str] = []
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None:
        return {"status": "HARD_FAIL", "hard_fail": ["index not tz-aware DatetimeIndex"], "blocking": []}
    if not idx.is_monotonic_increasing:
        hard.append("index not monotonic increasing")
    if idx.has_duplicates:
        hard.append("duplicate timestamps")
    sset = set(sessions)
    first, last = sessions[0], sessions[-1]
    dates: list[date] = []
    bad_labels = off_cal = pre = post = 0
    for ts in idx:
        d, midnight = session_of_label(ts)
        if not midnight:
            bad_labels += 1
        if d < first:
            pre += 1
        elif d > last:
            post += 1
        elif d not in sset:
            off_cal += 1
        dates.append(d)
    for name, n in (("label_not_ny_midnight", bad_labels), ("rows_before_stage_r", pre),
                    ("rows_after_stage_r", post), ("off_calendar_rows", off_cal)):
        if n:
            hard.append(f"{name}={n}")
    if len(dates) != len(set(dates)):
        hard.append("duplicate session dates")
    o, h, l, c, v = (df[k].to_numpy(dtype=np.float64) for k in ("open", "high", "low", "close", "volume"))
    nan_rows = int(np.isnan(np.vstack([o, h, l, c, v])).any(axis=0).sum())
    nonpos = int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum())
    ohlc_bad = int(((l > np.minimum(o, c)) | (h < np.maximum(o, c)) | (l > h)).sum())
    neg_vol = int((v < 0).sum())
    for name, n in (("nan_rows", nan_rows), ("non_positive_price_rows", nonpos), ("ohlc_inconsistent_rows", ohlc_bad),
                    ("negative_volume_rows", neg_vol)):
        if n:
            hard.append(f"{name}={n}")
    present = set(dates) & sset
    missing = sorted(sset - present)
    research = [s for s in sessions if s >= segment_first]
    research_missing = [s for s in missing if s >= segment_first]
    frac = len(research_missing) / len(research) if research else 0.0
    if frac > MISSING_SESSION_REVIEW_FRACTION:
        seg = "research-segment" if segment_first == RESEARCH_FIRST_SESSION else "evaluated-segment"
        blocking.append(f"{seg} missing fraction {len(research_missing)}/{len(research)} > 2%")
    first_bar = min(present) if present else None
    if first_bar is None or first_bar > sessions[FIRST_BAR_MAX_LAG_SESSIONS]:
        blocking.append(f"first bar {first_bar} later than {sessions[FIRST_BAR_MAX_LAG_SESSIONS]}")
    status = "HARD_FAIL" if hard else ("BLOCKING" if blocking else "OK")
    return {"status": status, "hard_fail": hard, "blocking": blocking, "rows": int(len(df)),
            "sessions_expected": len(sessions), "sessions_present": len(present),
            "missing_sessions": [m.isoformat() for m in missing], "research_missing_count": len(research_missing),
            "zero_volume_rows": int((v == 0).sum()), "first_bar": first_bar.isoformat() if first_bar else None,
            "last_bar": max(present).isoformat() if present else None,
            "session_dates": sorted(d.isoformat() for d in present)}


def check_raw_all(raw: dict[str, Any], adj: dict[str, Any]) -> dict[str, Any]:
    equal = raw.get("session_dates") == adj.get("session_dates")
    return {"session_sets_equal": equal, "status": "OK" if equal else "HARD_FAIL"}
