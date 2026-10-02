# DAY-15A — Finalization (frozen before any OOS download)

This record resolves the four DAY-15A blockers and freezes the acquisition rules for DAY-15B. It does not change DAY-14 (`5d48c53`), which still governs.

**Labels:**
- VERIFIED: checked in code, the calendar or the research cache.
- DECIDED: a protocol decision made here, before data, with the user's approval.
- INFERRED: follows from source code but has not been observed.
- UNRESOLVED: open. **Nothing required for acquisition is UNRESOLVED.**

## Frozen decisions

| Item | Value | Label |
|---|---|---|
| OOS boundary | 2026-09-25 (exclusive) | VERIFIED (DAY-14) |
| OOS session rule | first 60 NYSE regular trading sessions strictly after the boundary | VERIFIED (DAY-14) |
| Universe | frozen 25 symbols (`config/day_universe.py`); no additions, removals or substitutions; missing data recorded as MISSING | VERIFIED (DAY-14) / enforced in `acquisition/run.py` |
| Calendar | `exchange_calendars` **4.13.2**, calendar `XNYS`, explicit bounds 2026-01-02..2027-12-31, sessions in America/New_York; pinned in `requirements.txt`; resolution needs no network | DECIDED (user) / VERIFIED (installed, compatible with pandas 3.0.5 / numpy 2.5.2) |
| Resolved sessions | 60 sessions; first **2026-09-28**, last **2026-12-21**; holiday 2026-11-26 excluded; **early close 2026-11-27** (13:00 ET: 42 × 5m / 14 × 15m bars); deterministic (resolved twice, identical; covered by tests) | VERIFIED |
| Capture timing | `market_close = 16:00 ET`; `capture_not_before = 16:15 ET` on the session date; timezone America/New_York. The same fixed 16:15 applies on early-close days (conservative). Only sessions past this wait are requested. | DECIDED (user default) |
| Provider | yfinance **1.6.0** through `acquisition.provider_adapter.YFinanceAdapter`; explicit `start` / `end` (no `period`, no `max`) | VERIFIED |
| Intervals | 5m, 15m; RTH 09:30–16:00 America/New_York; storage UTC; index = bar OPEN | VERIFIED |
| Adjustment | `auto_adjust=False` (explicit), together with every other `download` option; raw OHLC plus `adj_close` stored; no transformation | DECIDED (user, DAY-15A) |
| Corporate actions | snapshots immutable (write-once, read-only); never modified in place or overwritten. A different re-acquisition or overlap is marked DISCREPANCY and both copies are kept with hashes; no "correct" version is chosen at acquisition. Discrepancies are data-integrity issues for later review. Metadata records `adj_close == close` counts and `corporate_action_status`. | DECIDED |
| Snapshot storage | `data/oos_cache/protocol_v1.0/snapshots/<snapshot_id>/`, plus a derived `manifest.json`; `data/oos_cache/` is git-ignored (OOS data stays outside git) | DECIDED |
| Research cache | `data/cache/` is never modified (write guard plus preflight hash check against `integrity-baseline.json`) | VERIFIED |
| Existing artifacts | DAY-04..DAY-14 never modified (preflight hash check); reports may be written only to `artifacts/day15/` | VERIFIED |
| OOS inspection boundary | structural validation only before the OOS gate (DAY-14 §11; data-expansion-spec §5) | VERIFIED (DAY-14) |
| Cost assumptions | DAY-14 transaction-cost contract unchanged | VERIFIED |
| Git | acquisition starts only from the clean DAY-15A finalization commit. Allowlisted untracked items: the pre-existing `day08-market-cache.tar.gz` and the DAY-15B report. The preflight records the commit SHA. | DECIDED |
| Environment | `artifacts/day15/environment-manifest-day15b.json` (pip-freeze equivalent, 57 distributions, Python 3.12.10, including yfinance 1.6.0, exchange_calendars 4.13.2, pandas 3.0.5, numpy 2.5.2); each snapshot writes its own `environment.json` | VERIFIED |

## Capture status at finalization

- At finalization, 2026-10-02 06:31 ET, **4 of 60** sessions are complete and past the capture wait: 2026-09-28, 09-29, 09-30, 10-01.
- DAY-15B therefore captures **snapshot #1 = PARTIAL**, by user decision, to secure these bars inside the provider's history window.
- Later snapshots follow DAY-14 (≤ 20 sessions apart). The first is required before about 2026-11-27 under the INFERRED 60-day reading; the last after 2026-12-21 16:15 ET.
- Overlapping sessions between snapshots are compared, never overwritten.

## Preflight (enforced by `acquisition.run.preflight`, `--capture` refuses on failure)
- `data/cache` and DAY-04..DAY-14 artifact hashes equal `artifacts/day15/integrity-baseline.json`;
- no tracked changes and no unexpected untracked files;
- the calendar resolves exactly 60 identical sessions twice, the first strictly after the boundary;
- a capture before 16:15 ET of a session is impossible (`capture_policy`).

## Remaining caveats (non-blocking)
- **INFERRED:** Yahoo's exact 60-day intraday window (calendar days vs inclusive), which sets the latest safe date for each snapshot.
- **INFERRED:** whether intraday `adj_close` ever differs from `close`. This is observed per snapshot (counts only).
- **Rule for using flagged discrepancies at evaluation time:** to be predeclared in the OOS evaluation protocol before the gate. It is not needed for acquisition.
