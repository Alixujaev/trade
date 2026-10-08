# Protocol v2.0.4 — Amendment (DAY-18J)

> **RECOVERED ARTIFACT.** This file was recovered on 2026-10-08 from the authoritative DAY-18J handoff content. The original DAY-18J work was never committed. Recovery is **not** a new protocol-owner decision and introduces no new semantics.

| Field | Value |
|---|---|
| Amendment version | **v2.0.4** |
| Type | **protocol_change** — `modified: true` |
| Status | **DRAFT — PENDING COMMIT** |
| Parent protocol | v2.0 R1 `ba3cefe54ccf2fe14c62f1c609f143d8a0904221` |
| Parent amendments | v2.0.1 `ed034b3e9500cc4d9b33625de7e1883f572cd5a4`; v2.0.2 `0ebb6065f6e981e324220bae2abd2222800b2228`; **v2.0.3 `d26b36ef802cf0810952b2e5c4e8e19d908b4555` (immediate parent)** |
| Evidence | DAY-18D `25d74f7`, DAY-18F records `c36b673`, DAY-18G `2ad9b27`, DAY-18H `75c914f` |
| Stage R snapshot (not read or modified by this task) | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` |
| Drafted / recovered | 2026-10-08 |

**Purpose.** This amendment defines deterministic, exact mathematical evaluation of the v2.0.3 precision-interval rule, so that finite-precision floating-point evaluation cannot create or hide detections.

**Precedence.** v2.0 R1 and v2.0.1–v2.0.3 remain immutable documents. Once this amendment is committed, items 1–4 below define how the v2.0.3 item 1 rule is evaluated. **The mathematical rule does not change. v2.0.4 clears no blocker by itself and does not make Stage R usable.**

## 0. Unchanged
- **v2.0.3 precision rule:** `d_k`, `δ_k`, `ρ`, `ρ_min`, `ρ_max` and the detection condition keep their mathematics. The interval is closed.
- **Blocking and event rules:** PRECISION_DEGENERATE ⇒ BLOCKING. The v2.0.2 coincidence rules hold, with no precision exemption. The split-magnitude tolerance stays at 0.1 %. The first-session rule is unchanged.
- **Review records:** the v2.0.3 review-record mechanism, its item types and its decision enums are unchanged. The existing DAY-18F records are not modified.
- **Everything else from v2.0.3 §0:** universe, timeline, strategies, execution, accounting, benchmarks, costs, gates, data roles, v2.0.1 C1–C4 including rule 4a, round-to-nearest and exact-raw assumptions, the 2 % missing-session rule, and the rule that every cross-check mismatch is a BLOCKING data review.

---

## 1. Exact evaluation — CHANGED (evaluation semantics only), **FROZEN**

**Old rule:** v2.0.3 item 1 defines the interval mathematically. It does not specify numerical evaluation semantics, and the implementation evaluates it in IEEE 754 float64.

**New rule:**
- **Mathematical rule (unchanged):** a factor change is **detected iff `NOT (ρ_min ≤ 1 ≤ ρ_max)`**.
- **Closed interval:** if `ρ_min ≤ 1 ≤ ρ_max`, there is **NO DETECTION**. Endpoint equality counts as containment.
- **Value source.** The inputs to exact evaluation are the IEEE 754 binary64 values persisted in column `close` of `bars_raw/<SYMBOL>.parquet` (raw close `r`) and `bars_all/<SYMBOL>.parquet` (adjusted close `a`) of the immutable snapshot under evaluation.
- **Exact value.** The exact rational value of each stored raw close and of each stored adjusted close is the rational number denoted by the shortest round-trip decimal representation of that persisted binary64 value. This is the decimal string with the fewest significant digits that converts back to the identical binary64 under round-to-nearest-even, choosing the one closest to the binary64 value if several exist. The exact binary64 value itself is not used.
- **Raw closes are exact.** They carry no precision term (unchanged from v2.0.2/v2.0.3). Adjusted closes carry `δ_k` (below), with `d_k` read from the same shortest representation.
- **Exact factor.** `f = R/A` is computed exactly from these rationals.
- **`d_k`:** remains the number of displayed decimal places used by v2.0.3.
- **`δ_k`:** `δ_k = 1 / (2 · 10^max(d_k, 2))`, represented exactly.
- **Arithmetic:** all v2.0.3 formulas are evaluated with **exact rational arithmetic**.
- **Detection:** evaluated exactly as `NOT (ρ_min ≤ 1 ≤ ρ_max)`.
- **No adjustments:** no floating-point tolerance, no epsilon, no provider-specific tolerance, no symbol-specific exception and no date-specific exception.
- **Authority:** the exact result is authoritative. float64 may be calculated only as diagnostic information.

## 2. Invalid values — NEW status
- **Degenerate values:** the existing v2.0.3 degenerate check remains authoritative. If `a − δ ≤ 0`, the item remains **BLOCKING** under the existing protocol.
- **EXACT_EVALUATION_INVALID:** a non-finite, non-positive or non-convertible value that cannot be represented under exact evaluation becomes **`EXACT_EVALUATION_INVALID`**, which is **BLOCKING**.
- **No coercion:** invalid values are never silently coerced.

## 3. float64 disagreement — NEW diagnostic classifications
| Exact | float64 | Classification | Consequence |
|---|---|---|---|
| NO DETECTION | DETECTION | **`NUMERICAL_FALSE_POSITIVE`** | Not a real factor change. **NON-BLOCKING.** Must be recorded in the evaluation evidence. |
| DETECTION | NO DETECTION | **`NUMERICAL_FALSE_NEGATIVE`** | Exact detection remains authoritative. Normal v2.0.3 coincidence/event rules apply. |

The rule works symmetrically in both directions.

## 4. Review-record interaction
- **No new decision type:** no new review-record decision type is introduced.
- **Existing records:** existing v2.0.3 records remain historically valid.
- **MOOT:** if an item that previously carried a v2.0.3 review record is no longer detected under exact v2.0.4 evaluation, the record becomes **MOOT**. It is not INVALID and it remains in history.
- **No record changes:** this amendment modifies no existing record and creates no new record.

---

## 5. Stage R status
**BLOCKED** (unchanged). v2.0.4 defines evaluation semantics only. Nothing is re-evaluated here and no blocker is cleared.

## 6. Rationale and history
v2.0.3 left the numerical evaluation of its closed-interval rule unspecified. DAY-18H showed that this lets float64 rounding create detections. For the two remaining v2.0.3 UNEXPLAINED_CHANGE items (AMZN 2016-02-22 and NFLX 2018-11-29), the exact `ρ_max` equals 1, while float64 evaluates it as `1 − 2.22·10⁻¹⁶` (1 ULP) and `1 − 1.11·10⁻¹⁶` (0.5 ULP) respectively. These items are cited **only** as history. The rule above is general, and neither item is resolved by this amendment. Both remain unresolved until a mechanical v2.0.4 re-evaluation. A tolerance or epsilon was not chosen because it would change the mathematical rule, whereas exact evaluation reproduces it as written.

## 7. Open questions
| ID | Question | Status |
|---|---|---|
| **OQ10** | Conversion of raw closes `r_p`, `r_k` to exact rationals. | **RESOLVED** (protocol-owner approved): `artifacts/day18j/oq10-raw-close-resolution.md`; rule in §1. |
| OQ1 | Precision-based exemption for undetected genuine events | OPEN; not adopted (unchanged) |
| OQ2 | Round-to-nearest and exact raw closes | NON-BLOCKING (unchanged) |
| OQ5 | CRLF drift of frozen artifacts | NON-BLOCKING (process) |
| OQ7 | Remaining v2.0.3 UNEXPLAINED_CHANGE items | **BLOCKING** until mechanical v2.0.4 re-evaluation |

## 8. Implementation impact (no code changed in DAY-18J)
- **`acquisition/v2/crosscheck.py`:** evaluates `ρ`, `ρ_min`, `ρ_max` and detection in exact rational arithmetic, with exact `δ_k`. Computes the float64 interval as a diagnostic. Adds the EXACT_EVALUATION_INVALID status and records NUMERICAL_FALSE_POSITIVE / NUMERICAL_FALSE_NEGATIVE in the evidence.
- **`acquisition/v2/reviews.py`:** a record whose item is no longer detected becomes MOOT. No new decision type.
- **`acquisition/v2/reevaluate.py`:** the protocol chain includes v2.0.4. Output goes to a new write-once directory; the v2.0.2 and v2.0.3 outputs are left untouched.
- **Tests:** exact `ρ_max = 1`, an interior interval, an exterior interval, disagreement in both directions, EXACT_EVALUATION_INVALID, PRECISION_DEGENERATE (unchanged) and MOOT handling.
- **Data:** no re-acquisition required.

## 9. Research-safety impact
No data acquired, no network, no snapshot access, no holdout or forward-OOS access, and no signal, return, TR index or backtest. The rule does not depend on outcomes, and v2.0.4 makes no Stage R data usable by itself.
