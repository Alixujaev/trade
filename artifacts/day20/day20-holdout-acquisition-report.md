# DAY-20 — Historical Holdout (Stage H) Data Acquisition and Validation

> **DATA ACQUISITION AND DATA VALIDATION ONLY.**
> - No strategy was evaluated.
> - No signal, TR index, ranking, position, portfolio or gate was computed.
> - No performance metric was calculated or persisted.
> - Forward OOS was not accessed.
>
> This is **data-acquisition validation, not strategy-lookahead validation**. Lookahead tests belong to the later frozen holdout evaluation.

| # | Item | Value |
|---|---|---|
| 1 | Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (frozen; unchanged) |
| 2 | Starting HEAD | `48ce878` (DAY-19 sign-off) |
| 3 | Commits this task | `eb7abf7` decision record (**before any Stage H request**) → `1cd321d` implementation (**before acquisition**; the capture ran on a clean tree at `1cd321d`) → this report commit |
| 4 | Stage R manifest | `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` (unchanged) |
| 5 | Stage H snapshot | `data/oos_cache/protocol_v2/stage_h/stage_h_20261008T100604Z/` (write-once; 63 files; 6.79 MB) |
| 6 | Stage H manifest SHA-256 | `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34` |
| 7 | Acquisition timestamp | 2026-10-08T10:06:04Z → 10:07:40Z (56 requests: 52 bars, 4 corporate-action) |
| 8 | Provider | Alpaca: `/v2/stocks/bars` (feed=sip, 1Day, raw and all) and `/v1/corporate-actions` (complete and all). No other source and no `/v2/assets` call. |
| 9 | Session range | Stage H 2021-01-04 → 2026-06-02 (frozen §3.9). **Evaluated holdout 2023-01-03 → 2026-06-02.** |
| 10 | Expected sessions | Stage H **1359** = **503** lookback (2021-01-04 → 2022-12-30, inside R∩H, never evaluated) + **856** holdout |
| 11 | Actual sessions | **1359 / 1359 for all 52 series** (26 raw, 26 all). 0 missing in the lookback, 0 missing in the holdout. First bar 2021-01-04, last bar 2026-06-02. |
| 12 | Symbols | The frozen 25 universe symbols + SPY (B2). CA query keys add FB (v2.0.1 C2 alias). |
| 13 | Raw / adjusted rows | 26 × 1359 raw and 26 × 1359 adjustment=all. Raw and all session sets are identical for every symbol. |
| 14 | Corporate actions | Retained **433** records (Q1: 429, Q2: 4); `complete` = `all` (0 differences). Discarded in memory, counts only: 3 before 2021-01-04 (Q1) and 17 after 2026-06-02 (Q2). Normalised events: **407 dividends + 8 splits**. The splits are AMZN 2022-06-06, GOOGL 2022-07-18, NVDA 2021-07-20, TSLA 2022-08-25, WMT 2024-02-26, NVDA 2024-06-10, AVGO 2024-07-15 and NFLX 2025-11-17. The first-session dividend (CSCO 2021-01-04) is excluded per v2.0.2. |
| 15 | Identity | 433 records: 428 assigned by **CUSIP** (0 ticker-only), 0 unassigned, **0 conflicts**. **4 foreign-entity records, correctly excluded under C2 rule 4:** META→METV, as in Stage R, and 3 cash dividends under the **reused ticker FB** with a CUSIP outside META's set. All 9 Meta Platforms dividends are CUSIP-assigned and matched. **1 IDENTITY_UNVERIFIED:** AMD←XLNX (see 23). |
| 16 | Boundary validation | **PASS** (detail below) |
| 17 | Stage R overlap (R∩H 2021-01-04 → 2022-12-30) | **Raw bars IDENTICAL, cell by cell,** for 26/26 symbols (OHLCV, trade count, VWAP). **Events IDENTICAL:** 152/152 records, with 0 only-in-R, 0 only-in-H and 0 content differences. adjustment=all levels are excluded, since rebasing is expected (frozen §3.9). |
| 18 | Manifest / hashes | 62/62 manifest entries match, no unlisted files, **0 writable files**. Stage R and all earlier outputs are unchanged. |
| 19 | Determinism / integrity | The offline recompute matches the capture for identity, events, data quality, validation, cross-check and reviews. A **second validation run is byte-identical** (`validation_report.json` SHA-256 `84cfe895…`). |
| 20 | Strategy evaluation | **None occurred.** |
| 21 | Performance metrics | **None calculated.** No price value is reported. |
| 22 | Forward OOS | **Not accessed:** bars end 2026-06-02; CA windows end 2026-08-31, before the 2026-10-07 freeze; asof 2026-10-07; no assets call. |
| 23 | **Final status** | **BLOCKED.** All data checks pass, but **18 frozen BLOCKING review items** need protocol-owner review records (below). |

**Boundary detail (item 16):**
- **Sessions:** 1359 expected, holdout 856 (2023-01-03 … 2026-06-02).
- **No overlap:** the research segment ends 2022-12-30 and the evaluated holdout starts 2023-01-03.
- **Bar range:** the min/max bar session is 2021-01-04 / 2026-06-02.
- **Bar requests:** every request is bounded by `2021-01-04T05:00Z` … `2026-06-02T04:00Z`.
- **CA windows:** they match the committed decision.
- **Event dates:** every persisted CA event_date lies in [2021-01-04, 2026-06-02]. 3,032 dates were leak-checked before the write.
- **Parameters:** asof = 2026-10-07; no assets endpoint call; no forward-dated request.

## Why BLOCKED (data is valid; frozen review items remain)
Under v2.0.3 item 2, each of these items can be resolved **only** by a committed, human-decided review record whose `source_snapshot_manifest_sha256` equals the Stage H manifest. The Stage R records are bound to the Stage R manifest and do not apply. **The agent creates no records.**

| # | Item | Category | Period |
|---|---|---|---|
| 1 | AMD←XLNX stock merger, 2022-02-14 (acquirer side) | IDENTITY_UNVERIFIED (AMD has no CUSIP anchor; same as Stage R) | lookback (R∩H) |
| 2–7 | NVDA cash dividends 2021-03-09, 2021-06-09, 2021-12-01, 2022-03-02, 2022-06-08, 2022-09-07 | UNCONFIRMED_EVENT (no detected change in the rebased adjusted series) | lookback (R∩H) |
| 8–18 | NVDA cash dividends 2023-03-07, 2023-06-07, 2023-09-06, 2023-12-05, 2024-03-05, 2024-09-12, 2024-12-05, 2025-03-12, 2025-06-11, 2025-09-11, 2025-12-04 | UNCONFIRMED_EVENT | holdout |

- **NVDA cross-check:** 23 expected events, 6 matched, 17 unconfirmed; 0 unexplained changes, 0 numerical false positives or negatives, 0 invalid.
- **Precedent:** the pattern is the same as the Stage R NVDA dividends that DAY-18F resolved with EVENT_RETAINED records.
- **Resolved automatically under the frozen rules:** 13 items. These are acquirer-side mergers on clean dates (AVGO←VMW ×2, CRM←WORK, CSCO←ACIA, JNJ←ITCI/SWAV/AMAM, MSFT←NUAN, XOM←DEN/PXD, AMZN←ONEM, WMT←VZIO) and the pure rename FB→META. Separately, 4 foreign-entity records are excluded.

## Methodology notes
- **Decisions committed first (`eb7abf7`):** CA windows mirror v2.0.1 C1; asof = 2026-10-07 because the literal acquisition date is forward OOS; no assets call.
- **Implementation committed before acquisition (`1cd321d`):** the capture ran on a clean tree, which avoids DAY-19 deviation D1.
- **Correction to the task brief (frozen §3.4):** adjustment=all bars are **audit-only**, used only for the implied-factor cross-check. The later holdout signals are built from the PIT TR index of raw closes and events. Provider adjustment=all levels reflect adjustments up to request time (disclosed; levels are never used).
- **Tests:** `tests/test_day20_stage_h.py` 9 passed; focused acquisition and research suites 123 passed. No strategy code was run.
