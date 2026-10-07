# Protocol v2.0.2 — Amendment (DAY-18A)

| Field | Value |
|---|---|
| Amendment version | **v2.0.2** |
| Type | **protocol_change** (changes a frozen rule of §3.4 and extends v2.0.1 C2) — `modified: true` |
| Status | **DRAFT — PENDING COMMIT** |
| Parent protocol | v2.0 R1, frozen at `ba3cefe54ccf2fe14c62f1c609f143d8a0904221` |
| Immediate clarification parent | v2.0.1, committed at `ed034b3e9500cc4d9b33625de7e1883f572cd5a4` |
| Stage R evidence | DAY-18 report, committed at `858547edbef943c9daedb09c2a623ac911779d8a` |
| Stage R implementation | `3fe0c92e18c70d35da73a5b4a799cfbb4c78bae4` |
| Stage R snapshot (read for evidence only, not modified) | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` |
| Drafted | 2026-10-07 |

**Precedence.** v2.0 R1 and v2.0.1 remain immutable documents. From the commit of this amendment, the four rules below replace or extend the cited text for all v2 acquisition/data processing. **This amendment does not declare Stage R usable**; the existing snapshot must be re-evaluated under v2.0.2 in a separate task.

**Decision provenance.** Items 1 and 3 were chosen by the protocol owner in DAY-18A (options: precision-interval rule / mark OPEN / fixed 1e-3; and identity B vs A). Items 2 and 4 follow from frozen formulas and the DAY-17 provider facts, as argued below.

## 0. Unchanged
Universe (25 symbols + SPY benchmark-only role); warmup, research, holdout, excluded and forward-OOS dates; strategy definitions and parameters (V2-MOM, V2-STR, V2-LRV); execution model; portfolio construction and accounting (§11); benchmarks B1/B2; transaction costs; economic gate and robustness completeness gate; family selection, multiple testing and graduation; the three-series price policy (raw = execution/accounting, PIT TR index = signals, `adjustment=all` = audit only); corporate-action normalisation and v2.0.1 C1, C3, C4 in full, and C2 except the addition of rule 4a; the frozen split-ratio tolerance (0.1 %) and the 2 % missing-session rule; the requirement that every cross-check mismatch is a BLOCKING data review.

---

## 1. Cross-check change-detection rule (§3.4) — CHANGED

**Old rule (v2.0 R1 §3.4, verbatim):** "per symbol, `f_i(k) = C_i(k) / C^all_i(k)`. Every session where `f` changes by more than a numerical tolerance of 1e-6 (relative) must coincide with an event in the event list, and every event must coincide with a change in `f`; split events must match the factor change ratio to within 0.1 %. Any mismatch is a BLOCKING data review…"

**Why the old rule is infeasible (provider limitation, DAY-18 evidence):**
- Alpaca stores `adjustment=all` closes with 2–4 decimal places (mostly 2). Backward adjustment through the `asof` date includes corporate actions after Stage R (e.g. dividends initiated in 2024, a 2025 split), so whole histories are rescaled and then rounded.
- The rounding error of a stored adjusted close is an **absolute** quantity (at most half a unit in the last stored decimal). Its effect on `f` is **relative to the adjusted price level**, so it differs by orders of magnitude across symbols and years. A single fixed relative tolerance is therefore wrong in principle, not merely mis-sized: 1e-6 flags 1,475–1,734 non-event sessions per affected symbol; a larger fixed value would be simultaneously too loose for high-priced periods and too strict for low-priced ones.
- DAY-18 also observed that 20 NVDA dividend dates move `f` by ≤ 1e-3 while no non-event session in any symbol exceeded 1e-3. **These observations are evidence about provider precision only. 1e-3 is not adopted**, because a fixed threshold at the observed noise ceiling would be chosen from this snapshot's outcome and would leave real events undetectable.

**New rule (precision-interval rule):**

Notation, per symbol `i`, on sessions present in both raw and `all` series (frozen §3.4 common-session set):
- `r_k` = stored raw close, treated as exact (an observed trade price; no rounding term).
- `a_k` = stored `adjustment=all` close.
- `d_i` = the **maximum number of decimal places** among symbol `i`'s stored `adjustment=all` closes in the snapshot, where the decimal places of a value are those of its shortest round-trip decimal representation (trailing zeros not counted).
- `δ_i = 0.5 · 10^(−d_i)` (half a unit in the last stored place: round-to-nearest assumption).
- `f_k = r_k / a_k`; for consecutive common sessions `p < k`: `ρ = f_k / f_p`.
- Admissible interval of the true ratio (true adjusted prices anywhere in `[a − δ, a + δ]`):
  - `ρ_min = ρ · (a_k / (a_k + δ_i)) · ((a_p − δ_i) / a_p)`
  - `ρ_max = ρ · (a_k / (a_k − δ_i)) · ((a_p + δ_i) / a_p)`
- **A factor change is detected at `k` if and only if `1 ∉ [ρ_min, ρ_max]`.**
- If `a_p − δ_i ≤ 0` or `a_k − δ_i ≤ 0`, the pair is **PRECISION_DEGENERATE** (no bound exists): BLOCKING data review.

**Coincidence rules (unchanged from §3.4 except for the detection test):**
- Every detected change must coincide with ≥ 1 retained split/dividend event whose `ex_date ∈ (p, k]` → otherwise **BLOCKING** (unexplained factor change: possible missing event).
- Every retained split/dividend event must coincide with a detected change → otherwise **BLOCKING** (event without provider confirmation). **No precision exemption is granted** (see open question OQ1).
- Split magnitude: on a session carrying only split events, `f_p / f_k` must equal the product of `q` within **0.1 %** (frozen, unchanged).
- Same-session split + dividend: remains BLOCKING (v2.0.1 C3 rule 4, unchanged).
- Events covered by the first-session rule (item 2) are excluded from these coincidence tests.

**PASS (per symbol):** zero unexplained detected changes, zero unconfirmed events, all split-magnitude checks within 0.1 %, zero PRECISION_DEGENERATE pairs. **BLOCKING:** any of these violated.

**Rationale:**
- The bound is derived from the provider's stored representation, not tuned to any outcome; it has no free constant.
- It **fails safe**: if the provider rounds more coarsely than `d_i` implies, or truncates instead of rounding, or raw closes are themselves rounded, the true jitter exceeds the bound and appears as unexplained detected changes → BLOCKING. A violated assumption can produce false BLOCKING results, never a false PASS.
- `d_i` is taken per symbol as the maximum observed decimals (the finest stored precision), which gives the tightest bound and therefore the most conservative detection.

**Persisted evidence (per symbol, no factor or price value):** `d_i`, `δ_i`, number of common sessions, detected changes, matched sessions, list of unexplained-change dates, list of unconfirmed-event ex-dates, split-magnitude check results (pass/fail per session), PRECISION_DEGENERATE count, first-session events list.

**Still forbidden:** using `adjustment=all` for any signal, fill, mark, weight or P&L; altering stored data; choosing `d_i`, `δ_i` or any tolerance from cross-check outcomes; widening the bound after observing failures without a new committed amendment.

---

## 2. First-session events (§3.4 coincidence test) — NEW RULE

**Old rule:** none. v2.0 R1 §3.4 requires every event to coincide with a change; an event whose `ex_date` is on or before the first acquired session has no previous session, so the bijection cannot be evaluated. DAY-18 found three: CSCO, JPM, ORCL cash dividends with `ex_date` 2016-01-04.

**New rule:**
1. An event of symbol `i` whose `ex_date` ≤ the first session present in both the raw and `all` series of symbol `i` **in the Stage R snapshot** is classified **`FIRST_SESSION_UNTESTABLE`**.
2. `FIRST_SESSION_UNTESTABLE` events are **NON-BLOCKING**, are listed in the cross-check evidence, and are **excluded from the PIT TR index and from accounting**.
3. The rule applies **only** to the symbol's first available common session. An event whose `ex_date` falls in a gap of missing bars later in the series is mapped to `(p, k]` and tested as usual (frozen).

**Rationale (methodology, not outcome):**
- **Untestable by construction, not missing data:** DAY-17 Q2 established that the provider returns no SIP 1Day bar before 2016-01-04, so no observable session exists before the first one; extending the window cannot help.
- **No effect on any Stage R quantity under frozen formulas:** the frozen TR index sets `TR_i(k₀) = 1` and applies only events with ex-date in `(p, k]` for later sessions, so an ex-date ≤ `k₀` never enters `TR`. Under frozen §11 every segment starts flat at its first open (the research segment starts 2017-02-01), so no position exists to receive the dividend.
- **Genuinely missing or inconsistent data remains detectable:** a missing event anywhere after the first session appears as an unexplained detected change (item 1) → BLOCKING. The exclusion cannot hide such a case, because it only removes events that can affect nothing.

---

## 3. Identity when no anchor exists (v2.0.1 C2) — NEW RULE 4a

**Old rule (v2.0.1 C2 rule 4, verbatim):** "a record under ticker `T` (or its alias) with a non-empty CUSIP not in `T`'s CUSIP set is a foreign-entity record: excluded from `T`, listed in the identity report, and documented in the frozen §3.4 BLOCKING data review. For Stage R this applies to META→METV."

**Gap found in DAY-18:** CRM and AMD have no CUSIP-bearing split/dividend record and no name change, so rule 3 yields no anchor and their CUSIP sets are empty. Rule 4 then classified the acquirer-side records CRM←WORK (stock_and_cash_merger, 2021-07-21) and AMD←XLNX (stock_merger, 2022-02-14) as foreign. Rule 4 presupposes an established identity: with an empty set the CUSIP can be neither confirmed nor refuted. v2.0.1 itself names only META→METV as the Stage R foreign entity. Economic neutrality (an acquirer-side merger changes neither shares nor cash) is **not** identity evidence.

**Decision: B — OPEN / BLOCKING pending confirmation.**

**New rule 4a:** if `T` has **no anchor** (v2.0.1 C2 rule 3), every record under ticker `T` (or its alias) carrying a non-empty CUSIP is classified **`IDENTITY_UNVERIFIED`** — neither assigned to `T` nor foreign. Each `IDENTITY_UNVERIFIED` record is a **BLOCKING data review**, resolved only by:
- (a) an anchor for `T` established from same-provider data under v2.0.1 C2 rule 3 in a later acquisition; or
- (b) an explicit reviewer decision recorded in a committed review artifact, stating for each record whether it belongs to `T` (then it is processed under frozen §3.4 as a review item: acquirer-side merger) or to another entity (then excluded), with the reasoning.

Rule 4 is unchanged where an anchor exists: **META→METV remains a foreign-entity record** (META's anchor is the FB→META `new_cusip`; the METV `old_cusip` differs).

**Current classification:** CRM←WORK and AMD←XLNX → `IDENTITY_UNVERIFIED`, **BLOCKING**.

---

## 4. SPY corporate-action completeness — STATUS CLARIFIED

- No external expectation (e.g. a quarterly distribution count) is a protocol criterion. The DAY-17A observation that a quarterly schedule would "imply 27" records is **withdrawn as a completeness criterion**; it was an inference from outside knowledge.
- SPY completeness **is** the v2.0.2 cross-check outcome for SPY (item 1 bijection plus item 2), exactly as for every other symbol.
- **Status now: `PENDING_REEVALUATION`** — unresolved. DAY-18 evidence (26 retained SPY dividends, all coincident with a change under the old test) is recorded but is not a v2.0.2 result.
- SPY remains benchmark B2, reference only; its status does not alter any gate definition.

---

## 5. Exact sections affected
| Location | Effect |
|---|---|
| v2.0 R1 §3.4 "Cross-check" paragraph | 1e-6 relative test replaced by the precision-interval rule (item 1); first-session classification added (item 2); coincidence rules, 0.1 % split tolerance and BLOCKING semantics unchanged |
| v2.0 R1 §3.8 "corporate-action cross-check" row | unchanged wording; now evaluated with v2.0.2 item 1–2 |
| v2.0.1 C2 | rule 4a added (item 3); rules 1–7 otherwise unchanged |
| v2.0.1 §7 SPY note / DAY-17A finding | withdrawn as a criterion (item 4) |
| v2.0 R1 §20 Q4 | unchanged (NON-BLOCKING); item 1 does not rely on Alpaca's adjustment method |

## 6. Open questions
| ID | Question | Status |
|---|---|---|
| OQ1 | If a genuine event yields no detected change because its factor change lies within the rounding interval, it is BLOCKING under item 1. Whether a precision-based exemption is warranted can be decided only by a later amendment, after re-evaluation, and must not be justified by research outcomes | OPEN (only if it occurs) |
| OQ2 | Round-to-nearest (`δ = ½·10^−d`) and exact raw closes are assumptions about the provider; violations fail safe (BLOCKING) | NON-BLOCKING assumption |
| OQ3 | Resolution of the CRM←WORK and AMD←XLNX `IDENTITY_UNVERIFIED` records (rule 4a path a or b) | **BLOCKING** |
| OQ4 | SPY completeness under v2.0.2 | PENDING_REEVALUATION |
| OQ5 | Line-ending (CRLF) drift of frozen artifacts under `core.autocrlf=true` (DAY-18 process event); not a protocol rule | NON-BLOCKING, process |

## 7. Implementation impact (no code changed in DAY-18A)
- `acquisition/v2/crosscheck.py`: replace the fixed `FACTOR_CHANGE_REL_TOL` test with the precision-interval test; compute `d_i` from stored `all` closes (shortest round-trip representation); add PRECISION_DEGENERATE detection; reclassify first-session events as `FIRST_SESSION_UNTESTABLE` (non-blocking) instead of BLOCKING `uncheckable`.
- `acquisition/v2/identity.py`: return `IDENTITY_UNVERIFIED` records (rule 4a) separately from foreign-entity records.
- `acquisition/v2/reviews.py`: classify `IDENTITY_UNVERIFIED` as BLOCKING; FIRST_SESSION_UNTESTABLE as non-blocking; review-item clean-date condition uses the v2.0.2 cross-check.
- `acquisition/v2/contract.py`: record protocol version 2.0 R1 + 2.0.1 + 2.0.2; the frozen 1e-6 constant is retired from the cross-check (kept only as historical record).
- Tests for the interval rule (incl. price-level dependence, coarser-than-assumed rounding failing safe, degenerate pairs), first-session classification, and rule 4a.
- **Re-evaluation needs no new acquisition:** the snapshot stores the provider's closes as float64 parsed from the JSON numbers, so `d_i` is recoverable from the stored values; events, identity inputs and bars are already persisted. Re-evaluation must write its results to a new location (the original snapshot is write-once and must not be modified).

## 8. Research-safety impact
- No data acquired, no holdout or forward-OOS access, no price/return/signal/backtest computation in DAY-18A.
- The new rule depends only on stored representation and corporate-action records; it cannot use or be tuned to any research outcome (none exists).
- The amendment makes no Stage R data usable; it only defines how the existing snapshot is to be re-evaluated.
