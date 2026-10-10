# DAY-26B — Protocol-Owner Adoption of Protocol v2.1

| Field | Value |
|---|---|
| **Decision** | **PROTOCOL 2.1 ADOPTED** (`2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 + 2.1`) |
| **Decided by** | Alixujaev (protocol owner) |
| **Decided (UTC)** | 2026-10-10T12:52:51Z |
| **Provenance** | Explicit protocol-owner instruction "DAY-26B — IMPLEMENT PROTOCOL v2.1": adopt `artifacts/day26b/protocol-v2.1-amendment.md` and `.json` as the operative protocol |
| **Effective from** | The commit that contains this record together with the pinned amendment files; **not earlier** |
| **Machine-readable record** | `artifacts/day26b/protocol-v2.1-adoption.json` (pins the LF-normalised SHA-256 of both amendment files) |

## Forward schedule

| Segment | Sessions | Dates | Earliest access (America/New_York) |
|---|---|---|---|
| Window | 1–63 (63) | 2026-10-08 → 2027-01-07 | — |
| `fwd-diag` (`V2-MOM-F002-DIAG`, descriptive) | 1–21 (21) | 2026-10-08 → 2026-11-05 | 2026-11-05 16:15 |
| `fwd-gate` (`V2-MOM-F002`, blind §13 gate) | 22–63 (42) | 2026-11-06 → 2027-01-07 | 2027-01-07 16:15 |

## Decisions recorded

1. Approvals A-1 … A-9 of the amendment (§15) are **accepted**.
2. The formal exceptions E1–E6 (amendment §17) to DAY-16 §3.6 / §3.9 / §15.6 / §15.11 / §14 / §16.7, DAY-22 §3.1 / §3.2.2–§3.2.3 and DAY-23 §8.2 condition 5 are adopted prospectively.
3. Until this record is committed, the 252-session rules governed. From 2026-10-08 to adoption, no forward data was acquired, computed or inspected.
4. DAY-24 (63-session proposal) and DAY-26A (21-session draft) are **superseded** as historical records. Their files are not edited.
5. Unchanged: strategy config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`, the §13 thresholds, B1/B2, costs 0/5/10 bps, the DAY-16 protocol files, the DAY-22 lockdown, the DAY-25B predeclaration and preflight record, and all historical artifacts.

## Stage F acquisition parameters (DAY-20 decision precedent)

| Parameter | Value |
|---|---|
| Range | `fwd-diag` 2025-01-02 → 2026-11-05; `fwd-gate` 2025-01-02 → 2027-01-07 |
| asof | The segment's last session |
| Corporate-action process_date window | Q1 = [2025-01-01, segment last session] only |
| Event-date boundary | [2025-01-02, segment last session]; records outside are discarded in memory, counts only (v2.0.1 C1) |
| Why no Q2 window | Capture follows the last close on the same evening, so later process dates are not yet observable. A later-processed action appears as an unexplained change in the v2.0.4 cross-check and is a BLOCKING review. |
| Assets endpoint | Not called |
| Snapshot root | `data/oos_cache/protocol_v2/stage_f/`, one snapshot per segment (`stage_f_<segment>_<UTC timestamp>`) |
| Review records | `artifacts/reviews/stage_f` |
| Required validation status | `READY_FOR_FORWARD_EVALUATION` |

## Enforcement

`backtest/v2/forward.py` refuses every Stage F capture, validation, load and forward run unless:
- this record is ADOPTED;
- the amendment files match the pinned SHA-256;
- all three files are committed unchanged;
- the segment's earliest access time has passed.

## Next task

Commit this record with the adopted amendment (S1). Then, after 2026-11-05 16:15 America/New_York, carry out S3 (preflight for `fwd-diag`) under a separate authorisation.

## Incident disclosure — appended 2026-10-10 (DAY-26C; the sections above are unchanged)

- After this decision was recorded (12:52:51Z) and before any commit, a DAY-26B full-suite verification run downloaded recent yfinance intraday data into `data/cache/` between 12:56:23 and 12:59:51 UTC: 54 files, believed to include forward sessions 1–2.
- Legacy tests in the same run consumed the files. No `fwd-gate` session existed, and no V2-MOM forward metric was computed.
- Record: `artifacts/day26c/day26c-forward-data-incident.md` / `.json`. The files are quarantined outside the repository.
- **`fwd-diag`: `FWD-DIAG-INVALID (protocol-breach)`** (final; S3–S5 cancelled). **`fwd-gate`: PENDING** (blind, not evaluated, unchanged).
- `decided_utc` and `integrity_at_adoption` are kept as written. They were true at 12:52:51Z and no longer hold from 12:56:23Z on.
- The amendment pins were re-pinned after the append-only disclosure. The original pins are kept in `adopted_files_sha256_lf_history`, and the incident record is pinned in `incident_records_sha256_lf`.
