# DAY-26A — 21-Session Forward Observation Amendment (Draft)

> **STATUS: PROPOSED — NOT EFFECTIVE.**
> This is a draft for protocol-owner review. It changes no protocol rule, no strategy, no configuration and no existing artifact. It takes effect only if the protocol owner signs it off in a separate adoption commit (§10). **The observation has not been started.** Until adoption, the frozen protocol (DAY-16 §3.6, DAY-22 §3) remains the only effective forward rule.

| Field | Value |
|---|---|
| Drafted | 2026-10-10 (starting HEAD `8ef01f4`) |
| Proposal | A **non-gating, blind, one-pass 21-session forward observation** of V2-MOM |
| Window | **2026-10-08 → 2026-11-05** (21 XNYS sessions, `exchange_calendars` 4.13.2) |
| Strategy | V2-MOM, unchanged: strategy-config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` |
| Relationship to DAY-24 | A separate, alternative amendment. DAY-24 (63 sessions, proposed "v2.0.5") is **not edited, withdrawn or superseded by this draft**; its fate is open decision OD-2 |
| Gate effect | **None.** No outcome of this observation is `FORWARD-PASSED` or `FORWARD-FAILED` (§8) |
| Open decisions | OD-1 … OD-5 (§11). **OD-1 is critical and blocks adoption.** |

---

## 1. Sources and lineage

Facts in this draft are quoted only from the committed documents below. Where something is not established by them, the text says so.

| Document | Status | What it says about forward OOS |
|---|---|---|
| `artifacts/day16/research-protocol-v2.md` §3.6, §3.9, §15 | **Frozen, effective** | Forward OOS = the **252** XNYS sessions starting at the first session after the freeze commit. Stage F is acquired once, after the period ends and not before 16:15 ET. "No interim forward performance is computed or inspected" (§15.6). The length "is never extended or shortened after looking" (§3.6 rationale 5). |
| `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md` | **Signed off, effective** | V2-MOM FROZEN FOR FORWARD OOS; window 2026-10-08 → 2027-10-08 (252 sessions). §3.2: no interim metrics, no forward data acquisition before the end, no forward-guided protocol changes. |
| `artifacts/day23/day23-forward-oos-252-session-audit.md` | Audit, no rule change | "PROTOCOL AMENDMENT MAY BE WARRANTED". §8.2 gives five conditions under which a shorter window keeps blindness: amendment before any forward data; fixed N*; frozen config SHA; one-shot evaluation; no interim inspection. |
| `artifacts/day24/day24-forward-oos-duration-amendment-design.md` | **PROPOSED — NOT YET EFFECTIVE** | Recommends 63 sessions (2026-10-08 → 2027-01-07) as the gating forward window. Its §2 table **rejects 20 sessions**: "Insufficient rebalance depth; 1 rebalance cannot evaluate factor drift". |
| `artifacts/day25/day25-robustness-report.md` | Research report | Records DAY-24 as "PROPOSED 63-session forward OOS amendment (not yet adopted)". |
| `artifacts/day25b/` (predeclaration + `run/`) | Descriptive diagnostics | No output changes V2-MOM's status or the forward-OOS boundaries. |

Lineage of the forward-window length:

| Step | Length | Status |
|---|---|---|
| DAY-16 §3.6 | 252 sessions | frozen |
| DAY-22 §3.1 | 252 sessions, 2026-10-08 → 2027-10-08 | signed off (effective) |
| DAY-24 | 63 sessions, 2026-10-08 → 2027-01-07 (gating) | proposed, not adopted |
| **DAY-26A (this draft)** | **21 sessions, 2026-10-08 → 2026-11-05 (non-gating observation)** | **proposed, not adopted** |

### Differences that matter

1. **DAY-24 rejected a ~20-session window as a gating test.** This draft does not contradict that finding. It proposes 21 sessions only as a **non-gating observation**: an operational and blindness check with descriptive output. It does not test "factor drift" or economic survivability.
2. **The 252-session window is still effective.** DAY-22 locked it, and DAY-24 has not been adopted. This draft cannot change that by itself.
3. **Acquiring forward data after session 21 conflicts with any longer gating window that also starts on 2026-10-08** (§15.6, DAY-22 §3.2). See OD-1.
4. **The forward period has already begun.** By the existing start rule (§3.6, DAY-22 §3.1) it started on 2026-10-08. As of drafting (2026-10-10), two sessions have elapsed. According to the repository's documented record, no forward data has been acquired or inspected; this draft adds none. DAY-23 §8.2 condition 1 ("amendment before any forward data is acquired") can therefore still be met, provided adoption happens before Stage F (OD-4, OD-5).

---

## 2. Window and calendar

Computed from the `exchange_calendars` 4.13.2 `XNYS` schedule. This is calendar information, not market data. No holiday or early close falls inside the window (the next weekday non-session is 2026-11-26).

| # | Session | Day | Event (rule source) |
|---|---|---|---|
| — | 2026-10-07 | Wed | Last Excluded session (§3.6). Its close is the formation point for the initial portfolio. Formation reads earlier data only, which is point-in-time legal (§3.6 rationale). |
| 1 | 2026-10-08 | Thu | Window starts flat (§11.6, E_0 = 100,000). Initial portfolio construction at the open, as described in DAY-24 §5.2. |
| 2 | 2026-10-09 | Fri | |
| 3 | 2026-10-12 | Mon | |
| 4 | 2026-10-13 | Tue | |
| 5 | 2026-10-14 | Wed | |
| 6 | 2026-10-15 | Thu | |
| 7 | 2026-10-16 | Fri | |
| 8 | 2026-10-19 | Mon | |
| 9 | 2026-10-20 | Tue | |
| 10 | 2026-10-21 | Wed | |
| 11 | 2026-10-22 | Thu | |
| 12 | 2026-10-23 | Fri | |
| 13 | 2026-10-26 | Mon | |
| 14 | 2026-10-27 | Tue | |
| 15 | 2026-10-28 | Wed | |
| 16 | 2026-10-29 | Thu | |
| 17 | 2026-10-30 | Fri | **Month-end decision close** (the only rebalance decision in the window) |
| 18 | 2026-11-02 | Mon | **Rebalance execution**, market-on-open t+1 |
| 19 | 2026-11-03 | Tue | |
| 20 | 2026-11-04 | Wed | |
| 21 | 2026-11-05 | Thu | Last session. Positions are marked and liquidated at the close (§11.6). |
| — | 2026-11-05 ≥ 16:15 ET | — | Earliest permitted Stage F acquisition (§3.9, `capture_policy`) |

The window therefore contains **two portfolio allocations** (the initial one and the 2026-11-02 rebalance) and **one rebalance transition**.

---

## 3. Invariants (nothing below may change)

All values are as recorded in DAY-22 §4; this draft does not restate them from memory.

| Item | Frozen value |
|---|---|
| Strategy | V2-MOM, cross-sectional momentum 12-1, long-only, top 5, equal weight 20% |
| Strategy-config SHA-256 | `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` |
| Engine | `backtest/v2/*`, unchanged |
| Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (freeze commit `ba3cefe…`) |
| Universe | `FROZEN_DAY_UNIVERSE` (25 US equities, listed in DAY-22 §4) |
| Benchmarks | B1 = equal-weight 25-stock buy-and-hold (primary comparison); B2 = SPY buy-and-hold (reference) |
| Capital | E_0 = 100,000; start flat; liquidate at the last close (§11.6) |
| Execution | Market-on-open t+1 at the raw (Series A) open; sells first; buy scaling λ (DAY-22 §4) |
| Costs | Linear per-side friction: 0 / **5 (primary)** / 10 bps |
| Calendar | `exchange_calendars` 4.13.2, XNYS, America/New_York |
| Data | Stage F per §3.9: raw bars, `all` bars and corporate-action events for the 25 symbols + SPY, 2025-01-02 → 2026-11-05, from the frozen providers only |

---

## 4. Recording procedure: blind, one-pass

1. **Before session 21 ends, nothing is observed.** No forward bars, quotes, signals, positions or P&L are acquired, computed or viewed. No dashboards, trackers or notebooks (DAY-22 §3.2 is unchanged).
2. **After 2026-11-05 16:15 ET**, in one separately authorised step:
   - a. Acquire Stage F once, write-once, under §3.9.
   - b. Run the §3.8 structural checks and the 2% review **before** any simulation.
   - c. Run the frozen engine once for V2-MOM, B1 and B2 at 0/5/10 bps, then a second identical run for determinism (§13.A.3).
3. **What is recorded** (write-once, with a §17 reproducibility block and result-file SHA-256s):
   - **Decision log:** for the 2026-10-07 formation and the 2026-10-30 decision, the momentum score and rank of every eligible symbol, the selected top 5, and the target weights.
   - **Fill log:** every fill (date, symbol, side, shares, raw open price, cost, λ).
   - **Daily close-marked equity** for V2-MOM, B1 and B2; corporate actions applied; final liquidation.
   - **Metrics** (§5) and the outcome status (§8).
4. **Proposed experiment ID:** `V2-MOM-F021-OBS`; benchmarks `V2-B1-forward21`, `V2-B2-forward21` (final IDs are OD-3). The run is entered in `artifacts/v2-experiment-registry.json` under §14 "Recording".

---

## 5. Predeclared comparison and metrics

There are no thresholds and no pass/fail rule. Every value is descriptive.

| Metric | Definition | Role |
|---|---|---|
| **Total return @5 bps** | E_T / E_0 − 1, not annualised | **Headline** |
| Active total return vs B1 @5 bps | V2-MOM total return − B1 total return (same sessions, same engine, same costs) | Headline comparison |
| Active total return vs B2 @5 bps | V2-MOM total return − B2 total return | Reference |
| Same three values @0 and @10 bps | as above | Cost sensitivity (§16.1) |
| Cost drag | gross − net total return | §16.4 |
| Max drawdown | peak-to-trough of close-marked equity | §16.6 |
| Turnover, executions, λ (mean/min) | §12 | §16.4 |
| Concentration | top-2 share of Σ\|P&L contribution\|; weight HHI; symbol breadth | §16.3 |
| Exposure | mean/min/max of Σ positions / E | §16.5 |
| Tracking error and information ratio vs B1 | §12 | Reported; flagged as computed from 21 daily returns |
| Net CAGR @0/5/10 bps | (E_T / E_0)^(252/21) − 1, i.e. the 12th power | Reported for §12 completeness only, labelled **"annualised from 21 sessions — not interpretable"** |
| Sharpe, Sortino, Calmar, volatility | §12 | Reported, labelled "21 daily returns" |
| Calendar subperiods | Oct 2026 and Nov 2026, both labelled **partial** | §16.2 |
| HAC t-statistic / Holm p-value | §12, §14 | `undefined (n = 21 daily returns; HAC lag 5 not meaningful)` — not computed |
| Episode statistics | §12 | Reported if defined, otherwise `undefined (reason)` |

---

## 6. Failure and exception rules (decided before any data)

| Event | Rule |
|---|---|
| Missing bar (session in calendar, no bar) | Listed, **never imputed** (§3.8), and handled by the existing §3.3/§8.6 rules. If any symbol misses more than 2% of the window's sessions (one session = 4.8% of 21), a **BLOCKING data review** happens before the run. The review is decided on data, never on results. |
| Structural HARD FAIL (§3.8) | The run does not start; status `FORWARD-OBSERVATION-INVALID (data-incomplete)` unless a §3.9 re-acquisition fixes it before any simulation. |
| Unscheduled market closure | The window runs until 21 **completed** XNYS sessions, as DAY-24 Spec 13 proposed. The end date and earliest Stage F time move accordingly; nothing else changes. |
| Scheduled calendar change after adoption | The adopted 21-session count governs; the session list is re-derived with the pinned `exchange_calendars` 4.13.2 and recorded. |
| Execution not at the raw open, wrong timing, or a non-raw mark | §13.A.6 methodological violation → `FORWARD-OBSERVATION-INVALID (methodological)` |
| Non-determinism between the two runs | §13.A.3 → `FORWARD-OBSERVATION-INVALID (methodological)` |
| Technical crash (code or environment, same frozen config) | Technical re-run per §14; both runs kept and reported |
| Corporate-action mismatch / unsupported type | BLOCKING data review (§3.8, §3.4) before the run |
| Any forward data, signal or P&L seen before 2026-11-05 16:15 ET | `FORWARD-OBSERVATION-INVALID (protocol-breach)`; recorded, never hidden |
| Any change to config, universe, engine, costs, benchmarks or this document after adoption | `FORWARD-OBSERVATION-INVALID (protocol-breach)`; any change is a new amendment (§10) |
| Observation not run, or authorisation withdrawn | `FORWARD-OBSERVATION-ABANDONED` (recorded with reason) |

---

## 7. Benchmark comparison rule

V2-MOM is compared with B1 and B2 over **identical sessions**, run by the **same engine**, with each benchmark charged the same per-side cost on its own trades (§13.B.2 wording). Comparisons use unrounded float64. The difference is **reported, not judged**: no sign, margin or threshold carries any consequence.

---

## 8. Outcome statuses (non-gating)

| Status | Meaning |
|---|---|
| `FORWARD-OBSERVED (complete)` | All §6 checks passed, two runs are identical, and every §5 item is present (value or `undefined (reason)`). Says nothing about whether the result was good or bad. |
| `FORWARD-OBSERVATION-INVALID (methodological \| data-incomplete \| protocol-breach)` | The observation cannot be used. Recorded with the reason; never re-run to obtain a different result. |
| `FORWARD-OBSERVATION-ABANDONED` | Not executed (with reason). |

None of these statuses is, implies, or substitutes for `FORWARD-PASSED`, `FORWARD-FAILED`, or "validated under v2" (§15.11). V2-MOM's governance status (DAY-22 §2) is unchanged by any outcome.

---

## 9. What this observation does NOT establish (explicit)

1. **A one-month result does not demonstrate a long-term edge.** The window contains one rebalance and 21 daily returns. Even the 856-session historical holdout did not reach statistical significance against B1 (HAC p = 0.166, DAY-22 §1.10). A 21-session result, positive or negative, does not prove or disprove the strategy.
2. **No automatic authorisation of real-money or live trading.** No outcome, including `FORWARD-OBSERVED (complete)` with a positive active return, authorises paper-to-live promotion, capital allocation or order routing. Any such step needs its own separate, explicit decision.
3. **No criterion here is derived from historical or diagnostic results.** DAY-25 and DAY-25B results were read only to confirm their stated scope. They were not used to choose the window, the metrics or any rule.
4. **The protocol owner cannot tune anything on the basis of this observation.** Under §14, any later change to the strategy is a new, DERIVED experiment that can never be confirmed on these 21 sessions.

---

## 10. Anti-mutation procedure (fixing criteria before results)

1. **Adoption window.** Adoption is valid only if the adoption commit is created **before 2026-11-05 16:15 ET** and **before any Stage F data exists** (DAY-23 §8.2 condition 1).
2. **Content pinning.** The adoption commit records the SHA-256 of the adopted `.md` and `.json` (CRLF normalised to LF, as in DAY-25B). The observation run refuses to start if either hash differs.
3. **Immutability.** After adoption, this document is never edited. Any change is a new amendment with a new ID. If made after any forward data exists, it is labelled **DERIVED FROM PRIOR OBSERVATION** and never applies to this window.
4. **Separate authorisations.** Adoption authorises nothing to run. Stage F acquisition and the observation run each need their own explicit authorisation reference, recorded in the run artifacts.
5. **Write-once outputs.** Outputs go to a fixed directory and are never overwritten (as in DAY-25B and §3.9). Invalid or abandoned runs are kept.

---

## 11. Open decisions (must be resolved before adoption)

| ID | Decision | Options | Note |
|---|---|---|---|
| **OD-1 (critical)** | **Interaction with the gating forward window.** If the 21-session observation acquires Stage F after 2026-11-05, forward data are inspected before any longer gating window that starts on 2026-10-08 has ended (63 sessions: 2027-01-07; 252 sessions: 2027-10-08). §15.6 and DAY-22 §3.2 forbid that. | (a) The observation **replaces** the forward step: no `FORWARD-PASSED` is possible under v2. (b) The gating window **restarts after** the observation (e.g. first session after 2026-11-05), with an explicitly amended start rule. (c) The observation result is **sealed** (acquired and run, but not opened) until the gating window ends. | Without a decision, adopting this draft would break the blindness of the effective 252-session window. |
| OD-2 | Fate of DAY-24 (63 sessions) | Withdrawn / superseded / kept as the gating window under OD-1 (b) or (c) | DAY-24 is not edited by this draft. |
| OD-3 | Final experiment ID and protocol version number | e.g. `V2-MOM-F021-OBS`; version assigned at adoption | DAY-24 reserved "v2.0.5". |
| OD-4 | Adoption deadline | Any time before 2026-11-05 16:15 ET | After that, this design cannot be adopted for this window. |
| OD-5 | Accept that the window started (2026-10-08) before adoption | Accept (no forward data viewed, per the repository's documented record) / move the start to the first session after adoption (window ends 21 sessions later; the start rule is amended) | Affects initial construction (session 1). |

---

## 12. Integrity affirmation (drafting task)

- No forward-period (≥ 2026-10-08) or Excluded-period (2026-06-03 → 2026-10-07) market data was acquired, read or inspected.
- No market-data provider was contacted; no backtest, simulation or diagnostic was run.
- Session dates come from the `exchange_calendars` 4.13.2 XNYS schedule only.
- No code, configuration, frozen protocol file, predeclaration, preflight record or existing artifact was modified; DAY-24 is unchanged.
- Nothing was committed.
