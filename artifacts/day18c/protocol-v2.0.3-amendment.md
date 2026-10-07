# Protocol v2.0.3 — Amendment (DAY-18C)

| Field | Value |
|---|---|
| Amendment version | **v2.0.3** |
| Type | **protocol_change** — `modified: true` |
| Status | **DRAFT — PENDING COMMIT** |
| Parent protocol | v2.0 R1 `ba3cefe54ccf2fe14c62f1c609f143d8a0904221` |
| Parent clarifications | v2.0.1 `ed034b3e9500cc4d9b33625de7e1883f572cd5a4`; **v2.0.2 `0ebb6065f6e981e324220bae2abd2222800b2228` (immediate parent)** |
| Evidence | DAY-18B re-evaluation, commit `4a36fc70e0b0d28d228e1ebdfd3ffda0ea4cd633` (`artifacts/day18b/day18b-stage-r-revaluation.{md,json}`) |
| Stage R snapshot (not read or modified by this task) | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` |
| Drafted | 2026-10-07 |

**Precedence.** v2.0 R1, v2.0.1 and v2.0.2 remain immutable documents. From the commit of this amendment, items 1–5 below replace or extend the cited rules. **v2.0.3 clears no existing blocker by itself and does not make Stage R usable**; the existing snapshot must be re-evaluated under v2.0.3 in a separate task.

**Decision provenance.** The precision model (item 1), the identity evidence scope (item 5) and the permission for reviewer records for AMZN/NVDA (items 3–4) were chosen by the protocol owner in DAY-18C. **No candidate precision rule was applied to the Stage R snapshot before or during this choice**; the choice rests on provider-representation logic and the representation statistics already reported in DAY-18B (decimal-place histograms), never on cross-check outcomes.

## 0. Unchanged
Universe (25 + SPY benchmark-only); timeline (warmup, research, holdout, excluded, forward OOS); strategy definitions and parameters; execution model; portfolio construction and accounting (§11); benchmarks B1/B2; transaction costs; Gate A, Gate B, Gate C; raw OHLC as execution/accounting source; `adjustment=all` as audit-only source; v2.0.1 C1, C3, C4 and C2 (incl. v2.0.2 rule 4a); v2.0.2 first-session rule (FIRST_SESSION_UNTESTABLE); v2.0.2 coincidence rules (every detected change needs an event in `(p,k]`, every event needs a detected change, no precision exemption); split-magnitude tolerance 0.1 %; PRECISION_DEGENERATE ⇒ BLOCKING; v2.0.2 round-to-nearest and exact-raw assumptions (OQ2); META→METV foreign-entity classification; SPY completeness criterion (v2.0.2 item 4); 2 % missing-session rule; every cross-check mismatch is a BLOCKING data review.

---

## 1. Precision model for the cross-check — CHANGED, **FROZEN**

**Old rule (v2.0.2 item 1):** "`d_i` = the maximum number of decimal places among symbol `i`'s stored `adjustment=all` closes … `δ_i = 0.5 · 10^(−d_i)`", one `δ` for all sessions of the symbol.

**Problem (DAY-18B evidence, representation only):** the provider does not store one precision per symbol. Decimal-place histograms of stored adjusted closes: AVGO {0:18, 1:151, 2:1573, 3:20}; MU {0:20, 1:162, 2:1565, 3:15}; NFLX {0:23, 1:146, 2:1456, 3:137}; TSLA {0:30, 1:160, 2:1568, 3:4}; NVDA {0:3, 1:63, 2:651, 3:966, 4:79}. A minority of finer values sets `d = max`, so `δ` is too small for the majority — the fail-safe failure anticipated in v2.0.2 OQ2. The rule's single-precision premise is refuted by the data representation.

**New rule (per-value precision with a 2-decimal floor):**
- For each stored adjusted close `a_k`: `d_k` = number of decimal places of its shortest round-trip decimal representation (trailing zeros not counted), and
  **`δ_k = ½ · 10^(−max(d_k, 2))`**.
- Raw closes are exact (unchanged). `f_k = r_k / a_k`; for consecutive common sessions `p < k`: `ρ = f_k / f_p`.
- **`ρ_min = ρ · (a_k / (a_k + δ_k)) · ((a_p − δ_p) / a_p)`**
- **`ρ_max = ρ · (a_k / (a_k − δ_k)) · ((a_p + δ_p) / a_p)`**
- **A factor change is detected iff `1 ∉ [ρ_min, ρ_max]`.**
- PRECISION_DEGENERATE iff `a_p − δ_p ≤ 0` or `a_k − δ_k ≤ 0` → BLOCKING (unchanged semantics).
- All coincidence, split-magnitude, first-session and BLOCKING rules of v2.0.2 apply unchanged.
- Persisted evidence per symbol: the precision histogram (count of values per `d_k`), the count of pairs evaluated, plus all v2.0.2 evidence fields; no price or factor values.

**Selection basis (provider-representation logic; outcome-independent):**
1. *Validity without new assumptions for `d_k ≥ 2`:* a value stored at `P` decimals and displayed without trailing zeros shows `d_k ≤ P` digits, so its rounding error is `≤ ½·10^(−P) ≤ ½·10^(−d_k)`. The per-value bound is therefore a guaranteed upper bound under the existing round-to-nearest assumption, whatever precision the provider used for that value.
2. *The 2-decimal floor:* for values displayed with 0 or 1 decimals, the floor assumes they were stored at ≥ 2 decimals (trailing zeros). This is consistent with every measured histogram: in the 10 symbols measured in DAY-18B (AAPL, ADBE, AMD, AMZN, AVGO, MU, NFLX, NVDA, SPY, TSLA) the shares of 0- and 1-decimal values (≈ 0.2–1.7 % and ≈ 3.6–11 %) match the trailing-zero frequencies expected from storage at ≥ 2 decimals (≈ 1 % and ≈ 9 %). The floor only **tightens** the bound relative to the pure per-value rule; if the assumption is false for some value, the bound is too tight and the result is a false BLOCKING, never a false pass (fail-safe).
3. *Continuity with v2.0.2:* for a series whose values all carry ≤ 2 decimals, `δ_k = 0.005` for every value — identical to v2.0.2 with `d = 2`. The change matters only where the representation is mixed.
4. *Rejected candidates (logic, not outcomes):* per-value without floor (valid but loose — `δ` of 0.05 or 0.5 on roughly 10 % of sessions could hide a missing event there); dominant/mode precision (not an error bound; NVDA shows two regimes, so a single symbol precision is wrong in principle); leaving the rule OPEN (unnecessary: a rigorous bound exists).
5. *Non-iteration:* this rule is frozen without having been evaluated on any Stage R symbol. If its later application blocks, the rule is **not** adjusted and re-run; any further change requires a new committed amendment justified by representation evidence, not by which symbols pass.

---

## 2. Committed review-record mechanism — NEW (used by items 3, 4, 5)

**Old rule:** v2.0.2 rule 4a and the frozen §3.4 "BLOCKING data review" did not define how a review is recorded or by whom.

**New rule:**
- **Location:** `artifacts/reviews/stage_r/<record_id>.json`, one file per decision.
- **Effective only when committed** to the repository; a record is immutable after commit. A correction is a new record with `supersedes: <record_id>`; the superseded record remains in history.
- **Who decides and records:** the **protocol owner** (human). An automated agent may prepare a draft record but **must not decide, approve or commit a decision on its own**; the committed record states the reviewer.
- **Required fields:** `record_id`; `item_type` ∈ {`UNEXPLAINED_CHANGE`, `UNCONFIRMED_EVENT`, `IDENTITY_UNVERIFIED`}; `item_key` (entity, session or event date, corporate-action `id` where applicable); `source_snapshot_manifest_sha256`; `protocol_version` (`2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3`); `evidence[]` (each: `type` ∈ {`same_provider_record`, `regulatory_filing`}, `reference` (snapshot file + record id, or URL), `retrieved_utc`, `sha256` of the cited document or record); `decision` (enum per item type, below); `reasoning`; `reviewer`; `decided_utc`; `supersedes` (or null).
- **Provenance:** a re-evaluation reads only records committed at its HEAD; it validates schema, `item_key` match and `source_snapshot_manifest_sha256`, and stores each applied record's blob SHA-256 in its output. Invalid, uncommitted or mismatching records are ignored and the item stays **BLOCKING**.
- **No decision may rely on economic neutrality, on the magnitude of a change, or on research outcomes.**

---

## 3. AMZN 2016-02-22 — UNEXPLAINED_CHANGE review path

**Old state (DAY-18B):** one detected factor change on 2016-02-22 with no AMZN corporate-action event in `(p, k]`; BLOCKING; cause UNKNOWN.

**New rule (applies to every UNEXPLAINED_CHANGE, AMZN 2016-02-22 included):**
1. The item is first re-classified by the v2.0.3 re-evaluation (item 1 mechanics). If the change is no longer detected, it disappears mechanically; otherwise it remains UNEXPLAINED_CHANGE — **BLOCKING**.
2. A remaining item can be resolved only by a committed review record (item 2) with one of:
   - `PROVIDER_ADJUSTMENT_ARTIFACT` → **RESOLVED** (no event added; TR and accounting, which use raw prices and retained events only, are unchanged). Required evidence: same-provider records showing that **no** corporate-action record of **any** of the 16 types for the entity has an `event_date` or `ex_date` in `(p, k]` in **both** `data_quality=complete` and `data_quality=all` payloads of the snapshot; plus written reasoning.
   - `MISSING_EVENT_CONFIRMED` → remains **BLOCKING** until a committed acquisition step or amendment supplies the event under the frozen rules.
   - `UNRESOLVED` → **BLOCKING**.
3. The size of the change is never evidence. Without a valid committed record the item stays BLOCKING and Stage R stays BLOCKED.

---

## 4. NVDA 2022-03-02 — UNCONFIRMED_EVENT review path (separate from NVDA←MLNX)

**Old state (DAY-18B):** a retained NVDA cash dividend (ex-date 2022-03-02) without a detected change at its session; BLOCKING; cause UNKNOWN.

**Separation:** this is a price-series cross-check item about one dividend record. It is **independent** of the NVDA←MLNX acquirer-side merger review (an identity/review item under frozen §3.4); neither decision affects the other.

**New rule (applies to every UNCONFIRMED_EVENT, NVDA 2022-03-02 included):**
1. First re-classified by the v2.0.3 re-evaluation: if a change is then detected at the event's session, it is **RESOLVED** mechanically. Otherwise it remains UNCONFIRMED_EVENT — **BLOCKING**.
2. A remaining item can be resolved only by a committed review record with one of:
   - `EVENT_RETAINED` → **RESOLVED**; the provider corporate-action record stays authoritative for TR and accounting (v2.0.1 C3). Required evidence: the record is identity-resolved under C2 (+4a), present with identical content in both `data_quality` payloads, field-complete, and not duplicated; plus written reasoning about the absence of corroboration in the adjusted series.
   - `EVENT_REJECTED` → the event is excluded from TR and accounting. Required evidence: same-provider evidence that the record is erroneous (e.g. a later same-provider acquisition, compared under the frozen IDENTICAL/DISCREPANCY rule, that shows the record changed or absent).
   - `UNRESOLVED` → **BLOCKING**.

---

## 5. CRM←WORK and AMD←XLNX — IDENTITY_UNVERIFIED review path

**Old state (v2.0.2 rule 4a):** BLOCKING until "(a) an anchor … established from same-provider data … or (b) an explicit reviewer decision recorded in a committed review artifact"; evidence types not specified.

**New rule:**
1. Resolution path (a) is unchanged. Path (b) uses the committed review-record mechanism (item 2) with `item_type = IDENTITY_UNVERIFIED` and one of:
   - `SAME_ENTITY` → the record is processed as the entity's frozen §3.4 review item (an acquirer-side merger is RESOLVED iff the entity's role is acquirer and the entity's cross-check shows no unexplained change on that date; otherwise BLOCKING).
   - `DIFFERENT_ENTITY` → the record is excluded from the entity (listed like a foreign-entity record).
   - `UNRESOLVED` → **BLOCKING**.
2. **Evidence required for `SAME_ENTITY` or `DIFFERENT_ENTITY`:** at least one item that ties the record's CUSIP to (or distinguishes it from) the issuer of the universe symbol, from either (i) same-provider data, or (ii) a **primary regulatory filing** (e.g. an SEC EDGAR document stating the issuer's CUSIP or the merger parties), cited by URL, retrieval UTC and SHA-256 of the retrieved document. Regulatory filings are admissible **only** for this identity decision; they are not market data, provide no prices or events, and do not substitute an anchor in C2 rule 3.
3. **Economic neutrality is not identity evidence.** No automatic conversion to FOREIGN, DIFFERENT_ENTITY or SAME_ENTITY.
4. If no reviewer confirmation is available, the records remain **BLOCKING** and Stage R remains **BLOCKED**.

**Current status:** CRM←WORK (stock_and_cash_merger, 2021-07-21) — **IDENTITY_UNVERIFIED, BLOCKING**; AMD←XLNX (stock_merger, 2022-02-14) — **IDENTITY_UNVERIFIED, BLOCKING**.

---

## 6. Stage R status
**BLOCKED** (unchanged). v2.0.3 defines rules only; nothing is re-evaluated here and no blocker is cleared.

## 7. Open questions
| ID | Question | Status |
|---|---|---|
| OQ1 (v2.0.2) | Precision-based exemption for undetected genuine events | remains OPEN; not adopted (items 3–4 provide review paths instead) |
| OQ2 (v2.0.2) | Round-to-nearest and exact raw closes | NON-BLOCKING assumption, unchanged; the 2-decimal floor adds the assumption "no value stored coarser than 0.01" (fail-safe) |
| OQ6 | The 2-decimal floor was checked against histograms of 10 symbols; the other 16 were not measured | NON-BLOCKING (fail-safe); histograms are persisted at re-evaluation |
| OQ7 | AMZN 2016-02-22 resolution | **BLOCKING** until re-evaluation and, if needed, a committed record |
| OQ8 | NVDA 2022-03-02 resolution | **BLOCKING** until re-evaluation and, if needed, a committed record |
| OQ9 | CRM←WORK, AMD←XLNX identity | **BLOCKING** until anchor or committed record |
| OQ5 (v2.0.2) | CRLF drift of frozen artifacts | NON-BLOCKING (process) |

## 8. Implementation impact (no code changed in DAY-18C)
- `acquisition/v2/crosscheck.py`: per-value `δ_k = ½·10^−max(d_k, 2)`; interval with `δ_p`, `δ_k`; per-symbol precision histogram in the output.
- New review-record loader/validator: reads `artifacts/reviews/stage_r/*.json` committed at HEAD; schema and key validation; applies decisions per items 3–5; records each blob SHA-256.
- `acquisition/v2/reviews.py`: item types UNEXPLAINED_CHANGE / UNCONFIRMED_EVENT / IDENTITY_UNVERIFIED with record-driven outcomes; default BLOCKING.
- `acquisition/v2/reevaluate.py`: protocol chain includes v2.0.3; writes to a new write-once directory `data/oos_cache/protocol_v2/stage_r/reviews/v2_0_3__<snapshot_id>/`; the v2.0.2 review output is left untouched.
- Tests for per-value precision (incl. floor behaviour and mixed precision), record validation, each decision enum, and BLOCKING defaults.
- No re-acquisition required.

## 9. Research-safety impact
No data acquired; no network; no snapshot access in this task; no holdout or forward-OOS access; no signal, return, TR index or backtest. The precision rule depends only on stored representation; review decisions may not use research outcomes; v2.0.3 makes no Stage R data usable by itself.
