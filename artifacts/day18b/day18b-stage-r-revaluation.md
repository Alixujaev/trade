# DAY-18B — Stage R Re-evaluation under Protocol v2.0.2

| Field | Value |
|---|---|
| Date | 2026-10-07 (evaluated 2026-10-07T10:07:53Z) |
| Protocol chain | v2.0 R1 `ba3cefe` + v2.0.1 `ed034b3` + v2.0.2 `0ebb606` (7 protocol files verified equal to their commits) |
| v2.0.2 amendment SHA-256 | md `0ce87282112c4407a56a868c462f8b39810597437d4e1ed240922ba4ce203e8e`; json `1b182ba1d582ffc921051db2dd278ffd16b097a6e8f7896c0ee8dfd2a97193d4` |
| Source snapshot | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/` (read only) |
| Source manifest SHA-256 | `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` |
| Review output (write-once, git-ignored) | `data/oos_cache/protocol_v2/stage_r/reviews/v2_0_2__stage_r_20261007T093410Z/` — `evaluation.json` SHA-256 `b62c5bcee144533920de8afb9fefeb049d556f2509247feaf124ac2b683360f5`, review `manifest.json` `387e83339e11762b4c3e71f6df81bbefee330168457180e95d6d0f1708abfde7` |
| Code | `acquisition/v2/` as committed with this report (SHA-256 of every module recorded in `evaluation.json` → `provenance`; run from HEAD `0ebb606` with these files uncommitted, verified equal to the committed blobs after the commit) |
| **Final status** | **B — BLOCKED** (`usable_for_research = false`) |

**Scope.** Offline data validation only: no network call (sockets refused for the run), no acquisition, no holdout/forward data, no signal, TR index, return, backtest or metric. No price, factor or rate value is reported; only counts, dates, `d`, `δ` and classifications.

## 1. Snapshot immutability — PASS
- Pre-check: manifest SHA-256 equals the expected value; all 63 manifest entries verify; no unlisted file; 64 files on disk (63 entries + `manifest.json`).
- Post-check: identical hash tree after the run (`tree_sha256_before == tree_sha256_after`, `unchanged = true`).
- Independent check: `sha256sum` of all 64 files against a listing taken before any DAY-18B code change — all match.
- Output written only to the separate `reviews/` directory.
- Correction to DAY-18 report: it stated "63 persisted files (… incl. manifest)"; the snapshot holds **64** files (63 manifest entries + `manifest.json`).

## 2. Rule applied (v2.0.2, exactly)
Per symbol: `d` = max decimal places of stored `adjustment=all` closes (shortest round-trip representation), `δ = 0.5·10^−d`; raw closes exact; for consecutive common sessions `ρ = f_k/f_p`, `ρ_min = ρ·(a_k/(a_k+δ))·((a_p−δ)/a_p)`, `ρ_max = ρ·(a_k/(a_k−δ))·((a_p+δ)/a_p)`; **change detected ⇔ 1 ∉ [ρ_min, ρ_max]**; `a−δ ≤ 0` → PRECISION_DEGENERATE (BLOCKING). Every detected change needs an event in `(p, k]`; every event needs a detected change (no exemption); split magnitude within 0.1 %. Events with `ex_date ≤` first common session → FIRST_SESSION_UNTESTABLE (non-blocking). No symbol-specific branch (SPY identical).

## 3. Cross-check results (26 symbols)

| Symbol | Status | d | δ | Detected | Expected events | Matched | Unexplained | Unconfirmed | Splits | First-session |
|---|---|---|---|---|---|---|---|---|---|---|
| AAPL | OK | 2 | 0.005 | 29 | 29 | 29 | 0 | 0 | ok | 0 |
| ADBE | OK | 3 | 0.0005 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| AMAT | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| AMD | OK | 4 | 5e-05 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| **AMZN** | **BLOCKING** | 2 | 0.005 | 2 | 1 | 1 | **1** (2016-02-22) | 0 | ok | 0 |
| **AVGO** | **BLOCKING** | 3 | 0.0005 | 1428 | 28 | 28 | **1400** | 0 | — | 0 |
| COST | OK | 2 | 0.005 | 30 | 30 | 30 | 0 | 0 | — | 0 |
| CRM | OK | 2 | 0.005 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| CSCO | OK | 2 | 0.005 | 27 | 27 | 27 | 0 | 0 | — | 1 |
| GOOGL | OK | 2 | 0.005 | 1 | 1 | 1 | 0 | 0 | ok | 0 |
| INTC | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| JNJ | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| JPM | OK | 2 | 0.005 | 27 | 27 | 27 | 0 | 0 | — | 1 |
| KO | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| META | OK | 2 | 0.005 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| MSFT | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| **MU** | **BLOCKING** | 3 | 0.0005 | 1429 | 6 | 6 | **1423** | 0 | — | 0 |
| **NFLX** | **BLOCKING** | 3 | 0.0005 | 1315 | 0 | 0 | **1315** | 0 | — | 0 |
| **NVDA** | **BLOCKING** | 4 | 5e-05 | 1463 | 29 | 28 | **1435** | **1** (2022-03-02) | ok | 0 |
| ORCL | OK | 2 | 0.005 | 27 | 27 | 27 | 0 | 0 | — | 1 |
| PEP | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| QCOM | OK | 2 | 0.005 | 29 | 29 | 29 | 0 | 0 | — | 0 |
| SPY | OK | 2 | 0.005 | 26 | 26 | 26 | 0 | 0 | — | 0 |
| **TSLA** | **BLOCKING** | 3 | 0.0005 | 1285 | 2 | 2 | **1283** | 0 | ok, ok | 0 |
| WMT | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| XOM | OK | 2 | 0.005 | 28 | 28 | 28 | 0 | 0 | — | 0 |

**20 OK, 6 BLOCKING.** No PRECISION_DEGENERATE pair and no uncheckable event in any symbol. All 6 split-magnitude checks pass.

### 3.1 Diagnosis of the 6 blocking symbols (structural evidence, no values)
- **AVGO, MU, NFLX, TSLA (d = 3), NVDA (d = 4):** the stored `all` closes do not share one precision. Decimal-place histograms (values per number of decimals): AVGO {0:18, 1:151, 2:1573, 3:20}; MU {0:20, 1:162, 2:1565, 3:15}; NFLX {0:23, 1:146, 2:1456, 3:137}; TSLA {0:30, 1:160, 2:1568, 3:4}; NVDA {0:3, 1:63, 2:651, 3:966, 4:79}. v2.0.2 sets `d` to the **maximum** decimals, so a minority of finer values makes `δ` 10–100× smaller than the rounding actually applied to most values; ordinary rounding jitter then exceeds the bound. This is the **fail-safe outcome anticipated by v2.0.2 OQ2** (provider rounds more coarsely than `d` implies) — a BLOCKING result, not a false pass. Resolving it requires a protocol decision (e.g. how `d` relates to mixed per-value precision); **DAY-18B does not change the rule.**
- **AMZN 2016-02-22:** both adjusted values have 2 decimals (`d = 2` for the whole series, histogram {0:29, 1:189, 2:1544}); the ratio change lies in the 1e-4–1e-3 bucket, beyond the rounding interval; no AMZN event exists. Unexplained → BLOCKING. Cause UNKNOWN (provider data irregularity or a rounding/precision effect not captured by the rule).
- **NVDA 2022-03-02:** a retained NVDA cash dividend with no detected change at its ex-date → unconfirmed → BLOCKING (no precision exemption under v2.0.2). Cause UNKNOWN; NVDA's series is in any case dominated by the precision issue above.
- Contrast: ADBE (d = 3) and AMD (d = 4) pass because their `all` series equals raw (no adjustment to round), so `f` is constant.

## 4. First-session events (v2.0.2 item 2)
`FIRST_SESSION_UNTESTABLE` (non-blocking, listed, excluded from TR/accounting): **CSCO cash_dividend 2016-01-04, JPM cash_dividend 2016-01-04, ORCL cash_dividend 2016-01-04** — exactly the three DAY-18 events; each symbol's first common session is 2016-01-04. No other event qualified.

## 5. Identity (v2.0.1 C2 + v2.0.2 rule 4a)
496 records: 493 assigned (209 by CUSIP, 284 ticker-only), **1 foreign** (META→METV, RESOLVED_EXCLUDED), **2 IDENTITY_UNVERIFIED** (CRM←WORK 2021-07-21; AMD←XLNX 2022-02-14 — **BLOCKING**, not auto-resolved), 0 unassigned, 0 conflicts. Alias FB→META.

## 6. Review classification
| Item | Status |
|---|---|
| identity-unverified stock_and_cash_merger CRM←WORK (2021-07-21) | **BLOCKING** (rule 4a; needs same-provider anchor or committed reviewer record) |
| identity-unverified stock_merger AMD←XLNX (2022-02-14) | **BLOCKING** (same) |
| raw/all cross-check AMZN, AVGO, MU, NFLX, NVDA, TSLA | **BLOCKING** (§3) |
| cash_merger NVDA←MLNX (2020-04-27) | RESOLVED by the frozen review rule (acquirer; no unexplained change on that date) — **caveat:** NVDA's cross-check is itself BLOCKING, so NVDA remains blocked regardless |
| cash_merger CSCO←ACIA (2021-03-01) | RESOLVED |
| cash_merger MSFT←NUAN (2022-03-04) | RESOLVED |
| name_change FB→META (2022-06-09) | RESOLVED (pure rename, clean date) |
| name_change META→METV | RESOLVED_EXCLUDED (foreign entity) |
| CSCO / JPM / ORCL dividends 2016-01-04 | FIRST_SESSION_UNTESTABLE (non-blocking) |
| structural validation (52 series) | OK (0 HARD_FAIL, 0 BLOCKING) |
| complete vs all | no difference |

Counts: RESOLVED 4, RESOLVED_EXCLUDED 1, FIRST_SESSION_UNTESTABLE 3, **BLOCKING 8**, HARD_FAIL 0.

## 7. SPY
Evaluated by the same code path as every symbol: `d = 2`, 26 detected changes, 26 expected events, 26 matched, 0 unexplained, 0 unconfirmed → **RESOLVED** under v2.0.2 (no outside quarterly-schedule assumption used).

## 8. Final status
**BLOCKED.** Blocking reviews: CRM←WORK and AMD←XLNX (identity); cross-check AMZN, AVGO, MU, NFLX, NVDA, TSLA. Stage R is **not** usable for research.

## 9. Tests
- `tests/test_day18b_v202.py` (15) + `tests/test_day18_stage_r.py` (23, three assertions renamed to v2.0.2 field names) — **38 passed**.
- Full suite: **1221 passed**, 0 failed (23 min 35 s), run before the commit.

## 10. Not done
No acquisition, no network access, no snapshot modification, no change to v2.0.2 or any tolerance, no research computation, no push.
