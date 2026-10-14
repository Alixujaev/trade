# ORB smoke test (local cache only)

- Range: 2026-07-02 → 2026-09-25 (60 sessions)
- Universe: 25 tickers; with trades: AAPL, ADBE, AMAT, AMD, AMZN, AVGO, COST, CRM, GOOGL, INTC, JNJ, JPM, KO, META, MSFT, MU, NFLX, NVDA, ORCL, QCOM, TSLA, WMT, XOM
- Data: `data/cache` (network blocked (socket connect refused)); earnings: `config\earnings_calendar.csv`
- Smoke test on 60 sessions of yfinance 5m data (`data/cache`; documented provenance, not recorded per file - see `artifacts/orb/provenance_correction.md`): **not evidence of an edge**.

| Metric | ORB | Equal-weight B&H |
|---|---|---|
| Trades | 95 | — |
| Win rate | 48.42% | — |
| Net return | -1.43% | 4.68% |
| CAGR (annualised from 60 sessions - not meaningful evidence) | -5.87% | 21.16% |
| Max drawdown | -2.10% | -4.68% |
| Sharpe (daily, √252) | -1.8702 | 1.4636 |
| Sortino (daily, √252) | -2.4310 | 2.5359 |

- Exits: {'STOP': 13, 'TARGET': 0, 'FORCE_EXIT_1555': 82, 'SESSION_END': 0}
- Costs: commission $48.56, slippage $1143.24 (both included in every trade's P&L (entry_fill/exit_fill and 2 x $0.005/share))
- Skips: {'no_prior_close': 25, 'max_trades_per_day': 59, 'earnings_day': 24}; earnings-skipped symbol-sessions: 24
- Capital-constrained B&H: not defined comparably for an intraday strategy limited to 2 concurrent positions; not computed rather than approximated

## Checks

| Check | Status | Detail |
|---|---|---|
| trade sessions within backtest range | PASS | 0 outside |
| no duplicate (symbol, session) trades | PASS | 0 duplicates |
| entry is the bar after the signal; entry <= exit (no lookahead) | PASS | 0 violations |
| exit in the same session (no overnight) | PASS | 0 violations |
| signal bar opens in 09:45-11:00 ET | PASS | 0 violations |
| stop = OR low, target = entry + 2R | PASS | 0 violations |
| <= 2 trades per day | PASS | max 2 |
| <= 2 concurrent positions | PASS | max 2 |
| concurrent notional <= available capital | PASS | 0 violations |
| no trade on an earnings session | PASS | 0 violations |
| earnings skips == CSV sessions in range | PASS | expected 24, skipped 24, missing [], extra [] |
| 5 bps slippage applied on both legs | PASS | 0 violations |
| $0.005/share commission on both legs in P&L | PASS | 0 violations |
