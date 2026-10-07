"""acquisition/validation.py: structural checks only (DAY-14 data-expansion-spec §5).

Reports counts and flags. It never reports price levels, returns, ranges or any statistic
that could inform a strategy (that would count as OOS inspection).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from acquisition.contract import EXCHANGE_TZ, FULL_SESSION_BARS, RTH_END, RTH_START, STORED_COLUMNS, validate_interval


def structural_checks(df: pd.DataFrame, interval: str) -> dict[str, Any]:
    step = validate_interval(interval)
    errors: list[str] = []
    rep: dict[str, Any] = {"interval": interval, "row_count": int(len(df))}

    missing_cols = [c for c in STORED_COLUMNS if c not in df.columns]
    rep["missing_columns"] = missing_cols
    if missing_cols:
        errors.append(f"missing columns {missing_cols}")
    if not isinstance(df.index, pd.DatetimeIndex):
        rep["errors"] = errors + ["index is not a DatetimeIndex"]
        rep["passed"] = False
        return rep

    idx = df.index
    rep["tz_aware"] = idx.tz is not None
    rep["tz"] = str(idx.tz) if idx.tz is not None else None
    if idx.tz is None:
        errors.append("index is tz-naive")
    elif rep["tz"] != "UTC":
        errors.append(f"index tz is {rep['tz']}, expected UTC")
    rep["first_timestamp"] = idx[0].isoformat() if len(idx) else None
    rep["last_timestamp"] = idx[-1].isoformat() if len(idx) else None

    rep["duplicate_timestamps"] = int(idx.duplicated().sum())
    if rep["duplicate_timestamps"]:
        errors.append("duplicate timestamps")
    rep["monotonic_increasing"] = bool(idx.is_monotonic_increasing)
    if not rep["monotonic_increasing"]:
        errors.append("timestamps not monotonic increasing")

    if not missing_cols:
        cols = df[list(STORED_COLUMNS)]
        rep["nan_cells"] = int(cols.isna().sum().sum())
        if rep["nan_cells"]:
            errors.append("NaN values present")
        o, h, l, c, v = (cols[k] for k in ("open", "high", "low", "close", "volume"))
        bad = (h < l) | (h < o) | (h < c) | (l > o) | (l > c)
        rep["ohlc_inconsistent_rows"] = int(bad.sum())
        if rep["ohlc_inconsistent_rows"]:
            errors.append("OHLC inconsistent rows")
        rep["non_positive_price_rows"] = int(((cols[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        if rep["non_positive_price_rows"]:
            errors.append("non-positive prices")
        rep["negative_volume_rows"] = int((v < 0).sum())
        if rep["negative_volume_rows"]:
            errors.append("negative volume")
        rep["zero_volume_rows"] = int((v == 0).sum())
        # Adjustment evidence only (boolean/count), no price values reported.
        rep["adj_close_differs_rows"] = int((cols["adj_close"] != c).sum())
        rep["adj_close_equals_close_all_rows"] = rep["adj_close_differs_rows"] == 0

    if idx.tz is not None and len(idx):
        et = idx.tz_convert(EXCHANGE_TZ)
        rep["off_grid_bars"] = int(((et.minute % step) != 0).sum() + (et.second != 0).sum())
        if rep["off_grid_bars"]:
            errors.append("bars not aligned to interval grid")
        t = pd.Series(et.time, index=idx)
        outside = ~t.map(lambda x: RTH_START <= x < RTH_END)
        rep["non_rth_bars"] = int(outside.sum())
        if rep["non_rth_bars"]:
            errors.append("bars outside RTH 09:30-16:00 ET")
        sessions = pd.Series(et.date, index=idx)
        counts = sessions.groupby(sessions.values).size()
        full = FULL_SESSION_BARS[interval]
        rep["session_count"] = int(len(counts))
        rep["sessions"] = [str(d) for d in counts.index]
        rep["bars_per_session"] = {str(d): int(n) for d, n in counts.items()}
        # Early closes cannot be classified without an NYSE calendar (UNRESOLVED) -> flag, do not judge.
        rep["sessions_not_full_length"] = [str(d) for d, n in counts.items() if n != full]
        rep["sessions_not_full_length_note"] = (
            f"expected {full} bars for a full session; deviations need an NYSE calendar to distinguish "
            "early closes from missing bars (calendar UNRESOLVED)"
        )
        diffs = pd.Series(et).groupby(sessions.values).diff().dropna()
        rep["intra_session_gaps"] = int((diffs != pd.Timedelta(minutes=step)).sum()) if len(diffs) else 0

    rep["errors"] = errors
    rep["passed"] = not errors
    return rep


def expected_bar_opens(session, interval: str) -> pd.DatetimeIndex:
    """Expected bar-open grid of one calendar session (UTC): open, open+step, ... < close."""
    step = validate_interval(interval)
    opens = pd.date_range(pd.Timestamp(session.open_et), pd.Timestamp(session.close_et), freq=f"{step}min",
                          inclusive="left")
    return opens.tz_convert("UTC")


def calendar_coverage(df: pd.DataFrame, interval: str, expected_sessions) -> dict[str, Any]:
    """Structural coverage against the frozen calendar: counts and timestamps only, no prices."""
    expected = {s.session: expected_bar_opens(s, interval) for s in expected_sessions}
    idx = df.index.tz_convert("UTC") if df.index.tz is not None else df.index
    present = set(idx)
    per_session = {}
    missing_total = 0
    for d, grid in expected.items():
        missing = [t for t in grid if t not in present]
        missing_total += len(missing)
        per_session[str(d)] = {"expected_bars": int(len(grid)), "present_bars": int(len(grid) - len(missing)),
                               "missing_bar_opens": [t.isoformat() for t in missing]}
    all_expected = set().union(*expected.values()) if expected else set()
    unexpected = sorted(t for t in present if t not in all_expected)
    sessions_missing = [d for d, v in per_session.items() if v["present_bars"] == 0]
    return {
        "interval": interval,
        "expected_sessions": len(expected),
        "sessions_with_data": len(expected) - len(sessions_missing),
        "sessions_missing": sessions_missing,
        "sessions_incomplete": [d for d, v in per_session.items() if 0 < v["present_bars"] < v["expected_bars"]],
        "expected_bars": int(sum(len(g) for g in expected.values())),
        "present_expected_bars": int(sum(v["present_bars"] for v in per_session.values())),
        "missing_bars": int(missing_total),
        "bars_outside_expected_grid": len(unexpected),
        "bars_outside_expected_grid_sample": [t.isoformat() for t in unexpected[:50]],
        "early_close_sessions": [str(s.session) for s in expected_sessions if s.early_close],
        "per_session": per_session,
        "complete": missing_total == 0 and not unexpected,
    }
