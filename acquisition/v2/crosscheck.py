"""acquisition/v2/crosscheck.py: raw/all implied-factor cross-check (protocol §3.4, frozen tolerances).

f(k) = C_raw(k) / C_all(k) on sessions present in both series. A change exists at k (previous common session p)
where |f(k)/f(p) - 1| > 1e-6. Every change must coincide with >= 1 retained split/dividend event whose ex_date
is in (p, k], and every such event must coincide with a change. Split magnitude: f(p)/f(k) must equal the
product of q within 0.1 % (sessions carrying only split events). Mismatches are BLOCKING data reviews.
This is an audit of data completeness; no factor value, price or return is written - only dates, counts, flags.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from acquisition.v2.contract import FACTOR_CHANGE_REL_TOL, SPLIT_RATIO_REL_TOL


def crosscheck_symbol(raw_close: pd.Series, all_close: pd.Series, events: list[dict[str, Any]]) -> dict[str, Any]:
    """raw_close/all_close: indexed by session date (datetime.date), strictly the acquired rows."""
    common = sorted(set(raw_close.index) & set(all_close.index))
    out: dict[str, Any] = {"common_sessions": len(common)}
    if len(common) < 2:
        out.update(status="BLOCKING", reason="fewer than two common sessions")
        return out
    r = raw_close.reindex(common).to_numpy(dtype=np.float64)
    a = all_close.reindex(common).to_numpy(dtype=np.float64)
    f = r / a
    rel = np.abs(f[1:] / f[:-1] - 1.0)
    change_at = {common[i + 1] for i in np.nonzero(rel > FACTOR_CHANGE_REL_TOL)[0]}

    # map events to the first common session k with p < ex_date <= k
    ev_at: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    uncheckable: list[dict[str, Any]] = []
    pos = {d: i for i, d in enumerate(common)}
    for e in events:
        ex = pd.Timestamp(e["ex_date"]).date()
        k = next((d for d in common if d >= ex), None)
        if k is None or pos[k] == 0:
            uncheckable.append({"id": e["id"], "event": e["event"], "ex_date": e["ex_date"],
                                "reason": "ex_date at/before first or after last common session"})
            continue
        ev_at[k].append(e)
    unmatched_changes = sorted(d.isoformat() for d in change_at - set(ev_at))
    unmatched_events = sorted({e["ex_date"] for k, es in ev_at.items() if k not in change_at for e in es})
    split_checks = []
    for k, es in sorted(ev_at.items()):
        if k not in change_at:
            continue
        splits = [e for e in es if "split" in e["event"]]
        if not splits:
            continue
        if len(splits) != len(es):
            split_checks.append({"session": k.isoformat(), "ok": None, "reason": "split shares session with dividend"})
            continue
        q = float(np.prod([e["q"] for e in splits]))
        i = pos[k]
        implied = f[i - 1] / f[i]
        ok = bool(abs(implied / q - 1.0) <= SPLIT_RATIO_REL_TOL)
        split_checks.append({"session": k.isoformat(), "ok": ok})
        del implied
    bad_splits = [s for s in split_checks if s["ok"] is not True]
    status = "OK" if not (unmatched_changes or unmatched_events or bad_splits or uncheckable) else "BLOCKING"
    out.update(status=status, factor_changes=len(change_at), events_checked=sum(len(v) for v in ev_at.values()),
               matched_sessions=len(change_at & set(ev_at)), unmatched_changes=unmatched_changes,
               unmatched_events=unmatched_events, split_magnitude_checks=split_checks,
               uncheckable_events=uncheckable)
    return out


def crosscheck_all(raw: dict[str, pd.DataFrame], adj: dict[str, pd.DataFrame],
                   events: list[dict[str, Any]], session_of) -> dict[str, Any]:
    per: dict[str, Any] = {}
    by_ent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_ent[e["entity"]].append(e)
    for sym in sorted(raw):
        rc = pd.Series(raw[sym]["close"].to_numpy(), index=[session_of(t)[0] for t in raw[sym].index])
        ac = pd.Series(adj[sym]["close"].to_numpy(), index=[session_of(t)[0] for t in adj[sym].index])
        per[sym] = crosscheck_symbol(rc, ac, by_ent.get(sym, []))
    return {"rule": "protocol §3.4 (1e-6 factor change; 0.1 % split ratio)", "per_symbol": per,
            "blocking_symbols": sorted(s for s, v in per.items() if v["status"] != "OK")}
