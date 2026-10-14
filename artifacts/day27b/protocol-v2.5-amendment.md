# DAY-27B — Protocol v2.5 Amendment: review audit records in the `V2-MOM-P001` health record

> **STATUS: DRAFT — NOT ADOPTED.** This is a review copy only. It does not authorise implementation. It takes effect only from a commit that contains this amendment and an owner-signed adoption record `artifacts/day27b/protocol-v2.5-adoption.json` with `final_status: "ADOPTED"`. The current file at that path is a proposal (`PROPOSED_NOT_ADOPTED`), not an adoption.
>
> It is append-only. These stay unchanged:
> - protocols 2.1–2.4, their adoption records and the DAY-26C incident record and quarantine;
> - the V2-MOM config (SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`);
> - the `fwd-gate2` calendar, status (PENDING), sample and access guards (`backtest/v2/forward.py`).

| Field | Value |
|---|---|
| Protocol version | **2.5** (`2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 + 2.1 + 2.2 + 2.3 + 2.4 + 2.5`) |
| Scope | **Paper runner `V2-MOM-P001` only.** Observability of review items in the plaintext health record. |
| Not in scope | Stage R/H/F, `fwd-gate2`, identity rules, review classification, strategy, ledger, seal |
| Amends | v2.3 P3 (permitted plaintext health content); v2.3 §3 (health-record fields) |

## 1. Problem

The 2026-10-12 session (`paper_state/runs/2026-10-12.json`, status OK) recorded `review_pending_count: 9`. The items themselves were never persisted:
- `paper/data.py:build_market_data` keeps only `entity`, `event_date` and `category` of each BLOCKING/HARD_FAIL review item;
- `paper/runner.py:run` stores only the count.

The input snapshot holds neither the raw corporate-action records nor the `all`-adjusted bars, so the items cannot be re-derived offline. The reporting behaviour itself (review items are reported, not blocking, for live data without review records) is correct under v2.3 P5 and is **not** changed.

## 2. Rules

### R1. Persisted fields
For every session processed after this amendment takes effect, `runs/<D>.json` contains `review_pending_items`: a list holding one object per review item whose classifier status is `BLOCKING` or `HARD_FAIL`. This is the same filter used today. Each object has exactly these seven keys, copied from the existing classifier output (`acquisition/v2/reviews.py:classify`):

| Key | Meaning |
|---|---|
| `item` | classifier item label (e.g. `unconfirmed-event NVDA cash_dividend 2025-03-12`) |
| `entity` | affected ticker / Stage R entity |
| `event_date` | associated event or session date |
| `category` | classifier category (e.g. `UNRESOLVED`, `IDENTITY_UNVERIFIED`, `BLOCKING`) |
| `status` | classifier status (`BLOCKING` or `HARD_FAIL`) |
| `reason` | classifier reason text |
| `id` | corporate-action record id, where the classifier provides one |

- A key the classifier did not produce for that item is stored as `null`. No value is inferred, derived or invented.
- Items are kept in classifier order. They are never merged or de-duplicated, so several items for the same entity or date stay distinct.
- No other keys are added.

### R2. Count/list consistency
- `review_pending_count` is retained with its meaning unchanged, and is computed as `len(review_pending_items)` from the same list. There is one source of truth.
- Before the commit point (writing `runs/<D>.json`), the runner checks that this count equals the number of `BLOCKING`/`HARD_FAIL` items in the classifier result. It also checks that the list serialises to canonical JSON.
- Any mismatch or serialisation failure raises an error. The session then stays unprocessed and is retried on the next run (v2.3 P5/P7). An unavailable list is never replaced by an empty one.

### R3. Schema marker
- New records carry `"health_schema": 2`.
- `check-health` reports UNHEALTHY if a `health_schema: 2` record lacks `review_pending_items` or if its count ≠ the list length.
- Records without the marker, i.e. records written before adoption such as 2026-10-12, stay valid as they are. They are never rewritten or backfilled.

### R4. Permitted plaintext health content (amends v2.3 P3)
v2.3 P3 limited plaintext output to health information: session, timestamps, data completeness counts, hashes and error codes. This amendment adds **non-performance review metadata**, meaning the seven R1 fields. These describe public market-data and corporate-action facts that are independent of holdings.

Still prohibited in plaintext:
- positions, weights, holdings, orders, fills, decisions or pending orders;
- equity, cash, P&L, returns or any performance metric;
- seal keys, credentials, tokens or any secret;
- encrypted or decrypted ledger content.

Raw corporate-action payloads and adjusted-price datasets are **not** added to the snapshot.

## 3. Invariants (must not change)
1. Strategy signals, ranking, sizing, timing, costs and corporate-action accounting (frozen engine `backtest/v2`).
2. Identity resolution (v2.0.1 C2 + v2.4 A1), exclusions and review classification, categories and statuses. Persisting an item never resolves it or turns it into an accepted event.
3. Session order, catch-up, idempotency (P7), locking, retries and `late` flags.
4. Sealed ledger format, `ledger_sha256`, seal key, `reveal` time lock and the `--now` refusal.
5. All fail-closed checks of v2.3 P5 and v2.4, `check_quarantine`, the endpoint guard and `check_config_sha`.
6. Frozen strategy configuration, historical artifacts and existing session records/snapshots.

## 4. Adoption chain and guard
- The paper runner refuses to run unless v2.5 is adopted and committed unchanged. The chain is **v2.5 → v2.3 → v2.4 → v2.2 → v2.1**: a new `check_adoption_25` in `paper/` checks the v2.5 pins and commit, then calls the existing `check_adoption_23`, which already chains to v2.4 → v2.2 → v2.1.
- `fwd-gate2` access (`backtest/v2/forward.py:check_forward_access`) is **not** changed and does not require v2.5.

## 5. Required tests (offline, before adoption)
New file `tests/test_day27b_review_audit.py`, using synthetic fixtures and a fake fetcher. No network, and no unsealing.

1. Every BLOCKING/HARD_FAIL item is persisted with exactly the seven keys.
2. `review_pending_count == len(review_pending_items)`.
3. Two items with the same entity and date but a different `item` are both persisted, not collapsed.
4. Keys missing from the classifier (e.g. no `id`, no `event_date`) are stored as `null`.
5. A count mismatch or a non-serialisable item raises before the commit point: no `runs/<D>.json` is written and the session stays pending.
6. The record contains no performance/position keys (`equity`, `pnl`, `weights`, `positions`, `fills`, `exposure`, `cash`, `return`) and not the seal-key value.
7. For identical input, `ledger_sha256` and the review classification are identical before and after the change.
8. `check-health`: a `health_schema: 2` record without the list, or with a count mismatch, is UNHEALTHY. A legacy record without the marker is unaffected.
9. The v2.5 adoption guard is refused when the record is missing, not ADOPTED, has mismatched pins or is uncommitted. The v2.4 and `fwd-gate2` guards are unchanged. Existing suites (`test_day27_paper.py`, `test_day27a_identity_pin.py`, `test_day26d_gate2.py`, …) still pass.

## 6. Files that would change after approval
- **Modified:**
  - `paper/data.py`: widen the review-item projection to the seven keys;
  - `paper/runner.py`: health record fields, R2 pre-commit check, R3 validation in `check_health`, `check_adoption_25`;
  - `paper/config.py`: `ADOPTION_JSON_25`, `AMENDMENT_FILES_25`.
- **New:** `tests/test_day27b_review_audit.py`.
- **Adoption:** `artifacts/day27b/protocol-v2.5-adoption.json` is rewritten as an effective record only at adoption, with the status changed first, then the hashes.
- **Not changed:**
  - `acquisition/`, `backtest/`, strategy/config;
  - `paper/seal.py`, `paper/ledger.py`;
  - all existing artifacts, records and `paper_state/` contents.

## 7. Evidence
- `paper_state/runs/2026-10-12.json`: `review_pending_count: 9`, no item details (health fields only).
- `paper_state/data/2026-10-12-da42c150fe38/`: `bars_raw/*.parquet`, `events.json`, `manifest.json`. No raw CA records, no `all` bars.
- `paper/data.py:153` and `paper/runner.py:221`: the current projection and the count-only persistence.
