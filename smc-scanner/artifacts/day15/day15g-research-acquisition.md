# DAY-15G — v1.1 Research Acquisition Report (structural only)

> **NO SIGNAL/PERFORMANCE ANALYSIS WAS PERFORMED.** No indicators, setups, trades, returns, P&L, R-multiples, win rate, profit factor, drawdown, benchmark or research-gate values were computed. Price values were not inspected. Only counts, timestamps, schema and hashes were examined.

## Status: **COMPLETE** — 4,050 / 4,050 units

| Item | Value |
|---|---|
| Protocol | v1.1, `artifacts/day15/protocol-v1.1.md` (SHA-256 `2b096cb5dd372d23cccda5e21ab410842730638c4dd7104a87383fa0e7746592`, committed in `57f4ece`) |
| Acquisition code commit | `57f4ecefc5861476d1b5ce43611cafe810843fb3` (Commit A). The task text gave `…810843fb`, which is the same hash with its last 3 characters missing; HEAD was verified as the full hash above. |
| Provider / endpoint | Alpaca Market Data v2, `GET https://data.alpaca.markets/v2/stocks/{symbol}/bars` (direct REST via `requests`; alpaca-py SDK and `data/alpaca_provider.py` not used) |
| Feed / adjustment | `feed=sip` / `adjustment=raw` |
| Request shape | one request per (session, symbol, interval); `start` = session open, `end` = **last bar open**. Alpaca `end` is inclusive. Fixed parameters: `limit=10000`, `sort=asc` |
| Capture | started 2026-10-06T09:52:01Z, finished 2026-10-06T10:46:38Z |
| Snapshot | `data/oos_cache/protocol_v1.1/research/snapshots/research_20261006T095201Z/` (write-once, read-only; 19 MB; git-ignored) |
| Derived manifest | `data/oos_cache/protocol_v1.1/research/manifest.json` (SHA-256 `11e0a3a0…2b3c40`) |
| Integrity report | `artifacts/day15/day15g-integrity.json` (SHA-256 `7b5b8bfb…3de278`) |
| Environment manifest | snapshot `environment.json` (file SHA-256 `e4c6a886…cd65ad`; `environment_sha256` `fa46ed65…f39b26`, the same Python 3.12.10 + distribution set as DAY-15B); clean git tree at capture |

## Access verification

| Interval | Probe | Result |
|---|---|---|
| 5Min | DAY-15E (`day15e-alpaca-access.md`), AAPL 2026-07-02 13:30–13:35Z | HTTP 200, 2 bars, inclusive `end`, bar-start labels |
| 15Min | DAY-15G (`day15g-alpaca-15m-access.md`), AAPL 2026-07-02 13:30–13:45Z | HTTP 200, 2 bars, inclusive `end`, bar-start labels |

## Implementation (Commit A)

**Files:**
- `acquisition/v1_1/`: `contract.py`, `sessions.py`, `alpaca_client.py`, `validation.py`, `snapshot.py`, `ledger.py`, `research.py`, `environment.py`, `__init__.py`;
- `tests/test_day15g_v11_acquisition.py`.

v1.0 acquisition code is unchanged.

| Topic | Implementation |
|---|---|
| Provider contract | `AlpacaBarsConfig` (frozen): `sip`, `raw`, `limit` 10000, `sort` asc, `end_semantics="inclusive"`; credentials only in headers, never in records |
| Inclusive end | callers pass the last wanted bar OPEN as `end`; the yfinance exclusive convention is not used; covered by tests |
| Pagination | follows `next_page_token` until null; identical cross-page duplicates are collapsed and counted, conflicting ones raise; stable chronological sort |
| Retry | up to 4 attempts per page on 429/5xx/connection errors, sleeps 2/5/15 s; 401/403 are fatal (abort, no retry, no substitution) |
| Normalization | UTC tz-aware index = bar START; `open, high, low, close, volume` + `trade_count` (`n`) + `provider_vwap` (`vw`); no `adj_close` |
| Timestamps / calendar | `exchange_calendars` 4.13.2 XNYS; expected bars derived from each session's open/close (`acquisition.validation.expected_bar_opens`), never hard-coded |
| RTH / extended hours | requests bounded to `[open, last bar open]`, so the provider returned no extended-hours rows. Any extended rows would have been counted and kept out of the canonical files, under `raw/` for provenance only. |
| VWAP policy | `provider_vwap` is provenance only; strategy VWAP stays `indicators/vwap.py::compute_vwap` from OHLCV |
| OOS guard | `assert_not_oos` (session ≥ 2026-09-29 rejected); an explicitly passed OOS / stage session is rejected, not dropped; the client refuses `end` > 2026-09-28 close; all checks run before any request |

## Dataset

| Segment | Sessions | First | Last |
|---|---|---|---|
| Warmup (indicator history only; never traded) | 20 | 2026-06-03 | 2026-07-01 |
| Research | 60 | 2026-07-02 | 2026-09-25 |
| Embargo (context only: no signal, trade or metric) | 1 | 2026-09-28 | 2026-09-28 |
| **Total** | **81** | | |

- **Symbols (frozen 25, sorted):** AAPL, ADBE, AMAT, AMD, AMZN, AVGO, COST, CRM, CSCO, GOOGL, INTC, JNJ, JPM, KO, META, MSFT, MU, NFLX, NVDA, ORCL, PEP, QCOM, TSLA, WMT, XOM.
- **Intervals:** 5m, 15m.
- **Early closes in the window:** none (calendar). Expected bars: 78 × 5m / 26 × 15m for every session.

| | Value |
|---|---|
| Expected units (81 × 25 × 2) | **4,050** |
| Units accounted for (unique) | 4,050 (no duplicates, no unexpected unit) |
| COMPLETE | **4,050** |
| Failed (MISSING) / structural fail / partial / not requested | 0 / 0 / 0 / 0 |
| Embargo units classified `embargo` | 50 (25 × 2) |
| Data files | 50 (`{SYM}_{5m,15m}.parquet` + `.meta.json`); no `raw/` files |
| Rows 5m | 157,950 = 25 × 81 × 78 |
| Rows 15m | 52,650 = 25 × 81 × 26 |
| Maximum requested `end` | `2026-09-28T19:55:00Z` (last 5m bar open of the embargo session) |

## Integrity

**Structural totals over all 4,050 units:**
- missing bars 0;
- duplicate timestamps 0;
- off-grid bars 0;
- extended-hours rows 0;
- NaN required cells 0;
- OHLC-inconsistent rows 0;
- non-positive price rows 0;
- negative-volume rows 0;
- non-integer volume rows 0;
- zero-volume rows 0;
- cross-page duplicates 0.

**Requests:**
- 4,050 requests, each a single page;
- **0 retries, 0 errors**;
- no 401/403/429/5xx observed.

**Independent re-verification** (separate read-only script; index and schema only):
- every data file's SHA-256 equals `files.json` and its meta;
- every file's index is UTC, unique, monotonic and **exactly equal** to the union of the 81 calendar grids;
- the schema equals the v1.1 column set, with no `adj_close`;
- the ledger shows 4,050 accepted and 0 pending;
- unit segments match the calendar resolution;
- no session ≥ 2026-09-29.

**Immutability:**
- This is the first v1.1 snapshot, so no earlier snapshot existed to overwrite and IDENTICAL/DISCREPANCY: n/a.
- Files are read-only. A repeat run is a no-op (COMPLETE), and `--recheck` writes a new snapshot that is compared against this one.

**Hashes of the snapshot metadata:**

| File | SHA-256 |
|---|---|
| `run.json` | `8b57b2dad2c22b69dee25845ef6d4d3520811088124c35b3b668e6fb510a4278` |
| `units.json` | `6a0466192a87ce53cb27d8b5e55a4fb510f8e790d8cc75548b6e9987a3b76b74` |
| `files.json` | `b43b8996d1e45a58c61aba74bc8bc83b173809e554f4c0c125c0f4f5f6b95139` |
| `environment.json` | `e4c6a886647d2fe35b916a7907c7665a6c3e755c4bd3d39e7dbcbf08c5cd65ad` |

Per-file content and file hashes are in `files.json`, the per-file `.meta.json` and `day15g-integrity.json`.

**Frozen inputs untouched:**
- `data/cache/` and `artifacts/day04` → `day14` match `integrity-baseline.json` (16 dirs, 0 changed), checked by preflight before the run and again after.
- `data/oos_cache/protocol_v1.0/`: 103 files, none modified after its 2026-10-02 manifest.
- `day15g-integrity.json` records the hashes of all of these, plus the DAY-15 protocol documents.

## Safety

- The OOS guard was enforced in code before every request. **No OOS session (≥ 2026-09-29) was requested or downloaded.** The latest requested bar is 2026-09-28 15:55 ET.
- 2026-09-28 is stored only as EMBARGO context.
- **No signals, setups, trades, returns, P&L or performance metrics were calculated. No backtest was run. No research-gate analysis was done.**
- The yfinance research cache (`data/cache/`) and the v1.0 OOS snapshots were not modified.

## Tests (before Commit A)

Each command was a separate process: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <file>`.

| File | Result |
|---|---|
| `test_day15g_v11_acquisition.py` | 29 passed |
| `test_day15a_acquisition.py` | 37 passed |
| `test_day15b_acquisition.py` | 19 passed |
| `test_day15b_lifecycle.py` | 23 passed |
| `test_session.py` | 8 passed |
| `test_data_validation.py` | 8 passed |
| `test_cache_immutability.py` | 6 passed |
| `test_alpaca_provider.py` | 9 passed |
| `test_intraday_provider.py` | 6 passed |
| `test_factory.py` | 5 passed |

- **Total: 150 passed, 0 failed.** The only warning was a third-party `websockets.legacy` DeprecationWarning.
- OOS guard subset (`-k "oos or beyond_limit or past_embargo"`): 3 passed.
- `python -m compileall -q acquisition/v1_1`: OK.

Full offline suite was attempted once and terminated by the environment for memory pressure at approximately 45%, with no test failure observed before termination. Memory-safe focused regression was used instead.

## Git

| Item | Value |
|---|---|
| Implementation commit | `57f4ecefc5861476d1b5ce43611cafe810843fb3` (Commit A) |
| After acquisition, untracked | `artifacts/day15/day15g-integrity.json`, `artifacts/day15/day15g-research-acquisition.md` (this file), `day08-market-cache.tar.gz` (pre-existing) |
| Tracked changes | none |
| Market data in git | none (`data/oos_cache/` is git-ignored) |
| Commit after acquisition | **NO** |
| Push | **NO** |

**Next (separate task):** the DAY-04 baseline re-run on this SIP research dataset under protocol v1.1 §21. Not started.
