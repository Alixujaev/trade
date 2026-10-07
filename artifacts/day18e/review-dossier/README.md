# DAY-18E — Stage R Review-Evidence Dossier (DRAFT — NOT REVIEW RECORDS)

> **DRAFT ONLY. Nothing in this directory is a review record, and nothing here decides anything.**
> Every item states: **"Decision: intentionally blank — protocol owner decision required."**
> Do **not** copy these files into `artifacts/reviews/stage_r/`. A real record must be written and committed by the protocol owner (v2.0.3 item 2).

| Field | Value |
|---|---|
| Prepared at HEAD | `25d74f770760460c3427b37c63f7fd9b6fd5803e` (uncommitted draft) |
| Protocol | `2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3` (commits `ba3cefe`, `ed034b3`, `0ebb606`, `d26b36e`) |
| Source snapshot | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/` — manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` (verified before use) |
| Evaluation reproduced | DAY-18D v2.0.3 output `data/oos_cache/protocol_v2/stage_r/reviews/v2_0_3__stage_r_20261007T093410Z/` (file hashes in `dossier.json`) |
| Generator | read-only, offline script in the session scratchpad (not a repository file), SHA-256 `bf8780112210858cb864bcc01cd834ffe366fbfab04196d6dca78eeb16dc72e0` |
| Review records present | **0** (`artifacts/reviews/` does not exist) |
| Review decisions made by the agent | **0** |

## How to read the files
- `dossier.json` — index of all **14** items, protocol/evidence hashes, generator hash.
- `crm-work.json`, `amd-xlnx.json` — IDENTITY_UNVERIFIED items.
- `amzn-2016-02-22.json`, `nflx-2018-11-29.json` — UNEXPLAINED_CHANGE items.
- `nvda-dividends.json` — 10 UNCONFIRMED_EVENT items.

Each item contains `facts` (mechanical, reproduced offline from the snapshot with the committed `acquisition/v2` functions; reproduction matched DAY-18D exactly), `mechanical_checks` (PASS / BLOCKING / UNRESOLVED / IDENTITY_UNVERIFIED), `provider_evidence`, `limitations`, `admissible_decisions` (the v2.0.3 enums and their evidence requirements, listed for reference — none is selected), `supporting_artifacts` (evaluation outputs, not provider evidence) and a `record_template`.

**Evidence hashes.** Each `record_template.evidence[]` entry uses the v2.0.3 validator form `snapshot:stage_r_20261007T093410Z/<file>#<locator>` with the SHA-256 of the **entire original snapshot file** (`hash_scope`); the locator after `#` names the record id or the sessions used (`content_scope`). Records also carry `record_canonical_sha256` (SHA-256 of the record's sorted-key compact JSON) as an identification aid only.

**Record templates.** `record_id` is `DRAFT-…` (draft-only; must be replaced), `decision`, `reasoning`, `reviewer`, `decided_utc` are `null`, and `DRAFT_NOT_A_REVIEW_RECORD` is `true`. To create a real record the protocol owner would choose a `record_id`, fill `decision` (one of the admissible values), `reasoning`, `reviewer`, `decided_utc`, add any further evidence (e.g. a regulatory filing with URL, retrieval time and SHA-256 for identity items), remove the draft-only fields, save it as `artifacts/reviews/stage_r/<record_id>.json`, commit it, and re-run the v2.0.3 re-evaluation into a new output directory. The validator re-checks every field and the mechanical preconditions.

**NVDA date note.** The DAY-18E brief listed 2020-03-02 and 2020-06-01; the committed DAY-18D report lists **2018-05-23 and 2019-08-28** instead (with 2020-09-01, 2020-12-03, 2021-03-09, 2021-06-09, 2021-12-01, 2022-03-02, 2022-06-08, 2022-09-07). The committed report governs; those ten events are documented here.

---

## 1. CRM←WORK — IDENTITY_UNVERIFIED (BLOCKING)
**Decision: intentionally blank — protocol owner decision required.**

| Fact | Value |
|---|---|
| Record | `stock_and_cash_mergers`, id `299d6bfe-da13-4491-bc28-481f1f2aa54c`, effective/event date 2021-07-21 |
| Acquirer | CRM, CUSIP `79466L302` (field `acquirer_cusip` of the record) |
| Acquiree | WORK, CUSIP `83088V102` |
| Identical in both `data_quality` payloads | yes |
| CRM asset metadata (`assets.json`) | `cusip` is null |
| v2.0.3 identity anchor for CRM | none — "no CUSIP-bearing split/dividend or name-change record" |
| Other snapshot records carrying CUSIP `79466L302` | 0 |

Mechanical checks: same-provider anchor → IDENTITY_UNVERIFIED; payload consistency → PASS; v2.0.3 item 5 resolution → IDENTITY_UNVERIFIED (no committed record).
Limitations: the snapshot contains no same-provider record that independently links `79466L302` to the CRM ticker; no regulatory filing was collected (network not allowed in DAY-18E). The snapshot alone does not establish either SAME_ENTITY or DIFFERENT_ENTITY.
Admissible: SAME_ENTITY / DIFFERENT_ENTITY (each requires ≥ 1 same-provider record or primary regulatory filing tying or distinguishing the record CUSIP and the issuer) / UNRESOLVED.

## 2. AMD←XLNX — IDENTITY_UNVERIFIED (BLOCKING)
**Decision: intentionally blank — protocol owner decision required.**

| Fact | Value |
|---|---|
| Record | `stock_mergers`, id `15459aa5-b297-4e33-9624-c9d59b75ba46`, effective/event date 2022-02-14 |
| Acquirer | AMD, CUSIP `007903107` |
| Acquiree | XLNX, CUSIP `983919101` |
| Identical in both `data_quality` payloads | yes |
| AMD asset metadata | `cusip` is null |
| v2.0.3 identity anchor for AMD | none — same reason as CRM |
| Other snapshot records carrying CUSIP `007903107` | 0 |

Mechanical checks, limitations and admissible decisions: as for item 1.

## 3. AMZN 2016-02-22 — UNEXPLAINED_CHANGE (UNRESOLVED, BLOCKING)
**Decision: intentionally blank — protocol owner decision required.**

| Fact (p = 2016-02-19, k = 2016-02-22) | p | k |
|---|---|---|
| Raw close | 534.9 | 559.5 |
| Adjusted close | 26.74 | 27.98 |
| Displayed decimals (adjusted) | 2 | 2 |
| δ (v2.0.3) | 0.005 | 0.005 |

ρ = f_k/f_p with |ρ − 1| = 3.656e-4; v2.0.3 interval [ρ_min, ρ_max] = [0.9992689, ~1.0 (just below 1)]; **1 lies outside the interval → change detected**. Corporate-action records of any type referencing AMZN with event/ex date in (2016-02-19, 2016-02-22]: **0** in `complete`, **0** in `all`; within ±30 sessions: 0; AMZN records in all of Stage R: 1 (the 2022 forward split).
Mechanical checks: detection → BLOCKING; retained event in (p,k] → none (UNRESOLVED); PROVIDER_ADJUSTMENT_ARTIFACT evidence precondition (no record of any type in (p,k], both payloads) → **satisfied** (a precondition only, not an outcome); item 3 resolution → UNRESOLVED.
Limitations: the snapshot does not state why the adjusted series changes on this session; magnitude is not evidence; no re-acquisition was performed.
Admissible: PROVIDER_ADJUSTMENT_ARTIFACT / MISSING_EVENT_CONFIRMED / UNRESOLVED (requirements in the JSON).

## 4. NFLX 2018-11-29 — UNEXPLAINED_CHANGE (UNRESOLVED, BLOCKING)
**Decision: intentionally blank — protocol owner decision required.**

| Fact (p = 2018-11-28, k = 2018-11-29) | p | k |
|---|---|---|
| Raw close | 282.65 | 288.75 |
| Adjusted close | 28.26 | 28.88 |
| Displayed decimals (adjusted) | 2 | 2 |
| δ (v2.0.3) | 0.005 | 0.005 |

|ρ − 1| = 3.5e-4; interval [0.99930013, ~1.0 (just below 1)]; **1 lies outside → change detected**. NFLX corporate-action records with event/ex date in (p,k]: **0** / **0**; within ±30 sessions: 0; NFLX records in all of Stage R: 0.
Mechanical checks, limitations and admissible decisions: as for item 3 (precondition for PROVIDER_ADJUSTMENT_ARTIFACT **satisfied**; item UNRESOLVED).

## 5–14. NVDA — 10 UNCONFIRMED_EVENT items (UNRESOLVED, BLOCKING)
**Decision: intentionally blank — protocol owner decision required (for each of the ten events).**

All ten are `cash_dividends` records, CUSIP-assigned to NVDA, present once and identical in both payloads, not duplicated. At each ex-date session the v2.0.3 interval contains 1, so **no change is detected and the event is unconfirmed** (v2.0.3 grants no precision exemption).

| Ex-date | p | Rate | Decimals p/k | δ p/k | \|ρ − 1\| | Interval half-width | Reference rate/raw_p* |
|---|---|---|---|---|---|---|---|
| 2018-05-23 | 2018-05-22 | 0.15 | 2/3 | 0.005/0.0005 | 5.80e-4 | 9.16e-4 | 6.18e-4 |
| 2019-08-28 | 2019-08-27 | 0.16 | 3/0 | 0.0005/0.005 | 8.45e-4 | 1.37e-3 | 9.89e-4 |
| 2020-09-01 | 2020-08-31 | 0.16 | 1/2 | 0.005/0.005 | 4.35e-4 | 7.39e-4 | 2.99e-4 |
| 2020-12-03 | 2020-12-02 | 0.16 | 2/2 | 0.005/0.005 | 5.76e-4 | 7.46e-4 | 2.95e-4 |
| 2021-03-09 | 2021-03-08 | 0.16 | 2/2 | 0.005/0.005 | 6.47e-4 | 8.34e-4 | 3.45e-4 |
| 2021-06-09 | 2021-06-08 | 0.16 | 2/2 | 0.005/0.005 | 4.78e-4 | 5.77e-4 | 2.29e-4 |
| 2021-12-01 | 2021-11-30 | 0.04 | 2/1 | 0.005/0.005 | 1.74e-4 | 3.13e-4 | 1.22e-4 |
| 2022-03-02 | 2022-03-01 | 0.04 | 2/2 | 0.005/0.005 | 2.90e-6 | 4.21e-4 | 1.70e-4 |
| 2022-06-08 | 2022-06-07 | 0.04 | 2/2 | 0.005/0.005 | 3.70e-4 | 5.34e-4 | 2.11e-4 |
| 2022-09-07 | 2022-09-06 | 0.04 | 2/2 | 0.005/0.005 | 1.48e-4 | 7.39e-4 | 2.97e-4 |

\*Reference quantity rate / raw close at p, shown for orientation only; it presumes a multiplicative dividend adjustment whose method is undocumented by the provider (v2.0 R1 Q4) and is **not** evidence under v2.0.3. Raw/adjusted closes per session are in `nvda-dividends.json`.

Mechanical checks per event: detection → UNRESOLVED (inside interval); EVENT_RETAINED preconditions (identity-resolved, identical in both payloads, not duplicated) → PASS ×3 (preconditions only); EVENT_REJECTED precondition (same-provider evidence from a different, later snapshot) → **not available** (only one Stage R snapshot exists); item 4 resolution → UNRESOLVED.
These items are separate from the NVDA←MLNX merger review (RESOLVED under the frozen review rule in DAY-18D).
Admissible: EVENT_RETAINED / EVENT_REJECTED / UNRESOLVED (requirements in the JSON).

---

## Scope statement
Prepared offline from the immutable snapshot and committed artifacts only: no acquisition, no network, no web research, no holdout or forward-OOS data, no research or backtest. The snapshot, the v2.0.2 and v2.0.3 review outputs and all protocol artifacts were verified unchanged. This dossier resolves **no** blocker; Stage R remains **BLOCKED** until the protocol owner commits review records (or a same-provider anchor becomes available) and a new re-evaluation is run.
