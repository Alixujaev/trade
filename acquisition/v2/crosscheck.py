"""acquisition/v2/crosscheck.py: raw/all implied-factor cross-check (v2.0 R1 §3.4 as amended by v2.0.2 and v2.0.3).

Per symbol, on sessions present in both raw and `all` series: r = stored raw close (exact), a = stored
adjustment=all close, f = r / a; for consecutive common sessions p < k, rho = f_k / f_p.

Precision models (selected explicitly):
- "v2.0.4" (v2.0.4, exact evaluation): the v2.0.3 interval evaluated in exact rational arithmetic. Each persisted
  binary64 close (raw and all) takes the exact value of its shortest round-trip decimal representation (OQ10; never
  the binary value itself); raw closes carry no delta; delta_k = 1/(2*10^max(d_k, 2)) exactly; f = R/A exactly.
  float64 is evaluated only as a diagnostic: exact NO / float YES -> NUMERICAL_FALSE_POSITIVE (non-blocking),
  exact YES / float NO -> NUMERICAL_FALSE_NEGATIVE (exact detection stands). A value that cannot be represented
  exactly (non-finite, non-positive, non-convertible) -> EXACT_EVALUATION_INVALID (BLOCKING).
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
from decimal import Decimal, localcontext
from fractions import Fraction
import math
from typing import Any

import numpy as np
import pandas as pd

from acquisition.v2.contract import SPLIT_RATIO_REL_TOL

PRECISION_MODELS = ("v2.0.4", "v2.0.3", "v2.0.2")
FLOOR_DECIMALS = 2
RULES = {
    "v2.0.4": "v2.0.4 exact rational evaluation of the v2.0.3 per-value precision interval (shortest round-trip decimal "
              "values, raw without delta, delta_k = 1/(2*10^max(d_k,2))); float64 diagnostic only; v2.0.2 item 2 "
              "first-session; split 0.1 % (frozen §3.4)",
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


class ExactEvaluationInvalid(ValueError):
    """v2.0.4: a stored value has no exact representation (non-finite, non-positive or non-convertible)."""


def shortest_decimal(x: Any) -> str:
    """v2.0.4 / OQ10: the shortest decimal string that converts back to exactly the persisted binary64 value (ties:
    the one nearest the binary value). CPython's float repr implements exactly this (David Gay, mode 0)."""
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExactEvaluationInvalid(f"non-convertible value: {type(exc).__name__}") from None
    if not math.isfinite(v):
        raise ExactEvaluationInvalid("non-finite value")
    s = repr(v)
    if float(s) != v:
        raise ExactEvaluationInvalid("shortest representation does not round-trip")
    return s


def exact_value(x: Any) -> Fraction:
    """v2.0.4 / OQ10: exact rational denoted by the shortest round-trip decimal of a persisted close (raw or all)."""
    v = Fraction(Decimal(shortest_decimal(x)))
    if v <= 0:
        raise ExactEvaluationInvalid("non-positive value")
    return v


def exact_delta(d: int) -> Fraction:
    """v2.0.4: delta_k = 1 / (2 * 10^max(d_k, 2)), exact (adjusted closes only; raw closes carry no delta)."""
    return Fraction(1, 2 * 10 ** max(int(d), FLOOR_DECIMALS))


def exact_interval(rp: Fraction, ap: Fraction, rk: Fraction, ak: Fraction, dp: Fraction,
                   dk: Fraction) -> tuple[Fraction, Fraction, Fraction]:
    """(rho, rho_min, rho_max) in exact arithmetic, f = R/A; caller guarantees a - delta > 0."""
    rho = (rk / ak) / (rp / ap)
    return rho, rho * (ak / (ak + dk)) * ((ap - dp) / ap), rho * (ak / (ak - dk)) * ((ap + dp) / ap)


def detect_changes_exact(r: np.ndarray, a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """v2.0.4, consecutive pairs (i-1, i): (detected, degenerate, invalid). Authoritative; no float comparison."""
    n = max(len(a) - 1, 0)
    detected, degenerate, invalid = (np.zeros(n, dtype=bool) for _ in range(3))
    vals: list[tuple[Fraction, Fraction, Fraction] | None] = []
    for x, y in zip(r, a):
        try:
            vals.append((exact_value(x), exact_value(y), exact_delta(decimals_of(y))))
        except ExactEvaluationInvalid:
            vals.append(None)
    for i in range(n):
        p, k = vals[i], vals[i + 1]
        if p is None or k is None:
            invalid[i] = True
            continue
        (rp, ap, dp), (rk, ak, dk) = p, k
        if ap - dp <= 0 or ak - dk <= 0:
            degenerate[i] = True
            continue
        _, lo, hi = exact_interval(rp, ap, rk, ak, dp, dk)
        detected[i] = not (lo <= 1 <= hi)
    return detected, degenerate, invalid


def _dec(q: Fraction, digits: int = 34) -> str:
    with localcontext() as ctx:
        ctx.prec = digits
        return str(Decimal(q.numerator) / Decimal(q.denominator))


def pair_evidence(rp: float, ap: float, rk: float, ak: float) -> dict[str, Any]:
    """Exact and float64 evidence for one pair (reports only; the cross-check output never carries prices)."""
    R = {"p": exact_value(rp), "k": exact_value(rk)}
    A = {"p": exact_value(ap), "k": exact_value(ak)}
    d = {"p": decimals_of(ap), "k": decimals_of(ak)}
    D = {s: exact_delta(d[s]) for s in d}
    rho, lo, hi = exact_interval(R["p"], A["p"], R["k"], A["k"], D["p"], D["k"])
    fdet, fdeg = detect_changes(np.array([rp, rk]), np.array([ap, ak]), per_value_deltas(np.array([ap, ak]))[1])
    frho = (rk / ak) / (rp / ap)
    fdp, fdk = 0.5 * 10.0 ** -max(d["p"], 2), 0.5 * 10.0 ** -max(d["k"], 2)
    exact_det = not (lo <= 1 <= hi)
    float_det = bool(fdet[0])
    return {
        "persisted": {f"{n}_{s}": {"binary64_hex": float(v).hex(), "shortest_decimal": shortest_decimal(v)}
                      for n, vs in (("raw", (rp, rk)), ("adjusted", (ap, ak))) for s, v in zip(("p", "k"), vs)},
        "d": d, "delta": {s: str(D[s]) for s in D}, "raw_delta": None,
        "exact": {"f_p": str(R["p"] / A["p"]), "f_k": str(R["k"] / A["k"]), "rho": str(rho), "rho_min": str(lo),
                  "rho_max": str(hi), "rho_decimal": _dec(rho), "rho_min_decimal": _dec(lo),
                  "rho_max_decimal": _dec(hi), "rho_max_equals_1": hi == 1, "contains_1": lo <= 1 <= hi,
                  "detected": exact_det},
        "float64": {"rho": repr(frho), "rho_min": repr(frho * (ak / (ak + fdk)) * ((ap - fdp) / ap)),
                    "rho_max": repr(frho * (ak / (ak - fdk)) * ((ap + fdp) / ap)), "detected": float_det,
                    "degenerate": bool(fdeg[0])},
        "numerical_classification": ("NUMERICAL_FALSE_POSITIVE" if float_det and not exact_det else
                                     "NUMERICAL_FALSE_NEGATIVE" if exact_det and not float_det else "AGREE"),
    }


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
    invalid_at: list[str] = []
    if precision_model == "v2.0.2":
        d, delta = precision_of(pd.Series(a))
        detected, degenerate = detect_changes(r, a, delta)
        out.update(d=d, delta=delta)
    elif precision_model == "v2.0.4":
        detected, degenerate, invalid = detect_changes_exact(r, a)          # authoritative
        f_det, f_deg = detect_changes(r, a, delta_k)                        # float64 diagnostic only
        both = ~invalid & ~degenerate & ~f_deg

        def pairs(mask: np.ndarray) -> list[dict[str, str]]:
            return [{"p": common[i].isoformat(), "k": common[i + 1].isoformat()} for i in np.nonzero(mask)[0]]

        invalid_at = sorted(common[i + 1].isoformat() for i in np.nonzero(invalid)[0])
        out.update(numerical_false_positives=pairs(both & f_det & ~detected),
                   numerical_false_negatives=pairs(both & detected & ~f_det),
                   float_degeneracy_disagreements=pairs(~invalid & (degenerate != f_deg)),
                   float64_diagnostic={"detected_changes": int(np.count_nonzero(f_det)),
                                       "degenerate_pairs": int(np.count_nonzero(f_deg))},
                   exact_evaluation_invalid_pairs=invalid_at)
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
        if precision_model == "v2.0.4":                                     # diagnostic: does exact f = R/A agree?
            f_ratio = (exact_value(r[i - 1]) / exact_value(a[i - 1])) / (exact_value(r[i]) / exact_value(a[i]))
            exact_ok = abs(f_ratio / Fraction(Decimal(repr(float(q)))) - 1) <= Fraction(Decimal(repr(SPLIT_RATIO_REL_TOL)))
            split_checks[-1]["exact_agrees"] = exact_ok == split_checks[-1]["ok"]
        del implied
    bad_splits = [s for s in split_checks if s["ok"] is not True]
    blocking = bool(unexplained or unconfirmed or bad_splits or uncheckable or degenerate_at or invalid_at)
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
