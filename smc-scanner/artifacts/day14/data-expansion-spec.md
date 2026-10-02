# DAY-14 — Independent Data Expansion Specification (v1.0)

**Status:** specification only. **No data has been acquired or inspected.** No files or directories described here have been created. The existing frozen cache (`data/cache`, 305 files) must never be modified. Any acquisition tool needed by this spec is **NOT YET IMPLEMENTED** and must be written as a separate, reviewed change before use.

---

## 1. Market-data contract

| Item | Requirement / current behaviour | Status |
|---|---|---|
| Required series | 5m RTH OHLCV for each universe symbol; 15m RTH OHLCV for each symbol (15m structure context); 5m and 15m RTH for SPY and QQQ (only if an experiment uses index context) | PREDEFINED |
| Columns | open, high, low, close, volume; tz-aware DatetimeIndex stored in **UTC**, index = bar **OPEN** | PREDEFINED (existing `validate_ohlcv`) |
| Symbol / session identity | symbol from the file name; session = America/New_York calendar date of the bar (`data/session.py::get_session_date`) | PREDEFINED (existing) |
| Timezone normalisation | naive timestamps are localised to UTC, aware ones converted to UTC; sessions are evaluated in America/New_York | PREDEFINED (existing) |
| DST | handled by tz conversion (EDT/EST). RTH is always 09:30–16:00 local time; a DST transition must not shift the expected 78 bars per full session. Sessions on or after a transition (2026-11-02, the first session after the 2026-11-01 change) are explicitly sanity-checked. | PREDEFINED |
| Missing bars | **not filled or interpolated.** Currently dropped silently if NaN. New requirement: count missing bars per symbol-session against the expected grid and **log** them in the manifest. | existing behaviour PREDEFINED; logging NOT YET IMPLEMENTED |
| Duplicate bars | currently keeps the **last** duplicate timestamp silently. New requirement: count and log duplicates; any duplicate in an OOS snapshot fails the structural check until explained. | existing behaviour PREDEFINED; logging NOT YET IMPLEMENTED |
| Zero-volume bars | currently kept (volume ≥ 0 is valid). Reported as a count per symbol-session; never dropped. They affect RVOL. | PREDEFINED |
| Malformed bars | rows with high < low, high < open/close, low > open/close, or negative volume are currently dropped silently. New requirement: count and log them. | existing behaviour PREDEFINED; logging NOT YET IMPLEMENTED |
| Corporate actions | provider called with `auto_adjust=True`. Whether yfinance back-adjusts 5m/15m bars after a split or dividend, and whether a later snapshot changes earlier bars, is not established. | OPEN QUESTION |
| Corporate-action detection | if overlapping bars differ between snapshots (§4), the symbol-session is flagged and **not** silently replaced | PREDEFINED |
| Extended hours | excluded (`prepost=False`, `include_extended_hours=False`) | PREDEFINED |
| Closed-bar policy | analysis uses only bars with `bar_end ≤ as_of` (`filter_closed_bars`); acquisition stores only sessions that are complete at capture time | PREDEFINED |
| Provider | yfinance only. Switching to Alpaca (IEX feed, not consolidated volume) would change RVOL semantics and is a separate experiment. | PREDEFINED |

**Minimum history and warmup** (existing indicator definitions, not changed):
- the engine evaluates from 5m bar index 14 (RSI(14), Wilder);
- RVOL uses the same time-of-day over the prior ≤ 20 sessions with `min_sessions=1`, so the first sessions of any series have thin baselines;
- 15m structure needs ≥ 5 closed 15m bars for index context (DAY-08).

**Warmup policy for OOS (PREDEFINED):**
- The OOS series is the research-window bars (2026-07-02 → 2026-09-25, already seen) **concatenated** with the OOS bars.
- Research-window bars serve only as indicator history, which gives at least 20 prior sessions of RVOL baseline.
- **Trades are counted only for signals whose signal bar falls inside an OOS session.** A position cannot be carried over, because there are no overnight positions.

## 2. Dataset roles

| Role | Definition | Status |
|---|---|---|
| A. Research | the existing frozen window: 2026-07-02 → 2026-09-25, 60 RTH sessions, `data/cache`. Already used by DAY-04..DAY-12B, so any result there is **exploratory** | PREDEFINED |
| B. Validation | **none** in this cycle. The research window is already exhausted and splitting it further would reuse inspected data. A validation period could only come from data after the OOS period, in a later protocol version. | PREDEFINED |
| C. OOS | the first **N = 60** complete NYSE RTH sessions strictly after 2026-09-25 | PREDEFINED |

## 3. OOS period: deterministic rule

- **Rule:** OOS = the first 60 NYSE trading sessions strictly after the research-window end (2026-09-25), counting full and scheduled early-close sessions and skipping exchange holidays.
- **Why 60:** it equals the research-window length. The number is fixed here, before any OOS bar has been acquired or viewed; it is not chosen from market behaviour.
- **Projected calendar (for planning only).** Computed from weekdays minus the holidays 2026-11-26 (Thanksgiving) and 2026-12-25:
  - first session 2026-09-28;
  - 20th session 2026-10-23;
  - 40th session 2026-11-20;
  - **60th session 2026-12-21**.
- **Authority:** the rule is authoritative, not the projected dates. At acquisition time the session list must be verified against the official NYSE calendar (`pandas_market_calendars` is not installed — OPEN QUESTION as to which calendar source is used). If an unscheduled closure occurs, the rule still selects the first 60 actual sessions.
- **Early-close sessions:** the expected one is 2026-11-27 (13:00 ET); 2026-12-24 is after session 60. They are included and flagged. Existing behaviour: no 15:55 bar, so positions exit at the close of the last bar through the session-change rule. Expected bar count: 42 × 5m / 14 × 15m.
- **Partial OOS:** if fewer than 60 sessions can be acquired, for example because of the provider window, the OOS set is the acquired prefix. It is reported as incomplete; sessions are never back-filled from another provider.

## 4. Acquisition procedure (to be implemented later; nothing run in DAY-14)

**Constraint:** yfinance serves 5m/15m history only for about the last 60 days (`PERIOD_INTRADAY_FAST="60d"`). Under a calendar-day reading of that limit (OPEN QUESTION), bars from 2026-09-28 stop being retrievable around **2026-11-27**.

**Snapshot schedule (PREDEFINED):**
- capture at least every **20 sessions**: after sessions 20, 40 and 60, i.e. ≈ 2026-10-23, 2026-11-20 and 2026-12-21;
- the first snapshot must happen before ≈ 2026-11-27;
- additional earlier snapshots are allowed and do not count as inspection.

**Isolation (PREDEFINED):**
- snapshots are written to a **separate write-once tree**, never into `data/cache`;
- the existing `YFinanceProvider._write_cache` writes into `data/cache` and must **not** be used for acquisition;
- the tests' cache guard (`tests/conftest.py`) already rejects writes to `data/cache`.

**Folder layout (specified, not created):**
```
data/oos_cache/
  protocol_v1.0/
    snapshots/
      <YYYYMMDD_capture>/            # write-once; one per capture
        {SYM}_5m.parquet
        {SYM}_15m.parquet
        capture.json                 # provider, version, call params, UTC capture time, python, pip freeze digest
        manifest.json                # per-file SHA-256, row counts, first/last bar
        structural_checks.json       # §5 results only
    merged/                          # built only after all snapshots, append-only
      {SYM}_5m.parquet  {SYM}_15m.parquet
      merge_report.json              # overlap equality per symbol-session, conflicts listed
      manifest.json
artifacts/day14/                     # this spec (already frozen)
```

**Merge rule (PREDEFINED):**
- For each symbol-session, take the bars from the **earliest** snapshot that contains the complete session.
- Overlapping sessions present in several snapshots must be identical in OHLCV. Any difference is recorded in `merge_report.json`, the symbol-session is flagged, and nothing is silently overwritten (this is also how corporate-action adjustments are detected).

**Immutability (PREDEFINED):**
- after `manifest.json` is written, snapshot files are read-only;
- every later use recomputes and compares the SHA-256 manifest;
- a mismatch invalidates the run.

## 5. Structural checks allowed before the OOS gate (no strategy information)

These are permitted on OOS data before a candidate is frozen. They do not count as inspection:

| Check | Expectation |
|---|---|
| Session list | equals the NYSE calendar list for the rule in §3; missing sessions listed |
| Bar count per full session | 78 × 5m (09:30 … 15:55 opens) and 26 × 15m (09:30 … 15:45 opens); early close 42 × 5m / 14 × 15m |
| Missing bars | bar opens absent from the expected grid, per symbol-session |
| Duplicates | duplicate timestamps (expected 0) |
| Monotonicity | strictly increasing index (expected) |
| OHLC consistency | high ≥ max(open, close), low ≤ min(open, close), high ≥ low |
| Volume | ≥ 0; zero-volume count reported |
| RTH filter | no bar outside 09:30 ≤ t < 16:00 ET |
| Timezone | index tz-aware UTC; DST sessions have the full 78-bar grid |
| 5m/15m consistency | 15m bars aggregate to the same session coverage as 5m (coverage only, not prices) |
| Hash manifest | per-file SHA-256 recorded and re-verified |

**Forbidden before the OOS gate passes:** computing signals, setups, indicators for trading, returns, P&L, R, any strategy or benchmark metric, or plotting prices. Viewing summary price statistics (for example the period return of a symbol) also counts as inspection.

## 6. Dataset split summary

```
|-- warmup/indicator history --|------------------- OOS (untouched) -------------------|
|  Research (exploratory)      |  first 60 NYSE sessions after 2026-09-25               |
|  2026-07-02 .. 2026-09-25    |  projected 2026-09-28 .. 2026-12-21 (rule governs)    |
|  60 sessions, data/cache     |  data/oos_cache/protocol_v1.0 (not yet acquired)       |
```

No validation period exists in this cycle. The OOS period may be evaluated only after `research-protocol.md` §11 passes for a candidate whose protocol is committed **before** the first OOS snapshot is merged.

## 7. Open questions specific to data

1. Intraday `auto_adjust=True` semantics and retroactive adjustment (detected through overlap comparison, §4).
2. The exact yfinance 60-day window definition, which sets the snapshot deadline.
3. Calendar source for NYSE sessions (no calendar library installed).
4. Whether yfinance ever returns a partially formed final bar inside a "complete" session. The capture must start after 16:00 ET plus a buffer; the buffer length is NOT PREDEFINED.
5. The acquisition and merge tool is NOT YET IMPLEMENTED and requires explicit approval before it is written.
