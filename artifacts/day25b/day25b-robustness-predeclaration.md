# DAY-25B: V2-MOM robustness diagnostics (predeclaration)

| Field | Value |
|---|---|
| Status | **FROZEN — NOT AUTHORIZED TO RUN** |
| Freeze | Frozen 2026-10-09 on protocol-owner approval. Approved pre-freeze content SHA-256: md `060da741014df387ab34fe28b48a0db2456072f1798acfff363de44a3dddc16c`, json `5b4b75ef4f19e2fb4bc621b9e87f85477acf8de44406860a2916d52b847f6805`. The only change from the approved content is this status and freeze record. The frozen files' SHA-256 values are recorded in the freeze commit message (a file cannot contain its own hash). Any later change requires a new, separately approved version. Freezing does not authorize any run (§8). |
| Nature | **New predeclaration.** It is not a reconstruction of the DAY-25B predeclaration reported at commit `c5ad968`. That commit is absent from this repository and from `origin` (verified 2026-10-09), and its content is unknown. |
| Drafted | 2026-10-09; revised 2026-10-09 (finalization audit), on `feature/day-trading-research` at HEAD `032479cfad20434e05b7b96bf62a61e439fb2f85` |
| Family | V2-MOM only |
| Frozen config SHA-256 | `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` (recomputed from `artifacts/day16/research-protocol-v2.json` via `backtest/v2/run.py::strategy_config_sha`; matches) |
| Engine commit | `5ed3d0ab5c2d205707d321494086bc7734f213d0` (DAY-22 §4) |
| Machine-readable twin | `artifacts/day25b/day25b-robustness-predeclaration.json`. Every parameter below has an identical value there. |
| Protocol label | **DERIVED FROM PRIOR OBSERVATION** (protocol v2 §14). It was drafted after the DAY-19 research results, the DAY-21 holdout results and the DAY-25 studies had been seen. |
| Scope | **Final and complete: D1–D7.** No diagnostic may be added. |

**Drafting constraints observed:** no experiment was run and no performance number was computed or read for this draft, beyond results already published in DAY-19/21/22/25. No code, frozen protocol file, existing artifact or snapshot was modified. No forward or excluded-period data was accessed. The session counts quoted below are XNYS calendar facts (`exchange_calendars` 4.13.2), not market data.

---

## 1. Why this exists and what it can and cannot do

The DAY-21 holdout showed V2-MOM ahead of B1, but the result is not statistically significant: HAC (Newey–West lag 5) gave t = 1.38, p = 0.166 (`day21-historical-holdout-report.md` §4). Performance is also concentrated, with the top-2 symbols producing 43% of absolute P&L on the holdout and 47% in research (DAY-19, DAY-22). DAY-25B describes **how much of the frozen historical result depends on particular symbols, particular years, and the cost assumption**. Its objective is robustness description, **not optimisation**.

Binding constraints:

1. **All outputs are descriptive.** No D1–D7 output carries a threshold, pass/fail rule or label. Protocol §13.C and §16 forbid robustness results from passing, failing, ranking, rescuing or modifying a family. **No DAY-25B output changes V2-MOM's status**: RESEARCH-PASSED, HOLDOUT-PASSED, the DAY-22 lockdown, or the forward-OOS plan.
2. **Diagnostics, not candidates (§14, §16).** Universe and cost variations are diagnostics of the frozen configuration. No variant may be proposed, adopted or reported as an alternative strategy.
3. **Nothing frozen changes (DAY-22 §3.2).** Cost rates and ranking universes are passed to the engine **as run-time diagnostic inputs only**. `artifacts/day16/*`, `backtest/v2/*` (including `run.py::COSTS`), `config/day_universe.py`, the B1/B2 definitions, the historical snapshots and the forward-OOS boundaries are unchanged, so the config SHA is unchanged.
4. **Reused historical data — not independent or forward evidence.** Every diagnostic reuses data that has already been evaluated, and the holdout period is not blind (§3.6 rationale 4). Every output carries the label *"robustness diagnostic on reused historical data — not independent or forward evidence"*. Only the forward OOS (DAY-22 §3) is genuine out-of-sample validation.

---

## 2. Common specification (applies to every diagnostic)

| Item | Rule |
|---|---|
| Segments | **Research** (Stage R, 2017-02-01 → 2022-12-30, 1,490 sessions) and **historical holdout** (Stage H, 2023-01-03 → 2026-06-02, 856 sessions). They are **analysed and reported separately and never pooled**. No Excluded-period (2026-06-03 → 2026-10-07) or forward (from 2026-10-08) data is read. |
| Data | Only via the existing verifying loaders `backtest/v2/data.py::load_stage_r` and `load_stage_h`. They check the snapshot manifests `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` (R) and `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34` (H), the review/validation manifests `755c905e0adae6c7cac924aa8146384defe7053784b526675e7b51d714f6d698` (R) and `e2a7d5a72d5a12342554edff34efb3e398b10eb8db101716dbc806592f82530f` (H), and the session boundaries (≤ 2022-12-30, ≤ 2026-06-02). Any mismatch aborts. A missing snapshot may be restored only with `python -m scripts.research_data.restore --version protocol-v2-historical-v1`. |
| Strategy | Frozen V2-MOM exactly as in `signals.mom_targets` (252/21 lookback/skip, top 5 at 0.20, month-end decisions, next-open execution) and `engine.simulate_targets`. The only things that vary are the **ranking universe** (D1–D3) and the **per-side cost `s`**, both passed as arguments. |
| Universe order | The 25 symbols of `FROZEN_DAY_UNIVERSE` in ascending ASCII order, exactly as Python `sorted` returns them: `AAPL, ADBE, AMAT, AMD, AMZN, AVGO, COST, CRM, CSCO, GOOGL, INTC, JNJ, JPM, KO, META, MSFT, MU, NFLX, NVDA, ORCL, PEP, QCOM, TSLA, WMT, XOM`. This order is used for every enumeration, the D3 key assignment, and every tie-break. |
| Cost scenarios | **Primary: 5 bps** per side (`s = 0.0005`). **Secondary sensitivity: 10 bps** (`s = 0.0010`). Both apply to **every** diagnostic D1–D5 and D7. The frozen 0 bps scenario is used only in D6 (cost drag). **15 bps (`s = 0.0015`) and 20 bps (`s = 0.0020`) are diagnostic cost overrides used only in D6**; they are not protocol scenarios. |
| Benchmarks | **B1** (equal-weight buy-and-hold of the 25) and **B2** (SPY), exactly as in `run.py::run_family`, are reported unchanged for every segment and cost. Diagnostic comparators (B1-sub, single stocks) are **additional** and never replace B1 or B2. |
| B1-sub | For a ranking universe `U ⊂ 25`: equal-weight buy-and-hold of the symbols in `U` that have a bar at the segment's first open. It is built from the same rule as B1 restricted to `U`, with the same engine, accounting and `λ` rule, and **the same cost scenario as the variant it is compared with**. |
| Comparators for subset analyses (D1–D3) | **Primary: B1-sub** (same symbols). **Secondary: B1** (full 25 symbols). Both at the variant's cost. |
| Active return (annualised) | `CAGR(strategy) − CAGR(comparator)`, both from the same engine over the same sessions and cost. CAGR = `(E_T/E_0)^(252/N) − 1` (protocol §12). Used in D1, D2, D3, D4c, D6 and D7. |
| Determinism | No randomness except D3's seeded subset list (§3). Ties are broken by universe order. Two runs must produce byte-identical outputs; a mismatch aborts. |
| Preflight (D6 integrity check) | A separate stage executed **before any D1–D7 computation** (§3 D6). Any `cagr` or `ending_equity` mismatch aborts the **entire DAY-25B process**: no D1–D7 result is created and the run is **not** marked successful. The preflight record is kept separately from diagnostic results. The exact-equality requirement is never relaxed automatically, including when the environment fingerprint differs. A passing preflight does **not** authorize the diagnostics. |
| Statistics | **No new significance tests.** The only p-value reported is the existing full-universe HAC/Holm diagnostic (protocol §12/§14), copied from DAY-19/DAY-21. No p-value, t-statistic or confidence interval is computed for any variant. |
| Isolation | The future run script must refuse network sockets (pattern of `backtest/v2/run.py::_refuse`), assert the config SHA at start, write diagnostic outputs only under `artifacts/day25b/run/`, and write the preflight record only under `artifacts/day25b/preflight/`. |

---

## 3. Diagnostics (final scope)

Each diagnostic runs **per segment** and **per cost scenario in {5 bps (primary), 10 bps (secondary)}**, except where D6 states otherwise.

### D1 — Leave-one-symbol-out
- **Purpose:** show whether the result depends on any single symbol.
- **Calculation:** for each of the 25 symbols `x`, in universe order: ranking universe `U = 25 \ {x}`, V2-MOM simulated with `mom_targets(tr, t, U, tickers)`, and B1-sub built over `U`. TR is computed from the full snapshot; `x` is excluded from **ranking and holding**, and its prices are not masked.
- **Outputs:**
  - per `x`: CAGR, active vs B1-sub (primary), active vs B1 (secondary), max drawdown, top-2 concentration, weight HHI;
  - summary: min, median and max of active vs B1-sub and vs B1, the count with active > 0, and the identity of the minimum.
- **Limitations:** 25 overlapping variants of the same path, not 25 independent tests. Removing a symbol also changes which other symbols reach the top 5.

### D2 — Remove the two largest absolute-P&L contributors
- **Purpose:** stress test of the concentration noted in DAY-19/22.
- **Ranking method (fixed):**
  - Run the frozen full-universe V2-MOM **at 5 bps on the same segment**.
  - Take `Result.flows`, the per-symbol net cash P&L: sale proceeds net of cost − purchases − cost + dividends + liquidation. This is identical to `symbol_pnl_contribution` in `metrics.json`.
  - Rank symbols by `|flows|` descending, with ties by universe order, and take the top 2.
  - Ranking is **per segment**. **The same two symbols are removed in both the 5 bps and the 10 bps runs**: there is no re-ranking at 10 bps.
- **Calculation:** as D1 with `U = 25 \ {top-2}` and B1-sub over `U`.
- **Outputs:**
  - the two symbols with their **signed** 5 bps contribution and share of Σ|flows|;
  - per cost: CAGR, active vs B1-sub (primary), active vs B1 (secondary), max drawdown, top-2 concentration of the reduced run.
- **Limitations (printed with every D2 result):**
  - The selection is **outcome-dependent by construction**.
  - The holdout top-2 are already known from DAY-21 `metrics.json`.
  - If both are positive contributors, removal is biased downward. D2 is a stress test, not an estimate of expected performance.
  - If either is negative, removing it can *raise* the result, and this must be stated.

### D3 — 300 random universe subsets
- **Purpose:** distribution of outcomes when the universe is perturbed without outcome-dependent selection.
- **Sampling algorithm (fixed and exact; it depends only on the PCG64 bit stream):**
  1. `bitgen = numpy.random.PCG64(20261008)`.
  2. For each draw: `keys[i] = bitgen.random_raw()` for `i = 0 … 24`, in universe order (§2). These are 25 unsigned 64-bit integers, consumed in that order.
  3. The draw's subset is the 20 tickers with the **smallest** keys. A tie on equal keys is broken by universe order (lower index first). The subset is stored as its tickers in universe order.
  4. **Within a subset there is no replacement**: 20 distinct tickers by construction.
  5. If the subset is the same **set** as an already accepted subset, it is discarded (counted) and the next draw continues the same bit stream.
  6. Stop when **300 distinct subsets** have been accepted. Subset `n` (1…300) is the `n`-th accepted one.
  7. Write the ordered list to `artifacts/day25b/run/subsets.json` with its SHA-256, the discard count and the numpy version. **The persisted list is authoritative** for any re-run.
- **Calculation:** per subset `U` and cost: V2-MOM with SELECT 5 unchanged, and B1-sub over `U`. **The same 300 subsets are used for both segments and both costs.**
- **Outputs (per segment and cost):**
  - for active vs B1-sub (primary) and active vs B1 (secondary): mean, median, 5th and 95th percentile (`numpy.percentile`, `method="linear"`), min, max, and fraction > 0;
  - the same summary statistics for CAGR;
  - the full per-subset table.
- **Limitations:**
  - Any two subsets share at least 15 of 20 symbols, so results are strongly dependent.
  - The distribution is a sensitivity description, not a sampling distribution of an estimator.
  - No subset may be singled out as "best".

### D4 — Time decomposition
All three use the frozen full-universe run and B1 of the segment, per cost.

- **D4a Calendar year.**
  - From the existing `calendar_years` output: strategy, B1 and B2 return per year, plus active = strategy year return − B1 year return.
  - **Labels (DAY-22 P1 correction in the DAY-25B report layer only; `backtest/v2/metrics.py` is not edited):**
    - Research: **2017 partial** (2017-02-01 → 2017-12-29, 231 sessions); 2018 (251), 2019 (252), 2020 (253), 2021 (252), 2022 (251) full.
    - Holdout: 2023 (250), 2024 (252), 2025 (250) full; **2026 partial** (2026-01-02 → 2026-06-02, 104 sessions).
  - Calendar years are slices of one continuous run, not separate simulations.
- **D4b Rolling window.**
  - Inputs are the daily returns `r_d` (protocol §12; the first uses `E_0`, the last includes the liquidation cost) of the strategy and B1.
  - Windows are `[i, i + 252)` for `i = 0, 21, 42, …` while `i + 252 ≤ N`, inside one segment only. That gives 59 windows for Research and 29 for Holdout. The trailing partial window is dropped.
  - **Window active = `Π(1 + r_strategy) − Π(1 + r_B1)`**: a total-return difference over equal-length 252-session windows, **not annualised**.
  - Outputs: window count, min, median, max, fraction > 0, start date of the minimum.
  - Limitation: windows overlap by 231 of 252 sessions and are not independent.
- **D4c Leave-one-year-out.**
  - For each calendar year `y` of the segment (Research: 2017 partial, 2018–2022; Holdout: 2023, 2024, 2025, 2026 partial), remove the daily returns dated in `y`.
  - Compound the remainder and annualise with the remaining session count: `CAGR_−y = Π(1 + r)^(252/N_−y) − 1`. Apply the same to B1.
  - Active = `CAGR_−y(strategy) − CAGR_−y(B1)`.
  - **No re-simulation:** the path is spliced, and this is disclosed.
  - Outputs: per `y`, CAGR_−y, B1 CAGR_−y, active, and N_−y.
  - Limitation: removing a partial year changes N unevenly, and splicing ignores path dependence.

### D5 — Concentration
- **Purpose:** quantify the dependence noted in DAY-19/22.
- **Calculation** (from the frozen full-universe run per segment and cost; no new strategy variant):
  - the per-symbol `flows` table (signed);
  - top-k share of Σ|flows| for k = 1…5;
  - the existing `top2_concentration`, `weight_hhi` and `1/weight_hhi` (effective number of names), and `symbol_breadth`;
  - the share of total positive P&L contributed by the two largest positive contributors.
- **Limitation:** monthly top-5 selection makes concentration structurally high, and there is no benchmark for "normal".

### D6 — Transaction-cost sensitivity and overrides
- **Purpose:** show how the result changes with friction, including beyond the frozen 0/5/10 bps grid.
- **Calculation:** full universe; V2-MOM, B1 and B2 at:
  - **0, 5 and 10 bps** (frozen protocol scenarios), as a **preflight integrity check** (approved decisions, 2026-10-09):
    - **Separate stage, executed first.** The preflight runs as its own stage **before any D1–D7 computation**, including the D6 15/20 bps overrides. No diagnostic computation starts until the preflight has completed and passed.
    - The existing DAY-19/DAY-21 reference metrics are **recomputed**. Inputs: identical segment, data (the verified Stage R/H snapshots), benchmark definitions, starting capital (`E_0 = 100,000`) and calculation conventions (`backtest/v2/*` unchanged).
    - `cagr` and `ending_equity` must equal the published values **exactly**, compared at **full float64 precision** (no rounding or tolerance). The references are `artifacts/day19/v2/{V2-MOM-R001,V2-B1-research,V2-B2-research}/{0,5,10}bps/metrics.json` and `artifacts/day21/v2/{V2-MOM-H001,V2-B1-holdout,V2-B2-holdout}/{0,5,10}bps/metrics.json` (18 files; stored with full-precision JSON floats).
    - **Precondition:** the reference runs recorded environment `distributions_sha256 = 7b47231b6bf706da340a4c8b940bb5cbd632c228c8f07dc57cde6c065c89379a` (Python 3.12.10, numpy 2.5.2). The check records the current fingerprint in the preflight record. **A differing fingerprint does not relax the equality requirement**: no tolerance, rounding or re-baselining is ever applied automatically. A value mismatch aborts the run as below, regardless of the environment. A differing fingerprint is recorded and reported, and is never used to explain away or excuse a mismatch.
    - **On any `cagr` or `ending_equity` mismatch:**
      - the **entire DAY-25B process aborts**;
      - **no D1–D7 result is created**;
      - the run is **not** marked successful (run status `ABORTED_PREFLIGHT_MISMATCH`);
      - the discrepancy is reported.

      Frozen code, historical reports, the protocol configuration and the reference values are **never** changed to force a match.
    - **Separate record.** The preflight writes `artifacts/day25b/preflight/preflight_record.json`, **separately from diagnostic results**, whether it passes or fails. It holds:
      - for every comparison: the reference file, the field, and the reference and recomputed values at full precision;
      - for any failure: its details;
      - the environment fingerprint: current `distributions_sha256`, Python version and numpy version.
    - **No authorization.** This is a reproducibility check, not new information. **A passing preflight does not authorize running any DAY-25B robustness diagnostic.** D1–D7 still require all three of the following (§8): (1) the approved and frozen predeclaration, (2) the reviewed implementation, and (3) a separate, explicit run authorization.
  - **15 bps and 20 bps** (diagnostic overrides): `s = 0.0015` and `s = 0.0020` passed to `engine.simulate_targets`. The frozen `COSTS` dict, the protocol JSON `costs` block and the config SHA are **unchanged**.
- **Outputs per segment and cost:** CAGR, B1 CAGR, B2 CAGR, active vs B1, total costs, cost drag = CAGR(0 bps) − CAGR(cost), annual turnover, mean and min `λ`.
- **Limitation:** a per-side flat rate is still not a market-impact model (protocol Q6).

### D7 — Single-stock buy-and-hold (supplemental)
- **Purpose:** context, placing V2-MOM next to holding each universe name alone.
- **Calculation:** for each of the 25 symbols, 100% target weight at the segment's first open via the same engine and accounting, with no rebalancing (the B2 rule applied to that symbol), at the same cost as the V2-MOM run it is compared with. A symbol without a bar at the first open is reported `undefined (no bar at first open)`.
- **Outputs per segment and cost:** each symbol's CAGR and max drawdown; V2-MOM's rank among the 25 single stocks + B1 + B2 by CAGR; the count of single stocks with a higher CAGR than V2-MOM.
- **Limitation:** the best single stock is known only in hindsight and is **not an investable comparator**; ranking it is outcome-dependent. D7 has **no decision role** and **never replaces B1 or B2**.

---

## 4. Multiple comparisons and selection risks

- **Volume:**
  - per segment and cost: 327 V2-MOM runs (1 frozen + 25 D1 + 1 D2 + 300 D3), 327 B1/B1-sub runs (1 B1 + 25 + 1 + 300), 1 B2 run and 25 single stocks. That is 680 simulations.
  - ×2 costs, plus D6's 0/15/20 bps runs of V2-MOM, B1 and B2 (9): **about 1,370 per segment and about 2,740 in total**.
  - With this many variants, some will look bad and some good by chance alone. **No individual variant result is evidence.** Only the predeclared summaries in §3 are reported as findings.
- **No cherry-picking:** results are reported in full (every row, both segments, both costs), and no variant may be highlighted as an improvement.
- **Outcome-dependent selection:** D2 (fixed 5 bps ranking; see §3) and any ranking in D7. Both are labelled every time they are shown.
- **No new statistical tests:** no p-values or CIs are produced for variants (§2), which avoids an uncontrolled multiple-testing burden.

---

## 5. Decision rules

**None.** The previously proposed report labels F1–F5 (and the 0.80 threshold proposed for F2) are **WITHDRAWN — not adopted**. DAY-25B has no pass/fail criteria, no thresholds and no flags. Every D1–D7 output is descriptive, and **nothing in DAY-25B can change V2-MOM's status**. No threshold may be introduced after any DAY-25B output exists.

---

## 6. Decisions recorded (finalization, 2026-10-09)

| # | Decision |
|---|---|
| 1 | D1–D7 are the complete and final scope; no diagnostic may be added. |
| 2 | D3: 300 distinct subsets of 20 of 25 symbols, seed `20261008`, explicit PCG64 key algorithm (§3), fixed universe order (§2). |
| 3 | D4b: 252-session rolling windows, step 21 sessions. |
| 4 | Research and historical holdout are analysed separately. |
| 5 | Costs: 5 bps primary; 10 bps secondary for all of D1–D5 and D7; 15/20 bps only as D6 diagnostic overrides. |
| 6 | Subset analyses: B1-sub primary, full-universe B1 secondary. |
| 7 | 2026 is labelled partial (and 2017, as before). |
| 8 | D2 removes the top 2 by \|5 bps flows\| per segment; the same two are removed at 10 bps. |
| 9 | F1–F5 withdrawn; all outputs descriptive; no effect on V2-MOM status. |
| 10 | Frozen config and SHA, implementation, B1/B2 definitions, historical data and forward-OOS boundaries are preserved. |
| 11 | D6 integrity check is a **separate preflight stage executed before any D1–D7 computation**. It recomputes the 0/5/10 bps DAY-19/21 references and requires exact full-precision equality of CAGR and ending equity under identical segment, data, benchmark, capital and conventions. On any CAGR or ending-equity mismatch the entire DAY-25B process aborts, no D1–D7 result is created, and the run is not marked successful. Failure details and the environment fingerprint are recorded in `artifacts/day25b/preflight/preflight_record.json`, separately from diagnostic results. The exact-equality requirement is never relaxed automatically, including when the environment fingerprint differs. Frozen code, reports, configuration and reference values are never changed to force a match. A passing preflight does not authorize any DAY-25B diagnostic: the frozen predeclaration, the reviewed implementation and a separate run authorization are still required. |

Open methodological items: **none**. Freezing requires the steps in §8.

---

## 7. Relation to DAY-25 (existing, not modified)

`artifacts/day25/` and `scripts/day25_robustness.py` remain as they are. DAY-25B differs in four ways:
- **Predeclared before any run.** DAY-25 had no predeclaration, and its tests assert outcomes chosen after the results.
- **Subset-matched B1.** DAY-25's universe drop compared against the full-universe B1 (`run_b1(st)`).
- **Explicit separation of segments, costs and labels.**
- **Correct boundary.** The DAY-25 report header states "Last Allowed Session 2026-10-07", but the evaluated data ends at **2026-06-02**, and that is the boundary DAY-25B uses.

DAY-25's lookback, skip and select sensitivity grids are parameter variants that protocol §16 does not permit as robustness checks. They are **not** repeated in DAY-25B.

---

## 8. Implementation and run (NOT YET IMPLEMENTED; NOT AUTHORIZED)

- Proposed entry point: `scripts/day25b_robustness.py`, run as `python -m scripts.day25b_robustness --out artifacts/day25b/run`. It imports `backtest/v2/*` unchanged.
- Proposed outputs:
  - `artifacts/day25b/run/{d1..d7}.json`, `subsets.json` and `run_summary.json`;
  - a reproducibility block per protocol §17, plus the seed, the numpy version, the subset-list SHA-256, and a reference to the preflight record (`artifacts/day25b/preflight/preflight_record.json`) with its SHA-256.
- Before any run, the following must be in place:
  1. this document and its JSON twin are approved and frozen (committed with their SHA-256 recorded);
  2. the implementation is reviewed, with synthetic-fixture tests, a test of the D3 algorithm, and a check that the config SHA is unchanged;
  3. the run is explicitly authorized.

No DAY-25B result may be described as passing or failing anything.
