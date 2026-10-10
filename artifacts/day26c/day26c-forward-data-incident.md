# DAY-26C — Forward-Data Incident Record

| Field | Value |
|---|---|
| **Incident** | Unauthorised recent yfinance intraday download into `data/cache/` during DAY-26B test verification |
| **Severity** | Protocol breach: DAY-22 §3.2.3; protocol 2.1 C3, C15, C16 (forward-period market data acquired before permitted) |
| **Status** | **CONTAINED.** Files quarantined, root cause fixed, `fwd-diag` invalidated |
| **Recorded** | 2026-10-10 by Claude (implementation agent) for the protocol owner Alixujaev |
| **Machine-readable record** | `artifacts/day26c/day26c-forward-data-incident.json` (includes the full 54-file inventory) |

## 1. Timeline (UTC, 2026-10-10)

| Time | Event |
|---|---|
| 12:52:51 | Protocol 2.1 adoption recorded (`decided_utc`). `integrity_at_adoption` was true at that time. |
| 12:54:59–12:55:20 | Full suite run 1 (`pytest -q -p no:cacheprovider -x --ignore=smc-scanner`). 318 passed; it stopped at `tests/test_day07_backtest.py`, whose function-scoped guard blocked its download (`total_trades=0`). **Nothing written** to `data/cache` (verified absent afterwards). |
| ≈12:56:11 | Full suite run 2 started: same command plus a session plugin refusing Python socket connections, intended as network-blocked. |
| **12:56:23–12:59:51** | **54 files written to `data/cache/`** by `YFinanceProvider`, through module-scoped fixtures of `tests/test_day08*`…`test_day12b*`: `yf.download(period=60d, interval=5m/15m)` for 27 symbols. The requests went through curl_cffi (libcurl), which the socket plugin could not intercept; it reported 0 blocked attempts. |
| 12:56–13:37:02 | **The same run consumed the files.** Legacy day-trading backtests (DAY-08…DAY-12B experiments and the index regime; not V2-MOM) ran on them inside pytest. 27 tests failed, and the printed failure summaries included legacy trade-count values (e.g. `test_json_serialization - assert 5783 ==...`). 1406 passed, 2 skipped. |
| ≈13:4x | Breach discovered (listing by name, size and time only), reported, work stopped. |
| 14:19:25 | Containment: inventory (metadata and SHA-256, no parsing), all 54 files moved to quarantine, post-move SHA-256 verified, files set read-only, empty `data/cache` removed. |

**Correction:** the DAY-26B report said the files were written during the *first* full-suite run. The timestamps show they were written during the *second* (network-blocked) run. The first run wrote nothing.

## 2. Root cause

`tests/conftest.py` guarded `yf.download` and real-cache writes only through **function-scoped** autouse fixtures. Module-scoped fixtures, such as `tests/test_day08_backtest.py:42` `day08_run` → `get_provider()`, run before those guards, so the legacy provider downloaded and wrote the real cache unguarded.

Contributing factors:
- The full suite was run as a regression step, although it contains legacy tests that depend on a market-data cache that is absent from this fresh clone.
- A socket-level block was assumed to stop all network access, but yfinance uses libcurl.

## 3. Exposure

- The agent did not open, parse or view any market value in these files.
- Believed coverage (not inspected): `period=60d` intraday requested on 2026-10-10. That means roughly 60 calendar days up to 2026-10-09: Excluded-period sessions (≤ 2026-10-07) and **forward sessions 1–2 (2026-10-08, 2026-10-09)**.
- **No `fwd-gate` session could be exposed.** `fwd-gate` starts on 2026-11-06, which did not exist at download time.
- No V2-MOM forward metric was computed.
- Consumption: legacy (non-V2) backtests inside pytest, plus printed legacy trade counts.

## 4. Inventory and quarantine

| Field | Value |
|---|---|
| Files | 54 (27 symbols: the 25-stock universe + SPY + QQQ; intervals 5m and 15m) |
| Bytes | 6,298,075 |
| Written (mtime) | 2026-10-10 12:56:23 → 12:59:51 UTC |
| Quarantine | `C:\Users\user\Desktop\Own\trade-quarantine\day26c-forward-data-incident-20261010\`: outside the repository, `CACHE_DIR` and every application and test search path; read-only; **not deleted** (protocol-owner decision) |
| Integrity | SHA-256 of every file verified identical after the move |
| Per-file name, size, SHA-256, mtime, ctime | JSON record, `inventory.files` |

## 5. Corrective actions

1. **`tests/conftest.py`:** a session-wide hard guard, installed when the conftest is imported (before collection and before any module or session fixture). It refuses `yf.download`, `yf.Ticker.history`, `AlpacaProvider._fetch_raw`, real-cache `_write_cache` and non-local socket connects.
2. **`backtest/v2/forward.py`:**
   - `check_quarantine()` refuses forward access if any inventoried SHA-256 exists under `data/`;
   - `fwd-diag` is permanently refused;
   - `diagnostic_report` can only return `FWD-DIAG-INVALID (protocol-breach)`;
   - the adoption check requires this record to be pinned and committed.
3. **`tests/test_day26c_incident.py`:** regression tests for the guard, the quarantine and the diagnostic status.
4. The full pytest suite is not to be run in this repository for v2 work.

## 6. Status decisions

| Segment | Status |
|---|---|
| `fwd-diag` (sessions 1–21) | **`FWD-DIAG-INVALID (protocol-breach)`.** Final. No `fwd-diag` acquisition, validation, load or evaluation. S3–S5 cancelled. |
| `fwd-gate` (sessions 22–63) | **PENDING.** Blind, not evaluated. Dates (2026-11-06 → 2027-01-07), thresholds and calendar unchanged. |

## 7. Gate assessment

**The 42-session gate remains usable.**
- No gate-period data (≥ 2026-11-06) existed or exists, so the breach cannot reveal gate outcomes.
- Strategy config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` is frozen, and nothing was changed after the breach.
- The gate's initial decision (2026-11-05 close) ranks on TR(t−21)/TR(t−252), i.e. the 2026-10-07 close and earlier. The exposed forward sessions 2026-10-08/09 enter later decisions only as formation history, used mechanically by the frozen rules.
- `fwd-diag` sessions are structurally excluded from the gate sample.

## 8. Next permitted steps

| Step | When | Action |
|---|---|---|
| S1 | Now (protocol owner) | Commit `artifacts/day26b/*`, `artifacts/day26c/*` and the DAY-26B/26C code and tests. Forward access stays refused until they are committed unchanged. |
| S7 | After **2027-01-07 16:15 America/New_York (21:15 UTC)** | Preflight for `fwd-gate` (P1–P13; the F-D items of P13 don't apply because `fwd-diag` is invalid). |
| S8 | After S7 | `python -m acquisition.v2.stage_f --capture --segment fwd-gate --authorization <reference>` |
| S8b | After S8 | `python -m acquisition.v2.stage_f --validate <stage_f_fwd-gate_snapshot> --segment fwd-gate --expect-manifest-sha256 <sha>` |
| S9 | After `READY_FOR_FORWARD_EVALUATION` | `python -m backtest.v2.run --segment fwd-gate --out artifacts/day27/v2 --snapshot <id> --expect-manifest-sha256 <sha> --authorization <reference>` |

**Known blocker before S8 (pre-existing, not caused by the incident):** the Stage F capture runs `stage_h.preflight` → `stage_r.preflight` → `acquisition.run`, which checks the integrity baseline `artifacts/day15/integrity-baseline.json`. That baseline requires `data/cache` to equal 305 frozen DAY-15 legacy cache files. They are absent from this clone and are not in the research-data vault. A protocol-owner decision is required before 2027-01-07.
