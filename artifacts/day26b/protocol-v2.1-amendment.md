# DAY-26B — Protocol v2.1 Amendment: 63-Session Forward Window (21-Session Diagnostic + 42-Session Blind Gate)

> **STATUS: ADOPTED — 2026-10-10T12:52:51Z by Alixujaev (protocol owner).**
> Decision record: `artifacts/day26b/protocol-v2.1-adoption.json` (with `.md`), which pins the LF-normalised SHA-256 of this file and its JSON twin. The adoption takes effect from the commit that contains that record. It was not adopted earlier: from 2026-10-08 until then, the 252-session rules of DAY-16 §3.6 / §3.9 / §15 and the DAY-22 §3 lockdown governed, and no forward data was acquired, computed or inspected under them. The code refuses all forward access until the record and this amendment are committed unchanged (`backtest/v2/forward.py`, P1). This document was drafted as a proposal on the same day; its text is unchanged except for this banner, the adoption row below, C23, and §17–§18. The machine-readable twin of this document is `artifacts/day26b/protocol-v2.1-amendment.json`; every date, count, ID, label and metric below matches it. Calendar values come from `scripts/day26b_forward_calendar.py` and are checked by `tests/test_day26b_forward_calendar.py`.

| Field | Value |
|---|---|
| Task | DAY-26B (drafted 2026-10-10, starting HEAD `8ef01f4`) |
| Adopted | **2026-10-10T12:52:51Z**, Alixujaev (protocol owner); effective from the commit containing `artifacts/day26b/protocol-v2.1-adoption.json` |
| Protocol version | **2.1** → full version `2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 + 2.1`. `2.0.5` stays reserved by DAY-24 and is not used. |
| Forward window | **63 XNYS sessions, 2026-10-08 → 2027-01-07** |
| Diagnostic | `fwd-diag`: sessions **1–21**, 2026-10-08 → 2026-11-05. Descriptive only, never gating. |
| Blind gate | `fwd-gate`: sessions **22–63** (42 sessions), 2026-11-06 → 2027-01-07. §13 gate, evaluated once. |
| Experiments | `V2-MOM-F002-DIAG` (diagnostic); `V2-MOM-F002` (gate). Benchmarks `V2-B1-fwd-diag`, `V2-B2-fwd-diag`, `V2-B1-fwd-gate`, `V2-B2-fwd-gate` |
| Gate labels | `FORWARD42-PASSED`, `FORWARD42-FAILED (economic \| methodological \| incomplete)`, `FORWARD42-INVALID (protocol-breach)`, `FORWARD42-ABANDONED` |
| Earliest diagnostic evaluation | **2026-11-05 16:15 America/New_York (EST, UTC−05:00) = 2026-11-05 21:15 UTC** |
| Earliest final gate evaluation | **2027-01-07 16:15 America/New_York (EST, UTC−05:00) = 2027-01-07 21:15 UTC** |
| Strategy | V2-MOM, unchanged. Strategy-config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` |

---

## 1. Amendment statuses

| Status | Meaning |
|---|---|
| `PROPOSED — NOT EFFECTIVE` | This draft. The DAY-16 §3.6 / DAY-22 §3 252-session rules remain binding. |
| `ADOPTED` | A protocol-owner sign-off commit records the LF-normalised SHA-256 of this `.md` and `.json`. |
| `LAPSED` | Not adopted before the first Stage F acquisition, or by 2027-01-07 16:15 America/New_York. The 252-session rules then stay in force unchanged. |

## 2. Sources and lineage

Clauses are quoted from the committed documents.

| Document | Status | Forward rule |
|---|---|---|
| `artifacts/day16/research-protocol-v2.md` | frozen, effective | §3.6: Forward OOS = "the **252** XNYS sessions starting at the first session strictly after the freeze-commit date" |
| `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md` | signed off, effective | §3.1: 2026-10-08 → 2027-10-08, exactly 252 sessions. §3.2: blind rules. |
| `artifacts/day23/day23-forward-oos-252-session-audit.md` | audit, no rule change | "PROTOCOL AMENDMENT MAY BE WARRANTED"; §8.2 lists five conditions for a shorter window to stay blind. |
| `artifacts/day24/day24-forward-oos-duration-amendment-design.md` | PROPOSED — NOT YET EFFECTIVE | 63 sessions, gated on all 63 (proposed v2.0.5). **On adoption of 2.1: superseded**; the file is kept unedited as a historical record. |
| `artifacts/day26a/day26a-forward-21-session-observation-amendment-draft.md` | PROPOSED — NOT EFFECTIVE (uncommitted draft) | 21-session non-gating observation; OD-1…OD-5 open. **On adoption of 2.1: superseded**; the file is kept unedited as a historical record. |

## 3. Design

1. **Total forward window: 63 sessions**, starting at the original forward start (2026-10-08). No further 63-session window follows the diagnostic.
2. **Sessions 1–21 (`fwd-diag`)** are a descriptive diagnostic. Its data may be acquired and inspected only after adoption **and** after the end of session 21. Its results can never change the strategy, any threshold, the protocol, or the schedule.
3. **Sessions 22–63 (`fwd-gate`)** are 42 blind sessions. Nothing from them is acquired, computed, inspected, monitored or visualized before the end of session 63.
4. The gate decision is made **once**, after session 63, with the unchanged §13 criteria applied to the 42 `fwd-gate` sessions only. The two segments are **never pooled**.
5. **Continuation is unconditional.** Only the predeclared invalidation and abandonment rules (§10) can stop the schedule.

## 4. Calendar (`exchange_calendars` 4.13.2, XNYS)

### 4.1 `fwd-diag`: sessions 1–21

| # | Session | # | Session | # | Session |
|---|---|---|---|---|---|
| 1 | 2026-10-08 | 8 | 2026-10-19 | 15 | 2026-10-28 |
| 2 | 2026-10-09 | 9 | 2026-10-20 | 16 | 2026-10-29 |
| 3 | 2026-10-12 | 10 | 2026-10-21 | 17 | 2026-10-30 |
| 4 | 2026-10-13 | 11 | 2026-10-22 | 18 | 2026-11-02 |
| 5 | 2026-10-14 | 12 | 2026-10-23 | 19 | 2026-11-03 |
| 6 | 2026-10-15 | 13 | 2026-10-26 | 20 | 2026-11-04 |
| 7 | 2026-10-16 | 14 | 2026-10-27 | 21 | 2026-11-05 |

- Initial decision at the 2026-10-07 close (§8.14: the session before the segment). Initial construction at the 2026-10-08 open.
- One month-end decision at the 2026-10-30 close, executed at the 2026-11-02 open.
- Liquidation at the 2026-11-05 close.
- Stage F-D lookback: 2025-01-02 → 2026-11-05. That gives 442 sessions before the segment.
- Earliest Stage F-D capture: **2026-11-05 16:15 America/New_York = 2026-11-05 21:15 UTC**.

### 4.2 `fwd-gate`: sessions 22–63 (42 sessions)

| # | Session | # | Session | # | Session |
|---|---|---|---|---|---|
| 22 | 2026-11-06 | 36 | 2026-11-27 (early close 13:00) | 50 | 2026-12-17 |
| 23 | 2026-11-09 | 37 | 2026-11-30 | 51 | 2026-12-18 |
| 24 | 2026-11-10 | 38 | 2026-12-01 | 52 | 2026-12-21 |
| 25 | 2026-11-11 | 39 | 2026-12-02 | 53 | 2026-12-22 |
| 26 | 2026-11-12 | 40 | 2026-12-03 | 54 | 2026-12-23 |
| 27 | 2026-11-13 | 41 | 2026-12-04 | 55 | 2026-12-24 (early close 13:00) |
| 28 | 2026-11-16 | 42 | 2026-12-07 | 56 | 2026-12-28 |
| 29 | 2026-11-17 | 43 | 2026-12-08 | 57 | 2026-12-29 |
| 30 | 2026-11-18 | 44 | 2026-12-09 | 58 | 2026-12-30 |
| 31 | 2026-11-19 | 45 | 2026-12-10 | 59 | 2026-12-31 |
| 32 | 2026-11-20 | 46 | 2026-12-11 | 60 | 2027-01-04 |
| 33 | 2026-11-23 | 47 | 2026-12-14 | 61 | 2027-01-05 |
| 34 | 2026-11-24 | 48 | 2026-12-15 | 62 | 2027-01-06 |
| 35 | 2026-11-25 | 49 | 2026-12-16 | 63 | 2027-01-07 |

- Initial decision at the 2026-11-05 close (§8.14). Initial construction at the 2026-11-06 open.
- Month-end decisions at the 2026-11-30 and 2026-12-31 closes, executed at the 2026-12-01 and 2027-01-04 opens.
- Liquidation at the 2027-01-07 close.
- Stage F-G lookback: 2025-01-02 → 2027-01-07. That gives 463 sessions before the segment.
- Earliest Stage F-G capture: **2027-01-07 16:15 America/New_York = 2027-01-07 21:15 UTC**.
- Weekday holidays in the window: 2026-11-26, 2026-12-25, 2027-01-01. Early closes: 2026-11-27 and 2026-12-24, both at 13:00.

## 5. Invariants (unchanged)

| Item | Value |
|---|---|
| Strategy | V2-MOM, cross-sectional momentum 12-1, long-only, top 5, equal weight 20% |
| Strategy-config SHA-256 | `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` |
| Universe | `FROZEN_DAY_UNIVERSE` (25 US equities, DAY-22 §4) |
| Benchmarks | B1 = equal-weight 25-stock buy-and-hold (gate reference). B2 = SPY buy-and-hold (reference, not gated). |
| Capital and accounting | E_0 = 100,000. Each segment starts 100% cash and is liquidated at its last close (§11.6, §3.7). |
| Execution | Market-on-open t+1 at the raw Series A open; sells first; buy scaling λ (§8, DAY-22 §4) |
| Costs | 0 / **5 (primary)** / 10 bps per side |
| Calendar | `exchange_calendars` 4.13.2 XNYS, America/New_York |
| Data | Frozen providers only: raw bars, `all` bars and corporate-action events for the 25 symbols + SPY |
| Gate thresholds | §13.B unchanged: net CAGR @5 bps ≥ 0 **and** ≥ B1 net CAGR @5 bps; margin 0; unrounded float64 |

## 6. Permissions: acquire, compute, inspect

| Period | Data scope | Acquire | Compute | Inspect |
|---|---|---|---|---|
| now → adoption | everything forward | no (252-session rules) | no | no |
| adoption → 2026-11-05 16:15 America/New_York | everything forward | no | no | no |
| after 2026-11-05 16:15 America/New_York (adopted, preflight passed, authorised) | data dated ≤ 2026-11-05 only | once (Stage F-D) | `fwd-diag` run ×2 | yes |
| 2026-11-06 → 2027-01-07 16:15 America/New_York | any data dated ≥ 2026-11-06 | no | no | no (also no monitoring or visualization) |
| after 2027-01-07 16:15 America/New_York (preflight passed, authorised) | data dated ≤ 2027-01-07 | once (Stage F-G) | `fwd-gate` run ×2 | yes |
| always | — | Operational feeds, if any, isolate raw ingestion and never compute or expose forward strategy performance (DAY-22 §3.2.2) | | |

## 7. Diagnostic report (`fwd-diag`, `V2-MOM-F002-DIAG`)

The headline cost case is 5 bps; 0 and 10 bps are supporting cases. **There are no thresholds and no consequences**: the report cannot change, extend, cancel or restart the `fwd-gate` schedule.

1. Total return, not annualised (V2-MOM, B1, B2).
2. Active total return vs B1 and vs B2.
3. Maximum drawdown (close-marked equity).
4. Turnover, executions, mean/min λ.
5. Transaction-cost impact: total costs and cost drag (gross minus net total return).
6. Concentration: top-2 share of Σ|P&L contribution|, weight HHI, symbol breadth.
7. Exposure: mean/min/max of Σ positions / equity.
8. Data completeness: missing sessions per symbol, §3.8 structural checks, corporate-action review outcome.
9. Protocol compliance: fill-source test, execution-timing test, determinism (two runs), config SHA, amendment SHA, §17 block.

CAGR, Sharpe, Sortino, Calmar and statistical tests are **not** part of the diagnostic report. Any engine file that contains CAGR carries the label "annualised from 21 sessions — not meaningful evidence".

## 8. Blind gate (`fwd-gate`, `V2-MOM-F002`)

| Part | Rule |
|---|---|
| A — methodological | §13.A items 1–7, unchanged |
| B — economic | §13.B unchanged, on the 42 `fwd-gate` sessions: net CAGR @5 bps ≥ 0 and ≥ B1 net CAGR @5 bps; margin 0; unrounded float64; CAGR = (E_T/E_0)^(252/42) − 1. Because N and E_0 are identical for V2-MOM and B1, both inequalities give the same decision as comparing net total returns, so **no threshold depends on 252**. |
| C — completeness | §16 items 1–7 at 0/5/10 bps, each a value or `undefined (reason)`. Calendar-year subperiods: 2026 (partial, 2026-11-06 → 2026-12-31, 38 sessions) and 2027 (partial, 2027-01-04 → 2027-01-07, 4 sessions). |
| Statistical diagnostic | HAC (Newey–West, lag 5) t-statistic of daily active return vs B1 on 42 returns. Holm adjustment with **m = 1**: V2-MOM is the only family in the forward stage, and DAY-21 P2 is the precedent for predeclaring m. Diagnostic only. |
| Excluded from the sample | All `fwd-diag` sessions, returns and metrics. Never pooled. |
| Evaluation | Once, after 2027-01-07 16:15 America/New_York, after Stage F-G and the §3.8 review |

Outcome mapping:

| Condition | Status |
|---|---|
| Any §13.A item fails | `FORWARD42-FAILED (methodological)` |
| §13.A passes, §13.B fails | `FORWARD42-FAILED (economic)` |
| §13.A and §13.B pass, a §16 item is missing | `FORWARD42-FAILED (incomplete)` |
| §13.A, §13.B and §13.C pass | `FORWARD42-PASSED` |

**Meaning of `FORWARD42-PASSED`:** the strategy survived a 42-session blind forward gate under protocol 2.1. This is **not** equivalent to the one-year test of §15.11, and it is **not** "validated under v2". `FORWARD-PASSED`, `FORWARD-FAILED` and "validated under v2" are not available under 2.1.

## 9. Statuses

| Segment | Status | Meaning |
|---|---|---|
| fwd-diag | `FWD-DIAG-COMPLETE` | All checks passed, two identical runs, every report item present. Says nothing about whether performance was good or bad. |
| fwd-diag | `FWD-DIAG-INVALID (methodological \| data-incomplete \| protocol-breach)` | The diagnostic is unusable. Recorded with the reason; never re-run to obtain a different result. |
| fwd-diag | `FWD-DIAG-ABANDONED` | Not executed; recorded with the reason. |
| fwd-gate | `FORWARD42-PASSED` | See §8 |
| fwd-gate | `FORWARD42-FAILED (economic \| methodological \| incomplete)` | §13 vocabulary applied to the 42-session gate |
| fwd-gate | `FORWARD42-INVALID (protocol-breach)` | `fwd-gate` data, returns or metrics were acquired, computed or inspected before 2027-01-07 16:15 America/New_York, or a frozen item changed after adoption |
| fwd-gate | `FORWARD42-ABANDONED` | Only for a predeclared abandonment reason (§10) |

## 10. Invalidation and abandonment rules

| Event | Rule |
|---|---|
| Missing session for a symbol | Listed, never imputed (§3.8). If any symbol misses more than 2% of a segment's sessions (1 session = 4.8% of `fwd-diag`, 2.4% of `fwd-gate`), a BLOCKING data review happens before the run, decided on data only. |
| §3.8 structural HARD FAIL or unresolved BLOCKING review | No run until resolved by a §3.9 write-once re-acquisition (originals kept). If unresolved: `FWD-DIAG-INVALID (data-incomplete)` / `FORWARD42-FAILED (methodological)` per §13.A.2 and A.7. |
| Corporate-action mismatch or unsupported type | BLOCKING data review before the run (§3.4, §3.8) |
| Unscheduled market closure | The window runs to the 63rd completed XNYS session. The split stays at sessions 1–21 / 22–63 by count. Dates are re-derived and recorded before any acquisition; nothing else changes. |
| Fill not at the raw open, wrong timing, non-raw mark | §13.A.6 → methodological |
| The two runs differ | §13.A.3 → methodological |
| Technical crash with the identical frozen configuration | Technical re-run per §14; both runs kept and reported |
| `fwd-gate` data or metrics seen before 2027-01-07 16:15 America/New_York | `FORWARD42-INVALID (protocol-breach)`; recorded, never hidden |
| `fwd-diag` data seen before adoption or before 2026-11-05 16:15 America/New_York | `FWD-DIAG-INVALID (protocol-breach)`. If the exposure includes data dated ≥ 2026-11-06, also `FORWARD42-INVALID (protocol-breach)`. |
| `fwd-diag` invalid or abandoned for its own reasons | `fwd-gate` continues unchanged |
| Abandonment | `fwd-gate` may be abandoned only if (i) the amendment lapses, (ii) the protocol owner withdraws it before Stage F-D is acquired, or (iii) the frozen provider cannot supply the required data and the §3.8 review records this as unresolvable. **Never** because of a diagnostic result or a market observation (DAY-22 §3.2.4, DAY-23 §8.1.1). |

## 11. Conflict resolution (old clause → amended rule)

| ID | Clause | Old | Amended |
|---|---|---|---|
| C1 | DAY-16 §3.6 segment table | Forward OOS = the 252 XNYS sessions starting at the first session strictly after the freeze-commit date | 63 sessions from that first session (2026-10-08 → 2027-01-07): `fwd-diag` 1–21, `fwd-gate` 22–63 |
| C2 | DAY-16 §3.6 rationale 5 (length) | "its length is fixed now and is never extended or shortened after looking" | Shortened once, by this amendment, before any forward data exists (DAY-23 §8.2 condition 1); fixed thereafter |
| C3 | DAY-16 §3.6 rationale 5 (data) | "No data dated after the freeze commit may be acquired or inspected before the forward period has ended" | Data dated ≤ 2026-11-05: after 2026-11-05 16:15 America/New_York. Data dated ≥ 2026-11-06: after 2027-01-07 16:15 America/New_York. |
| C4 | DAY-16 §3.9 Stage F | Acquired only after the forward period has ended (2025-01-02 → last forward session); no interim forward data | Two write-once snapshots, each acquired once: F-D (2025-01-02 → 2026-11-05) and F-G (2025-01-02 → 2027-01-07). Overlap control H∩F-D, H∩F-G and F-D∩F-G, cell by cell. |
| C5 | DAY-16 §3.7 / §11.6 | Each segment starts flat and is liquidated at its last close | Unchanged; applied to `fwd-diag` and `fwd-gate` separately |
| C6 | DAY-16 §13 (gate re-applied on Forward) | "The same gate is re-applied, unchanged, on the Holdout and Forward segments" | Applied unchanged to `fwd-gate` only; `fwd-diag` is not gated |
| C7 | DAY-16 §13 outcome vocabulary / §15 diagram | FORWARD-PASSED / FORWARD-FAILED | `FORWARD42-PASSED` / `FORWARD42-FAILED (…)` / `FORWARD42-INVALID` / `FORWARD42-ABANDONED` |
| C8 | DAY-16 §14 New experiment | Any change to a … segment → new ID, new protocol version, DERIVED FROM PRIOR OBSERVATION if proposed after any v2 result | Protocol 2.1; IDs `V2-MOM-F002-DIAG` / `V2-MOM-F002`; `V2-MOM-F002` labelled **DERIVED FROM PRIOR OBSERVATION (segment change only; strategy unchanged)** |
| C9 | DAY-16 §14 / §16.7 Holm across the three families | Holm-adjusted p-values across the three families, per segment | m = 1 in `fwd-gate` (only V2-MOM is in the forward stage); predeclared here (DAY-21 P2 precedent) |
| C10 | DAY-16 §15.6 | Forward data acquired once, after the forward period ends; no interim forward performance computed or inspected | Once per segment, after that segment ends (C3, C4); no interim computation or inspection inside `fwd-gate` |
| C11 | DAY-16 §15.11 / §14 normative | FORWARD-PASSED = "survived one year of genuinely unseen data — the only status labelled 'validated under v2'" | Not available for this 42-session gate. `FORWARD42-PASSED` is defined in §8 and is never called "validated". |
| C12 | DAY-16 §20 Q11 | Forward OOS = 1 year (low power) | `fwd-gate` = 42 sessions: weaker long-term evidence than the original design (§12) |
| C13 | DAY-22 §3.1 | 2026-10-08 → 2027-10-08, exactly 252 XNYS sessions | 2026-10-08 → 2027-01-07, 63 sessions (21 + 42) |
| C14 | DAY-22 §3.2.1 configuration lockdown | Config SHA `62827d70…` locked; zero changes | Unchanged |
| C15 | DAY-22 §3.2.2 no interim peeking | Prohibited to compute/inspect/monitor/visualize interim forward performance | Binding for all `fwd-gate` data until 2027-01-07 16:15 America/New_York. For `fwd-diag` data, lifted only after adoption and 2026-11-05 16:15 America/New_York. Operational-feed clause unchanged. |
| C16 | DAY-22 §3.2.3 no forward data acquisition | Until the 252-session waiting period has concluded | Per segment (C3) |
| C17 | DAY-22 §3.2.4 no forward-guided mutations | Observations during the blind period shall not be used to propose protocol changes | Unchanged and extended: `fwd-diag` results can never change the strategy, thresholds, protocol or schedule |
| C18 | DAY-22 §6 exact next task | Wait for completion of the frozen 252-session forward OOS period | Execution sequence S0–S12 (§14) |
| C19 | DAY-23 §8.1.1 adaptive early stopping | "Halting the evaluation prematurely because interim performance happens to be positive" | `fwd-gate` continues unconditionally; abandonment only for predeclared reasons (§10) |
| C20 | DAY-23 §8.2 conditions 1–5 | Before any forward data; fixed N*; frozen SHA; one-shot; no interim inspection | 1: adoption before any Stage F. 2: N fixed (63 = 21 + 42). 3: SHA frozen. 4: one-shot per segment. 5: holds inside `fwd-gate`. **Deviation:** for the 63-session window as a whole, condition 5 is relaxed by the `fwd-diag` inspection; this is mitigated by excluding `fwd-diag` from the gate sample (approval A-8). |
| C21 | DAY-24 Specs 1–15 (63 sessions gated on all 63, v2.0.5, FORWARD-PASSED) | Proposed, not adopted | Superseded on adoption: total length 63 kept; gate restricted to sessions 22–63; v2.0.5 and FORWARD-PASSED not used |
| C22 | DAY-26A draft (21-session observation, OD-1…OD-5) | Proposed, not adopted | Superseded on adoption. OD-1 resolved as a gate after the observation, inside the same 63 sessions. OD-2: DAY-24 superseded. OD-3: IDs and version above. OD-4: adoption deadline (A-5). OD-5: start 2026-10-08 accepted (A-7). |
| C23 | Implementation: `backtest/v2/run.py` (calendar end 2026-12-31; `SEGMENTS` research/holdout only); no Stage F loader or acquisition | Cannot run forward segments | Implemented in DAY-26B (§18), with byte-identical research/holdout regression (DAY-21 / DAY-22 §1.7 precedent). Strategy config SHA unaffected (approval A-6). |

## 12. Evidence and trading disclaimers

1. **Shortening the forward window from 252 to 63 sessions, with only 42 gated, weakens the long-term evidence.** A 42-session result does not provide evidence equivalent to a one-year test.
2. **No outcome, including `FORWARD42-PASSED`, authorises real-money or live trading.** That requires a separate, explicit decision.
3. A 21-session diagnostic is descriptive; its CAGR is not meaningful evidence.
4. Even the 856-session historical holdout did not reach statistical significance vs B1 (HAC p = 0.166, DAY-22 §1.10).

## 13. Preflight checklist (must pass before any forward data access)

| ID | Check |
|---|---|
| P1 | The adoption commit exists, and the LF-normalised SHA-256 of this `.md` and `.json` match the values pinned in it |
| P2 | Strategy-config SHA-256 == `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` |
| P3 | DAY-16 protocol files and the DAY-22 lockdown are unchanged since adoption (git diff empty) |
| P4 | Forward-capable code reproduces the DAY-19 research and DAY-21 holdout result files byte-identically |
| P5 | `python -m scripts.day26b_forward_calendar` output equals the calendar block of the JSON; `exchange_calendars` == 4.13.2 |
| P6 | Environment fingerprint recorded (reference distributions SHA-256 `7b47231b…`). A different fingerprint is reported and never relaxes any check. |
| P7 | No Stage F snapshot for the segment exists yet, and there are no forward bars in any project cache (directory listing only) |
| P8 | Current time ≥ the segment's earliest Stage F capture time (America/New_York) |
| P9 | An explicit authorisation reference for the step is recorded in the run artifacts |
| P10 | The Stage F request is bounded to the segment's last session; no bar or event dated later is persisted or displayed (v2.0.1 C1 precedent) |
| P11 | Simulation runs with network sockets refused; acquisition is the only networked step |
| P12 | Git tree clean except untracked run outputs (§17) |
| P13 | `fwd-gate` only: the `fwd-diag` artifacts and the F-D snapshot exist write-once and unchanged, and no `fwd-gate` artifact or interim output exists |

## 14. Execution sequence (approval → final evaluation)

| Step | When | Action |
|---|---|---|
| S0 | now | Draft review; no forward access |
| S1 | Before any Stage F (to keep the diagnostic on time: before 2026-11-05 16:15 America/New_York) | Protocol-owner sign-off commit adopting 2.1; SHA-256 of `.md`/`.json` pinned; DAY-24 and DAY-26A recorded as superseded |
| S2 | After S1, before 2026-11-05 16:15 America/New_York | Separately authorised implementation: `fwd-diag`/`fwd-gate` segments, Stage F loader and acquisition with bounded requests, calendar bound; regression P4; commit |
| S3 | After 2026-11-05 16:15 America/New_York | Preflight P1–P12 for `fwd-diag` |
| S4 | After S3, separately authorised | Stage F-D acquisition once (2025-01-02 → 2026-11-05), write-once; overlap control vs Stage H; §3.8 review |
| S5 | After S4 | `fwd-diag` run (V2-MOM, B1, B2 at 0/5/10 bps) twice; diagnostic report; status `FWD-DIAG-*`; registry entry |
| S6 | 2026-11-06 → 2027-01-07 | `fwd-gate` blind period: nothing acquired, computed, inspected, monitored or visualized; continues regardless of S5 |
| S7 | After 2027-01-07 16:15 America/New_York | Preflight P1–P13 for `fwd-gate` |
| S8 | After S7, separately authorised | Stage F-G acquisition once (2025-01-02 → 2027-01-07), write-once; overlap control vs H and F-D; §3.8 review |
| S9 | After S8 | `fwd-gate` run twice; §13 A/B/C on the 42 sessions only |
| S10 | After S9 | Status `FORWARD42-*`; registry entry; report |
| S11 | After S10 | Protocol-owner review and sign-off of the forward result |
| S12 | After S11 | Any decision about real-money trading is a separate, explicit decision outside this protocol |

**Early-2027 conclusion:** possible. The final evaluation can start on 2027-01-07 after 16:15 America/New_York. Completion in January 2027 depends on no BLOCKING data review arising and on S2 being finished in time.

## 15. Decisions requiring explicit approval

| ID | Decision |
|---|---|
| A-1 | Adopt protocol version 2.1 (2.0.5 stays reserved by DAY-24) |
| A-2 | Gate labels `FORWARD42-*` and no "validated" label (the alternative, a 2.1-specific "validated" meaning, would need explicit wording) |
| A-3 | Label `V2-MOM-F002` DERIVED FROM PRIOR OBSERVATION under §14 (segment change only) |
| A-4 | Holm m = 1 for the `fwd-gate` statistical diagnostic |
| A-5 | Adoption deadline: before any Stage F; to keep the diagnostic on time, before 2026-11-05 16:15 America/New_York; LAPSED rule |
| A-6 | Authorise the separate implementation task S2 (forward segments, Stage F code, calendar bound) with regression proof |
| A-7 | Accept that the window started on 2026-10-08, before adoption (no forward data accessed) |
| A-8 | Accept the DAY-23 §8.2 condition-5 deviation for the window as a whole (`fwd-diag` inspected mid-window), mitigated by exclusion from the gate sample |
| A-9 | The closed list of abandonment reasons (§10) |

## 16. Integrity affirmation (drafting task)

- No forward-period (≥ 2026-10-08) or Excluded-period (2026-06-03 → 2026-10-07) market data was acquired, read or inspected. No market-data provider was contacted.
- No forward return, P&L, CAGR, drawdown or benchmark result was computed. No Stage F, backtest, simulation or strategy evaluation was run.
- No existing file was modified (frozen strategy, config, predeclarations, preflight record, DAY-24 and DAY-26A included). Nothing was committed.
- No evidence of prior forward access was found: `data/oos_cache/protocol_v2` contains only `stage_r`, `stage_h` and `evidence` (vault-restored on 2026-10-10); there is no `stage_f`.

## 17. Formal exceptions (recorded at adoption)

Adoption accepts approvals A-1 … A-9 (§15) as written. The following formal exceptions to earlier binding text are made by this amendment, prospectively, from its adoption commit:

| Exception | Earlier text | Basis |
|---|---|---|
| E1 | DAY-16 §3.6 / DAY-22 §3.1: forward OOS = 252 sessions, 2026-10-08 → 2027-10-08 | Replaced by 63 sessions (21 + 42), C1, C13. Adopted on 2026-10-10, before any forward data existed in the project (DAY-23 §8.2 condition 1). |
| E2 | DAY-16 §3.6 rationale 5: the length "is never extended or shortened after looking" | No forward data had been looked at; shortened once, C2. |
| E3 | DAY-16 §3.6 r5, §3.9, §15.6; DAY-22 §3.2.2–§3.2.3: one Stage F after the whole forward period, no interim inspection | Two per-segment Stage F snapshots and permissions, C3, C4, C10, C15, C16. Inside `fwd-gate` the original rules apply unchanged. |
| E4 | DAY-23 §8.2 condition 5 for the 63-session window as a whole | Relaxed by the `fwd-diag` inspection after session 21 (A-8); mitigated by permanent exclusion of `fwd-diag` from the gate sample and the unconditional schedule (C19, C20). |
| E5 | DAY-16 §15.11 / §14 normative: FORWARD-PASSED = one year, "validated under v2" | Not available; `FORWARD42-*` labels (A-2), C7, C11. |
| E6 | DAY-16 §14 / §16.7 Holm across three families | m = 1 (A-4), C9. |

The strategy, its configuration (SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`), the §13 thresholds, the benchmarks and the costs are not excepted and are unchanged. DAY-24 and DAY-26A are superseded as historical records; their files are not edited.

## 18. Implementation (DAY-26B, step S2)

| Path | Change |
|---|---|
| `backtest/v2/forward.py` (new) | Forward guards: `check_forward_access` = time gate (16:15 America/New_York on the segment's last session) + adoption gate (record ADOPTED, pinned SHA-256 match, all three files committed unchanged) + calendar split 21 + 42 = 63. `diagnostic_report` (§7). |
| `backtest/v2/run.py` | XNYS calendar bound 2027-12-31; `SEGMENTS` `fwd-diag` / `fwd-gate` (IDs §1 table, `inputs_before` 442 / 463); forward segments require `--authorization` and pass `check_forward_access` before any data is loaded; write-once output; `fwd-diag` is never gated; `fwd-gate` uses the unchanged §13 code with prefix `FORWARD42`; partial calendar-year labels. Research and holdout paths unchanged. |
| `backtest/v2/data.py` | `load_stage_f` (gated; validated READY snapshot; session index ends at the segment's last session). |
| `acquisition/v2/stage_f.py` (new) | Stage F capture and offline validation, gated before any client exists; acquired once per segment; request and persistence bounds per the adoption record. |
| `acquisition/v2/contract.py`, `acquisition/v2/sessions.py` | Stage F constants; `stage_f_sessions`. |
| `acquisition/v2/stage_h.py` | Keyword parameters with unchanged defaults (`derive`, `overlap_control`, `assert_no_leakage_h`) reused by Stage F. |
| `tests/test_day26b_forward.py` (new) | Synthetic/offline tests of the split, time and adoption gates, refusal before loading, sample separation, diagnostic report. |

## 19. Incident disclosure — appended 2026-10-10 (DAY-26C; §1–§18 and the banner are unchanged)

On 2026-10-10 between 12:56:23 and 12:59:51 UTC, after this amendment's adoption was recorded (12:52:51Z) and before it was committed, a DAY-26B verification run of the full pytest suite downloaded recent yfinance intraday data (54 files, 5m/15m, 27 symbols) into `data/cache/`. The same run then consumed the files in legacy day-trading tests and printed legacy trade counts. The files are believed to cover Excluded-period sessions and **forward sessions 1–2 (2026-10-08, 2026-10-09)**. No `fwd-gate` session existed. The values were not opened or viewed, and no V2-MOM forward metric was computed. Full record: `artifacts/day26c/day26c-forward-data-incident.md` / `.json`.

Consequences, decided at disclosure:

| Segment | Status |
|---|---|
| `fwd-diag` (sessions 1–21) | **`FWD-DIAG-INVALID (protocol-breach)`.** Final (§9, §10). No `fwd-diag` acquisition, validation, load or evaluation. S3–S5 (§14) are cancelled. |
| `fwd-gate` (sessions 22–63) | **PENDING.** Blind, not evaluated. Dates, thresholds and calendar unchanged. |

The adoption timestamp and every historical field above are preserved. The integrity statements in §16 were true when written; this section supersedes them from 12:56:23Z on. The adoption record re-pins the SHA-256 of this file after this disclosure and keeps the original pins as history.
