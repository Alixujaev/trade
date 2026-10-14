# ORB — SIP 5m data availability (read-only check)

Date: 2026-10-14. Scope: local files only. No network/API call, no download, no backtest, no paper runner, no orders, no code/config/data change. The only file written is this report.

## 1. Locations checked

| Location | Interval | Provider / feed (as recorded) | Period | Usable for ORB 5m SIP? |
|---|---|---|---|---|
| `data/oos_cache/protocol_v1.1/research/snapshots/research_20261006T095201Z/` | 5m + 15m, RTH | Alpaca Market Data v2, `feed=sip`, `adjustment=raw` | 2026-06-03 → 2026-09-28 (81 sessions) | **Yes, the only 5m SIP set in the repo** |
| `data/cache/<T>_5m.parquet` (+ `_5m_ext`, `_15m`) | 5m | **yfinance** (DAY-14 spec line 24; DAY-15C line 56). No per-file metadata | 2026-07-02 → 2026-09-25 (60 sessions) | No, not SIP |
| `data/oos_cache/protocol_v1.0/snapshots/capture_20261002T0636ET_s001-s004/` | 5m + 15m | yfinance 1.6.0 (`meta.json`) | 2026-09-28 → 2026-10-01 (4 sessions) | No, not SIP |
| `data/oos_cache/protocol_v2/stage_r/…`, `stage_h/…` | **1Day** | Alpaca, `feed=sip` (`run.json`, 104 requests each) | daily history | No: daily only |
| `paper_state/data/2026-10-12-da42c150fe38/bars_raw/` | daily (445 rows, 2025-01-02 → 2026-10-12) | V2-MOM paper runner | — | No: daily only |
| `data/cache/alpaca_*_4h.parquet` | 4h | Alpaca via `data/alpaca_provider.py` (IEX hard-coded) | — | No |

No other 5m parquet exists outside `.venv`.

## 2. v1.1 research snapshot: source evidence

The snapshot is **not new data**. It was acquired on 2026-10-06 (DAY-15G, git `57f4ece`) and already used for the DAY-15H V2-MOM re-baseline.

Recorded source (repo evidence):
- Every `<T>_{5m,15m}.meta.json` (50/50) and `run.json`: `provider=alpaca-market-data-v2`, `base_url=https://data.alpaca.markets/v2/stocks`, `feed=sip`, `adjustment=raw`, `rth_only=true`.
- `units.json`: 4,050 / 4,050 request units with `params.feed = "sip"`, all pages HTTP 200 with an `X-Request-ID`, all `checks.passed = true` (no missing/off-grid bars, no NaN, no zero or negative volume).
- `environment.json`: direct REST via `requests`. The `alpaca-py` SDK and the IEX-hard-coded `data/alpaca_provider.py` were **not** used.
- Integrity: the `file_sha256` of all 50 parquet files matches `data/oos_cache/protocol_v1.1/research/manifest.json` (0 mismatches, recomputed in this check). The ledger records 4050/4050 complete.

Entitlement and subscription documents:
- `artifacts/day15/day15e-alpaca-access.md`: an in-sample `feed=sip` 5Min request returned HTTP 200 with no subscription error. SIP historical entitlement: **VERIFIED**. Plan tier "Basic (free)": **INFERRED** from the 200/min rate limit.
- `artifacts/day15/day15g-alpaca-15m-access.md`: same check for 15Min, VERIFIED.
- `artifacts/day15/day15c-provider-audit.md`: Alpaca docs say the Basic plan allows historical SIP except the latest 15 minutes, and that `feed` takes the values sip/iex/boats/otc.
- `artifacts/day15/day15g-research-acquisition.md`: the acquisition contract (`AlpacaBarsConfig` frozen, `sip`, `raw`).
- `artifacts/day17/day17-data-blockers.md` §4: SIP 1Day entitlement probe (relevant to stage R/H only).

**Confirmation level:** SIP is confirmed **from the repo's own records**: request parameters, HTTP 200 per request, entitlement probes, and matching hashes. The records show that the API accepted `feed=sip` and returned data under it. The bar values themselves contain nothing that independently proves they are consolidated volume, and no external cross-check (e.g. against another consolidated vendor) was done here. The subscription tier is inferred, not documented by an account statement.

## 3. Coverage per ticker (5m, RTH)

Universe = `config/day_universe.py::FROZEN_DAY_UNIVERSE` (25 tickers, identical to the snapshot). Times are UTC bar starts (13:30Z = 09:30 ET; 19:55Z = 15:55 ET). Every session has exactly 78 bars for every ticker.

Columns: total 5m bars; bars by segment W = warmup 2026-06-03..07-01 (20 sessions), R = research 07-02..09-25 (60), E = embargo 09-28 (1).

| Ticker | Start | End | 5m bars | W / R / E | Source | Source confirmed |
|---|---|---|---|---|---|---|
| AAPL | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| ADBE | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| AMAT | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| AMD | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| AMZN | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| AVGO | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| COST | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| CRM | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| CSCO | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| GOOGL | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| INTC | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| JNJ | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| JPM | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| KO | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| META | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| MSFT | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| MU | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| NFLX | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| NVDA | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| ORCL | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| PEP | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| QCOM | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| TSLA | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| WMT | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |
| XOM | 2026-06-03 13:30 | 2026-09-28 19:55 | 6318 | 1560 / 4680 / 78 | Alpaca SIP (v1.1 snapshot) | Yes (repo records) |

For comparison, the ORB smoke-test input `data/cache/<T>_5m.parquet` covers all 25 tickers (plus BAC, QQQ, SPY; QQQ/SPY start 2026-07-08) with 4,680 bars each over 2026-07-02 13:30 → 2026-09-25 19:55. Its source is **yfinance** (not SIP) and is not recorded per file.

## 4. SIP data outside 2026-07-02 → 2026-09-25

Only these SIP 5m sessions exist locally outside the ORB development window:

| Segment | Sessions | Dates | 5m bars per ticker | v1.1 protocol role |
|---|---|---|---|---|
| Warmup | 20 | 2026-06-03 → 2026-07-01 | 1,560 | "indicator warmup only. No trades. No performance evaluation." (`protocol-v1.1.md` §4) |
| Embargo | 1 | 2026-09-28 | 78 | explicit embargo; "partly inside the development information set" (`protocol-v1.1.md` §3.2) |

No SIP 5m bars exist locally for any other date: nothing before 2026-06-03 and nothing after 2026-09-28. No other dates are assumed.

Caveats for using the 20-session warmup for ORB:
- 20 sessions × 25 tickers is one third of the 60-session smoke test, so ORB would produce roughly 30 trades at the smoke test's rate (95 / 60 sessions). That is too few for a meaningful test.
- The v1.1 protocol froze this range as warmup-only for V2-MOM. DAY-15H simulated it, but under the same protocol it was "never evaluated". Using it as an ORB test sample is a new protocol decision, not something the existing protocol covers.
- The ORB earnings calendar `config/earnings_calendar.csv` covers only 2026-07-02 → 2026-09-25. It has **no entries for June 2026**, so the ORB earnings filter cannot run on the warmup range without a new, source-verified calendar.
- SIP volume differs from yfinance volume. Any ORB volume-ratio threshold derived on `data/cache` would not transfer 1:1.

## 5. Inconsistency found (corrected 2026-10-14)

`artifacts/orb/smoke_test/report.md` (line 6), `artifacts/orb/diagnostics_v2/report.md` (lines 3, 49) and `artifacts/orb/diagnostics/report.md` (lines 61, 78) described the `data/cache` 5m data as "IEX". The repo provenance (`artifacts/day14/data-expansion-spec.md` line 24, `artifacts/day15/day15c-provider-audit.md` line 56: "all in-sample research (DAY-04 → DAY-12B) used the yfinance 5m cache") identifies it as **yfinance**. No file metadata says IEX.

A later read-only check compared `data/cache` volume with this SIP snapshot. The aggregate ratio was 1.005–1.068 per ticker, which rules out single-venue IEX volume. The labels were corrected to yfinance, with the per-file provenance gap stated. See `artifacts/orb/provenance_correction.md`.

## 6. Conclusion

- **SIP 5m data exists:** only the v1.1 research snapshot, covering the 25 tickers from 2026-06-03 to 2026-09-28 (81 sessions, 78 bars/session, complete and hash-verified).
- **Source:** confirmed as Alpaca `feed=sip` by the repo's own request logs, metadata and entitlement probes. It is not independently verified against an external consolidated source, and the plan tier is inferred.
- **Outside 2026-07-02 → 2026-09-25:** only 20 warmup sessions (2026-06-03 → 07-01) and 1 embargo session (2026-09-28).
- **Ready for the next ORB test: no.** The non-overlapping SIP sample is too small, it is protocol-restricted as warmup/embargo, and it has no earnings-calendar coverage. A proper non-overlapping SIP test needs a separately approved acquisition of a new date range, plus a matching source-verified earnings calendar.
