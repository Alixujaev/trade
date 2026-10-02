# DAY-15A — Provider Verification (yfinance)

**Scope:** verifies provider behaviour relevant to OOS acquisition **without any network call**.

**Evidence sources:**
1. the installed yfinance source (`.venv/Lib/site-packages/yfinance`, version 1.6.0);
2. the project's own provider and validation code;
3. read-only inspection of the existing **research** cache (`data/cache`, 2026-07-02 → 2026-09-25).

**No OOS data was downloaded or inspected.**

**Labels:**
- **VERIFIED:** confirmed in source code or in the research cache.
- **INFERRED:** follows from the source code but depends on what Yahoo's server sends, which cannot be observed offline.
- **UNRESOLVED:** must be settled before or during DAY-15B.

---

## 1. Version

| Item | Finding | Label |
|---|---|---|
| yfinance | 1.6.0 (`yfinance/version.py`, `importlib.metadata`) | VERIFIED |
| Related packages | pandas 3.0.5, numpy 2.5.2, pyarrow 25.0.1, requests 2.34.2, curl_cffi 0.16.1 (`environment-manifest-day15a.json`) | VERIFIED |
| Pinning | `requirements.txt` lists unpinned names (yfinance, pandas, numpy, pyarrow, …); no lock file in the repository | VERIFIED |

## 2. Supported intervals

| Item | Finding | Label |
|---|---|---|
| 5m, 15m | listed as valid in `TickerBase.history()` docstring ("1m,2m,5m,15m,30m,60m,90m,1h,…") | VERIFIED |
| Project usage | `YFinanceProvider` supports 5m and 15m; research cache files `{SYM}_5m.parquet`, `{SYM}_15m.parquet` | VERIFIED |
| 30m | fetched from Yahoo as 15m and resampled client-side (source comment); not used by this project | VERIFIED |
| 1m | not required; rejected by the acquisition contract | VERIFIED (contract) |

## 3. Intraday history limitation

| Item | Finding | Label |
|---|---|---|
| Documented limit | `history()` docstring: "Intraday data cannot extend last 60 days" | VERIFIED |
| Client-side enforcement | only for `period="max"`: start = end − 5,184,000 s (60 days) for 2m/5m/15m/30m/90m | VERIFIED |
| `period="60d"` or start/end | passed to Yahoo as `range` or `period1/period2`; the 60-day cut-off is applied by Yahoo's server | INFERRED |
| Exact definition | calendar vs trading days, inclusivity, and behaviour when start is older than the limit (error vs truncation) | **UNRESOLVED** |
| Research cache consistency | the 5m cache spans exactly 60 RTH sessions (2026-07-02 → 2026-09-25), consistent with a `period="60d"` request made near 2026-09-25 | VERIFIED (data) |

**Design implication:** a session can be fetched only while it lies inside the provider window. The first OOS session (2026-09-28, projected) leaves a 60-calendar-day window around 2026-11-27 under the INFERRED reading. That is why DAY-14 requires snapshots at least every 20 sessions. The acquisition adapter requests explicit `start` / `end`, never `period`.

## 4. Timestamp and timezone semantics

| Item | Finding | Label |
|---|---|---|
| yfinance intraday index | `history()` localises quotes with `utils.set_df_tz(quotes, interval, tz_exchange)`, so the index is tz-aware in the exchange timezone (America/New_York for these symbols) | VERIFIED (source) |
| `download()` | `ignore_tz` defaults to False for intraday; the index stays tz-aware in the most common exchange tz (docstring; before 1.4.0 it was UTC) | VERIFIED (source) |
| DST quirks | `utils.fix_Yahoo_dst_issue` is applied to intraday quotes | VERIFIED (source) |
| Project conversion | `data/validation.py::validate_ohlcv` converts to UTC (naive is localised as UTC); research cache index is tz-aware **UTC** | VERIFIED (code and data) |
| Acquisition conversion | `acquisition.provider_adapter.normalize_frame` converts tz-aware to UTC and **refuses** a naive index instead of guessing | VERIFIED (tests) |
| ET conversion | sessions and RTH evaluated via `tz_convert("America/New_York")` (`data/session.py`, `acquisition/validation.py`) | VERIFIED |
| **Bar timestamp = bar OPEN** | research cache: first 5m bar of every session 09:30 ET, last 15:55 ET; 15m first 09:30, last 15:45; exactly 78 (5m) / 26 (15m) bars per session; 0 off-grid, 0 non-RTH, 0 duplicates, monotonic (checked on AAPL, SPY, KO). A bar-close convention would end at 16:00. | VERIFIED (data) |
| Frozen convention (unchanged) | signal usable at `bar_open + interval`; entry at the next eligible 5m bar OPEN | VERIFIED (DAY-08B audit, `backtest/execution.py`) |

## 5. Adjustment semantics

| Item | Finding | Label |
|---|---|---|
| `download()` default | `auto_adjust=True`, `back_adjust=False`, `repair=False`, `actions=False` | VERIFIED (source) |
| Research cache call | `YFinanceProvider` passes `auto_adjust=True` explicitly; the stored columns are open/high/low/close/volume (no Adj Close) | VERIFIED (code and data) |
| How `auto_adjust` works | `utils.auto_adjust` multiplies Open/High/Low by `Adj Close / Close` and replaces Close with Adj Close | VERIFIED (source) |
| Where Adj Close comes from | `utils.parse_quotes`: `adjclose = closes` unless the Yahoo response contains `indicators.adjclose`; then the ratio is exactly 1 and auto_adjust changes nothing | VERIFIED (source) |
| Do intraday responses contain `adjclose`? | not observable offline | **UNRESOLVED** (INFERRED: absent, so intraday prices are raw under both settings) |
| Retroactive revision of past intraday bars after a split or dividend | not observable offline | **UNRESOLVED** |

**Decision for the acquisition layer (user decision, DAY-15A):**
- `auto_adjust=False` is passed **explicitly**, together with every other `download` option; nothing relies on defaults.
- Raw OHLC is stored together with Yahoo's `Adj Close` as `adj_close`.
- Structural checks record `adj_close_equals_close_all_rows` and `adj_close_differs_rows` (counts only).

**Compatibility with research data:**
- If `adj_close == close` on every row, the stored OHLC is identical to what `auto_adjust=True` would have produced (ratio 1), so OOS bars are price-compatible with the research cache. INFERRED; confirmed per snapshot in DAY-15B.
- If any row differs, the snapshot is **flagged** as an adjustment discrepancy. The research convention is not silently switched; the issue must be resolved explicitly before the OOS gate.

## 6. Corporate actions

- `actions=False`: split and dividend events are not returned with the bars (VERIFIED, contract). The acquisition never adjusts prices itself.
- A split inside the OOS window would create a raw price discontinuity in unadjusted intraday bars. It is detected through the `adj_close` flag and/or overlap discrepancies between snapshots (§ acquisition-design 5). The handling rule is **UNRESOLVED / to be predeclared** before the OOS gate.
- Comparability with the research window (where the same INFERRED raw-intraday behaviour applies) holds only if no adjustment is applied in either; this is verified per snapshot by the flag.

## 7. RTH and extended hours

| Item | Finding | Label |
|---|---|---|
| `prepost=False` | requested explicitly; yfinance additionally removes unrequested pre/post bars using the response's `tradingPeriods` (`fix_Yahoo_returning_prepost_unrequested`) | VERIFIED (source) |
| Project RTH | 09:30 ≤ t < 16:00 America/New_York (`data/session.py::is_rth`) | VERIFIED |
| Acquisition | non-RTH bars are not dropped; they are **flagged** as a structural error | VERIFIED (tests) |
| Pre/after-hours storage | not stored in this cycle (DAY-14 extended-hours policy) | VERIFIED (contract) |

## 8. Other provider behaviours relevant to integrity

| Behaviour | Finding | Label |
|---|---|---|
| Duplicate timestamps | yfinance keeps the **first** duplicate (`df[~df.index.duplicated(keep='first')]`); the project's `validate_ohlcv` keeps the **last**. The acquisition adapter does not deduplicate; duplicates are counted and fail the structural check. | VERIFIED |
| NaN / zero rows | with `keepna=False`, yfinance drops rows whose data columns are all NaN or zero, so missing bars appear as gaps. They are detected by per-session bar counts and gap counts. | VERIFIED (source) |
| Volume | `fillna(0).astype(int64)`, so a NaN volume becomes 0 and shows up in the zero-volume count | VERIFIED (source) |
| Live / forming bar | `fix_Yahoo_returning_live_separate` applies to all intervals, intraday included. When the last two rows fall in the same interval it merges Yahoo's separate "live" row into the bar. So while a session is open, the final bar can be a forming bar. Capture must happen after the session close; the buffer length is NOT PREDEFINED. | VERIFIED (source) / buffer UNRESOLVED |
| Network blocking in tests | `tests/conftest.py` replaces `yfinance.download` and blocks sockets; acquisition tests use a fake `download` | VERIFIED |

## 9. Unresolved questions (blocking or relevant for DAY-15B)

1. **NYSE calendar source:** none installed, and DAY-15A does not invent holidays. **Blocks DAY-15B.**
2. Exact yfinance/Yahoo 60-day window semantics; this sets the deadline for the first snapshot.
3. Whether intraday responses carry `adjclose` and whether past intraday bars are revised after corporate actions. Answered empirically by the first DAY-15B snapshot's `adj_close` flag and by overlap comparisons.
4. The handling rule for a corporate action inside the OOS window. It must be predeclared before the OOS gate.
5. The capture buffer after 16:00 ET, to avoid forming bars.
