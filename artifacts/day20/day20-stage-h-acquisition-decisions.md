# DAY-20 — Stage H acquisition decisions (committed before any Stage H request)

| Field | Value |
|---|---|
| Decided by | **Alixujaev (protocol owner)**, 2026-10-08, before any Stage H network request |
| Protocol | 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (frozen; unchanged) |
| Frozen Stage H range (§3.9) | Bars and events **2021-01-04 → 2026-06-02**: 503 lookback sessions plus the **856-session holdout** 2023-01-03 → 2026-06-02 |
| Trigger (§15.1) | The research gate is recorded for all families. V2-MOM and V2-STR are RESEARCH-PASSED (DAY-19 sign-off `48ce878`). |

## Clarifications
1. **Stage H corporate-action windows** mirror v2.0.1 C1, which defined windows for Stage R only:
   - **Q1:** process_date 2021-01-01 → 2026-06-02.
   - **Q2:** 2026-06-03 → 2026-08-31.
   - **Event_date boundary:** [2021-01-04, 2026-06-02].
   - **Out-of-range records:** discarded in memory before persistence, with counts only.
   - **Data quality:** both windows are queried with `complete` and `all`.
   - **Query keys:** 25 + SPY + FB.
   - **Forward isolation:** Q2 ends before the 2026-10-07 freeze, so no forward-dated process_date is requested.
2. **asof = 2026-10-07**, the freeze date and the same as Stage R. The literal acquisition date, 2026-10-08, is the first forward-OOS session.

## Conservative choices and disclosures
- **No `/v2/assets` call:** it returns current, forward-dated metadata, and its `cusip` is null.
- **Bar requests are hard-guarded** to the range 2021-01-04 … 2026-06-02.
- **adjustment=all is audit only (§3.4):** provider adjustment=all levels reflect adjustments up to request time. This is inherent to the frozen design: the series is never used for signals, fills, marks or P&L, and rebasing between stages is expected.
- **No strategy evaluation:** DAY-20 computes no signal, TR index, return, portfolio, metric or gate.
