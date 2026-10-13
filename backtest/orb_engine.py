"""backtest/orb_engine.py: ORB backtest - sessiyalar bo'yicha strategy.day.orb_rules.simulate_session tsikli.

Signal, risk va ijro kodi paper_orb/runner.py bilan AYNAN bir xil (simulate_session). Bu modul faqat sessiyalarni
tartiblaydi, carry'ni uzatadi va earnings coverage'ni butun oraliq uchun oldindan tekshiradi (fail closed).
NO PARAMETER OPTIMIZATION; natijalar o'tmish kuzatuvi, tasdiqlangan edge emas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from data.earnings import EarningsCalendar
from data.provider import DataProvider
from data.session import get_session_dates, is_rth_series
from strategy.day.orb_rules import OrbCarry, OrbRules, simulate_session


@dataclass
class OrbBacktestResult:
    rules: OrbRules
    sessions: list[date] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    skips: list[dict] = field(default_factory=list)
    carry: OrbCarry = field(default_factory=OrbCarry)


def rth_sessions(bars_by_symbol: dict[str, pd.DataFrame], start: date, end: date) -> list[date]:
    days: set[date] = set()
    for df in bars_by_symbol.values():
        if len(df):
            sd = get_session_dates(df.index)[is_rth_series(df.index).to_numpy()]
            days.update(d for d in sd if start <= d <= end)
    return sorted(days)


def run_orb_backtest(bars_by_symbol: dict[str, pd.DataFrame], rules: OrbRules, earnings: EarningsCalendar,
                     start: date, end: date, carry: OrbCarry | None = None) -> OrbBacktestResult:
    earnings.check_coverage(sorted(bars_by_symbol), start, end)                 # fail closed before any session
    res = OrbBacktestResult(rules=rules, carry=carry or OrbCarry())
    for session in rth_sessions(bars_by_symbol, start, end):
        trades, skips, res.carry = simulate_session(bars_by_symbol, session, rules, earnings, res.carry)
        res.sessions.append(session)
        res.trades.extend(trades)
        res.skips.extend({"session": session.isoformat(), **s} for s in skips)
    return res


def load_bars(provider: DataProvider, symbols: list[str], *, as_of: datetime | None = None) -> dict[str, pd.DataFrame]:
    """Faqat yopilgan RTH 5m barlar (provayder orqali). Testlarda chaqirilmaydi; tarmoq ishlatishi mumkin."""
    return {s: provider.get_ohlcv(s, "5m", closed_only=True, as_of=as_of) for s in symbols}
