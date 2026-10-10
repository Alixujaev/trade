# DAY-26D — Protocol-Owner Adoption of Protocol v2.2

| Field | Value |
|---|---|
| **Decision** | **PROTOCOL 2.2 ADOPTED** (`2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 + 2.1 + 2.2`) |
| **Decided by** | Alixujaev (protocol owner) |
| **Decided (UTC)** | 2026-10-10T14:56:30Z |
| **Provenance** | Explicit instruction "DAY-26D — RESOLVE BLOCKERS, COMMIT, START A CLEAN FORWARD GATE" (2026-10-10), which authorised the amendment, the commit and the start of a new clean gate without further approval |
| **Effective from** | The commit that contains this record and the pinned amendment; not earlier |
| **Machine-readable** | `artifacts/day26d/protocol-v2.2-adoption.json` (pins the LF-normalised SHA-256 of `protocol-v2.2-amendment.md` and `.json`; references the v2.1 adoption and DAY-26C incident pins) |

## Decisions adopted

- **D1:** the Stage F preflight no longer requires the unrecoverable DAY-15 `data/cache`. Every other frozen-directory check is retained (line-ending-invariant).
- **D2–D5:** the new clean gate is `fwd-gate2` / `V2-MOM-F003`, 2026-10-12 → 2026-12-09 (42 XNYS sessions).
  - The exposed sessions 2026-10-08/09 are excluded from the sample.
  - It uses a fresh, immutable Stage F snapshot and unchanged strategy, config SHA, thresholds, universe, benchmarks, execution and costs.

## Segment status

| Segment | Status |
|---|---|
| `fwd-diag` | `FWD-DIAG-INVALID (protocol-breach)` (unchanged) |
| `fwd-gate` | `SUPERSEDED (protocol 2.2) — never acquired or evaluated` |
| `fwd-gate2` | `PENDING — blind, not evaluated` |

## Next step

The sessions begin on 2026-10-12, and nothing is acquired before the end. The Stage F capture for `fwd-gate2` is permitted from **2026-12-09 16:15 America/New_York (21:15 UTC)**.
