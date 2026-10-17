# Independent strategy candidate selection and forward-test protocol review: 2026-10-17

> **Owner decision recorded (2026-10-17):** OD-2 = **REJECT** the proposed TOM-SPY confirmatory forward experiment.
> See §9. The §4 protocol draft below is kept unchanged as history and is **not to be created or run**.

This is a read-only planning document. No experiment, backtest, simulation, parameter search, data download, external
API call or test suite was run. No existing file was modified. No sealed forward-test data, paper-runner ledger,
paper-runner market-data snapshot or Stage F data was opened. Nothing here changes any protocol, gate, seal, schedule,
configuration or ledger. Every protocol change below is a **proposal only**.

**Labels** (same vocabulary as `docs/strategy-evidence-inventory-2026-10-17.md`):
- **FACT:** read directly from the cited file or command output.
- **OBS:** an observation across several files.
- **INF:** an inference.
- **REC:** a recommendation.
- **PROPOSED — REQUIRES APPROVAL:** a value or threshold that no adopted project policy supports.
- **REQUIRES OWNER APPROVAL:** an action the current rules don't clearly permit. It was not performed.

---

## 1. Verified repository state

| Item | Value (FACT, from `git` on 2026-10-17) |
|---|---|
| Working directory | `C:/Users/Admin/Desktop/own/trade` |
| Branch | `feature/day-trading-research`, 3 commits ahead of `origin/feature/day-trading-research` |
| HEAD | `f6d628692f2faa35e41df7e1c59dd1e8d98851e8`: "ORB paper runner: enforce Sharia eligibility gate before market data" |
| Staged files | none (`git diff --cached` is empty) |
| Untracked files before this report | `docs/strategy-evidence-inventory-2026-10-17.md`, `docs/v2-mom-holdout-daily-concentration-2026-10-17.md` |
| Untracked after this report | the two above, plus this file |
| Modified tracked files | none |
| Most recent protocol commits | `a479e20` (v2.3 paper runner; last change to the v2.2/v2.3 adoption records), `5bfa3e3` (v2.4 adopted), `656e99d` (last commit touching `artifacts/day27b`, the v2.5 draft) |

**FACT, operational:** the Stage F capture preflight refuses to run if the tree has **any** untracked file:
`acquisition/v2/stage_f.py:322-323` (`git status --porcelain --untracked-files=all` → `"git working tree not clean"`).
The three untracked `docs/` files will therefore block the `fwd-gate2` capture on 2026-12-09 unless they are committed
or moved first. See §6.4 and OD-7.

**What was inspected:** protocols, adoption records, code (reading only), file listings, and permitted plaintext
health metadata. Specifically:
- the protocol and governance documents in §2;
- `artifacts/v2-experiment-registry.json`;
- the code in `backtest/v2/signals.py`, `backtest/v2/forward.py`, `acquisition/v2/stage_f.py`, `strategy/`,
  `indicators/` and `config/`;
- directory listings of `data/oos_cache/protocol_v2/` and `paper_state/`;
- the plaintext health files `paper_state/heartbeat.json` and `paper_state/last_error.json`.

**What was not opened:**
- `paper_state/sealed/`, `paper_state/runs/` and `paper_state/data/` (the last holds raw bars dated inside the gate
  window);
- any parquet file;
- any Stage F data (none exists);
- the root CSVs.

**Tests were not run.** DAY-26C is the reason: a full `pytest` run downloaded forward-dated market data and
invalidated `fwd-diag` (`artifacts/day26c/day26c-forward-data-incident.md:16-19`). That incident record says "the full
pytest suite is not to be run in this repository for v2 work" (`:61`).

---

## 2. Evidence inventory used for candidate selection

### 2.1 Governing protocol and gate documents

| Document | Status | Rule relevant here |
|---|---|---|
| `artifacts/day16/research-protocol-v2.md` | Frozen (v2.0 R1 and later amendments) | §2 (`:73-85`): a static, hindsight-selected 25-symbol universe, not point-in-time (Q5). §3.6 (`:150-169`): the segments. §14 (`:468-487`): variants: none; any change is a new DERIVED experiment that "can never be confirmed on a segment already used"; winner selection prohibited. §15 (`:489-509`): no rescue. |
| `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md` | Signed off 2026-10-08 | §2 (`:116-124`): V2-STR and V2-LRV STOPPED and "shall not be reopened, modified, re-parameterized, or reconsidered under protocol v2". §3.2 (`:138-157`): no interim peeking, no forward data acquisition, **no forward-guided protocol mutations or new strategy variants**. |
| `artifacts/day26b/protocol-v2.1-amendment.md` | ADOPTED 2026-10-10T12:52:51Z | §6 (`:120-129`): the permission table. §9 (`:169`): `FORWARD42-INVALID` if gate data is seen early **or a frozen item changes after adoption**. §10 (`:186`): a closed list of abandonment reasons, never because of a market observation. |
| `artifacts/day26c/day26c-forward-data-incident.md` | Final | `fwd-diag` = `FWD-DIAG-INVALID (protocol-breach)` |
| `artifacts/day26d/protocol-v2.2-amendment.md` | ADOPTED 2026-10-10T14:56:30Z | `fwd-gate2` / `V2-MOM-F003`: 42 sessions, 2026-10-12 → 2026-12-09 (`:11`). Earliest capture **2026-12-09 16:15 America/New_York** (`:12`, `:49`). §13 gate applied once (`:32`). One fresh Stage F snapshot, 2025-01-02 → 2026-12-09 (`:34`). |
| `artifacts/day27/protocol-v2.3-amendment.md` | ADOPTED 2026-10-10T15:47:33Z | Sealed paper runner `V2-MOM-P001`. It is never gate evidence (P1, `:23`). Plaintext output is health only (P3, `:25`). Any decryption or disclosure before 2026-12-09 16:15 ET makes `fwd-gate2` `FORWARD42-INVALID` (P4, `:26`). It runs indefinitely. |
| `artifacts/day27a/protocol-v2.4-amendment.md` | ADOPTED 2026-10-13T07:05:10Z (`protocol-v2.4-adoption.json`: `final_status: ADOPTED`) | Pinned `FB → META` identity alias only |
| `artifacts/day27b/protocol-v2.5-amendment.md` | **DRAFT — NOT ADOPTED** (`protocol-v2.5-adoption.json`: `PROPOSED_NOT_ADOPTED`) | Paper-runner health fields only; `fwd-gate2` guards unchanged (`§4`) |
| `backtest/v2/forward.py:31-37` | Code | Forward access pins the v2.1, v2.2 and v2.4 adoption records and amendment files by SHA-256. INF: a **new** append-only amendment file would not trip these pins; changing a pinned file would. |

**FACT, current governing version:** `2.0 R1 + 2.0.1 … 2.0.4 + 2.1 + 2.2 + 2.3 + 2.4`. Version 2.5 is not adopted.

### 2.2 Prior strategy work (novelty baseline)

The inventory below was cross-checked against code and registry, not just reports.

| Family | Code / config | Run records | Status (FACT) |
|---|---|---|---|
| Intraday VWAP momentum, with RSI, RVOL, gap, index-regime, time-window, stop and exit variants | `strategy/day/vwap_momentum.py`; `backtest/day_engine.py` (RSI(14) > 50 as a descriptive split, `:394-395`, `:504`); `backtest/failure_analysis.py:157`; `indicators/rsi.py` | `artifacts/day04`–`day15` | DAY-13 OOS gate **NO** (`artifacts/day13/oos-gate.md:5`); DAY-15H research gate FAIL |
| ORB (intraday) | `strategy/day/orb.py`, `orb_rules.py`; `backtest/orb_engine.py`; `paper_orb/runner.py` | `artifacts/orb/` | Not evidence of an edge; not independent; "ready for next test: no" (`artifacts/orb/sip_diagnostic_decision.md:71-73`) |
| V2-MOM (12-1 cross-sectional momentum, top 5) | `backtest/v2/signals.py:43-57` | Registry `V2-MOM-R001`, `-H001` | RESEARCH-PASSED · HOLDOUT-PASSED · forward `fwd-gate2` PENDING |
| V2-STR (weekly 5-day cross-sectional reversal, long-only) | `backtest/v2/signals.py:62-90` | `V2-STR-R001`, `-H001` | HOLDOUT-FAILED (economic) → **STOPPED, no rescue** |
| V2-LRV (pairs, long-only relative value) | `backtest/v2/signals.py:96-140` | `V2-LRV-R001` | RESEARCH-FAILED → **STOPPED** |
| Legacy daily: breakout/retest with EMA 20/50/200 trend filter, SMC zones, six exit models, selection | `strategy/breakout_retest.py`, `strategy/trend.py`, `smc/`, `scripts/backtest_breakout_retest.py`, `scripts/exit_research.py` | `experiments/*.json` (18); `reports/run_log.txt:15-29` | "NO SELECTION EDGE", "NO EXIT EDGE FOUND", exits INCONCLUSIVE; no protocol |

**Searched and NOT FOUND in tracked code, configs, experiment JSONs and artifacts** (`git grep`, read-only):
- calendar or seasonal timing (turn-of-month, day-of-week, holiday). The only hits are incidental wording in
  `artifacts/day23` and `day24` ("annual seasonal cycle");
- low-volatility or defensive selection. The only hit is regime wording in `artifacts/day25/day25-robustness-report.md:186`;
- post-earnings drift. `config/earnings_calendar.csv` holds ORB earnings **dates** only (columns
  `symbol,coverage_start,coverage_end,earnings_date`), with no surprise data;
- 52-week-high momentum. `scripts/core_monitor.py:53-98` only displays a "% below 52-week high" monitor column.

### 2.3 Data and eligibility constraints

- **FACT, approved data:**
  - provider: Alpaca SIP daily raw and `all` bars plus corporate actions (`day16 …:89-101`);
  - v2 vault snapshots hold the 25 universe symbols and **SPY**. SPY's raw and `all` daily bars exist in
    `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/` and `.../stage_h/stage_h_20261008T100604Z/`
    (directory listing only; contents not opened);
  - coverage: 2016-01-04 → 2026-06-02 (warmup + research + holdout).
- **FACT, data-date restrictions:**
  - data dated **≥ 2026-10-12** for the 25 symbols and SPY is gate-window data. It may not be acquired, computed or
    inspected before 2026-12-09 16:15 ET (`day26d …:12`; `day22 …:154-155`);
  - 2026-06-03 → 2026-10-07 is "Excluded … never evaluated" for v2 (`day16 …:160`, rationale 3 at `:167`).
- **FACT, point-in-time universe:** no point-in-time universe source exists. Survivorship is "known limitation, not
  solved" (`day16 …:80-81`).
- **FACT, Sharia eligibility:**
  - `config/sharia_eligibility.csv` is header-only (1 line);
  - the only accepted methodology is Akinda `/compliance` (D13-A, `docs/shariah/AAOIFI_MVP_DECISIONS.md:9,21`). It
    has no backfill: "a verdict never covers a session before it was retrieved"
    (`docs/shariah/AKINDA_PROVIDER_DECISION.md:75`). A point-in-time Sharia screen for a historical test is therefore
    impossible;
  - D12 (day-trading permissibility) is ADVISER_REQUIRED (`AAOIFI_MVP_DECISIONS.md:42`);
  - D13: ETF or index membership is never evidence (`:43`);
  - D10: purification for period-end holders is ADVISER_REQUIRED (`:40`).

### 2.4 Structural constraint on any new candidate

OBS: every new candidate faces the same constraints.

1. **The 25-symbol universe has no untouched historical segment.**
   - Research and holdout are consumed, with per-symbol and per-year results published in DAY-19, DAY-21, DAY-22 and
     DAY-25B.
   - 2026-06-03 onward was viewed by intraday research.
   - The gate window is sealed.
2. **No point-in-time universe** exists to build a new one.
3. **No historical Sharia screen** is possible.
4. **Forward evidence is slow.** Any daily strategy needs many months of genuinely new data, and none can be acquired
   for the gate's instruments before 2026-12-09.

---

## 3. Candidate comparison and selection

Three families survived a first screen and were examined. Families screened out immediately:
- **Breakout/retest and ORB:** already tested (§2.2).
- **A trend or regime filter on V2-MOM:** a variant of the frozen strategy, prohibited during the lockdown by
  `day22 …:140-148,156-157`. DAY-08 already tested an index-regime filter for VWAP.
- **Post-earnings drift:** no approved surprise data.
- **Cross-asset trend on bond or commodity ETFs:** not in the approved data; bond ETFs are interest-bearing (Sharia).
- **Any intraday family:** D12 is unresolved, and there is no non-overlapping intraday data.

| | **C1: Turn-of-month (TOM) calendar timing, SPY** | **C2: Cross-sectional low-volatility, frozen 25** | **C3: Daily RSI(2) oversold mean reversion, frozen 25** |
|---|---|---|---|
| Hypothesis | Broad-index returns are higher on the last session of a month and the first three sessions of the next than on other sessions. Cited mechanism: month-end flows and payroll investing (literature claim; not verified in this task). | Lower-volatility stocks earn higher risk-adjusted returns than higher-volatility stocks (low-vol anomaly). | Short-horizon oversold stocks rebound. |
| Distinct from prior work? | **Yes.** No calendar timing in any code, config or artifact (§2.2). Timing of one instrument, not selection among 25. | Partly. It's a new signal, but it's another long-only top-k selection rule in the same universe against the same B1, i.e. a fourth v2-style family. | **No.** Economically the same hypothesis as V2-STR (short-horizon reversal, long-only losers), which is STOPPED with no rescue (`day22 …:119,124`). RSI is already a feature in the VWAP research. A rename. |
| Existing evidence in repo | None, positive or negative | None directly. INF: the hindsight universe and the published per-symbol holdout results (tech mega caps dominant, `day22 …:105-106`) make the direction of a 2017–2026 result largely predictable to the authors. | V2-STR: holdout 22.19% vs B1 53.24%, cost drag 5.04 pp (`docs/strategy-evidence-inventory-2026-10-17.md` §4) |
| Independent test possible? | **Yes, with limits.** SPY is a single, continuously listed instrument (no survivorship issue for the instrument itself). Its historical bars are in the approved vault. The decisive test can be a pre-registered forward window that starts after the gate window. | **No** credible untouched historical segment (§2.4). A forward test would overlap V2-MOM's universe and invite cross-family winner comparison (`day16 …:482`). | No: STOPPED family |
| Data | Approved and already vaulted (SPY 2016-01-04 → 2026-06-02). Forward SPY data only after the gate (SPY is `fwd-gate2`'s B2). | Approved (same vault) | Same |
| Discretionary choices | Few. Window definition fixed from the literature (L, F1–F3), one instrument, one execution convention. | Volatility window, k, rebalance frequency: several free choices with no project precedent | — |
| Costs / turnover | About 12 round trips a year. At 5 bps per side that's about 1.2% a year of notional (arithmetic). | Low-moderate | High (V2-STR precedent) |
| Implementation complexity | Low. Calendar flags reuse `month_end_flags` (`backtest/v2/signals.py:24`); single-asset accounting. | Moderate | — |
| Sharia / eligibility | **New question.** SPY holds non-compliant issuers, so a SPY result is a **research-only hypothesis test**. Trading it would need a compliant vehicle (e.g. a Sharia-screened ETF), whose instrument eligibility is undecided under D13. A month-end holding also touches D10 purification. Not day trading, so D12 doesn't apply. | All 25 are unscreened (registry empty) | — |
| Main failure modes | (a) **Low statistical power** (§4.9). (b) Post-publication decay. (c) A broad index can't be "unseen" in the forward window. Blinding here means no computation and no rule changes. (d) It may still fail economically after costs. | Hindsight-predictable outcome; selection bias against B1; multiple testing on consumed data | — |
| Grounds to reject | Development segment Δ ≤ 0 → stop. Or the owner judges a probably-inconclusive forward test not worth the time. | **Rejected:** no credible test design on unused data | **Rejected:** renames a STOPPED family |

### Selection

**REC: C1 (turn-of-month timing on SPY) is CONDITIONALLY SELECTED for pre-registration only.**

- It is the only candidate that:
  - is genuinely distinct from all prior work;
  - uses approved, already-vaulted data;
  - has few discretionary choices;
  - can be tested without touching the sealed gate.
- It is **not** selected because of published performance. The literature is used only to fix the window definition
  in advance and avoid choosing it.
- **The selection lapses to `NO CANDIDATE SELECTED`** if the owner does not accept the decisions OD-1 to OD-4 in §6,
  in particular OD-2. OD-2 is the explicit acknowledgment that a 24-month forward test is expected to be
  **INCONCLUSIVE** unless the effect is large (§4.9).
- Repository evidence for C1's profitability: **none**. This is a hypothesis test, not a promising strategy.

---

## 4. Draft pre-registered experiment protocol: `TOM-SPY` (PROPOSED — NOT ADOPTED, NOT AUTHORIZED TO RUN)

Every numeric threshold below that no adopted project policy supports is labelled **PROPOSED — REQUIRES APPROVAL**.
Conventions taken over from protocol v2 are labelled **EXISTING CONVENTION**.

### 4.1 Research question and falsifiable hypothesis

- **Question:** do SPY's open-to-open total returns on turn-of-month sessions exceed those on all other sessions, by
  enough to survive costs in a long-only, TOM-only exposure strategy?
- **Definitions:**
  - for XNYS session `k`, the daily return is `r_k = (O_{k+1} · q + d) / O_k − 1`, where `q` is the split ratio and
    `d` the cash dividend with ex-date `k+1` (series A raw opens plus the event list; the same event semantics as
    `day16 …:117-140`);
  - TOM set: the last XNYS session of each calendar month (L) and the first three XNYS sessions of the next month
    (F1, F2, F3);
  - `Δ = mean(r_k : k ∈ TOM) − mean(r_k : k ∉ TOM)`.
- **H0:** Δ ≤ 0.
- **H1:** Δ > 0.
- **Falsified (FAIL)** if Δ ≤ 0 in the forward test window.
- **One definition only.** Variants such as −1…+4 or close-to-close are **not** tested. Any change is a new derived
  experiment that can't be confirmed on a used segment (mirrors `day16 …:476`).

### 4.2 Strategy rules (no discretion)

| Item | Rule |
|---|---|
| Instrument | SPY only (research-only, see §3) |
| Entry | Market-on-open buy at the raw open of L, to target weight 1.0 of equity. The calendar is known in advance, so there is no signal look-ahead. |
| Exit | Market-on-open sell of the full position at the raw open of F4, the fourth session of the new month |
| Exposure otherwise | 100% cash at 0% (EXISTING CONVENTION, `day16` Q7; also consistent with D15, no interest) |
| Window overlap | Impossible: L and F1–F3 of consecutive months are disjoint |
| Calendar | `exchange_calendars` 4.13.2 XNYS, America/New_York (EXISTING CONVENTION). An unscheduled closure triggers re-derivation before acquisition and a documented review, never substitution. |
| Missing open at L | No entry that month; recorded |
| Missing open at F4 | Exit at the next available session open; recorded |
| Leverage, shorting, stops | None |
| Rationale for open fills | Matches the frozen v2 execution convention (raw open fills, `day16` §8). Close-to-close is the canonical literature definition, so this deviation is disclosed, and close-to-close is never also tested. |

### 4.3 Data, universe and eligibility

- **Data:** Alpaca SIP `1Day` raw bars plus corporate actions for SPY (EXISTING CONVENTION). `adjustment=all` is used
  for audit only.
  - **Historical stages:** the existing vault snapshots only (`stage_r_20261007T093410Z`, `stage_h_20261008T100604Z`).
    No new acquisition.
  - **Forward stage:** one write-once snapshot, acquired once after the forward window ends.
- **Universe:** a single instrument that existed throughout. Point-in-time universe construction is not applicable;
  instrument survivorship is not an issue (disclosed). Index reconstitution inside SPY is point-in-time by
  construction of the fund.
- **Eligibility:** research-only. **No PASS authorizes trading.** A tradable vehicle needs OD-3.

### 4.4 Segments (PROPOSED — REQUIRES APPROVAL)

| Segment | Dates | Role | Blind? |
|---|---|---|---|
| Development (`TOM-SPY-D001`) | 2017-02-01 → 2022-12-30 (same calendar rule as v2 Research, `day16 …:158`) | First kill test | No. SPY was used for B2, but its TOM decomposition was never computed in the repository. |
| Validation (`TOM-SPY-V001`) | 2023-01-03 → 2026-06-02 (same as v2 Holdout) | Second kill test (pseudo-OOS) | No (labelled pseudo-OOS) |
| Excluded | 2026-06-03 → last session before the forward start | Never used | — |
| **Untouched test (`TOM-SPY-F001`)** | **First XNYS session of the first calendar month starting strictly after both the adoption commit and 2026-12-09.** If adopted before 2026-12-31, that is **2027-01-04 → 2028-12-29**: 24 calendar months, 24 TOM windows. | **Decisive** | Yes: no TOM computation and no rule changes until it ends |

INF: starting after the gate window keeps every TOM data window disjoint from `fwd-gate2`, including its SPY B2
leg. Owner alternative: OD-5.

### 4.5 Baselines

1. **Primary statistical null:** non-TOM sessions of the same instrument and segment (defines Δ).
2. **Exposure-matched timing null (permutation):**
   - for each calendar month in the segment, a block of 4 consecutive sessions starting at a uniformly random session
     of that month;
   - 100,000 draws, seed 20261017, recorded;
   - one-sided `p = (1 + #{Δ* ≥ Δ}) / (1 + N)`.

   This preserves exposure and block length. **PROPOSED — REQUIRES APPROVAL.**
3. **SPY buy-and-hold:** reported only, **not gated**. TOM-only exposure is about 19% of sessions, so beating
   buy-and-hold on total return is not the hypothesis.

### 4.6 Costs, sizing and risk

- **Costs:** 0 / **5 (primary)** / 10 bps per side on traded notional, as separate deterministic runs (EXISTING
  CONVENTION, `day16` §9). There is no spread or impact model; 5 bps is a friction scenario, not an estimate.
- **Sizing:** E₀ = 100,000. Fractional shares, which are disclosed (EXISTING CONVENTION). Dividends are credited as
  cash on the ex-date.
- **Exposure limit:** ≤ 1.0. Cash ≥ 0.
- **Drawdown controls:** none inside the rule, since a stop would add parameters. Max drawdown is reported. The
  experiment stops only under §4.10.

### 4.7 Metrics

- **Primary:** Δ (forward segment), with the one-sided permutation p-value (§4.5 item 2).
- **Secondary:**
  - HAC (Newey–West, lag 5) t-statistic of the difference (diagnostic);
  - TOM-strategy net total return and CAGR at 0/5/10 bps;
  - max drawdown;
  - exposure;
  - turnover and cost drag;
  - per-window hit rate;
  - worst window;
  - Δ by calendar year;
  - SPY buy-and-hold for reference.
- **Multiple testing:**
  - one family, one hypothesis, m = 1, with no variants;
  - the report must disclose the project's prior trial history (about 40 VWAP variants, ORB, three v2 families,
    legacy exit models) as context, not pooled.
- The segments are **never pooled**.

### 4.8 Decision criteria (all thresholds PROPOSED — REQUIRES APPROVAL)

| Stage | Criteria | Outcomes |
|---|---|---|
| **A: validity, all stages (hard fail)** | No look-ahead (fill-source and timing tests); data structural checks pass; two identical runs are byte-identical; reproducibility block complete (same item list as `day16` §17); the frozen config SHA-256 matches | Any failure → `TOM-FAILED (methodological)` |
| **Development** | Δ_D > 0 **and** TOM-strategy net total return @5 bps > 0 | Both → proceed to Validation. Otherwise `TOM-STOPPED-DEV`. The p-value is reported, not gated. |
| **Validation** | Same two conditions on the validation segment | Both → eligible for forward. Otherwise `TOM-STOPPED-VAL`. No re-run, no rescue. |
| **Forward (decisive)** | **PASS:** A passes, Δ_F > 0, permutation p ≤ 0.05, **and** net total return @5 bps > 0 | `TOM-FORWARD-PASSED` (research evidence only; not trading authorization) |
| | **FAIL:** Δ_F ≤ 0 | `TOM-FORWARD-FAILED` |
| | **INCONCLUSIVE:** Δ_F > 0 and p > 0.05; **or** Δ_F > 0 and p ≤ 0.05 but net return @5 bps ≤ 0 | `TOM-FORWARD-INCONCLUSIVE`, with the reason stated |

Notes:
- Equality of Δ to 0 counts as FAIL, since H0 includes 0.
- Unrounded float64 values are used throughout (EXISTING CONVENTION).

### 4.9 Power: why INCONCLUSIVE is the likely forward outcome (ASSUMPTION-based arithmetic, no data used)

**ASSUMPTION:** SPY daily return standard deviation σ ≈ 1.1%. This is a generic assumed value, not computed from any
file. Returns are treated as i.i.d.; real heteroskedasticity makes the numbers worse.

The minimum detectable Δ at 80% power with a one-sided α of 0.05 is `MDE ≈ 2.49 · σ · √(1/n_TOM + 1/n_other)`.

| Segment | n_TOM / n_other (approx.) | MDE per session |
|---|---|---|
| Development (1,490 sessions) | 284 / 1,206 | ≈ 0.18% |
| Validation (856) | 164 / 692 | ≈ 0.24% |
| Forward, 24 months (≈ 502) | 96 / 406 | ≈ **0.31%** |
| Forward, 60 months (≈ 1,260), alternative | 240 / 1,020 | ≈ 0.20% |

- INF: an excess of 0.2–0.3% **per session** on a broad index would be very large.
- The forward test is therefore powered mainly to **falsify** (Δ ≤ 0 → FAIL) or to return INCONCLUSIVE, not to
  confirm. OD-2 asks the owner to accept this or lengthen the window.

### 4.10 Untouched-test rules

1. The protocol is frozen and its SHA-256 is pinned in an owner adoption record **before** the forward window starts.
2. No SPY data dated inside the forward window is acquired into any research path, and no TOM statistic is computed,
   until the window has ended and a preflight passes. The preflight covers: time, adoption pins, clean tree, frozen
   config SHA, and no existing forward snapshot.
3. INF: general market observation (news, prices) can't be prevented for a broad index. Blindness is defined as no
   computation, no inspection of derived statistics and no rule changes.
4. `V2-MOM-P001` runs indefinitely with SPY as its B2 benchmark (`day27 …:16`, `:23`). Its post-seal outputs
   covering the TOM forward window must **not** be used to compute TOM statistics. Proposed rule: deriving Δ from P001
   outputs before the TOM window ends = `TOM-FORWARD-INVALID (protocol-breach)`.
5. One forward evaluation run, plus one determinism re-run. Technical re-runs only with an identical configuration;
   both are kept.
6. Abandonment is allowed only if the protocol is withdrawn before the forward window starts, or the frozen provider
   cannot supply the data (documented review). Never because of market behaviour.

### 4.11 Artifacts and reproducibility (PROPOSED paths)

- **Protocol:**
  - `artifacts/day28/tom-spy-protocol-v1.md` and `.json` twin;
  - adoption record `artifacts/day28/tom-spy-protocol-v1-adoption.json`.
- **Runs:**
  - `artifacts/day28/tom/TOM-SPY-D001/`, `.../TOM-SPY-V001/`, later `artifacts/<dayNN>/tom/TOM-SPY-F001/`;
  - each with `run_summary.json` and a reproducibility block (git SHA and dirty flag, environment fingerprint,
    snapshot ID and manifest SHA-256, config SHA-256, command line, seed, output SHA-256), daily returns, the TOM flag
    series, fills, the permutation distribution summary, and metrics at 0/5/10 bps.
- **Registry:** a new append-only `artifacts/tom-experiment-registry.json`. OD-6 covers using the v2 registry instead.
- **Final report format:** like DAY-21. Gate table A/B/stage; metrics table; per-year Δ; deviations; limitations
  (power, non-blind historical stages, research-only instrument); integrity affirmation.
- **Code needed (NOT YET IMPLEMENTED):**
  - TOM flag function;
  - single-asset open-to-open return series with events;
  - permutation test;
  - forward guards modelled on `backtest/v2/forward.py`.

  Separately authorized. Offline synthetic tests only; never the full `pytest` suite (DAY-26C).

---

## 5. Forward-test protocol decision memo (V2-MOM `fwd-gate2`)

**Current state (FACT):**
- `fwd-gate2` is PENDING, covering 42 sessions from 2026-10-12 to 2026-12-09, with capture no earlier than
  2026-12-09 16:15 ET;
- `fwd-diag` is INVALID;
- the old `fwd-gate` is SUPERSEDED;
- `V2-MOM-P001` is sealed until the same time.

**Paper-runner health (FACT, plaintext health files only):**
- `heartbeat.json`: last run 2026-10-13T08:15:32Z, status OK, `processed_total: 1` (2026-10-12);
- `last_error.json`: `DataFailClosed: corporate-action identity conflicts` at 2026-10-13T05:37:50Z, which was before
  the v2.4 fix.
- INF: the runner has not run since 2026-10-13. v2.3 P6 provides catch-up, and P001 is never gate evidence
  (`day27 …:23`), so this does not affect `fwd-gate2`. The runner was not executed in this task.

| | **Option 1: preserve unchanged** | **Option 2: preserve, plus a future append-only amendment** | **Option 3: replace or terminate** |
|---|---|---|---|
| Effect on validity | None. The gate is evaluated as adopted. | None, **if** the amendment changes no pinned file, calendar, threshold, config or guard, and does not touch the sample. A change to a frozen item = `FORWARD42-INVALID` (`day26b …:169`). | Ends or replaces the only true forward evidence. A second restart after DAY-26D erodes credibility (DAY-26C/D precedent). |
| Permitted by current rules? | Yes; it's the default (`day26d …:32`) | Append-only amendments are the established mechanism (v2.3, v2.4). **However**, DAY-22 §3.2.4 (`:156-157`) forbids blind-period observations motivating protocol changes or new variants. Justification must rest only on pre-gate evidence. **REQUIRES OWNER APPROVAL.** | v2.2 restates the `FORWARD42-ABANDONED` label but not the closed reason list. The v2.1 list (`day26b …:186`) refers to the superseded `fwd-gate` and Stage F-D. No rule clearly permits termination of `fwd-gate2` → **REQUIRES OWNER APPROVAL**. Market observation is never a valid reason. |
| Existing sealed sample | Unchanged; one evaluation after capture | Unchanged; the new segment is disjoint (it starts after 2026-12-09) | Becomes unusable or ambiguous |
| Future sample | None defined after 2026-12-09 | A pre-registered follow-on segment (e.g. `fwd-gate3`) can be defined **before** the `FORWARD42` result exists. That avoids an outcome-dependent "extend or not" decision later. | Undefined |
| Authorization and documentation | None new. Operational items in §6.4. | Owner adoption record with pinned SHA-256 (v2.x pattern), committed before 2026-12-09 16:15 ET. An affirmation that no gate data was seen. A rationale citing only DAY-23, v2.1 §12 and DAY-21 p = 0.166. | Owner decision plus a new amendment defining the reason. Disclosure. |
| Leakage, selection bias, ambiguity | None | Low, if adopted before the result and made **unconditional** (runs whatever `FORWARD42` says). If adopted after the result: outcome-dependent, so it must be labelled DERIVED. | High: which protocol was tested becomes ambiguous |

**REC: Option 1 now. Option 2 is optional and only by explicit owner decision before 2026-12-09 16:15 ET.**

**The candidate content of Option 2** (a proposal, not drafted as an amendment):
- an unconditional, longer follow-on blind V2-MOM segment after 2026-12-09, under the unchanged §13 gate;
- motivation: the project itself records that 42 sessions is weak evidence (`day26b …` §12;
  `day26d …:7` "A 42-session forward gate is weak long-term evidence").

**The TOM-SPY proposal in §4 does not require changing `fwd-gate2`.** It is a separate protocol. Its data windows are
disjoint from the gate, and it acquires nothing before 2026-12-09.

---

## 6. Remaining unknowns and owner decisions

### 6.1 Owner decisions required for TOM-SPY (selection lapses without OD-1 to OD-4)

| ID | Decision |
|---|---|
| OD-1 | Whether to open a non-v2 research protocol (`TOM-SPY v1`) during the V2-MOM blind period. It touches no gate data, but it is new research activity under DAY-22 §3.2.4 scrutiny. |
| OD-2 | Accept that a 24-month forward test is mainly a falsification test and is likely INCONCLUSIVE (§4.9), **or** set a longer window, e.g. 60 months, before adoption |
| OD-3 | Instrument: SPY as a research-only hypothesis test, accepting that no PASS is tradable; **or** route the instrument-eligibility question for a Sharia-screened ETF to the owner or adviser (D13 does not cover ETFs as instruments; D10 purification for month-end holdings) |
| OD-4 | Approve every **PROPOSED — REQUIRES APPROVAL** value: segments, the permutation null and seed, p ≤ 0.05, net return > 0 @5 bps, the outcome mapping |

### 6.2 Other owner decisions

| ID | Decision |
|---|---|
| OD-5 | Forward start alternative: begin right after adoption (overlapping the gate window in time, though data is still acquired only after the window ends) vs the proposed post-2026-12-09 start |
| OD-6 | Registry: a separate `tom-experiment-registry.json` vs appending to the v2 registry |
| OD-7 | **Before 2026-12-09 16:15 ET:** commit or relocate the untracked `docs/` files, so the Stage F preflight's clean-tree check (`acquisition/v2/stage_f.py:322-323`) passes. Committing was not done here (out of scope). |
| OD-8 | Whether to adopt Option 2 (follow-on blind segment) before the gate result exists |
| OD-9 | Paper runner `V2-MOM-P001` has not run since 2026-10-13 (health metadata). Whether and where to resume it. It is not gate evidence. |
| OD-10 | Disposition of the v2.5 draft (paper-runner-only; independent of `fwd-gate2`) |

### 6.3 Unknowns

1. Whether `fwd-gate2` has a defined closed list of abandonment reasons (v2.2 does not restate one).
2. Whether any SPY TOM decomposition was ever computed outside the repository. NOT FOUND in the repository.
3. The actual SPY volatility and the published TOM effect sizes. Not checked (no external calls); §4.9 rests on an
   assumption.
4. Whether the GitHub Actions paper workflow is active anywhere. `day27 …` §3 says "not activated"; current state
   UNCONFIRMED.
5. Instrument eligibility of any ETF under the project methodology.

### 6.4 Operational readiness of the existing gate (FACT-based; no action taken)

- The capture command is fixed (`day26d …` §4, S7–S9). The preflight requires a clean tree with no untracked files
  (OD-7).

---

## 7. Single recommended next action

**REC:** the protocol owner reviews this document and decides OD-1 to OD-4, starting with OD-2 (accept or lengthen
the underpowered forward window).
- **If accepted:** the next task drafts `artifacts/day28/tom-spy-protocol-v1.md` and its JSON twin for adoption.
  Drafting only; no data, code or runs.
- **If not accepted:** the outcome is `NO CANDIDATE SELECTED`, and V2-MOM stays the only active candidate.
- **In either case:** `fwd-gate2` is preserved unchanged (Option 1), and OD-7 is resolved before 2026-12-09 16:15 ET.

---

## 8. Integrity affirmation

- No experiment, backtest, simulation, parameter search, data download, external API call or test run.
- No sealed, Stage F, paper-runner ledger, paper-runner run record or paper-runner market-data file opened. Only
  `paper_state/heartbeat.json` and `paper_state/last_error.json` (plaintext health) were read.
- No parquet or market-data file opened. Vault contents were checked by directory listing only.
- No existing file modified. No commit, push, deployment or trading. Exactly one new file: this report.
- Candidate C1 was not motivated by any blind-period market observation (DAY-22 §3.2.4).

---

## 9. Owner decision log (append-only)

Sections 1–8 above are the original 2026-10-17 review and are not edited. Entries below are appended only.

### 9.1 OD-2: TOM-SPY confirmatory forward experiment (2026-10-17)

| Field | Value |
|---|---|
| Decision ID | **OD-2** (§6.1) |
| Decided by | Protocol owner, explicit instruction, 2026-10-17 |
| Decision | **REJECT** the proposed TOM-SPY confirmatory forward experiment (§4, `TOM-SPY-F001`) as impractical under the evaluated power assumptions. Neither option offered in §6.1 (24-month window accepted as mainly a falsification test, or a 60-month window) is accepted. |
| Rationale | The proposed 24- and 60-month forward windows are insufficiently powered for plausible modest TOM effects (details below). |
| Consequence | `artifacts/day28/tom-spy-protocol-v1.md` (and its JSON twin and adoption record, §4.11) is **not** created. No TOM-SPY confirmatory forward test is scheduled or run under this rejected design. The §7 "if accepted" branch does not apply. |
| Scope limitation | This rejects the **proposed confirmatory forward design only**. It does not establish that the TOM hypothesis is false, or that every TOM strategy is ineffective, and it does not rule out a different future exploratory or re-scoped study (which would need its own owner decision). |
| Sharia / instrument | **Unresolved.** SPY was considered as a research-only instrument (§4.3, OD-3). It is not labelled Sharia-compliant, and this decision does not change that. |
| `fwd-gate2` / `V2-MOM-F003` | Unaffected. No gate, seal, schedule, configuration, protocol or capture file is changed by this decision. |

**Evidence provenance.**
- **FACT:** the power analysis behind this decision was delivered as a terminal report in a Claude Code session on
  2026-10-17. **No report file exists in the repository**; none is cited here by filename.
- **FACT:** §4.9 of this document is the earlier, simpler in-repo version of the same arithmetic (i.i.d., σ ≈ 1.1%) and
  gives the same headline MDEs.
- **Method (as reported):** session counts from the `exchange_calendars` 4.13.2 XNYS calendar only (24 months:
  96 TOM / 406 other sessions; 60 months: 240 / 1,015); analytic power for a one-sided test at α = 0.05; and a Monte
  Carlo on **synthetic** returns only. No SPY prices, vault data, sealed data or external sources were used.
- **Stated assumptions (not estimated from data):** per-session σ ≈ 1.1% (sensitivity 0.8–2.0%); drift ≈ 0.04% per
  session; literature effect sizes of roughly 0.1–0.15% per session, cited from memory and **unverified**; 5 bps per
  side costs.

**Reported findings (conditional on those assumptions, not universal facts).**
- The 24-month design reaches about 80% power only for an effect of about **0.31% per session**.
- The 60-month design reaches about 80% power only for an effect of about **0.20% per session**.
- Plausible effects of **0.05–0.15% per session** would need substantially longer observation (roughly 9 years or more
  at 0.15%, and decades at 0.05%, under the base-case σ).
- The proposed "net total return @5 bps > 0" condition does not by itself establish a TOM effect: with general market
  drift it is met in roughly half of synthetic runs even with no TOM effect at all.
- The report also noted two count corrections to §4.9 (Validation 166/690 rather than 164/692; 60 months
  1,255 sessions rather than ≈ 1,260) and definitional issues with the §4.5 permutation null. These are not edited in
  §4 because the design is rejected.

**Effect on the other §6 items.**
- **INF:** under the §3 rule ("the selection lapses to `NO CANDIDATE SELECTED` if the owner does not accept … OD-2"),
  the conditional selection of C1 lapses. The owner has not separately confirmed this label; it is recorded as an
  inference, not a decision.
- OD-1, OD-3 (as it applies to TOM-SPY), OD-4, OD-5 and OD-6 concern only the rejected design and are left
  undecided.
- OD-7 (clean tree before the `fwd-gate2` capture) still applies: this entry itself is an uncommitted change and must
  be committed, or otherwise resolved, before 2026-12-09 16:15 ET. OD-8 to OD-10 are unaffected.

### 9.2 Candidate-selection status: `NO CANDIDATE SELECTED` (2026-10-17)

| Field | Value |
|---|---|
| Decision | **`NO CANDIDATE SELECTED`** |
| Decision date | 2026-10-17 |
| Decision authority | Protocol owner (the user), explicit confirmation, 2026-10-17 |
| Relationship to §9.1 | Confirms the outcome that §9.1 recorded only as an inference. From this entry on, it is an owner decision, not an inference. Consistent with OD-2 (§9.1) and with the §3 lapse rule and the §7 "if not accepted" branch. |
| Rationale | Under OD-2 the TOM-SPY confirmatory forward experiment was rejected for insufficient statistical power (§9.1). The current evidence is not sufficient to select any new candidate. C1 (TOM-SPY) lapses; C2 and C3 (§3) were not selected and remain unselected. |
| Interpretation | This does **not** show that every strategy, or every TOM hypothesis, is ineffective. It records only that no new candidate is selected on the current evidence. |
| `fwd-gate2` / `V2-MOM-F003` | Unchanged. The gate, its schedule, configuration and sealed data are not touched. V2-MOM remains the only active candidate (§7). |
| What this does not authorise | No new strategy, experiment, protocol, backtest, capture or acquisition is started or permitted by this entry. Any future candidate needs a new owner decision. |
