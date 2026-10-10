"""paper/ledger.py: virtual ledger of V2-MOM-P001 by replaying the frozen engine (backtest/v2) up to a session.

The paper ledger is a pure function of (frozen engine, input data up to session D): en.simulate_targets with the
frozen V2-MOM decision function (signals.mom_targets), the frozen month-end schedule (signals.month_end_flags, §8.14
initial decision on the session before FIRST_SESSION) and the frozen B1 / B2 rules, run with upto=D (no liquidation).
Ranking, sizing, λ buy scaling, costs, corporate actions and market-on-open t+1 fills are therefore identical to the
research engine. A month-end decision at D becomes the pending order filled at the next session's raw open.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math

import numpy as np

from backtest.v2 import engine as en
from backtest.v2 import signals as sg
from backtest.v2.data import MarketData, tr_index
from paper.config import COST_PRIMARY, EXPERIMENT_ID, LEDGERS, RISK


class RiskViolation(RuntimeError):
    """A frozen risk invariant does not hold: nothing is recorded."""


def _next_session(d: date) -> date:
    import exchange_calendars as xcals
    import pandas as pd
    cal = xcals.get_calendar("XNYS", start=(pd.Timestamp(d) - pd.Timedelta(days=10)).date().isoformat(),
                             end=(pd.Timestamp(d) + pd.Timedelta(days=40)).date().isoformat())
    return cal.next_session(d.isoformat()).date()


def replay(data: MarketData, first_idx: int, upto_idx: int, cost: float = COST_PRIMARY) -> dict[str, en.Result]:
    """Frozen-engine replay of V2-MOM, B1, B2 from first_idx through upto_idx (inclusive); no liquidation."""
    if not 0 < first_idx <= upto_idx < len(data.sessions):
        raise ValueError("replay window outside the loaded data")
    tr = tr_index(data)
    uni = [data.col(t) for t in data.universe]
    flags = sg.month_end_flags(data.sessions, _next_session(data.sessions[-1]))
    month = [first_idx - 1] + [k for k in range(first_idx, upto_idx + 1) if flags[k]]
    beyond = len(data.sessions) + 10                     # never reached: every in-window decision is executable

    def b1(_t):
        have = [j for j in uni if not math.isnan(data.open[first_idx, j])]
        return {j: 1.0 / len(have) for j in have}
    spy = data.col("SPY")
    return {"V2-MOM": en.simulate_targets(data, lambda t: sg.mom_targets(tr, t, uni, data.tickers), month, cost,
                                          first_idx, beyond, "V2-MOM", upto_idx),
            "B1": en.simulate_targets(data, b1, [first_idx - 1], cost, first_idx, beyond, "B1", upto_idx),
            "B2": en.simulate_targets(data, lambda _t: {spy: 1.0}, [first_idx - 1], cost, first_idx, beyond, "B2", upto_idx)}


def check_risk(data: MarketData, res: dict[str, en.Result]) -> None:
    pos = {s.isoformat(): i for i, s in enumerate(data.sessions)}
    for fam, r in res.items():
        for dcs in r.decisions:
            tg = dcs.get("targets") or {}
            if len(tg) > RISK["max_names"] and fam == "V2-MOM":
                raise RiskViolation(f"{fam}: more than {RISK['max_names']} target names")
            if fam == "V2-MOM" and any(w > RISK["max_target_weight"] + 1e-12 for w in tg.values()):
                raise RiskViolation(f"{fam}: target weight above {RISK['max_target_weight']}")
            if sum(tg.values()) > RISK["max_target_sum"] + 1e-12:
                raise RiskViolation(f"{fam}: target weights sum above 1 (leverage)")
        for e, x in zip(r.equity, r.exposure):
            if not (math.isfinite(e) and e > 0):
                raise RiskViolation(f"{fam}: non-finite or non-positive equity")
            if x > RISK["max_exposure"]:
                raise RiskViolation(f"{fam}: exposure above {RISK['max_exposure']} (leverage)")
            if e * (1.0 - x) < RISK["min_cash"]:
                raise RiskViolation(f"{fam}: negative cash")
        for f in r.fills:
            if f["price"] != data.open[pos[f["session"]], data.col(f["ticker"])]:
                raise RiskViolation(f"{fam}: fill not at the raw open of its session")


def session_ledger(data: MarketData, res: dict[str, en.Result], session: date, input_ref: str,
                   config_sha256: str) -> dict:
    """Canonical (sealed) ledger content for one session."""
    iso = session.isoformat()
    out = {"experiment": EXPERIMENT_ID, "session": iso, "input_manifest_sha256": input_ref,
           "strategy_config_sha256": config_sha256, "cost_per_side": COST_PRIMARY, "ledgers": {}}
    for fam in LEDGERS:
        r = res[fam]
        i = r.sessions.index(iso)
        eq = r.equity[i]
        prev = r.equity[i - 1] if i else en.E0
        dec_today = [d for d in r.decisions if d["close"] == iso]
        out["ledgers"][fam] = {
            "equity_close": eq, "daily_pnl": eq - prev, "daily_return": eq / prev - 1.0, "exposure": r.exposure[i],
            "cash": eq * (1.0 - r.exposure[i]), "weights": r.weights[i], "positions_value": {t: w * eq for t, w in r.weights[i].items()},
            "names_held": r.n_held[i],
            "fills_today": [f for f in r.fills if f["session"] == iso],
            "executions_today": [x for x in r.executions if x["session"] == iso],
            "decisions_today": dec_today,
            "pending_orders_next_open": dec_today[-1]["targets"] if dec_today and "targets" in dec_today[-1] else {},
            "cumulative_costs": sum(f["cost"] for f in r.fills if f["session"] <= iso),
        }
    return out


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      default=lambda o: float(o) if isinstance(o, np.floating) else int(o)).encode("utf-8")


def ledger_sha256(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()
