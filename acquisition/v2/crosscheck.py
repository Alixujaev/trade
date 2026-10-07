"""acquisition/v2/crosscheck.py: raw/all implied-factor cross-check (v2.0 R1 §3.4 as amended by v2.0.2 and v2.0.3).

Per symbol, on sessions present in both raw and `all` series: r = stored raw close (exact), a = stored
adjustment=all close, f = r / a; for consecutive common sessions p < k, rho = f_k / f_p.

Precision models (selected explicitly; v2.0.3 is current):
- "v2.0.3" (v2.0.3 item 1, FROZEN): per value, d_k = decimal places of the shortest round-trip representation of
  a_k (trailing zeros not counted) and delta_k = 0.5 * 10^-max(d_k, 2).
- "v2.0.2" (retired; kept only to reproduce the DAY-18B output): d = max d_k over the symbol, one delta = 0.5*10^-d.

Interval (both models, with delta_p / delta_k per value):
      rho_min = rho * (a_k / (a_k + delta_k)) * ((a_p - delta_p) / a_p)
      rho_max = rho * (a_k / (a_k - delta_k)) * ((a_p + delta_p) / a_p)
A change is DETECTED iff 1 lies outside [rho_min, rho_max]. PRECISION_DEGENERATE (BLOCKING) iff a_p - delta_p <= 0
or a_k - delta_k <= 0, or the interval is not finite.

Coincidence (unchanged): every detected change needs a retained split/dividend event with ex_date in (p, k]
(else UNEXPLAINED change); every event needs a detected change (else UNCONFIRMED; no precision exemption); split
magnitude within 0.1 % of prod(q). Events with ex_date <= first common session: FIRST_SESSION_UNTESTABLE
(non-blocking). Events after the last common session: uncheckable (BLOCKING). No symbol-specific branch exists.
Only dates, counts, flags and precision statistics are reported - never prices or factors.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from acquisition.v2.contract import SPLIT_RATIO_REL_TOL

PRECISION_MODELS = ("v2.0.3", "v2.0.2")
FLOOR_DECIMALS = 2
RULES = {
    "v2.0.3": "v2.0.3 item 1 per-value precision (delta_k = 0.5*10^-max(d_k,2)) + v2.0.2 item 2 first-session; split 0.1 % (frozen §3.4)",
    "v2.0.2": "v2.0.2 item 1 precision-interval (d = max decimals) + item 2 first-session; split 0.1 % (frozen §3.4)",
}
RULE = RULES["v2.0.3"]


def decimals_of(x: float) -> int:
    """Decimal places of the shortest round-trip representation of a stored float (trailing zeros dropped)."""
    exp = Decimal(repr(float(x))).normalize().as_tuple().exponent
    return int(-exp) if isinstance(exp, int) and exp < 0 else 0


def precision_of(all_close: pd.Series) -> tuple[int, float]:
    """v2.0.2: (max decimals, 0.5*10^-max)."""
    d = max(decimals_of(v) for v in all_close.to_numpy(dtype=np.float64))
    return d, 0.5 * 10.0 ** (-d)


def per_value_deltas(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """v2.0.3: (d_k array, delta_k = 0.5*10^-max(d_k, 2) array)."""
    d = np.array([decimals_of(v) for v in a], dtype=np.int64)
    return d, 0.5 * np.power(10.0, -np.maximum(d, FLOOR_DECIMALS).astype(np.float64))


def detect_changes(r: np.ndarray, a: np.ndarray, delta: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For consecutive pairs (i-1, i): (detected[i-1], degenerate[i-1]). `delta` is a scalar or a per-value array."""
    dl = np.broadcast_to(np.asarray(delta, dtype=np.float64), a.shape)
    rp, rk, ap, ak = r[:-1], r[1:], a[:-1], a[1:]
    dp, dk = dl[:-1], dl[1:]
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        rho = (rk / ak) / (rp / ap)
        rho_min = rho * (ak / (ak + dk)) * ((ap - dp) / ap)
        rho_max = rho * (ak / (ak - dk)) * ((ap + dp) / ap)
        degenerate = (ap - dp <= 0) | (ak - dk <= 0) | ~np.isfinite(rho_min) | ~np.isfinite(rho_max)
        detected = ~((rho_min <= 1.0) & (1.0 <= rho_max))
    return detected & ~degenerate, degenerate


def crosscheck_symbol(raw_close: pd.Series, all_close: pd.Series, events: list[dict[str, Any]], *,
                      precision_model: str = "v2.0.3") -> dict[str, Any]:
    """raw_close / all_close: indexed by session date, exactly the acquired rows."""
    if precision_model not in PRECISION_MODELS:
        raise ValueError(f"precision_model must be one of {PRECISION_MODELS}")
    common = sorted(set(raw_close.index) & set(all_close.index))
    out: dict[str, Any] = {"rule": RULES[precision_model], "precision_model": precision_model,
                           "common_sessions": len(common)}
    if len(common) < 2:
        out.update(status="BLOCKING", reason="fewer than two common sessions")
        return out
    r = raw_close.reindex(common).to_numpy(dtype=np.float64)
    a = all_close.reindex(common).to_numpy(dtype=np.float64)
    d_k, delta_k = per_value_deltas(a)
    hist = {str(k): int(v) for k, v in sorted(Counter(d_k.tolist()).items())}
    if precision_model == "v2.0.2":
        d, delta = precision_of(pd.Series(a))
        detected, degenerate = detect_changes(r, a, delta)
        out.update(d=d, delta=delta)
    else:
        detected, degenerate = detect_changes(r, a, delta_k)
    out.update(precision_histogram=hist, pairs_evaluated=len(common) - 1)
    change_at = {common[i + 1] for i in np.nonzero(detected)[0]}
    degenerate_at = sorted(common[i + 1].isoformat() for i in np.nonzero(degenerate)[0])

    pos = {dd: i for i, dd in enumerate(common)}
    first, last = common[0], common[-1]
    ev_at: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    first_session: list[dict[str, Any]] = []
    uncheckable: list[dict[str, Any]] = []
    for e in events:
        ex = pd.Timestamp(e["ex_date"]).date()
        if ex <= first:
            first_session.append({"id": e["id"], "event": e["event"], "ex_date": e["ex_date"],
                                  "classification": "FIRST_SESSION_UNTESTABLE", "blocking": False})
            continue
        if ex > last:
            uncheckable.append({"id": e["id"], "event": e["event"], "ex_date": e["ex_date"],
                                "reason": "ex_date after the last common session (not covered by v2.0.2/v2.0.3)"})
            continue
        k = next(dd for dd in common if dd >= ex)
        ev_at[k].append(e)
    # unexplained change: session k plus its previous common session p (needed by v2.0.3 review records)
    unexplained = sorted(dd.isoformat() for dd in change_at - set(ev_at))
    unexplained_pairs = [{"p": common[pos[pd.Timestamp(u).date()] - 1].isoformat(), "k": u} for u in unexplained]
    unconfirmed_ev = sorted(({"id": e["id"], "event": e["event"], "ex_date": e["ex_date"], "session": k.isoformat()}
                             for k, es in ev_at.items() if k not in change_at for e in es),
                            key=lambda x: (x["ex_date"], x["id"]))
    unconfirmed = sorted({u["ex_date"] for u in unconfirmed_ev})
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
        implied = (r[i - 1] / a[i - 1]) / (r[i] / a[i])
        split_checks.append({"session": k.isoformat(), "ok": bool(abs(implied / q - 1.0) <= SPLIT_RATIO_REL_TOL)})
        del implied
    bad_splits = [s for s in split_checks if s["ok"] is not True]
    blocking = bool(unexplained or unconfirmed or bad_splits or uncheckable or degenerate_at)
    out.update(status="BLOCKING" if blocking else "OK", detected_changes=len(change_at),
               expected_events=sum(len(v) for v in ev_at.values()),
               matched_events=sum(len(v) for k, v in ev_at.items() if k in change_at),
               matched_sessions=len(change_at & set(ev_at)), unexplained_changes=unexplained,
               unexplained_pairs=unexplained_pairs, unconfirmed_events=unconfirmed,
               unconfirmed_event_records=unconfirmed_ev, split_magnitude_checks=split_checks,
               precision_degenerate_pairs=degenerate_at, first_session_untestable=first_session,
               uncheckable_events=uncheckable)
    return out


def crosscheck_all(raw: dict[str, pd.DataFrame], adj: dict[str, pd.DataFrame],
                   events: list[dict[str, Any]], session_of, *, precision_model: str = "v2.0.3") -> dict[str, Any]:
    per: dict[str, Any] = {}
    by_ent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_ent[e["entity"]].append(e)
    for sym in sorted(raw):
        rc = pd.Series(raw[sym]["close"].to_numpy(), index=[session_of(t)[0] for t in raw[sym].index])
        ac = pd.Series(adj[sym]["close"].to_numpy(), index=[session_of(t)[0] for t in adj[sym].index])
        per[sym] = crosscheck_symbol(rc, ac, by_ent.get(sym, []), precision_model=precision_model)
    return {"rule": RULES[precision_model], "precision_model": precision_model, "per_symbol": per,
            "blocking_symbols": sorted(s for s, v in per.items() if v["status"] != "OK"),
            "first_session_untestable": sorted(f"{s} {e['event']} {e['ex_date']}" for s, v in per.items()
                                              for e in v.get("first_session_untestable", []))}
