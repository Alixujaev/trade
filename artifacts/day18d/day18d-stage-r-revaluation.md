# DAY-18D — Stage R Re-evaluation under Protocol v2.0.3

| Field | Value |
|---|---|
| Starting HEAD | `d26b36ef802cf0810952b2e5c4e8e19d908b4555` |
| Protocol chain | v2.0 R1 `ba3cefe` + v2.0.1 `ed034b3` + v2.0.2 `0ebb606` + **v2.0.3 `d26b36e`** (9 protocol files verified equal to their commits) |
| Source snapshot (read only) | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`, 64 files |
| Review output (write-once, git-ignored) | `data/oos_cache/protocol_v2/stage_r/reviews/v2_0_3__stage_r_20261007T093410Z/` (9 files) — `evaluation.json` `c0a0f240da77aec83798cc402689ce5b149ce6e6df6b9eceac3eb6ba18dd85b7`, `manifest.json` `8999961a059c73c5dbacd33f127a57092019e3a33ed1938108ee2fc81c4dabed`, `review_records.json` `140f7df96e5ed2142fbca0f4bf876815c603bbb191d8d44692b358f3fb1055f6` |
| Evaluated | 2026-10-07T10:56:37Z, offline (sockets refused), code SHA-256 per module recorded in `evaluation.json` → `provenance` |
| **Final status** | **BLOCKED** — `usable_for_research = false` |

**Scope.** Implementation of v2.0.3 and one offline re-evaluation. No acquisition, network, holdout/forward access, signal, return, TR index, backtest, gate or metric. Only counts, dates, precision histograms and classifications are reported. **The precision rule was implemented and tested before the single real run and was not changed afterwards.**

## 1. Integrity
- Snapshot: manifest SHA and all 63 entries verified before and after (unchanged); independent `sha256sum` of all 64 files against the pre-DAY-18B listing — **all match**.
- Existing v2.0.2 review output `reviews/v2_0_2__stage_r_20261007T093410Z/` (8 files): hashed before/after by the run and independently — **unchanged**.
- Leakage assertion: 1,513 event/ex dates checked in all outputs; none after 2022-12-30.

## 2. Review records (v2.0.3 item 2)
- Directory `artifacts/reviews/stage_r/` **does not exist**: **0 records present, 0 applied, 0 invalid**.
- **No review record was created and no review decision was made by the agent.** Every item that needs a record therefore remains BLOCKING.

## 3. Rule applied (v2.0.3 item 1, exactly)
`d_k` = displayed decimals of each stored adjusted close; `δ_k = ½·10^−max(d_k, 2)`; `ρ = f_k/f_p`; `ρ_min = ρ·(a_k/(a_k+δ_k))·((a_p−δ_p)/a_p)`; `ρ_max = ρ·(a_k/(a_k−δ_k))·((a_p+δ_p)/a_p)`; change ⇔ `1 ∉ [ρ_min, ρ_max]`; degenerate (`a−δ ≤ 0` or non-finite) ⇒ BLOCKING. Coincidence rules, no precision exemption, split 0.1 %, first-session rule — unchanged. No symbol-specific branch.

## 4. Per-symbol results (26 symbols, 1,761 pairs each)

| Symbol | Status | Precision histogram (values per d_k) | Detected | Expected events | Matched | Unexplained | Unconfirmed | Splits | First-session |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | PASS | 0:9 1:168 2:1585 | 29 | 29 | 29 | 0 | 0 | ok | 0 |
| ADBE | PASS | 0:29 1:196 2:1534 3:3 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| AMAT | PASS | 0:23 1:170 2:1569 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| AMD | PASS | 0:21 1:179 2:1529 3:27 4:6 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| **AMZN** | **BLOCKING** | 0:29 1:189 2:1544 | 2 | 1 | 1 | **1** (2016-02-22) | 0 | ok | 0 |
| AVGO | PASS | 0:18 1:151 2:1573 3:20 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| COST | PASS | 0:16 1:141 2:1605 | 30 | 30 | 30 | 0 | 0 | — | 0 |
| CRM | PASS | 0:14 1:167 2:1581 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| CSCO | PASS | 0:13 1:159 2:1590 | 27 | 27 | 27 | 0 | 0 | — | 1 |
| GOOGL | PASS | 0:17 1:142 2:1603 | 1 | 1 | 1 | 0 | 0 | ok | 0 |
| INTC | PASS | 0:25 1:136 2:1601 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| JNJ | PASS | 0:19 1:178 2:1565 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| JPM | PASS | 0:21 1:163 2:1578 | 27 | 27 | 27 | 0 | 0 | — | 1 |
| KO | PASS | 0:13 1:166 2:1583 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| META | PASS | 0:14 1:152 2:1596 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| MSFT | PASS | 0:22 1:146 2:1594 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| MU | PASS | 0:20 1:162 2:1565 3:15 | 6 | 6 | 6 | 0 | 0 | — | 0 |
| **NFLX** | **BLOCKING** | 0:23 1:146 2:1456 3:137 | 1 | 0 | 0 | **1** (2018-11-29) | 0 | — | 0 |
| **NVDA** | **BLOCKING** | 0:3 1:63 2:651 3:966 4:79 | 19 | 29 | 19 | 0 | **10** | ok | 0 |
| ORCL | PASS | 0:15 1:147 2:1600 | 27 | 27 | 27 | 0 | 0 | — | 1 |
| PEP | PASS | 0:12 1:170 2:1580 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| QCOM | PASS | 0:17 1:150 2:1595 | 29 | 29 | 29 | 0 | 0 | — | 0 |
| SPY | PASS | 0:18 1:144 2:1600 | 26 | 26 | 26 | 0 | 0 | — | 0 |
| TSLA | PASS | 0:30 1:160 2:1568 3:4 | 2 | 2 | 2 | 0 | 0 | ok, ok | 0 |
| WMT | PASS | 0:20 1:172 2:1570 | 28 | 28 | 28 | 0 | 0 | — | 0 |
| XOM | PASS | 0:23 1:176 2:1563 | 28 | 28 | 28 | 0 | 0 | — | 0 |

**23 PASS, 3 BLOCKING.** No precision-degenerate pair and no uncheckable event in any symbol; all 6 split checks pass.

### 4.1 Facts about the previous blockers (no interpretation added to the rule)
- **AVGO, MU, TSLA:** BLOCKING under v2.0.2 (1,283–1,423 unexplained changes) → **PASS** under v2.0.3 (all events matched, 0 unexplained).
- **NFLX:** v2.0.2: 1,315 unexplained → v2.0.3: **1 unexplained change on 2018-11-29**; NFLX has no retained corporate-action event in Stage R.
- **NVDA:** v2.0.2: 1,435 unexplained + 1 unconfirmed → v2.0.3: **0 unexplained, 10 unconfirmed cash dividends** (ex 2018-05-23, 2019-08-28, 2020-09-01, 2020-12-03, 2021-03-09, 2021-06-09, 2021-12-01, **2022-03-02**, 2022-06-08, 2022-09-07). Under the per-value bound these dividends produce no change outside the rounding interval. This is the situation recorded as v2.0.2 OQ1 (no precision exemption) — v2.0.3 grants none, so each is an UNCONFIRMED_EVENT item.
- **AMZN 2016-02-22:** still **unexplained** under v2.0.3 (its values carry ≤ 2 decimals, so the bound is unchanged from v2.0.2).
- The NVDA 2022-03-02 item is **separate** from the NVDA←MLNX merger review, which is RESOLVED by the frozen review rule (acquirer, no open unexplained change on 2020-04-27).

## 5. Identity
496 records: 493 assigned, 1 foreign (META→METV, RESOLVED_EXCLUDED), **2 IDENTITY_UNVERIFIED** — CRM←WORK (2021-07-21) and AMD←XLNX (2022-02-14) — **BLOCKING** (no anchor, no committed record), 0 conflicts.

## 6. SPY
26 detected changes, 26 expected events, 26 matched, 0 unexplained, 0 unconfirmed → **PASS / RESOLVED** (same code path as every symbol).

## 7. First-session events
FIRST_SESSION_UNTESTABLE (non-blocking): CSCO, JPM, ORCL cash dividends dated 2016-01-04.

## 8. Blocker inventory (14 items)
| Category | Count | Items |
|---|---|---|
| IDENTITY_UNVERIFIED | 2 | CRM←WORK 2021-07-21; AMD←XLNX 2022-02-14 |
| UNRESOLVED — UNEXPLAINED_CHANGE | 2 | AMZN 2016-02-22; NFLX 2018-11-29 |
| UNRESOLVED — UNCONFIRMED_EVENT | 10 | NVDA cash dividends listed in §4.1 |
| BLOCKING (other) | 0 | — |

Category counts over all review items: PASS 5 (4 RESOLVED + 1 RESOLVED_EXCLUDED), FIRST_SESSION_UNTESTABLE 3, IDENTITY_UNVERIFIED 2, UNRESOLVED 12, BLOCKING 0.

## 9. Final status
**BLOCKED** (`usable_for_research = false`). All 14 blockers require committed, human-decided review records under v2.0.3 items 3–5 (or, for identity, a same-provider anchor). None exists.

## 10. Tests
- Focused: `tests/test_day18d_v203.py` 28 + `tests/test_day18b_v202.py` 15 + `tests/test_day18_stage_r.py` 23 = **66 passed**.
- `tests/test_day18b_v202.py`: three v2.0.2-specific calls now pin `precision_model="v2.0.2"` / `protocol="v2.0.2"`; their assertions are unchanged.
- One DAY-18D test fixture was corrected before the real run (a constructed price move larger than intended); the assertion was unchanged.
- Full suite: **1249 passed**, 0 failed (24 min 26 s; 28 warnings, the same third-party deprecation warnings as previous runs).

## 11. Not done
No review record created or decided; no acquisition or network; no change to the snapshot, the v2.0.2 review output, or any protocol artifact; no research computation; no push.
