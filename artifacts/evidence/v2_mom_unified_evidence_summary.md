# V2-MOM: unified evidence summary (DAY-19/21, DAY-25B, DAY-29, DAY-30)

| Field | Value |
|---|---|
| Date | 2026-10-19 |
| Repository state | `feature/day-trading-research` at HEAD `4829060d142589c971a98e39adaef4fa0588b6ba`, which equals `origin`. The working tree was clean before this file was created. |
| Nature | Review and synthesis only. No study, replay, backtest or data acquisition was run. Only synthetic test suites were re-run. No F003, `fwd-gate2`, P001 or sealed data was accessed. |
| Labels | **FACT**: verified from a repository file during this review. **REPORTED**: stated in a repository report, not recalculated here. **ASSUMPTION**. **INFERENCE**. **REC**: recommendation. |

---

## 1. Executive decision and confidence

**REC: pause V2-MOM research and development.** Run no further historical robustness studies, and do not start a new paper-trading evaluation now. Let the already pre-registered, untouched forward gate `fwd-gate2` (`V2-MOM-F003`) run **unchanged** to its evaluation, no earlier than 2026-12-09 16:15 America/New_York. Take the next V2-MOM decision on that result.

**Confidence**
- **That V2-MOM has a durable, generalisable edge over B1: low.**
  - The edge is not statistically significant in either segment: HAC p = 0.101 in research and 0.166 in holdout, at 5 bps.
  - It is concentrated in a few tickers and a few days.
  - Every piece of evidence comes from one hindsight-selected survivor universe.
- **That pausing is the right next step: medium.** INFERENCE: further analysis of the same historical data cannot materially change the decision. The only untouched evidence is already scheduled.

**Not recommended:** live trading on the basis of these studies, under any option.

---

## 2. Evidence table

All figures are at 5 bps, V2-MOM vs B1 (equal-weight 25-name buy-and-hold), unless stated otherwise. **These four groups are not independent confirmations.** They analyse the same strategy, universe and price history.

| | **DAY-19 research / DAY-21 historical holdout** | **DAY-25B robustness D1–D7** | **DAY-29 stability** | **DAY-30 attribution** |
|---|---|---|---|---|
| Purpose | Frozen v2 gates: research, then a one-shot holdout | Descriptive robustness on reused data | Day-level tail dependence and ticker recurrence | Day × ticker accounting attribution of daily simple active return |
| Periods / N | Research 2017-02-01..2022-12-30 (1,490 sessions). Holdout 2023-01-03..2026-06-02 (856). **FACT** | Same two segments. **FACT** | Same. **FACT** | Same; the day and ticker sets are fixed from DAY-29 and DAY-25B. **FACT** |
| Strategy vs baseline | CAGR 28.82% vs 18.44% (+10.38 pp) in research; 71.25% vs 53.24% (+18.01 pp) in holdout. **FACT** (`metrics.json`). Max DD 36.0% vs 44.6% and 26.9% vs 25.1%. **REPORTED** | Copied from DAY-19/21 | L (Σ log active) 0.4965 / 0.3774; share of positive active days 0.521 / 0.509. **FACT** | Σ daily simple active return 0.6270 / 0.4808. **FACT**: recomputed exactly from `equity.csv` |
| Costs | 0 / 5 / 10 bps per side. Cost drag 0.40 / 0.53 pp at 5 bps. **REPORTED** | D6: active stays positive up to 20 bps (+9.25 / +16.55 pp). **FACT** | 5 bps primary, 10 bps secondary | 5 bps primary, 10 bps secondary; qualitatively the same |
| Statistical evidence | HAC (NW lag 5) active vs B1: t = 1.64, p = 0.101 in research; t = 1.38, p = 0.166 in holdout. **FACT**. Holm p 0.303 / 0.166. **REPORTED**. **Not significant.** | None (descriptive) | None (descriptive) | None (descriptive) |
| Robustness / concentration | Top-2 share of \|P&L\| 0.465 / 0.433. **FACT**. V2-MOM trails B1 in calendar years 2018 and 2021, and 2023 and 2025. **REPORTED**, consistent with D4a. | See the list below the table | Removing the best-k active days (spliced, not re-simulated) gives active CAGR, research / holdout: **k = 5: +6.51 / +5.63 pp; k = 10: +3.51 / −2.41 pp; k = 20: −1.60 / −13.69 pp**. K3 matched targets to holdings on every session (0 mismatches). **FACT** | Top-two tickers account for **87.8%** (research, TSLA+NVDA) and **55.9%** (holdout, MU+AMD) of Σ daily simple active return. On days outside the best-20, all other tickers sum to **negative** in both segments. **FACT** (§4) |
| Data / universe limits | One survivor universe chosen with present knowledge (Q5). Holdout not blind (DAY-21 §8). | The same, plus outcome-dependent selections in D2 and D7 | Outcome-dependent day sets | Outcome-dependent day and ticker sets. G7/G8 conditional on A1/A4 (§6). |
| Evidence class | Research: in-sample, gated. Holdout: **historical pseudo-OOS**, not blind. | Exploratory, descriptive, reused data | Exploratory, descriptive, reused data | Exploratory, descriptive, **conditional** |
| Supports | V2-MOM passed its predeclared economic gates on historical data. **It earned forward testing, not deployment.** | The edge is not a single-ticker artefact (D1). It survives costs up to 20 bps. | The excess depends heavily on a few days, strongly so in the holdout. | Where the summed active return sits: in a few tickers, and in research mostly in two. |
| Does not support | Statistical significance; forward or live performance | Independent confirmation; robustness to period selection (D4c) | Significance; causation | Causation, counterfactuals ("without TSLA"), CAGR attribution, robustness |

**DAY-25B details** (5 bps, research / holdout; all **FACT**, from `artifacts/day25b/run/d*.json`):
- **D1, drop one ticker and re-simulate:** active vs B1 stays positive in all 25 cases. The minimum is 7.08 / 6.86 pp, both when NVDA is dropped.
- **D2, remove the top two and re-simulate:** active vs full B1 falls to **+0.80 / +0.56 pp**. Against the predeclared primary comparator B1-sub it is +3.21 / +10.75 pp.
- **D3, 300 random 20-of-25 subsets:** active vs B1 is negative in 13 / 25 subsets (vs B1-sub: 5 / 5).
- **D4b, 252-session rolling windows:** the active total return is positive in 0.58 / 0.76 of windows.
- **D4c, holdout leave-one-year-out:** **excluding 2026, active is −2.55 pp.**
- **D7:** 3 / 4 of 28 single stocks had a higher CAGR (hindsight comparator).

---

## 3. DAY-30 integrity and methodology review

**Integrity: all FACT, checked on 2026-10-19.**
- **Predeclaration:** `artifacts/day30/day30-attribution-predeclaration.md` has SHA-256 `09f8b4e6…c72e`, the expected frozen hash. It was frozen in `2f94f7d`. `verify_frozen_doc()` passes, including the revert-to-approved check (`5f25ae08…18b4`).
- **DAY-29:** the predeclaration (`7f9d1bea…`), implementation (`c444e1ab…`) and tests (`97fc60a4…`) are unchanged. All 13 pinned outputs and the integrity record match `run_summary.json` (`d7795bb9…`).
- **DAY-30 outputs:**
  - all 10 files listed in `artifacts/day30/run/run_summary.json` (`5ec2f054…`) exist and match their hashes;
  - `gate_record.json` (`2e17b2b0…`) matches the summary's pin and reads `PASSED` for G1–G8;
  - the summary reads `COMPLETED`, all gates `passed`, authorization `DAY30-ATTRIBUTION-RUN`.
- **Synthetic tests re-run now:** `pytest tests/test_day30_attribution.py tests/test_day29_stability.py` gives **54 passed** (29 + 25).
- **Execution:** exit code 0. **REPORTED** in the session log; the repository does not record it, but the `COMPLETED` summary is consistent with it.
- **Implementation identity at run time:** the run summary records HEAD `2f94f7d` with the script and tests **untracked**; the script's own hash is **not** recorded in it. The committed blob (`80d5bcb`, `a233fd38…`) equals the hash taken immediately before the run. That pre-run hash is **REPORTED** in the session log, not in a repository record. **Limitation.**

**Methodology: implementation compared with the frozen document. FACT unless noted.**
- **Fixed inputs:**
  - the day sets are read from the pinned DAY-29 `t1.json` files and equal them (recomputed: set equality for all 24 sets);
  - the ticker sets are fixed to TSLA/NVDA and MU/AMD and checked against the pinned `d2.json`;
  - costs are 5 bps primary and 10 bps secondary;
  - the research and holdout segments are processed separately;
  - nothing is ranked, and there are no thresholds.
- **Gates G1–G8** are implemented as §6 specifies. Each has a fail-closed synthetic test (the G8 test calls `g8_check` directly).
- **One additional fail-closed check:** each recorded cost must equal float64 notional × s. It identifies the engine's s and is reported as a G7 precondition.
- **Hash-gate wording:** §10 says "approved hash in §12". It is implemented as the frozen-file hash plus a check that reverting the freeze rows gives the approved hash.
- **G5a–G5d** are integrity checks only (§6A.6). They do **not** prove bit-identical state after every transition.
- **The engine rounding residual ε** is kept as a separate O1 column and never assigned to a ticker. In the real run its cell values are about 1e-15.
- **The daily §6A identity** is tested exactly **at group level** (close rounding, cash, splits, liquidation), not per single operation. The buy-step and per-ticker G8 identities are tested per operation. **Test-supported.**
- **No protected data:** the script's read allow-list and loaders cover only I1–I4 and Stage R/H. A text scan finds no F003, `fwd-gate2`, P001 or Stage F path.

---

## 4. Concentration findings (DAY-30, 5 bps; FACT, independently cross-checked)

Units: **sums of daily simple active returns** (r_MOM − r_B1). They are not compounded and are not CAGR, log return or cumulative return.

| | Research (total 0.6270) | Holdout (total 0.4808) |
|---|---|---|
| Top-two, whole segment | TSLA+NVDA **0.5502 (87.8%)** | MU+AMD **0.2687 (55.9%)** |
| All other tickers, whole segment | 0.0768 | 0.2121 |
| Best-20 days: top-two / others | 0.2432 / 0.3530 | 0.2681 / 0.5013 |
| Outside best-20: top-two / others | 0.3070 / **−0.2762** | **0.0006** / **−0.2893** |
| Worst-20 days: top-two / others | −0.2053 / −0.4286 | −0.1688 / −0.4079 |
| Engine residual (any cell) | ≈ 1e-15 | ≈ 1e-15 |

- **10 bps (secondary sensitivity):** totals are 0.6096 / 0.4712, and the top-two shares are 89.9% / 56.8%. The pattern is unchanged.
- **Cross-checks performed:**
  - every O1 total equals the exact rational Σ daily active return recomputed from the pinned `equity.csv` files (equal in float64);
  - day-set rows equal the equity-derived day totals;
  - cells sum to the total, and O2 per-ticker rows sum to the O1 cells, to within 1.1e-16;
  - all 24 day sets equal DAY-29's.
- **INFERENCE:** in the holdout, MU+AMD contributed essentially nothing outside the 20 best active days, and the other tickers were net negative there. In research, the other tickers were net negative outside the best-20 days and close to zero over the whole segment.
- **Why this is not a contradiction of DAY-25B D2** (it survives top-two removal, +0.80 / +0.56 pp):
  - D2 is a **re-simulation** in which other tickers replace the removed ones, measured in CAGR;
  - DAY-30 is **accounting attribution** of the realised path in summed simple returns.
  - These are different estimands, so this is not a conflict.
  - The DAY-19/21 "top-2 share of |P&L|" (0.465 / 0.433) is a third estimand: dollar P&L of V2-MOM alone, not active return.
- **Mechanical component:** both sets were selected by outcome, so large shares are partly built in (frozen §7).

---

## 5. Statistical limitations and conflicting metrics

- **Significance:** no significance test establishes an edge. The HAC p-values for active return vs B1 are 0.101 in research and 0.166 in holdout (FACT). DAY-25B, DAY-29 and DAY-30 are descriptive and add no inferential evidence.
- **Multiplicity and reuse:** DAY-25B, DAY-29 and DAY-30 were drafted after the earlier results were seen (they are labelled DERIVED FROM PRIOR OBSERVATION).
- **Period dependence:**
  - excluding 2026 turns holdout active return negative (D4c: −2.55 pp);
  - removing the best 10 holdout days turns active CAGR negative (DAY-29 T2: −2.41 pp).
- **Conflicts inherited from `docs/strategy-evidence-inventory-2026-10-17.md` §5** (not resolved here):
  - **C1/C2:** non-predeclared DAY-25 figures (28.22%, 28.17% / 71.54%) differ from the official 28.82% / 71.25%. The official gate figures are used here.
  - **C5:** the DAY-25B authorization documentation.
- **Different units, not conflicts:**
  - that inventory (§7) mentions an *unpersisted* "+1.954 additive" holdout figure, defined as (E_MOM − E_B1)/100,000;
  - DAY-30's 0.4808 is a sum of daily simple active returns.
  - These are different units. The +1.954 figure is not repository evidence and is not used.

---

## 6. Status of A1, A4 and D3

| Item | Status | Evidence |
|---|---|---|
| A1: IEEE-754 binary64 round-to-nearest platform arithmetic | **ASSUMPTION; not verified** | Supported only by the DAY-25B exact reproduction on this platform class |
| A4: reconstructed share/price state bit-identical to the engine after every transition | **Premise; not proven** | Entry and pre-exit states are proven. Add-on buys, partial sells and splits leave no recorded state. G5a–G5d are integrity checks only (frozen §6A.6). |
| D3: loaded input arrays identical to the engine's | **Not proven** | Snapshot bytes and loader source are pinned, but the arrays were never recorded |

**Consequence:** G7/G8 passing (max \|ε\|/τ = 0.34; max per-ticker difference/τ = 0.30) is consistency evidence **under** A1 and A4. It is not proof of exact reconstruction. **The DAY-30 attribution values themselves do not depend on G7/G8.** They are exact accounting of the reconstructed state, and the O1 totals match the engine's equity series exactly (§4).

---

## 7. Universe, holdout and leakage considerations

- **Survivor universe (Q5):** the 25-name universe was selected with present knowledge. Momentum is plausibly favoured by that bias (DAY-19 §10). There is no point-in-time universe.
- **Historical holdout:** DAY-21 is pseudo-OOS that the protocol authors could not blind themselves to (DAY-21 §8). It is not forward evidence.
- **Analyst leakage:** DAY-25B, DAY-29 and DAY-30 were all designed after the holdout was seen. Their sets (top-two tickers, best and worst days) are outcome-selected.
- **Untouched evidence:** the only untouched evidence is the pending `fwd-gate2` (42 sessions, 2026-10-12..2026-12-09) and the sealed paper experiment P001.
  - Neither was opened for this review.
  - The project itself records that 42 sessions is weak evidence (DAY-26D, per the 2026-10-17 review).

---

## 8. What is **not** established

- **Future profitability** of V2-MOM.
- **Statistical significance** of its active return vs B1, beyond the reported p-values (0.101 and 0.166, not significant).
- **Live execution performance:** fills, slippage, capacity and operational reliability. All results are simulated at the raw open with fixed per-side costs.
- **Sharia compliance:** no screening has been done. The eligibility registry is header-only, and adviser input is required (inventory §8).
- **Causation:** none of DAY-30's contributions is a counterfactual.

---

## 9. Decision matrix

| Option | What it adds | Can it materially change the decision? | Risks / cost | Verdict |
|---|---|---|---|---|
| **A. Continue targeted robustness research** (more historical diagnostics) | Further description of the same data | **Low.** Same data, outcome-dependent designs, no inferential gain. Four such studies already agree on concentration. | More analyst degrees of freedom; it looks like data mining | Not recommended |
| **B. Pause V2-MOM** (no new historical research; `fwd-gate2` and P001 preserved unchanged) | Waits for the only untouched evidence, already pre-registered | **Yes**, at the scheduled gate evaluation | No information before 2026-12-09; 42 sessions is weak evidence | **Recommended** |
| **C. Prepare a separately specified paper-trading evaluation** | Possibly evidence about execution | Not now: a sealed paper experiment (P001) already exists, and a new evaluation would add little before the gate | Risk of conflicting with the `fwd-gate2` / P001 rules (no early inspection, no blind-period-motivated changes, clean-tree capture preflight); duplication | Defer. Reconsider only after the `fwd-gate2` result, as a new predeclared protocol. |

---

## 10. Recommended next step

- **Question:** under the adopted, unchanged protocol (v2.2 gate with the v2.3/v2.4 amendments), does V2-MOM meet its §13 forward gate on the 42 untouched `fwd-gate2` sessions?
- **Scope:**
  - preserve `fwd-gate2` and P001 exactly;
  - acquire, compute, inspect or decrypt nothing before 2026-12-09 16:15 ET;
  - evaluate once, using the capture command fixed in DAY-26D.
- **Before the capture:**
  - **operational:** the capture preflight requires a clean tree with no untracked files (2026-10-17 review §6.4, OD-7). **This summary file is untracked, so it must be committed (or removed) before the capture.**
  - **optional owner decision, valid only if adopted before 2026-12-09 16:15 ET and unconditional on the result:** pre-register a longer follow-on blind V2-MOM segment (Option 2 of the 2026-10-17 review §5). This is the smallest step that addresses the 42-session power problem without touching the existing sample.
- **Acceptance criteria:**
  - capture time ≥ 2026-12-09 16:15 ET;
  - all pinned protocol files unchanged;
  - clean tree;
  - the gate is applied exactly once, with an outcome label from the adopted set.
- **Stop conditions:**
  - any early access, decryption of P001 or change to a pinned file (the protocol then makes the gate `FORWARD42-INVALID`);
  - a data fail-closed at capture;
  - any proposal to change V2-MOM rules before the result.
- **After the result:** decide between stopping V2-MOM and designing a separately predeclared longer forward or paper evaluation. **Live trading is not on the table on this evidence.**

---

## 11. Source inventory (SHA-256, first 16 hex characters; raw bytes)

| Path | SHA-256 | Role |
|---|---|---|
| `artifacts/day19/day19-research-report.md` | `3569b0f216088905` | DAY-19 report (REPORTED figures) |
| `artifacts/day19/v2/run_summary.json` | `698b8c3bbea9ca30` | DAY-19 pins |
| `artifacts/day19/v2/V2-MOM-R001/5bps/metrics.json` | pinned in the run summary | CAGR and HAC (FACT) |
| `artifacts/day21/day21-historical-holdout-report.md` | `5078f6fb63d53539` | DAY-21 report |
| `artifacts/day21/v2/run_summary.json` | `019095d42644fd5e` | DAY-21 pins |
| `artifacts/day25b/day25b-robustness-predeclaration.md` | `f5b32aed2e31d95f` | DAY-25B design |
| `artifacts/day25b/run/run_summary.json` | `d29f15cd53433546` | DAY-25B pins |
| `artifacts/day25b/run/d1.json` … `d7.json` | `9dfe44de…`, `541a9226…`, `82afc091…`, `a08211e5…`, `1738dd9e…`, `949d6df8…`, `5d96008e…` | D1–D7 |
| `artifacts/day29/day29-stability-predeclaration.md` | `7f9d1bea5236de2a` | DAY-29 frozen design |
| `artifacts/day29/run/run_summary.json` | `d7795bb91ebad4bf` | DAY-29 pins |
| `artifacts/day29/run/5bps/{t0,t1,t2,k3}.json` | `9915526b…`, `f02769bf…`, `38dc940e…`, `37b03534…` | T0, T1, T2, K3 |
| `artifacts/day30/day30-attribution-predeclaration.md` | `09f8b4e6be9355ef` | DAY-30 frozen design |
| `artifacts/day30/run/run_summary.json` | `5ec2f054eb2cec4e` | DAY-30 manifest |
| `artifacts/day30/preflight/gate_record.json` | `2e17b2b0d517a658` | G1–G8 record |
| `artifacts/day30/run/5bps/{o1,o2,o3}.json` | `8d5b8cfc…`, `4c128c8d…`, `427a7cd4…` | DAY-30 primary outputs |
| `artifacts/day30/run/10bps/o1.json` | `76576fb247283057` | DAY-30 secondary output |
| `scripts/day30_attribution.py`, `tests/test_day30_attribution.py` | `a233fd386a9ae786`, `c3d21b5fc0ca4822` | DAY-30 implementation (commit `80d5bcb`) |
| `docs/strategy-evidence-inventory-2026-10-17.md` | `322be6504d5d24a9` | Conflicts C1–C9; forward status |
| `docs/strategy-candidate-selection-and-forward-protocol-review-2026-10-17.md` | `eafac04071fd890d` | Forward-gate options; OD-7 |
