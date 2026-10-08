"""backtest/v2/metrics.py: frozen §12 metrics; non-gated diagnostics follow artifacts/day19/day19-predeclared-definitions.json.

r_d = E(d)/E(d-1) - 1, E(0) = E_0, last E = post-liquidation E_T; N = segment sessions; annualisation 252.
Undefined metrics are reported as {"undefined": reason}, never imputed.
"""

from __future__ import annotations

from collections import defaultdict
import math
from statistics import median

import numpy as np

from backtest.v2.engine import E0, Result

ANN = 252
HAC_LAG = 5


def undefined(reason: str) -> dict:
    return {"undefined": reason}


def returns(res: Result) -> np.ndarray:
    e = np.array([E0] + list(res.equity))
    return e[1:] / e[:-1] - 1.0


def cagr(e_t: float, n: int) -> float:
    return (e_t / E0) ** (ANN / n) - 1.0


def _vol(r):
    return float(np.std(r, ddof=1) * math.sqrt(ANN)) if len(r) > 1 else undefined("fewer than 2 returns")


def _sharpe(r):
    sd = np.std(r, ddof=1) if len(r) > 1 else 0.0
    return float(np.mean(r) / sd * math.sqrt(ANN)) if sd > 0 else undefined("zero return volatility")


def _sortino(r):
    dn = math.sqrt(float(np.mean(np.minimum(r, 0.0) ** 2)))
    return float(np.mean(r) / dn * math.sqrt(ANN)) if dn > 0 else undefined("no negative daily return")


def _mdd(curve: np.ndarray) -> float:
    peak = np.maximum.accumulate(curve)
    return float(np.max(1.0 - curve / peak))


def _period_returns(r: np.ndarray, sessions: list[str], key) -> dict[str, float]:
    acc: dict[str, float] = defaultdict(lambda: 1.0)
    for x, s in zip(r, sessions):
        acc[key(s)] *= 1.0 + x
    return {k: v - 1.0 for k, v in acc.items()}


def hac_t(a: np.ndarray, lag: int = HAC_LAG) -> tuple[float, float]:
    n = len(a)
    dm = a - a.mean()
    g = lambda l: float(np.sum(dm[l:] * dm[:n - l]) / n)
    v = g(0) + 2 * sum((1 - l / (lag + 1)) * g(l) for l in range(1, lag + 1))
    if v <= 0:
        return float("nan"), float("nan")
    t = float(a.mean() / math.sqrt(v / n))
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return t, p


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda x: (x[1], x[0]))
    m, out, run = len(items), {}, 0.0
    for rank, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - rank) * p))
        out[k] = run
    return out


def compute(res: Result, b1: Result | None, b2: Result | None) -> dict:
    n = len(res.equity)
    r = returns(res)
    curve = np.array([E0] + list(res.equity))
    e_t = res.equity[-1]
    out: dict = {
        "starting_capital": E0, "ending_equity": e_t, "pre_liquidation_equity": res.pre_liq_last, "sessions": n,
        "total_return": e_t / E0 - 1.0, "cagr": cagr(e_t, n), "volatility": _vol(r), "sharpe": _sharpe(r),
        "sortino": _sortino(r), "max_drawdown": _mdd(curve),
    }
    out["calmar"] = out["cagr"] / out["max_drawdown"] if out["max_drawdown"] > 0 else undefined("zero drawdown")
    tos = [x["turnover"] for x in res.executions]
    lams = [x["lambda"] for x in res.executions if x["lambda"] is not None]
    out.update({
        "executions": len(res.executions), "trades": len(res.fills), "rebalances": res.rebalances,
        "turnover_per_execution_mean": float(np.mean(tos)) if tos else undefined("no executions"),
        "turnover_total": float(np.sum(tos)), "annual_turnover": float(np.sum(tos)) / (n / ANN),
        "mean_lambda": float(np.mean(lams)) if lams else undefined("no buy executions"),
        "min_lambda": float(np.min(lams)) if lams else undefined("no buy executions"),
        "total_costs": res.costs,
        "cost_per_execution": res.costs / len(res.executions) if res.executions else undefined("no executions"),
        "dividend_cash_total": res.dividends,
        "exposure": {"mean": float(np.mean(res.exposure)), "min": float(np.min(res.exposure)),
                     "max": float(np.max(res.exposure))},
        "cash_exposure": {"mean": float(1 - np.mean(res.exposure)), "min": float(1 - np.max(res.exposure)),
                          "max": float(1 - np.min(res.exposure))},
        "symbols_held": {"mean": float(np.mean(res.n_held)), "min": int(np.min(res.n_held)), "max": int(np.max(res.n_held)),
                         "distinct_ever_held": len(res.flows)},
        "mean_positions": float(np.mean(res.n_held)),
        "position_episodes": len(res.episodes),
    })
    eps = [ep["inflow"] / ep["outflow"] - 1.0 for ep in res.episodes if ep["outflow"] > 0]
    pnl = [ep["inflow"] - ep["outflow"] for ep in res.episodes]
    gains, losses = sum(x for x in pnl if x > 0), sum(x for x in pnl if x < 0)
    out["episodes"] = {
        "win_rate": sum(1 for x in eps if x > 0) / len(eps) if eps else undefined("zero episodes"),
        "mean": float(np.mean(eps)) if eps else undefined("zero episodes"),
        "median": float(median(eps)) if eps else undefined("zero episodes"),
        "profit_factor": gains / abs(losses) if losses < 0 else undefined("no losing episode"),
    }
    months = _period_returns(r, res.sessions, lambda s: s[:7])
    years = _period_returns(r, res.sessions, lambda s: s[:4])
    out["worst_month"] = {"month": min(months, key=lambda k: (months[k], k)), "return": min(months.values())}
    out["worst_year"] = {"year": min(years, key=lambda k: (years[k], k)), "return": min(years.values()),
                         "note": "2017 is partial (from 2017-02-01)"}
    contrib = res.flows
    held = list(contrib)
    out["symbol_breadth"] = (sum(1 for t in held if contrib[t] > 0) / len(held)) if held else undefined("never invested")
    absum = sum(abs(v) for v in contrib.values())
    out["top2_concentration"] = (sum(sorted((abs(v) for v in contrib.values()), reverse=True)[:2]) / absum
                                 if absum > 0 else undefined("no P&L contribution"))
    wbar: dict[str, float] = defaultdict(float)
    for w in res.weights:
        for t, v in w.items():
            wbar[t] += v / n
    tot = sum(wbar.values())
    out["weight_hhi"] = sum((v / tot) ** 2 for v in wbar.values()) if tot > 0 else undefined("never invested")
    out["symbol_pnl_contribution"] = dict(sorted(contrib.items()))
    yearly = {}
    rb1 = returns(b1) if b1 is not None else None
    rb2 = returns(b2) if b2 is not None else None
    for y in sorted(years):
        idx = [i for i, s in enumerate(res.sessions) if s.startswith(y)]
        ry = r[idx]
        eqy = np.cumprod(1 + ry)
        yearly[y] = {"label": "partial (from 2017-02-01)" if y == "2017" else "full", "sessions": len(idx),
                     "return": float(eqy[-1] - 1), "cagr": float(eqy[-1] ** (ANN / len(idx)) - 1),
                     "volatility": _vol(ry), "sharpe": _sharpe(ry), "sortino": _sortino(ry),
                     "max_drawdown": _mdd(np.concatenate([[1.0], eqy]))}
        if rb1 is not None:
            yearly[y]["b1_return"] = float(np.prod(1 + rb1[idx]) - 1)
        if rb2 is not None:
            yearly[y]["b2_return"] = float(np.prod(1 + rb2[idx]) - 1)
    out["calendar_years"] = yearly
    for name, b, rb in (("b1", b1, rb1), ("b2", b2, rb2)):
        if b is None:
            continue
        out[f"{name}_ending_equity"] = b.equity[-1]
        out[f"{name}_total_return"] = b.equity[-1] / E0 - 1.0
        out[f"{name}_cagr"] = cagr(b.equity[-1], len(b.equity))
        out[f"total_return_minus_{name}"] = out["total_return"] - out[f"{name}_total_return"]
        out[f"cagr_minus_{name}"] = out["cagr"] - out[f"{name}_cagr"]
    if rb1 is not None:
        a = r - rb1
        sd = np.std(a, ddof=1)
        out["tracking_error_b1"] = float(sd * math.sqrt(ANN))
        out["information_ratio_b1"] = float(np.mean(a) / sd * math.sqrt(ANN)) if sd > 0 else undefined("zero tracking error")
        t, p = hac_t(a)
        out["active_return_vs_b1_annualised"] = float(np.mean(a) * ANN)
        out["hac_tstat_active_vs_b1"] = t if not math.isnan(t) else undefined("non-positive HAC variance")
        out["hac_p_value"] = p if not math.isnan(p) else undefined("non-positive HAC variance")
    return out
