"""strategy/day/orb_rules.py: ORB risk + ijro qoidalari - backtest VA paper runner uchun YAGONA manba.

Ikkala yo'l (backtest/orb_engine.py va paper_orb/runner.py) ham faqat `simulate_session` ni chaqiradi; stop,
share sizing, komissiya, slippage, kunlik limitlar va majburiy exit shu yerda bir marta yozilgan.

Qoidalar (owner-approved):
- Stop = OR low; risk/share = entry_open - OR low; target = entry_open + 2R (raw narxlar bo'yicha).
- Sizing: floor(0.25% * initial_capital / risk_per_share) (strategy/position_sizing.size_position orqali), so'ng
  mavjud kapitalga sig'adigan qilib kesiladi; < 1 aksiya -> trade yo'q.
- Slippage har tomonga 5 bps (kirish yuqoriga, chiqish pastga); komissiya har tomonga $0.005/share.
- Bir barda stop va target -> STOP_FIRST. Bar open stopdan past bo'lsa (gap) -> open narxida chiqish.
- Bar open >= 15:55 ET -> shu bar open'ida majburiy exit; sessiya undan oldin tugasa (qisqa kun) -> oxirgi bar close.
- Kunlik: jami <= 2 trade; bir vaqtda <= 2 ochiq pozitsiya; realised R <= -2 bo'lsa yangi entry yo'q;
  ochiq pozitsiyalar notional'i mavjud kapitaldan (initial + realised P&L) oshmaydi.

Vaqt tartibi (point-in-time): har bir bar vaqtida avval shu bar open'ida kirishlar (gate holati faqat oldingi
barlardan), keyin barcha ochiq pozitsiyalar (yangi ochilganlar ham) shu bar bo'yicha tekshiriladi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, time
import math
from typing import Any

import pandas as pd

from data.earnings import EarningsCalendar
from data.session import get_session_dates, is_rth_series, to_eastern
from strategy.day.orb import OrbSignal, find_signal, precompute, session_bars
from strategy.position_sizing import size_position


@dataclass(frozen=True)
class OrbRules:
    initial_capital: float
    risk_pct: float = 0.0025
    target_r: float = 2.0
    max_trades_per_day: int = 2
    max_open_positions: int = 2
    daily_loss_limit_r: float = -2.0
    min_price: float = 5.0
    slippage_bps: float = 5.0
    commission_per_share: float = 0.005
    force_exit: time = time(15, 55)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.initial_capital) and self.initial_capital > 0):
            raise ValueError("initial_capital must be positive")
        if not 0 < self.risk_pct < 1:
            raise ValueError("risk_pct must be in (0, 1)")
        if self.target_r <= 0 or self.max_trades_per_day < 1 or self.max_open_positions < 1:
            raise ValueError("invalid target / limits")
        if self.daily_loss_limit_r >= 0 or self.slippage_bps < 0 or self.commission_per_share < 0:
            raise ValueError("invalid loss limit / costs")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["force_exit"] = self.force_exit.isoformat()
        return d

    def buy_fill(self, price: float) -> float:
        return price * (1.0 + self.slippage_bps / 10_000.0)

    def sell_fill(self, price: float) -> float:
        return price * (1.0 - self.slippage_bps / 10_000.0)


@dataclass(frozen=True)
class EntryPlan:
    shares: int
    entry_open: float
    entry_fill: float
    stop: float
    target: float
    risk_per_share: float
    capped: bool


def plan_entry(entry_open: float, or_low: float, available_capital: float,
               rules: OrbRules) -> tuple[EntryPlan | None, str]:
    """(plan, "ok") yoki (None, sabab). Stop = OR low; entry_open <= OR low (gap stop ostida) -> trade yo'q."""
    risk = entry_open - or_low
    if not (math.isfinite(risk) and risk > 0):
        return None, "entry_not_above_stop"
    sized = size_position(rules.initial_capital, entry_open, or_low, risk_pct=rules.risk_pct)
    shares = math.floor(sized.shares) if sized.acceptable else 0
    fill = rules.buy_fill(entry_open)
    affordable = math.floor(max(available_capital, 0.0) / (fill + rules.commission_per_share))
    capped = sized.capped_to_equity or affordable < shares
    shares = min(shares, affordable)
    if shares < 1:
        return None, "insufficient_capital" if capped else "zero_shares"
    return EntryPlan(shares=shares, entry_open=entry_open, entry_fill=fill, stop=or_low,
                     target=entry_open + rules.target_r * risk, risk_per_share=risk, capped=capped), "ok"


@dataclass
class OpenPosition:
    symbol: str
    signal: OrbSignal
    plan: EntryPlan
    commission_per_share: float

    @property
    def notional(self) -> float:
        """Pozitsiya band qilgan kapital: shares * (entry fill + kirish komissiyasi) - plan_entry bilan bir xil."""
        return self.plan.shares * (self.plan.entry_fill + self.commission_per_share)


def step_bar(pos: OpenPosition, bar_open_et: time, o: float, h: float, low: float,
             rules: OrbRules) -> tuple[str, float] | None:
    """Pozitsiyani bitta bar bo'yicha tekshiradi -> (sabab, raw exit narxi) yoki None."""
    if bar_open_et >= rules.force_exit:
        return "FORCE_EXIT_1555", o
    if low <= pos.plan.stop:                                   # STOP_FIRST (stop va target bir barda bo'lsa ham)
        return "STOP", min(o, pos.plan.stop)
    if h >= pos.plan.target:
        return "TARGET", pos.plan.target
    return None


def close_trade(pos: OpenPosition, exit_time: pd.Timestamp, reason: str, exit_raw: float,
                rules: OrbRules) -> dict[str, Any]:
    p = pos.plan
    exit_fill = rules.sell_fill(exit_raw)
    pnl = (exit_fill - p.entry_fill) * p.shares - 2.0 * rules.commission_per_share * p.shares
    return {"symbol": pos.symbol, "session": pos.signal.session.isoformat(),
            "signal_time": pos.signal.signal_time.isoformat(), "entry_time": pos.signal.entry_time.isoformat(),
            "exit_time": exit_time.isoformat(), "exit_reason": reason,
            "or_high": pos.signal.or_high, "or_low": pos.signal.or_low,
            "entry_open": p.entry_open, "entry_fill": p.entry_fill, "stop": p.stop, "target": p.target,
            "risk_per_share": p.risk_per_share, "shares": p.shares, "capped": p.capped,
            "exit_raw": exit_raw, "exit_fill": exit_fill, "pnl": pnl,
            "r_multiple": pnl / (p.shares * p.risk_per_share)}


@dataclass
class OrbCarry:
    """Sessiyalararo holat: faqat realised P&L va oxirgi qayta ishlangan sessiya."""

    realised_pnl_total: float = 0.0
    last_session: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"realised_pnl_total": self.realised_pnl_total,
                "last_session": self.last_session.isoformat() if self.last_session else None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OrbCarry":
        ls = d.get("last_session")
        return cls(realised_pnl_total=float(d["realised_pnl_total"]),
                   last_session=date.fromisoformat(ls) if ls else None)


@dataclass
class DayRiskGate:
    rules: OrbRules
    capital: float                                             # initial + oldingi kunlar realised P&L
    trades: int = 0
    realised_r: float = 0.0
    realised_pnl: float = 0.0
    open_positions: dict[str, OpenPosition] = field(default_factory=dict)

    def available_capital(self) -> float:
        return self.capital + self.realised_pnl - sum(p.notional for p in self.open_positions.values())

    def block_reason(self) -> str | None:
        if self.trades >= self.rules.max_trades_per_day:
            return "max_trades_per_day"
        if self.realised_r <= self.rules.daily_loss_limit_r:
            return "daily_loss_limit"
        if len(self.open_positions) >= self.rules.max_open_positions:
            return "max_open_positions"
        return None


def _prior_close(df: pd.DataFrame, session: date) -> float | None:
    if df.empty:
        return None
    mask = (get_session_dates(df.index) < session) & is_rth_series(df.index)
    prior = df.loc[mask.to_numpy()]
    return float(prior["close"].iloc[-1]) if len(prior) else None


def simulate_session(bars_by_symbol: dict[str, pd.DataFrame], session: date, rules: OrbRules,
                     earnings: EarningsCalendar, carry: OrbCarry) -> tuple[list[dict], list[dict], OrbCarry]:
    """Bitta sessiyani barcha simvollar bo'yicha simulyatsiya qiladi -> (trades, skips, yangi carry).

    `bars_by_symbol`: 5m OHLCV (tz-aware index). Sessiyadan keyingi barlar e'tiborga olinmaydi.
    """
    if carry.last_session is not None and session <= carry.last_session:
        raise ValueError(f"session {session} is not after the last processed session {carry.last_session}")
    symbols = sorted(bars_by_symbol)
    earnings.check_coverage(symbols, session, session)                  # fail closed
    gate = DayRiskGate(rules=rules, capital=rules.initial_capital + carry.realised_pnl_total)
    skips: list[dict] = []
    trades: list[dict] = []
    sessions_bars: dict[str, pd.DataFrame] = {}
    entries: dict[pd.Timestamp, list[OrbSignal]] = {}

    for sym in symbols:
        df = bars_by_symbol[sym]
        df = df.loc[(get_session_dates(df.index) <= session).to_numpy()] if len(df) else df   # no future bars
        sdf = session_bars(df, session)
        if sdf.empty:
            continue
        sessions_bars[sym] = sdf
        if earnings.is_earnings_day(sym, session):
            skips.append({"symbol": sym, "reason": "earnings_day"})
            continue
        pc = _prior_close(df, session)
        if pc is None:
            skips.append({"symbol": sym, "reason": "no_prior_close"})
            continue
        if pc < rules.min_price:
            skips.append({"symbol": sym, "reason": "penny_stock"})
            continue
        sig = find_signal(sym, df, precompute(df), session)
        if sig is not None:
            entries.setdefault(sig.entry_time, []).append(sig)

    timeline = sorted({ts for sdf in sessions_bars.values() for ts in sdf.index})
    for ts in timeline:
        for sig in sorted(entries.get(ts, []), key=lambda s: s.symbol):            # 1) kirishlar (bar open)
            reason = gate.block_reason()
            if reason is None:
                o = float(sessions_bars[sig.symbol].at[ts, "open"])
                plan, reason = plan_entry(o, sig.or_low, gate.available_capital(), rules)
                if plan is not None:
                    gate.open_positions[sig.symbol] = OpenPosition(sig.symbol, sig, plan, rules.commission_per_share)
                    gate.trades += 1
                    continue
            skips.append({"symbol": sig.symbol, "reason": reason, "signal_time": sig.signal_time.isoformat()})
        bar_et = to_eastern(ts).time()
        for sym in sorted(gate.open_positions):                                    # 2) chiqishlar (shu bar)
            sdf = sessions_bars[sym]
            if ts not in sdf.index:
                continue
            row = sdf.loc[ts]
            hit = step_bar(gate.open_positions[sym], bar_et, float(row["open"]), float(row["high"]),
                           float(row["low"]), rules)
            if hit is not None:
                tr = close_trade(gate.open_positions.pop(sym), ts, hit[0], hit[1], rules)
                trades.append(tr)
                gate.realised_pnl += tr["pnl"]
                gate.realised_r += tr["r_multiple"]

    for sym in sorted(gate.open_positions):                                        # qisqa kun: oxirgi bar close
        last = sessions_bars[sym].iloc[-1]
        tr = close_trade(gate.open_positions.pop(sym), sessions_bars[sym].index[-1], "SESSION_END",
                         float(last["close"]), rules)
        trades.append(tr)
        gate.realised_pnl += tr["pnl"]

    trades.sort(key=lambda t: (t["entry_time"], t["symbol"]))
    return trades, skips, OrbCarry(realised_pnl_total=carry.realised_pnl_total + gate.realised_pnl,
                                   last_session=session)
