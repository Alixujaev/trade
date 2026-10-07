# DAY-18 — Stage R Acquisition Report (protocol v2.0 R1 + v2.0.1)

| Field | Value |
|---|---|
| Date | 2026-10-07 |
| Governing protocol | v2.0 R1 (`ba3cefe`) + v2.0.1 clarification (`ed034b3`) — both unchanged |
| Code commit used for the run | `3fe0c92e18c70d35da73a5b4a799cfbb4c78bae4` (`feat: implement DAY-18 Stage R acquisition`), clean tree at run time |
| Snapshot | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/` (git-ignored, write-once, read-only files) |
| Snapshot manifest SHA-256 | `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` |
| `usable_for_research` | **false** |
| Stage R status | **ACQUIRED — BLOCKED** (protocol change required, §4) |

**Scope statement.** Acquisition, identity resolution, normalisation, structural validation, raw/all cross-check and leakage checks only. **No signal, return, index, backtest or performance value was computed. No price was printed or inspected.** The statistics in §4 are counts of threshold exceedances of the raw/all adjustment-factor ratio, computed programmatically; no factor, price or return value was displayed.

---

## 1. What was acquired

| Item | Value |
|---|---|
| Symbols | 25 `FROZEN_DAY_UNIVERSE` + SPY |
| Bars | SIP `1Day`, `adjustment=raw` and `adjustment=all`, `asof=2026-10-07`, start label `2016-01-04T05:00:00Z`, end label `2022-12-30T05:00:00Z` (inclusive) — 52 requests, 26 × 1762 rows per series |
| Corporate actions | `/v1/corporate-actions`, symbols = 25 + SPY + FB, all 16 types; Q1 process 2016-01-01→2022-12-30 and Q2 process 2022-12-31→2023-03-31; each with `data_quality=complete` and `all` |
| Corporate-action records retained | Q1: 492 (complete) / 492 (all); Q2: 4 / 4 — total 496 unique |
| Discarded by the event-date boundary (in memory, never persisted) | Q2: 15 (complete) / 15 (all) with event_date > 2022-12-30; 0 before 2016-01-04; 0 undated |
| Asset metadata | 26 × `/v2/assets/{symbol}` (status, exchange, name; `cusip` null, as in DAY-17A) |
| Requests total | 82, all HTTP 200 |
| Persisted files | 63 (52 parquet + 11 JSON incl. manifest) |

## 2. Checks that PASSED

| Check | Result |
|---|---|
| Preflight: DAY-16 + v2.0.1 files equal to their commits; integrity baseline; clean tree; 1762 sessions | passed (after restoring line endings, §6) |
| Structural validation (labels = 00:00 New York of an XNYS session, no pre/post rows, no duplicates, monotonic UTC, OHLC consistency, prices > 0, volume ≥ 0, first bar, missing-session rule) | **52 / 52 series OK**, 0 HARD_FAIL, 0 BLOCKING |
| raw vs all session-date sets | equal for 26 / 26 symbols |
| Bar request range | every request within 2016-01-04 … 2022-12-30 labels; persisted session_date range 2016-01-04 … 2022-12-30 |
| `data_quality` complete vs all | identical id sets and content (0 differences) |
| Identity (v2.0.1 C2) | 496 records: 493 assigned (209 by CUSIP, 284 ticker-only on empty-CUSIP records), 3 foreign-entity, 0 unassigned, **0 conflicts**; alias FB→META; anchors defined for 22 / 26 symbols |
| Event normalisation (v2.0.1 C3) | 489 events: 483 cash dividends (`d` = declared rate), 6 forward splits (q > 1); 0 normalisation blockers (no same-ex-date split + dividend, no duplicates, no invalid rates) |
| Event → factor-change coincidence | **0 unmatched events in all 26 symbols** (every checked retained event coincides with a raw/all factor change); **6 / 6 split magnitudes within the frozen 0.1 %** |
| Leakage (runtime) | pre-persistence assertion over 3,458 event/ex dates: none > 2022-12-30 |
| Leakage (independent scan of the written snapshot) | no `event_date` / `ex_date` / `effective_date` after 2022-12-30 in any file; dates after 2022-12-30 occur only as `process_date`/`payable_date`/`record_date` of the 4 retained Q2 records (construction metadata, v2.0.1 C1 rule 6), the Q2 window constants and run timestamps |

## 3. Tests
- `tests/test_day18_stage_r.py`: **23 passed** (fake provider; leakage, identity, normalisation, validation, cross-check, write-once, forbidden roots, end-to-end).
- Full suite: **1206 passed**, 0 failed (19 min 14 s), run before commit `3fe0c92`.

## 4. BLOCKING — PROTOCOL CHANGE REQUIRED: cross-check tolerance infeasible

**Frozen rule (v2.0 R1 §3.4):** a factor change exists where `|f(k)/f(p) − 1| > 1e-6`, `f = C_raw / C_all`; every change must coincide with an event.

**Finding:**
- Alpaca's `adjustment=all` closes are stored with **2–4 decimals** (mostly 2). Backward adjustment for corporate actions up to the `asof` date (including post-2022 events, e.g. dividends initiated by META and CRM in 2024 and NFLX's 2025 split) rescales the whole history, and rounding the rescaled values makes the ratio `f` jitter from day to day.
- Result: 24 / 26 symbols show **1,475 – 1,734 "factor changes" on non-event sessions** (only ADBE and AMD, whose `all` series equals `raw`, show 0).
- Non-event jitter counts across all 26 symbols: exceeds 1e-6 on almost every session, 1e-5 on 904–1,647 sessions per affected symbol, 1e-4 on 0–907, **1e-3 on 0 sessions in every symbol**.
- Event-date changes: dividends exceed 1e-3 on 460 / 480 checked dates; **20 NVDA dividend dates are ≤ 1e-3** (very low yield), i.e. inside the observed non-event noise band; splits exceed 1e-2 on 6 / 6.

**Consequence:** with the frozen 1e-6 tolerance the cross-check cannot pass for any symbol with post-2022 adjustments; and no single fixed threshold cleanly separates every true dividend (NVDA) from rounding noise. **No tolerance was changed in DAY-18.** The protocol owner must decide a v2.0.x rule (for example a precision-aware tolerance derived from the stored decimal places, or a different completeness test); that decision is out of scope here.

Supporting evidence that event completeness is otherwise sound (not a resolution): 0 unmatched events; 0 non-event factor changes above 1e-3 in any symbol, which would be the signature of a missing ordinary dividend or split.

## 5. Review classification (rules in `acquisition/v2/reviews.py`; data only)

| Item | Status | Basis |
|---|---|---|
| raw/all cross-check: AAPL, AMAT, AMZN, AVGO, COST, CRM, CSCO, GOOGL, INTC, JNJ, JPM, KO, META, MSFT, MU, NFLX, NVDA, ORCL, PEP, QCOM, SPY, TSLA, WMT, XOM | **BLOCKING** | §4 (tolerance infeasible); ADBE, AMD pass |
| cash_merger NVDA ← MLNX (2020-04-27) | **BLOCKING** | NVDA is the acquirer (CUSIP-matched), but the rule requires a clean cross-check on the date — blocked only by §4 |
| cash_merger CSCO ← ACIA (2021-03-01) | **BLOCKING** | same as above |
| cash_merger MSFT ← NUAN (2022-03-04) | **BLOCKING** | same as above |
| name_change FB → META (2022-06-09) | **BLOCKING** | pure rename (old CUSIP = new CUSIP); blocked only by §4 |
| name_change META → METV (2022-01-31) | RESOLVED_EXCLUDED | foreign entity (CUSIP not in META's set; v2.0.1 C2 rule 4) |
| stock_and_cash_merger CRM ← WORK (2021-07-21) | RESOLVED_EXCLUDED — **caveat** | CRM has no CUSIP-bearing split/dividend record, so its anchor is undefined and every CUSIP-bearing CRM record is classified foreign by C2 rule 4. Economically neutral under either classification (acquirer side: no share or cash effect), but the classification should be confirmed by the reviewer |
| stock_merger AMD ← XLNX (2022-02-14) | RESOLVED_EXCLUDED — **caveat** | same situation as CRM |
| 3 dividends with ex_date 2016-01-04 (CSCO, JPM, ORCL) | **BLOCKING (decision needed)** | ex_date on the first acquired session: no previous session exists, so the frozen bijection cannot check them. Under the frozen TR formula an ex-date equal to the first close is never applied (it lies in no `(p, k]`), so the impact is nil; the protocol does not state how to treat such events |
| SPY corporate-action completeness (DAY-17A question) | **BLOCKING (undetermined)** | 26 SPY dividends retained (incl. 1 from Q2), all 26 coincide with factor changes; 0 non-event SPY changes above 1e-3. Strong evidence of no missing SPY event, but formally undetermined until §4 is decided |
| complete vs all difference | NOT APPLICABLE (none) | — |
| same-ex-date split + dividend | NOT APPLICABLE (none) | — |
| identity conflicts / unassigned records | NOT APPLICABLE (none) | — |

## 6. Process event: frozen artifacts' line endings restored
Preflight initially refused (no request made): `artifacts/day13` and `artifacts/day14` differed from `artifacts/day15/integrity-baseline.json`. Diagnosis: 5 Markdown files carried CRLF line endings written by the earlier `main → feature` checkout under `core.autocrlf=true`; their LF-normalised bytes and committed blobs equal the baseline exactly. With the user's approval each file was rewritten from its committed blob (byte-identical to the baseline). `git diff` was empty throughout; `git add` refreshed the index entries with an empty staged diff. No artifact content changed. Caveat: a future checkout can reintroduce CRLF; a `.gitattributes` rule would be a separate decision.

## 7. Not done
No holdout or forward-OOS bars; no corporate-action record with event_date > 2022-12-30 persisted; no TR index, signal, return, backtest or metric; no protocol, universe, strategy or tolerance change; no push.
