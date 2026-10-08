# DAY-21 — Frozen Historical Holdout Evaluation (V2-MOM, V2-STR)

| Field | Value |
|---|---|
| **Final status** | **FROZEN HISTORICAL HOLDOUT EVALUATION COMPLETED SUCCESSFULLY** |
| **Outcome** | **V2-MOM HOLDOUT-PASSED · V2-STR HOLDOUT-FAILED (economic)** |
| Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (frozen; unchanged) |
| Starting HEAD | `6dfd638` |
| Evaluation commit | `5ed3d0a`: code and predeclarations committed **before** the run; clean tree; the engine SHA-256 equals the committed blobs |
| Data | Stage H `stage_h_20261008T100604Z`, manifest `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34`. READY per DAY-20A (18 records applied). Tree unchanged from DAY-20. |
| Holdout segment | **2023-01-03 → 2026-06-02, 856 sessions.** The 503-session lookback (2021-01-04 → 2022-12-30) is used for signal inputs only. |
| Families | **V2-MOM, V2-STR** (both research-passed, run together). V2-LRV is **not run** (§15.3). The configuration is **identical to research:** strategy-config SHA-256 MOM `62827d70…`, STR `0fc76b8a…` (§15.7). |
| Forward OOS / new data | Not accessed / none acquired |

## 1. Holdout results (E₀ = 100,000)
| Family | Cost | Ending equity | Total return | CAGR | Max DD | Sharpe | Sortino | Ann. turnover | Trades | Rebalances | Exposure mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V2-MOM | 0 bps | 628,280 | 528.3 % | 71.78 % | 26.9 % | 1.76 | 2.79 | 2.99 | 253 | 42 | 0.9996 |
| V2-MOM | **5 bps** | 621,683 | 521.7 % | **71.25 %** | 26.9 % | 1.75 | 2.77 | 2.99 | 253 | 42 | 0.9996 |
| V2-MOM | 10 bps | 615,159 | 515.2 % | 70.72 % | 26.9 % | 1.74 | 2.76 | 2.99 | 253 | 42 | 0.9996 |
| V2-STR | 0 bps | 226,609 | 126.6 % | 27.23 % | 27.7 % | 1.13 | 1.68 | 40.30 | 1571 | 179 | 0.9999 |
| V2-STR | **5 bps** | 197,520 | 97.5 % | **22.19 %** | 29.8 % | 0.96 | 1.42 | 40.28 | 1571 | 179 | 0.9999 |
| V2-STR | 10 bps | 172,169 | 72.2 % | 17.34 % | 32.3 % | 0.79 | 1.16 | 40.26 | 1571 | 179 | 0.9999 |

**Cost drag (gross − net CAGR):** MOM 0.53 pp at 5 bps and 1.06 pp at 10 bps. **STR 5.04 pp at 5 bps and 9.89 pp at 10 bps.**

## 2. Benchmark results
| Benchmark | 0 bps CAGR | 5 bps CAGR | 10 bps CAGR | 5 bps total return | Max DD |
|---|---|---|---|---|---|
| B1 equal-weight 25 (primary) | 53.28 % | **53.24 %** | 53.19 % | 326.3 % | 25.1 % |
| B2 SPY (reference, not gated) | 23.27 % | 23.24 % | 23.20 % | 103.3 % | 18.3 % |

**Strategy minus benchmark at 5 bps:**

| Family | CAGR − B1 | CAGR − B2 |
|---|---|---|
| V2-MOM | +18.01 pp | +48.01 pp |
| V2-STR | **−31.05 pp** | −1.05 pp |

An independent buy-and-hold recompute, written without engine code, matches B1 and B2 **exactly** (E_T at 0 bps: 426,674.5934 and 203,540.0731).

## 3. Gate outcomes (§13, 5 bps, unrounded float64; identical to research)
| Family | Net CAGR 5 bps | B1 net CAGR 5 bps | Gate 1 (≥ 0) | Gate 2 (≥ B1) | Gate A | Gate C | **Status** |
|---|---|---|---|---|---|---|---|
| V2-MOM | 0.7124610715568995 | 0.5323880517105726 | PASS | PASS | PASS | PASS | **HOLDOUT-PASSED** |
| V2-STR | 0.22187154409624155 | 0.5323880517105726 | PASS | **FAIL** | PASS | PASS | **HOLDOUT-FAILED (economic)** |

## 4. Non-gated diagnostics (cannot pass, fail, rank or rescue a family)
- **HAC (Newey–West lag 5), active return vs B1, at 5 bps, Holm with m = 2 as predeclared:**

  | Family | t | p | Holm p |
  |---|---|---|---|
  | V2-MOM | 1.38 | 0.166 | 0.166 |
  | V2-STR | −2.05 | 0.040 | 0.080 |

  **V2-MOM's outperformance of B1 is not statistically significant.**
- **Tracking error and information ratio vs B1 at 5 bps:**

  | Family | Tracking error | Information ratio |
  |---|---|---|
  | V2-MOM | 17.9 % | 0.79 |
  | V2-STR | 19.0 % | −1.19 |
- **Breadth, top-2 concentration and HHI at 5 bps:**

  | Family | Breadth | Top-2 share of \|P&L\| | HHI |
  |---|---|---|---|
  | V2-MOM | 0.74 | **0.43** | 0.081 |
  | V2-STR | 0.76 | 0.21 | 0.046 |
- **Calendar years at 5 bps** (strategy / B1):

  | Family | 2023 | 2024 | 2025 | 2026 (partial to 06-02) |
  |---|---|---|---|---|
  | V2-MOM | 53.0 / 63.4 | 54.8 / 39.5 | 19.4 / 30.8 | 119.9 / 43.0 |
  | V2-STR | 22.8 / 63.4 | −3.3 / 39.5 | 27.5 / 30.8 | 30.4 / 43.0 |

  V2-MOM **trails B1 in 2023 and 2025**, and its excess is concentrated in 2024 and partial-2026.
- **Worst month at 5 bps:** MOM 2025-03 (−11.3 %); STR 2024-08 (−11.8 %).

## 5. Data and integrity validation
- **Before the run:** the Stage H manifest was verified, and the DAY-20A READY validation was checked (manifest `e2a7d5a7…`, 18 applied, 0 invalid).
- **Event set:** 415 events − 1 first-session (CSCO 2021-01-04) = 414; the 17 NVDA dividends are retained by record.
- **Bars:** 0 missing; series C (adjustment=all) is not loaded; the last session loaded is 2026-06-02.
- **Snapshots and records:** Stage H was re-verified after the run (tree `8a51463b…`, unchanged from DAY-20). Stage R, all earlier outputs and every review record are unchanged.
- **Anti-lookahead (§7): all PASS.** Index test (29 sessions); truncation, future-mutation and future-deletion tests (MOM 6, STR 19 sampled decisions); fill-source test (1850 fills at 5 bps each equal the raw open); execution-timing test (every fill at the open t+1, all inside the holdout).

## 6. Determinism and reproducibility
- **In-process:** an identical second simulation of every run matched.
- **Two CLI runs:** **73/73 result files byte-identical** (`run_provenance.json` excluded).
- **Hashes:** `run_summary.json` SHA-256 `019095d4…`; combined result hash `c75ec15a…`; combined fills hash `c6b55858…`.
- **Engine identity:** the engine SHA-256s equal the committed `5ed3d0a` blobs. At run time the git tree held only the run's own outputs (allowed by §17).
- **Tests:** 4 new DAY-21 tests; 61 focused; **full suite 1310 passed, 0 failed**.
- **Research regression:** after the refactor, the Research evaluation reproduced all 90 DAY-19 result files byte-identically.

## 7. Procedural deviations (none affects any number or gate)
- **P1:** the calendar-year labels in the DAY-19 metrics code mark only 2017 as partial. In the holdout artifacts, 2026 (to 06-02) is labelled "full", and `worst_year` carries a "2017 is partial" note. This is cosmetic, non-gated, and was not changed after the run.
- **P2:** Holm uses m = 2 because V2-LRV is not run (§15.3). This was predeclared before the run.

## 8. Interpretation (normative)
- **V2-MOM — HOLDOUT-PASSED** means it survived a **historical pseudo-OOS** that the protocol authors could not blind themselves to (§3.6, §15.11). It is **not forward-OOS validation** and **not statistically proven alpha:**
  - the HAC p-value vs B1 is 0.17
  - the universe is a hindsight-selected set of survivors (Q5)
  - the excess is uneven by year and concentrated in a few symbols
- **V2-STR — HOLDOUT-FAILED (economic).** It stops here (§15.10) and is not modified, re-run or rescued.
- **No winner selection:** V2-MOM proceeds alone only because it is the only family that passed (§15.6).

## 9. Next research task
Protocol-owner review and sign-off of this DAY-21 result. After that, per §15.6 and §3.9, **wait until the 252-session forward OOS period (2026-10-08 → about 2027-10-08) has ended** before acquiring Stage F for **V2-MOM only**. No forward data may be acquired or inspected, and no forward performance computed, in the interim.
