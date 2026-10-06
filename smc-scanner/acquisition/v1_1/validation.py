"""acquisition/v1_1/validation.py: structural checks for one symbol/session/interval unit (protocol v1.1 §17).

Counts and timestamps only; never price levels, returns or any strategy-relevant statistic.
Expected bars come from the exchange calendar (session open/close), never from a hard-coded 78/26.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from acquisition.contract import EXCHANGE_TZ
from acquisition.validation import expected_bar_opens
from acquisition.v1_1.contract import STORED_COLUMNS, STRATEGY_COLUMNS, bar_minutes
from acquisition.v1_1.sessions import V11Session


def split_rth(df: pd.DataFrame, session: V11Session) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(rows inside [session open, session close) ET on the session date, all other rows)."""
    if len(df) == 0:
        return df, df
    et = df.index.tz_convert(EXCHANGE_TZ)
    open_ts, close_ts = pd.Timestamp(session.open_et), pd.Timestamp(session.close_et)
    inside = (et >= open_ts) & (et < close_ts)
    return df[inside], df[~inside]


def unit_checks(df: pd.DataFrame, session: V11Session, interval: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Returns (canonical RTH frame, structural report) for one unit."""
    step = bar_minutes(interval)
    errors: list[str] = []
    rep: dict[str, Any] = {"session": session.session.isoformat(), "segment": session.segment,
                           "interval": interval, "returned_rows": int(len(df))}
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        rep.update(errors=["index is not a tz-aware DatetimeIndex"], passed=False)
        return df.iloc[0:0], rep
    rep["tz"] = str(df.index.tz)
    if rep["tz"] != "UTC":
        errors.append(f"index tz is {rep['tz']}, expected UTC")
    missing_cols = [c for c in STORED_COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"missing columns {missing_cols}")
    rep["adj_close_present"] = "adj_close" in df.columns
    if rep["adj_close_present"]:
        errors.append("unexpected adj_close column in v1.1 data")

    rth, ext = split_rth(df, session)
    rep["extended_rows"] = int(len(ext))
    grid = expected_bar_opens(session, interval)
    rep["expected_bars"] = int(len(grid))
    rep["early_close"] = session.early_close
    idx = rth.index
    rep["duplicate_timestamps"] = int(idx.duplicated().sum())
    if rep["duplicate_timestamps"]:
        errors.append("duplicate timestamps")
    rep["monotonic_increasing"] = bool(idx.is_monotonic_increasing)
    if not rep["monotonic_increasing"]:
        errors.append("timestamps not monotonic increasing")
    present = set(idx)
    gridset = set(grid)
    missing = [t for t in grid if t not in present]
    unexpected = sorted(t for t in present if t not in gridset)
    rep["present_bars"] = int(len(grid) - len(missing))
    rep["missing_bars"] = len(missing)
    rep["missing_bar_opens"] = [t.isoformat() for t in missing]
    rep["off_grid_bars"] = len(unexpected)
    rep["off_grid_bar_opens"] = [t.isoformat() for t in unexpected[:50]]
    if missing:
        errors.append(f"{len(missing)} missing bars")
    if unexpected:
        errors.append(f"{len(unexpected)} bars off the {step}-minute calendar grid")
    if len(idx):
        rep["first_bar_open_utc"] = idx.min().isoformat()
        rep["last_bar_open_utc"] = idx.max().isoformat()
    if not missing_cols and len(rth):
        cols = rth[list(STRATEGY_COLUMNS)]
        rep["nan_cells"] = int(cols.isna().sum().sum())
        if rep["nan_cells"]:
            errors.append("NaN in required fields")
        numeric = all(pd.api.types.is_numeric_dtype(cols[c]) for c in STRATEGY_COLUMNS)
        rep["numeric"] = numeric
        if not numeric:
            errors.append("non-numeric OHLCV")
        else:
            o, h, l, c, v = (cols[k] for k in STRATEGY_COLUMNS)
            bad = (h < l) | (h < o) | (h < c) | (l > o) | (l > c)
            rep["ohlc_inconsistent_rows"] = int(bad.sum())
            if rep["ohlc_inconsistent_rows"]:
                errors.append("OHLC inconsistent rows")
            rep["non_positive_price_rows"] = int((cols[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
            if rep["non_positive_price_rows"]:
                errors.append("non-positive prices")
            vv = v.dropna().to_numpy(dtype=np.float64)
            rep["negative_volume_rows"] = int((vv < 0).sum())
            rep["non_integer_volume_rows"] = int((vv != np.floor(vv)).sum())
            rep["zero_volume_rows"] = int((vv == 0).sum())
            if rep["negative_volume_rows"]:
                errors.append("negative volume")
            if rep["non_integer_volume_rows"]:
                errors.append("non-integer volume")
    rep["errors"] = errors
    rep["passed"] = not errors
    return rth, rep
