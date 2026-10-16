# ORB SIP diagnostic: entry-time signal strength, STOP vs FORCE_EXIT_1555 (descriptive, exploratory)

Inputs (read only): `artifacts/orb/sip_diagnostic_excursions/trade_excursions.csv` and `artifacts/orb/sip_diagnostic/trades.csv`. No snapshot or parquet access, no engine, no backtest, no network. One-off code was kept outside the repository. Source run: Alpaca SIP raw 5m RTH snapshot `research_20261006T095201Z`, research segment 2026-07-02 to 2026-09-25.

## Already-viewed disclosure

The STOP and FORCE_EXIT_1555 medians of F1, F2 and F3, and a stop-distance (F5) summary, were seen in earlier reports before this plan was written. This analysis is exploratory and descriptive. It is not blind, not confirmatory, and makes no claim of significance or predictive power.

## Methods

- Groups: `exit_reason` STOP (n=13) and FORCE_EXIT_1555 (n=88). The group label is never a predictor.
- R = `risk_per_share` = entry_open - or_low (known at the entry bar's open, not at the signal close).
- F1 signal close - OR high (USD; % of OR high; R). F2 signal close - session RTH VWAP (USD; % of VWAP). F3 signal volume / mean of the last 20 five-minute bars including the signal bar (strategy baseline). F4 OR width (USD; % of entry_open). F5 R as % of entry_open. F6 (entry_open - OR high) / R. F7 entry_open - signal close (USD; % of signal close; R). F8 minutes after 09:45 ET of the signal bar. F9 order (1 or 2) of the trade among the session's executed trades, same-bar ties in alphabetical (engine) order.
- F1-F3 are copied from recorded columns; F4-F9 are reconstructed from CSV fields only.
- Mechanical links: F6 = 1 - F4_usd / R and F6 = F1_R + F7_R; F4, F5 and F6 are not independent.
- Statistics per group: n, median, IQR (p25-p75), min, max, mean. Cliff's delta = P(STOP > FORCE) - P(STOP < FORCE); positive means STOP values tend to be higher. Descriptive only: no p-values, thresholds, ranking, feature selection or models. Every predeclared feature is reported.

## Validations (all passed; any failure would have stopped before writing)

101 trades, 13 STOP, 88 FORCE_EXIT_1555; one-to-one join on symbol, session and entry_time; exit_reason, signal_time, entry_open and risk_per_share agree across files; entry = signal + 5 minutes; R = entry_open - or_low; F1/F2/F3 recorded values reproduce from their components; both F6 identities hold; F1 > 0, F2 > 0 and F3 >= 1.5 for every trade (the strategy's entry conditions); F8 on the 5-minute grid within 0-70 and EDT throughout; F9 in {1, 2}; no missing values; no excluded column used.

## Table 1: feature summary

| Feature | Tier | Unit | STOP median [p25, p75] | STOP min / max / mean | FORCE median [p25, p75] | FORCE min / max / mean | Cliff's delta |
|---|---|---|---|---|---|---|---|
| F1_R | primary | R | 0.1871 [0.07711, 0.2554] (n=13) | 0.006706 / 0.5469 / 0.1823 | 0.1817 [0.08916, 0.2632] (n=88) | 0.003094 / 0.6613 / 0.1915 | -0.066 |
| F1_pct | primary | % | 0.2158 [0.1411, 0.3309] (n=13) | 0.008665 / 2.589 / 0.4403 | 0.3549 [0.237, 0.6752] (n=88) | 0.01032 / 1.992 / 0.4905 | -0.292 |
| F2_pct | primary | % | 0.6262 [0.5854, 0.8087] (n=13) | 0.3695 / 2.584 / 0.8737 | 0.9912 [0.6712, 1.266] (n=88) | 0.2735 / 2.849 / 1.069 | -0.309 |
| F3 | primary | ratio | 1.829 [1.763, 2.116] (n=13) | 1.504 / 2.298 / 1.912 | 2.06 [1.705, 2.397] (n=88) | 1.53 / 3.486 / 2.111 | -0.217 |
| F4_pct | primary | % of entry | 1.316 [1.199, 1.687] (n=13) | 0.4892 / 2.928 / 1.515 | 1.852 [1.306, 2.729] (n=88) | 0.6662 / 5.214 / 2.109 | -0.329 |
| F1_usd | secondary | USD | 0.4909 [0.3095, 0.985] (n=13) | 0.085 / 14.86 / 1.691 | 1.315 [0.5663, 2.724] (n=88) | 0.0294 / 11.03 / 1.908 | -0.365 |
| F2_usd | secondary | USD | 1.929 [1.457, 2.916] (n=13) | 0.7241 / 14.83 / 3.054 | 3.167 [1.647, 5.243] (n=88) | 0.2016 / 24.24 / 4.582 | -0.283 |
| F4_usd | secondary | USD | 3.95 [2.67, 5.98] (n=13) | 1.05 / 12.9 / 5.045 | 6.259 [3.383, 11.74] (n=88) | 0.67 / 36.97 / 9.096 | -0.288 |
| F5_pct | secondary | % of entry | 1.65 [1.292, 1.828] (n=13) | 0.6222 / 4.615 / 1.941 | 2.332 [1.749, 3.201] (n=88) | 0.9307 / 6.097 / 2.596 | -0.385 |
| F6_R | secondary | R | 0.1511 [0.07699, 0.2491] (n=13) | -0.01815 / 0.5438 / 0.1759 | 0.1876 [0.09, 0.2617] (n=88) | -0.004642 / 0.6613 / 0.1916 | -0.100 |
| F7_R | secondary | R | -0.00313 [-0.01285, 0.003413] (n=13) | -0.03597 / 0.009472 / -0.00643 | 0 [-0.002318, 0.002252] (n=88) | -0.0232 / 0.0264 / 0.0001008 | -0.285 |
| F7_usd | secondary | USD | -0.015 [-0.05, 0.01] (n=13) | -0.315 / 0.07 / -0.03369 | 0 [-0.01625, 0.02125] (n=88) | -0.23 / 0.36 / 0.01095 | -0.260 |
| F7_pct | secondary | % of signal close | -0.01089 [-0.0147, 0.007011] (n=13) | -0.0434 / 0.01264 / -0.00822 | 0 [-0.005059, 0.007038] (n=88) | -0.04313 / 0.05248 / 0.0009092 | -0.290 |
| F8_min | secondary | minutes | 0 [0, 0] (n=13) | 0 / 20 / 2.692 | 0 [0, 10] (n=88) | 0 / 70 / 8.864 | -0.232 |
| F9_order | secondary | 1 or 2 | 1 [1, 2] (n=13) | 1 / 2 / 1.385 | 1 [1, 2] (n=88) | 1 / 2 / 1.455 | -0.070 |

## Table 2: the 13 STOP trades (entry-time features only)

| Symbol | Session | F1 R | F1 % | F2 % | F3 | F4 % | F5 % | F6 R | F7 R | F8 min | F9 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AMZN | 2026-07-07 | 0.211 | 0.331 | 0.771 | 1.61 | 1.26 | 1.57 | 0.198 | -0.013 | 5 | 2 |
| AMAT | 2026-07-16 | 0.547 | 2.589 | 2.584 | 2.12 | 2.11 | 4.61 | 0.544 | -0.003 | 20 | 2 |
| COST | 2026-07-28 | 0.007 | 0.009 | 0.504 | 1.76 | 1.32 | 1.29 | -0.018 | -0.025 | 0 | 1 |
| WMT | 2026-07-28 | 0.187 | 0.226 | 0.632 | 2.25 | 1.02 | 1.21 | 0.151 | -0.036 | 0 | 2 |
| AAPL | 2026-07-29 | 0.274 | 0.294 | 0.565 | 1.79 | 0.78 | 1.07 | 0.272 | -0.001 | 0 | 1 |
| INTC | 2026-08-05 | 0.289 | 0.974 | 1.599 | 1.96 | 2.39 | 3.34 | 0.284 | -0.004 | 0 | 1 |
| AMAT | 2026-08-13 | 0.091 | 0.122 | 0.605 | 1.50 | 1.20 | 1.33 | 0.101 | 0.009 | 0 | 1 |
| TSLA | 2026-08-14 | 0.078 | 0.141 | 0.588 | 2.19 | 1.66 | 1.81 | 0.084 | 0.006 | 0 | 1 |
| INTC | 2026-08-28 | 0.068 | 0.216 | 1.120 | 2.02 | 2.93 | 3.15 | 0.072 | 0.003 | 0 | 2 |
| NVDA | 2026-09-04 | 0.077 | 0.141 | 0.626 | 2.30 | 1.69 | 1.83 | 0.077 | -0.000 | 0 | 1 |
| NVDA | 2026-09-16 | 0.232 | 0.144 | 0.370 | 1.79 | 0.49 | 0.62 | 0.214 | -0.018 | 0 | 1 |
| GOOGL | 2026-09-22 | 0.255 | 0.446 | 0.809 | 1.83 | 1.31 | 1.74 | 0.249 | -0.006 | 0 | 1 |
| TSLA | 2026-09-23 | 0.055 | 0.090 | 0.585 | 1.74 | 1.55 | 1.65 | 0.059 | 0.004 | 10 | 2 |

## Table 3: sample structure

- Trades 101 (STOP 13, FORCE_EXIT_1555 88); symbols 22 (STOP 9, FORCE 21); sessions 56 (STOP 12, FORCE 55).
- Trades per session: {'1': 11, '2': 45} (trades: number of sessions).
- STOP trades per symbol: {'AAPL': 1, 'AMAT': 2, 'AMZN': 1, 'COST': 1, 'GOOGL': 1, 'INTC': 2, 'NVDA': 2, 'TSLA': 2, 'WMT': 1}.
- Sessions with more than one STOP: {'2026-07-28': 2}.
- F9 counts: STOP {'1': 8, '2': 5}; FORCE_EXIT_1555 {'1': 48, '2': 40}.

## Caveats and leakage safeguards

- Excluded from every feature: exit time and prices, hold duration, MFE/MAE, +1R/+2R reach, give-back, stop-bar fields, realised P&L and R, target, fills, shares and caps. Inputs were restricted to a column whitelist.
- Small, uneven samples (13 vs 88) with repeated symbols and paired same-day trades; observations are not independent. Differences describe this run only.
- Selection: executed trades only. Cap-skipped signals (81) and earnings-skipped symbol-sessions (24) are excluded; same-bar ties were resolved alphabetically by the engine.
- Raw prices; no corporate-action data (events could distort F3 and the prior-close filter on ex-dates); 5-minute bars; SIP volume may differ from yfinance volume; first session has no prior close.
- Descriptive re-run on sessions already examined; not independent evidence or strategy validation. Not compared or pooled with any yfinance artifact. No strategy, parameter or risk-rule change follows.
