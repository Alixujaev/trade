"""backtest/v2/signals.py: frozen v2 signal formulas and schedules (§4, §5, §6, §8.14, §8.15).

Every function reads only TR rows <= the decision session index t (callers may pass truncated data; the PIT tests
check that decisions are identical either way). Indices are XNYS calendar session indices (§3.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import numpy as np

SELECT = 5
WEIGHT = 0.20
MOM_LONG, MOM_SKIP = 252, 21
STR_R, STR_VOL = 5, 60
LRV_FORMATION, LRV_PERIOD, LRV_SLOTS, LRV_SIGMA = 252, 126, 5, 2.0


# ------------------------------------------------------------------ schedules

def month_end_flags(sessions: tuple[date, ...], next_session: date) -> list[bool]:
    """True where the session is the last XNYS session of its calendar month (next_session = first session after)."""
    nxt = list(sessions[1:]) + [next_session]
    return [(s.year, s.month) != (n.year, n.month) for s, n in zip(sessions, nxt)]


def iso_week_end_flags(sessions: tuple[date, ...], next_session: date) -> list[bool]:
    nxt = list(sessions[1:]) + [next_session]
    return [s.isocalendar()[:2] != n.isocalendar()[:2] for s, n in zip(sessions, nxt)]


def decision_sessions(flags: list[bool], seg_first: int, seg_last: int) -> list[int]:
    """§8.14 initial decision at seg_first-1 (even off-schedule), then scheduled sessions in [seg_first, seg_last-1];
    decisions at the segment's last close are discarded (§8.15)."""
    return [seg_first - 1] + [k for k in range(seg_first, seg_last) if flags[k]]


# ------------------------------------------------------------------ V2-MOM (§4)

def mom_scores(tr: np.ndarray, t: int, universe: list[int]) -> dict[int, float]:
    out = {}
    if t - MOM_LONG < 0:
        return out
    for j in universe:
        a, b = tr[t - MOM_SKIP, j], tr[t - MOM_LONG, j]
        if not (math.isnan(a) or math.isnan(b)):
            out[j] = a / b - 1.0
    return out


def mom_targets(tr: np.ndarray, t: int, universe: list[int], tickers: tuple[str, ...]) -> dict[int, float]:
    sc = mom_scores(tr, t, universe)
    ranked = sorted(sc, key=lambda j: (-sc[j], tickers[j]))
    return {j: WEIGHT for j in ranked[:SELECT]}


# ------------------------------------------------------------------ V2-STR (§5)

def str_scores(tr: np.ndarray, t: int, universe: list[int]) -> dict[int, float]:
    if t - STR_VOL < 0:
        return {}
    r5, sig = {}, {}
    for j in universe:
        w = tr[t - STR_VOL:t + 1, j]                      # 61 closes t-60 .. t
        if np.isnan(w).any():
            continue
        R = w[1:] / w[:-1] - 1.0                          # 60 daily returns, k = t-59 .. t (includes R(t))
        s = float(np.std(R, ddof=1))
        if s > 0:
            r5[j], sig[j] = tr[t, j] / tr[t - STR_R, j] - 1.0, s
    if not r5:
        return {}
    mean = sum(r5.values()) / len(r5)                     # same-t cross-sectional mean over eligible symbols
    return {j: (r5[j] - mean) / (sig[j] * math.sqrt(STR_R)) for j in r5}


def str_targets(tr: np.ndarray, t: int, universe: list[int], tickers: tuple[str, ...]) -> dict[int, float]:
    z = str_scores(tr, t, universe)
    ranked = sorted(z, key=lambda j: (z[j], tickers[j]))
    return {j: WEIGHT for j in ranked[:SELECT]}


# ------------------------------------------------------------------ V2-LRV (§6)

@dataclass(frozen=True)
class Pair:
    i: int                                                # ticker_i < ticker_j
    j: int
    ssd: float
    sigma: float


def lrv_formation(tr: np.ndarray, t_f: int, universe: list[int], tickers: tuple[str, ...]) -> list[Pair]:
    f0 = t_f - (LRV_FORMATION - 1)
    if f0 < 0:
        return []
    win = tr[f0:t_f + 1]
    elig = sorted((j for j in universe if not np.isnan(win[:, j]).any()), key=lambda j: tickers[j])
    norm = {j: win[:, j] / win[0, j] for j in elig}       # N_i(k) = TR_i(k) / TR_i(F0)
    cands = []
    for a in range(len(elig)):
        for b in range(a + 1, len(elig)):
            i, j = elig[a], elig[b]
            D = norm[i] - norm[j]
            cands.append((float(np.sum(D * D)), tickers[i], tickers[j], i, j, float(np.std(D, ddof=1))))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    used: set[int] = set()
    pairs: list[Pair] = []
    for ssd, _, _, i, j, sigma in cands:
        if len(pairs) == LRV_SLOTS:
            break
        if i in used or j in used:
            continue
        used.update((i, j))
        pairs.append(Pair(i, j, ssd, sigma))
    return pairs


def lrv_spread(tr: np.ndarray, t: int, t_f: int, pair: Pair) -> float | None:
    """S_ij(t) = M_i(t) - M_j(t), M = TR(t)/TR(t_F); None if either member's TR is undefined (row 25)."""
    vals = (tr[t, pair.i], tr[t_f, pair.i], tr[t, pair.j], tr[t_f, pair.j])
    if any(math.isnan(v) for v in vals):
        return None
    return vals[0] / vals[1] - vals[2] / vals[3]


def lrv_trigger(s: float, pair: Pair) -> bool:
    return abs(s) > LRV_SIGMA * pair.sigma                # strict inequality (row 10)


def lrv_lagging(s: float, pair: Pair) -> int:
    return pair.j if s > 0 else pair.i                    # row 11 (lower M)


def sign(x: float) -> int:
    return int(x > 0) - int(x < 0)
