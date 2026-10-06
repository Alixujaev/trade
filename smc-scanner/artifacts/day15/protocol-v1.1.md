# Protocol v1.1 — Alpaca SIP Research Re-baseline and Chronological OOS

## 1. Status and version

| Field | Value |
|---|---|
| **Status** | **FROZEN DRAFT — PENDING COMMIT** |
| **Version** | **1.1** |
| Drafted | 2026-10-06 |
| Parent protocol | v1.0 (`artifacts/day14/research-protocol.md`, commit `5d48c53`) |
| Repository HEAD at drafting | `b7977f5` |
| Authority | Once committed, this document governs every v1.1 experiment: Alpaca SIP research re-baseline and OOS evaluation. v1.0 documents are **not modified**. Where they conflict with v1.1, this document records the conflict (§24) and v1.1 governs v1.1 experiments only. |

**Freeze procedure:**
1. The user commits this file. The commit SHA and the file's SHA-256 are recorded by the first v1.1 task (DAY-15G) before it acquires any bar.
2. The commit must precede every v1.1 market-data request, every v1.1 snapshot, and every v1.1 result.
3. Several provenance documents this protocol relies on are **untracked** at drafting time (VERIFIED, `git status`):
   - `day15b-acquisition.md`;
   - `day15c-provider-audit.md`;
   - `day15d-oos-window-redesign.md`;
   - `day15e-alpaca-access.md`.

   They should be committed together with, or before, this file so that the provenance in §25 is fixed in git.
4. After the commit, any change is a new version (v1.1.x or v1.2) with its own commit. Results stay attributed to the version under which they were produced.

**Labels:**
- FROZEN: fixed by this protocol.
- VERIFIED: checked in the repository, the calendar, documentation or the DAY-15E probe.
- INFERRED: follows from documentation or code but was not observed.
- NOT VERIFIED: not established.
- NOT YET IMPLEMENTED: required code that does not exist.
- NOT PREDEFINED: deliberately has no threshold; it cannot be filled in after results.

**Drafting constraints (this task):**
- No market-data endpoint was called, and no OOS or research bar value was read.
- No indicator, signal, return or metric was computed.
- No code was changed.
- The only computation was a local `exchange_calendars` session resolution (no network).

---

## 2. Provider contract (FROZEN)

| Item | Value |
|---|---|
| Provider | Alpaca Market Data API v2 — Historical Stock Bars (`GET https://data.alpaca.markets/v2/stocks/{symbol}/bars`) |
| Feed | `feed=sip` |
| Intervals | `timeframe=5Min` (signal / execution) and `timeframe=15Min` (context) |
| Adjustment | `adjustment=raw` |
| Time bounds | explicit `start` and `end` on every request, as RFC-3339 UTC strings; no relative or "latest" requests |
| **End semantics** | **Alpaca request intervals use inclusive `end`. The acquisition implementation MUST NOT copy yfinance's exclusive-end convention.** (VERIFIED, DAY-15E: a request ending at 13:35:00Z returned the bar starting at 13:35:00Z.) |
| Strategy data | RTH only: `[09:30, 16:00)` America/New_York |
| Credentials | the existing paper key (`ALPACA_API_KEY` / `ALPACA_SECRET_KEY` in `.env`); never printed, logged or stored in artifacts |
| Entitlement | historical SIP 5Min verified for one in-sample request (VERIFIED, DAY-15E, request ID `0101142d296542296c6b8e19a1f5f4de`); 15Min NOT VERIFIED (§24) |
| Excluded providers | yfinance and Massive are not used for any v1.1 dataset. No v1.1 bar may come from another provider, and no back-fill is allowed. |

## 3. Chronological timeline (FROZEN)

Resolved with `exchange_calendars` 4.13.2, calendar `XNYS`, bounds 2026-01-02 → 2027-12-31, sessions in America/New_York (VERIFIED, local re-resolution on 2026-10-06).

**Rule (authoritative; the dates are its resolution):**
- `S` = XNYS sessions.
- Research = sessions of `S` in 2026-07-02 → 2026-09-25.
- Warmup = the 20 sessions of `S` immediately before 2026-07-02.
- `P` = sessions of `S` strictly after 2026-09-25, ascending.
- Embargo = `P[0]`; Stage 1 = `P[1:21]`; Stage 2 = `P[21:61]`; Final OOS = `P[1:61]`.

| Segment | Sessions | First | Last | Holidays skipped | Early closes |
|---|---|---|---|---|---|
| Research warmup | 20 | 2026-06-03 | 2026-07-01 | 2026-06-19 | none |
| Research | 60 | 2026-07-02 | 2026-09-25 | 2026-07-03, 2026-09-07 | none |
| Embargo | 1 | 2026-09-28 | 2026-09-28 | — | none |
| OOS Stage 1 | 20 | 2026-09-29 | 2026-10-26 | none | none |
| OOS Stage 2 | 40 | 2026-10-27 | 2026-12-22 | 2026-11-26 | **2026-11-27** (13:00 ET) |
| **Final OOS** | **60** | **2026-09-29** | **2026-12-22** | 2026-11-26 | 2026-11-27 |

```
 warmup (20)        research (60)               embargo   Stage 1 (20)         Stage 2 (40)
 06-03..07-01  |  07-02 .. 09-25           |  09-28  |  09-29 .. 10-26   |  10-27 .. 12-22
 no trades        Alpaca SIP re-baseline      no eval    interim report       continuation
                                                        |<------- final OOS: 60 sessions ------->|
```

- If the pinned calendar resolves differently at acquisition time (for example, an unscheduled closure), the rule governs. Acquisition stops for a documented review; nothing is substituted.
- Sessions are **never** substituted, dropped or moved because of market behaviour.
- DST: the US change on 2026-11-01 makes **2026-11-02** the first EST session (Stage 2). It is checked for the full 78/26 grid. No DST change falls in the warmup or research segments.

### Why this is a chronological OOS

1. Strategy development and research (DAY-01 → DAY-12B) used data through **2026-09-25**. The research cache's extended-hours files reach the **premarket of 2026-09-28** for 24 of 25 symbols (VERIFIED, DAY-15D §2).
2. This protocol is frozen **before** any Alpaca research re-baseline and before any OOS evaluation.
3. **2026-09-28 is an explicit embargo.** It is the session partly inside the development information set.
4. The first OOS session is **2026-09-29**, the first session wholly after the information cutoff.
5. The OOS dates are fixed by the calendar rule above. They were not selected after seeing performance; no OOS performance exists or has been viewed.
6. Stage 1 is an interim slice of the same fixed OOS period. Stage 2 completes it.
7. **No 2026 data before the research window is valid OOS** for this strategy. The warmup is indicator history only.

## 4. Research warmup (FROZEN)

- 2026-06-03 → 2026-07-01, 20 XNYS sessions, Alpaca SIP 5Min + 15Min.
- Purpose: indicator warmup only. RVOL uses up to 20 prior sessions (`strategy/day/vwap_momentum.py:122`, `lookback_sessions=20`).
- **No trades. No performance evaluation.** Signals whose signal bar falls in a warmup session are not traded or counted.
- **Known difference from the v1.0 research:** the yfinance research had no warmup, so its first sessions had thin RVOL baselines. The v1.1 re-baseline therefore differs from DAY-04 by design (provider and warmup). The difference is reported, never tuned away.

## 5. Research window (FROZEN)

- 2026-07-02 → 2026-09-25, 60 XNYS sessions: the historical research window of DAY-04 → DAY-12B.
- For v1.1, the frozen DAY-04 baseline is **re-run on Alpaca SIP data** before any OOS evaluation (§21).
- **The old yfinance DAY-04 → DAY-13 results remain historical exploratory evidence only.** They are not mixed numerically with Alpaca SIP results: no averaging, pooling, differencing presented as a result, or substitution. They are not used for any v1.1 gate or acceptance decision.

## 6. Embargo (FROZEN)

- Exactly one XNYS session: **2026-09-28**.
- **No research and no OOS performance evaluation.** No signal whose signal bar falls on 2026-09-28 is traded, counted or reported as a result.
- Its bars are acquired from Alpaca SIP together with Stage 1. They are used **only as indicator history** (RVOL continuity) for Stage 1 sessions. This is the same role warmup bars play.
- Reason for exactly one session: features are backward-looking and nothing is held overnight, so no trade label crosses the boundary. The only contamination is the research cache's 2026-09-28 premarket (DAY-15D §10).

## 7. OOS Stage 1 (FROZEN)

- 2026-09-29 → 2026-10-26, 20 XNYS sessions.
- Acquisition not before **2026-10-26 16:15 ET** (DAY-15A capture policy), and only if the research gate (§21) has passed.
- One interim run, after acquisition and structural checks.

## 8. OOS Stage 2 (FROZEN)

- 2026-10-27 → 2026-12-22, 40 XNYS sessions. Includes the early close 2026-11-27 (42 × 5m / 14 × 15m bars) and the first EST session 2026-11-02.
- Acquisition not before **2026-12-22 16:15 ET**.

## 9. Final 60-session OOS (FROZEN)

- **2026-09-29 → 2026-12-22, 60 XNYS sessions. This is the authoritative OOS evaluation.**
- One final run over the full 60 sessions after Stage 2 is acquired.
  - Indicator history is the continuous Alpaca SIP series: warmup → research → embargo → OOS.
  - Only signals whose signal bar lies in an OOS session are traded.
- **Determinism check (FROZEN):** the Stage 1 slice of the final run must reproduce the interim Stage 1 run trade-for-trade. Same data, PIT rules and no overnight positions make this expected. A mismatch is a protocol violation; it is reported and investigated, never reconciled by choosing one result.

## 10. Stage 1 interpretation (FROZEN)

- **Stage 1 is an interim report, not a permanent rejection gate.**
- Stage 1 results are reported after 20 sessions with the full metric set (§12).
- **A negative Stage 1 primary metric cannot, by itself, permanently reject the candidate.** Stage 2 continues on the fixed calendar regardless of Stage 1.
- Stage 1 also cannot accept the candidate.
- The DAY-15D draft rule "Stage 1 < 0 ⇒ reject forever" is **NOT ADOPTED**.
- **Independence:** the 20-session Stage 1 sample is **not** treated as statistically independent observations because it contains many trades across 25 symbols. Same-day trades across correlated large caps share market moves; the effective sample is closer to the number of sessions than to the number of trades. Stage 1 is reported as low-sample interim evidence.
- No tuning, re-run or interpretation change follows from Stage 1.

## 11. Stage 2 interpretation (FROZEN)

- Stage 2 is the continuation and confirmation part of the same fixed OOS period.
- Stage 2 results are reported separately, with the full metric set.
- Stage 2 alone does not decide acceptance. The decision is on the full 60 sessions (§12).

## 12. Final acceptance criteria (FROZEN)

**Primary metric** (carried from DAY-14 research-protocol §13; unchanged): **mean net trade return at 5 bps per side**.

**Accept** if and only if all of these hold on the **final 60-session OOS** (§9):
1. `mean_net_trade_return_5bps >= 0`;
2. data integrity: every structural check passes and the hash manifests match (§23);
3. the PIT future-mutation test passes for the candidate (research-protocol §3 rule 4);
4. the reproducibility block is complete (research-protocol §2);
5. the Stage 1 determinism check passes (§9).

Otherwise the candidate is **not accepted**. Stage-level results never override the full-period decision. The better-looking stage is never selected.

**Reported for Stage 1, Stage 2 and the combined 60 sessions, every time:**
- net returns at 0 / 5 / 10 bps per side:
  - compounded (1 unit per trade, entry order);
  - mean net trade return;
  - median net trade return;
- trade count, wins / losses / breakevens, win rate, profit factor (gross);
- expectancy (mean trade return %), total R, average R, median R;
- maximum drawdown;
- average and median holding time; exit-reason distribution;
- benchmark return (§15);
- symbol breadth: the share of symbols with positive net R, plus the per-symbol total R table;
- concentration: the top-2 symbols' share of total R;
- results by month and by time-of-day bin;
- trade-count accounting: candidates, entries, skips, `simulation_none`, missing-data exclusions;
- same-bar ambiguity count; gap-through fill count;
- session count actually evaluated.

**Thresholds that stay NOT PREDEFINED** (research-protocol §13): primary-metric magnitude, minimum trades, maximum drawdown, minimum symbol breadth, concentration limit, benchmark margin. They are reported only and are never added after results.

**No new primary metric.** No other metric may be promoted to primary after results.

## 13. Minimum-sample policy (FROZEN)

- No minimum Stage 1 trade count is required.
- No minimum Stage 2 trade count is required.
- No minimum total OOS trade count is imposed.
- **However:**
  - the actual trade count MUST always be reported, per stage and combined;
  - the actual session count MUST always be reported, per stage and combined, with any excluded symbol-sessions listed;
  - a low sample size MUST be described as a limitation in every report;
  - **the absence of a minimum count MUST NOT be changed after results are seen.**

## 14. Universe (FROZEN)

- The existing 25 symbols (`config/day_universe.py::FROZEN_DAY_UNIVERSE`): AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AVGO, AMD, QCOM, INTC, MU, AMAT, ADBE, CRM, ORCL, CSCO, COST, WMT, KO, PEP, NFLX, JNJ, JPM, XOM.
- No additions. No removals. No replacement symbols.
- A symbol-session genuinely unavailable in the provider data is **excluded and reported explicitly**, for both the strategy and the benchmark. It is never replaced, and never excluded for performance reasons.
- All 25 assets were active and tradable per Alpaca asset metadata on 2026-10-05 (VERIFIED, DAY-15C appendix).
- **The historical selection timestamp of the universe is UNKNOWN / NOT RECORDED** (DAY-14 research-protocol §1). The universe was first committed on 2026-09-28 (`dcebe47`). It consists of present-day large caps. v1.1 makes no survivorship-bias claim beyond this.
- SPY / QQQ are not part of the v1.1 baseline and are not acquired.

## 15. Benchmark (FROZEN)

- Equal-weight per-symbol buy & hold, as in DAY-14 research-protocol §12.
- Per symbol: from the **first RTH open** to the **last RTH close** of the evaluated sessions, from the same Alpaca SIP data. The returns are averaged with equal weights across symbols.
- Computed separately for Stage 1, Stage 2 and the final 60 sessions, over exactly the same sessions as the strategy.
- Same universe, same session exclusions, same missing-data exclusions as the strategy.
- **Never compared against the old yfinance benchmark.** It is not chosen or modified after strategy results are seen.

## 16. PIT / timestamp semantics (FROZEN)

- The provider bar timestamp is the bar **START** (VERIFIED for Alpaca 5Min, DAY-15E). Storage: tz-aware UTC index = bar open.
- A 5m or 15m bar is usable only after it closes: `bar_open + interval`.
- Entry happens at the **OPEN of the next eligible 5m bar** in the same session (research-protocol §1, §3).
- A decision at `as_of` uses only bars with `bar_end ≤ as_of` (`data/bars.py::filter_closed_bars`). No future bar may influence a signal, setup, stop, target, filter or eligibility.
- Sessions and RTH are evaluated in America/New_York; RTH = `[09:30, 16:00)`.
- **Any timestamp ambiguity is a protocol violation**: a naive index, off-grid bars, a bar-end labelling, or a mismatch between 5m and 15m coverage. It is reported and stops the run; it is never silently corrected.

## 17. Acquisition contract (FROZEN)

| Item | Rule |
|---|---|
| Request | `GET /v2/stocks/{symbol}/bars`, `feed=sip`, `adjustment=raw`, `timeframe` ∈ {`5Min`, `15Min`}, explicit `start` / `end` (UTC RFC-3339), fixed `limit`, every parameter recorded |
| `end` | **inclusive** (§2). For a contiguous block of sessions: `start` = the first session's 09:30 ET open; `end` = the last session's **last RTH bar open**. That is 15:55 ET (5Min) / 15:45 ET (15Min) on full days, and 12:55 / 12:45 ET on 2026-11-27. The yfinance "end = next day 00:00, exclusive" convention is **forbidden**. |
| Pagination | follow `next_page_token` until it is null; record the page count per request |
| Extended hours | Alpaca has no server-side session filter (INFERRED, DAY-15C). Bars outside `[09:30, 16:00)` ET returned inside a multi-session range are expected. They are excluded by the deterministic RTH rule, and **their count is recorded** per symbol-session. They are never used by the strategy. |
| Expected RTH bars | 78 × 5m (09:30 … 15:55 opens) and 26 × 15m (09:30 … 15:45) per full session; 42 × 5m / 14 × 15m on 2026-11-27 |
| Structural validation | data-expansion-spec §5 checks (the existing `acquisition/validation.py::structural_checks` logic): session list, bar grid, missing bars, duplicates, monotonicity, OHLC consistency, volume ≥ 0 and zero-volume count, RTH, UTC tz, 5m/15m coverage, hashes |
| Stored columns | `open, high, low, close, volume` (strategy); `trade_count` (Alpaca `n`) and `provider_vwap` (Alpaca `vw`) for provenance only. **The strategy VWAP is computed from bars (`indicators/vwap.py::compute_vwap`); provider `vw` is never used by the strategy.** No `adj_close` column exists for Alpaca. |
| Storage | write-once tree `data/oos_cache/protocol_v1.1/` (git-ignored), with separate `research/` (warmup + research) and `oos/` (embargo + Stage 1 + Stage 2) snapshots. **Never `data/cache/`.** |
| Snapshots | write-once, read-only after their manifest is written; per-file content and file SHA-256; `run.json` / `environment.json` per snapshot; derived manifest |
| Overwrite | forbidden |
| Discrepancy detection | any re-acquisition or overlap compared cell by cell → IDENTICAL or DISCREPANCY (§23) |
| Environment manifest | pip-freeze equivalent, Python version and calendar version per snapshot |
| Capture timing | no session requested before 16:15 ET on its date (DAY-15A capture policy) |
| Order | research (warmup + research) first; OOS only after the research gate passes (§21) |
| Separation | v1.1 acquisition never reads, merges or compares values with `data/oos_cache/protocol_v1.0/` (the yfinance captures) or with `data/cache/`. The v1.0 captures continue under v1.0 rules and are out of scope for v1.1. |
| Implementation | **NOT YET IMPLEMENTED** (§24). It must be a reviewed change in DAY-15G, made before acquisition. |

## 18. Corporate-action policy (FROZEN)

- The acquisition parameter is **`adjustment=raw`**. It is frozen and will not be reinterpreted or switched after any result is observed.
- **What DAY-15E verified:** the API accepted `adjustment=raw` (HTTP 200, no error).
- **What DAY-15E did not do:** a price-level semantic comparison. The response does not echo the adjustment applied. Semantic corporate-action validation beyond API acceptance was **not performed** and must not be claimed retroactively as verified.
- No price or volume adjustment is applied by the acquisition or the backtest.
- **No symbol-session is excluded because of a corporate action.**
- Split and dividend events for the 25 symbols over 2026-06-03 → 2026-12-22 may be listed from event *metadata* (not bars) and disclosed. A split inside the dataset is a known limitation: raw volume makes RVOL discontinuous across it. Intraday returns are unaffected because there are no overnight positions.

## 19. Transaction-cost scenarios (FROZEN)

| Scenario | Per side | ≈ Round trip | Role |
|---|---|---|---|
| 0 bps | 0 | 0 | reported (gross reference) |
| **5 bps** | **5 bps** | **≈ 10 bps** | **primary cost-adjusted evaluation** |
| 10 bps | 10 bps | ≈ 20 bps | stress case, reported |

- Formula: per-trade net return `(1 + g)(1 − s)/(1 + s) − 1`, with `s` = bps / 10,000, applied to every exit including breakeven, stop, target and forced exits (research-protocol §7).
- Commission is folded into the per-side bps. No spread or impact model.
- Gap-through stop and target fills are at the level price (an inherited limitation, research-protocol §7).
- Costs are never changed after results.

## 20. Candidate definition (FROZEN)

- **The only protocol-approved candidate is the frozen DAY-04 baseline.**
  - signal: `strategy/day/vwap_momentum.py`; valid statuses {DETECTED, CONFIRMED};
  - execution semantics: research-protocol §1 / §8, including the SIGNAL_LOW / VWAP / 0.99 stop, 2R target, STOP_FIRST, forced exit at the ≥ 15:55 ET bar close, one position per symbol, long-only;
  - `ExecutionConfig` defaults; costs 0 bps inside the simulation, with scenarios applied post hoc.
- The exact signal commit, full serialised `ExecutionConfig` and thresholds are recorded in DAY-15G's reproducibility block. **No strategy, signal, indicator or execution code may change between this freeze and the final OOS run.**
- Other variants (DAY-05 → DAY-12B families) are **not** approved by v1.1.
  - Re-testing any of them requires an amendment (v1.1.x), committed before its SIP research run, naming the variants and why they are included.
  - Such variants are labelled **DERIVED FROM PRIOR OBSERVATION**, counted in their family's cumulative variant count, and cannot silently become primary candidates.

## 21. Research re-baseline gate (FROZEN)

Before any OOS performance evaluation, in this order:
1. Acquire the Alpaca SIP research dataset: warmup + research, 2026-06-03 → 2026-09-25, 25 symbols, 5Min + 15Min (§17).
2. Run the structural checks; every check must pass or be documented as an exclusion (§14).
3. Re-run the frozen DAY-04 baseline (§20) on the continuous SIP series, trading only research sessions.
4. Apply this v1.1 methodology: costs (§19), metrics (§12 list), PIT test (§16).
5. **Gate:** the research `mean_net_trade_return_5bps >= 0` (DAY-14 research-protocol §11 / §13 primary sign condition; no new threshold).
6. **Only if the gate passes** does the candidate proceed. OOS bars (embargo, Stage 1, Stage 2) are acquired only then.
   - If the gate fails, no OOS bar is acquired under v1.1, and the result is reported as "v1.1 research gate: NO".

**Rules:**
- **The old yfinance DAY-04 result is not used** to decide whether the Alpaca OOS proceeds.
- No variant is selected by the best observed Alpaca research result.
- If amended variants are re-tested (§20), their inclusion is fixed by the amendment, not by performance. **Every tested variant stays visible in the research record, including failures and zero-trade variants.**
- The research re-baseline is a new exploratory run in family F-BASE (provenance PREDECLARED; variant count +1). The research window remains exhausted for confirmation.
- No Alpaca research performance was inspected while writing this protocol; none exists.

## 22. No-post-hoc-selection rules (FROZEN)

After this protocol is committed, none of the following may happen in response to any result:
- choosing the best Stage 1 result;
- choosing the best Stage 2 result;
- changing any threshold, including adding a NOT PREDEFINED threshold;
- changing the universe;
- changing the provider, feed, adjustment or intervals;
- changing cost assumptions;
- changing the warmup, research, embargo or OOS dates or session rule;
- changing the Stage 1 / Stage 2 interpretation or the final acceptance rule;
- changing the primary metric or promoting a secondary metric;
- re-running an OOS stage, except a documented technical-failure re-run with the identical frozen configuration, reported as such;
- changing strategy, signal, indicator or execution code for v1.1 candidates.

**Derived hypotheses** prompted by any v1.1 result are labelled DERIVED FROM PRIOR OBSERVATION. They need a new protocol version and new, later data, and cannot be confirmed on the v1.1 OOS.

## 23. Data-integrity rules (FROZEN)

Every snapshot (research and each OOS stage) records:
- provider and endpoint;
- feed;
- adjustment;
- interval;
- requested `start` / `end` and their **inclusive** semantics;
- timezone (UTC storage, America/New_York sessions);
- row counts before and after the RTH rule;
- expected-bar validation per symbol-session;
- per-file content and file SHA-256;
- the environment manifest;
- the acquisition timestamp (UTC);
- page count;
- the acquisition code commit SHA;
- this protocol's commit SHA.

**Overlapping or repeated acquisitions:**
- **IDENTICAL** → acceptable; recorded.
- **DISCREPANCY** → the original immutable snapshot is retained, the new copy is kept separately with its hashes, and the symbol-session is flagged. No "correct" version is chosen at acquisition time.
- **The original snapshot is never overwritten.**

Every later use recomputes and compares the manifests. A mismatch invalidates the run.

Before every v1.1 step, a preflight confirms that frozen inputs are unchanged.
- **Already covered** by `artifacts/day15/integrity-baseline.json` (VERIFIED: it lists `data/cache` and `artifacts/day04` … `artifacts/day14`):
  - `data/cache/`;
  - the DAY-04 → DAY-14 artifacts.
- **Not yet covered** (NOT YET IMPLEMENTED; a v1.1 baseline extension is needed):
  - `data/oos_cache/protocol_v1.0/`;
  - the DAY-15 documents;
  - this protocol file.

## 24. Conflicts, implementation gaps and open issues

### 24.1 Conflicts with historical documents (recorded; historical documents not modified)

| Document / location | Historical content | v1.1 position |
|---|---|---|
| `day14/data-expansion-spec.md` §1, line 24 | provider = yfinance only | superseded for v1.1: Alpaca SIP (§2) |
| `day14/data-expansion-spec.md` §3, line 55 | no back-fill from another provider | not applicable: v1.1 is single-provider from the start |
| `day14/data-expansion-spec.md` §2–§3 | OOS = first 60 sessions after 2026-09-25 (09-28 → 12-21), no embargo | superseded for v1.1: embargo 09-28; OOS 09-29 → 12-22 in two stages (§3) |
| `day14/data-expansion-spec.md` §4 | yfinance incremental snapshots in `protocol_v1.0/` | v1.1 uses `protocol_v1.1/` (§17); v1.0 captures continue untouched |
| `day14/oos-protocol-template.md` §5, §7 | v1.0 OOS rule; single-run acceptance | the v1.1 candidate protocol uses §3, §10–§12 |
| `day14/research-protocol.md` §1 | yfinance baseline (5,691 trades, PF 0.9388) | historical exploratory evidence; not a v1.1 reference |
| `day15/day15d-oos-window-redesign.md` §8 | proposed: Stage 1 < 0 ⇒ final rejection; accept iff Stage 1 ≥ 0 **and** Stage 2 ≥ 0 | **not adopted**: Stage 1 is interim (§10); acceptance is on the full 60 sessions (§12) |
| `day15/day15d-oos-window-redesign.md` §16 Q1 | adjustment mode open | resolved: `adjustment=raw` (§18) |
| `day15/day15d-oos-window-redesign.md` §13 | DAY-05 → DAY-12B families "optional" on SIP | allowed only via an amendment before the run (§20) |
| DAY-15F task text | cites `artifacts/day15/day15a-provider-verification.md` | the actual file is `artifacts/day15/provider-verification.md` (the DAY-15A yfinance verification) |

### 24.2 Implementation gaps (existing code contradicts v1.1; documented, not changed)

All are **NOT YET IMPLEMENTED** for v1.1. They must be addressed by a reviewed DAY-15G change before any v1.1 acquisition.

1. **`acquisition/contract.py`** is the v1.0 contract:
   - `ProviderConfig(provider="yfinance")`;
   - `RESEARCH_WINDOW_END` / `OOS_RULE` = first 60 after 2026-09-25;
   - `OOS_ROOT = data/oos_cache/protocol_v1.0`;
   - `STORED_COLUMNS` includes `adj_close`, which Alpaca does not provide.
2. **`acquisition/provider_adapter.py`** is yfinance-only:
   - its request window is documented as `[start, end)`, the exclusive convention forbidden for Alpaca;
   - `earliest_requestable_start` encodes the yfinance 60-day limit, which does not apply to Alpaca.
3. **`acquisition/sessions.py::resolve_oos_sessions`** resolves 2026-09-28 → 2026-12-21. v1.1 needs `P[1:61]` = 2026-09-29 → 2026-12-22, plus the warmup, research and embargo segments.
4. **`acquisition/run.py::preflight`** asserts the v1.0 rule (60 sessions, first strictly after 2026-09-25).
5. **`data/alpaca_provider.py`** hard-codes the IEX feed and a relative start, and writes to `data/cache/`. It must not be used for v1.1 (DAY-15C §4).
6. **Reusable as-is or by pattern** (INFERRED from code reading):
   - `acquisition/capture_policy.py` (16:15 ET wait);
   - `acquisition/validation.py::structural_checks` (column set to be parameterised);
   - the write-once snapshot, ledger and hash mechanisms (`snapshot.py`, `ledger.py`);
   - `environment.py`;
   - `FULL_SESSION_BARS` 78 / 26;
   - the calendar pinning in `sessions.py`.
7. No backtest entry point currently reads `data/oos_cache/protocol_v1.1/`. The engine reads the research cache. A v1.1 data loader that feeds the continuous SIP series into the unchanged engine is NOT YET IMPLEMENTED. It must not change strategy or execution logic.

### 24.3 Open issues (none changes a frozen rule)

| # | Issue | Status |
|---|---|---|
| O1 | 15Min SIP access: only 5Min was probed (DAY-15E) | NOT VERIFIED; the first DAY-15G request will reveal it. If unavailable, stop and amend; never substitute a resample silently. |
| O2 | Finality of Alpaca historical bars (late-trade recalculation; no documented cutoff) | NOT VERIFIED; covered by the DISCREPANCY mechanism (§23) |
| O3 | Universe selection date | UNKNOWN (inherited) |
| O4 | Intrabar order (5m), gap-through fills at level, 1-unit compounding | inherited limitations (research-protocol §7); separate experiments only |
| O5 | Low effective sample of Stage 1 and of a one-quarter OOS | disclosed (§10, §13); no threshold added |
| O6 | Corporate actions under raw adjustment | disclosed only (§18) |
| O7 | Implementation gaps §24.2 | DAY-15G prerequisite |

## 25. Provenance

| Ref | Path | Relevance |
|---|---|---|
| DAY-13 | `artifacts/day13/oos-gate.md`, `research-synthesis.md` | OOS gate = NO; no cost-robust variant on yfinance research |
| DAY-14 | `artifacts/day14/research-protocol.md` (v1.0, commit `5d48c53`) | primary metric, costs, PIT, execution, reproducibility, acceptance framework |
| DAY-14 | `artifacts/day14/data-expansion-spec.md` | market-data contract, structural checks, v1.0 OOS rule |
| DAY-14 | `artifacts/day14/oos-protocol-template.md` | candidate-protocol template |
| DAY-15A | `artifacts/day15/provider-verification.md`, `day15a-finalization.md`, `acquisition-design.md` (commit `e213772`) | yfinance semantics; calendar pin; capture policy; write-once design |
| DAY-15B | `artifacts/day15/day15b-lifecycle.md` (commit `b7977f5`), `day15b-acquisition.md` | incremental capture lifecycle; v1.0 snapshot `capture_20261002T0636ET_s001-s004` (structural only) |
| DAY-15C | `artifacts/day15/day15c-provider-audit.md` | Alpaca / Massive / yfinance capabilities; docs references [A1]–[A4], [M1], [M2], [Y1] |
| DAY-15D | `artifacts/day15/day15d-oos-window-redesign.md` | information cutoff (09-28 premarket), chronology, timeline |
| DAY-15E | `artifacts/day15/day15e-alpaca-access.md` | SIP 5Min entitlement, inclusive `end`, bar-start labels, `raw` accepted |
| Code | `config/day_universe.py`, `strategy/day/vwap_momentum.py`, `indicators/vwap.py`, `backtest/execution.py`, `data/bars.py`, `data/session.py`, `acquisition/*` | frozen definitions referenced above |

**What information was known when this protocol was written:**
- every artifact listed above;
- the yfinance research results of DAY-04 → DAY-12B (all negative after 5 bps; DAY-13);
- the structural-only v1.0 snapshot report;
- the DAY-15E probe (field presence and timestamps of two AAPL bars on 2026-07-02; no prices viewed).

No Alpaca research or OOS performance, and no OOS price, was known.
