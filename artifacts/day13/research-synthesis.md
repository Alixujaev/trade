# DAY-13 — Research Synthesis (DAY-01 → DAY-12B)

**Nature of this document:** analysis only. No backtest was run, no rule was added, and no parameter was searched. Every number comes from existing artifacts. `research-matrix.json` carries a source path for each value, extracted programmatically from the artifact JSONs. Fields that cannot be established from the repository are marked **UNKNOWN / NOT RECORDED**.

**Frozen dataset shared by DAY-04 → DAY-12B:**
- 25 symbols (`config/day_universe.py`);
- 2026-07-02 → 2026-09-25, 60 RTH sessions, yfinance 5m cache;
- 5,691 baseline trades from 21,087 candidate signals.

**Cost model shared by DAY-04 → DAY-12B** (`backtest/dynamic_stop.py::_calc_slippage_return`):
- "X bps" is applied **per side**, so the round trip is ≈2X: 5 bps per side ≈ 0.10% round trip, 10 bps per side ≈ 0.20%.
- It is applied post-hoc to a return compounded over **all trades in entry order at 1 unit per trade**, with no position sizing.

---

## 1. Research matrix (summary)

| ID | Type | Tested rule | Variants | Provenance | Population | Classification |
|---|---|---|---|---|---|---|
| DAY-01 | strategy definition | VWAP reclaim/hold + RSI>50 + RVOL≥2 + 5m trigger + 15m context | 1 | UNKNOWN | — (no artifact) | UNKNOWN / NOT RECORDED |
| DAY-02 | execution model | T+1 open, SIGNAL_LOW stop, 2R, STOP_FIRST, 15:55 exit | 1 | UNKNOWN | — (no artifact) | UNKNOWN / NOT RECORDED |
| DAY-03 | infrastructure | fast causal engine ≡ reference engine (speed; not parameter optimisation) | n/a | UNKNOWN | n/a | engineering; no benchmark artifact |
| DAY-04 | baseline measurement | DAY-01 + DAY-02 on 25 symbols | 1 | UNKNOWN | 5,691 (sequential engine) | negative gross and net (no label) |
| DAY-05 | diagnostic | failure decomposition | n/a | UNKNOWN | 5,691 | diagnostic |
| DAY-06 | selection filter | abs gap ≥ 2%, premarket RVOL ≥ 2× | 3 (B, C: 0 trades) | UNKNOWN | filtered subsets | NOT VALIDATED (research log) |
| DAY-06A | selection filter | gap ≥ 1/2/3/4% | 4 | MIXED | filtered subsets | descriptive robustness |
| DAY-07 | exit management | BE at +1R (closed bar, next-bar activation) | 1 | MIXED | 5,691 paired | NOT VALIDATED (research log) |
| DAY-07A | exit management | BE at 0.75/1.00/1.25R | 3 | MIXED | 5,691 paired | descriptive ("not a profitable edge") |
| DAY-08/08B | selection filter | SPY / QQQ / both bullish context | 3 | MIXED | subsets of the 5,691 | NOT VALIDATED (research log) |
| DAY-09 | stop geometry | ATR_5m(14) × 0.50/0.75/1.00/1.25 | 4 | MIXED | 5,691 paired | NOT VALIDATED (commit `2396974` only) |
| DAY-10 | entry gate | max entries per symbol-session 1–5 | 5 | MIXED | sequential engine | INCONCLUSIVE |
| DAY-11 | entry gate | ET entry windows (4 restricted) | 4 | MIXED | sequential engine | INCONCLUSIVE |
| DAY-12A | diagnostic | path MFE/MAE, two exit-bar conventions | 2 conventions | DERIVED | 5,691 | MECHANISM INCONCLUSIVE |
| DAY-12B | exit management | BE at +0.5R | 1 | DERIVED | 5,691 paired | MECHANISM INCONCLUSIVE |

**Common to every experiment:**
- date range: the one 60-session window above (DAY-01/02/03: UNKNOWN);
- symbols: the same 25;
- costs: 0 / 5 / 10 bps per side;
- OOS eligibility: **NOT ELIGIBLE**, with a per-experiment reason in the matrix.

**Inconsistencies in existing artifacts** (reported, not modified):
- DAY-07A section 11 text (+38.6..+48.9R, 32.74%, 1,023 BE exits) contradicts its own table (+93.9 / +47.9 / +8.5R, 32.4%, 1,140). The table is used.
- The DAY-08B findings text (59.97% / 2,278) contradicts its own eligibility table (60.39% excluded / 2,254 eligible). The table is used.
- The original DAY-08 artifact used lagged timestamp semantics and is superseded by DAY-08B.
- The DAY-09 status is recorded only in commit `2396974`, not in the artifact.
- DAY-05 MFE uses the full-bar (optimistic) convention: its 61.5% / 40.53% equal DAY-12A UPPER_BOUND, not PRIMARY.
- The DAY-12A artifact predates the code's `bar_resolution_limit` block (left untouched).
- DAY-06/07/08 classifications come from the research log; their artifacts carry no status field.

## 2. Evidence hierarchy

| ID | A. Diagnostic finding | B. Mechanism effect | C. Gross (0 bps) improvement | D. Cost-robust edge |
|---|---|---|---|---|
| DAY-04 | Baseline PF 0.9388, total R −738.98, mean trade −0.0083% | — | — (baseline) | **NOT ESTABLISHED** (5 bps −99.80%) |
| DAY-05 | 50.4% of trades exit in the entry bar (total R −1,140.4); 73.4% have stops <0.25% (total R −616.0); 70.4% of traded sessions have ≥2 trades | — | — | n/a |
| DAY-06 | premarket RVOL untestable (0 volume) | gap filter cuts trades by 85% | gap ≥ 2%: PF 1.01, compounded −0.47% (vs −41.19%) | **NOT ESTABLISHED** (5 bps −57.05%) |
| DAY-06A | stop distance widens with gap threshold | monotonic subset; trades 2,010 → 210 | compounded −19.63 / −0.47 / +0.63 / +5.66% | **NOT ESTABLISHED** (best 5 bps −14.36% at 4%) |
| DAY-07 | — | 523 STOP→BE, 222 TARGET→BE | mixed: total R +47.9 but PF 0.94 → 0.92 and compounded −44.25% | **NOT ESTABLISHED** (−99.81%) |
| DAY-07A | — | BE exits 1,140 / 830 / 570 | total R improves for all three; compounded better only at 0.75R (−37.71%) | **NOT ESTABLISHED** (≈ −99.8%) |
| DAY-08 | 264 trades lack index context | trades cut 60–68% | smaller total loss; PF > baseline only for SPY (0.9686); H6-C avg R worse | **NOT ESTABLISHED** (5 bps −86.70% .. −92.09%) |
| DAY-09 | stop geometry is the main loss driver (DAY-05 bins) | exit mix shifts; 1R is a different risk unit per variant | compounded −19.53 / −12.69 / +1.34 / −27.24% (not monotonic) | **NOT ESTABLISHED** (−99.66% .. −99.75%) |
| DAY-10 | first trade per session PF 1.0224 vs later trades 0.87–0.89 | entries 5,691 → 1,168..3,680 | PF and avg R above baseline for every cap; CAP 1 +3.58% | **NOT ESTABLISHED** (−67.79% .. −98.21%) |
| DAY-11 | — | entries restricted by window | PF and avg R above FULL for 3 of 4 windows; no PF > 1 | **NOT ESTABLISHED** (−81.55% .. −98.28%) |
| DAY-12A | losers reaching +1R before exit: 14.68% (PRIMARY) .. 40.53% (UPPER_BOUND); 50.4% single-bar trades | — | n/a | n/a |
| DAY-12B | — | 984 STOP→BE, 379 TARGET→BE, 179 FORCED→BE | total R +156.11; PF 0.9522; compounded −23.73% | **NOT ESTABLISHED** (−99.74%) |

Levels A, B and C are **not** collapsed into D. Column D is not established for any experiment.

## 3. Data-snooping audit

**Rule applied:** an experiment is PREDECLARED only if a protocol predating its results is in the repository. **None is.** Artifacts calling variants "pre-declared" (DAY-06A, DAY-07, DAY-07A, DAY-09, DAY-10, DAY-11) are therefore at most **MIXED**. Analyst-written status criteria (DAY-11, DAY-12A, DAY-12B) are labelled as such in their artifacts.

| ID | Provenance | Prior observation that motivated it |
|---|---|---|
| DAY-01..05 | UNKNOWN | committed together in `dcebe47`; internal order not recorded |
| DAY-06 | UNKNOWN | 2.0% labelled a "research assumption"; committed with DAY-05 |
| DAY-06A | MIXED | exists because DAY-06 showed a gross gap effect |
| DAY-07 | MIXED | DAY-05: 40.53% of losers reached +1R (full-bar convention) |
| DAY-07A | MIXED | robustness of DAY-07 |
| DAY-08 | MIXED | DAY-04 already reported SPY/QQQ market-context diagnostics |
| DAY-09 (H4) | MIXED | DAY-05 stop-distance table (stops <0.25% lose most) |
| DAY-10 (H3) | MIXED | DAY-05 repeated-entry table |
| DAY-11 (H5) | MIXED | DAY-05 time-of-day table |
| DAY-12A | DERIVED FROM PRIOR OBSERVATION | recurring cost sensitivity DAY-06..11 |
| DAY-12B | DERIVED FROM PRIOR OBSERVATION | 0.5R chosen after DAY-12A |

**Specific concerns:**
- **DAY-12B is post-hoc and in-sample.** It cannot serve as independent confirmation of anything. Its 0.5R is the 4th threshold of the breakeven family already tested at 0.75 / 1.00 / 1.25R (DAY-07/07A) on the same data.
- **Multiple comparisons on one window:** 40 variant rows were evaluated on the same 60 sessions. Choosing the best gross variant of any family (gap 4%, CAP 1, ATR × 1.00, MORNING, BE 0.75R / 0.5R) would be in-sample selection.
- Every experiment uses one 60-session in-sample window. There is no held-out period.

## 4. Transaction-cost audit

**Central question:** *does any tested mechanism show a robust positive result after realistic costs?* **No.** Among the 38 variant rows with trades, none has a non-negative 5 bps or 10 bps compounded return. The two DAY-06 rows with 0 trades are excluded.

| Experiment / variant | 0 bps | 5 bps | 10 bps |
|---|---|---|---|
| DAY-04 baseline | −41.19% | −99.80% | −100.00% |
| DAY-06 gap ≥ 2% | −0.47% | −57.05% | −81.48% |
| DAY-06 positive gap ≥ +2% (subset) | +15.84% | −34.83% | −63.35% |
| DAY-06A gap ≥ 1 / 2 / 3 / 4% | −19.63 / −0.47 / +0.63 / +5.66% | −89.24 / −57.05 / −32.02 / −14.36% | −98.56 / −81.48 / −54.09 / −30.60% |
| DAY-07 BE 1.0R | −44.25% | −99.81% | −100.00% |
| DAY-07A BE 0.75 / 1.00 / 1.25R | −37.71 / −44.25 / −44.03% | −99.79 / −99.81 / −99.81% | −100% (all) |
| DAY-08B SPY / QQQ / both | −10.99 / −20.82 / −16.83% | −90.66 / −92.09 / −86.70% | −99.02 / −99.21 / −97.87% |
| DAY-09 ATR × 0.50 / 0.75 / 1.00 / 1.25 | −19.53 / −12.69 / +1.34 / −27.24% | −99.73 / −99.71 / −99.66 / −99.75% | −100% (all) |
| DAY-10 CAP 1 .. CAP 5 | +3.58 .. −28.96% | −67.79 .. −98.21% | −89.98 .. −99.95% |
| DAY-11 MORNING .. NO_LATE | −11.68 .. −29.30% | −81.55 .. −98.28% | −96.15 .. −99.96% |
| **DAY-12B baseline** | **−41.19%** | **−99.80%** | **−100%** |
| **DAY-12B +0.5R BE** | **−23.73%** | **−99.74%** | **−100%** |

**Sizing-independent check:**
- The largest mean gross trade return of any variant is **+0.0288%** (DAY-06A gap ≥ 4%, 210 trades).
- The round-trip cost at 5 bps per side is **≈0.10%**, and **≈0.20%** at 10 bps.
- No variant's average gross trade return covers even the 5 bps-per-side round trip.

**Caveat on the compounded figures:** compounding all trades sequentially at 1 unit is not a portfolio simulation and exaggerates terminal values. The mean-trade comparison above does not depend on sizing and leads to the same conclusion.

**DAY-12B specifically:** it improves gross performance (−41.19% → −23.73%; +156.11R) but does **not** establish transaction-cost robustness (−99.74% at 5 bps). About 84.21R of its +156.11R gross gain depends on 275 gap-through breakeven exits being filled at entry rather than at the bar open.

## 5. What has been learned (supported by artifacts)

1. **The frozen baseline has no edge before costs** (PF 0.9388, mean trade −0.0083%; DAY-04) and collapses under costs (5 bps −99.80%).
2. **Very tight stops dominate the baseline geometry.**
   - 73.4% of trades have a stop distance below 0.25%, and they account for −616.0R of the total (DAY-05).
   - Every ATR-scaled stop multiplier improved gross R and compounded return (DAY-09), though not monotonically.
   - Both are associations on in-sample data, not demonstrated causation.
3. **Half of all trades end in the entry bar.** 2,869 trades (50.4%) carry a total R of −1,140.4 (DAY-05, DAY-12A). At 5m resolution their intrabar path cannot be observed.
4. **Repeated same-session entries degrade aggregate quality.**
   - The first trade per session has PF 1.0224; trades #2..#5+ have PF 0.87–0.89.
   - Every cap 1–5 raised PF and avg R over no cap (DAY-10).
   - The effect is not cost-robust.
5. **Time-of-day effects are weak and non-monotonic.**
   - Total R is worst at 15:00–15:55 (−198.8R) and best at 09:30–10:00 (−47.6R).
   - No restricted window reached PF > 1 (DAY-05, DAY-11).
6. **Gap (stock-in-play) filters improve gross metrics as the threshold tightens,** while trade counts collapse (2,010 → 210). They remain negative at 5 and 10 bps (DAY-06/06A). Premarket RVOL could not be tested (DAY-06).
7. **Index-regime filters mostly reduce total loss by removing trades.** Per-trade quality is not consistently better: H6-C avg R is worse than the baseline (DAY-08B).
8. **Breakeven rules materially change the exit distribution at every tested threshold** (0.5, 0.75, 1.00, 1.25R). Gross effects are mixed: total R improves in all four, while the compounded return improves only at 0.5R and 0.75R. None is cost-robust (DAY-07/07A/12B).
9. **The favorable excursion of eventual losers is real but its size is bounded by resolution.** Between 14.68% and 40.53% of losers reached +1R before exit, depending on the unobservable intrabar order (DAY-12A).
10. **Average gross edge per trade is below the round-trip cost in every variant tested** (section 4).

## 6. What has NOT been established

"Not validated" means the in-sample evidence does not support the claim. It does **not** mean the idea is proven impossible.

- **No transaction-cost-robust day-trading edge** has been validated for the DAY-01 signal under DAY-02 execution.
- **No validated exit-management edge:** BE at 0.5 / 0.75 / 1.00 / 1.25R (DAY-07, 07A, 12B).
- **No validated frequency-cap edge** (DAY-10, INCONCLUSIVE).
- **No validated index-regime edge** (DAY-08/08B).
- **No validated time-window edge** (DAY-11, INCONCLUSIVE).
- **No validated stock-in-play selection edge** (DAY-06/06A). The premarket-RVOL and catalyst components were never testable.
- **No validated ATR-stop edge** (DAY-09).
- **No result has been tested out of sample.** All evidence comes from one 60-session in-sample window on 25 large caps.
- **The size of the "missed favorable excursion" is not established beyond a bound** (14.68%–40.53% of losers reaching +1R) because of 5m resolution.
