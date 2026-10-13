"""paper_orb/runner.py: ORB virtual paper ledger - sessiya yopilgandan keyin uning yopilgan 5m barlarini qayta o'ynaydi.

- Broker yoki order kodi YO'Q; faqat virtual ledger (JSON).
- Signal/risk/ijro: strategy.day.orb_rules.simulate_session - backtest/orb_engine.py bilan aynan bir xil kod.
- Idempotent: har sessiya uchun bitta `sessions/<D>.json` (commit point); qayta chaqiruv NOOP. Tartibdan tashqari
  yoki boshqa qoidalar (OrbRules) bilan chaqiruv rad etiladi. Carry oxirgi sessiya yozuvidan o'qiladi (yagona manba).
- State: $ORB_PAPER_STATE_DIR, aks holda <repo>/paper_orb_state. paper/ va paper_state/ ga tegilmaydi.

CLI (faqat owner ruxsati bilan ishga tushiriladi; tarmoqdan data oladi):
    python -m paper_orb.runner process --session YYYY-MM-DD --capital 100000 --earnings config/earnings_calendar.csv
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from acquisition.contract import ROOT_DIR
from data.earnings import EarningsCalendar, load_earnings_calendar
from data.session import NY_TZ
from strategy.day.orb_rules import OrbCarry, OrbRules, simulate_session

READY_AFTER_CLOSE = timedelta(minutes=15)


class PaperOrbError(RuntimeError):
    pass


def state_dir() -> Path:
    return Path(os.environ.get("ORB_PAPER_STATE_DIR") or (ROOT_DIR / "paper_orb_state"))


def _records(root: Path) -> list[dict[str, Any]]:
    d = root / "sessions"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("????-??-??.json"))] if d.is_dir() else []


def load_carry(root: Path) -> OrbCarry:
    recs = _records(root)
    return OrbCarry.from_dict(recs[-1]["carry_after"]) if recs else OrbCarry()


def process_session(session: date, bars_by_symbol: dict[str, pd.DataFrame], rules: OrbRules,
                    earnings: EarningsCalendar, root: Path | None = None) -> dict[str, Any]:
    root = Path(root) if root is not None else state_dir()
    path = root / "sessions" / f"{session.isoformat()}.json"
    if path.is_file():
        return {"status": "NOOP", "session": session.isoformat()}
    recs = _records(root)
    if recs and recs[-1]["rules"] != rules.to_dict():
        raise PaperOrbError("OrbRules differ from the rules of the existing ledger")
    carry = OrbCarry.from_dict(recs[-1]["carry_after"]) if recs else OrbCarry()
    trades, skips, after = simulate_session(bars_by_symbol, session, rules, earnings, carry)
    rec = {"session": session.isoformat(), "status": "OK", "rules": rules.to_dict(),
           "carry_before": carry.to_dict(), "carry_after": after.to_dict(), "trades": trades, "skips": skips}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)                                                       # commit point
    return {"status": "OK", "session": session.isoformat(), "trades": len(trades)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("process",))
    ap.add_argument("--session", required=True)
    ap.add_argument("--capital", type=float, required=True)
    ap.add_argument("--earnings", required=True)
    ap.add_argument("--symbols", nargs="*")
    a = ap.parse_args(argv)
    session = date.fromisoformat(a.session)
    close = datetime.combine(session, datetime.min.time(), NY_TZ).replace(hour=16)
    if datetime.now(timezone.utc) < close + READY_AFTER_CLOSE:
        print(f"NOT_READY: session {session} has not closed (+15 min)")
        return 0
    from backtest.orb_engine import load_bars
    from config.day_universe import FROZEN_DAY_UNIVERSE
    from data.factory import get_provider
    earnings = load_earnings_calendar(a.earnings)
    symbols = a.symbols or sorted(FROZEN_DAY_UNIVERSE)
    bars = load_bars(get_provider(), symbols, as_of=close + READY_AFTER_CLOSE)
    print(json.dumps(process_session(session, bars, OrbRules(initial_capital=a.capital), earnings), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
