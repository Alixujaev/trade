# DAY-18K — Protocol v2.0.4 Exact Evaluation and Offline Stage R Re-evaluation

| Field | Value |
|---|---|
| Task | DAY-18K: finalize v2.0.4 with approved OQ10, implement exact arithmetic, offline Stage R re-evaluation |
| Starting HEAD | `75c914f5226685f331cbb2e56a9c4db7c52b24b9` |
| HEAD at evaluation (before implementation commit) | `71dbfa226e66c7c664079a98a84c45914fc4ece8` (v2.0.4 amendment commit) |
| Protocol | **2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4**: R1 `ba3cefe`, v2.0.1 `ed034b3`, v2.0.2 `0ebb606`, v2.0.3 `d26b36e`, **v2.0.4 `71dbfa2`**. All 11 protocol files verified against their commits. |
| OQ10 | **RESOLVED** (protocol-owner approved). The authoritative value is the shortest round-trip decimal of the persisted parquet DOUBLE (`bars_raw/<SYMBOL>.parquet` and `bars_all/<SYMBOL>.parquet`, column `close`). Ties go to the decimal nearest the binary64. Raw closes carry no δ. `f = R/A` is exact. |
| Source snapshot | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/`. 64 files; manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`; 63/63 entries verified; 0 writable; tree SHA-256 `c5d78635…dc54590` before = after. |
| Output (new, write-once) | `data/oos_cache/protocol_v2/stage_r/reviews/v2_0_4__stage_r_20261007T093410Z/`. Output manifest SHA-256 `755c905e0adae6c7cac924aa8146384defe7053784b526675e7b51d714f6d698`; `evaluation.json` `9c0e4d85afdaa344ea6533cddd14f29453909337cb0ad26031a9af325e62d33f`. |
| **Final status** | **USABLE_FOR_RESEARCH** (`usable_for_research = true`) |
| Blockers | **v2.0.3 (DAY-18G): 2 → v2.0.4 (DAY-18K): 0** |
| Network / data / OOS | Offline (sockets refused), 0 network calls, no acquisition, no holdout or forward-OOS access, no research/backtest |
| Review records | 14 found, 12 applied, **2 MOOT**, 0 invalid. **None created or modified** (no git diff against HEAD). |

## 1. Implementation (v2.0.4)
- **`crosscheck.py`: `precision_model="v2.0.4"`.**
  - `shortest_decimal` uses `repr` and asserts that the result round-trips.
  - `exact_value` converts that decimal to a `Fraction`. Non-finite, non-positive or non-convertible values raise `ExactEvaluationInvalid`.
  - `exact_delta` = `1/(2·10^max(d,2))`. Raw closes carry no δ.
  - `detect_changes_exact` evaluates `NOT (ρ_min ≤ 1 ≤ ρ_max)` exactly and is authoritative.
  - The float64 `detect_changes` is kept as a diagnostic only.
  - Numerical false positives and negatives, float-degeneracy disagreements and invalid pairs are recorded as dates only.
  - The 0.1 % split check is unchanged; its exact agreement is recorded as a diagnostic.
  - `Decimal.from_float` is never used, the binary64 value never enters protocol arithmetic, and there is no symbol or date branch.
- **`review_records.py`:**
  - v2.0.3 records are accepted under v2.0.4 (`accepted_protocol_versions`).
  - A record whose *only* defect is that its item no longer exists, while that item is open under the same-run v2.0.3 evaluation, is **MOOT** rather than INVALID.
  - A key that was never open stays INVALID.
- **`reviews.py`:** adds the v2.0.4 categories MOOT, NUMERICAL_FALSE_POSITIVE (non-blocking), NUMERICAL_FALSE_NEGATIVE (audit item; the exact detection goes through coincidence) and EXACT_EVALUATION_INVALID (BLOCKING). v2.0.3 output is unchanged.
- **`reevaluate.py`:**
  - Adds `--protocol v2.0.4`; the default stays v2.0.3.
  - The protocol chain includes `71dbfa2`.
  - Output goes to `v2_0_4__<snapshot_id>`.
  - An in-memory v2.0.3 reference evaluation reproduces DAY-18D's `crosscheck.json` byte for byte (`98f3efd0…`) and defines the MOOT keys.
- **`contract.py`:** adds `AMENDMENT_004_COMMIT/FILES` and `PROTOCOL_VERSION_004`.

## 2. Tests
- **New** `tests/test_day18k_v204.py`: **31 passed**. Covers:
  - the exact boundary `ρ_max = 1`
  - outside and interior intervals
  - AMZN- and NFLX-style false positives
  - exact authority over float64
  - false-positive and false-negative classification (a constructed false negative: exact `ρ_max = 0.99999999999999989…`, float64 `1.0`)
  - invalid values: NaN, inf, 0, negative, non-convertible
  - the degenerate rule
  - raw and adjusted representation determinism
  - round-trip to the DOUBLE
  - exact `f = R/A` and δ, and no raw δ
  - the nearest-candidate tie-break property against an independent Dragon4 implementation (no genuine equidistant tie was found by a bounded search)
  - MOOT vs INVALID
  - v2.0.3 records valid under v2.0.4
  - EXACT_EVALUATION_INVALID blocking
  - v2.0.3 mode unchanged
  - no symbol or date branch
- **Focused:** **97 passed** (test_day18k_v204 31, test_day18d_v203 28, test_day18b_v202 15, test_day18_stage_r 23).
- **Full suite:** **1280 passed, 0 failed** (18 min 08 s; 28 third-party deprecation warnings, as before).

## 3. Exact-evaluation result (all 26 symbols, 45,786 pairs)
| Check | Result |
|---|---|
| NUMERICAL_FALSE_POSITIVE | **2**: AMZN (2016-02-19 → 2016-02-22), NFLX (2018-11-28 → 2018-11-29) |
| NUMERICAL_FALSE_NEGATIVE | **0** |
| EXACT_EVALUATION_INVALID | **0** |
| Float/exact degeneracy disagreements | 0 |
| Split-check exact/float disagreements | 0 |
| v2.0.3 open review items → v2.0.4 open review items | 14 → 12 (the two UNEXPLAINED_CHANGE items disappeared) |

No other symbol's classification changed. The identity, events, validation and data-quality outputs are byte-identical to DAY-18D/18G. Only `crosscheck.json` differs, because of the v2.0.4 fields and the two removed detections.

## 4. Key evidence — AMZN 2016-02-22 and NFLX 2018-11-29
Source: `bars_raw/<SYM>.parquet` and `bars_all/<SYM>.parquet`, column `close` (read-only).

| | AMZN (p 2016-02-19, k 2016-02-22) | NFLX (p 2018-11-28, k 2018-11-29) |
|---|---|---|
| Persisted raw p / k (binary64) | `0x1.0b73333333333p+9` / `0x1.17c0000000000p+9` | `0x1.1aa6666666666p+8` / `0x1.20c0000000000p+8` |
| Exact raw p / k (shortest decimal) | 534.9 / 559.5 | 282.65 / 288.75 |
| Persisted adjusted p / k (binary64) | `0x1.abd70a3d70a3dp+4` / `0x1.bfae147ae147bp+4` | `0x1.c428f5c28f5c3p+4` / `0x1.ce147ae147ae1p+4` |
| Exact adjusted p / k | 26.74 / 27.98 | 28.26 / 28.88 |
| d_p, d_k / δ_p, δ_k | 2, 2 / 1/200, 1/200 (raw: none) | 2, 2 / 1/200, 1/200 (raw: none) |
| Exact f_p / f_k | 26745/1337 / 27975/1399 | 28265/2826 / 28875/2888 |
| Exact ρ | 2493505/2494417 ≈ 0.99963438350524391070 | 8160075/8162932 ≈ 0.99965000320963104924 |
| Exact ρ_min | 9972155/9979451 ≈ 0.99926889765779700707 | 32634525/32657381 ≈ 0.99930012758830844396 |
| **Exact ρ_max** | **1** (exactly) | **1** (exactly) |
| Exact detection | **NO** (1 ∈ [ρ_min, ρ_max], endpoint equality) | **NO** |
| float64 diagnostic | ρ_max = 0.9999999999999998 → DETECTION | ρ_max = 0.9999999999999999 → DETECTION |
| **Final classification** | **NUMERICAL_FALSE_POSITIVE** (non-blocking). The UNEXPLAINED_CHANGE item no longer exists. DAY-18F record `amzn-20160222-20261007` (UNRESOLVED) is **MOOT**. | **NUMERICAL_FALSE_POSITIVE** (non-blocking). The item no longer exists. Record `nflx-20181129-20261007` (UNRESOLVED) is **MOOT**. |

## 5. Stage R status
| | DAY-18G (v2.0.3) | DAY-18K (v2.0.4) |
|---|---|---|
| Blocking items | 2 (AMZN, NFLX UNRESOLVED) | **0** |
| Status counts | RESOLVED 16, RESOLVED_EXCLUDED 1, FIRST_SESSION_UNTESTABLE 3, BLOCKING 2 | RESOLVED 16, RESOLVED_EXCLUDED 1, FIRST_SESSION_UNTESTABLE 3, BLOCKING 0, HARD_FAIL 0, MOOT 2, NUMERICAL_FALSE_POSITIVE 2, NUMERICAL_FALSE_NEGATIVE 0 |
| Final | BLOCKED | **USABLE_FOR_RESEARCH** |

- **Remaining blockers:** none.
- **MOOT:** `amzn-20160222-20261007`, `nflx-20181129-20261007`. They stay in history unchanged.
- **NVDA:** remains mechanically blocking (10 unconfirmed dividends), and each dividend is resolved by its committed DAY-18F `EVENT_RETAINED` record, as in DAY-18G.
- **CRM←WORK, AMD←XLNX:** resolved by their committed `SAME_ENTITY` records. NVDA←MLNX is resolved acquirer-side.
- **Not affected:** universe, timeline, strategies, execution, accounting, benchmarks, costs, Gates A/B/C, C1/C3/C4, the first-session rule, the 0.1 % split tolerance, identity rules, and review-record semantics.

## 6. Integrity and reproducibility
1. **Snapshot:** the manifest SHA-256 is unchanged and all 64 files are unchanged. This was checked by the run (before and after) and independently against a pre-run baseline.
2. **Earlier outputs:**
   - The v2.0.2 output is unchanged (7/7 self-manifest).
   - The v2.0.3 output is unchanged (8/8).
   - The DAY-18G output is unchanged (8/8 and 9/9 against the DAY-18G recorded hashes).
   - All three trees are identical to the pre-run baseline.
3. **Review records:** all 14 unchanged, no git diff, none created.
4. **Offline:** socket connections were refused and 0 network calls were made. No holdout or OOS path was touched.
5. **Write-once:** a second run into the same directory was refused (`FileExistsError`). Output files are read-only.
6. **Determinism: PASS.** A second offline run into a scratchpad directory produced 7 byte-identical files. `evaluation.json` and `manifest.json` are identical after removing the timestamp, provenance and guard-list fields.

## 7. Not done
No acquisition and no network. No holdout or forward-OOS access. No research, backtest, signal or return. No review record created or modified. No snapshot modification. No push.
