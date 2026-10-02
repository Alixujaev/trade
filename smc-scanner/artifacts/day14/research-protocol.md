# DAY-14 — Research Protocol (v1.0)

**Status:** specification only. It runs no backtest, downloads no data, inspects no OOS data and changes no code.

**Freeze rule:** this protocol is frozen only once it is committed. The SHA-256 of this file is recorded in `research-checklist.json`. Any later change requires a new protocol version with its own commit, and results produced under v1.0 stay attributed to v1.0.

**Status vocabulary:** PREDEFINED, NOT PREDEFINED, OPEN QUESTION, NOT YET IMPLEMENTED, UNKNOWN / NOT RECORDED.

---

## 1. Current frozen research baseline (repository evidence)

| Item | Value | Evidence |
|---|---|---|
| Universe | 25 symbols: AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AVGO, AMD, QCOM, INTC, MU, AMAT, ADBE, CRM, ORCL, CSCO, COST, WMT, KO, PEP, NFLX, JNJ, JPM, XOM | `config/day_universe.py::FROZEN_DAY_UNIVERSE` |
| Market context | SPY, QQQ (diagnostic / H6 only; not part of the baseline signal) | `MARKET_BENCHMARK_SYMBOLS` |
| Bars | 5m signal/execution bars; 15m context bars; RTH only (`include_extended_hours=False`) | `backtest/multi_symbol.py` |
| Session | RTH 09:30 ≤ t < 16:00 America/New_York | `data/session.py::is_rth` |
| Research window | 2026-07-02 13:30 UTC → 2026-09-25 19:55 UTC, 60 RTH sessions (common window of all symbols) | DAY-04..12B artifacts |
| Index-context coverage | SPY/QQQ 5m from 2026-07-08; 264 baseline trades lack context | DAY-08B |
| Data provider | yfinance 1.6.0 (installed), `auto_adjust=True`, `prepost=False`, `period="60d"` for 5m/15m | `data/yfinance_provider.py`, `config/settings.py` |
| Signal population traded | setup status ∈ {DETECTED, CONFIRMED} | `ExecutionConfig.valid_statuses` |
| DETECTED | close above session VWAP with a VWAP reclaim or VWAP hold, not extended (ABOVE_VWAP excluded), no 15m bearish conflict. **RSI > 50, RVOL ≥ 2.0 and a 5m trigger are NOT required.** | `strategy/day/vwap_momentum.py` (status block) |
| CONFIRMED | DETECTED conditions + RSI(14) > 50 + RVOL ≥ 2.0 + 5m trigger + 15m bullish | same |
| Direction / overnight | long-only; no overnight positions | `backtest/execution.py` |
| Signal timing | evaluated on the closed 5m bar T (index = bar open; observable at bar end) | DAY-08B timestamp audit |
| Entry | OPEN of bar T+1, only within the same session (otherwise no trade) | `simulate_trade_execution` |
| Initial stop | SIGNAL_LOW (low of bar T) if below entry; otherwise session VWAP if below entry; otherwise entry × 0.99 | same |
| Target | entry + 2.0 × (entry − stop) | same |
| Same-bar ambiguity | STOP_FIRST | `ExecutionConfig.same_bar_rule` |
| Forced exit | first bar with ET time ≥ 15:55 exits at that bar's CLOSE (no stop/target check on that bar); also on a session change | same |
| Position limit | one open position per symbol; signals while a position is open are skipped | `backtest/day_engine.py` |
| Simulated costs | 0 bps, commission 0 | `ExecutionConfig` defaults |
| Cost scenarios | 0 / 5 / 10 bps **per side**, applied post-hoc | `backtest/dynamic_stop.py::_calc_slippage_return` |
| Benchmark | per-symbol buy & hold, first RTH open → last RTH close of the window, mean across symbols | DAY-11 metadata |
| Baseline result | 5,691 trades from 21,087 candidates; WR 30.42%; PF 0.9388; total R −738.98; 0/5/10 bps −41.19 / −99.80 / −100.00% | DAY-04, DAY-10 anchors |
| Runtime | Python 3.12.10; pandas 3.0.5; numpy 2.5.2; pyarrow 25.0.1 | observed in `.venv` |
| Dependency lock | **NONE**: `requirements.txt` unpinned, no lock file | repository |
| Universe selection date | UNKNOWN / NOT RECORDED. The code comment says "chosen before research", but there is no timestamped evidence; the universe was first committed on 2026-09-28 (`dcebe47`), after the window ended | git history |

**Baseline-definition clarification (not a change):** earlier report headers describe the strategy as "VWAP reclaim, RSI > 50, RVOL ≥ 2.0x, 5m trigger". That describes CONFIRMED only. The traded population also includes DETECTED setups; DAY-05 shows 3,760 traded rows with RVOL < 1.0 and 1,561 with RSI < 50. Future protocols must name the exact status set.

## 2. Reproducibility contract

An experiment is **not reproducible** if any MUST item below is missing. Each item is recorded in the experiment's results JSON under `reproducibility`.

**A. Code identity (MUST)**
- git commit SHA;
- clean/dirty flag; if dirty, the list of uncommitted files with their SHA-256;
- Python version;
- `pip freeze` output (or a lock file) stored as an artifact. Required because `requirements.txt` is unpinned.

**B. Data identity (MUST)**
- provider and version;
- provider call parameters (interval, period/start-end, `prepost`, `auto_adjust`);
- symbol list;
- exact first and last bar timestamp;
- interval, timezone (stored UTC; sessions America/New_York);
- session filter, extended-hours policy, closed-bar policy;
- cache directory, file count and SHA-256 manifest (per file plus a manifest digest).

**C. Strategy identity (MUST)**
- signal module and commit;
- valid status set;
- all thresholds (RSI period/threshold, RVOL lookback/min_sessions/threshold, VWAP relation rules, 15m structure lookback);
- the full `ExecutionConfig` serialised;
- stop and target definitions;
- same-bar rule, forced-exit time, position-limit rule.

**D. Experiment identity (MUST)**
- experiment ID and family ID (§10);
- hypothesis text;
- protocol file path and its commit SHA, created **before** results;
- `frozen_before_results` true/false with evidence;
- the full list of variants;
- the variant-selection rule;
- cost scenarios;
- provenance (PREDECLARED / DERIVED FROM PRIOR OBSERVATION / MIXED / UNKNOWN).

**E. Output identity (MUST)**
- artifact paths;
- JSON schema version;
- text report;
- trade-level CSV when trades exist;
- exact test command and counts;
- before/after hash comparison of the cache and every prior artifact directory.

## 3. Timestamp / point-in-time (PIT) contract

| Term | Definition (existing semantics) |
|---|---|
| bar OPEN timestamp | the DataFrame index value; stored in UTC |
| bar CLOSE (end) timestamp | open + interval (5m: +5 min; 15m: +15 min) |
| signal observation time | the CLOSE of signal bar T. `setup_time` stores the bar OPEN; the signal is usable only at `setup_time + 5m` |
| entry time | OPEN of bar T+1 = signal observation time; entry price = that bar's open |
| exit observation time | the bar in which a stop or target is touched (fill at the level); forced exit at the CLOSE of the ≥ 15:55 bar |
| `as_of` | for any decision, `as_of` = signal observation time (or, for in-trade management, the CLOSE of the bar whose information is used) |

**Rules (PREDEFINED):**
1. A decision at `as_of` may use only bars with `bar_end ≤ as_of` (`data/bars.py::filter_closed_bars`). This applies to the 5m and 15m context and to SPY/QQQ alike.
2. Future bars must never influence the signal, setup, stop, target, filter, regime, position sizing or trade eligibility.
3. In-trade state changes (for example a breakeven trigger) are recognised at a bar's CLOSE and take effect from the next bar.
4. **Mandatory PIT audit:** each experiment includes a future-data mutation test. Mutate prices, volumes and structure strictly after the decision timestamp (later bars and later sessions), and assert that every earlier decision and every earlier trade field is unchanged. This follows the existing pattern in `tests/test_day07_point_in_time.py` and `tests/test_day08_point_in_time.py`.

## 4. Market-data contract

See `data-expansion-spec.md` §1. It covers required data, warmup, and the missing / duplicate / zero-volume / malformed / timezone / DST / corporate-action policies.

## 5. Independent data and dataset split

See `data-expansion-spec.md` §2–§5.

## 6. Universe contract

**Problem:** a universe chosen with knowledge of the research period, or of which companies are still large and liquid today, can introduce selection and survivorship bias. The current 25 are all present-day mega/large caps; their selection date is UNKNOWN / NOT RECORDED.

**Policy for the next cycle:**

| Item | Rule | Status |
|---|---|---|
| Universe for the first OOS cycle | The existing 25 symbols, unchanged. It is frozen by this commit, before any OOS bar is acquired, so OOS cannot influence membership. | PREDEFINED |
| How symbols enter | No additions during a cycle | PREDEFINED |
| How symbols leave | A symbol with no data for a session (halt, delisting, ticker change) stays in the universe. Its missing sessions are recorded and excluded per session, never replaced. | PREDEFINED |
| Delisted names | No delisting data source exists; this would surface only as missing data | NOT YET IMPLEMENTED |
| Liquidity criteria / minimum price / minimum dollar volume | Not applied to the fixed 25 | NOT PREDEFINED (only needed for a rule-based universe) |
| PIT market cap | No PIT market-cap or index-constituent source in the repository | OPEN QUESTION |
| Rule-based, survivorship-safe universe | Requires PIT constituents or listings plus PIT liquidity from data available before the test period | NOT YET IMPLEMENTED |
| When membership is frozen | At the commit of the experiment's protocol file, before data acquisition | PREDEFINED |
| Forbidden | Choosing or dropping symbols based on backtest results (including DAY-05/09/10 per-symbol tables) | PREDEFINED |

## 7. Transaction-cost contract

| Item | Rule | Status |
|---|---|---|
| Scenarios | 0, 5, 10 bps **per side**, all reported, none chosen as "the" result | PREDEFINED |
| Formula | per-trade net return = (1 + g)(1 − s)/(1 + s) − 1, with g = gross return and s = bps/10,000. Entry and exit are both charged. | PREDEFINED (existing) |
| Commission | not modelled separately (it is folded into the per-side bps); `commission_per_share` stays 0 | PREDEFINED |
| Breakeven / any exit | every exit incurs cost, including BE, stop, target and forced exits | PREDEFINED (existing) |
| Gap-through fills | stops and targets fill at the level price, then the same bps applies; there is no extra gap slippage | PREDEFINED (existing), limitation below |
| Scaling | proportional to notional (bps); independent of share count and price | PREDEFINED |
| Aggregation | (a) compounded 1-unit-per-trade return in entry order; (b) **mean net trade return** and its comparison with the round trip (≈ 0.10% at 5 bps, ≈ 0.20% at 10 bps). Both are reported. | PREDEFINED |

**Known limitations** (they cannot be changed silently; any change is a separate experiment):
1. Compounding all trades sequentially at 1 unit is not a portfolio simulation; overlapping trades across symbols are chained.
2. Gap-through stop fills at the stop price understate the loss. In DAY-12B, 275 breakeven exits opened below entry; filling them at the bar open would change the result by about −84.21R.
3. There is no spread model, no market-impact model and no borrow/fee model. A single bps level is applied to all symbols regardless of liquidity.
4. 5m OHLC cannot resolve intrabar order (50.4% of baseline trades enter and exit within one bar).

## 8. Execution-semantics contract (frozen)

Frozen exactly as in §1:
- signal at the CLOSE of T; entry at the OPEN of T+1 within the same session;
- SIGNAL_LOW stop with the VWAP / 0.99 fallbacks;
- 2R target; STOP_FIRST on same-bar ambiguity;
- forced exit at the CLOSE of the first bar at or after 15:55 ET, or at the last bar before a session change;
- stop and target filled at the level price, including on gaps;
- one position per symbol; no partial fills (unsupported); no pyramiding; no shorting;
- slippage and commission per §7.

**Rule (PREDEFINED):** an execution-model change constitutes a separate future experiment with its own experiment ID and protocol. Examples: gap fills at the open, intrabar ordering, sizing, partial exits, cost model. Such a change cannot be introduced into an existing experiment, nor applied retroactively to its results.

Early-close sessions (13:00 ET) have no 15:55 bar. Existing behaviour: open positions exit at the close of the session's last bar through the session-change rule. This is kept, and such sessions are flagged in reports.

## 9. Hypothesis-freeze contract

Before any result is generated, a protocol file `artifacts/<exp-id>/protocol.md` (from `oos-protocol-template.md` or an equivalent research template) is committed. It contains:
- hypothesis, rationale, exact rule, exact parameters;
- every parameter variant and why those variants;
- the expected observable mechanism;
- primary and secondary metrics;
- cost scenarios, exclusion criteria;
- the candidate-selection rule and the stopping rule;
- the relationship to prior experiments (family ID, DERIVED flag);
- "what was known before this experiment".

The commit SHA and timestamp of the protocol must **precede** the commit or timestamp of every results artifact. The results JSON records both.

**Selection rule for multiple variants (PREDEFINED form):** "All predeclared variants are evaluated and reported. None is retained unless it meets the predeclared acceptance condition." Choosing the variant with the best observed metric is forbidden.

A threshold that is not written before results is reported as NOT PREDEFINED and cannot be added afterwards.

## 10. Multiple-hypothesis control

- Each experiment receives a unique **experiment ID** (`EXP-<YYYYMMDD>-<n>`), a **family ID** and a **variant count**.
- **Existing families:**
  - F-BASE: DAY-01..05;
  - F-GAP: DAY-06/06A;
  - F-BE: DAY-07, 07A, 12B (4 thresholds: 0.5 / 0.75 / 1.00 / 1.25R);
  - F-INDEX: DAY-08/08B;
  - F-STOPGEO: DAY-09;
  - F-FREQ: DAY-10;
  - F-TOD: DAY-11;
  - F-EXITDIAG: DAY-12A.
- An experiment directly motivated by an earlier observed result is marked **DERIVED FROM PRIOR OBSERVATION**. It cannot count as independent confirmation.
- Repeated testing of the same family on the same data is recorded as one family. The family's cumulative variant count is reported with every new result. In the existing window, 40 variant rows have been evaluated (DAY-13 matrix).
- Failed and zero-trade variants are never removed from reports.
- The existing 60-session window is **exhausted for confirmation.** New hypotheses may be explored there, but any result from it is exploratory.

## 11. OOS candidate gate

A candidate may enter OOS only if **all** of the following hold. Otherwise **OOS GATE = NO**.
1. Its rule is completely specified (§2C).
2. Its parameters are frozen.
3. Its execution semantics are frozen (§8).
4. Its transaction-cost assumptions are frozen (§7).
5. The candidate-selection rule was committed before the OOS data was acquired.
6. The OOS dataset has not been inspected beyond the permitted structural checks (`data-expansion-spec.md` §4).
7. No OOS-specific tuning will occur. The OOS run is executed once, and its result is final for that candidate.

Additional condition carried from DAY-13 (PREDEFINED): the candidate's in-sample result must itself be non-negative after the frozen cost scenarios that the OOS evaluation will use. Without that, there is nothing to confirm.

An OOS test is not forced just because a research cycle has ended. The current state is OOS GATE = NO (DAY-13).

## 12. OOS evaluation contract

Metrics are fixed now and reported for every OOS run (PREDEFINED):
- trades, wins / losses / breakevens, win rate, profit factor (on gross returns);
- expectancy (mean trade return %), total R, average R, median R;
- max drawdown and geometric (compounded) return;
- average and median holding time; exit-reason distribution;
- compounded 0 / 5 / 10 bps returns; mean net trade return at 0 / 5 / 10 bps;
- per-symbol total R and spread;
- trade-count accounting (candidates, entries, skips, simulation_none, missing-data exclusions);
- same-bar ambiguity count; gap-through fill count;
- benchmark return.

**Benchmark (PREDEFINED):** per-symbol buy & hold from the first RTH open to the last RTH close of the same OOS sessions, averaged equally across the universe. Missing symbol-sessions follow the same exclusion as the strategy. The benchmark is not selected or altered after results.

R-based metrics are never reported alone; return-based metrics and cost scenarios always accompany them.

## 13. Acceptance framework

| Criterion | Definition | Status |
|---|---|---|
| Primary metric | mean net trade return at 5 bps per side (sizing-independent) | PREDEFINED (metric) / NOT PREDEFINED (numeric threshold) |
| Primary direction | the candidate must have a non-negative primary metric | PREDEFINED (sign condition only; no magnitude threshold) |
| Secondary metrics | PF, total R, median R, max DD, compounded 0/5/10 bps, win rate | PREDEFINED (reported) / NOT PREDEFINED (thresholds) |
| Transaction-cost requirement | results reported at 0/5/10 bps; acceptance judged at 5 bps; 10 bps reported as a stress case | PREDEFINED |
| Robustness: symbols | per-symbol distribution reported; share of symbols with positive net R | PREDEFINED (reported) / NOT PREDEFINED (minimum share) |
| Robustness: concentration | top-2 symbols' share of total R | PREDEFINED (reported) / NOT PREDEFINED (limit) |
| Robustness: time | results by month / sub-period and by time-of-day bin | PREDEFINED (reported) / NOT PREDEFINED (limit) |
| Trade-count sufficiency | minimum OOS trade count | NOT PREDEFINED (no justified number from prior research) |
| Benchmark comparison | strategy vs equal-weight buy & hold over the same sessions | PREDEFINED (reported) / NOT PREDEFINED (required margin) |
| Drawdown constraint | maximum acceptable drawdown | NOT PREDEFINED |
| Data-integrity requirement | all structural checks pass; hash manifest matches; missing data documented | PREDEFINED (hard requirement) |
| PIT requirement | the future-mutation test passes for the candidate | PREDEFINED (hard requirement) |
| Reproducibility requirement | every §2 MUST item is present | PREDEFINED (hard requirement) |

A NOT PREDEFINED threshold remains NOT PREDEFINED. It is never filled in after OOS results are seen.

## 14. Research-log standard

Every experiment produces:
- `protocol.md`, committed before results;
- the results JSON, including the `reproducibility` block;
- a human-readable report;
- a trade-level CSV when applicable;
- the hash manifest, with before/after comparison;
- the test command and counts;
- the git SHA and a UTC timestamp;
- the classification and its source;
- limitations;
- provenance.

Every report contains a section titled **"What information was known before this experiment was run?"** It lists the prior artifacts and observations, by path, that the experimenter had seen.

## 15. Open methodological questions

1. Behaviour of yfinance `auto_adjust=True` on 5m/15m bars around splits and dividends: are intraday bars back-adjusted retroactively? (OPEN QUESTION)
2. Is the yfinance 60-day intraday limit measured in calendar days from the request time? This determines snapshot deadlines. (OPEN QUESTION)
3. No PIT constituent, listing or market-cap source exists, so a survivorship-safe universe is NOT YET IMPLEMENTED.
4. No dependency lock exists; future runs must store `pip freeze`. (gap)
5. RVOL uses `min_sessions=1`, so the first sessions of any window have thin baselines. Whether OOS uses research-window bars for warmup is fixed in `data-expansion-spec.md` §3.
6. Whether to replace the compounded 1-unit model with a sized portfolio model. That would be a separate experiment (§8).
7. Gap-through fill realism (DAY-12B, −84.21R). That would be a separate experiment (§8).
8. Intrabar order (5m) cannot be resolved without finer data; no 1m data source is defined. (OPEN QUESTION)
