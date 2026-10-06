# DAY-15C — Historical Provider Audit (audit only)

**Scope:**
- This is a provider capability and contract audit only.
- **No OOS data was downloaded.** No market-data bars of any date were requested from any provider.
- **No production code was changed.** `acquisition/`, `data/`, DAY-14 and the existing OOS snapshots are untouched.
- **No OOS signals, returns, backtests, performance or metrics were computed or inspected.**
- The frozen 25-symbol universe is unchanged.

**Date of audit:** 2026-10-05. Documentation accessed the same day (references in §8).

**Labels:**
- VERIFIED: checked in documentation, the repository, or a metadata call.
- INFERRED: follows from documentation or forum statements but is not stated contractually.
- NOT VERIFIED: could not be checked without requesting bars, which this audit does not do.

---

## 1. Question

Can the fixed OOS window be obtained from a historical provider **today**, instead of capturing it incrementally?

- The window is the first 60 XNYS sessions strictly after 2026-09-25, i.e. 2026-09-28 → 2026-12-21 (`artifacts/day15/day15a-finalization.md`).

## 2. Fundamental blocker (independent of provider)

**Most of the OOS window has not happened yet.**

| Item | Value |
|---|---|
| Sessions in the fixed OOS window | 60 (2026-09-28 → 2026-12-21) |
| Sessions that have occurred as of 2026-10-05 | **5**: 2026-09-28, 09-29, 09-30, 10-01, 10-02 |
| Sessions still in the future | **55**: 2026-10-05 → 2026-12-21 |
| Already captured (snapshot `capture_20261002T0636ET_s001-s004`) | 4 |
| Earliest moment a complete 60/60 set can exist anywhere | after 2026-12-21 16:00 ET (capture policy: not before 16:15 ET) |

**Conclusions:**
- No provider, at any price, can return bars for sessions that have not traded.
- The bottleneck is therefore **not** provider depth. It is that the window is defined in calendar time that has not elapsed yet.
- A historical provider cannot shorten the wait for 60/60. What it **can** remove is the yfinance ~60-day expiry risk (DAY-15B `BLOCKED` state, `acquisition/provider_adapter.py::earliest_requestable_start`).
  - With a provider whose history does not expire, the full window could be backfilled in **one** acquisition after 2026-12-21.
  - The ≥ 4 incremental captures with deadlines (session 1 stops being requestable from yfinance around 2026-11-25) would no longer be needed.

## 2a. Protocol conflict (recorded, not resolved here)

`artifacts/day14/data-expansion-spec.md` (DAY-14, frozen under protocol v1.0) states:

- line 24: "Provider | yfinance only. Switching to Alpaca (IEX feed, not consolidated volume) would change RVOL semantics and is a separate experiment. | PREDEFINED"
- line 55: "… It is reported as incomplete; sessions are never back-filled from another provider."

**Consequences:**
- Under protocol v1.0, a non-yfinance provider **cannot** be used for the OOS set, not even for backfill.
- Using one requires a new protocol version (v1.1), committed **before** any OOS bar from the new provider is read.
- This audit does not modify DAY-14.

**Second-order issue:** all in-sample research (DAY-04 → DAY-12B) used the yfinance 5m cache.
- An OOS set from a different provider (different volume source, trade-condition filtering and bar construction) would test the rule on differently constructed data.
- A clean v1.1 would also have to re-establish the in-sample baseline on the new provider before OOS evaluation.
- That is possible for Alpaca and Massive, because 2026-07-02 → 09-25 is within their history.

---

## 3. Provider comparison

Repository status:
- **yfinance** is used by `acquisition/provider_adapter.py` and `data/yfinance_provider.py`.
- **Alpaca** is supported by `data/alpaca_provider.py`, with `DataFeed.IEX` hard-coded, a `start` relative to now and no `end`.
- **Massive / Polygon** has no code and no credentials in the repo or environment.

| | **Alpaca Market Data v2** | **Massive (formerly Polygon.io)** | **yfinance** (current OOS provider) |
|---|---|---|---|
| **A. Arbitrary historical 5m bars** | Yes, explicit `start`/`end`; history "Since 2016" (VERIFIED [A1]) | Yes, `/v2/aggs/.../range/5/minute/{from}/{to}` (VERIFIED [M1]); depth by plan: Basic 2y, Starter 5y, Developer 10y (VERIFIED [M2]) | No: "Intraday data cannot extend last 60 days" (VERIFIED [Y1]) |
| **A. 2026-09-28 → today retrievable now** | Yes for the 5 occurred sessions (INFERRED from docs; no bar probe) | Yes for the 5 occurred sessions on any plan, Basic = EOD data (INFERRED; no key) | Yes, only while within ~60 days (already captured 4/5) |
| **A. Plan / feed restriction** | Basic (free): SIP history allowed except the "latest 15 minutes"; IEX real-time only (VERIFIED [A1]) | Basic: "End of Day Data", 5 calls/min; paid tiers 15-min delayed or real-time (VERIFIED [M2]) | Unofficial scraper of Yahoo; no contract, ToS-dependent (INFERRED) |
| **A. IEX vs SIP history** | `feed` = sip / iex / boats / otc, default `sip` (VERIFIED [A2]). IEX ≈ one venue's trades only; SIP = consolidated tape. **The repo hard-codes IEX.** | Single consolidated feed: "100% Market Coverage" (VERIFIED [M2]) | Volume source not documented (NOT VERIFIED) |
| **B. 5m bars** | Native `5Min` (VERIFIED [A2]) | Native, multiplier 5 / timespan minute (VERIFIED [M1]) | Native `5m` (VERIFIED [Y1]) |
| **B. 15m bars** | Native `15Min` (VERIFIED [A2]) | Native, multiplier 15 (VERIFIED [M1]) | Native `15m` (VERIFIED [Y1]) |
| **B. Timestamp semantics** | Bar labelled by its **start**; interval `Tstart <= trade < Tend` (VERIFIED [A3]) | `t` = "start of the aggregate window" (VERIFIED [M1]) | Bar **open** (VERIFIED in repo: DAY-08B timestamp audit) |
| **B. Timezone** | RFC-3339 timestamps, UTC (VERIFIED [A2]) | Unix milliseconds, i.e. UTC epoch (VERIFIED [M1]) | tz-aware; stored as UTC by acquisition (VERIFIED in repo) |
| **B. RTH filtering** | No server-side session filter; must filter client-side (INFERRED: no such parameter in [A2]); repo `data/session.py::filter_rth` exists | No server-side session filter; extended-hours trades included (INFERRED: no such parameter in [M1]) | `prepost=False` server-side (VERIFIED [Y1]) |
| **B. Trade- or quote-based** | Trade-based. Trades filtered by condition per field, following CTS/UTP guidance (VERIFIED [A3], [A4]) | Trade-based: "constructed exclusively from qualifying trades" (VERIFIED [M1]); condition list not on that page | NOT VERIFIED |
| **B. Empty intervals** | Bars only where trades exist; empty minutes omitted (INFERRED, [A4]) | "If no eligible trades occur … no aggregate bar is produced" (VERIFIED [M1]) | Omitted rows (INFERRED) |
| **C. Fields** | t, o, h, l, c, v, n (trade count), vw (VERIFIED [A2]) | o, h, l, c, v, vw, n, t (VERIFIED [M1]) | OHLC, Adj Close, Volume (VERIFIED in repo) |
| **C. Adjustment** | `adjustment` = raw / split / dividend / spin-off / all, **default raw** (VERIFIED [A2]) | `adjusted`, **default true** (split-adjusted); `false` = raw (VERIFIED [M1]) | `auto_adjust` default True; OOS acquisition uses False (VERIFIED [Y1], repo) |
| **C. Retroactive revision** | Bars are recalculated to include late trades (INFERRED from [A3]); no published finality cutoff (NOT VERIFIED) | Not documented on the aggregates page (NOT VERIFIED) | Undocumented (NOT VERIFIED) |
| **C. Explicit start/end** | Yes, RFC-3339 or YYYY-MM-DD (VERIFIED [A2]) | Yes, YYYY-MM-DD or ms timestamp (VERIFIED [M1]) | Yes; `end` exclusive (VERIFIED [Y1]) |
| **C. Pagination** | `limit` ≤ 10,000 data points total across symbols; `next_page_token` / `page_token` (VERIFIED [A2]) | `limit` ≤ 50,000, default 5,000; `next_url` (VERIFIED [M1]) | None (single response) |
| **C. Rate limits** | Basic 200 calls/min; Algo Trader Plus 10,000/min (VERIFIED [A1]) | Basic 5 calls/min; paid "Unlimited" (VERIFIED [M2]) | Undocumented; throttled by Yahoo (INFERRED) |
| **C. Identical repeat requests** | Expected identical for settled history with fixed `feed` + `adjustment=raw` + `asof` (INFERRED); not contractually guaranteed | Expected identical with `adjusted=false` (INFERRED); not guaranteed | Not guaranteed; the DAY-15A design already treats re-acquisition as DISCREPANCY-checked |
| **D. 25-symbol coverage** | **All 25 present**: `/v2/assets/{sym}` → HTTP 200, `active`, `tradable`, `us_equity` (19 NASDAQ, 6 NYSE) (VERIFIED, metadata call §5) | "All US Stocks Tickers" (VERIFIED [M2]); per-symbol check not done (no key) | Already 25/25 in snapshot #1 (VERIFIED, `day15b-acquisition.md`) |
| **E. Cost** | Basic $0 (SIP history, 15-min embargo); Algo Trader Plus $99/mo (VERIFIED [A1]) | Basic $0 (EOD); Starter $29; Developer $79; Advanced $199 per month (VERIFIED [M2]) | $0 |
| **E. Existing account can access** | Key valid: paper `/v2/account` → HTTP 200, `ACTIVE`; live endpoint → 401, so the keys are **paper** keys. SIP historical bar entitlement NOT VERIFIED (no bar probe by decision) | No account / key in environment | n/a (keyless) |

---

## 4. Best candidate

**Alpaca Market Data v2 with `feed=sip`, `adjustment=raw`, explicit `start`/`end`.**

Why:
- A key already exists locally and authenticates.
- History goes back to 2016, with no 60-day expiry.
- Under the free Basic plan, SIP history is documented as available except the latest 15 minutes, which is irrelevant for settled sessions.
- 5m and 15m bars are native; bars are start-labelled and in UTC, matching the acquisition storage convention.
- All 25 symbols are present.
- Rate limits are ample: one 5m request per symbol covering 60 RTH sessions (~4,680 RTH bars, plus extended hours) fits in about 2 pages of 10,000.

**Runner-up: Massive Stocks Basic (free).**
- It provides minute aggregates over 2 years with EOD timeliness and 5 calls/min, which is enough for 50 symbol×interval requests in about 10 minutes.
- It requires opening an account and storing a new key.

**Caveats for either candidate:**
- The repository's `AlpacaProvider` hard-codes `DataFeed.IEX` and a `now − lookback` start. It is **not** suitable as-is for OOS acquisition: it also writes to the research cache `data/cache/`, which acquisition must never touch.
- SIP volume from Alpaca or Massive is constructed differently from yfinance volume. RVOL and VWAP inputs would differ from the in-sample data (§2a).

## 5. Exact blockers

1. **Time (hard, provider-independent):** 55 of 60 sessions have not occurred. Full 60/60 is impossible before 2026-12-21 16:15 ET.
2. **Protocol (hard under v1.0):** DAY-14 fixes the provider to yfinance and forbids back-fill from another provider (`data-expansion-spec.md` lines 24 and 55). Switching requires protocol v1.1, committed before any OOS bar is read.
3. **Methodological:** OOS data from a different provider than the in-sample data confounds the test. v1.1 would need an in-sample re-baseline on the same provider and feed.
4. **Entitlement (soft, unverified):** that the existing paper key can read **SIP** historical 5m bars is documented but not verified, because no bar request was made. The first bar-level check should target an in-sample date (≤ 2026-09-25), never an OOS date, and record only HTTP status and error text.
5. **Revision policy (soft):** neither Alpaca nor Massive documents when historical bars become final. The existing DISCREPANCY mechanism (DAY-15A) would still be needed.

## 6. Can the full 60-session backfill be done now?

**No.**

- No provider can supply the 55 sessions that have not traded.
- Today a historical provider could supply only the 5 occurred sessions, which is not a material speed-up over the current yfinance captures.
- The earliest a complete 60/60 backfill can happen is after 2026-12-21 16:15 ET:
  - **from yfinance**, only if every session has been captured within its ~60-day window (incremental, as now);
  - **from Alpaca SIP or Massive**, in a single request set, but only after a protocol v1.1.

## 7. Recommended next step

The user decides; nothing below has been done.

**Option A — stay on protocol v1.0 (no change):**
- Keep the yfinance incremental captures.
- The next capture is due now (session 5, 2026-10-02, is capturable). Then capture at intervals of ≤ 20 sessions, with the first-session deadline around 2026-11-25.
- This needs no protocol change and keeps OOS on the same provider as in-sample.

**Option B — draft protocol v1.1 (before any new-provider bar is read):**
- Adopt Alpaca SIP (`adjustment=raw`) as the provider for both a re-run in-sample baseline and the OOS set.
- Acquire the full 60-session window in one pass after 2026-12-21.
- Keep the v1.0 yfinance captures running in parallel as an independent cross-check.

**Recommendation:**
- Continue Option A regardless. It is cheap and keeps v1.0 valid.
- Treat Option B as insurance against yfinance expiry or outages, decided and committed well before 2026-11-25.
- Neither option makes 60/60 available before 2026-12-21.

---

## 8. References (accessed 2026-10-05)

- [A1] Alpaca — About Market Data API (plans, history since 2016, Basic "latest 15 minutes" limitation, rate limits, $99/mo Algo Trader Plus): https://docs.alpaca.markets/docs/about-market-data-api
- [A2] Alpaca — Historical bars API reference (timeframes, start/end, limit 10,000, page_token, `adjustment` default raw, `feed` default sip, fields): https://docs.alpaca.markets/reference/stockbars
- [A3] Alpaca Learn — Stock Minute Bars (start-labelled, `Tstart <= trade < Tend`, per-field trade-condition filtering, recalculation for late trades): https://alpaca.markets/learn/stock-minute-bars/
- [A4] Alpaca forum — (How) are Bars calculated? (CTS/UTP condition guidance): https://forum.alpaca.markets/t/how-are-bars-calculated-different-bars-than-in-tradingview/9445
- [M1] Massive — Stocks Custom Bars (OHLC) REST docs (endpoint, `adjusted` default true, limit 50,000, `next_url`, `t` = window start ms, no bar without eligible trades): https://massive.com/docs/rest/stocks/aggregates/custom-bars
- [M2] Massive — Pricing (Stocks Basic $0 / 2y / EOD / 5 calls per min; Starter $29; Developer $79; Advanced $199): https://massive.com/pricing
- [Y1] yfinance — `download()` reference ("Intraday data cannot extend last 60 days", intervals, start/end, auto_adjust, prepost): https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- Repo:
  - `data/alpaca_provider.py` (IEX hard-coded);
  - `acquisition/provider_adapter.py` (`INTRADAY_LOOKBACK_DAYS = 60`);
  - `artifacts/day14/data-expansion-spec.md` (lines 24, 55);
  - `artifacts/day15/day15a-finalization.md`;
  - `artifacts/day15/day15b-acquisition.md`;
  - `artifacts/day15/day15b-lifecycle.md`.

## Appendix — metadata calls made (no market data)

The script was run from the session scratchpad (not in the repo). Credentials were read from `.env` and never printed.

| Call | Result |
|---|---|
| `GET https://paper-api.alpaca.markets/v2/account` | HTTP 200; status ACTIVE; trading_blocked false; account_blocked false |
| `GET https://api.alpaca.markets/v2/account` | HTTP 401 (keys are paper keys) |
| `GET {paper}/v2/assets/{sym}` × 25 | all HTTP 200, `active`, `tradable`, `us_equity`. NASDAQ: AAPL MSFT NVDA AMZN META GOOGL TSLA AVGO AMD QCOM INTC MU AMAT ADBE CSCO COST WMT PEP NFLX; NYSE: CRM ORCL KO JNJ JPM XOM |

No Alpaca or Massive market-data endpoint (`data.alpaca.markets`, `api.massive.com` / `api.polygon.io`) was called.
