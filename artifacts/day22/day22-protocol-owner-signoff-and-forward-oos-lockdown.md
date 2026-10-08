# DAY-22 — Protocol-Owner Sign-Off of DAY-21 + Forward OOS Lockdown

| Field | Value |
|---|---|
| **Governance Decision** | **DAY-21 HISTORICAL HOLDOUT AUDIT SIGNED OFF · V2-MOM FROZEN AND LOCKED FOR FORWARD OOS** |
| **Decided by** | **Alixujaev (protocol owner)**, 2026-10-08 |
| **Role & Mandate** | Protocol-Owner governance and formal forward OOS lockdown for the frozen systematic research chain |
| **Strategy Status** | **V2-MOM: FROZEN FOR FORWARD OOS** · **V2-STR: STOPPED** · **V2-LRV: STOPPED** |
| **Forward OOS Window** | **2026-10-08 → 2027-10-08** (Target: **252 XNYS sessions**, blind evaluation period) |
| **Starting HEAD** | `8645e9177335fe5c264361aaba7bda67c4448d98` (committed DAY-21 holdout evaluation) |
| **Evaluation Commit** | `5ed3d0ab5c2d205707d321494086bc7734f213d0` (pre-run code and predeclarations committed before execution) |
| **Frozen Protocol** | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (freeze commit `ba3cefe54ccf2fe14c62f1c609f143d8a0904221`) |
| **Stage H Snapshot** | `stage_h_20261008T100604Z`, manifest `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34` (READY per DAY-20A) |
| **Holdout Segment** | **2023-01-03 → 2026-06-02** (856 XNYS sessions; 503 lookback sessions 2021-01-04 → 2022-12-30 as signal inputs only) |
| **Forward OOS Data / Performance** | **NOT ACQUIRED · NOT LOADED · NOT COMPUTED · NOT INSPECTED** |

---

## 1. Audit of DAY-21 Historical Holdout Evaluation

The protocol owner conducted a comprehensive, independent audit of the committed DAY-21 artifacts (`artifacts/day21/day21-historical-holdout-report.md`, `artifacts/day21/day21-historical-holdout-report.json`, `artifacts/day21/v2/run_summary.json`, `artifacts/day21/v2/run_provenance.json`, and all 73 individual simulation result files).

### 1.1 Holdout Segment & Date Verification
- **Holdout Evaluation Segment**: 2023-01-03 to 2026-06-02 inclusive, spanning exactly **856 XNYS sessions**.
- **Lookback / Warmup Inputs**: 2021-01-04 to 2022-12-30 inclusive, spanning exactly **503 XNYS sessions**. These bars were strictly utilized for historical lookback inputs (e.g. 252-day momentum base) and never evaluated for trade execution or performance accounting.
- **Total Stage H Dataset**: Exactly 1,359 XNYS sessions loaded.
- **Verification Result**: **VERIFIED** against `SEGMENTS["holdout"]` in `backtest/v2/run.py` and `run_summary.json`.

### 1.2 Stage H Snapshot & Manifest Integrity
- **Snapshot ID**: `stage_h_20261008T100604Z`.
- **Committed Manifest SHA-256**: `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34`.
- **Stage H Tree SHA-256**: `8a51463b335f0f4e2acf776bd4fdfb36ca07cf52eb2d5878f3f0251d328c5556` (unchanged from DAY-20 acquisition and DAY-20A review).
- **Readiness Record**: Validated under DAY-20A review manifest `e2a7d5a72d5a12342554edff34efb3e398b10eb8db101716dbc806592f82530f`, status `READY_FOR_HISTORICAL_HOLDOUT_EVALUATION` with 18 corporate action review records applied and 0 invalid.
- **Event Set Accounting**: 415 corporate action events loaded; 1 first-session entry excluded (`ba50d815-d70c-4eb9-9b11-bcaf89a75331`, CSCO 2021-01-04); exactly 414 events utilized; 17 NVDA cash dividends retained per review record.
- **Bar Quality**: 0 missing bars; Series C (`adjustment=all`) was not loaded; execution and accounting restricted to Series A (raw OHLC) and signals restricted to Series B (point-in-time total-return index TR).
- **Verification Result**: **VERIFIED**.

### 1.3 Evaluated Strategies & Scope
- **Evaluated Families**: Only **V2-MOM** (`V2-MOM-H001`) and **V2-STR** (`V2-STR-H001`) were evaluated on the holdout segment, alongside benchmarks B1 (`V2-B1-holdout`) and B2 (`V2-B2-holdout`).
- **Non-Evaluated Family (V2-LRV)**: V2-LRV was **not evaluated** on the holdout segment. V2-LRV failed Gate 2 in the DAY-19 research evaluation (net CAGR 13.34% vs B1 18.44%) and was permanently stopped per protocol §15.3 ("Only strategies that passed the research gates are eligible for holdout evaluation"). V2-LRV was not run, not modified, and not resurrected.
- **Verification Result**: **VERIFIED**.

### 1.4 Strategy Configuration Hash Preservation
Protocol §15.7 strictly mandates that holdout evaluation must utilize the identical frozen strategy configuration SHA-256 as research:
- **V2-MOM Research Config SHA-256**: `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`
- **V2-MOM Holdout Config SHA-256**: `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` (`MATCH: EXACT`)
- **V2-STR Research Config SHA-256**: `0fc76b8a9ba8250c8fa1b399871ca6f511d5e0283f0ffe94f9085f0e38aa600e`
- **V2-STR Holdout Config SHA-256**: `0fc76b8a9ba8250c8fa1b399871ca6f511d5e0283f0ffe94f9085f0e38aa600e` (`MATCH: EXACT`)
- **Verification Result**: **VERIFIED**.

### 1.5 Gate Reproduction & Economic Verification
Holdout gates are evaluated under protocol §13 at the 5 bps primary friction scenario using unrounded float64 arithmetic:

| Strategy / Benchmark | Ending Equity ($) | Total Return | Net CAGR (0 bps) | Net CAGR (5 bps) | Net CAGR (10 bps) | Cost Drag (5 bps) | Gate 1 (≥ 0) | Gate 2 (≥ B1) | Gate A (Integrity) | Gate C (Complete) | Outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **V2-MOM** | $621,682.66 | +521.68% | 71.78% | **71.25%** (`0.71246107`) | 70.72% | 0.53 pp | **PASS** | **PASS** (+18.01 pp) | **PASS** | **PASS** | **HOLDOUT-PASSED** |
| **V2-STR** | $197,519.78 | +97.52% | 27.23% | **22.19%** (`0.22187154`) | 17.34% | 5.04 pp | **PASS** | **FAIL** (-31.05 pp) | **PASS** | **PASS** | **HOLDOUT-FAILED (economic)** |
| **B1 (Equal-Weight 25)** | $426,250.89 | +326.25% | 53.28% | **53.24%** (`0.53238805`) | 53.19% | 0.05 pp | — | — | PASS | PASS | **BENCHMARK (Primary Gate)** |
| **B2 (SPY Buy-and-Hold)** | $203,339.60 | +103.34% | 23.27% | **23.24%** (`0.23236183`) | 23.20% | 0.04 pp | — | — | PASS | PASS | **BENCHMARK (Reference)** |

- **V2-MOM Economic Gate**: Net CAGR at 5 bps of `0.7124610715568995` exceeds B1 net CAGR of `0.5323880517105726` by +18.01 percentage points. Gate 1 (>= 0) and Gate 2 (>= B1) both evaluate to `True`.
- **V2-STR Economic Gate**: Net CAGR at 5 bps of `0.22187154409624155` falls short of B1 net CAGR of `0.5323880517105726` by -31.05 percentage points. Gate 2 evaluates to `False`. Under protocol §15.10, V2-STR is permanently stopped.
- **Verification Result**: **VERIFIED**.

### 1.6 Independent Benchmark Recomputation
- Primary benchmark B1 and reference benchmark B2 were recomputed via an independent standalone algorithm bypassing engine code.
- Ending equity at 0 bps:
  - B1 Engine: `$426,674.59336522804` vs Independent Recompute: `$426,674.5934` (`MATCH: EXACT`)
  - B2 Engine: `$203,540.07310664203` vs Independent Recompute: `$203,540.0731` (`MATCH: EXACT`)
- **Verification Result**: **VERIFIED**.

### 1.7 Determinism & Anti-Lookahead Audit
- **Determinism**: 73 of 73 output result files across runs are byte-identical (excluding `run_provenance.json` volatile runtime timestamps).
  - `run_summary.json` SHA-256: `019095d42644fd5e00d4855e744b60602249ed73147637edf502949bf98b9d36`
  - Combined result files SHA-256: `c75ec15a341f23d23375b6d8983dcf7b772c22219f6f1579ecd357a043ea790e`
  - Combined fills SHA-256: `c6b5585877166c4145e9aff98674fb19a3cf403f87ce9548ab590b7f35ca1bc6`
- **Engine Blobs**: At run time, engine SHA-256s matched the committed blobs in commit `5ed3d0ab5c2d205707d321494086bc7734f213d0`.
- **Anti-Lookahead Suite (§7)**: All point-in-time checks passed:
  - Index truncation test: 29 sessions checked; TR on truncated slices equals the full series.
  - Decision mutation and deletion tests: 6 sampled decision sessions for V2-MOM and 19 for V2-STR; future bar alterations produce identical historical decisions.
  - Fill-source verification: All 1,850 fills executed at 5 bps matched Series A raw open prices exactly.
  - Timing verification: All fills executed strictly at the open of session $t+1$ following decision close at $t$.
- **Regression Invariance**: Re-running the research evaluation from the refactored codebase reproduced all 90 DAY-19 research result files byte-identically.
- **Verification Result**: **VERIFIED**.

### 1.8 Strict Data Isolation & Protocol Freeze
- The last session loaded and processed was **2026-06-02**.
- No market data past 2026-06-02 was requested, loaded, accessed, or evaluated.
- No network requests were permitted (socket access globally refused).
- No post-result tuning occurred: code and predeclarations were committed in `5ed3d0a` before running holdout backtests.
- **Verification Result**: **VERIFIED**.

### 1.9 Procedural Deviations
- **P1 — Calendar-Year Diagnostic Labelling**: In `backtest/v2/metrics.py`, the calendar-year subperiod diagnostic routine was configured to flag only 2017 as partial. As a consequence, 2026 (spanning 2026-01-02 to 2026-06-02) is labelled "full" in diagnostic outputs, and `worst_year` includes a diagnostic text note referring to 2017.
  - **Ruling**: Classified as **non-gating cosmetic reporting defect**.
  - **Rationale**: All underlying equity curves, returns, and gate metrics are mathematically exact. The frozen protocol strictly prohibits post-run tampering with results. This deviation is recorded for transparency and does not affect any gate decision.
- **P2 — Holm Adjustment Parameter ($m=2$)**: Holm multiple-hypothesis adjustment for active return diagnostics was executed with $m=2$ rather than $m=3$, because V2-LRV was rejected during research and excluded from the holdout evaluation (§15.3).
  - **Ruling**: Classified as **non-gating; fully valid**.
  - **Rationale**: Predeclared prior to the run in `artifacts/day21/day21-predeclared-holdout-config.json` (commit `5ed3d0a`).
- **Verification Result**: **VERIFIED**.

### 1.10 Scientific Context & Anti-Overclaiming Affirmation
The protocol owner expressly affirms the methodological caveats documented in the DAY-21 report:
1. **No Statistically Proven Alpha**: The HAC Newey-West $t$-statistic for V2-MOM's active return over B1 at 5 bps is $t = 1.38$, with a $p$-value of **0.166** (Holm-adjusted $p = 0.166$). V2-MOM's active outperformance does **not** achieve statistical significance at standard significance thresholds ($p > 0.05$).
2. **Extreme Asset Concentration**: V2-MOM performance is heavily concentrated; the top-2 performing symbols account for **43% of total absolute P&L** (HHI = 0.081).
3. **Temporal Inconsistency**: V2-MOM trailed B1 in two out of four calendar years (2023: +53.0% vs +63.4%; 2025: +19.4% vs +30.8%). Its cumulative outperformance is heavily driven by 2024 (+54.8% vs +39.5%) and partial 2026 (+119.9% vs +43.0%).
4. **Survivorship and Hindsight Bias**: The 25-symbol universe represents mega-cap survivor equities selected with 2026 hindsight.
5. **Pseudo-OOS vs Forward OOS**: Historical holdout is a pseudo-out-of-sample period that could not be fully blinded from the protocol authors. It does not constitute forward out-of-sample validation.

---

## 2. Formal Strategy Post-Holdout Status

Pursuant to protocol §§13, 15.6, 15.10, and the DAY-21 audit findings, the definitive governance status for all three strategy families is recorded as:

| Strategy Family | Research Phase | Historical Holdout Phase | Forward OOS Eligibility | Formal Governance Status | Directive |
|---|---|---|---|---|---|
| **V2-MOM** | **PASSED** | **PASSED** | **ELIGIBLE** | **FROZEN FOR FORWARD OOS** | Advanced to 252-session forward blind evaluation period (§15.6) |
| **V2-STR** | **PASSED** | **FAILED (economic)** | **NOT ELIGIBLE** | **STOPPED** | Permanently terminated (§15.10); no tuning, no rerun, no rescue |
| **V2-LRV** | **FAILED (economic)** | **NOT RUN** | **NOT ELIGIBLE** | **STOPPED** | Permanently terminated (§15.3); never evaluated on holdout |

**Governance Rule Enforcement**:
- No winner selection was performed between strategies: V2-MOM advances exclusively because it is the sole family that satisfied all protocol gates on both research and holdout.
- Neither V2-STR nor V2-LRV shall be reopened, modified, re-parameterized, or reconsidered under protocol v2.

---

## 3. Forward OOS Lockdown & Blind Evaluation Governance

A formal governance lockdown is hereby enacted for **V2-MOM**.

### 3.1 Forward OOS Window & Duration
- **Start Date**: **2026-10-08**
- **End Date**: **2027-10-08**
- **Target Duration**: Exactly **252 XNYS trading sessions**.
- **Calendar Determination**: The exact closing date and final session count will be established strictly by the frozen protocol's `exchange_calendars` 4.13.2 `XNYS` schedule when the formal OOS evaluation is executed at the close of the forward period.

### 3.2 Strict Blind-Period Restrictions
To prevent forward lookahead, data leakage, and adaptive bias, the forward period is governed by strict blind-evaluation rules:
1. **Configuration Lockdown**:
   - Strategy configuration SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` is permanently locked.
   - Zero parameter modifications.
   - Zero universe adjustments.
   - Zero signal calculation modifications.
   - Zero ranking or tie-breaker modifications.
   - Zero execution rule modifications.
   - Zero cost model modifications.
   - Zero portfolio sizing or cash management modifications.
2. **Total Blind Evaluation (No Interim Peeking)**:
   - **STRICTLY PROHIBITED** to compute interim forward CAGR, Sharpe ratio, Sortino ratio, max drawdown, win rate, total return, or P&L.
   - **STRICTLY PROHIBITED** to inspect, summarize, monitor, or visualize forward strategy performance.
   - **STRICTLY PROHIBITED** to create or run interim dashboards, performance trackers, reports, notebooks, or continuous evaluation jobs revealing forward metrics.
   - Operational data feeds, if maintained for external operational systems, must strictly isolate raw ingestion and must never calculate or expose forward strategy performance during the blind evaluation window.
3. **No Forward Data Acquisition**:
   - No forward market data may be acquired into the research cache until the 252-session waiting period has concluded and the formal forward evaluation step is executed under the protocol.
4. **No Forward-Guided Protocol Mutations**:
   - Observations of market conditions, regime shifts, or macroeconomic trends during the blind period shall not be used to propose protocol changes, branch forks, or new strategy variants.

### 3.3 Affirmation of Data Isolation
The protocol owner and automated agent certify that:
- Zero forward market data has been acquired into the research environment.
- Zero forward strategy performance has been computed, inspected, or estimated.
- The repository state remains completely isolated from forward market observations.

---

## 4. Frozen V2-MOM Configuration Identity

To ensure that the strategy evaluated after 252 forward sessions is mathematically and operationally identical to the strategy that passed DAY-21, the exact configuration identity is recorded below:

| Dimension | Specification | Identity Reference |
|---|---|---|
| **Strategy Family** | V2-MOM (Cross-sectional momentum 12-1, long-only) | Protocol §5.1, `artifacts/day16/research-protocol-v2.json` |
| **Strategy Config SHA-256** | `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` | Canonical JSON hash of strategy, execution, costs, portfolio, price series |
| **Engine Implementation Commit** | `5ed3d0ab5c2d205707d321494086bc7734f213d0` | Verified byte-identical blobs in `backtest/v2/` |
| **Protocol Version** | `2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4` | Freeze commit `ba3cefe54ccf2fe14c62f1c609f143d8a0904221` |
| **Universe Definition** | `FROZEN_DAY_UNIVERSE` (25 US equities): AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AVGO, AMD, QCOM, INTC, MU, AMAT, ADBE, CRM, ORCL, CSCO, COST, WMT, KO, PEP, NFLX, JNJ, JPM, XOM | Shared fixed universe; SPY for B2 benchmark |
| **Signal Formula** | $r_{\text{mom}}(t) = \frac{TR(t-21)}{TR(t-252)} - 1$ | Series B (Point-in-time Total Return index), excludes bar $t$ close |
| **Decision Timing** | Close of the last XNYS session of each calendar month | Derived via rule-based calendar month-end flags |
| **Eligibility & Ranking** | Valid $TR(t-21)$ and $TR(t-252)$; ranked descending by $r_{\text{mom}}$; ties resolved by ascending alphabetical ticker | Top 5 equities selected |
| **Target Weights & Sizing** | Equal weight 20% (0.20) of $E_{\text{open}}$ across selected 5 names; max 5 positions | Long-only; no leverage; no shorting; fractional shares (float64) |
| **Cash Management** | Cash returns 0.0%; residual cash, unallocated weight, and dividends remain cash until next rebalance | Cash non-negative constraint strictly enforced |
| **Order Execution** | Market-on-open $t+1$ at raw open price $O(t+1)$ (Series A) | Sells executed first; buys scaled by $\lambda = \min(1, \frac{K}{B(1+s)})$ if required |
| **Cost Model** | Linear friction $s \cdot \sum |\text{traded notional}|$ charged at execution | Scenarios: 0 bps, 5 bps (primary gate), 10 bps stress test |
| **Primary Benchmark (B1)** | Equal-weight 25 buy-and-hold basket of universe | Rebalanced at segment start |
| **Reference Benchmark (B2)** | SPY 100% buy-and-hold | Reference comparison |
| **Calendar Definition** | `exchange_calendars` version 4.13.2, calendar code `XNYS` | Timezone: America/New_York |

---

## 5. Governance Safety Checklist

Before formal sign-off and local commit, all ten mandatory governance safety assertions were verified:

- [x] **1. No forward data acquired**: Stage H remains the latest data snapshot (`stage_h_20261008T100604Z`).
- [x] **2. No forward performance computed**: No CAGR, Sharpe, Drawdown, or return calculated for dates $\ge$ 2026-06-03.
- [x] **3. No strategy code modified**: Engine implementation in `backtest/v2/` remains completely unmodified.
- [x] **4. No protocol rule modified**: Protocol version remains `2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4`.
- [x] **5. No historical holdout result modified**: Holdout artifacts from commit `8645e91` are untouched and preserved.
- [x] **6. No V2-STR resurrection**: V2-STR is recorded as permanently STOPPED (§15.10).
- [x] **7. No V2-LRV resurrection**: V2-LRV remains permanently STOPPED (§15.3).
- [x] **8. No winner selection between strategies**: V2-MOM proceeds solely because it is the only family that passed holdout gates.
- [x] **9. No new parameters introduced**: Strategy parameter set remains 100% frozen.
- [x] **10. No hidden thresholds introduced**: Evaluation gates strictly adhere to the predefined §13 formulas.

---

## 6. Exact Next Task

In strict adherence to protocol §§15.6 and 3.9, the next research task is defined uniquely as:

> **Wait for completion of the frozen 252-session forward OOS period, then run the final V2-MOM forward OOS evaluation without any tuning, protocol changes, or retrospective rule changes.**
