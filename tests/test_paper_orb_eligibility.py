"""tests/test_paper_orb_eligibility.py: the ORB paper runner enforces the Sharia eligibility registry (fail closed).

Offline and synthetic: registries are written to tmp_path with fictitious tickers (AAA, BBB) and the test-only
methodology TEST_ONLY_METHOD, so no test states that any real ticker is Sharia-compliant. The production registry
(config/sharia_eligibility.csv) and ACCEPTED_METHODOLOGIES are only read, never changed by these tests.
"""

from __future__ import annotations

from datetime import date
import inspect
import json
from pathlib import Path

import pytest

import backtest.orb_engine as orb_engine
import data.factory as data_factory
from paper_orb import runner as po
from screening import eligibility as el
from screening.eligibility import REQUIRED_COLUMNS, EligibilityError, load_registry
from tests.test_orb import BREAKOUT, D0, D1, RULES, day_df, hist

TEST_ONLY = frozenset({"TEST_ONLY_METHOD"})
MARCH = dict(valid_from="2026-03-01", valid_until="2026-03-31", source_date="2026-02-27", reviewed_on="2026-02-28")


def reg_row(symbol: str, status: str, **kw) -> dict[str, str]:
    return {"symbol": symbol, "status": status, "methodology": "TEST_ONLY_METHOD", "source": "Synthetic test screen",
            "source_ref": f"doc-{symbol}", "reviewer": "tester", "note": "synthetic fixture", **MARCH, **kw}


def write_registry(tmp_path: Path, *rows: dict[str, str]) -> Path:
    p = tmp_path / "reg.csv"
    lines = [",".join(REQUIRED_COLUMNS)] + [",".join(r.get(c, "") for c in REQUIRED_COLUMNS) for r in rows]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def registry(tmp_path: Path, *rows: dict[str, str]):
    return load_registry(write_registry(tmp_path, *rows), accepted_methodologies=TEST_ONLY)


def two_symbol_bars():
    return {"AAA": hist(day_df(D0), day_df(D1, BREAKOUT)), "BBB": hist(day_df(D0), day_df(D1, BREAKOUT))}


@pytest.fixture
def earnings(tmp_path):
    from data.earnings import load_earnings_calendar
    p = tmp_path / "earn.csv"
    p.write_text("symbol,coverage_start,coverage_end,earnings_date\n"
                 + "".join(f"{s},{D0},2026-03-31,\n" for s in ("AAA", "BBB")), encoding="utf-8")
    return load_earnings_calendar(p)


def session_files(root: Path) -> list[Path]:
    d = root / "sessions"
    return sorted(d.iterdir()) if d.is_dir() else []


# ------------------------------------------------------------------ process_session

def test_eligibility_is_a_required_keyword_without_default():
    p = inspect.signature(po.process_session).parameters["eligibility"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is inspect.Parameter.empty


def test_default_production_registry_refuses_every_symbol(tmp_path, earnings):
    assert el.ACCEPTED_METHODOLOGIES == frozenset({el.AKINDA_COMPLIANCE_METHODOLOGY})   # D13-A; registry still empty
    state = tmp_path / "state"
    with pytest.raises(po.PaperOrbError, match="no Sharia-eligible symbols"):
        po.process_session(D1, two_symbol_bars(), RULES, earnings, state, eligibility=load_registry())
    assert session_files(state) == []
    assert po.load_carry(state).to_dict() == po.OrbCarry().to_dict()


def test_only_compliant_symbols_reach_simulation_and_all_decisions_are_recorded(tmp_path, earnings, monkeypatch):
    reg = registry(tmp_path, reg_row("AAA", "COMPLIANT"), reg_row("BBB", "NON_COMPLIANT"))
    seen: list[list[str]] = []
    real = po.simulate_session

    def spy(bars_by_symbol, *a, **k):
        seen.append(sorted(bars_by_symbol))
        return real(bars_by_symbol, *a, **k)

    monkeypatch.setattr(po, "simulate_session", spy)
    state = tmp_path / "state"
    assert po.process_session(D1, two_symbol_bars(), RULES, earnings, state, eligibility=reg)["status"] == "OK"
    assert seen == [["AAA"]]
    rec = json.loads((state / "sessions" / f"{D1}.json").read_text(encoding="utf-8"))
    assert {t["symbol"] for t in rec["trades"]} == {"AAA"}
    assert all(s["symbol"] != "BBB" for s in rec["skips"])
    elig = rec["eligibility"]
    assert elig["registry_path"] == reg.source_path
    assert elig["registry_sha256"] == reg.source_sha256
    assert elig["decisions"] == {
        "AAA": {"status": "COMPLIANT", "reason": "recorded_compliant", "methodology": "TEST_ONLY_METHOD"},
        "BBB": {"status": "NON_COMPLIANT", "reason": "recorded_non_compliant", "methodology": "TEST_ONLY_METHOD"},
    }


def test_expired_compliant_record_is_excluded(tmp_path, earnings):
    expired = dict(valid_from="2026-02-01", valid_until=str(D0), source_date="2026-01-30", reviewed_on="2026-01-31")
    reg = registry(tmp_path, reg_row("AAA", "COMPLIANT", **expired), reg_row("BBB", "COMPLIANT"))
    state = tmp_path / "state"
    po.process_session(D1, two_symbol_bars(), RULES, earnings, state, eligibility=reg)
    rec = json.loads((state / "sessions" / f"{D1}.json").read_text(encoding="utf-8"))
    assert rec["eligibility"]["decisions"]["AAA"] == {"status": "UNKNOWN", "reason": "expired", "methodology": None}
    assert all(t["symbol"] == "BBB" for t in rec["trades"])
    assert all(s["symbol"] != "AAA" for s in rec["skips"])


def test_no_eligible_symbols_after_existing_state_writes_nothing_and_keeps_carry(tmp_path, earnings):
    state = tmp_path / "state"
    ok = registry(tmp_path, reg_row("AAA", "COMPLIANT"), reg_row("BBB", "COMPLIANT"))
    po.process_session(D0, two_symbol_bars(), RULES, earnings, state, eligibility=ok)
    before = [(p.name, p.read_bytes()) for p in session_files(state)]
    carry = po.load_carry(state).to_dict()
    none = registry(tmp_path, reg_row("AAA", "UNVERIFIED"), reg_row("BBB", "NON_COMPLIANT"))
    with pytest.raises(po.PaperOrbError, match="no Sharia-eligible symbols"):
        po.process_session(D1, two_symbol_bars(), RULES, earnings, state, eligibility=none)
    assert [(p.name, p.read_bytes()) for p in session_files(state)] == before
    assert po.load_carry(state).to_dict() == carry


def test_record_keeps_decisions_for_whole_universe_when_only_eligible_bars_are_supplied(tmp_path, earnings,
                                                                                        monkeypatch):
    reg = registry(tmp_path, reg_row("AAA", "COMPLIANT"), reg_row("BBB", "NON_COMPLIANT"))
    seen: list[list[str]] = []
    real = po.simulate_session

    def spy(bars_by_symbol, *a, **k):
        seen.append(sorted(bars_by_symbol))
        return real(bars_by_symbol, *a, **k)

    monkeypatch.setattr(po, "simulate_session", spy)
    state = tmp_path / "state"
    only_aaa = {"AAA": two_symbol_bars()["AAA"]}                     # BBB's bars were never fetched
    po.process_session(D1, only_aaa, RULES, earnings, state, eligibility=reg, universe=["AAA", "BBB"])
    assert seen == [["AAA"]]
    rec = json.loads((state / "sessions" / f"{D1}.json").read_text(encoding="utf-8"))
    assert rec["eligibility"]["decisions"] == {
        "AAA": {"status": "COMPLIANT", "reason": "recorded_compliant", "methodology": "TEST_ONLY_METHOD"},
        "BBB": {"status": "NON_COMPLIANT", "reason": "recorded_non_compliant", "methodology": "TEST_ONLY_METHOD"},
    }


def test_missing_bars_for_an_eligible_symbol_fail_closed(tmp_path, earnings):
    reg = registry(tmp_path, reg_row("AAA", "COMPLIANT"), reg_row("BBB", "COMPLIANT"))
    state = tmp_path / "state"
    with pytest.raises(po.PaperOrbError, match="missing bars for eligible symbols"):
        po.process_session(D1, {"AAA": two_symbol_bars()["AAA"]}, RULES, earnings, state, eligibility=reg,
                           universe=["AAA", "BBB"])
    assert session_files(state) == []


def test_bars_outside_the_universe_fail_closed(tmp_path, earnings):
    reg = registry(tmp_path, reg_row("AAA", "COMPLIANT"), reg_row("BBB", "COMPLIANT"))
    state = tmp_path / "state"
    with pytest.raises(po.PaperOrbError, match="outside the universe"):
        po.process_session(D1, two_symbol_bars(), RULES, earnings, state, eligibility=reg, universe=["AAA"])
    assert session_files(state) == []


# ------------------------------------------------------------------ main()

def _forbid_market_data(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("market data accessed")
    monkeypatch.setattr(data_factory, "get_provider", refuse)
    monkeypatch.setattr(orb_engine, "load_bars", refuse)


def _argv(tmp_path):
    p = tmp_path / "earn.csv"
    p.write_text(f"symbol,coverage_start,coverage_end,earnings_date\nAAA,{D0},2026-03-31,\n", encoding="utf-8")
    return ["process", "--session", str(D1), "--capital", "100000", "--earnings", str(p), "--symbols", "AAA"]


def test_main_fails_before_market_data_when_registry_cannot_load(tmp_path, monkeypatch, capsys):
    _forbid_market_data(monkeypatch)
    monkeypatch.setenv("ORB_PAPER_STATE_DIR", str(tmp_path / "state"))

    def broken():
        raise EligibilityError("registry not found: synthetic")

    monkeypatch.setattr(po, "load_eligibility_registry", broken)
    assert po.main(_argv(tmp_path)) != 0
    assert "registry not found" in capsys.readouterr().out
    assert session_files(tmp_path / "state") == []


def test_main_with_production_registry_refuses_before_market_data(tmp_path, monkeypatch, capsys):
    _forbid_market_data(monkeypatch)
    monkeypatch.setenv("ORB_PAPER_STATE_DIR", str(tmp_path / "state"))
    assert po.main(_argv(tmp_path)) != 0
    assert "no Sharia-eligible symbols" in capsys.readouterr().out
    assert session_files(tmp_path / "state") == []


def test_main_fetches_market_data_only_for_eligible_symbols(tmp_path, monkeypatch, capsys):
    reg = registry(tmp_path, reg_row("AAA", "COMPLIANT"), reg_row("BBB", "NON_COMPLIANT"))
    monkeypatch.setattr(po, "load_eligibility_registry", lambda: reg)
    monkeypatch.setattr(data_factory, "get_provider", lambda *_a, **_k: object())
    fetched: list[list[str]] = []

    def fake_load_bars(_provider, symbols, *, as_of=None):
        fetched.append(list(symbols))
        return {s: hist(day_df(D0), day_df(D1, BREAKOUT)) for s in symbols}

    monkeypatch.setattr(orb_engine, "load_bars", fake_load_bars)
    monkeypatch.setenv("ORB_PAPER_STATE_DIR", str(tmp_path / "state"))
    earn = tmp_path / "earn.csv"
    earn.write_text(f"symbol,coverage_start,coverage_end,earnings_date\nAAA,{D0},2026-03-31,\n", encoding="utf-8")
    argv = ["process", "--session", str(D1), "--capital", "100000", "--earnings", str(earn), "--symbols", "AAA", "BBB"]
    assert po.main(argv) == 0
    assert fetched == [["AAA"]]
    out = capsys.readouterr().out
    assert "BBB" in out and "NON_COMPLIANT" in out
    rec = json.loads((tmp_path / "state" / "sessions" / f"{D1}.json").read_text(encoding="utf-8"))
    assert sorted(rec["eligibility"]["decisions"]) == ["AAA", "BBB"]
    assert rec["eligibility"]["decisions"]["BBB"]["status"] == "NON_COMPLIANT"
    assert {t["symbol"] for t in rec["trades"]} <= {"AAA"}


# ------------------------------------------------------------------ source guards

def test_runner_has_no_methodology_override_or_order_code():
    src = inspect.getsource(po)
    for banned in ("accepted_methodologies", "ACCEPTED_METHODOLOGIES", "submit_order", "TradingClient",
                   "place_order", "paper-api.alpaca", "api.alpaca.markets/v2/orders"):
        assert banned not in src, banned
