# ORB SIP snapshot diagnostic (descriptive; not independent evidence)

- Range: 2026-07-02 → 2026-09-25 (60 sessions)
- Universe: 25 tickers; with trades: AAPL, ADBE, AMAT, AMD, AMZN, AVGO, COST, CRM, GOOGL, INTC, JNJ, KO, META, MSFT, MU, NFLX, NVDA, ORCL, QCOM, TSLA, WMT, XOM
- Data: Alpaca SIP snapshot `research_20261006T095201Z` (research segment 2026-07-02 → 2026-09-25, RTH only, no warmup; network blocked (socket connect refused)); earnings: `config\earnings_calendar.csv`
- Source: Alpaca SIP raw (v1.1 research snapshot research_20261006T095201Z, hash-pinned; research segment 2026-07-02..2026-09-25)
- **Descriptive diagnostic only:** a re-run on the same 60 sessions previously examined with yfinance data. Not independent evidence and not strategy validation (ORB-SIP-D5).
- SIP results are reported on their own. Prior yfinance run: `artifacts/orb/smoke_test/report.md`, referenced by path only; no deltas or numeric comparison.
- SIP volume differs from yfinance volume and can change the 20-bar volume-confirmation outcomes.
- No warmup segment is supplied, so the first session (2026-07-02) has no prior close for any symbol.
- Corporate actions: prices are raw. Events for 2026-07-02 → 2026-09-25 are unknown (no event data was acquired) and could affect the rolling 20-bar volume filter and the raw prior-close $5 minimum-price filter (ORB-SIP-D4). Whether protocol v1.1 §18 governs ORB is not decided.
- Decision record: `artifacts/orb/sip_diagnostic_decision.md`.

| Metric | ORB | Equal-weight B&H |
|---|---|---|
| Trades | 101 | — |
| Win rate | 48.51% | — |
| Net return | -1.54% | 4.66% |
| CAGR (annualised from 60 sessions - not meaningful evidence) | -6.31% | 21.10% |
| Max drawdown | -2.61% | -4.65% |
| Sharpe (daily, √252) | -1.9619 | 1.4628 |
| Sortino (daily, √252) | -2.5575 | 2.5316 |

- Exits: {'STOP': 13, 'TARGET': 0, 'FORCE_EXIT_1555': 88, 'SESSION_END': 0}
- Costs: commission $49.23, slippage $1222.81 (both included in every trade's P&L (entry_fill/exit_fill and 2 x $0.005/share))
- Skips: {'no_prior_close': 25, 'max_trades_per_day': 81, 'earnings_day': 24}; earnings-skipped symbol-sessions: 24
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
