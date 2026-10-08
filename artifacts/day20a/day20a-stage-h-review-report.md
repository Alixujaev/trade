# DAY-20A — Stage H Protocol-Owner Review Records

| Field | Value |
|---|---|
| **Final status** | **READY_FOR_HISTORICAL_HOLDOUT_EVALUATION** |
| Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (frozen; unchanged; no v2.0.5) |
| Starting HEAD | `73230fc` |
| Records commit | `06c60b4` (18 new files in `artifacts/reviews/stage_h/`) |
| Stage H snapshot | `stage_h_20261008T100604Z`, manifest `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34`. **Unchanged:** tree SHA identical to DAY-20, 63 files, 0 writable. |
| Stage R | Manifest `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`. **Unchanged** (64 files). The 14 Stage R review records are unchanged (last commit `c36b673`). |
| Decisions | **Alixujaev (protocol owner)**, in the DAY-20A instruction. The agent encoded them; every record carries an `authorization` field, and the agent made no decision. |

## Review items (18) and decisions
| Item | Decision | Evidence basis |
|---|---|---|
| AMD←XLNX stock merger, 2022-02-14 (IDENTITY_UNVERIFIED) | **SAME_ENTITY** | The Stage H provider record `15459aa5-…` (acquirer AMD 007903107, acquiree XLNX 983919101) appears once and identically in both payloads and is byte-identical to the Stage R record. The previously accepted DAY-18F SEC 8-K (URL, retrieval time, SHA-256 `492d6a6e…`) was re-verified offline against its local copy, and both quotations are present. AMD's Stage H cross-check is clean, so the acquirer-side merger is **RESOLVED**. |
| 17 NVDA cash dividends (UNCONFIRMED_EVENT) | **EVENT_RETAINED** ×17 | Each Stage H record appears once and identically in both payloads, is CUSIP-assigned to NVDA (67066G104) and is not duplicated. The exact v2.0.4 rounding interval contains 1 at the ex-date session (no numerical false positive or negative, no invalid value). DAY-18F reasoning applied unchanged: an undetectable change within the provider's precision does not invalidate the record. |

**The 17 NVDA ex-dates:**
- **Overlap R∩H (6):** 2021-03-09, 2021-06-09, 2021-12-01, 2022-03-02, 2022-06-08, 2022-09-07. Each cites its Stage R record as evidence only.
- **Holdout (11):** 2023-03-07, 2023-06-07, 2023-09-06, 2023-12-05, 2024-03-05, 2024-09-12, 2024-12-05, 2025-03-12, 2025-06-11, 2025-09-11, 2025-12-04.

**Stage R records are evidence, not Stage H records.** Each new record carries the Stage H manifest binding, its own Stage H evidence references and file SHA-256s, and the current protocol chain. Stage R records were not copied, mutated or superseded.

## Validation
- **Strict loader** (`acquisition/v2/review_records.load`): **18 found, 18 applied, 0 invalid**, no duplicate active records and no supersedes chains. The checks performed:
  - each record is committed at HEAD, with worktree bytes equal to the blob
  - schema and required fields; record_id equals the file name
  - Stage H manifest binding and protocol version
  - decision enums and item_key match
  - Stage H evidence file SHA-256s
  - EVENT_RETAINED mechanical checks
- **Blockers: 18 before → 0 after.** Review status counts: RESOLVED 31, RESOLVED_EXCLUDED 4, FIRST_SESSION_UNTESTABLE 1, BLOCKING 0. UNRESOLVED 0 and IDENTITY_UNVERIFIED 0.
- **All DAY-20 data checks still PASS:** structural, boundary, identity, complete vs all, R∩H overlap, and recompute vs capture.
- **Offline re-validation:** the output is written to `data/oos_cache/protocol_v2/stage_h/validation__stage_h_20261008T100604Z__day20a/` (`validation_report.json` SHA-256 `c58a7d32…`). A **second run is byte-identical**.

## Statements
- **No strategy evaluation:** no MOM or STR signals, positions, trades or gates were computed.
- **No performance metrics:** no returns, CAGR, Sharpe, Sortino, drawdown, turnover, exposure or benchmark performance.
- **No data acquired and no network used;** forward OOS was not accessed.
- **Snapshots:** Stage H and Stage R are unchanged.
- **Holdout status:** Stage H is validated and READY for the frozen historical holdout evaluation of **V2-MOM and V2-STR only**. V2-LRV remains rejected. **The holdout was not run in this task.**
