# ORB diagnostics: signal selection bias and trade excursions

Inputs: `artifacts/orb/smoke_test/trades.csv`, `skips.csv`, `metrics.json`; bars `data/cache/<T>_5m.parquet` (same files as the smoke test). No backtest was rerun, no network, no code changed.

## A. How simultaneous signals are chosen

- `strategy/day/orb_rules.py:simulate_session` walks one timeline; at each bar it processes entries `sorted(entries.get(ts, []), key=lambda s: s.symbol)` and each must pass `DayRiskGate.block_reason()` (max 2 trades/day, realised R > -2, max 2 open).
- Effective rule: **time priority** (earlier entry bar wins) then **alphabetical** order for signals on the same bar.
- `scripts/backtest_orb.py` does not reorder anything.

- Signals: 154 = 95 selected + 59 rejected (reasons: {'max_trades_per_day': 59}).
- Rejected because a same-bar, alphabetically earlier symbol took the slot (**alphabetical_tiebreak**): 11; rejected because earlier-bar entries had filled the day (**time_priority**): 48.
- Entry bars with more than one signal: 24.

| Alpha rank | Symbols | Signals | Selected | Rejected | of which alphabetical | Selection rate |
|---|---|---|---|---|---|---|
| 1-5 | AAPL, ADBE, AMAT, AMD, AMZN | 37 | 25 | 12 | 1 | 67.6% |
| 6-10 | AVGO, COST, CRM, CSCO, GOOGL | 16 | 7 | 9 | 2 | 43.8% |
| 11-15 | INTC, JNJ, JPM, KO, META | 34 | 22 | 12 | 2 | 64.7% |
| 16-20 | MSFT, MU, NFLX, NVDA, ORCL | 38 | 24 | 14 | 3 | 63.2% |
| 21-25 | PEP, QCOM, TSLA, WMT, XOM | 29 | 17 | 12 | 3 | 58.6% |

<details><summary>Per symbol</summary>

| Rank | Symbol | Signals | Selected | Rejected | Alphabetical rejections |
|---|---|---|---|---|---|
| 1 | AAPL | 12 | 8 | 4 | 0 |
| 2 | ADBE | 7 | 3 | 4 | 0 |
| 3 | AMAT | 4 | 3 | 1 | 0 |
| 4 | AMD | 11 | 9 | 2 | 1 |
| 5 | AMZN | 3 | 2 | 1 | 0 |
| 6 | AVGO | 2 | 1 | 1 | 0 |
| 7 | COST | 3 | 2 | 1 | 1 |
| 8 | CRM | 3 | 1 | 2 | 0 |
| 9 | CSCO | 3 | 0 | 3 | 1 |
| 10 | GOOGL | 5 | 3 | 2 | 0 |
| 11 | INTC | 11 | 9 | 2 | 1 |
| 12 | JNJ | 7 | 5 | 2 | 0 |
| 13 | JPM | 3 | 1 | 2 | 0 |
| 14 | KO | 4 | 1 | 3 | 1 |
| 15 | META | 9 | 6 | 3 | 0 |
| 16 | MSFT | 4 | 1 | 3 | 1 |
| 17 | MU | 14 | 10 | 4 | 2 |
| 18 | NFLX | 5 | 2 | 3 | 0 |
| 19 | NVDA | 8 | 7 | 1 | 0 |
| 20 | ORCL | 7 | 4 | 3 | 0 |
| 21 | PEP | 2 | 0 | 2 | 0 |
| 22 | QCOM | 4 | 3 | 1 | 1 |
| 23 | TSLA | 15 | 9 | 6 | 1 |
| 24 | WMT | 5 | 3 | 2 | 1 |
| 25 | XOM | 3 | 2 | 1 | 0 |

</details>

No P&L is computed for rejected signals (that would be outcome-driven selection).

### Proposed point-in-time ranking variants (NOT implemented; must be fixed before any evaluation)

Each ranks only the signals competing for a slot at the same entry bar; time priority stays; symbol order remains only as the final deterministic tie-break.

1. **Breakout-bar relative volume** (higher first): `volume_ratio` at the signal bar - the same series `is_volume_confirmed` already uses (rolling mean of bars <= signal). Lookahead risk: low; it must not use the entry bar's or the day's total volume. Caveat: IEX volume is not consolidated.
2. **Prior-session liquidity** (higher first): previous session RTH dollar volume (sum close x volume). Uses only completed earlier sessions -> no intraday lookahead. Risk: it favours mega-caps (a structural, not alphabetical, preference) and needs >= 1 prior session (first session N/A).
3. **Normalised breakout strength** (higher first): (signal close - OR high) / (OR high - OR low), from the OR bars and the signal bar only. Lookahead risk: low if computed at signal close; must not use the entry bar open or later bars.

## B. Trade excursions (MFE / MAE in R)

Window = entry bar (entry at its open) through the exit bar. Exit bar: FORCE_EXIT uses only the 15:55 open; STOP uses the low only down to the fill and excludes the high (intrabar order unknown; backtest is STOP_FIRST). No bar before entry or after exit is used (asserted). R = risk_per_share = entry open - OR low.

| Group | Trades | MFE median | MFE mean | MAE median | MAE mean | Reached 1R | 1.5R | 2R | Realised R mean |
|---|---|---|---|---|---|---|---|---|---|
| ALL | 95 | 0.45 | 0.58 | 0.46 | 0.50 | 17.9% | 6.3% | 0.0% | -0.06 |
| STOP | 13 | 0.15 | 0.30 | 1.00 | 1.00 | 7.7% | 7.7% | 0.0% | -1.07 |
| TARGET | 0 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| FORCE_EXIT_1555 | 82 | 0.53 | 0.62 | 0.41 | 0.42 | 19.5% | 6.1% | 0.0% | 0.10 |

- N/A excursions: 0
- TARGET group: no trade exited at target in the smoke test (N/A, not zero).
- Descriptive only (60 IEX sessions); not used to choose any parameter.
