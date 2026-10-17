"""paper_orb/runner.py: ORB virtual paper ledger - sessiya yopilgandan keyin uning yopilgan 5m barlarini qayta o'ynaydi.

- Broker yoki order kodi YO'Q; faqat virtual ledger (JSON).
- Signal/risk/ijro: strategy.day.orb_rules.simulate_session - backtest/orb_engine.py bilan aynan bir xil kod.
- Idempotent: har sessiya uchun bitta `sessions/<D>.json` (commit point); qayta chaqiruv NOOP. Tartibdan tashqari
  yoki boshqa qoidalar (OrbRules) bilan chaqiruv rad etiladi. Carry oxirgi sessiya yozuvidan o'qiladi (yagona manba).
- State: $ORB_PAPER_STATE_DIR, aks holda <repo>/paper_orb_state. paper/ va paper_state/ ga tegilmaydi.
- Sharia gate (fail closed): faqat screening.eligibility registry'si sessiya kuni COMPLIANT deb bergan simvollar
  simulatsiyaga kiradi. Registry yuklanmasa yoki eligible simvol bo'lmasa -> xato, hech narsa yozilmaydi.
  main() registry'ni market data'dan OLDIN tekshiradi va faqat eligible simvollar uchun data oladi.

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
from screening.eligibility import EligibilityDecision, EligibilityError, EligibilityRegistry, load_registry
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


def load_eligibility_registry() -> EligibilityRegistry:
    """Production registry: library defaults only (default path, default accepted-methodology set; no override)."""
    return load_registry()


def _decision_record(dec: EligibilityDecision) -> dict[str, Any]:
    return {"status": dec.status.value, "reason": dec.reason,
            "methodology": dec.record.methodology if dec.record is not None else None}


def eligible_symbols(eligibility: EligibilityRegistry, symbols: list[str], session: date
                     ) -> tuple[tuple[str, ...], dict[str, EligibilityDecision]]:
    """(tradable, decisions) from the registry; PaperOrbError if no symbol is tradable (fail closed)."""
    tradable, decisions = eligibility.filter_universe(sorted(symbols), session)
    if not tradable:
        raise PaperOrbError(f"no Sharia-eligible symbols for session {session.isoformat()} "
                            f"(registry {eligibility.source_path}, sha256 {eligibility.source_sha256})")
    return tradable, decisions


def process_session(session: date, bars_by_symbol: dict[str, pd.DataFrame], rules: OrbRules,
                    earnings: EarningsCalendar, root: Path | None = None, *,
                    eligibility: EligibilityRegistry, universe: list[str] | None = None) -> dict[str, Any]:
    """`universe`: the original input universe (default: the symbols of `bars_by_symbol`). Eligibility decisions are
    recorded for all of it; `bars_by_symbol` may hold only the eligible symbols (main() never fetches the rest)."""
    root = Path(root) if root is not None else state_dir()
    path = root / "sessions" / f"{session.isoformat()}.json"
    if path.is_file():
        return {"status": "NOOP", "session": session.isoformat()}
    recs = _records(root)
    if recs and recs[-1]["rules"] != rules.to_dict():
        raise PaperOrbError("OrbRules differ from the rules of the existing ledger")
    tradable, decisions = eligible_symbols(eligibility, list(universe if universe is not None else bars_by_symbol),
                                           session)                            # before any write
    outside = sorted(set(bars_by_symbol) - set(decisions))
    if outside:
        raise PaperOrbError(f"bars supplied for symbols outside the universe: {outside}")
    missing = [s for s in tradable if s not in bars_by_symbol]
    if missing:
        raise PaperOrbError(f"missing bars for eligible symbols: {missing}")
    carry = OrbCarry.from_dict(recs[-1]["carry_after"]) if recs else OrbCarry()
    trades, skips, after = simulate_session({s: bars_by_symbol[s] for s in tradable}, session, rules, earnings, carry)
    rec = {"session": session.isoformat(), "status": "OK", "rules": rules.to_dict(),
           "carry_before": carry.to_dict(), "carry_after": after.to_dict(), "trades": trades, "skips": skips,
           "eligibility": {"registry_path": eligibility.source_path, "registry_sha256": eligibility.source_sha256,
                           "decisions": {s: _decision_record(d) for s, d in decisions.items()}}}
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
    from config.day_universe import FROZEN_DAY_UNIVERSE
    symbols = a.symbols or sorted(FROZEN_DAY_UNIVERSE)
    try:                                                                        # Sharia gate BEFORE any market data
        eligibility = load_eligibility_registry()
        tradable, decisions = eligible_symbols(eligibility, symbols, session)
    except (EligibilityError, PaperOrbError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    excluded = {s: _decision_record(d) for s, d in decisions.items() if s not in tradable}
    if excluded:
        print(json.dumps({"excluded_by_eligibility": excluded}, indent=1, sort_keys=True))
    from backtest.orb_engine import load_bars
    from data.factory import get_provider
    earnings = load_earnings_calendar(a.earnings)
    bars = load_bars(get_provider(), list(tradable), as_of=close + READY_AFTER_CLOSE)
    print(json.dumps(process_session(session, bars, OrbRules(initial_capital=a.capital), earnings,
                                     eligibility=eligibility, universe=list(symbols)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
