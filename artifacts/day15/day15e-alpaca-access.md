# DAY-15E — Alpaca SIP Historical Access Verification (in-sample, one request)

**Question:** can our existing Alpaca key retrieve historical SIP 5m bars under the contract proposed in DAY-15D?

**Answer: YES** (VERIFIED, one request, 2026-10-06).

**Scope:**
- An access and contract check only.
- Exactly **one** market-data request, for **one in-sample date** (2026-07-02), **one symbol**, **10 minutes**.
- No price value was printed, stored or inspected. Only field presence, field types and timestamps were recorded.
- Protocol v1.1 is **not** approved or committed by this document.

**Labels:**
- VERIFIED: observed in the response.
- INFERRED: follows from the response plus documentation.
- NOT VERIFIED: cannot be established from this request without inspecting values.

---

## 1. Request contract

| Item | Value |
|---|---|
| Method / endpoint | `GET https://data.alpaca.markets/v2/stocks/AAPL/bars` |
| `timeframe` | `5Min` |
| `feed` | `sip` |
| `adjustment` | `raw` |
| `start` | `2026-07-02T13:30:00Z` (09:30 ET, first RTH bar of an in-sample session) |
| `end` | `2026-07-02T13:35:00Z` |
| `limit` | `10` |
| Auth | headers `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY`, read from `smc-scanner/.env` (`ALPACA_API_KEY` / `ALPACA_SECRET_KEY`); not printed or stored |
| Client | Python 3.12.10 stdlib `urllib`, script in the session scratchpad (outside the repo) |
| Requests made | **1** (no retry, no second date, no other symbol) |
| Response storage | memory only; nothing written to disk |

## 2. Access result

| Property | Result | Label |
|---|---|---|
| HTTP status | **200** | VERIFIED |
| SIP historical entitlement | **yes**. `feed=sip` was accepted with no 403 or subscription error for a date about 3 months old. | VERIFIED |
| Bars returned | yes, **2** | VERIFIED |
| Provider error / restriction | none in the body; rate-limit headers `X-Ratelimit-Limit: 200`, `X-Ratelimit-Remaining: 199` | VERIFIED |
| Plan tier | a 200/min limit matches the documented Basic (free) plan (DAY-15C [A1]) | INFERRED |
| Request ID | `0101142d296542296c6b8e19a1f5f4de` | VERIFIED |

## 3. Data contract result

| # | Property | Result | Label |
|---|---|---|---|
| 1 | Top-level keys | `bars`, `next_page_token`, `symbol` (= `AAPL`) | VERIFIED |
| 2 | First timestamp | `2026-07-02T13:30:00Z` | VERIFIED |
| 3 | Last timestamp | `2026-07-02T13:35:00Z` | VERIFIED |
| 4 | Bar count | 2 | VERIFIED |
| 5 | OHLC fields | `o`, `h`, `l`, `c` present, type float, non-null, in both bars | VERIFIED |
| 6 | Volume | `v` present, type int, non-null; also `n` (trade count, int) and `vw` (float) | VERIFIED |
| 7 | Timestamp format / timezone | RFC-3339 string with a `Z` suffix, i.e. UTC, second precision | VERIFIED |
| 8 | Bar timestamp = interval start | The first bar is labelled 13:30:00Z = 09:30 ET, the session open. No trade can precede the open in RTH, so the label is the interval start. Consistent with the documented `Tstart ≤ trade < Tend` (DAY-15C [A3]) and with the repo convention (index = bar open). | VERIFIED (label) / INFERRED (trade window) |
| 9 | **`end` semantics** | **Inclusive.** The bar starting exactly at `end` (13:35:00Z) was returned. | VERIFIED |
| 10 | Raw / unadjusted | `adjustment=raw` was accepted without error. The response carries no adjustment field. Whether the values are unadjusted cannot be confirmed without comparing prices, which this check does not do. | VERIFIED (parameter accepted) / NOT VERIFIED (values) |
| 11 | Pagination | not required: `next_page_token` is null | VERIFIED |

## 4. Provider limitations discovered (observed only)

1. **`end` is inclusive.**
   - yfinance's `end` is exclusive (DAY-15A).
   - A v1.1 adapter that copies the yfinance "end = next day 00:00" convention would pull in the first bar of the next day at 00:00 ET. That bar is outside RTH and would be filtered, but the adapter must still state its `end` semantics explicitly and test them.
2. **No adjustment echo.** The response does not state the adjustment applied. Provenance must come from the request parameters recorded by the adapter.
3. **Rate limit 200 requests/min** on this key.
4. No other restriction was observed.
   - Not tested: recent-data limits ("latest 15 minutes"), multi-page behaviour, non-RTH bars, other symbols, 15Min.
   - These are out of scope for this check.

## 5. Protocol impact

- **Alpaca SIP is technically viable for the DAY-15D v1.1 proposal.** The existing key reads historical SIP 5m bars with explicit start/end and `adjustment=raw`, with OHLCV present and start-labelled UTC timestamps.
- DAY-15D open question **Q2 (entitlement) is resolved: YES**.
- Still open before a v1.1 commit:
  - Q1, adjustment mode (raw vs. split);
  - the inclusive-`end` convention (§4);
  - 15Min availability (INFERRED from docs, not tested);
  - the Stage 1 rule (§6).
- **v1.1 is NOT approved by this document.**

## 6. Note on the DAY-15D Stage 1 rule (not changed)

The draft rule is: "if the stage 1 primary metric < 0, the candidate is REJECTED; final."

**Status:**
- It is a **proposed decision rule** in an uncommitted draft (DAY-15D §8, Q4). It is **not** a protocol rule.
- No committed protocol contains it. DAY-14 v1.0's acceptance framework has only a sign condition on one 60-session OOS.

**Why 20 sessions may not suffice for an irreversible rejection** (reasoning only; no performance data used):
- **A sign test on one month is noisy.** The primary metric is a mean over all trades in 20 sessions.
  - Trades on the same day across 25 correlated mega-caps are not independent. The effective sample is closer to the number of sessions than to the number of trades.
  - With 20 effective observations, a truly non-negative strategy can show a negative mean by chance with substantial probability. A truly zero-edge strategy does so about half the time.
- **"Final" makes a false rejection unrecoverable.** Stage 2 (40 sessions) would be collected but could not reverse it.
- **No minimum trade count is predefined** (research-protocol §13: NOT PREDEFINED). A stage 1 with very few trades would still trigger a permanent rejection.
- **The rule is asymmetric.** Stage 1 can reject alone but cannot accept alone.

**Why it might still be defensible:**
- It removes any temptation to wait, look again, or reinterpret a negative stage 1.
- Stage 1 decides only rejection, not acceptance. Acceptance still needs the full 60 sessions.
- A sign-only threshold is the least tunable choice.

**What must be frozen before a v1.1 commit** (decisions only; no values proposed here):
1. The exact stage-1 rule text. Choose one:
   - (a) sign < 0 → final rejection;
   - (b) stage 1 is reported only and the decision is taken on 60 sessions;
   - (c) a three-way outcome (reject / inconclusive / continue) with a predeclared inconclusive band.
2. A minimum stage-1 trade or session count below which stage 1 is "inconclusive", or an explicit statement that none exists.
3. How stage 1 and stage 2 combine for acceptance: both ≥ 0, the combined 60 ≥ 0, or both.
4. Whether stage 2 is still evaluated and reported after a stage-1 rejection (DAY-15D proposes yes, reported only).

None of these may be chosen after any OOS or SIP research value is seen. DAY-15D was not modified.

## 7. Safety

- **No OOS endpoint or date was requested.** The only market-data request covered 2026-07-02 13:30–13:35 UTC, inside the research period (2026-07-02 → 2026-09-25). No date after 2026-09-25 was requested.
- **No OOS bars were read.**
- **No price values were inspected.** Field presence, types and timestamps only; the response was not saved.
- **No indicators, signals, returns or performance metrics were calculated.**
- **No production code changed:** strategy, execution, acquisition and data code are untouched; the probe script lives in the session scratchpad.
- **No OOS snapshots changed;** `data/oos_cache/` and `data/cache/` are untouched.
- Credentials were never printed or written.

## 8. Git status

- Files created: `artifacts/day15/day15e-alpaca-access.md`.
- Files modified: none (tracked tree unchanged; DAY-15D unchanged).
- Untracked (all pre-existing except this file):
  - `artifacts/day15/day15b-acquisition.md`
  - `artifacts/day15/day15c-provider-audit.md`
  - `artifacts/day15/day15d-oos-window-redesign.md`
  - `artifacts/day15/day15e-alpaca-access.md`
  - `day08-market-cache.tar.gz`
- No commit. No push.
