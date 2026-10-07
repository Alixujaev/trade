# DAY-17 — v2 Data / Acquisition Blockers (Q1, Q2, Q3, Q16) and Stage R Acquisition Design

| Field | Value |
|---|---|
| Date | 2026-10-07 |
| Governing protocol | `artifacts/day16/research-protocol-v2.md` v2.0 R1, frozen at `ba3cefe54ccf2fe14c62f1c609f143d8a0904221` (**not modified**) |
| Branch / HEAD at start | `feature/day-trading-research` / `ba3cefe` |
| Scope | documentation + minimal structural probe; Stage R acquisition **designed, not run** |
| Research / backtest run | **NO** |
| Prices inspected | **NO** (no OHLC, volume, VWAP, trade-count or corporate-action rate value was printed, stored or analysed) |
| Holdout / forward-OOS dates accessed | **NO** (every request bounded ≤ 2022-12-31) |

**Evidence labels:** **DOC** = official Alpaca documentation/API reference; **STAFF** = Alpaca employee answer on the official forum; **PROBE** = observed in this task's structural probe; **REPO** = repository fact; **INFERENCE** = reasoning from the above, not directly observed.

---

## 1. Files and sources inspected

**Repository (read-only):** `artifacts/day16/research-protocol-v2.{md,json}`, `artifacts/day16/research-checklist.json`; `artifacts/day15/day15c-provider-audit.md`, `artifacts/day15/day15e-alpaca-access.md`, `artifacts/day15/protocol-v1.1.md`; `acquisition/v1_1/{alpaca_client,contract,sessions,snapshot,ledger,validation,environment,research}.py`; `acquisition/{capture_policy,snapshot,ledger,environment}.py`; `data/alpaca_provider.py`; `config/day_universe.py`.

**Documentation:**
- [D1] Historical bars reference: https://docs.alpaca.markets/reference/stockbars
- [D2] Market-data FAQ ("How are bars aggregated?", trade-condition table, `asof`): https://docs.alpaca.markets/docs/market-data-faq
- [D3] About Market Data API (history depth, plan limits): https://docs.alpaca.markets/docs/about-market-data-api
- [D4] Corporate-actions reference: https://docs.alpaca.markets/reference/corporateactions-1
- [S1] Alpaca staff (Dan_Whitnable_Alpaca, 2024-05-17), "Open/Close Daily Bar Prices vs. Open/Close Auction Prices on Primary Exchange": https://forum.alpaca.markets/t/open-close-daily-bar-prices-vs-open-close-auction-prices-on-primary-exchange/14227
- [S2] Alpaca staff (Gergely_Alpaca, 2025-03-31), "Disconnect between daily and minute-bar data": https://forum.alpaca.markets/t/disconnect-between-daily-and-minute-bar-data-returned-via-v2-stocks-bars/16605
- Unverified secondary claim encountered: corporate-actions data "dating back to April 2020" (search-engine summary, no primary source found). **Contradicted by PROBE** (§5).

**REPO facts relevant to v2:**
- `acquisition/v1_1/alpaca_client.py::AlpacaBarsClient` handles only `/v2/stocks/{symbol}/bars` for 5Min/15Min under protocol v1.1; no `asof`, no 1Day, no multi-symbol endpoint, no corporate-actions client.
- `data/alpaca_provider.py` hard-codes the IEX feed and writes to `data/cache/` — **must not be used** for v2.
- Write-once snapshot, canonical content hash, ledger and environment capture (`acquisition/v1_1/{snapshot,ledger,environment}.py`) are reusable by pattern.

---

## 2. Probe log (structural only)

| Item | Value |
|---|---|
| Client | Python 3.12.10 stdlib `urllib`, scripts in the session scratchpad (outside the repo), run with `python -I`; deleted after the task |
| Credentials | `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` from `.env` (never printed or stored) |
| Requests | **8**, all HTTP 200 |
| Date guard | every `start`/`end` ≤ 2022-12-31 (asserted in code) |
| Retained | HTTP status, request IDs, response keys, field names, row counts, timestamp labels, event counts by type/symbol/year, SHA-256 of canonical payloads |
| Discarded immediately | all `o, h, l, c, v, vw, n` values; all `rate`, `old_rate`, `new_rate`, `cash_rate`, `acquirer_rate`, `acquiree_rate` values |
| Written to disk | only the structural summary (scratchpad, deleted after this report) |

| # | Request | Purpose | X-Request-ID |
|---|---|---|---|
| B1 | `GET /v2/stocks/bars` symbols=25+SPY, `timeframe=1Day`, `feed=sip`, `adjustment=raw`, start=2015-12-01, end=2016-01-08, limit=10000, sort=asc (default `asof`) | entitlement, coverage start, labels, META | `04d43da972955689864d18e9821fda1e` |
| B2 | identical to B1 | determinism (payload SHA-256) | `8230117fdfa20bda165549d003aa7d69` |
| B3 | B1 with `adjustment=all` | parameter acceptance, raw/all session-set equality | `1a967cf28c0ce143b53fd3cb830c537c` |
| C1 | `GET /v1/corporate-actions` symbols=25+SPY, start=2016-01-01, end=2016-12-31, limit=1000 | pre-2020 coverage | `de5fa7d6f167aa6296f22eb22eb37a60` |
| C2 | same, 2019 | pre-2020 coverage | `5df765fea3b5b193a09c5f210a6fb5fc` |
| C3 | same, 2021 | post-2020 comparison | `430c7b6787e7bd5df0096ca89df4378f` |
| C4 | symbols=META,FB, types=name_change, 2022-06-01 → 2022-06-30 | FB→META identity in corporate actions | `3fc173e7a1a5033aae6760212811f9de` |
| C5 | symbols=25+SPY+FB, all non-dividend types, start=2016-01-01, end=2022-12-30 | splits/other events in Stage R | `5f7a35e457ccfa9c652e352ada9a9bcf` |

---

## 3. Q1 — Alpaca SIP 1Day bar semantics

**STATUS: RESOLVED**

**EVIDENCE:**
- DOC [D2]: "Minute and daily bars are aggregated from trades. The (SIP) timestamp of the trade is truncated to the minute for minute bars and to the day (in New York) for daily bars." Rules follow "the CTS specification for NYSE (tape A and B), the UTP specification for Nasdaq (tape C)".
- DOC [D2] trade-condition table, **daily-bar rows**: `T` (Extended Hours Trade): open/close **no**, high/low **no**, volume **yes**; `U` (Extended Trading Hours): open/close no, high/low no, volume yes; `I` (Odd Lot): volume only; `M` (Official Close) and `Q` (Official Open): update nothing; `O` (Opening Trade), `5` (Reopening), `6` (Closing Trade), ` `/`@` (Regular Sale): update everything; `Z` and `4` update open/close only if first trade of bar, high/low yes. Minute and daily rules differ for `T`, `Z`, `4`.
- STAFF [S1]: "Alpaca calculates the Open price by filtering for the same trade conditions used to calculate the Close/Last prices then simply takes the first trade of the day. While this often may be an exchange's opening print it isn't guaranteed." Volume and trade count "include after hour trades." Example daily label `…T04:00:00Z`.
- STAFF [S2]: "the aggregating rules for minute and daily bars are different"; the 09:30 minute-bar open will not match the daily open.
- DOC [D1]: fields `t` (RFC-3339), `o`, `h`, `l`, `c`, `v`, `n` (trade count), `vw`.
- PROBE B1: all 26 symbols return 1Day rows labelled `2016-01-04T05:00:00Z` … `2016-01-08T05:00:00Z` = 00:00 America/New_York (EST) of each session date; one row per XNYS session (5 rows = 5 calendar sessions); fields exactly `c,h,l,n,o,t,v,vw`.

**CONCLUSION:**
1. A 1Day bar is the aggregate of SIP trades whose timestamp falls on that New York calendar day, filtered by trade condition per field.
2. `open` = first trade of the day eligible for Close/Last updates (not guaranteed to be the primary-exchange opening auction print); `close` = last such eligible trade; `high`/`low` = extremes over eligible trades; `volume` and `n` include all volume-eligible trades, **including extended-hours trades**.
3. **Extended-hours trades flagged `T`/`U` do not update daily open/high/low/close** (DOC). The frozen §3.3 / Q1 amendment trigger ("if 1Day OHLC includes extended-hours trades") is **not triggered**.
4. Timestamp = 00:00 America/New_York of the session date, expressed in UTC (05:00Z in EST; 04:00Z in EDT per STAFF example; the EDT value is INFERENCE from DOC + STAFF, not probed). Session date = the New York calendar date of `t`.
5. Suitability for the frozen execution model (signal at close `t`, fill at raw open `t+1`): **suitable**. The close of `t` is formed from RTH-eligible trades and is known after the session; the open of `t+1` is a traded price. The open is not necessarily the auction print — this is the already-disclosed NON-BLOCKING Q6 (fill realism), not a new limitation.
6. NON-BLOCKING notes: (a) `v`/`n` include extended-hours volume; no v2 signal or check uses volume beyond `volume ≥ 0` and zero-volume counting; (b) bars are recomputed from trades by Alpaca (late trades may change history; DAY-15C INFERENCE) — handled by the frozen IDENTICAL/DISCREPANCY rule; (c) the trade-condition table is the current documentation; whether identical rules were applied to every historical computation is not independently verifiable (INFERENCE: Alpaca computes historical bars from stored trades with the same rules).

**NEXT IMPLICATION:** Stage R structural check: every bar label must equal 00:00 America/New_York of an XNYS session date (05:00Z EST / 04:00Z EDT); any other label is a HARD FAIL (frozen §3.8 off-calendar / timestamp rules). No protocol change needed.

---

## 4. Q2 — SIP historical coverage and entitlement

**STATUS: RESOLVED**

**EVIDENCE:**
- DOC [D3]: equities history "Since 2016" on both Basic and Algo Trader Plus; Basic plan historical limitation is the "latest 15 minutes".
- REPO (DAY-15E): the existing paper key is entitled to SIP historical 5Min bars (HTTP 200).
- PROBE B1/B3: `feed=sip`, `timeframe=1Day`, raw and all → HTTP 200, no entitlement error, rate limit header 200/min. All **26/26** symbols (25 universe + SPY) returned. Requested from 2015-12-01: **zero rows before 2016-01-04** for every symbol; the **first row for every symbol is 2016-01-04** (the first XNYS session of 2016). 5 rows per symbol for 2016-01-04 → 2016-01-08 = all 5 sessions.
- PROBE B2: an identical repeat request returned a byte-identical canonical payload (SHA-256 equal).
- PROBE B3: `adjustment=all` returned the same per-symbol timestamp label sets as raw.

**CONCLUSION:** Earliest available SIP 1Day date is 2016-01-04 (no earlier rows exist, consistent with "Since 2016"); 2016-01-04 is reachable for all 25 universe symbols and SPY; the current key is entitled to historical SIP 1Day bars for both `raw` and `all`; repeated identical requests were deterministic in the probed window. Symbol-specific gaps **inside** 2016-01-04 → 2022-12-30 cannot be known without acquisition; they are covered by the frozen §3.8 checks (missing sessions listed; > 2 % → BLOCKING review) at Stage R acquisition.

**NEXT IMPLICATION:** Stage R may request from `start=2016-01-04`; expected rows per symbol per series = **1762** XNYS sessions (2016-01-04 → 2022-12-30, local calendar resolution; 13 early-close sessions in range). The frozen first-bar check (≤ 2016-01-04 + 5 sessions) is expected to pass.

---

## 5. Q16 — Corporate-actions endpoint

**STATUS: PARTIALLY_RESOLVED**

**EVIDENCE:**
- DOC [D4]: endpoint `GET /v1/corporate-actions` (data API). Parameters: `symbols`, `cusips`, `types`, `start`, `end`, `ids`, `limit` (1–1000), `sort`, `page_token`, `region`, `data_quality` (`complete` default: "exclude corporate actions that are still missing required fields and have not yet been processed"; `all`). Types: reverse_split, forward_split, unit_split, cash_dividend, stock_dividend, spin_off, cash_merger, stock_merger, stock_and_cash_merger, redemption, name_change, worthless_removal, rights_distribution, partial_call, reorganization, capital_gains_distribution. **`start`/`end`: "The inclusive start/end of the interval. The corporate actions are sorted by their `process_date`."** "Currently Alpaca has no guarantees on the creation time of corporate actions." No documented history depth; no entitlement statement; **no `asof` parameter**.
- PROBE C1–C3, C5 (HTTP 200 throughout → endpoint available to the current key):
  - `cash_dividends` returned for 2016 (67 events), 2019 (68), 2021 (69). Each of the 17 symbols that returned dividends in 2016 and 2019 (AAPL, AMAT, AVGO, COST, CSCO, INTC, JNJ, JPM, KO, MSFT, NVDA, ORCL, PEP, QCOM, WMT, XOM: 4 each; SPY: 3 in 2016, 4 in 2019). → **pre-2020 dividend coverage exists**; the "April 2020" claim is false for this endpoint.
  - The 2021 window returned 3 dividends with **2020 ex-dates**; the 2016 window returned SPY with 3 events. INFERENCE: consistent with DOC that the window filters on `process_date` (≈ payable date), so December ex-dates paid in January fall in the next window. No event with a 2015 ex-date appeared in the 2016 window (INFERENCE: coverage begins around 2016 ex-dates; irrelevant for Stage R, whose TR index starts at 2016-01-04).
  - Field names: `cash_dividends` = cusip, ex_date, foreign, id, payable_date, process_date, rate, record_date, special, symbol; `forward_splits` = cusip, due_bill_redemption_date, ex_date, id, new_rate, old_rate, payable_date, process_date, record_date, symbol; mergers = acquirer/acquiree symbol & cusip, rates, effective_date, id, process_date; `name_changes` = id, new_cusip, new_symbol, old_cusip, old_symbol, process_date. **No status / correction / cancellation field observed.**
  - C5 (non-dividend types, process_date 2016-01-01 → 2022-12-30): `forward_splits` AAPL 2020, TSLA 2020, NVDA 2021, AMZN 2022, GOOGL 2022, TSLA 2022 (GOOGL's 2022 20-for-1 is classified as a **forward split**, not a stock dividend); `cash_mergers` NVDA←MLNX 2020, CSCO←ACIA 2021, MSFT←NUAN 2022; `stock_and_cash_mergers` CRM←WORK 2021; `stock_mergers` AMD←XLNX 2022; `name_changes` FB→META 2022 and **META→METV 2022**. No reverse split, stock dividend, spin-off or other type for the universe.
  - Six forward splits match the publicly known Stage R splits of the universe (INFERENCE: public knowledge used only as an existence check; no ratio was read).

**CONCLUSION:**
1. Coverage back to 2016 for cash dividends: **established** (PROBE). Splits: present for every publicly known Stage R split (2020–2022); no pre-2020 split exists in the universe to test (INFERENCE).
2. Types needed by the frozen TR construction (forward/reverse split, regular/special cash dividend) exist with `ex_date`, split `old_rate`/`new_rate`, dividend `rate`, `special`. Entitlement: available to the current key.
3. Deterministic querying: possible by explicit `start`/`end`/`symbols`/`types`/`sort`/`page_token`; the endpoint's determinism itself was **not** tested (no repeat CA request).
4. **Unresolved for the exact frozen requirement:**
   - **(a) Window semantics conflict — PROTOCOL CHANGE REQUIRED (§8 C1).** The API filters by `process_date`. Events with `ex_date ≤ 2022-12-30` but `process_date` in 2023 (e.g. December ex-dates paid in January) are only reachable by querying 2023 process dates, which also returns events with **2023 ex-dates (holdout period)**. Frozen §3.9 limits Stage R to "events 2016-01-04 → 2022-12-30" and frozen §15.1/§3.9 forbid holdout acquisition before the research gate. Neither choice (miss late-December events → TR/accounting incomplete and cross-check mismatch; or retrieve holdout-dated records) is permitted by the frozen text.
   - **(b) Identity — OPEN — REQUIRES PROTOCOL DECISION (§8 C2).** The ticker "META" historically identified a different entity (Roundhill metaverse ETF, renamed META→METV in 2022). The corporate-actions endpoint has no `asof`; symbol-based queries can return the wrong entity's events. A CUSIP-based identity rule is required and is not frozen.
   - **(c) Field semantics not documented:** whether `rate` is per pre-split or post-split share when a split and a dividend share an ex-date; split ratio direction (`q = new_rate / old_rate` is INFERENCE from field names); `data_quality` choice; how corrections/cancellations are represented (no status field; records may change silently). See §8 C3–C5.
   - Completeness of dividend events can be fully verified only by the frozen raw/all implied-factor cross-check, which needs Stage R bars.

**NEXT IMPLICATION:** Stage R acquisition **must not run** until C1 is decided by a protocol clarification (v2.0.x) and C2–C4 are decided. The endpoint itself is adequate in coverage, types, fields and entitlement.

---

## 6. Q3 — META / FB historical identity

**STATUS: PARTIALLY_RESOLVED**

**EVIDENCE:**
- DOC [D1]: `asof` — "The as-of date of the queried stock symbol(s)… Default: current day"; "FB was renamed to META in 2022-06-09. Querying META with an asof date after 2022-06-09 will also yield FB data."
- DOC [D2]: "On the historical endpoints we introduced the asof parameter to link together the data before and after the rename. By default, this parameter is 'enabled'." "If you disable the asof parameter, you won't get the FB bars." "the asof mapping is only available on our historical endpoints the day after the rename."
- PROBE B1: `symbols=META` with default `asof` returned 5 rows for 2016-01-04 → 2016-01-08 (INFERENCE: these are FB's bars; the Roundhill ETF did not exist in 2016).
- PROBE C4/C5: `name_changes` FB→META (2022) and META→METV (2022) both returned when querying symbols META/FB; corporate-action records carry `cusip` (dividends, splits) and `old_cusip`/`new_cusip` (name changes).
- REPO (DAY-15C): META is an active, tradable `us_equity` on NASDAQ.

**CONCLUSION:**
- **Bars:** RESOLVED. Alpaca maps by entity via `asof` (default = request date); querying `META` with `asof` = acquisition date (frozen §3.1) returns Meta Platforms' full history including the FB period. No acquisition-layer mapping table is needed for bars. The 25-symbol universe stays unchanged.
- **Corporate actions:** NOT resolved. The endpoint has no `asof`; the symbol string "META" before 2022 belonged to another issuer. Associating events with Meta Platforms requires an identity rule (e.g. CUSIP equality with the FB→META `name_changes` record) that the frozen protocol does not specify (§8 C2). INFERENCE: Meta Platforms paid no dividend and had no split between 2016 and 2022, so the correct Stage R event set for META is expected to be empty except the name change — but that must be established by the identity rule, not assumed.

**NEXT IMPLICATION:** Decide C2 before acquisition; Stage R bar requests use the default/acquisition-date `asof`, recorded explicitly.

---

## 7. Interaction with frozen rules (no protocol change; consequences only)

- Frozen §3.4: "Any other event type … for a universe symbol in an acquired range is a BLOCKING data review before any run." Stage R will therefore contain **six expected BLOCKING data reviews** (acquirer-side cash mergers NVDA←MLNX, CSCO←ACIA, MSFT←NUAN; stock_and_cash CRM←WORK; stock merger AMD←XLNX; name change FB→META) plus the foreign-entity META→METV record. Each must be reviewed and documented on data before any run (INFERENCE: acquirer-side mergers and a pure rename do not change the holder's share count or cash; the review must still be recorded).
- Frozen §3.4 cross-check tolerances (1e-6 relative factor change; split ratio within 0.1 %) are frozen and are used as is.
- Frozen §3.8 2 % missing-session review threshold is frozen and used as is.

---

## 8. Decisions required before Stage R can run (not chosen here)

| ID | Item | Classification | Why it is not resolvable within the frozen protocol |
|---|---|---|---|
| **C1** | Corporate-action query window: API filters by `process_date`; Stage R needs all events with `ex_date ∈ [2016-01-04, 2022-12-30]`, some of which have `process_date` in 2023 | **PROTOCOL CHANGE REQUIRED** (v2.0.x clarification) | Frozen §3.9 Stage R range + §15.1/§3.9 holdout prohibition. Options for the user/protocol owner (not chosen): (i) query `process_date` up to a fixed later bound and drop events with `ex_date > 2022-12-30` in memory before persistence, recording only their count; (ii) end Stage R events at `process_date ≤ 2022-12-30` and treat any later-processed Stage R-ex-date event as missing (cross-check will flag it); (iii) defer late-December events to Stage H and truncate the research segment's TR/accounting accordingly. Each changes or interprets frozen text |
| **C2** | Corporate-action entity identity (META/FB vs META ETF; generally symbol reuse) | **OPEN — REQUIRES PROTOCOL DECISION** | Frozen §3.1 mandates `asof` for bars only; the CA endpoint has no `asof`; the rule for associating events with an issuer (CUSIP, name-change chain) is unspecified |
| **C3** | Same-ex-date split + dividend: whether Alpaca `rate` is per pre-split or post-split share | **OPEN — REQUIRES PROTOCOL DECISION** if any such event exists in Stage R (detectable from ex-dates without values) | Frozen §3.4 defines `d` per pre-split share; Alpaca semantics undocumented |
| **C4** | `data_quality` parameter (`complete` default vs `all`) | **OPEN — REQUIRES PROTOCOL DECISION** | Not frozen; changes which records are returned |
| **C5** | Corrections / cancellations: no status field; records may change between acquisitions | design within frozen rules (write-once + IDENTICAL/DISCREPANCY), no new decision | — |
| **C6** | Split ratio direction `q = new_rate / old_rate` | INFERENCE; to be verified structurally at acquisition (q > 1 for all six forward splits; the ratio value itself is cross-checked against the raw/all factor per frozen §3.4) | — |

---

## 9. Stage R acquisition design (DESIGN ONLY — NOT RUN)

**Preconditions (all must hold before the first request):** C1 resolved by a committed protocol clarification; C2–C4 decided; Stage R implementation reviewed; DAY-16 hashes verified at preflight.

### 9.1 Scope
- Sessions: XNYS 2016-01-04 → 2022-12-30 (**1762** sessions; 13 early closes).
- Symbols: 25 `FROZEN_DAY_UNIVERSE` + SPY (B2 only).
- Series: A raw 1Day bars; C `adjustment=all` 1Day bars (audit); corporate-action events; identity metadata. Series B (PIT TR index) is **derived** downstream from raw bars + events, never acquired.

### 9.2 Request contracts
| Series | Endpoint | Fixed parameters | Notes |
|---|---|---|---|
| Raw bars | `GET /v2/stocks/bars` | `symbols` (fixed sorted list), `timeframe=1Day`, `feed=sip`, `adjustment=raw`, `asof=<acquisition date, explicit>`, `start=2016-01-04`, `end=2022-12-30` (inclusive), `limit=10000`, `sort=asc`, `currency=USD` | follow `next_page_token` until null; record page count |
| `all` bars (audit) | same | `adjustment=all`, otherwise identical | levels expected to differ from raw; never an input |
| Corporate actions | `GET /v1/corporate-actions` | `symbols` = 25 + SPY + identity aliases per C2, `types` = all 16 documented types (so unsupported types are seen and reviewed), `sort=asc`, `limit=1000`, `data_quality` per C4, window per **C1** | follow `page_token`; persist the raw JSON payload canonically |
| Identity | `GET /v2/assets/{symbol}` (paper/trading API) + `name_changes` records | — | snapshot of asset status/exchange; identity map per C2 |

### 9.3 Snapshot layout (write-once; git-ignored)
```
data/oos_cache/protocol_v2/stage_r/<capture_id>/
    bars_raw/<SYMBOL>.parquet        t (UTC), session_date (NY), open, high, low, close, volume, trade_count, provider_vwap
    bars_all/<SYMBOL>.parquet        same columns (audit)
    corporate_actions.json           canonical full API payload(s), all types
    events_normalised.parquet        per (symbol identity, ex_date, type): q, d, special, id, cusip, process_date
    identity.json                    entity map (symbol, CUSIPs, name-change chain, asof)
    assets.json                      asset metadata snapshot
    run.json                         every request: endpoint, params, X-Request-ID, status, pages, timestamps, row counts
    environment.json                 Python, platform, distributions + SHA-256, exchange_calendars version, git SHA/dirty
    manifest.json                    per-file content SHA-256 and file SHA-256; protocol SHA (ba3cefe + file hashes)
```
Metadata per request (in `run.json`): provider, endpoint, feed, symbol set, start, end, timeframe, adjustment, role (A/C/events/identity), all request parameters, retrieval timestamp (UTC), HTTP status, X-Request-ID, page count, row/event count, response SHA-256, entitlement evidence (HTTP status / error text), `asof`.

Properties: deterministic (fixed parameter set, fixed symbol order, sort asc); write-once (existing files never overwritten; `acquisition/v1_1/snapshot.py` pattern); idempotent (re-run detects existing complete capture via ledger and compares IDENTICAL/DISCREPANCY instead of rewriting); hash-verifiable (manifest); capture after 16:15 ET only matters for forward data (Stage R is historical).

### 9.4 FAIL conditions (acquisition stops; no partial snapshot is accepted)
| Condition | Basis |
|---|---|
| HTTP 401/403 or any entitlement/subscription error | Q2 / frozen §3.1 |
| Any request date outside 2016-01-04 → 2022-12-30 for bars, or outside the C1-decided window for events | frozen §3.9 |
| A required symbol absent from the response | frozen §2 |
| First bar of any symbol later than 2016-01-04 + 5 sessions | frozen §3.8 (BLOCKING review) |
| Bar label not equal to 00:00 America/New_York of an XNYS session date; bar on a non-session date | Q1 / frozen §3.8 (HARD FAIL) |
| Duplicate timestamp or session date; non-monotonic index; naive timestamp | frozen §3.8 (HARD FAIL) |
| OHLC inconsistency, non-positive price, negative volume | frozen §3.8 (HARD FAIL) |
| raw vs all session-date sets differ | frozen §3.8 (HARD FAIL) |
| Missing sessions > 2 % for a symbol in any evaluated segment | frozen §3.8 (BLOCKING review) |
| Unexplained missing session (listed; never imputed) | frozen §3.8 (listed; review per 2 % rule) |
| Corporate-action record whose entity cannot be uniquely resolved | C2 (BLOCKING) |
| Corporate-action type other than split / cash dividend for a universe entity | frozen §3.4 (BLOCKING data review) |
| raw/all implied-factor change without a matching event, or an event without a factor change; split ratio mismatch > 0.1 % | frozen §3.4 (BLOCKING data review) |
| Repeat of an identical request returns a different canonical payload | frozen §3.9 DISCREPANCY (reported; original retained) |
| Pagination token loop / page count exceeding a fixed maximum | implementation guard (`MAX_PAGES` pattern in `alpaca_client.py`) |

No tolerance beyond those frozen in DAY-16 is introduced here.

### 9.5 Cross-check design (exact relations)
For each identity-resolved symbol `i` and session `k` with bars in both series:
1. `f_i(k) = C^raw_i(k) / C^all_i(k)`.
2. Event set `E_i` = normalised events with `ex_date ∈ [2016-01-04, 2022-12-30]`.
3. **Change detection:** `Δ_i(k) = |f_i(k)/f_i(p) − 1|` with `p` the previous session with a bar. A change exists where `Δ_i(k) > 1e-6` (frozen).
4. **Bijection:** every change session `k` must have ≥ 1 event in `E_i` with `ex_date = k` (or, if bars are missing on `ex_date`, with `ex_date ∈ (p, k]`), and every event must coincide with a change. Mismatch → BLOCKING data review (frozen).
5. **Split magnitude:** for split events, the factor ratio implied by `f` must equal `q = new_rate/old_rate` within 0.1 % (frozen). Dividend magnitudes are **not** cross-checked by the frozen protocol (only coincidence).
6. Results recorded in a corporate-action report (data only; computed before any research run; no return or signal is computed by the check).

### 9.6 PIT total-return index inputs and future-action leakage test (to be implemented with Stage R processing, not now)
- Inputs: raw closes `C_i(k)` and normalised events (`q_i`, `d_i`, ex-dates) only. Series C is never an input.
- **Leakage test (mandatory, frozen §7 test 4 extended):**
  1. **Truncation invariance:** for every symbol and a deterministic set of cut sessions `τ` (e.g. every ex-date and the session before it), build `TR_i` from data truncated at `τ` (bars with `session_date ≤ τ`, events with `ex_date ≤ τ`) and from the full snapshot; `TR_i(k)` for all `k ≤ τ` must be identical (exact float equality given identical arithmetic order).
  2. **Future-event mutation:** append or alter a synthetic event with `ex_date > τ` (e.g. a fictitious split) and rebuild; `TR_i(k ≤ τ)` must be unchanged.
  3. **Adjusted-series exclusion:** replace the `all` series by arbitrary values; `TR_i` must be unchanged (proves series C is not an input).
  4. **Event-date discipline:** an event with ex-date `e` must change `TR` only at `k ≥ e`; removing it must change no `TR(k < e)`.
  These tests use synthetic perturbations of the loaded snapshot and compute no strategy signal or return statistic.

---

## 10. Implementation prerequisites ("Implementation change required for DAY-17 … " — reported, not made)
- Implementation change required: a v2 bars client supporting the multi-symbol `/v2/stocks/bars`, `timeframe=1Day`, explicit `asof`, `adjustment ∈ {raw, all}` (the v1.1 `AlpacaBarsClient` is 5Min/15Min-only and must not be modified for v1.1 semantics).
- Implementation change required: a corporate-actions client (`/v1/corporate-actions`, pagination, all types, `data_quality`, canonical payload persistence).
- Implementation change required: v2 contract/sessions module (protocol_v2 roots, Stage R session resolver, FORBIDDEN roots incl. `data/cache/`, v1.0 and v1.1 roots).
- Implementation change required: daily structural validation (label = NY midnight, session set, raw/all equality), identity resolution (per C2), event normalisation, implied-factor cross-check, and the leakage tests of §9.6.
- `data/alpaca_provider.py` (IEX) must not be used.
- No code was changed in DAY-17.

---

## 11. Safety statement
- No research, backtest, signal, return or performance computation was run.
- No price, volume, VWAP, trade count, dividend amount or split ratio value was printed, stored or analysed; only structural metadata (status, fields, counts, labels, dates as event-year counts, payload hashes).
- No request touched a date after 2022-12-31; no holdout (2023-01-03 → 2026-06-02) or forward-OOS (2026-10-08 → 2027-10-08) data was requested.
- Stage R was **not** acquired. No market-data cache was written or modified.
- DAY-16 frozen artifacts were not modified.
