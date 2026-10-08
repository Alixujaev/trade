# OQ10 — Exact Representation of Stored Raw Closes (v2.0.4 draft)

| Field | Value |
|---|---|
| Status | **RESOLUTION PROPOSED — pending protocol-owner approval** (v2.0.4 itself is still a DRAFT) |
| HEAD | `75c914f5226685f331cbb2e56a9c4db7c52b24b9` |
| Parent protocol | v2.0.3 `d26b36ef802cf0810952b2e5c4e8e19d908b4555` |
| Draft concerned | `artifacts/day18j/protocol-v2.0.4-amendment.{md,json}` (not modified by this task) |
| Snapshot | `stage_r_20261007T093410Z`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`. Read-only, unchanged. |
| Date | 2026-10-08 |

## 1. Question
v2.0.4 defines how a stored **adjusted** close becomes an exact rational: its shortest round-trip decimal representation, converted exactly. It does not define the same for stored **raw** closes.

`f(t) = r(t) / a(t)`, and `ρ`, `ρ_min`, `ρ_max` all depend on `f`. Exact evaluation therefore needs a deterministic exact value for `r(t)` as well. Which source representation is authoritative?

## 2. Evidence inspected
**Protocol chain**
- **v2.0.2 item 1:** "`r_k` = stored raw close, treated as exact (an observed trade price; no rounding term)".
- **v2.0.2 implementation note:** "the snapshot stores the provider's closes as float64 parsed from the JSON numbers".
- **v2.0.2/v2.0.3:** `d_k` is defined through "the shortest round-trip decimal representation" of the stored adjusted value.
- **v2.0.3:** `raw_close: exact (unchanged)`.
- **R1 §11.10:** float64 accounting concerns accounting only and is not affected.

**Serialization path (code).** Raw and adjusted closes take the same path:
1. `acquisition/v2/http.py` parses the provider JSON with `resp.json()`, so each JSON number becomes a Python float (IEEE 754 binary64).
2. `acquisition/v2/bars_client.py::normalize_daily` applies `pd.to_numeric(...).astype("float64")`.
3. `acquisition/v2/stage_r.py::write_parquet_once` writes the frame with `df.to_parquet`.

**The provider's decimal text is not persisted anywhere in the snapshot.** The existing `acquisition/v2/crosscheck.py::decimals_of` obtains the shortest round-trip form as `Decimal(repr(float(x)))`.

**Snapshot (read-only).**
- `bars_raw/<SYMBOL>.parquet` and `bars_all/<SYMBOL>.parquet`: 26 + 26 files, all listed in the manifest.
- Column `close` has Arrow type `double` and Parquet physical type `DOUBLE`, i.e. IEEE 754 binary64. Raw and adjusted are serialized **identically**; no difference in format was found.

| | raw (`bars_raw`) | adjusted (`bars_all`) |
|---|---|---|
| values | 45,812 | 45,812 |
| null / non-finite / non-positive | 0 / 0 / 0 | 0 / 0 / 0 |
| max significant digits of shortest repr | 7 | 6 |
| decimal places of shortest repr | {0: 779, 1: 4527, 2: 40240, 3: 176, 4: 90} | {0: 484, 1: 4093, 2: 39978, 3: 1172, 4: 85} |
| `float(shortest) == stored` | 45,812 / 45,812 | 45,812 / 45,812 |
| Python `repr` vs numpy Dragon4 `format_float_positional(unique=True)` | 0 mismatches | 0 mismatches |
| exact binary64 value ≠ shortest decimal value | 43,498 | 43,996 |

Example: stored raw `105.35` has shortest form `105.35`, while its exact binary64 value is `105.349999999999994315658113919198513031005859375`.

## 3. Exact raw-close representation rule
> **The exact rational value of a stored raw close is the rational number denoted by the shortest round-trip decimal representation of the IEEE 754 binary64 value persisted in column `close` of `bars_raw/<SYMBOL>.parquet` in the immutable snapshot.** The shortest round-trip decimal representation is the decimal string with the fewest significant digits that converts back to exactly the same binary64 value under round-to-nearest-even. If several such strings exist, it is the one numerically closest to the binary64 value. Raw closes carry **no** precision term (`δ`); they remain exact, as in v2.0.2/v2.0.3.

**Rejected sources:**
- **The exact binary64 value** (the literal stored bits). It is persisted, but it is an artefact of converting the provider's decimal JSON into binary. 95 % of stored closes are not exactly representable in binary. Using the bits would make the raw side inconsistent with the adjusted side and reintroduce binary noise into exact arithmetic, the defect v2.0.4 removes.
- **The provider's JSON decimal text.** It is not persisted, so it can't be reproduced from the snapshot alone.
- **The economic market price.** It is not observable from the snapshot.

**Corroboration (not part of the rule):**
- Every stored value's shortest form has at most 7 significant digits.
- Any decimal with at most 15 significant digits converts to binary64 and back unchanged.
- So whenever the provider's JSON literal had at most 15 significant digits, the chosen value equals that literal, ignoring trailing zeros.

The rule does not depend on this property or on any provider behaviour.

## 4. Why it is deterministic
- **Single fixed input:** the source is the binary64 stored in the hash-verified immutable snapshot.
- **Unique output:** for every finite binary64 the shortest round-trip decimal is uniquely defined, with ties going to the string nearest the binary value. Conforming algorithms (Steele–White/Dragon4, Grisu-exact, Ryu, David Gay's `dtoa` mode 0) all produce it. On this snapshot, Python `repr` and numpy's independent Dragon4 agree on all 91,624 closes.
- **Exact arithmetic only:** converting a decimal string to a rational is exact. Every later operation is exact rational arithmetic, and float64 is never authoritative.
- **No adjustable parameters:** no tolerance, epsilon, or symbol, date or provider exception is involved.

## 5. Interaction with the adjusted-close representation
- **One rule for both:** the same rule applies to column `close` of `bars_all/<SYMBOL>.parquet`. This only makes explicit the source behind the existing v2.0.4 adjusted-close bullet; its meaning is unchanged.
- **The only difference:** adjusted closes keep `d_k` and `δ_k = 1/(2·10^max(d_k,2))`, taken from the same shortest form. Raw closes have no `δ`.
- **Exact factor:** `f(t) = R(t) / A(t)`, where `R` and `A` are the two exact rationals. `ρ`, `ρ_min`, `ρ_max` and the detection condition are then evaluated exactly as in v2.0.4 §1.

## 6. Must the v2.0.4 draft be amended?
**Yes.** The change is to wording only and is not made in this task; DAY-18K makes it once the protocol owner approves. It covers:
- **§1 / `exact_evaluation_rule`:** add the value source and the raw-close conversion.
- **§7 / `open_questions`:** mark OQ10 resolved, citing this artifact.
- **`implementation_impact`:** remove `blocked_by: ["OQ10"]`.

## 7. Exact proposed wording for v2.0.4 §1
Replace the bullet "Each stored adjusted close is converted from its shortest round-trip decimal representation into an exact rational number." with:

> - **Value source.** The inputs to exact evaluation are the IEEE 754 binary64 values persisted in column `close` of `bars_raw/<SYMBOL>.parquet` (raw close `r`) and `bars_all/<SYMBOL>.parquet` (adjusted close `a`) of the immutable snapshot under evaluation.
> - **Exact value.** The exact rational value of each stored raw close and of each stored adjusted close is the rational number denoted by the shortest round-trip decimal representation of that persisted binary64 value. This is the decimal string with the fewest significant digits that converts back to the identical binary64 under round-to-nearest-even, choosing the one closest to the binary64 value if several exist. The exact binary64 value itself is not used.
> - **Raw closes are exact.** They carry no precision term (unchanged from v2.0.2/v2.0.3). Adjusted closes carry `δ_k = 1/(2·10^max(d_k,2))`, with `d_k` read from the same shortest representation.
> - **Exact factor.** `f = R/A` is computed exactly from these rationals.

## 8. Do any protocol semantics change besides numerical representation?
**No.**
- The mathematical rule, the closed interval, `d_k`, `δ_k` and the degenerate check are unchanged.
- EXACT_EVALUATION_INVALID, the NUMERICAL_FALSE_POSITIVE/NEGATIVE handling and the review-record (MOOT) interaction are unchanged.
- The coincidence rules and every other section are unchanged.
- No tolerance and no symbol, date or provider exception is introduced.
- Raw closes keep their v2.0.2 status as exact observed prices.

The only addition is the explicit source and exact-value definition for `r` and `a`.

## Validation run
- Read-only profile of all raw and adjusted closes (the table in §2).
- `repr` checked against numpy Dragon4, plus the round-trip and binary-vs-shortest counts (numpy 2.5.2, pyarrow 25.0.1, Python 3.12.10).
- JSON syntax check of the companion file.
- Snapshot manifest SHA-256 confirmed unchanged afterwards.

Not done: no Stage R re-evaluation, no production code, no test suite, no network, and no review records.
