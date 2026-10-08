"""backtest/v2/engine.py: deterministic portfolio simulator for protocol v2 (§8 execution, §9 costs, §11 accounting).

At every open k of the segment (frozen §8.4): (1) corporate actions with ex-date k (dividend = shares held at the
previous close x d, credited as cash; split = shares x q); (2) E_open = cash + sum shares x v (v = raw open, else
last mark); (3) trade notionals; (4) all sells at the raw open, cash += proceeds x (1 - s); (5) buys scaled by
lambda = min(1, K / (B (1 + s))), cash -= lambda B (1 + s). At every close: mark = raw close, else last close / Q
(§11.5); E(k) = cash + sum shares x mark. At the segment's last close a liquidation cost s x sum shares x mark is
deducted (E_T). Decisions at the last close are discarded; pending orders at segment end are discarded (§8.15).

V2-LRV (protocol-owner clarification, DAY-19, decided before results): the §8.4 lambda is applied per entering slot
with K = the slot's own cash, so a slot never spends another slot's cash ("no cross-slot lending", §6.2 row 20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable

import numpy as np

from backtest.v2 import signals as sg
from backtest.v2.data import MarketData

E0 = 100_000.0


class AmbiguousState(RuntimeError):
    """A situation the frozen protocol does not specify (raised instead of improvising; never seen on Stage R)."""


@dataclass
class Book:
    data: MarketData
    s: float
    cash: float = E0
    shares: np.ndarray = None
    mark_carry: np.ndarray = None          # last close / product of splits since that close (§11.5)
    fills: list = field(default_factory=list)
    executions: list = field(default_factory=list)
    dividends: float = 0.0
    costs: float = 0.0
    flows: dict = field(default_factory=dict)       # per symbol: net cash flows (inflows - outflows)
    episodes: list = field(default_factory=list)
    open_ep: dict = field(default_factory=dict)

    def __post_init__(self):
        m = len(self.data.tickers)
        self.shares = np.zeros(m)
        self.mark_carry = np.full(m, np.nan)

    # -- corporate actions (start of session k, before the open)
    def apply_events(self, k: int, credit: Callable[[int, float], None] | None = None) -> None:
        for j in np.nonzero(self.shares)[0]:
            dv = self.data.d[k, j]
            if dv:
                amt = self.shares[j] * dv                 # shares held at the previous close (pre-split basis)
                (credit or self._credit)(j, amt)
                self.dividends += amt
                self.flows[j] = self.flows.get(j, 0.0) + amt
                self.open_ep[j]["inflow"] += amt
            qv = self.data.q[k, j]
            if qv != 1.0:
                self.shares[j] *= qv
                self.mark_carry[j] /= qv
        for j in range(len(self.data.tickers)):        # unheld symbols: keep the mark carry split-consistent
            if not self.shares[j] and self.data.q[k, j] != 1.0 and not math.isnan(self.mark_carry[j]):
                self.mark_carry[j] /= self.data.q[k, j]

    def _credit(self, j: int, amt: float) -> None:
        self.cash += amt

    def value_at_open(self, k: int, j: int) -> float:
        o = self.data.open[k, j]
        return o if not math.isnan(o) else self.mark_carry[j]

    def e_open(self, k: int) -> float:
        return self.cash + sum(self.shares[j] * self.value_at_open(k, j) for j in np.nonzero(self.shares)[0])

    # -- fills (cash handled by the caller for slot accounting; this records shares, costs, flows, episodes)
    def sell(self, k: int, j: int, qty: float, slot: int | None = None) -> float:
        px = self.data.open[k, j]
        notional = qty * px
        cost = notional * self.s
        self.shares[j] = 0.0 if qty == self.shares[j] else self.shares[j] - qty   # full sells pass the exact quantity
        self.costs += cost
        net = notional - cost
        self.flows[j] = self.flows.get(j, 0.0) + net
        self.open_ep[j]["inflow"] += net
        self.fills.append({"session": self.data.sessions[k].isoformat(), "ticker": self.data.tickers[j], "side": "sell",
                           "shares": qty, "price": px, "notional": notional, "cost": cost, "slot": slot})
        if self.shares[j] == 0.0:
            ep = self.open_ep.pop(j)
            ep.update(end=self.data.sessions[k].isoformat(), final_net_mark=0.0)
            self.episodes.append(ep)
        return net

    def buy(self, k: int, j: int, notional: float, lam: float, slot: int | None = None) -> float:
        px = self.data.open[k, j]
        cost = notional * self.s
        if not self.shares[j]:
            self.open_ep[j] = {"ticker": self.data.tickers[j], "start": self.data.sessions[k].isoformat(),
                               "outflow": 0.0, "inflow": 0.0}
        self.shares[j] += notional / px
        self.costs += cost
        self.flows[j] = self.flows.get(j, 0.0) - notional - cost
        self.open_ep[j]["outflow"] += notional + cost
        self.fills.append({"session": self.data.sessions[k].isoformat(), "ticker": self.data.tickers[j], "side": "buy",
                           "shares": notional / px, "price": px, "notional": notional, "cost": cost, "lambda": lam,
                           "slot": slot})
        return notional + cost

    def mark(self, k: int) -> np.ndarray:
        c = self.data.close[k]
        have = ~np.isnan(c)
        self.mark_carry[have] = c[have]
        return self.mark_carry

    def liquidate_marks(self, k: int) -> float:
        """Segment end (§11.6): liquidation cost on the marked positions; closes every open episode."""
        mk = self.mark_carry
        gross = sum(self.shares[j] * mk[j] for j in np.nonzero(self.shares)[0])
        cost = gross * self.s
        for j in list(self.open_ep):
            net = self.shares[j] * mk[j] * (1 - self.s)
            ep = self.open_ep.pop(j)
            ep.update(end=self.data.sessions[k].isoformat() + " (segment end)", final_net_mark=net)
            ep["inflow"] += net
            self.flows[j] = self.flows.get(j, 0.0) + net
            self.episodes.append(ep)
        self.costs += cost
        return cost


@dataclass
class Result:
    label: str
    s: float
    equity: list            # E(k) at each segment close; last entry is the post-liquidation E_T
    pre_liq_last: float
    exposure: list
    weights: list           # per close: {ticker: weight}
    n_held: list
    fills: list
    executions: list
    decisions: list
    dividends: float
    costs: float
    flows: dict
    episodes: list
    rebalances: int
    sessions: list


def _close_phase(book: Book, k: int, eq: list, expo: list, wts: list, nh: list) -> float:
    mk = book.mark(k)
    held = np.nonzero(book.shares)[0]
    pos = {j: book.shares[j] * mk[j] for j in held}
    e = book.cash + sum(pos.values())
    eq.append(e)
    expo.append(sum(pos.values()) / e)
    wts.append({book.data.tickers[j]: v / e for j, v in pos.items()})
    nh.append(len(held))
    return e


def simulate_targets(data: MarketData, decide: Callable[[int], dict[int, float]], decision_idx: list[int], s: float,
                     seg_first: int, seg_last: int, label: str, upto: int | None = None) -> Result:
    """Target-weight strategies (V2-MOM, V2-STR) and buy-and-hold benchmarks (one decision at seg_first - 1)."""
    book = Book(data, s)
    eq, expo, wts, nh, decisions = [], [], [], [], []
    plan: dict[int, dict[int, float]] = {}
    pending: set[int] = set()                     # pending full sells (§8.6)
    last = seg_last if upto is None else upto
    if seg_first - 1 in decision_idx:
        tg = decide(seg_first - 1)
        decisions.append({"close": data.sessions[seg_first - 1].isoformat(), "targets": _named(data, tg)})
        plan[seg_first] = tg
    rebal = 0
    for k in range(seg_first, last + 1):
        book.apply_events(k)
        fills0 = len(book.fills)
        if k in plan:
            rebal += 1
            tg = plan.pop(k)
            pending.clear()                       # superseded by the newer decision (§8.6)
            E = book.e_open(k)
            sells, buys = [], []
            for j in sorted(set(np.nonzero(book.shares)[0]) | set(tg), key=lambda j: data.tickers[j]):
                o = data.open[k, j]
                target = tg.get(j, 0.0) * E
                if math.isnan(o):
                    if book.shares[j] and target == 0.0:
                        pending.add(j)            # full sell becomes a pending sell
                    elif book.shares[j] and target < book.shares[j] * book.value_at_open(k, j):
                        raise AmbiguousState("partial resize-down at a missing open is not specified by §8.6")
                    continue                      # buys at a missing open are cancelled
                cur = book.shares[j] * o
                if target == 0.0 and book.shares[j]:
                    sells.append((j, book.shares[j]))
                elif target < cur:
                    sells.append((j, (cur - target) / o))
                elif target > cur:
                    buys.append((j, target - cur))
            traded = 0.0
            for j, qty in sells:
                book.cash += book.sell(k, j, qty)
                traded += qty * data.open[k, j]
            lam = _buy_all(book, k, buys, s)
            traded += sum(lam * n for _, n in buys)
            if len(book.fills) > fills0:
                book.executions.append({"session": data.sessions[k].isoformat(), "E_open": E, "turnover": 0.5 * traded / E,
                                        "lambda": lam if buys else None, "fills": len(book.fills) - fills0})
        elif pending:
            E = book.e_open(k)
            traded = 0.0
            for j in sorted(pending, key=lambda j: data.tickers[j]):
                if not math.isnan(data.open[k, j]):
                    traded += book.shares[j] * data.open[k, j]
                    book.cash += book.sell(k, j, book.shares[j])
                    pending.discard(j)
            if len(book.fills) > fills0:
                book.executions.append({"session": data.sessions[k].isoformat(), "E_open": E, "turnover": 0.5 * traded / E,
                                        "lambda": None, "fills": len(book.fills) - fills0})
        _close_phase(book, k, eq, expo, wts, nh)
        if k in decision_idx and k != seg_last:
            tg = decide(k)
            decisions.append({"close": data.sessions[k].isoformat(), "targets": _named(data, tg)})
            plan[k + 1] = tg
        elif k in decision_idx:
            decisions.append({"close": data.sessions[k].isoformat(), "discarded": "segment last close (§8.15)"})
    return _finish(book, label, s, eq, expo, wts, nh, decisions, rebal, seg_first, last, upto is None)


def _buy_all(book: Book, k: int, buys: list, s: float) -> float:
    B = sum(n for _, n in buys)
    if B <= 0:
        return 1.0
    K = book.cash
    lam = min(1.0, K / (B * (1 + s)))
    for j, n in buys:
        book.buy(k, j, lam * n, lam)
    book.cash = 0.0 if lam < 1.0 else K - B * (1 + s)   # lambda < 1: K - lambda B (1+s) = 0 exactly (algebraic)
    return lam


def _named(data: MarketData, tg: dict[int, float]) -> dict[str, float]:
    return {data.tickers[j]: w for j, w in sorted(tg.items(), key=lambda x: data.tickers[x[0]])}


def _finish(book, label, s, eq, expo, wts, nh, decisions, rebal, seg_first, last, liquidate) -> Result:
    pre = eq[-1] if eq else E0
    if liquidate:
        eq[-1] = pre - book.liquidate_marks(last)
    return Result(label, s, eq, pre, expo, wts, nh, book.fills, book.executions, decisions, book.dividends, book.costs,
                  {book.data.tickers[j]: v for j, v in sorted(book.flows.items())}, book.episodes, rebal,
                  [book.data.sessions[k].isoformat() for k in range(seg_first, last + 1)])


def simulate_lrv(data: MarketData, tr: np.ndarray, s: float, seg_first: int, seg_last: int, label: str = "V2-LRV",
                 upto: int | None = None) -> Result:
    """V2-LRV (§6.2) with 5 independent slots and sequential 126-session cycles."""
    book = Book(data, s)
    universe = [data.col(t) for t in data.universe]
    eq, expo, wts, nh, decisions = [], [], [], [], []
    last = seg_last if upto is None else upto
    starts = list(range(seg_first, seg_last + 1, sg.LRV_PERIOD))
    slot_cash = [0.0] * sg.LRV_SLOTS
    slot_pos: list[dict | None] = [None] * sg.LRV_SLOTS          # {"j", "s0"}
    queued: list[tuple | None] = [None] * sg.LRV_SLOTS           # ("buy", j, s0) | ("sell",) for the next open
    pending_sell = [False] * sg.LRV_SLOTS
    pairs: list = []
    p0 = t_f = None
    cycles = 0
    credit_slot = {}
    next_pairs: list = []

    def credit(j: int, amt: float) -> None:
        slot_cash[credit_slot[j]] += amt

    def form(tf: int) -> list:
        """Pair formation at the close of t_F (rows 1-7, 22); known before the open of p0."""
        prs = sg.lrv_formation(tr, tf, universe, data.tickers)
        decisions.append({"close": data.sessions[tf].isoformat(), "formation": [
            {"i": data.tickers[pr.i], "j": data.tickers[pr.j], "ssd": pr.ssd, "sigma": pr.sigma} for pr in prs]})
        return prs

    next_pairs = form(seg_first - 1)                              # §8.14: first cycle's t_F = session before segment

    for k in range(seg_first, last + 1):
        for i, p in enumerate(slot_pos):
            if p is not None:
                credit_slot[p["j"]] = i
        book.apply_events(k, credit)
        book.cash = sum(slot_cash)                                # dividends were credited to their slots
        fills0 = len(book.fills)
        E = book.cash + sum(book.shares[j] * book.value_at_open(k, j) for j in np.nonzero(book.shares)[0])
        traded, lam_used = 0.0, []
        if k in starts:
            # period-end exits of the previous cycle (row 15), then new slot capital (row 20)
            for i, p in enumerate(slot_pos):
                if p is not None:
                    if math.isnan(data.open[k, p["j"]]):
                        raise AmbiguousState("period-end exit with a missing open at a cycle start is not specified")
                    traded += book.shares[p["j"]] * data.open[k, p["j"]]
                    slot_cash[i] += book.sell(k, p["j"], book.shares[p["j"]], slot=i)
                    slot_pos[i] = None
            total = E0 if k == seg_first else sum(slot_cash)
            slot_cash = [total / sg.LRV_SLOTS] * sg.LRV_SLOTS
            queued = [None] * sg.LRV_SLOTS
            p0, t_f = k, k - 1
            cycles += 1
            pairs = next_pairs
        else:
            for i, q in enumerate(queued):                       # sells first (§8.4)
                if q and q[0] == "sell":
                    j = slot_pos[i]["j"]
                    if math.isnan(data.open[k, j]):
                        pending_sell[i] = True                   # retried at each later open (§8.6)
                        continue
                    traded += book.shares[j] * data.open[k, j]
                    slot_cash[i] += book.sell(k, j, book.shares[j], slot=i)
                    slot_pos[i], queued[i], pending_sell[i] = None, None, False
            for i, q in enumerate(queued):
                if q and q[0] == "buy":
                    queued[i] = None
                    j, s0 = q[1], q[2]
                    if math.isnan(data.open[k, j]):
                        continue                                 # cancelled; slot re-evaluated at its next signal
                    B = slot_cash[i]
                    lam = min(1.0, slot_cash[i] / (B * (1 + s))) if B > 0 else 1.0
                    if B > 0:
                        book.buy(k, j, lam * B, lam, slot=i)
                        slot_cash[i] = 0.0 if lam < 1.0 else slot_cash[i] - B * (1 + s)
                        slot_pos[i] = {"j": j, "s0": s0}
                        traded += lam * B
                        lam_used.append(lam)
        book.cash = sum(slot_cash)
        if len(book.fills) > fills0:
            book.executions.append({"session": data.sessions[k].isoformat(), "E_open": E, "turnover": 0.5 * traded / E,
                                    "lambda": min(lam_used) if lam_used else None, "fills": len(book.fills) - fills0})
        _close_phase(book, k, eq, expo, wts, nh)
        # signals at the close (rows 10-17): entry window p0..p124, never at the segment's last close
        if p0 is not None and k <= p0 + sg.LRV_PERIOD - 2 and k != seg_last:
            for i, pr in enumerate(pairs):
                S = sg.lrv_spread(tr, k, t_f, pr)
                if S is None:
                    continue
                if slot_pos[i] is not None:
                    if not pending_sell[i] and queued[i] is None and slot_pos[i]["s0"] * S <= 0:
                        queued[i] = ("sell",)
                        decisions.append({"close": data.sessions[k].isoformat(), "slot": i, "action": "exit",
                                          "ticker": data.tickers[slot_pos[i]["j"]], "S": S})
                elif queued[i] is None and sg.lrv_trigger(S, pr):
                    j = sg.lrv_lagging(S, pr)
                    queued[i] = ("buy", j, sg.sign(S))
                    decisions.append({"close": data.sessions[k].isoformat(), "slot": i, "action": "entry",
                                      "ticker": data.tickers[j], "S": S})
        elif p0 is not None and k == seg_last and k <= p0 + sg.LRV_PERIOD - 2:
            decisions.append({"close": data.sessions[k].isoformat(), "discarded": "segment last close (§8.15)"})
        if k + 1 in starts:                                       # next cycle's formation close is p125 (row 21)
            next_pairs = form(k)
    return _finish(book, label, s, eq, expo, wts, nh, decisions, cycles, seg_first, last, upto is None)
