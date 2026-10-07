# DAY-15G — Alpaca SIP 15Min Historical Access Verification (in-sample, one request)

**Question:** can the existing Alpaca key retrieve historical SIP **15Min** bars under the protocol v1.1 contract?

**Answer: YES** (VERIFIED, one request, 2026-10-06). This closes protocol v1.1 open issue O1.

**Scope:**
- An access and contract check only.
- Exactly one market-data request: one in-sample date (2026-07-02), one symbol, 15 minutes.
- No price value was printed, stored or inspected. Only field presence, field types and timestamps were recorded.

## 1. Request contract

| Item | Value |
|---|---|
| Endpoint | `GET https://data.alpaca.markets/v2/stocks/AAPL/bars` |
| `timeframe` | `15Min` |
| `feed` | `sip` |
| `adjustment` | `raw` |
| `start` / `end` | `2026-07-02T13:30:00Z` / `2026-07-02T13:45:00Z` (09:30 / 09:45 ET) |
| `limit` | 10 |
| Auth | `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` from `.env`; never printed or stored |
| Client | Python stdlib `urllib`, scratchpad script (outside the repo) |
| Requests | **1**; no retry; response kept in memory only |

## 2. Access result

| Property | Result | Label |
|---|---|---|
| HTTP status | **200** | VERIFIED |
| SIP entitlement for 15Min | yes; no subscription error | VERIFIED |
| Rate-limit headers | `X-Ratelimit-Limit: 200`, remaining 199 | VERIFIED |
| Request ID | `141bdcc03ce438bd1be614733f3858b3` | VERIFIED |

## 3. Data contract result

| Property | Result | Label |
|---|---|---|
| Top-level keys | `bars`, `next_page_token`, `symbol` (= AAPL) | VERIFIED |
| Bars returned | 2 | VERIFIED |
| First / last timestamp | `2026-07-02T13:30:00Z` / `2026-07-02T13:45:00Z` | VERIFIED |
| OHLC | `o h l c` present, float, non-null in both bars | VERIFIED |
| Volume | `v` present, int, non-null; also `n` (int) and `vw` (float) | VERIFIED |
| Timezone / format | RFC-3339 with `Z` (UTC) | VERIFIED |
| Bar-start semantics | the first bar is labelled 13:30:00Z = the 09:30 ET session open | VERIFIED (label) |
| **Inclusive `end`** | the bar starting exactly at `end` (13:45:00Z) was returned, the same as the 5Min behaviour in DAY-15E | VERIFIED |
| Pagination | not required (`next_page_token` null) | VERIFIED |
| Raw adjustment | parameter accepted; values not compared (no price inspection) | VERIFIED (parameter) / NOT VERIFIED (values) |

## 4. Safety

- **No OOS date was requested.** The only request covered 2026-07-02 13:30–13:45 UTC, inside the research window. Nothing after 2026-09-25 was requested.
- No OOS bars were read.
- No indicators, signals, returns or metrics were computed.
- No code changed for the probe.
- `data/cache/` and `data/oos_cache/` were untouched.
