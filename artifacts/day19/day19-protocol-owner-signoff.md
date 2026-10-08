# DAY-19 — Protocol-Owner Review and Sign-off

| Field | Value |
|---|---|
| **Final status** | **APPROVED FOR HISTORICAL HOLDOUT** (V2-MOM and V2-STR) |
| Decided by | **Alixujaev (protocol owner)**, 2026-10-08 |
| Review prepared and recorded by | Claude (automated agent) at the protocol owner's direction. **Not independent:** the same agent implemented and ran DAY-19, so every claim was re-derived from hashes, committed blobs, metrics files and a clean-tree reproduction. |
| Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (frozen; freeze commit `ba3cefe`; DAY-18L sign-off `8b8b586`) |
| Starting HEAD | `fee0e9e` (the DAY-19 commit; DAY-19 itself started from `8b8b586`) |
| Stage R snapshot | `stage_r_20261007T093410Z`, manifest `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`. All 64 files unchanged. |
| Research period | 2017-02-01 → 2022-12-30, **1490** sessions |
| Warmup | 2016-01-04 → 2017-01-31, **272** sessions |
| Holdout / forward OOS | **Not acquired, not loaded, not inspected.** The last session loaded is 2022-12-30, and no Stage H or Stage F directory exists. The only 2023 date used is 2023-01-03, the next session in the rule-based exchange calendar (no market data), which flags 2022-12-30 as a month and week end. |

## A. Protocol compliance
- **Specifications:** the frozen specifications of V2-MOM, V2-STR and V2-LRV were executed as written. No rule changed after results. No parameter, universe, cost, benchmark, execution or gate rule changed.
- **No hidden thresholds:** the gate logic in `backtest/v2/run.py` reads only net CAGR at 5 bps, B1 net CAGR at 5 bps, the PIT/determinism/integrity flags and the presence of the Gate C items.
- **Two decisions taken before results**, both in `day19-predeclared-definitions.json`, SHA-256 `926e4926…`:
  - The file's mtime is **06:39:19Z**.
  - The first Stage R invocation was at about **07:08Z**, and the recorded run started at **07:09:38Z**.
  - The run embedded the file's SHA in its reproducibility block, and the file is unchanged since.

## B. Data isolation
Only the Stage R snapshot and the signed-off v2.0.4 event set were read; series C was not loaded. No holdout or forward data was acquired, loaded or inspected. The last loaded and evaluated session is **2022-12-30**.

## C. Lookahead
- **Tests: all PASS.** Index test (37 sessions); truncation, future-mutation and future-deletion tests (MOM 8, STR 32, LRV 150 sampled decisions); fill-source test (3335 fills each equal the raw open of their session); execution-timing test (every fill at the open t+1 after its decision close).
- **Signals:** signal t uses only TR up to t.
- **Corporate actions:** dividends are credited as cash on the ex-date using the previous close's shares, and splits scale shares. An independent buy-and-hold recompute, written without engine code, matches B1 and B2 **exactly**.

## D. Determinism
- **DAY-19 runs:** two runs gave **91/91 result files byte-identical** (`run_summary` SHA `698b8c3b…`, matching the provenance).
- **Clean-tree reproduction (sign-off):** a re-run from the committed HEAD `fee0e9e` with `git_dirty = false` gave **90/91 byte-identical** files. `run_summary.json` differs only in `reproducibility.git_commit` (`8b8b586` → `fee0e9e`).
- **Engine identity:** all 6 recorded engine SHA-256s equal the committed blobs.

## E. Research gates (5 bps, unrounded float64)
| Family | Net CAGR 5 bps | B1 net CAGR 5 bps | Gate 1 (≥ 0) | Gate 2 (≥ B1) | Gate A | Gate C | **Status** |
|---|---|---|---|---|---|---|---|
| V2-MOM | 0.28816164633146335 | 0.1844074874473387 | PASS | PASS | PASS | PASS | **RESEARCH-PASSED** |
| V2-STR | 0.24978852160383114 | 0.1844074874473387 | PASS | PASS | PASS | PASS | **RESEARCH-PASSED** |
| V2-LRV | 0.13344464778558618 | 0.1844074874473387 | PASS | **FAIL** | PASS | PASS | **RESEARCH-FAILED (economic)** |

**CAGR at 0 / 5 / 10 bps:**

| Family | 0 bps | 5 bps | 10 bps |
|---|---|---|---|
| V2-MOM | 29.21 % | 28.82 % | 28.42 % |
| V2-STR | 30.18 % | 24.98 % | 19.99 % |
| V2-LRV | 13.63 % | 13.34 % | 13.06 % |
| B1 | 18.46 % | 18.44 % | 18.42 % |
| B2 | 10.61 % | 10.60 % | 10.58 % |

Each status was verified against the committed metrics files. **No winner was selected between V2-MOM and V2-STR.**

## F. Robustness / Gate C
- **Completeness:** every §16 item is present for 0/5/10 bps, with no missing items. Calendar-year subperiods use the predeclared scope.
- **Diagnostics cannot alter Gate A or B:** no diagnostic value enters the gate logic.
- **Statistical diagnostic (not a gate):** Holm-adjusted p at 5 bps is **MOM 0.30, STR 0.67, LRV 0.67**. No active return vs B1 is significant.

## G. V2-LRV per-slot λ decision
- **Timing:** decided before results (see A).
- **Implementation:** `simulate_lrv` uses λ = min(1, slot_cash / (B·(1+s))) with B = slot cash, and `test_lrv_per_slot_lambda_never_lends_across_slots` covers it.
- **MOM and STR unaffected:** they use the global §8.4 λ (`_buy_all`).
- **The LRV failure does not depend on it:** both readings are identical at 0 bps, where LRV is 13.63 % against B1 18.46 %. LRV's total cost at 5 bps is 2,247 on 100,000.

## H. Engineering correctness (chronology)
1. **During test development, before any Stage R run:**
   - V2-LRV `sign()` failed on numpy floats; fixed.
   - V2-LRV formation was moved to the t_F close (PIT semantics).
   - V2-LRV dividends were missing from the turnover denominator; fixed, and the full suite restarted.
2. **Full suite:** 1297 passed.
3. **Stage R run 1 (~07:08Z):** the simulations completed and the per-experiment files were written, but it crashed writing `run_summary.json` (a numpy bool is not JSON-serialisable). **The values were not inspected.**
4. **Fix:** `_jsonable` now handles numpy bool. This touches serialisation only, with no calculation path.
5. **Recorded run (07:09:38Z):** an identical configuration that overwrote run 1's files.
6. **Then:** the determinism run, the commit `fee0e9e`, and the engine hashes confirmed equal to the committed blobs.
7. **At sign-off:** the DAY-19 tests re-ran on the committed HEAD (**17 passed**), and the clean-tree reproduction (D) exercises the post-suite serialisation change.

## Deviations ruled on by the protocol owner (none changes any number or gate)
| ID | Rule | Finding | Ruling / cure |
|---|---|---|---|
| D1 | §17: a dirty tree is allowed only for untracked run outputs | The engine and test code were uncommitted at run time | **Cured** by the clean-tree reproduction (D) |
| D2 | §17 reproducibility block | The full distribution list, asof/CA endpoint, per-file `bars_all` SHAs and dirty-file SHAs were recorded only transitively | **Cured** by the hash-verified addendum in the JSON (56 distributions with matching SHA; asof 2026-10-07 from the manifest-pinned `run.json`; 26 `bars_all` SHAs; 98 dirty-file SHAs, all equal to the committed blobs) |
| D3 | Freeze procedure: clarifications are committed v2.0.x versions | The per-slot λ was recorded pre-run in an uncommitted file | **Disclosed; immaterial.** Recommendation: a committed v2.0.5 clarification before any reuse touching V2-LRV |
| D4 | Evidence of pre-run decisions | The timing rests on mtime, the recorded SHA and the session log, not a pre-run commit | **Disclosed.** Recommendation: commit predeclarations before future runs |

## Interpretation (normative)
- **"Research-Passed"** means V2-MOM and V2-STR passed the predefined **minimum historical research-viability gate** on one sample.
- **It is not a "validated edge":** only FORWARD-PASSED is "validated under v2".
- **It is not "statistically proven alpha":** Holm p is 0.30 / 0.67 / 0.67.
- **Robustness observations (not gates):**
  - About **47 %** of V2-MOM's absolute P&L comes from its top two symbols.
  - V2-MOM's excess over B1 is **uneven** by year: it is concentrated in 2019–2020 and 2022, and V2-MOM trails B1 in 2018 and 2021.
  - V2-STR is **materially cost-sensitive**: costs take 5.2 pp of CAGR at 5 bps and 10.2 pp at 10 bps.
- **Limitations:** a hindsight-selected surviving mega-cap universe (Q5), a single strong-drift sample, and cash at 0 % (Q7).

## Governance conclusion
- **Approved for the historical holdout:** **V2-MOM and V2-STR**, together, with identical frozen configurations. Strategy-config SHA-256: MOM `62827d70…`, STR `0fc76b8a…`.
- **V2-LRV:** permanently rejected for this frozen branch (Gate 2 FAIL). It is never run on the holdout (§15.3).
- **No winner selection**, no protocol change, no parameter change.
- **Holdout:** 2023-01-03 → 2026-06-02, 856 sessions. **Not acquired and not run in this task.**
- **Push status:** nothing pushed.
