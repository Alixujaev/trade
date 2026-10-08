# DAY-19 — Frozen v2 Research Execution (Stage R, Research segment)

| Field | Value |
|---|---|
| Starting HEAD | `8b8b586495ce99002d055e37f87e40c029c9da56` (DAY-18L sign-off; on origin) |
| Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (frozen). Freeze commit `ba3cefe`. |
| Data | Stage R snapshot `stage_r_20261007T093410Z`, manifest `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`. Events come from the signed-off v2.0.4 review output (manifest `755c905e…`): 486 events used (483 dividends + 6 splits, minus 3 first-session dividends). |
| Research segment | 2017-02-01 → 2022-12-30, **1490** sessions |
| Warmup | 2016-01-04 → 2017-01-31, **272** sessions (inputs only) |
| Holdout / forward OOS | **Not accessed.** The last session loaded is 2022-12-30. No Stage H or Stage F data exists. |
| **Result** | **V2-MOM RESEARCH-PASSED · V2-STR RESEARCH-PASSED · V2-LRV RESEARCH-FAILED (economic)** |

## 1. Methodology
- **Specifications:** the frozen v2 specifications were executed exactly.
  - **V2-MOM:** month-end; `TR(t−21)/TR(t−252)−1`; top 5 at 0.20.
  - **V2-STR:** ISO-week-end; `z = (r5 − mean r5)/(σ60·√5)` with σ including R(t); 5 lowest at 0.20.
  - **V2-LRV:** 252-session formation, greedy-disjoint 5 closest SSD pairs, frozen σ; 126-session cycles; strict `|S| > 2σ`; buy the lagging member only; exit on `s0·S ≤ 0` or at period end.
- **Signals:** series B, the PIT total-return index from raw closes and events.
- **Execution:** fills at the raw open t+1 (series A). Each open follows the §8.4 order: events, then `E_open`, then sells, then buys with λ.
- **Accounting:** fractional shares; no leverage; dividends as cash on the ex-date; splits scale shares. The initial decision at 2017-01-31 follows §8.14; decisions at the last close are discarded.
- **Costs:** 0/5/10 bps per side, each a separate simulation, including the segment-end liquidation.
- **Benchmarks:** B1 is the equal-weight 25-name buy-and-hold; B2 is SPY. Both use the same engine, costs and sessions.
- **Protocol-owner decisions recorded before any result** (`artifacts/day19/day19-predeclared-definitions.json`, SHA-256 `926e4926…`):
  1. **V2-LRV per-slot λ.** Frozen §6.2 ("entire slot capital", "no cross-slot lending") conflicts with the single global λ of §8.4. The §8.4 formula is applied per entering slot with K = that slot's cash, so λ = 1/(1+s). This applies to V2-LRV only and has no effect at 0 bps.
  2. **Predeclared formulas for non-gated diagnostics:** episode return, HHI normalisation, HAC p-value (normal), drawdown series, worst month/year and calendar-year subperiods.
- **No other choices were made.** No parameter, threshold, universe, cost, benchmark or period was changed. There was no winner selection.

## 2. Data validation
- **Sessions:** research 1490 and warmup 272, both asserted.
- **Bars:** 52/52 series OK with **0 missing bars**, so the §8.6 missing-bar paths are implemented but were never triggered.
- **Snapshot:** manifest and all 63 entries verified before the run and re-verified after it (tree SHA unchanged). Series C (adjustment=all) is never loaded.
- **Events:** every event ex-date is a session. There is no same-day split + dividend and no unsupported event type.

## 3. Implementation validation
- **Engine:** new `backtest/v2/` (data, signals, engine, metrics, run). No v2 portfolio engine existed before (DAY-16 Q14).
- **Tests:** `tests/test_day19_v2_research.py` **17 passed**. Full suite **1297 passed, 0 failed**.
- **Independent check:** a pandas buy-and-hold recompute that uses no engine code matches the engine exactly at 0 bps (B1 E_T 272,278.8239; B2 E_T 181,566.7705).
- **Defects fixed before any Stage R result:**
  - V2-LRV `sign()` failed on numpy floats.
  - V2-LRV dividends were missing from the turnover denominator.
  - Formation was moved to the t_F close, as the PIT semantics require.
- **Technical re-run (§14):** run 1 stopped while writing `run_summary.json` (a numpy bool JSON serialisation error). Its result files already written were then overwritten by an identical-configuration re-run after the fix. The fix touches output serialisation only.

## 4. Strategy results (Research segment, E₀ = 100,000)
| Family | Cost | Ending equity | Total return | CAGR | Max DD | Sharpe | Sortino | Ann. turnover | Trades | Rebalances | Exposure mean | Cash mean | Symbols held (mean) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V2-MOM | 0 bps | 455,143 | 355.1 % | 29.21 % | 36.0 % | 0.92 | 1.29 | 3.07 | 435 | 71 | 0.9996 | 0.0004 | 5.0 |
| V2-MOM | **5 bps** | 446,912 | 346.9 % | **28.82 %** | 36.0 % | 0.91 | 1.28 | 3.06 | 435 | 71 | 0.9996 | 0.0004 | 5.0 |
| V2-MOM | 10 bps | 438,833 | 338.8 % | 28.42 % | 36.1 % | 0.90 | 1.27 | 3.06 | 435 | 71 | 0.9996 | 0.0004 | 5.0 |
| V2-STR | 0 bps | 475,627 | 375.6 % | 30.18 % | 34.9 % | 1.08 | 1.58 | 40.70 | 2735 | 309 | 0.9999 | 0.0001 | 5.0 |
| V2-STR | **5 bps** | 373,736 | 273.7 % | **24.98 %** | 35.2 % | 0.94 | 1.36 | 40.68 | 2735 | 309 | 0.9999 | 0.0001 | 5.0 |
| V2-STR | 10 bps | 293,685 | 193.7 % | 19.99 % | 35.6 % | 0.79 | 1.14 | 40.66 | 2735 | 309 | 0.9999 | 0.0001 | 5.0 |
| V2-LRV | 0 bps | 212,845 | 112.8 % | 13.63 % | 17.3 % | 1.04 | 1.55 | 2.40 | 139 | 12 cycles | 0.447 | 0.553 | 2.24 |
| V2-LRV | **5 bps** | 209,726 | 109.7 % | **13.34 %** | 17.3 % | 1.02 | 1.52 | 2.40 | 139 | 12 cycles | 0.447 | 0.553 | 2.24 |
| V2-LRV | 10 bps | 206,654 | 106.7 % | 13.06 % | 17.4 % | 1.00 | 1.49 | 2.40 | 139 | 12 cycles | 0.447 | 0.553 | 2.24 |

**Cost drag** (gross − net CAGR):
- V2-MOM: 0.40 pp at 5 bps, 0.79 pp at 10 bps.
- **V2-STR: 5.20 pp at 5 bps, 10.19 pp at 10 bps.** Its annual turnover is about 41×.
- V2-LRV: 0.28 pp at 5 bps, 0.57 pp at 10 bps.

**Mean / min λ:** 0.999 at 5 bps (0.9995 for LRV). Per-cost values for executions, cost per execution, dividends, episodes, breadth, concentration and HHI are in `day19-research-report.json` and `v2/<experiment>/<cost>/metrics.json`.

## 5. Benchmark results
| Benchmark | 0 bps CAGR | 5 bps CAGR | 10 bps CAGR | 5 bps total return | Max DD |
|---|---|---|---|---|---|
| B1 equal-weight 25 (primary) | 18.46 % | **18.44 %** | 18.42 % | 172.0 % | 44.6 % |
| B2 SPY (reference, not gated) | 10.61 % | 10.60 % | 10.58 % | 81.4 % | 32.4 % |

**Strategy minus benchmark at 5 bps:**

| Family | CAGR − B1 | CAGR − B2 | Tracking error vs B1 | Information ratio vs B1 |
|---|---|---|---|---|
| V2-MOM | +10.38 pp | +18.22 pp | 15.7 % | 0.67 |
| V2-STR | +6.54 pp | +14.38 pp | 15.6 % | 0.36 |
| V2-LRV | **−5.10 pp** | +2.75 pp | 20.6 % | −0.35 |

## 6. Economic gate (§13.B, 5 bps, unrounded float64)
| | 0 bps | 5 bps | 10 bps |
|---|---|---|---|
| V2-MOM | 29.21 % | 28.82 % | 28.42 % |
| V2-STR | 30.18 % | 24.98 % | 19.99 % |
| V2-LRV | 13.63 % | 13.34 % | 13.06 % |

| | 5 bps net CAGR (unrounded) |
|---|---|
| V2-MOM | 0.28816164633146335 |
| V2-STR | 0.24978852160383114 |
| V2-LRV | 0.13344464778558618 |
| B1 | 0.1844074874473387 |
| B2 | 0.10600 (reference) |

| | Gate 1: CAGR ≥ 0 | Gate 2: CAGR ≥ B1 | Gate A | Gate C | **Final** |
|---|---|---|---|---|---|
| V2-MOM | PASS | PASS | PASS | PASS | **RESEARCH-PASSED** |
| V2-STR | PASS | PASS | PASS | PASS | **RESEARCH-PASSED** |
| V2-LRV | PASS | **FAIL** | PASS | PASS | **RESEARCH-FAILED (economic)** |

## 7. Robustness (§16; reporting only, no threshold, cannot change any gate)
1. **Cost sensitivity:** see §4. V2-STR is highly cost-sensitive. At 10 bps its margin over B1 shrinks to +1.57 pp.
2. **Calendar years at 5 bps** (strategy / B1):

   | Family | 2017 (partial) | 2018 | 2019 | 2020 | 2021 | 2022 |
   |---|---|---|---|---|---|---|
   | V2-MOM | 37.3 / 31.6 | −1.4 / 3.2 | 61.8 / 42.8 | 119.0 / 68.1 | 12.5 / 40.2 | −17.2 / −40.5 |
   | V2-STR | 38.8 / 31.6 | 22.8 / 3.2 | 58.3 / 42.8 | 43.3 / 68.1 | 28.4 / 40.2 | −24.7 / −40.5 |
   | V2-LRV | 8.0 / 31.6 | 9.6 / 3.2 | 11.5 / 42.8 | 41.7 / 68.1 | 21.5 / 40.2 | −7.7 / −40.5 |

   V2-MOM's excess over B1 is concentrated in 2019–2020 and 2022, and it trails B1 in 2018 and 2021.
3. **Breadth and concentration at 5 bps:**

   | Family | Breadth | Top-2 share of \|P&L\| | HHI |
   |---|---|---|---|
   | V2-MOM | 0.72 | **0.47** | 0.066 |
   | V2-STR | 0.76 | 0.23 | 0.044 |
   | V2-LRV | 0.68 | 0.25 | 0.060 |

   About half of V2-MOM's absolute P&L comes from two symbols.
4. **Turnover, λ and cost drag:** see §4.
5. **Exposure and benchmark-relative behaviour:** V2-LRV is invested 44.7 % of the time on average and holds cash otherwise, at 0 % interest (Q7). Its gap to B1 is largely low exposure in a strongly rising sample. Tracking error and information ratio are in §5.
6. **Drawdown profile at 5 bps:**

   | Family | Max DD | Worst month | Worst year |
   |---|---|---|---|
   | V2-MOM | 36.0 % | 2018-10 (−20.5 %) | 2022 (−17.2 %) |
   | V2-STR | 35.2 % | 2018-10 (−14.5 %) | 2022 (−24.7 %) |
   | V2-LRV | 17.3 % | 2022-01 (−9.5 %) | 2022 (−7.7 %) |
   | B1 | 44.6 % | — | 2022 (−40.5 %) |
7. **Statistical diagnostic** (HAC Newey–West lag 5, active return vs B1, Holm across 3 families, 5 bps):

   | Family | t | p | Holm p |
   |---|---|---|---|
   | V2-MOM | 1.64 | 0.101 | 0.303 |
   | V2-STR | 0.88 | 0.377 | 0.671 |
   | V2-LRV | −0.96 | 0.336 | 0.671 |

   **No family's active return vs B1 is statistically significant.** This is a diagnostic only.

## 8. Anti-lookahead audit (§7; Gate A1/A5/A6)
| Test | Result |
|---|---|
| Index test (TR on data truncated at k equals the full TR; 37 sessions) | **PASS** |
| Truncation test (decisions on data cut at t equal the full run; MOM 8, STR 32, LRV 150 sampled decision closes) | **PASS** |
| Future-mutation test (all bars and events after t perturbed, plus a fake split) | **PASS** |
| Future-deletion test (all bars and events after t deleted) | **PASS** |
| Fill-source test (3335 fills at 5 bps each equal the raw open of their session) | **PASS** |
| Execution-timing test (every fill at the open after its decision close; LRV period-end exits at the cycle start; all fills inside Research) | **PASS** |
| Structural checks | Series C is never loaded. No session after 2022-12-30 is loaded. Signals read TR only, and fills and marks read raw OHLC only. |

**Audit result: no lookahead violation detected.**

## 9. Determinism (§13.A3, §17)
- **In-process:** a second simulation of all 15 (family × cost) runs gave identical fills, decisions, executions and equity.
- **Two-process:** a second CLI run into a scratchpad directory gave **91/91 result files byte-identical**. Only `run_provenance.json` differs, and it holds only UTC times and the command.
- **Hashes:** `run_summary.json` SHA-256 `698b8c3bbea9ca304a9a2d7f1095e82e0de7fb137a2fc7d1e06ad88bface32cf`; combined result hash `7042cfa5…09ce0c`; combined fills hash `73092275…8960ca`.
- **Strategy-config SHA-256:** MOM `62827d70…`, STR `0fc76b8a…`, LRV `0beffbe1…`.
- **Engine identity:** the git tree was dirty at run time (DAY-19 code and artifacts uncommitted). The run recorded the SHA-256 of every `backtest/v2/*.py` file, and these are checked against the DAY-19 commit.

## 10. Conclusion
- **V2-MOM: RESEARCH-PASSED.** Net CAGR at 5 bps is 28.82 % against B1's 18.44 %.
- **V2-STR: RESEARCH-PASSED.** Net CAGR at 5 bps is 24.98 % against 18.44 %. It is highly cost-sensitive.
- **V2-LRV: RESEARCH-FAILED (economic).** Net CAGR at 5 bps is 13.34 %, below B1's 18.44 %. Per §15.3 it is never run on the holdout and is not modified.
- **v2 research gate: YES.** Per §15.4, V2-MOM and V2-STR proceed **unchanged** to the one-shot historical holdout. There is no winner selection (§14).
- **What a pass means and does not mean (§13.B, §20):** a pass is only minimum in-sample viability on one hindsight-selected, survivorship-biased mega-cap universe (Q5) over a strong bull sample. Momentum is plausibly favoured by that bias. No active return is statistically significant. Neither family is "validated".

**Not done:** no holdout or forward access, no tuning or parameter change, no re-run for a better result, no push.
