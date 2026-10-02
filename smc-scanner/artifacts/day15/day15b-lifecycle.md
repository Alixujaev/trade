# DAY-15B — Acquisition Lifecycle (incremental capture, 60/60 guard)

**Scope:** an acquisition-robustness fix only.
- The OOS dataset definition is unchanged: the first 60 XNYS sessions strictly after 2026-09-25, i.e. 2026-09-28 … 2026-12-21, on the frozen 25-symbol universe, 5m and 15m bars.
- DAY-14, `day15a-finalization.md`, the existing snapshot `capture_20261002T0636ET_s001-s004`, `data/cache/`, and all strategy, signal and backtest code are unchanged.
- No OOS data was downloaded for this change.

## 1. Why
The first DAY-15B implementation requested from session 1 (2026-09-28) on every capture and had no stop condition. Yahoo serves intraday history for only about 60 days (INFERRED), so later captures would eventually request data the provider no longer has. Repeated runs after 60/60 would also re-download everything.

## 2. Completeness ledger (`acquisition/ledger.py`)
A unit is (session, symbol, interval). It counts as **complete** only if an accepted snapshot file:
- belongs to a non-MISSING run result with `structural_passed = true`;
- has `present_bars == expected_bars` (calendar grid: 78 / 26, or 42 / 14 on 2026-11-27) and no missing bar opens for that session;
- has its data file and meta file present, with the required metadata (`content_sha256`, `file_sha256`, `provider_config` with `auto_adjust = false`, …);
- has bytes whose SHA-256 still equals the recorded `file_sha256`.

**Further rules:**
- A session is complete only when all 25 × 2 = 50 units are complete.
- Discrepancy copies (`conflicts/`) never count; the earliest complete snapshot is the accepted original.
- The ledger reads JSON metadata and file hashes only; it never parses market-data content.
- Both file namings are supported: `{SYM}_{iv}.parquet` (snapshot #1) and `{SYM}_{iv}_sNNN-sMMM.parquet` (incremental parts).

## 3. Lifecycle states (`capture_state`)

| State | Meaning | Provider requests |
|---|---|---|
| COMPLETE | 60/60 sessions complete | none; no snapshot, no manifest write (idempotent) |
| UP_TO_DATE | every session already past its capture wait is complete | none |
| READY | some capturable units are missing and all of them lie inside the provider window | only the missing units |
| BLOCKED | the earliest missing capturable session starts before the provider window | none (`AcquisitionBlockedError`; CLI exit 4) |

**BLOCKED is final for that session.** It is never dropped, substituted, moved forward, or reported as acquired. The OOS definition does not change.

## 4. Provider window (`acquisition/provider_adapter.py`)
- `INTRADAY_LOOKBACK_DAYS = 60`, `LOOKBACK_SAFETY_MARGIN_DAYS = 2`, and `earliest_requestable_start(now) = now − 58 days`.
- **INFERRED, not a contractual guarantee:** the yfinance docstring says "Intraday data cannot extend last 60 days"; the cut-off is applied by Yahoo's server.
- No calendar date is hard-coded; the window is derived from the capture time.
- Under this rule, session 1 (2026-09-28) stops being requestable at about 2026-11-25, so the session-40 capture (2026-11-20) is still inside the window.

## 5. Incremental requests (`capture_run`)
- For each symbol × interval, the missing capturable sessions are grouped into contiguous runs.
- Each run is one explicit start/end request: start = the run's first session at 00:00 ET; end = the day after its last session (exclusive).
- Complete sessions are never requested again. A partial session requests only its missing symbol/interval units.
- **Write-once:** each capture writes a new snapshot directory `capture_<YYYYMMDD>T<HHMM>ET_sLLL-sHHH/` with part files `{SYM}_{iv}_sNNN-sMMM.parquet` plus `.meta.json`, `environment.json` and `run.json`. Nothing existing is overwritten.
- **Overlaps:** a re-requested partial session overlaps an earlier file and is compared cell by cell. The result is recorded as IDENTICAL or DISCREPANCY, and the original is kept.
- **Provider failures:** a failing unit is recorded as MISSING (never substituted) and stays in the next plan.
- The derived `manifest.json` now carries a `progress` block (`complete_sessions`, `progress`, `complete_units`).

## 6. CLI
- `--dry-run`: no network, no market-data content. It shows:
  - status, total 60, progress;
  - complete / partial / missing sessions;
  - the earliest missing capturable session and the latest capturable session;
  - the provider window;
  - the planned request count and session ranges.
- `--capture`:
  1. preflight (unchanged; exit 3 on failure);
  2. COMPLETE / UP_TO_DATE → message, exit 0, nothing written;
  3. BLOCKED → exit 4;
  4. otherwise the incremental capture, then the report.
- The report writer may write **only** `artifacts/day15/day15b-acquisition.md`, so the DAY-15A documents are protected.

## 7. State at the time of this change (dry run, 2026-10-02 before 16:15 ET)
- Progress **4/60** (2026-09-28 … 2026-10-01), read from snapshot #1's metadata and hashes; status UP_TO_DATE; 0 planned requests.
- **Next scheduled capture:** after 16:15 ET on 2026-10-23. It will request sessions 5–20 only (2026-10-02 … 2026-10-23).
