# DAY-15A — OOS Acquisition Design (protocol v1.0)

**Status:** design and implementation of the acquisition layer, verified with offline tests. **No OOS market data was downloaded or inspected.** Live acquisition is disabled: `scripts/acquire_oos_data.py` without `--dry-run` exits with code 2. DAY-14 (`5d48c53`) is unchanged and governs.

## 1. Architecture

```text
scripts/acquire_oos_data.py      (DAY-15A: --dry-run only; live mode disabled)
  -> acquisition.pipeline.acquire_one
       -> acquisition.provider_adapter.YFinanceAdapter   (yfinance, every option explicit)
       -> acquisition.validation.structural_checks       (counts/flags only)
       -> acquisition.snapshot.build_metadata / write_snapshot   (write-once, SHA-256)
       -> acquisition.environment.capture_environment    (exact environment manifest)
  acquisition.sessions.resolve_oos_sessions              (UNRESOLVED: raises CalendarUnavailableError)
  acquisition.contract                                   (frozen constants, ProviderConfig)
```

**Independence:**
- The package imports only `config.day_universe`, pandas, numpy, yfinance and the standard library.
- It imports nothing from `strategy`, `signals`, `indicators`, `backtest`, `smc`, `levels`, `journal`, `risk`, `telegram_bot` or `data`.
- This is enforced by a static AST test and a subprocess `sys.modules` test.
- The existing `YFinanceProvider` and its `_write_cache` into `data/cache` are not used.

## 2. Contract (`acquisition/contract.py`)

| Constant | Value |
|---|---|
| Schema / protocol | `oos-snapshot/1.0` / v1.0 (`artifacts/day14/research-protocol.md`, commit `5d48c53`) |
| OOS rule | first 60 NYSE sessions strictly after 2026-09-25 |
| Universe | `config.day_universe.get_day_universe()`: the frozen 25 symbols; no additions or removals; missing sessions excluded, never replaced |
| Intervals | 5m (78 bars per full session), 15m (26); everything else rejected |
| RTH | 09:30 ≤ t < 16:00 America/New_York; storage tz UTC; index = bar OPEN |
| Provider config (all explicit) | `auto_adjust=False, back_adjust=False, prepost=False, actions=False, repair=False, keepna=False, ignore_tz=False, rounding=False, threads=False, progress=False, group_by="column", multi_level_index=False`; request by explicit `start` / `end` |
| Stored columns | open, high, low, close, adj_close, volume (raw OHLC plus Yahoo Adj Close) |
| Snapshot root | `data/oos_cache/protocol_v1.0/` |
| Refused write roots | `data/cache/`, `artifacts/` |

## 3. Snapshot layout

```text
data/oos_cache/protocol_v1.0/
  snapshots/<snapshot_id>/                 # e.g. 20261023_capture (one per capture run)
    environment.json                       # write-once environment manifest of this capture
    {SYM}_{interval}.parquet               # write-once, read-only after write
    {SYM}_{interval}.meta.json             # write-once metadata (schema below)
    attempts/<utc>_{SYM}_{interval}.json   # re-acquisition records (IDENTICAL / DISCREPANCY)
    conflicts/<utc>_{SYM}_{interval}.parquet  # differing re-acquired data, preserved separately
  merged/                                  # DAY-14 §4; built only after all snapshots (NOT YET IMPLEMENTED)
```

## 4. Metadata schema (`oos-snapshot/1.0`, per symbol/interval)

- `schema_version`, `protocol_version`, `snapshot_id`, `symbol`, `interval`;
- `acquisition_utc`, `requested_start`, `requested_end`, `session_rule`;
- `actual_first_timestamp`, `actual_last_timestamp`, `row_count`;
- `timezone` (UTC), `timestamp_semantics` ("bar OPEN …");
- `provider`, `provider_version`, `provider_config` (every `download` kwarg), `columns`;
- `content_sha256`, `file_sha256`;
- `structural_checks` (§6), `environment_sha256`, `git_commit`, `git_dirty`;
- `request` (the full request record, including `request_utc`).

Metadata is deterministic for identical inputs (tested).

## 5. Immutability, hashing and overlap

**Content hash.** `content_sha256` is the SHA-256 of a canonical serialisation:
- index sorted, as UTC int64 nanoseconds;
- the fixed column order;
- `repr(float64)` values.

It is independent of the parquet writer and of row order (tested). `file_sha256` hashes the stored parquet bytes.

**Write-once.**
- Files are created with exclusive-create mode (`'xb'`) and then made read-only.
- There is no overwrite, refresh or merge into an existing snapshot (tested: bytes unchanged).

**Re-acquisition of an existing snapshot.**
1. The stored file is re-verified against its recorded content hash; a mismatch raises an error.
2. If the new content hash is equal: status **IDENTICAL**, recorded in `attempts/`.
3. If it differs: status **DISCREPANCY**:
   - the new data is written separately to `conflicts/`, and the original is kept untouched;
   - the attempt record includes a cell-level overlap comparison;
   - nothing is chosen or replaced.

**Overlap comparison (`compare_overlap`).** It reports:
- common timestamps, rows only in A, rows only in B;
- differing rows, differing cells per column (open / high / low / close / adj_close / volume);
- the differing timestamps.

It never selects a winner. Discrepancies are data-integrity findings and never alter the research dataset.

## 6. Structural validation (allowed before the OOS gate)

`structural_checks(df, interval)` reports **counts and flags only**:
- index type, tz-aware UTC;
- first and last timestamp, row count;
- duplicates, monotonicity, NaN cells, missing columns;
- OHLC inconsistency, non-positive prices, negative volume, zero-volume count;
- off-grid bars, non-RTH bars, intra-session gaps;
- per-session bar counts compared with 78 / 26;
- `adj_close_equals_close_all_rows` / `adj_close_differs_rows`.

**Not computed** (a test asserts no such keys): returns, means, ranges, price summaries, indicators (RSI, VWAP, RVOL, ATR, BOS/CHoCH), signals, P&L, benchmark or any strategy metric.

Sessions shorter than full length are flagged, not classified: an NYSE calendar is required to tell early closes from missing bars (UNRESOLVED).

The adapter performs no row cleaning (no dedup, no NaN drop, no RTH filter), so problems surface in the checks.

## 7. OOS pre-gate separation

| Allowed before the gate | Forbidden before the gate |
|---|---|
| fetch raw bars, write-once storage | signal counts / timestamps, setup distributions |
| structural checks (§6), hashes, manifests | indicators of any kind |
| overlap comparison between snapshots (equality only) | returns, P&L, R, strategy metrics |
| `adj_close == close` flag (counts) | benchmark returns, price summaries or plots |

The acquisition package cannot reach the strategy, indicator or backtest code by construction (separation tests). Running any research code on `data/oos_cache` before the gate is a protocol violation (DAY-14 §11).

## 8. Environment and dependency capture

- `requirements.txt` is unpinned and there is no lock file (VERIFIED).
- `capture_environment()` records:
  - the Python version, executable and platform;
  - every installed distribution `name==version` (`importlib.metadata`, the equivalent of `pip freeze`) and its SHA-256;
  - the git commit, dirty flag and dirty files;
  - an overall `environment_sha256`.
- Every snapshot writes its own `environment.json` (write-once), and each meta file carries `environment_sha256`.
- Reference capture at DAY-15A: `artifacts/day15/environment-manifest-day15a.json` (53 distributions; yfinance 1.6.0). It is reference evidence, not a lock.
- **Recommendation before DAY-15B:** commit the DAY-15A code so that acquisition runs on a clean tree (`git_dirty=false`). No dependency-manager migration is proposed.

## 9. NYSE calendar dependency (UNRESOLVED; blocks DAY-15B)

- Neither `pandas_market_calendars` nor `exchange_calendars` is installed, and the repository has no NYSE calendar.
- `resolve_oos_sessions()` raises `CalendarUnavailableError`, and the dry run reports `oos_sessions_status: UNRESOLVED`.
- No holiday list is invented.
- **Required before DAY-15B:** an approved, version-pinned calendar source, recorded in the environment manifest. It is used only to enumerate session dates and early closes, never market data.

## 10. Boundary: DAY-15A vs DAY-15B

| DAY-15A (this phase, done) | DAY-15B (not started) |
|---|---|
| provider verification (offline) | approve and pin an NYSE calendar source; resolve the 60 sessions |
| contract, adapter, validation, write-once snapshot, overlap compare, environment capture, pipeline step | enable live mode in the CLI (with a dry-run diff first) |
| offline tests with a fake provider | take capture snapshots on the DAY-14 schedule (≤ 20 sessions apart; first before ≈ 2026-11-27 under the INFERRED 60-day reading) |
| dry-run CLI, live mode disabled | review structural reports and `adj_close` flags (no strategy information) |
| documentation | merge tool (`merged/`, append-only, overlap equality) — NOT YET IMPLEMENTED |

## 11. DAY-15B readiness checklist

> **Superseded status (DAY-15A finalization):** the blockers below were resolved in `day15a-finalization.md` (calendar exchange_calendars 4.13.2 XNYS, capture wait 16:15 ET, corporate-action policy, clean commit). Live capture is now `--capture` with a mandatory preflight.

| Item | State |
|---|---|
| Acquisition contract, adapter, validation, snapshot, overlap, environment, pipeline | READY (37 offline tests) |
| Separation from strategy / indicators / backtest | READY (tested) |
| Research cache protection | READY (write refusal plus conftest hash guard) |
| NYSE calendar source | **NOT READY (UNRESOLVED)** |
| Live CLI mode | disabled by design |
| Capture buffer after the 16:00 ET close | NOT PREDEFINED |
| Corporate-action handling rule inside the OOS window | NOT PREDEFINED |
| DAY-15A code committed (clean tree for acquisition) | pending user review |
| Merge tool for `merged/` | NOT YET IMPLEMENTED (needed only after the last snapshot) |

**Verdict: the acquisition layer is NOT READY for DAY-15B.** The single hard blocker is the unresolved NYSE calendar. The remaining items (capture buffer, corporate-action rule, commit) must be decided and committed before the first live capture. Because of the provider window, the first capture should happen well before ≈ 2026-11-27.
