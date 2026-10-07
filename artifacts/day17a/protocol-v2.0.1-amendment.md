# Protocol v2.0.1 — Clarification Amendment (DAY-17A)

| Field | Value |
|---|---|
| Amendment version | **v2.0.1** (clarification) |
| Status | **DRAFT — PENDING COMMIT** |
| Parent protocol | v2.0 R1, `artifacts/day16/research-protocol-v2.{md,json}`, `research-checklist.json`, frozen at **`ba3cefe54ccf2fe14c62f1c609f143d8a0904221`** |
| Parent file SHA-256 | md `57cc368d80a0a3c89af78fe5fd1a6b95962859a3f494ae79a759fb7406a86fb1`; json `ed21cfa508ac9aadcb6600b227014a084cbbfd6a9a5546433bd5327f5154e037`; checklist `7142f02ca243c08163385b5e5e1560024d3b71b87d3aaabf449d41f8ddf40eb3` |
| Evidence base | `artifacts/day17/day17-data-blockers.{md,json}` (SHA-256 `4c4187cb…`, `68ae17c4…`) + DAY-17A structural probe (§6) |
| Drafted | 2026-10-07 |

**Precedence:** v2.0 R1 remains immutable and authoritative. Where this amendment states a v2.0.1 rule, that rule governs v2 acquisition and data processing from the commit of this amendment onward. Nothing else in v2.0 R1 changes.

## 0. What this amendment does NOT change
Universe (25 symbols); SPY benchmark-only role; warmup, research, holdout, excluded and forward-OOS dates; strategy definitions (V2-MOM, V2-STR, V2-LRV) and all parameters; portfolio construction and accounting model; execution model; transaction costs; benchmarks; economic gate; robustness (completeness) gate; family-selection, multiple-testing and graduation rules; frozen tolerances (1e-6 factor change, 0.1 % split ratio, 2 % missing sessions); the three-series price policy (raw = execution/accounting; PIT TR index = signals; `adjustment=all` = audit only). It introduces **no new numeric tolerance**.

---

## C1 — Corporate-action query window at the Stage R / holdout boundary

**STATUS: RESOLVED** (decision taken by the protocol owner in DAY-17A)

**Original v2.0 R1 rule** (§3.9): "Stage R (research): acquired after the freeze commit: bars and events **2016-01-04 → 2022-12-30**." §15.1: "No holdout data before the research gate." §3.3: "A corporate-action event with ex-date `d` is usable from the start of session `d`."

**Problem (DAY-17):** the Alpaca corporate-actions endpoint filters `start`/`end` on `process_date` ("The date when the corporate action is processed by Alpaca"), not on `ex_date`. Events with `ex_date ≤ 2022-12-30` can have `process_date` in 2023 (e.g. December ex-dates paid in January). A `process_date ≤ 2022-12-30` query misses them; a query reaching 2023 also returns records whose economic date lies in the holdout.

**EVIDENCE:** DOC corporate-actions reference (`start`/`end`: "The corporate actions are sorted by their `process_date`"); PROBE DAY-17 (2021 window contained events with 2020 ex-dates).

**DECISION (v2.0.1 rule):**
1. **Event date** of a corporate-action record: `event_date = ex_date` if present, else `effective_date`, else `process_date`.
2. **Stage R event set** = all identity-resolved records (C2) of the 25 universe symbols + SPY with `2016-01-04 ≤ event_date ≤ 2022-12-30`. The research-period boundary is defined by **event_date**, never by `process_date`.
3. **Two-stage bounded query:**
   - **Q1:** `process_date` 2016-01-01 → 2022-12-30.
   - **Q2 (supplementary):** `process_date` 2022-12-31 → **2023-03-31**.
   Both with the same symbols (C2 query keys), all 16 documented types, `sort=asc`, `limit=1000`, pagination followed, `data_quality` per C4.
4. **In-memory boundary filter:** every record with `event_date > 2022-12-30` or `event_date < 2016-01-04` is discarded **inside the acquisition filter, before any persistence**. Discarded records are **never written, printed, logged field-by-field, displayed or used**; only the **total count** of discarded records per query (Q1, Q2) is logged.
5. **Is retrieving a 2023-`process_date` record prohibited holdout acquisition?** A retained record (event_date ≤ 2022-12-30) is **research-period information**: its economic effect date lies in the research period; `process_date` is Alpaca's bookkeeping date, not an economic fact about the holdout. It is **not** holdout acquisition. Records with `event_date > 2022-12-30` **are** holdout information; their transient presence in process memory inside the filter, under rule 4, is the only permitted contact and does **not** constitute acquisition. Any persistence, display or use of them is a protocol violation.
6. **Research data vs construction metadata:** research data = raw/all bars of sessions 2016-01-04 → 2022-12-30 and retained events (rule 2). `process_date`, `payable_date`, `record_date`, `id` and the Q2 window are **construction metadata**: they may be stored with retained records and used for audit, never as signal, accounting or gate inputs (accounting uses `ex_date` per frozen §11.2).
7. **Completeness guard (frozen, unchanged):** the raw/all implied-factor cross-check (frozen §3.4) must match every factor change in 2016-01-04 → 2022-12-30 to a retained event. A late-December-2022 factor change without a retained event is a **BLOCKING data review**; it is never resolved by widening Q2 without a further committed amendment.
8. **No other 2023+ economic information:** Stage R requests no bars after 2022-12-30 (frozen); the Q2 window is the only 2023-dated request and is fixed at 2023-03-31.

**PROTOCOL IMPACT:** clarifies §3.9 (Stage R "events" = event_date range), §3.1 (query contract), §15.1/§3.9 (what counts as holdout acquisition for corporate-action metadata). No date, segment or gate changes.

**IMPLEMENTATION IMPACT:** the CA client must implement Q1+Q2, the event_date filter before persistence, and per-query discard counters; tests must prove that no record with event_date > 2022-12-30 reaches disk or logs.

---

## C2 — Corporate-action entity identity (ticker reuse)

**STATUS: RESOLVED**

**Original v2.0 R1 rule** (§3.1): "Symbol mapping: `asof` fixed to the acquisition date and recorded"; §2: META traded as FB before 2022-06-09, coverage via `asof`. No identity rule for corporate actions.

**Problem (DAY-17):** the CA endpoint has no `asof`; the ticker "META" identified a different entity (META→METV, 2022) before Meta Platforms took it.

**EVIDENCE:**
- DOC asset object lists an optional `cusip` field; **PROBE A1: `cusip` is null for all 26 assets** on the current key → the asset endpoint cannot anchor identity.
- PROBE A1/A2: CA records carry `cusip` (dividends, splits) and `old_cusip`/`new_cusip` (name changes). **Records with ex-dates 2016 → 2019/2020 have an empty `cusip` (`""`); records from 2020 on carry a 9-character CUSIP, exactly one non-empty CUSIP per symbol** among split/dividend records. FB→META record: `old_cusip == new_cusip`. META→METV record: `old_cusip` ≠ the FB→META CUSIP. META, AMD, ADBE, CRM, NFLX have **no** split/dividend records in Stage R (process_date ≤ 2022-12-30).
- PROBE A2: no duplicate (type, symbol, event_date) groups.

**DECISION (v2.0.1 rule):**
1. **Identity key:** a non-empty `cusip` (or `old_cusip`/`new_cusip`) is **authoritative**. The ticker is a **query key** only.
2. **Query keys:** the 25 symbols + SPY + every alias reachable by `name_changes` records whose `new_symbol` is a universe symbol (for Stage R: **FB**).
3. **Anchor CUSIP** of universe symbol `T` (derived from the retained Stage R CA set; no external identifier is introduced):
   - if one or more `name_changes` records have `new_symbol = T`, the anchor is the `new_cusip` of the latest such record (META → the FB→META `new_cusip`);
   - otherwise, the anchor is the **single** non-empty CUSIP among `T`'s split/dividend records;
   - CUSIPs linked to the anchor by `name_changes` (`old_cusip`↔`new_cusip`) or split CUSIP changes (`old_cusip`/`new_cusip`) form `T`'s **CUSIP set**.
4. **Ticker matches, CUSIP does not:** a record under ticker `T` (or its alias) with a non-empty CUSIP not in `T`'s CUSIP set is a **foreign-entity record**: excluded from `T`, listed in the identity report, and documented in the frozen §3.4 BLOCKING data review. For Stage R this applies to **META→METV**.
5. **CUSIP missing (empty string or absent):** the record is matched **by ticker only**, and only if `T` has **no foreign-entity record** in the retained Stage R set; otherwise it is an **unresolved identity conflict**. (Observed: empty CUSIPs on all 2016 → 2019/2020 records; META — the only symbol with a foreign entity — has no split/dividend record, empty or not.)
6. **FB → META:** bars via the documented `asof` mapping (frozen); corporate actions via query keys META + FB and the CUSIP set anchored on the FB→META record.
7. **Unresolved identity conflict** (any one): (a) `T` has ≥ 2 non-empty CUSIPs not linked by a name-change/split chain; (b) an empty-CUSIP split/dividend record under a `T` that has a foreign-entity record; (c) one CUSIP belongs to the sets of two universe symbols; (d) a chain cycle or a name change whose direction cannot be ordered by `process_date`.
8. **Blocking:** any unresolved identity conflict is a **BLOCKING data review**; Stage R data may not be used for any run until it is resolved and documented, or until a further committed amendment.
9. **Backstop (frozen, unchanged):** a foreign or mis-attributed dividend/split under ticker-only matching would appear as an event without a raw/all factor change and is caught by the frozen cross-check.

**PROTOCOL IMPACT:** adds the identity rule to §3.4 (events) and §3.8 (checks); §2/§3.1 (bars `asof`) unchanged.

**IMPLEMENTATION IMPACT:** identity resolver producing `identity.json` (anchors, CUSIP sets, aliases, foreign-entity records, conflicts); the asset endpoint's null `cusip` must not be relied on.

---

## C3 — Dividend `rate` basis

**STATUS: RESOLVED**

**Original v2.0 R1 rule** (§3.4): "`d_i(k)` = cash dividend per share with ex-date `k`, expressed per share held at the close of the previous session (pre-split basis if a split shares the ex-date)."

**Problem (DAY-17):** Alpaca documents no meaning for `rate` (DOC: "format: double"); restatement for later splits was unknown.

**EVIDENCE (PROBE A4 + follow-up; categories only, no rate printed):**
- For **AAPL** (2020 4-for-1) and **NVDA** (2021 4-for-1) — both publicly kept the per-share dividend economically unchanged across their splits — the ratio `rate(last dividend before split) / rate(first dividend after split)` **equals the split ratio** (`new_rate/old_rate`) → rates are on the **declared, unadjusted** basis, not restated.
- **Old (empty-CUSIP) vs new source:** for NVDA (constant per-share dividend from late 2018 to its 2021 split), `rate(last empty-CUSIP record) / rate(first CUSIP-bearing pre-split record) = 1` → the old source uses the same declared basis.
- **No symbol in Stage R has a split and a cash dividend on the same `ex_date`** (AAPL, NVDA, TSLA, AMZN, GOOGL checked).
- All forward splits have `new_rate/old_rate > 1` (confirms `q = new_rate / old_rate`, DAY-17 C6).
- The probe classification used 1e-6 only to categorise ratios; it is **not** a protocol tolerance.

**DECISION (v2.0.1 rule):**
1. `d_i(e)` = Alpaca `rate` of the identity-resolved `cash_dividends` record with `ex_date = e` (regular and `special = true` alike), interpreted as the **declared cash amount per share outstanding on the record date, unadjusted for any later split**.
2. Accounting (frozen §11.2, unchanged): on ex-date `e`, `cash += shares held at the close before e × d_i(e)`. When the ex-date precedes a later split, the shares held are pre-split shares and `d` is per pre-split share — consistent. When the ex-date follows a split, holdings already reflect the split and `d` is per post-split share — consistent.
3. PIT TR index (frozen §3.4 formula, unchanged): `D_i(p,k)` uses `d_i(e)` for ex-dates in `(p,k]` with the frozen post-split carry factor.
4. **Same-ex-date split + dividend** for one entity: Alpaca's basis for that case is not verified; such a case is a **BLOCKING data review** (none exists in Stage R).
5. Dividend **magnitude** is not cross-checked (frozen §3.4 cross-checks coincidence only); no new tolerance.

**PROTOCOL IMPACT:** clarifies §3.4 `d` source and basis; §11.2 unchanged.

**IMPLEMENTATION IMPACT:** normaliser maps `rate` → `d` without adjustment; `q = new_rate/old_rate`; same-ex-date detector raises BLOCKING.

---

## C4 — `data_quality` parameter, duplicates, corrections

**STATUS: RESOLVED**

**Original v2.0 R1 rule:** none (parameter not frozen).

**EVIDENCE:**
- DOC: `complete` (default) "exclude[s] corporate actions that are still missing required fields and have not yet been processed"; `all` returns them "regardless of field completeness".
- PROBE A2: for process_date 2016-01-01 → 2022-12-30 (25 + SPY + FB), `complete` and `all` returned the **same 492 records** (id-set difference 0; no record without `id`).
- PROBE A3: an identical repeat `complete` request returned an identical canonical payload; no duplicate (type, symbol, event_date) groups. (An earlier grouping by `cusip` reported 46 groups — an artifact of empty CUSIPs colliding across symbols, not duplicates.)
- DOC/PROBE: no status, correction or cancellation field exists.

**DECISION (v2.0.1 rule):**
1. Every Stage R CA query (Q1, Q2) is issued **twice**: `data_quality=complete` (**canonical**) and `data_quality=all` (**audit**). Both payloads are persisted (after the C1 filter).
2. Any retained universe record present in `all` but absent from `complete` (or vice versa) is a **BLOCKING data review**: incomplete records are never silently dropped or silently used.
3. **Duplicates:** two canonical records with the same (type, resolved entity, event_date) and different `id` are a **BLOCKING data review**.
4. **Corrections / cancellations:** Alpaca exposes no correction model; none is invented. Records are identified by `id`; any re-acquisition is compared record-by-record under the frozen write-once + IDENTICAL/DISCREPANCY rule (frozen §3.9); a DISCREPANCY is reported and investigated, the original snapshot is retained.

**PROTOCOL IMPACT:** adds the query parameter and two checks to §3.1/§3.8.

**IMPLEMENTATION IMPACT:** dual-query persistence, id-set comparison, duplicate detector.

---

## 5. Exact sections affected
| v2.0 R1 location | v2.0.1 effect |
|---|---|
| §3.1 "Corporate-action events" row | query contract: Q1 + Q2 windows (C1), query keys incl. aliases (C2), `data_quality` complete + all (C4) |
| §3.4 "Events" bullets | `event_date` definition (C1); identity rule (C2); `d` = declared `rate`, unadjusted; same-ex-date case = BLOCKING (C3) |
| §3.8 data-quality table | new BLOCKING data reviews: unresolved identity conflict (C2); complete/all difference; duplicate records (C4) |
| §3.9 Stage R bullet | "events 2016-01-04 → 2022-12-30" = event_date range; obtained via Q1 + Q2 with in-memory discard (C1) |
| §15.1 / §3.9 holdout prohibition | transient filtered contact with Q2 records whose event_date > 2022-12-30 is not acquisition; persistence/display/use is a violation (C1) |
| §20 Q3, Q16 | resolved for Stage R subject to C1–C4 rules |
| Checklist DATA-16, DATA-18, DATA-19, UNIV-07 | status changes listed in the JSON amendment (checklist file itself not modified) |

---

## 6. DAY-17A structural probe log
| Item | Value |
|---|---|
| Client | stdlib `urllib`, scratchpad scripts, `python -I`; deleted after the task |
| Requests | **32**, all HTTP 200 |
| Endpoints | `GET paper-api…/v2/assets/{symbol}` × 26 (metadata); `GET data…/v1/corporate-actions` × 6 |
| CA windows | `process_date` 2016-01-01 → 2022-12-30 only; **no Q2 (2023) window was requested in DAY-17A** |
| Bars | none requested |
| Output retained | booleans, counts, CUSIP-length/presence flags, ex-year ranges, ratio **categories**, request IDs |
| Never printed/stored | prices, volumes, dividend rates, split rates, CUSIP values |
| CA request IDs | complete `a13b3d4f9e65129dc8edc7804112520e`; all `9267d2d327b43b32d73cce06674e2cd1`; complete repeat `6bf8f49c8a22e2736bd5990ae56de9e9`; characterisation `3824ad5f5708ac9ff607a6d5c2467ed4` (output truncated by a local pipe, re-run as) `d766102fbdb4dc70ad4ff8782e45501b`; C3 old-source check `261b08b8cf9d4738a2f14f7253c625c9` |

## 7. Findings outside C1–C4 (recorded, not decided here)
- **SPY dividend-record count** in process_date 2016-01-01 → 2022-12-30 is 25, while a quarterly schedule with the December-2022 distribution processed in 2023 would imply 27 (INFERENCE from public knowledge of SPY's quarterly distributions; no values read). This may be a coverage gap in the old/new source transition. It affects **B2 (reference only)** and will be decided by the frozen raw/all cross-check at Stage R (BLOCKING data review if confirmed). No rule is changed here.
- The asset endpoint's documented `cusip` field is null on the current key (C2 evidence).

## 8. Stage R readiness
All four acquisition-semantic decisions are resolved by this amendment. Stage R may be **implemented and dry-run** only after this amendment is committed. Expected BLOCKING data reviews at Stage R (by frozen and v2.0.1 rules): acquirer-side mergers (NVDA←MLNX, CSCO←ACIA, MSFT←NUAN, CRM←WORK, AMD←XLNX), name change FB→META, foreign-entity record META→METV, and the SPY count question if the cross-check confirms a gap.

## 9. Safety statement
No bars were requested; no price, volume, dividend amount, split ratio or CUSIP value was printed or stored; every corporate-action request was bounded by `process_date ≤ 2022-12-30` (no 2023 process-date window was queried; any returned record was reduced in memory to the aggregate categories listed in §6 and discarded); no Stage R/H/forward acquisition; no research, backtest, signal or return; no code, data, cache, DAY-16 or DAY-17 file changed.
