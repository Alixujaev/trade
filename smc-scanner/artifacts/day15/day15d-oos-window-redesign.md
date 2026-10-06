# DAY-15D — OOS Window Redesign (corrected chronology)

**Scope:**
- Protocol design only. **No market-data endpoint was called.** No bar of any date was requested, and no OOS bar was read.
- No signals, returns, backtests or metrics were computed.
- No code, protocol document, snapshot, `data/cache/` or `data/oos_cache/` file was changed. DAY-04 → DAY-15C artifacts are untouched.
- **Nothing here is in force.** This is a proposal for protocol **v1.1**. It takes effect only once committed, before any v1.1 bar is read.

**Date:** 2026-10-06. This version **replaces** the earlier DAY-15D draft of the same date. That draft recommended a pre-sample OOS (2026-03-09 → 06-02); it is retracted in §1.

**Labels:**
- VERIFIED: checked in git history, repository files, documentation, a local calendar resolution, or parquet footer metadata (timestamp statistics and row counts only; no price or volume values read).
- INFERRED: follows from documentation or code but was not observed.
- NOT VERIFIED: cannot be checked without requesting bars.
- REJECTED: fails a hard requirement.
- RECOMMENDED: the single proposed primary path.

**User decision recorded (2026-10-06):** primary path = "Shorter OOS, fixed now" (§8). It was chosen from the options in §3 before any OOS bar existed in readable form. The only OOS-period data already held is the v1.0 snapshot of 2026-09-28 → 10-01, which has had structural checks only.

---

## 1. Why the previous recommendation was invalid — REJECTED

- The previous draft set OOS = 2026-03-09 → 2026-06-02, which comes **before** the research data (2026-07-02 → 2026-09-25).
- The strategy, its thresholds, the 40 variants and every research decision were made by a researcher who had seen 2026-07-02 → 09-25.
- Testing that strategy on an earlier period means the model was built with information from **after** the test period.
- "The intraday bars of that period were never inspected" does not repair this. The defect is chronological: the development information set extends past the OOS.
- A forward OOS claim requires: **development information set → embargo → OOS → today**. The previous draft violated that.

## 2. Correct chronological requirement

**Requirement:** every OOS session must lie strictly after the end of the information set used to develop the strategy. It is not enough that it lie after the end of a window *labelled* "research".

**The information cutoff (VERIFIED):**

| Evidence | Value |
|---|---|
| First commit of strategy, universe and execution code (`strategy/day/vwap_momentum.py`, `config/day_universe.py`, `backtest/execution.py`) | `dcebe47`, 2026-09-28, together with DAY-01 → DAY-06 |
| Later variant work | DAY-07 → DAY-12B commits, 2026-09-29 → 2026-10-05 |
| Research cache, RTH 5m / 15m | 2026-07-02 → 2026-09-25 (all 5m/15m files) |
| Research cache, `*_5m_ext.parquet` (extended hours) | 24 of 25 symbols end on **2026-09-28 between 12:05 and 12:28 UTC (≈ 08:05–08:28 ET, premarket)**; AAPL ends 2026-09-25 23:55 UTC |
| Pre-day-trading exposure | swing-bot phase: `*_1d.parquet` 2016-09-06 → 2026-09-03; `alpaca_*_4h.parquet` 2026-06-26 → 2026-08-25 |

**Consequence:** the development information set reaches into the **premarket of 2026-09-28**. Every valid OOS session must therefore be a session that starts after that point. Session 2026-09-28 itself is partly known (its premarket), so it cannot be OOS.

**Why moving the research window backward does not help:**
- Relabelling an earlier period as "research" does not erase what the researcher has already seen. The information set is fixed by what was seen, not by the label.
- If the new research window is moved backward to some boundary B < 2026-07-02, the new OOS (after B) falls into one of two cases:
  - **inside 2026-07-02 → 09-25:** this is the most-inspected data in the project. Every variant was built and compared on it;
  - **before 2026-07-02:** the strategy was developed with later information. This is the same defect as §1.
- No historical boundary B gives an OOS that is both after the development information and already complete, except sessions after 2026-09-28's premarket.

## 3. Candidate timelines

All dates are resolved with `exchange_calendars` 4.13.2, XNYS (VERIFIED, local, no network).

| # | Timeline | Status |
|---|---|---|
| T1 | Research moved backward (e.g. 2026-04 → 06), OOS = the following 60 sessions (≈ 2026-07 → 09) | REJECTED |
| T2 | Research moved backward, OOS = 60 sessions before 2026-07-02 | REJECTED |
| T3 | Previous DAY-15D: research 07-02 → 09-25, embargo 06-03 → 07-01, OOS 03-09 → 06-02 | REJECTED |
| T4 | Latest 60 completed sessions: 2026-07-13 → 2026-10-05 | REJECTED |
| T5 | v1.0: research 07-02 → 09-25, OOS = first 60 sessions after 09-25: 2026-09-28 → 2026-12-21 | VALID, not complete until 2026-12-21 |
| T6 | Research 07-02 → 09-25; embargo 09-28; **OOS stage 1 = 2026-09-29 → 2026-10-26 (20 sessions)**; stage 2 = 2026-10-27 → 2026-12-22 (40 sessions) | **RECOMMENDED** |
| T7 | OOS = the sessions completed after the embargo as of today: 2026-09-29 → 2026-10-05 (5 sessions) | REJECTED |

**The seven questions per timeline:**

| Question | T1 | T2 | T3 | T4 | T5 | T6 | T7 |
|---|---|---|---|---|---|---|---|
| 1. Boundary definable before seeing OOS results? | no — the OOS was already inspected | yes (calendar) | yes (calendar) | no — overlaps the inspected data | yes (DAY-14, before acquisition) | yes — fixed now from the calendar and the cache cutoff; no OOS value read | yes, but N = "whatever exists today" depends on today's date |
| 2. Research strictly before OOS (in information terms)? | **no** | **no** | **no** | **no** (54 sessions overlap) | yes, except the 09-28 premarket | **yes** (09-28 embargoed) | yes |
| 3. OOS already complete today? | yes | yes | yes | yes | **no** (6/60) | stage 1 **no**: complete 2026-10-26 16:15 ET (15 sessions away); stage 2 on 2026-12-22 | yes |
| 4. Fixed embargo? | arbitrary | arbitrary | 20 | none | none | **1 session, data-derived** | 1 session |
| 5. Sufficient warmup? | yes | yes | yes | yes | yes (research bars) | yes (research bars, continuous) | yes |
| 6. One provider for research and OOS? | Alpaca/Massive | Alpaca/Massive | Alpaca/Massive | Alpaca/Massive | yfinance (cache + captures) or Alpaca/Massive | **yes, Alpaca SIP** | yes |
| 7. Research re-run needed? | full new research | full new research | baseline re-run | n/a | no (yfinance) / baseline re-run (Alpaca) | baseline re-run on SIP | baseline re-run |

**Answer to the critical question** ("the latest historical OOS that can be completed today with research strictly before it"):
- It is the set of sessions after 2026-09-28, which is **2026-09-29 → 2026-10-05, 5 sessions**.
- No chronologically valid 60-session OOS exists today, and none can exist before 2026-12-22 (with the embargo) or 2026-12-21 (T5).
- The fastest valid design with a meaningful N is T6 stage 1, complete on **2026-10-26**.

**Why T7 is rejected:**
- 5 sessions is about one trading week.
- Its length is "whatever exists on the day we decided", so a different decision day gives a different N.

## 4. Minimum research data requirements (from code and protocol)

| Requirement | Value | Source | Label |
|---|---|---|---|
| RSI(14) on 5m | evaluation starts at 5m bar index 14 | research-protocol §1 (data-expansion-spec §1 warmup) | VERIFIED |
| RVOL | same time-of-day over prior ≤ 20 sessions, `min_sessions=1` | `strategy/day/vwap_momentum.py:122` | VERIFIED |
| 15m structure | swings with `lookback=2`; ≥ 5 closed 15m bars for index context | `vwap_momentum.py:205`, DAY-08 | VERIFIED |
| Research-window length | **not required by the protocol.** DAY-14 fixes 60 only for OOS ("equals the research-window length"); 60 for research came from the yfinance 60-day download | data-expansion-spec §3; research-protocol §1 | VERIFIED |
| Technical minimum | 20 warmup sessions + ≥ 1 research session | derived from the rows above | INFERRED |

**Why the minimum does not matter here:** the research window cannot be moved or shortened in information terms (§2). What the researcher saw is what defines it. The minimum only sets the warmup requirement for the re-baseline.

## 5. Warmup requirements

- **Research re-baseline warmup (new):** the 20 XNYS sessions before 2026-07-02, i.e. **2026-06-03 → 2026-07-01**. Indicator history only; no trades.
  - The original yfinance research had no warmup; RVOL baselines were thin in its first sessions (research-protocol §15 Q5).
  - Adding warmup means the re-baseline is a new research run, not a replication (§13).
- **OOS warmup:** the research bars and the embargo session (2026-07-02 → 2026-09-28), from the **same provider**, concatenated in one continuous series. Indicator history only.
  - Trades are counted only for signals whose signal bar lies inside an OOS session (data-expansion-spec §1 rule, unchanged).
- Warmup sessions are earlier than the OOS. They add no chronology problem.

## 6. Provider feasibility (no bars requested)

Requirement: one provider for 2026-06-03 → 2026-12-22 (warmup, research, embargo, OOS); 5m + 15m, 25 symbols, RTH, explicit start/end. References [Y1], [A1]–[A4], [M1], [M2] are listed in `day15c-provider-audit.md` §8 (accessed 2026-10-05; not re-fetched).

| Requirement | yfinance | Alpaca Market Data v2, `feed=sip` | Massive (formerly Polygon) |
|---|---|---|---|
| Depth to 2026-06-03 **today** | **no**: intraday "cannot extend last 60 days" (VERIFIED [Y1]). The research exists only in the frozen `data/cache` and cannot be re-downloaded. | yes, history since 2016 (VERIFIED [A1]) | yes, Basic 2 years (VERIFIED [M2]) |
| OOS 2026-09-29 → 12-22 | only by incremental captures within ~60 days (VERIFIED, DAY-15B) | one pass after each stage completes (INFERRED [A2]) | one pass (INFERRED [M1]) |
| 5m / 15m | native (VERIFIED [Y1]) | `5Min` / `15Min` (VERIFIED [A2]) | 5 / 15 minute (VERIFIED [M1]) |
| 25 symbols | yes (VERIFIED, snapshot #1) | all 25 assets active (VERIFIED, DAY-15C metadata call) | "all US stocks" (VERIFIED [M2]); per symbol NOT VERIFIED |
| RTH | server-side `prepost=False` | client-side filter (INFERRED [A2]); `data/session.py::filter_rth` exists | client-side (INFERRED [M1]) |
| Volume source | undocumented (NOT VERIFIED) | consolidated SIP, trade-condition filtered (VERIFIED [A3]/[A4]) | consolidated, qualifying trades (VERIFIED [M1]) |
| Timestamps | bar open (VERIFIED, DAY-08B) | bar start, UTC (VERIFIED [A2]/[A3]) | window start, epoch ms (VERIFIED [M1]) |
| Adjustment | research cache `auto_adjust=True`; v1.0 OOS captures `auto_adjust=False` (VERIFIED) | `adjustment` raw/split/dividend/all, default raw (VERIFIED [A2]) | `adjusted` default true (VERIFIED [M1]) |
| Deterministic start/end | yes, end exclusive (VERIFIED) | yes (VERIFIED [A2]) | yes (VERIFIED [M1]) |
| Reproducibility | no: data expires; unofficial source | settled history expected stable (INFERRED); late-trade recalculation (INFERRED [A3]); finality NOT VERIFIED | expected stable with `adjusted=false` (INFERRED) |
| Access here | keyless | paper key authenticates (VERIFIED); **SIP historical-bar entitlement NOT VERIFIED** | no account or key |
| Limits | throttling undocumented | Basic: SIP history except latest 15 minutes; 200 calls/min (VERIFIED [A1]) | Basic: 5 calls/min, EOD (VERIFIED [M2]) |

## 7. Provider consistency analysis

**Rule:** one provider, one feed, one adjustment mode, one RTH filter, for warmup + research + OOS. They are frozen in v1.1 before any bar is read.

| Option | Assessment |
|---|---|
| yfinance research (existing cache) → yfinance OOS (v1.0 captures) | Feasible, and needs no re-run. **Not recommended:** <br>• the research data cannot be re-acquired, so the pipeline is not reproducible end to end; <br>• the research cache used `auto_adjust=True` while OOS captures use `auto_adjust=False`, which is not one configuration; <br>• the volume source is undocumented; <br>• the source is unofficial. |
| **Alpaca SIP research → Alpaca SIP OOS** | **RECOMMENDED.** Full depth, documented construction, existing key, one configuration end to end. Requires a research re-baseline (§13). |
| Massive research → Massive OOS | Valid **runner-up**. Needs a new account and key; Basic tier rate limit. No methodological advantage. |
| yfinance research → Alpaca/Massive OOS (mixed) | **REJECTED:** provider confound (below). |

**Why mixing providers confounds the test:**

| Dimension | Effect |
|---|---|
| Volume | Different sources → different RVOL (the CONFIRMED gate at RVOL ≥ 2.0) and different VWAP weights. |
| Trade-condition filtering | SIP providers filter conditions separately for OHLC and for volume (VERIFIED [A3]). Highs and lows can differ, which moves SIGNAL_LOW stops, target touches and same-bar ambiguity. |
| Empty intervals | No bar without qualifying trades (VERIFIED [M1], INFERRED [A4]) → missing-bar counts, RSI bar indexing. |
| VWAP | Computed from bar high/low/close and volume (`indicators/vwap.py::compute_vwap`). It inherits every OHLC and volume difference. |
| Timestamps | All three are start-labelled (VERIFIED). Compatible once stored as UTC bar open. |
| Adjustment | Intraday returns are scale-invariant; RVOL across a split is not. One mode must be fixed (§16, Q1). |

The provider is chosen on reproducibility, access and data construction. No provider's data has been looked at or compared.

## 8. Recommended timeline — **RECOMMENDED** (proposed v1.1, user-selected path)

```
 research warmup      research (frozen information set)     embargo   OOS stage 1 (primary)    OOS stage 2 (confirmation)
 2026-06-03..07-01 |  2026-07-02 .. 2026-09-25 (60)      |  09-28  |  09-29 .. 10-26 (20)   |  10-27 .. 12-22 (40)
 (20, no trades)      exploratory; re-baselined on SIP     (1)       complete 10-26 16:15 ET    complete 12-22 16:15 ET
                      ←──────────── one provider: Alpaca Market Data v2, feed=sip ────────────────────────────→
```

**Decision rule** (proposed, to be frozen verbatim in v1.1, before any OOS bar is read):
1. The primary metric is unchanged: mean net trade return at 5 bps per side (research-protocol §13).
2. **Stage 1** is evaluated once, after 2026-10-26 16:15 ET.
   - If the primary metric is < 0, the candidate is **REJECTED**. This is final.
   - Stage 2 is still acquired and reported, but it can never reverse a stage-1 rejection.
3. **Stage 2** is evaluated once, after 2026-12-22 16:15 ET.
   - **ACCEPT** requires both stage 1 ≥ 0 **and** stage 2 ≥ 0. Every other PREDEFINED hard requirement must also pass (data integrity, PIT test, reproducibility).
4. Stage 1, stage 2 and the combined 60 sessions are all reported with every research-protocol §12 metric. None is chosen after the fact.
5. Nothing is tuned between stages.

**Why N = 20 for stage 1 (performance-blind):**
- It was fixed on 2026-10-06 for a calendar reason: the result arrives in about 3 weeks instead of 11.
- It equals the DAY-14 snapshot interval (data-expansion-spec §4) and the RVOL lookback.
- No OOS value was read to choose it.

**Stated costs of this choice (INFERRED):**
- 20 sessions is about one month and one market regime, so statistical power is lower than with 60.
- Stage 2 exists to cover that.

**The OOS gate is still NO.**
- DAY-13: no in-sample variant is non-negative after 5 bps costs.
- This timeline removes the *data* bottleneck. It does not create a candidate.
- If the SIP re-baseline also yields no qualifying candidate, no OOS run takes place (§16).

## 9. Exact research dates

| Segment | Sessions | First | Last | Holidays skipped |
|---|---|---|---|---|
| Research warmup | 20 | 2026-06-03 | 2026-07-01 | 2026-06-19 |
| Research | 60 | 2026-07-02 | 2026-09-25 | 2026-07-03, 2026-09-07 |

Rule: research = the existing window (VERIFIED, DAY-14 §1). Warmup = the 20 XNYS sessions immediately before 2026-07-02.

## 10. Exact embargo dates

| Segment | Sessions | Date | Reason |
|---|---|---|---|
| Embargo | 1 | **2026-09-28** | Its premarket (until ≈ 08:28 ET) is in the research cache for 24 of 25 symbols (VERIFIED, §2). The session is partly inside the information set. |

**Why not longer (INFERRED from code):**
- All features are backward-looking (PIT contract, research-protocol §3).
- No position is held overnight, so no trade label spans the boundary.
- No information from after the cutoff enters the research set.
- A longer embargo would only discard sessions.

The length is fixed by the cache evidence, not chosen.

## 11. Exact OOS dates

| Segment | Sessions | First | Last | Complete after | Notes |
|---|---|---|---|---|---|
| **OOS stage 1 (primary)** | **20** | **2026-09-29** | **2026-10-26** | 2026-10-26 16:15 ET | no holidays; no early close |
| OOS stage 2 (confirmation) | 40 | 2026-10-27 | 2026-12-22 | 2026-12-22 16:15 ET | skips 2026-11-26; early close **2026-11-27** (42 × 5m / 14 × 15m); first session after the DST change: **2026-11-02** |

**Rule (authoritative; the dates are its resolution):**
- `S` = XNYS sessions (`exchange_calendars` 4.13.2).
- `P` = sessions of `S` strictly after 2026-09-25.
- Embargo = `P[0]`.
- Stage 1 = `P[1:21]`.
- Stage 2 = `P[21:61]`.

If the pinned calendar disagrees at acquisition time (for example, an unscheduled closure), the rule governs and acquisition stops for review.

## 12. Required protocol version

**v1.1.**
- v1.0 documents are not edited. v1.1 is written as new files and committed before any v1.1 bar is read.
- Results stay attributed to their version.

| v1.0 location | v1.0 content | v1.1 replacement |
|---|---|---|
| `data-expansion-spec.md` §1, line 24 | provider = yfinance only | Alpaca SIP, fixed config, for warmup + research + OOS |
| `data-expansion-spec.md` §1 warmup policy | research bars as OOS warmup (yfinance cache) | same principle, on the SIP series; plus a 20-session research warmup |
| `data-expansion-spec.md` §2 roles | research / no validation / OOS 60 | research (re-baselined) / embargo / OOS stage 1 (20) / OOS stage 2 (40) |
| `data-expansion-spec.md` §3 | first 60 after 09-25, no embargo | §11 rule with a 1-session embargo |
| `data-expansion-spec.md` §3, line 55 | no backfill from another provider | n/a: a single provider from the start |
| `data-expansion-spec.md` §4 | yfinance incremental snapshots, `protocol_v1.0/` | one pass per stage, `data/oos_cache/protocol_v1.1/` |
| `oos-protocol-template.md` §5, §7 | OOS rule; acceptance table | §11 rule; the staged decision rule in §8 |
| `research-protocol.md` §1 | yfinance baseline | adds the SIP re-baselined research as the v1.1 reference |

**v1.0 status:**
- The v1.0 yfinance captures (`protocol_v1.0/`) continue under their own rules, untouched, as an independent cross-check.
- They are never merged into v1.1.

## 13. Required re-run scope

| Item | Required? | Classification |
|---|---|---|
| Acquire SIP warmup + research (2026-06-03 → 2026-09-25) | yes | new data, research period |
| Structural checks on it (data-expansion-spec §5) | yes | — |
| **Frozen DAY-04 baseline** re-run on SIP research | **yes, mandatory** | new research run, family F-BASE, PREDECLARED, variant count +1 |
| Candidate(s) for OOS | must be named in a committed candidate protocol **before** the SIP re-baseline results are viewed | provenance per research-protocol §10 |
| DAY-05 → DAY-12B families on SIP data | optional; not required for the OOS | new exploration in the existing families; DERIVED FROM PRIOR OBSERVATION; counts added to each family; cannot select a candidate after the fact without a new protocol |
| yfinance DAY-04 → DAY-13 results | not re-run | historical exploratory evidence (§14) |

**Candidate rule (from research-protocol §11, unchanged):** a candidate enters OOS only if its SIP research result is non-negative at 5 bps per side. That result is computed after the candidate is named. **If no candidate qualifies, there is no OOS run.**

## 14. What remains frozen from the old research

- Universe: the 25 symbols (`config/day_universe.py`).
- Signal logic and thresholds (`strategy/day/vwap_momentum.py`), the valid status set {DETECTED, CONFIRMED}.
- Execution semantics (research-protocol §8): T+1 open entry, SIGNAL_LOW / VWAP / 0.99 stop, 2R target, STOP_FIRST, 15:55 forced exit, one position per symbol, long-only.
- Cost contract (0 / 5 / 10 bps per side, formula), metrics (§12), benchmark, acceptance framework (§13), PIT contract (§3), structural checks, hash manifests, write-once storage.
- Calendar: `exchange_calendars` 4.13.2, XNYS.
- **DAY-04 → DAY-13 artifacts and results:**
  - kept unchanged as **historical exploratory evidence** under v1.0 / yfinance;
  - they are not mixed with v1.1 numbers, not averaged with them, and not used as the in-sample reference for the v1.1 OOS;
  - their information content is exactly what defines the cutoff in §2.

## 15. What becomes new research

- Protocol v1.1 and its staged OOS design.
- The SIP data series 2026-06-03 → 2026-12-22 (in stages).
- The 20-session research warmup, which the yfinance research lacked.
- The SIP re-baselined research result. It will differ from the yfinance baseline (5,691 trades, PF 0.9388). The difference is reported as a provider/warmup effect, never tuned away.
- Any variant evaluated on SIP research data (§13).
- The 1-session embargo.

## 16. What must happen before any OOS bar is read

In order; each code step is a separate, reviewed change:

1. **Freeze v1.1:**
   - provider config: `feed=sip`, the adjustment mode, the RTH filter;
   - the §11 rule and the §8 decision rule;
   - commit the v1.1 documents and record their SHA-256.
2. **Pin the calendar:** a test that resolves §9–§11 twice and asserts the exact dates.
3. **Entitlement probe:** one Alpaca SIP historical 5m request on **one research date** (2026-07-02 → 09-25), recording only the HTTP status and error text. Never an embargo or OOS date.
4. **New acquisition adapter** for Alpaca SIP:
   - explicit start/end, pagination;
   - writes only to `data/oos_cache/protocol_v1.1/`, write-once and hashed;
   - must not reuse `data/alpaca_provider.py`, which hard-codes IEX and writes to `data/cache/` (DAY-15C §4);
   - preflight hash checks as in DAY-15A.
5. **Acquire warmup + research** (2026-06-03 → 2026-09-25 only); run the structural checks.
6. **Commit the candidate protocol** (from `oos-protocol-template.md`, adapted to v1.1), naming the candidate(s) and the frozen config.
7. **Re-baseline the research** on SIP; report it in full.
8. **Gate (research-protocol §11)** on the SIP research result.
   - If NO, stop. No OOS bar is acquired.
9. **After 2026-10-26 16:15 ET:** acquire the embargo + stage 1 (2026-09-28 → 10-26); structural checks only; then a single stage-1 run.
10. **After 2026-12-22 16:15 ET:** acquire stage 2; structural checks; a single stage-2 run; final report.

**Must NOT happen:**
- Moving, shortening or extending any window, or changing N, the embargo or the decision rule, after v1.1 is committed.
- Reading any bar dated 2026-09-28 or later from any provider before step 9. This includes summary statistics or charts.
- Using the yfinance research as the in-sample reference for a SIP OOS.
- Mixing v1.0 captures into v1.1.
- Selecting a candidate after viewing SIP research results without a new protocol.
- Writing to `data/cache/`; modifying `data/oos_cache/protocol_v1.0/`; editing DAY-04 → DAY-15C artifacts.
- Re-running an OOS stage, except a documented technical failure re-run with the identical config.

**Open questions:**

| # | Question | Blocks? | Status |
|---|---|---|---|
| Q1 | Adjustment mode for SIP (`raw` vs `split`). Can be settled from corporate-action metadata for 2026-06-03 → 12-22 (not bar data). | step 1 | OPEN |
| Q2 | Does the paper key have SIP historical-bar entitlement? | step 3 | NOT VERIFIED |
| Q3 | Finality of Alpaca historical bars (late-trade recalculation); capture timing buffer beyond 16:15 ET | no (DISCREPANCY mechanism) | NOT VERIFIED |
| Q4 | Confirm the staged decision rule in §8 verbatim, or amend it, before the v1.1 commit | step 1 | OPEN (user) |
| Q5 | Statistical power of a 20-session stage 1. No minimum-trade threshold is predefined (research-protocol §13). | no; disclose | OPEN |
| Q6 | Universe selection date is UNKNOWN (inherited, research-protocol §1). Present-day survivorship is not fixed by any timeline. | no; disclose | OPEN |

## Final decision

- **Retracted:** the earlier pre-sample OOS (T3) and any backward-moved research (T1, T2).
  - The development information set ends at the premarket of 2026-09-28.
  - Relabelling windows cannot move that point.
- **No valid 60-session historical OOS exists today.** Only 5 post-cutoff sessions are complete.
- **Recommended (v1.1, user-selected path):**
  - research **2026-07-02 → 2026-09-25** (warmup 2026-06-03 → 07-01);
  - embargo **2026-09-28**;
  - **OOS stage 1 = 2026-09-29 → 2026-10-26 (20 sessions, primary)**;
  - OOS stage 2 = 2026-10-27 → 2026-12-22 (40 sessions, confirmation);
  - all on **Alpaca Market Data v2, SIP feed**, with a mandatory SIP research re-baseline.
- **Earliest valid OOS result:** after 2026-10-26 16:15 ET. This assumes a candidate passes the gate on the SIP research; today the gate is NO.
