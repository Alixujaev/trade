"""scripts/backtest_orb.py: golden tests for the default ORB report (Stage 5 step 1; network yo'q, backtest yo'q).

The expected strings are hand-written from the render_report template, not captured from its output. A mismatch
means the default report changed; fix the code or get the change approved, never regenerate these strings.
"""

from __future__ import annotations

import ast
from pathlib import Path

from config.settings import CACHE_DIR
import scripts.backtest_orb as bo

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backtest_orb.py"
YF_CACHE = "yfinance (documented provenance; not recorded per file)"

FULL = {
    "range": {"start": "2026-07-02", "end": "2026-09-25", "sessions": 60},
    "universe": {"count": 2, "symbols_with_trades": ["AAA", "BBB"]},
    "trades": 3, "win_rate": 0.5, "net_return": -0.0625, "cagr": 0.25,
    "cagr_note": "annualised from 60 sessions - not meaningful evidence",
    "max_drawdown": -0.125, "sharpe": 1.25, "sortino": bo.NA,
    "exits": {"STOP": 1, "TARGET": 1, "FORCE_EXIT_1555": 1, "SESSION_END": 0},
    "costs": {"commission_total": 0.03, "slippage_total": 1.5, "note": "both included"},
    "skips": {"no_prior_close": 2, "earnings_day": 1},
    "earnings_skipped_symbol_sessions": 1,
    "benchmarks": {
        "equal_weight_buy_and_hold": {"net_return": 0.0625, "cagr": bo.NA, "max_drawdown": -0.25, "sharpe": -0.5},
        "capital_constrained_buy_and_hold": {"reason": "not computed"},
    },
    "inputs": {"cache_dir": "data/cache", "network": "blocked (socket connect refused)",
               "earnings_calendar": "config/earnings_calendar.csv", "data_source": YF_CACHE},
    "checks": [{"check": "a", "status": "PASS", "detail": "0 outside"},
               {"check": "b", "status": "FAIL", "detail": "1 violations"}],
}

FULL_REPORT = """\
# ORB smoke test (local cache only)

- Range: 2026-07-02 → 2026-09-25 (60 sessions)
- Universe: 2 tickers; with trades: AAA, BBB
- Data: `data/cache` (network blocked (socket connect refused)); earnings: `config/earnings_calendar.csv`
- Smoke test on 60 sessions of yfinance (documented provenance; not recorded per file) 5m data: **not evidence of an edge**.

| Metric | ORB | Equal-weight B&H |
|---|---|---|
| Trades | 3 | — |
| Win rate | 50.00% | — |
| Net return | -6.25% | 6.25% |
| CAGR (annualised from 60 sessions - not meaningful evidence) | 25.00% | N/A |
| Max drawdown | -12.50% | -25.00% |
| Sharpe (daily, √252) | 1.2500 | -0.5000 |
| Sortino (daily, √252) | N/A | N/A |

- Exits: {'STOP': 1, 'TARGET': 1, 'FORCE_EXIT_1555': 1, 'SESSION_END': 0}
- Costs: commission $0.03, slippage $1.50 (both included)
- Skips: {'no_prior_close': 2, 'earnings_day': 1}; earnings-skipped symbol-sessions: 1
- Capital-constrained B&H: not computed

## Checks

| Check | Status | Detail |
|---|---|---|
| a | PASS | 0 outside |
| b | FAIL | 1 violations |
"""

EMPTY = {
    "range": {"start": "2026-07-02", "end": "2026-09-25", "sessions": 0},
    "universe": {"count": 1, "symbols_with_trades": []},
    "trades": 0, "win_rate": bo.NA, "net_return": bo.NA, "cagr": bo.NA, "max_drawdown": bo.NA,
    "sharpe": bo.NA, "sortino": bo.NA, "exits": {}, "skips": {}, "earnings_skipped_symbol_sessions": 0,
    "costs": {"commission_total": 0.0, "slippage_total": 0.0, "note": ""},
    "benchmarks": {"equal_weight_buy_and_hold": {}, "capital_constrained_buy_and_hold": {"reason": "n/a"}},
    "inputs": {"cache_dir": "data/cache", "network": "blocked", "earnings_calendar": "e.csv"},
    "checks": [],
}

EMPTY_REPORT = """\
# ORB smoke test (local cache only)

- Range: 2026-07-02 → 2026-09-25 (0 sessions)
- Universe: 1 tickers; with trades: none
- Data: `data/cache` (network blocked); earnings: `e.csv`
- Smoke test on 0 sessions of UNKNOWN/UNVERIFIED 5m data: **not evidence of an edge**.

| Metric | ORB | Equal-weight B&H |
|---|---|---|
| Trades | 0 | — |
| Win rate | N/A | — |
| Net return | N/A | N/A |
| CAGR () | N/A | N/A |
| Max drawdown | N/A | N/A |
| Sharpe (daily, √252) | N/A | N/A |
| Sortino (daily, √252) | N/A | N/A |

- Exits: {}
- Costs: commission $0.00, slippage $0.00 ()
- Skips: {}; earnings-skipped symbol-sessions: 0
- Capital-constrained B&H: n/a

## Checks

| Check | Status | Detail |
|---|---|---|
"""


def test_default_report_golden_full():
    assert bo.render_report(FULL) == FULL_REPORT


def test_default_report_golden_empty():
    assert bo.render_report(EMPTY) == EMPTY_REPORT


def test_data_source_label_exact(tmp_path):
    assert bo.data_source_label(str(CACHE_DIR), None) == YF_CACHE
    assert bo.data_source_label(str(tmp_path), None) == f"UNKNOWN/UNVERIFIED (no recorded provenance for {tmp_path})"
    assert bo.data_source_label(None, "yfinance") == "yfinance (provider run; provenance not recorded per file)"
    assert bo.data_source_label(None, "alpaca") == (
        "Alpaca IEX (provider run; DataFeed.IEX hard-coded in data/alpaca_provider.py)")
    assert bo.data_source_label(None, "other") == "UNKNOWN/UNVERIFIED (provider other)"
    assert bo.data_source_label(None, None) == "UNKNOWN/UNVERIFIED (provider None)"


def test_module_top_level_imports_exclude_providers_and_snapshot_loader():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    top: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module)
    forbidden = {"data.factory", "data.alpaca_provider", "data.yfinance_provider", "data.v11_research_loader"}
    assert not top & forbidden, sorted(top & forbidden)
