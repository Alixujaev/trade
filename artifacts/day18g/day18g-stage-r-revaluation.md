# DAY-18G — Stage R Re-evaluation with the DAY-18F Review Records (v2.0.3)

| Field | Value |
|---|---|
| Starting HEAD | `c36b673609e1f238dd52e15fcc9b5503e108468f` (DAY-18F review records) |
| Protocol chain | v2.0 R1 `ba3cefe` + v2.0.1 `ed034b3` + v2.0.2 `0ebb606` + v2.0.3 `d26b36e` (9 protocol files verified equal to their commits) |
| Source snapshot (read only) | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/`, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`, 64 files |
| Review records | `artifacts/reviews/stage_r/` — 14 found, **14 applied, 0 invalid, 0 superseded**; all tracked and identical to HEAD |
| Review output (write-once, read-only, git-ignored, not committed) | `data/oos_cache/protocol_v2/stage_r/reviews/v2_0_3__stage_r_20261007T093410Z__day18g/` (9 files) — `evaluation.json` `09dab92f31bdbd0854a7cec10ed0c945b7546229be9ac56272801a0cdc99a829`, `manifest.json` `a1c9ea1283ba46b6e3a395cc84a1794eeae205bb5ed96fc57eab9e49aaadd9ea`, `reviews.json` `228baeef8b43952068d961631345acd005f92f6305482e7c5490e00a7b52ac60`, `review_records.json` `f34a045efd4a16cffc35431596337cbbe488b4a4daac3c908c96ccf9989d6a43` |
| Evaluated | 2026-10-07T12:23:49Z, offline (socket connections refused; `network_calls` 0) |
| **Final status** | **BLOCKED** — `usable_for_research = false` — **2 blockers** (DAY-18D: 14) |

**Scope.** One offline run of the frozen v2.0.3 implementation (`acquisition/v2/reevaluate.reevaluate`, protocol `v2.0.3`). The DAY-18F records were consumed by the production loader (`acquisition/v2/review_records.load`). No code, rule, protocol file or review record was changed. No acquisition, network, holdout/forward access, signal, return, TR index, backtest or metric.

**Output directory.** `reevaluate.output_dir_for()` always returns `reviews/v2_0_3__<snapshot_id>/`, which DAY-18D already occupies; the run is write-once and would refuse. A session-scratchpad wrapper (not a repository file) did exactly what `reevaluate.main()` does (socket guard, `code_identity()` provenance, `reevaluate(...)`), except that `output_dir_for()` returned the default name + `__day18g`. All other guards stayed active: snapshot verification before and after, the record loader, write-once, the leakage assertion, and the before/after hashing of the other review outputs. The `acquisition/v2` module SHA-256s recorded in provenance are **identical** to DAY-18D's.

## 1. Integrity
- Snapshot: verified by the run (manifest + all entries, before and after; tree hash unchanged) and independently (`sha256sum` 64/64). **Unchanged.**
- DAY-18D v2.0.3 output (9/9) and v2.0.2 output (8/8): unchanged (run guard + independent check).
- DAY-18E dossier: unchanged (7/7) and still untracked.
- Review records: 14 files, unchanged, worktree equal to committed blobs.
- Leakage assertion: 1,513 event/ex dates checked; none after 2022-12-30.

## 2. Mechanical layer vs DAY-18D — invariant
`crosscheck.json`, `identity.json`, `events_normalised.json`, `validation.json` and `data_quality_comparison.json` are **byte-identical** to DAY-18D. Per-symbol summaries (precision histograms, detected/expected/matched counts, unexplained/unconfirmed counts, split checks, first-session events) are identical. Precision rule, split tolerance, first-session handling and coincidence rules are unchanged. All 8 review items without a record are identical to DAY-18D. Only `reviews.json`, `review_records.json`, `evaluation.json` and `manifest.json` differ — the review-resolution layer.

Note: `identity.json` still counts `identity_unverified: 2`; that is the mechanical identity result (no same-provider anchor). Resolution by a committed record happens in the review layer (`reviews.json`).

## 3. Items with committed review records

| Item | DAY-18D | DAY-18G | Record (decision) | Reason (verbatim) |
|---|---|---|---|---|
| CRM←WORK `stock_and_cash_mergers` 2021-07-21 | BLOCKING / IDENTITY_UNVERIFIED | **RESOLVED / PASS** | `crm-work-20261007` (SAME_ENTITY) | committed review SAME_ENTITY; processed as frozen §3.4 review item (acquirer-side, clean date) |
| AMD←XLNX `stock_mergers` 2022-02-14 | BLOCKING / IDENTITY_UNVERIFIED | **RESOLVED / PASS** | `amd-xlnx-20261007` (SAME_ENTITY) | same as above |
| AMZN unexplained change 2016-02-22 | BLOCKING / UNRESOLVED | **BLOCKING / UNRESOLVED** | `amzn-20160222-20261007` (UNRESOLVED) | v2.0.3 item 3: unexplained change without an applicable committed review record |
| NFLX unexplained change 2018-11-29 | BLOCKING / UNRESOLVED | **BLOCKING / UNRESOLVED** | `nflx-20181129-20261007` (UNRESOLVED) | same as above |
| NVDA cash dividends ×10 (below) | BLOCKING / UNRESOLVED | **RESOLVED / PASS** | `nvda-div-<date>-20261007` (EVENT_RETAINED) | committed review EVENT_RETAINED (mechanical evidence check passed) |

**CRM←WORK and AMD←XLNX.** The records were not simply dropped. `reviews.classify` set them RESOLVED only after the frozen §3.4 condition held: a merger type, the Stage R entity is the **acquirer**, and there is no open unexplained change for the entity on the event date (`clean_on`). CRM and AMD have 0 detected changes in the cross-check, so both dates are clean. **No acquirer-side review condition remains**, and neither item caused a new blocker. CRM and AMD remain PASS in the cross-check (0 detected / 0 expected), and no event was excluded (`events_excluded_by_review = []`).

**AMZN / NFLX.** The UNRESOLVED records are applied (they appear in `review_record`), but under v2.0.3 item 3 only PROVIDER_ADJUSTMENT_ARTIFACT resolves an unexplained change, so they remain **BLOCKING**. The reason text says "without an *applicable* … record" because the frozen code uses one fallback message for both "no record" and "UNRESOLVED record"; the record is attached to the item.

**NVDA — all ten EVENT_RETAINED records consumed by the loader:**

| Ex-date | CA id | Record | Record blob SHA-256 | DAY-18G |
|---|---|---|---|---|
| 2018-05-23 | `4be70358-dc7e-429c-ad3a-6b56e5c29ca0` | `nvda-div-20180523-20261007` | `6249980c…` | RESOLVED |
| 2019-08-28 | `08cdc20f-26c2-47bd-a6d4-3b10ca86185c` | `nvda-div-20190828-20261007` | `ad62fdbc…` | RESOLVED |
| 2020-09-01 | `391f36bb-8a9c-4b04-85fc-2661d20f9ae5` | `nvda-div-20200901-20261007` | `7a9ca338…` | RESOLVED |
| 2020-12-03 | `c94296da-7080-4fe3-b101-e41e06f2cd09` | `nvda-div-20201203-20261007` | `7d3425ee…` | RESOLVED |
| 2021-03-09 | `d80fa14c-6eb4-418f-b003-f5775322eba3` | `nvda-div-20210309-20261007` | `3e81d07b…` | RESOLVED |
| 2021-06-09 | `d1a013e0-aea6-46ec-b844-d7a546ace337` | `nvda-div-20210609-20261007` | `d5c4c980…` | RESOLVED |
| 2021-12-01 | `ef9b148b-f031-4c05-8faf-4814f099b11d` | `nvda-div-20211201-20261007` | `98fce0f6…` | RESOLVED |
| 2022-03-02 | `13ca6ae3-efe8-461a-af9c-fa2490d56d9c` | `nvda-div-20220302-20261007` | `89a24809…` | RESOLVED |
| 2022-06-08 | `4ac972c2-d010-4c59-9bc5-3804d580e957` | `nvda-div-20220608-20261007` | `eca834e0…` | RESOLVED |
| 2022-09-07 | `90e63976-7fbe-41e6-a747-98da5ec27d03` | `nvda-div-20220907-20261007` | `bb064736…` | RESOLVED |

Full blob hashes are in the JSON report. The NVDA←MLNX merger review (2020-04-27) remains RESOLVED as in DAY-18D. NVDA is no longer listed among review-layer blocking symbols (`crosscheck_symbols_blocking`: AMZN, NFLX). The mechanical cross-check still reports 10 unconfirmed NVDA events; they are resolved by the records, not reclassified.

## 4. Counts

| | DAY-18D | DAY-18G |
|---|---|---|
| Status RESOLVED / RESOLVED_EXCLUDED / FIRST_SESSION_UNTESTABLE / BLOCKING / HARD_FAIL | 4 / 1 / 3 / 14 / 0 | 16 / 1 / 3 / **2** / 0 |
| Category PASS / IDENTITY_UNVERIFIED / UNRESOLVED / BLOCKING / FIRST_SESSION_UNTESTABLE | 5 / 2 / 12 / 0 / 3 | 17 / 0 / 2 / 0 / 3 |
| Review-layer blocking symbols | AMZN, NFLX, NVDA | AMZN, NFLX |
| Final status | BLOCKED | **BLOCKED** |

## 5. Blocker inventory (2)
| Category | Item |
|---|---|
| UNRESOLVED — UNEXPLAINED_CHANGE | AMZN 2016-02-22 (record `amzn-20160222-20261007`, UNRESOLVED) |
| UNRESOLVED — UNEXPLAINED_CHANGE | NFLX 2018-11-29 (record `nflx-20181129-20261007`, UNRESOLVED) |

No new blocker; no acquirer-side condition outstanding.

## 6. Tests
- Focused: `tests/test_day18d_v203.py` 28 + `tests/test_day18b_v202.py` 15 + `tests/test_day18_stage_r.py` 23 = **66 passed**.
- Full suite: **1249 passed**, 0 failed (38 min 16 s; the same 28 third-party deprecation warnings as before).

## 7. Not done
No acquisition or network; no holdout or forward-OOS access; no research computation; no change to the snapshot, existing review outputs, the DAY-18E dossier, protocol files, code or review records; the new review output is not committed; no push.
