# DAY-18I — Protocol-Owner Review of the Two Remaining Stage R Blockers

> **Decision document. No review record created, superseded or modified. No protocol amendment. No code, snapshot or protocol file changed. No re-evaluation.**
> Per v2.0.3 item 2 the decision is the protocol owner's; this document was prepared by the implementation agent under the DAY-18I instruction and must be confirmed by the protocol owner when committed.

| Field | Value |
|---|---|
| Task | DAY-18I — protocol-owner disposition of AMZN 2016-02-22 and NFLX 2018-11-29 (UNEXPLAINED_CHANGE) |
| Instructed HEAD | `2ad9b272002ce514318ce7c3774b422f24a19f3c` |
| Working HEAD | `75c914f5226685f331cbb2e56a9c4db7c52b24b9` (= 2ad9b27 + DAY-18E dossier and DAY-18H evidence artifacts only; no code/protocol/record change) |
| Protocol chain | v2.0 R1 `ba3cefe` + v2.0.1 `ed034b3` + v2.0.2 `0ebb606` + v2.0.3 `d26b36e` |
| Snapshot | `stage_r_20261007T093410Z`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` (not present in this environment; not read) |
| Evidence | `artifacts/day18h/{day18h-evidence-report.md,.json, amzn-evidence.json, nflx-evidence.json}` |
| Existing records | `artifacts/reviews/stage_r/amzn-20160222-20261007.json`, `nflx-20181129-20261007.json` — both `UNRESOLVED` (DAY-18F), unchanged |

## 1. Independent verification of the DAY-18H arithmetic
Values as reported by DAY-18H (r = raw close, a = stored adjusted close, δ = 0.005 for both, v2.0.3 item 1):

| Item | r_p | r_k | a_p | a_k | exact ρ_max (rational) | float64 ρ_max | float `1 ≤ ρ_max` |
|---|---|---|---|---|---|---|---|
| AMZN | 534.90 | 559.50 | 26.74 | 27.98 | **1** | 0.9999999999999998 | False |
| NFLX | 282.65 | 288.75 | 28.26 | 28.88 | **1** | 0.9999999999999999 | False |

Exact evaluation (Python `fractions.Fraction` over the decimal values) gives `ρ_max = (r_k/(a_k−δ)) / (r_p/(a_p+δ)) = 1` exactly and `ρ_min ≤ 1 ≤ ρ_max` for both items. The reconciliation uses **only** r, a, δ from the snapshot; no external source is needed. (The snapshot bytes themselves were not re-hashed here because the snapshot is absent from this environment.)

## 2. Answers to the eight review questions
1. **Is the v2.0.3 interval defined in real arithmetic?** Yes. Item 1 defines `d_k` from the shortest round-trip *decimal* representation, `δ_k = ½·10^(−max(d_k,2))`, closed-form `ρ_min`, `ρ_max`, and "detected iff `1 ∉ [ρ_min, ρ_max]`". No evaluation precision, rounding mode or tolerance is specified; the text is a statement about real numbers.
2. **Is the float64 result merely evaluation error?** Yes. The true bound is exactly 1; float64 under-evaluates it by 1 ULP (AMZN) and 0.5 ULP (NFLX) because `a_p + δ` is not representable. Under the rule as written, **neither pair is a detected factor change**.
3. **Does the protocol permit treating an implementation artifact as a resolved false positive?** No explicit rule. v2.0.3 item 3.1 provides the *mechanical* path ("if the change is no longer detected, it disappears mechanically"), which presupposes a re-evaluation that evaluates item 1 correctly. Item 3.2 review records address items that *remain* detected under the rule. No item, enum or rule addresses "detected by the implementation, not detected by the rule".
4. **Is `PROVIDER_ADJUSTMENT_ARTIFACT` the correct category?** No. Its mechanical precondition (zero corporate-action records of any type in `(p,k]` in both `data_quality` payloads) is satisfied, so the validator would accept such a record. But the category asserts that the provider's adjusted series contains an artifact that explains a genuine detected change. The evidence shows the opposite: the provider values are exactly the round-half-to-even representations the rule already accounts for, and the rule detects nothing. Recording it would encode a cause the evidence refutes. Rejected.
5. **Is exact reconciliation sufficient without inventing a provider error?** Yes, it fully establishes the defect (non-detection under the rule) without any provider-error claim. It is not sufficient to authorise any existing *review-record* decision, because none describes this situation (item 4).
6. **Can the future split explain the adjusted level without being an event in `(p,k]`?** Yes. A constant backward-adjustment factor (20 for AMZN, 10 for NFLX) affects the level of `f`, not the ratio `ρ`. Backward adjustment through post-Stage-R actions is already acknowledged in v2.0.2 item 1. The splits are outside `(p,k]` and are not needed as evidence: the detection test concerns `ρ` only.
7. **Same disposition for AMZN and NFLX?** Yes: identical mechanism, identical evidence structure, identical rule text.
8. **Is an amendment required before resolution?** Yes. Correcting the implementation would make the items disappear mechanically, but the frozen chain does not specify evaluation arithmetic, and v2.0.3 item 1.5 (non-iteration) forbids changing the detection behaviour and re-running after observing blocks without a new committed amendment. Changing `crosscheck.py` now and re-evaluating would be exactly that pattern. A committed amendment must first make the evaluation semantics explicit.

## 3. Decision
- **AMZN 2016-02-22: UNRESOLVED — BLOCKING** (existing DAY-18F record stays in force; no new or superseding record).
- **NFLX 2018-11-29: UNRESOLVED — BLOCKING** (same).
- **Finding:** the evidence is sufficient to establish that both detections are finite-precision implementation artifacts that the frozen rule, evaluated as written, does not produce. **The current protocol has no admissible disposition for this case.** No resolution is forced; no new category is invented.
- **Stage R: BLOCKED** (`usable_for_research = false`).

## 4. Scope for the next task (not started)
DAY-18J: draft a minimal protocol amendment defining the disposition of precision-interval detections caused solely by finite-precision implementation. Recommended content, for the protocol owner to decide:
- Prefer an **evaluation-semantics rule** (item 1 evaluated in exact rational arithmetic on the shortest round-trip decimal values of `r_k`, `a_k`, `δ_k`) over a new review category or an epsilon tolerance. Exact evaluation introduces no free constant, is outcome-independent, and fixes errors in **both** directions (false detections and false non-detections) for every pair, not only these two.
- State that the rule is applied to all symbols and pairs at once, and that the re-evaluation is not adjusted after its result (item 1.5 unchanged).
