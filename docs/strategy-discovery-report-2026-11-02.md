# Strategy discovery report: 2026-11-02

> **Status: DISCOVERY / DESIGN ONLY.** No data was acquired, no API was called, no backtest or optimization was run,
> and no strategy code was written or changed. Stage R, Stage H, `fwd-gate2`, sealed P001, `paper_state/` and
> forward-test artifacts were not opened. Nothing here is an owner decision.
> **No candidate in this report is claimed to be profitable.**

**Labels:**
- **FACT**: read directly from the cited repository file.
- **OBS**: an observation across several files.
- **HYP**: a hypothesis about markets, to be tested.
- **INF**: an inference drawn from facts.
- **REC**: a recommendation to the owner.
- **LIT [UNVERIFIED]**: a claim from the academic literature, from prior knowledge only. Not verified against the
  source in this task and not repository evidence.

Mechanism strength uses four grades: **ESTABLISHED** (documented, widely replicated mechanism), **PLAUSIBLE**,
**UNVERIFIED ASSUMPTION**, **SPECULATION**.

---

## 1. Executive summary

- **OBS:** every day-trading family the project has tested (DAY-01 VWAP and its 40 variants, ORB) shows no edge
  after costs on the only intraday window examined. Every live day-trading use is also blocked by the unresolved
  Sharia question D12.
- **OBS:** on the swing side, the 25-symbol universe has no untouched historical segment. The momentum family
  (V2-MOM) is under forward lockdown, reversal (V2-STR) and pairs (V2-LRV) are stopped, and the legacy
  breakout/exit research found no edge.
- **REC, swing track (1 candidate):** **SW-A, earnings-reaction drift** (price-based post-earnings-announcement
  drift).
  - It is the only candidate with all four properties: an established, information-based mechanism; no overlap
    with any tested family's mechanism; low turnover; and a point-in-time data method that already exists in the
    repository (SEC 8-K Item 2.02 acceptance timestamps, `config/earnings_calendar_sources.csv`).
  - Main risk: the effect may have decayed in mega caps (LIT [UNVERIFIED]). The test is designed to falsify it.
- **REC, day track (0 unconditional, 1 conditional):** **DT-A, market intraday momentum** on a broad index ETF.
  - It is mechanistically distinct and has a documented literature basis.
  - It is **BLOCKED_FOR_LIVE_USE** on two independent counts: D12 (day trading) and instrument eligibility (SPY
    is not Sharia-screened; a compliant ETF's intraday liquidity and spread are unverified).
  - Recommended only if the owner wants a research-only day track before D12 is ruled. Otherwise the honest day
    recommendation is **research nothing until D12 is ruled.**
- **No second candidate in either track is justified.** Two others were close (SW-B earnings-announcement premium
  and SW-F index trend timing). They are rejected for now and §11 says why.
- All data-dependent stages remain blocked by the research hold (owner memo, OPEN-G2).
- **Operational note:** creating this report adds a second untracked file, so OPS-1 now covers two files (§13).

---

## 2. Existing strategy family inventory

A parameter or indicator change on the same economic mechanism counts as the same family.

| Family | Mechanism | Previously tested? | Result (FACT) | Known weakness | Can be reconsidered? |
|---|---|---|---|---|---|
| **F1 Intraday VWAP momentum / reclaim** (DAY-01..12B, DAY-15H; D1) | intraday trend continuation around VWAP | Yes: 40 variant rows on 60 sessions (`artifacts/day13/research-synthesis.md:95`) | DAY-13 OOS gate NO; **DAY-15H research gate FAIL**: avg R −0.132, PF 0.944 (`day15h-alpaca-rebaseline.md:3,73-80`). Best mean gross trade +0.0288% against a ≈0.10% round trip (`research-synthesis.md:113-115`) | edge below costs; tight stops; 50% single-bar trades | **No.** D1 rejected as a derived variant (owner memo 2026-11-02) |
| F1a Stock-in-play gap filter (DAY-06/06A) | gap as a proxy for interest | Yes, as a filter on F1 | not cost-robust; premarket RVOL untestable (`research-synthesis.md:56-57`) | trades collapse 2,010 → 210 | Only inside a new mechanism with a broad universe (DT-D, rejected) |
| F1b Index-regime filter (DAY-08/08B) | market context | Yes, on F1 | NOT VALIDATED | removes trades, not per-trade quality | No |
| F1c Time-window, frequency-cap, breakeven, ATR stop (DAY-07..12B) | exit and entry mechanics | Yes | none cost-robust | in-sample, MIXED provenance | No |
| **F2 ORB** | opening-range breakout continuation | Yes: smoke test and diagnostics on the same 60 sessions | SIP 101 trades, net −1.54%, total R −6.22, exits STOP 13 / TARGET 0 / FORCE 88; "not evidence of an edge"; **"Ready for the next ORB test: no"** (`docs/strategy-evidence-inventory-2026-10-17.md` §4) | same window as F1; small n; earnings sessions excluded | Only as a pre-registered **re-test** on non-overlapping data. Not a new hypothesis |
| **F3 V2-MOM** (12-1 cross-sectional momentum) | underreaction / momentum | Yes: research, holdout, forward | RESEARCH-PASSED · HOLDOUT-PASSED; `fwd-gate2` PENDING | p 0.166; concentrated | **No.** Locked; no variants (`day22 …:140-157`) |
| **F4 V2-STR** (5-day reversal, long-only) | short-horizon reversal | Yes | HOLDOUT-FAILED → STOPPED, no rescue | cost drag 5.04 pp | **No** |
| **F5 V2-LRV** (long-only pairs) | relative-value convergence | Yes | RESEARCH-FAILED → STOPPED | — | **No** |
| **F6 Legacy daily breakout/retest + EMA trend + SMC zones + six exit models** | breakout continuation / structure | Yes, without a protocol (`reports/run_log.txt`) | "NO SELECTION EDGE", "NO EXIT EDGE FOUND" | no protocol; untracked CSVs | No (same mechanism as consolidation breakout) |
| **F7 TOM-SPY** (turn-of-month timing) | calendar flows | Designed, not run | **OD-2 = REJECT** by the owner (`docs/strategy-candidate-selection-…:3`) | low power | No (owner decision) |
| F8 Low-volatility selection | low-vol anomaly | Screened | rejected: no credible test design on unused data (`…candidate-selection…` §3) | hindsight universe | No (same reasons) |
| F9 RSI(2) mean reversion | short-term reversal | Screened | rejected as a rename of F4 | — | No |
| **S1 Daily trend pullback** | trend filter + short-term pullback entry | No (draft) | not run; Stage R use not approved | combines F3 (trend) and F4 (reversal) mechanisms on the same universe and period | Remains the owner's draft; not ranked above SW-A (§9) |

**Searched and NOT FOUND in the repository** (FACT, from `docs/strategy-candidate-selection-…:89-98`, re-checked
in this task):
- post-earnings drift (dates only, no surprise data);
- calendar effects other than TOM;
- intraday index timing;
- earnings-announcement premium;
- overnight / intraday return decomposition.

---

## 3. Day trading candidate analysis

Constraint common to all of them (FACT, `docs/shariah/AAOIFI_MVP_DECISIONS.md` D12): day trading permissibility
is **ADVISER_REQUIRED**. No live intraday order code may be added. Every day candidate is therefore
**BLOCKED_FOR_LIVE_USE** whatever its research result.

| ID | Candidate | Family check | Verdict |
|---|---|---|---|
| **DT-A** | **Market intraday momentum**: the early-session index return predicts the last-half-hour index return (long side only) | new: no index intraday timing anywhere in the repo | **Conditional shortlist** (§10) |
| DT-B | ORB continuation | F2 (same mechanism) | Re-test only, not new. Excluded from the shortlist |
| DT-C | Intraday momentum after a genuine news catalyst | new mechanism | **Hard reject: data.** No news or catalyst timestamps (§6) |
| DT-D | Gap-and-go in stocks-in-play, broad universe | overlaps F1a | **Hard reject: data.** Needs a point-in-time broad universe and premarket volume |
| DT-E | Intraday volatility compression → expansion | — | **Hard reject:** no mechanism beyond "price moves after indicator X" |
| DT-F | Intraday relative strength / leadership vs SPY | close to F1b | Reject: no specific economic mechanism; the "leaders keep leading intraday" claim has no identified source of mispricing |
| DT-G | Earnings-day intraday continuation (on the reaction session, after the open) | new, partly overlaps F1a (gap days) | Not recommended: ≈4 events per symbol per year (≈100 per year on 25 symbols); low power; intraday costs; D12 |

---

## 4. Swing trading candidate analysis

| ID | Candidate | Family check | Verdict |
|---|---|---|---|
| **SW-A** | **Earnings-reaction drift**: after a positive, large, market-adjusted price reaction to a quarterly earnings release, prices continue to drift in the same direction for weeks | new (event-driven; information signal, not trend rank). Partial correlation with momentum (§9) | **Shortlist** (§10) |
| SW-B | Earnings-announcement premium: hold through scheduled announcements | new | Not recommended now: incompatible with the stop-based 0.5% sizing rule (§7) |
| SW-C | Medium-term momentum / cross-sectional relative strength / 52-week-high | F3 | **Hard reject:** same family as V2-MOM, locked |
| SW-D | Volatility contraction / consolidation breakout | F6 | **Hard reject:** failed legacy family; weak mechanism |
| SW-E | Pullback continuation (S1) | F3 + F4 | Not ranked above SW-A (§9); stays an owner draft |
| SW-F | Time-series trend timing of a broad (Sharia-screened) index ETF | new for the project | Not recommended now: low statistical power, no research independence (§11) |
| SW-G | Short-term reversal (any form) | F4 / F9 | **Hard reject:** STOPPED family |
| SW-H | Low-volatility selection | F8 | Reject (previous decision stands) |
| SW-I | Turn-of-month | F7 | Reject (owner OD-2) |
| SW-J | Overnight return premium (buy close, sell open) | new | **Hard reject: costs.** About 250 round trips a year on full capital (§7) |

---

## 5. Economic hypotheses (shortlisted and closest runners-up)

### DT-A: market intraday momentum (index ETF)

| # | Question | Answer |
|---|---|---|
| 1 | Inefficiency / mechanism | The direction of the index move in the first part of the session predicts the direction of the final half hour. LIT [UNVERIFIED]: Gao, Han, Li & Zhou (2018, *J. Financial Economics*, "Market intraday momentum"); Baltussen, Da, Lammers & Martens (2021, *JFE*, "Hedging demand and market intraday momentum") |
| 2 | Why it might exist | (a) late-informed traders and infrequent rebalancers trade near the close in the direction of the day's news; (b) dealers hedging options gamma trade with the trend late in the day; (c) end-of-day flows of leveraged and inverse ETFs rebalance in the direction of the daily return. All three are LIT [UNVERIFIED] |
| 3 | Who creates it | institutional rebalancers, options dealers, leveraged-ETF sponsors |
| 4 | Why it might persist | the flows are mechanical and driven by mandates, not by information, so they are hard to arbitrage away entirely |
| 5 | Why it might disappear | post-publication arbitrage; changes in dealer positioning (gamma sign flips); growth of closing-auction liquidity |
| 6 | Holding period | ≈ 30 minutes, flat by the close |
| 7 | Favourable regimes | high-volatility, news-heavy days (LIT [UNVERIFIED]) |
| 8 | Adverse regimes | quiet, range-bound days; days when dealers are long gamma (mean reversion) |
| 9 | Failure mode | the edge per trade is smaller than the round-trip cost; or it only works on the short side, which is not allowed |
| 10 | Why it might survive costs | one highly liquid instrument at most once a day. **Only** if the real cost is near the instrument's spread, not the project's 5 bps-per-side convention (§7) |
| — | Grade | **PLAUSIBLE** (published, with competing mechanisms; replication and post-publication persistence not verified here) |

### SW-A: earnings-reaction drift

| # | Question | Answer |
|---|---|---|
| 1 | Inefficiency / mechanism | Investors underreact to earnings information, so prices keep moving in the direction of the announcement reaction for weeks. LIT [UNVERIFIED]: Ball & Brown (1968); Bernard & Thomas (1989, 1990). A price-based version measures the news by the announcement-window return instead of an analyst surprise (Chan, Jegadeesh & Lakonishok 1996; Brandt et al. 2008) |
| 2 | Why it might exist | limited attention, anchoring on prior expectations, and slow incorporation of the implications of earnings for future earnings (LIT [UNVERIFIED]) |
| 3 | Who creates it | investors who underreact; constrained arbitrageurs |
| 4 | Why it might persist | attention limits are behavioural; the drift occurs over weeks, where arbitrage capital is costlier |
| 5 | Why it might disappear | decay after publication. LIT [UNVERIFIED]: several later studies (e.g. Martineau 2022, "Rest in peace post-earnings announcement drift") report that the drift has largely vanished, especially in large caps. **This is the central risk for a mega-cap universe** |
| 6 | Holding period | weeks (strictly shorter than the time to the next announcement) |
| 7 | Favourable regimes | high dispersion of earnings news; low-attention periods |
| 8 | Adverse regimes | sharp market reversals; crowded "beat-and-raise" trades |
| 9 | Failure mode | no drift after costs in mega caps; or the drift is fully explained by momentum exposure (overlap with V2-MOM) |
| 10 | Why it might survive costs | low turnover (at most four signals per symbol per year, only the positive tail traded); a multi-week holding period means a 0.10% round trip is small relative to the plausible move **if** the effect exists |
| — | Grade | **ESTABLISHED historically**; **persistence in current mega caps: UNVERIFIED ASSUMPTION** |

### SW-B and SW-F (close but not shortlisted)

- **SW-B (earnings-announcement premium):**
  - Mechanism: a risk premium for non-diversifiable announcement risk, or attention-driven buying before
    announcements. LIT [UNVERIFIED]: Frazzini & Lamont (2007); Savor & Wilson (2016).
  - Grade: PLAUSIBLE.
  - Rejected for now on risk-framework grounds (§7).
- **SW-F (time-series trend timing):**
  - Mechanism: slow diffusion of information and de-risking flows. LIT [UNVERIFIED]: Moskowitz, Ooi & Pedersen
    (2012).
  - Grade: ESTABLISHED as a risk-management effect.
  - Rejected for power and independence reasons (§11).

---

## 6. Data feasibility matrix

**Verified capabilities (FACT):**
- Alpaca SIP 5Min: `artifacts/day15/day15e-alpaca-access.md`.
- Alpaca SIP 15Min: `day15g-alpaca-15m-access.md`.
- Alpaca SIP 1Day, 26/26 symbols including SPY, history from 2016-01-04: `artifacts/day17/day17-data-blockers.md` §4.
- Corporate actions endpoint: `day17…` §5, used in Stage R.
- `data/alpaca_provider.py` is IEX, not SIP: `data/alpaca_provider.py:8-12`.

The endpoint probes covered **individual equities** (AAPL for 5Min/15Min) and SPY for 1Day only.

**Correction to the owner memo of 2026-11-02 (§7 there):** the earnings calendar **does** have a source file:
- `config/earnings_calendar_sources.csv` (26 rows) records, per event, the SEC 8-K accession, the `accepted_et`
  acceptance timestamp, an AMC/BMO timing class, a `timing_status` (23 VERIFIED, 1 UNVERIFIED, 1 NOT_EARNINGS,
  1 VERIFIED_NO_EARNINGS_IN_WINDOW), and the EDGAR index and exhibit URLs.
- It was committed in `eb87c88`.
- Coverage is still only 2026-07-02 → 2026-09-25.
- The rows also document real edge cases:
  - a TSLA Item 2.02 filing that was a deliveries report, excluded by owner decision;
  - an XOM CIK change;
  - an issuer with no Item 2.02 filing in the window;
  - an acceptance time that does not state the release time ("IR confirmation pending").

Statuses: **AV** = AVAILABLE_AND_VERIFIED, **ANV** = AVAILABLE_BUT_NOT_VERIFIED, **NA** = NOT_AVAILABLE,
**NP** = REQUIRES_NEW_PROVIDER (or new source integration), **NR** = NOT_REQUIRED.

| Requirement | DT-A | SW-A | SW-B | SW-F | S1 (ref.) | Evidence / note |
|---|---|---|---|---|---|---|
| Daily OHLCV, equities (SIP) | NR | **AV** | AV | NR | AV | day17 probe; acquisition not authorized (hold) |
| Daily OHLCV, SPY | ANV-for-use (AV endpoint) | **AV** (benchmark) | AV | AV | AV | Stage R had SPY 1Day; Stage R itself is off-limits, so a fresh acquisition is needed |
| Daily OHLCV, Sharia-screened ETF (e.g. SPUS, HLAL) | NR | NR | NR | **ANV** | NR | never probed; inception dates and liquidity not verified |
| 5m OHLCV, equities | NR | optional (reaction timing) | NR | NR | NR | day15e |
| 5m OHLCV, SPY / index ETF | **ANV** | NR | NR | NR | NR | the 5Min probe was AAPL only |
| Intraday volume / RVOL baselines | derivable from bars | NR | NR | NR | NR | — |
| Market benchmark | the instrument itself | SPY daily (AV endpoint) | same | — | same | — |
| Point-in-time universe | NR (single instrument) | **NA** | NA | NR | NA | `day16 …:79-80`: universe not PIT, hindsight-selected |
| Corporate actions | NR (intraday, ETF) | **AV** | AV | AV (ETF distributions) | AV | Alpaca `/v1/corporate-actions` used in Stage R |
| Earnings timestamps (PIT) | NR | **NP** (method exists; history missing) | NP | NR | NP (S4) | `config/earnings_calendar_sources.csv` (2026-07..09 only); EDGAR access terms [UNVERIFIED] (`docs/shariah/AAOIFI_DATA_PROVIDER_ASSESSMENT.md:41-45`) |
| News / catalyst timestamps | NR | NR | NR | NR | NR | NA anywhere (relevant only to DT-C) |
| Sector classification | NR | optional | optional | NR | optional | SIC via EDGAR `submissions` [UNVERIFIED] → NP |
| Bid/ask spread | **NA** (critical for the cost model) | NA (minor) | NA | NA (minor) | NA | no quote data or quote endpoint verified in the repo |
| Trade-level data | NA (not required) | NR | NR | NR | NR | bars are trade-based (day15c [A3]); trades endpoint not used |
| Closing-auction prints | ANV | NR | NR | NR | NR | the 1Day close is the last eligible trade, not necessarily the auction (`day17 …:76`) |
| Untouched data period | SPY intraday never examined; dates ≥ 2026-10-08 blocked by the hold | event-level reactions never computed; any period overlapping Stage H dates needs a **fresh** snapshot and an owner decision | same | SPY history well known; SPY is `fwd-gate2`'s B2 | Stage R only by owner permission | — |

**INF:** SW-A's critical path is a historical EDGAR 8-K Item 2.02 earnings calendar built with the method already
used in `config/earnings_calendar_sources.csv`. DT-A's critical path is a credible cost estimate, which needs spread
data the project does not have.

---

## 7. Execution and cost analysis

The project convention is 5 bps per side as the primary friction and 10 bps as stress, with no spread model
(`artifacts/day16/research-protocol-v2.md` §9). No profitability number is assigned below.

| Factor | DT-A | SW-A | SW-B | SW-F | SW-J (rejected) |
|---|---|---|---|---|---|
| Expected turnover | ≤ 1 round trip per session; long-only roughly halves that (INF) | ≤ 4 signals per symbol per year; only the positive tail is traded | 4 per symbol per year | a few switches per year | ≈ 250 round trips per year on full capital |
| Trades per year (25 symbols / 1 ETF) | up to ≈ 125 (INF) | ≈ 100 events, of which a fraction trade (INF): **low n** | ≈ 100 | single digits | ≈ 250 |
| Spread sensitivity | **critical**: per-trade gross moves are intraday-sized | low | low | very low | **critical** |
| Slippage | MOC or a limit order near the close; the auction print is not in the data | open fill (daily); the open is not necessarily the auction print (Q6 precedent) | same | same | — |
| Liquidity / capacity | SPY: very deep. A compliant ETF: **unverified**, probably much thinner | mega caps: deep | deep | ETF-dependent | — |
| Gap risk | none (flat at close) | overnight, multi-week; earnings excluded by construction (exit before the next announcement) | **by design**: it holds through the earnings gap | overnight | by design |
| Stop execution uncertainty | intraday stop on 5m bars; STOP_FIRST | daily bars; gap-through fills at the open | a stop cannot bound the announcement gap | — | — |
| Compatibility with `floor(0.005·Capital/(E−S))` | yes, but a tight stop means a large notional (cash-capped) | yes | **no**: realized loss on a gap can be a large multiple of 1R, so stop-based sizing understates risk | needs a stop definition | — |
| Market impact | negligible at research size | negligible | negligible | negligible | — |
| **Cost verdict** | **UNRESOLVED**: at the 5 bps convention (10 bps round trip) an intraday index edge is unlikely to clear costs (INF); at true SPY spreads it might. Needs a quote-based cost model before any claim | **PASS (plausibly)** if the drift exists | PASS on costs, **FAIL on the risk framework** | PASS | **FAIL**: hard reject |

---

## 8. Sharia feasibility

Project rules (FACT, `docs/shariah/AAOIFI_MVP_DECISIONS.md`, `AKINDA_PROVIDER_DECISION.md`):
- long-only, cash account, no margin, no shorting, no derivatives (D15 PROVISIONAL);
- stock screening by Akinda `/compliance` (D13-A), fail-closed; the registry is currently header-only, so no
  ticker is tradable;
- Akinda Basic quota is 10 requests a day;
- ETF or index membership is never evidence (D13).

| Candidate | Technical feasibility (long-only, cash) | Screening feasibility | Adviser questions | Live status |
|---|---|---|---|---|
| DT-A | yes | **SPY is not a compliant instrument** (it holds conventional banks and others). A Sharia-screened ETF's eligibility as an **instrument** is undecided (D13 covers stocks; ETF eligibility is not settled). Akinda covers tickers; ETF coverage NOT VERIFIED | D12 (day trading, qabd/daman under T+1); D11 (intraday purification) | **BLOCKED_FOR_LIVE_USE** (D12 and instrument eligibility) |
| SW-A | yes | per-stock Akinda screening needed; historical (point-in-time) screening is impossible, so research results are unscreened | D10 (purification of dividends received while holding); D2 multi-day exit logic must exist before live use | Live needs screening rows, D2 exit logic, a D15 broker checklist and a D10 ruling for dividends → **BLOCKED_FOR_LIVE_USE until those exist** (not blocked for research) |
| SW-B | yes | same as SW-A | same | same |
| SW-F | yes | instrument eligibility of the ETF undecided | D10 for ETF distributions | BLOCKED_FOR_LIVE_USE (instrument) |
| S1 | yes | as SW-A | as SW-A | as SW-A |

**Settlement (INF, NOT VERIFIED; broker confirmation required):** in a cash account, US T+1 settlement can create
good-faith violations if unsettled proceeds are reused and sold before settlement. DT-A uses capital every day, so
it needs this checked with the broker. Swing candidates are less affected.

No candidate is labelled halal by this report.

---

## 9. Candidate scoring

Scale 1–5, where 5 = best for the project:
- Cost sensitivity: 5 = least sensitive.
- Operational complexity: 5 = simplest.
- Sharia feasibility: 5 = no open question.

**The "Blocker" column overrides the total.**

| ID | Econ. rationale | Novelty | Data | Execution | Cost | Robustness | Sharia | Independence | Ops | Total /45 | Blocker |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **SW-A** | 4 | 4 | 2 | 4 | 4 | 3 | 3 | 3 | 3 | **30** | needs an EDGAR historical calendar (NP); research hold |
| SW-F | 4 | 3 | 3 | 5 | 5 | 2 | 2 | 1 | 5 | 30 | no research independence; low power; ETF eligibility |
| SW-B | 3 | 4 | 2 | 2 | 3 | 2 | 3 | 3 | 3 | 25 | incompatible with stop-based 0.5% sizing |
| S1 | 3 | 2 | 3 | 4 | 3 | 2 | 3 | 1 | 4 | 25 | Stage R not authorized; V2 knowledge bias |
| **DT-A** | 4 | 5 | 3 | 4 | 2 | 3 | 1 | 4 | 4 | **30** | **BLOCKED_FOR_LIVE_USE** (D12, instrument); cost model unresolved |
| DT-G | 3 | 3 | 2 | 3 | 2 | 2 | 1 | 3 | 2 | 21 | D12; low n |
| DT-B ORB | 2 | 1 | 3 | 3 | 2 | 2 | 1 | 1 | 3 | 18 | **same family (F2)** |
| DT-D | 3 | 2 | 1 | 2 | 1 | 2 | 1 | 2 | 2 | 16 | **data: no PIT universe** |
| DT-C | 4 | 4 | 1 | — | — | — | 1 | — | — | — | **data: no news** |
| DT-E, DT-F | 1–2 | — | — | — | — | — | — | — | — | — | **no mechanism** |
| SW-C, SW-G, SW-H, SW-I | — | 1 | — | — | — | — | — | — | — | — | **existing locked / stopped / rejected family** |
| SW-J | 2 | 4 | 3 | 3 | 1 | 2 | 2 | 3 | 4 | 24 | **costs** |

**Score rationale (shortlisted candidates and the main runners-up):**

- **SW-A:**
  - Rationale 4: documented mechanism; decay is disputed.
  - Novelty 4: no event-driven work in the repo, but positive earnings reactions correlate with momentum winners,
    so some overlap with F3 is expected and must be measured.
  - Data 2: the method exists, the history does not.
  - Execution 4: daily, liquid, open fills.
  - Cost 4: low turnover.
  - Robustness 3: few events; mega-cap decay.
  - Sharia 3: screenable stocks; D10 and D2 open.
  - Independence 3: event-level outcomes have never been computed, but the period is broadly known.
  - Ops 3: EDGAR timing edge cases (§6).
- **DT-A:**
  - Rationale 4: published, with competing mechanisms.
  - Novelty 5: nothing similar in the repo.
  - Data 3: SPY 5m not probed; no spreads.
  - Execution 4: one instrument.
  - Cost 2: decisive and unresolved.
  - Robustness 3: post-publication risk.
  - Sharia 1: two live blockers.
  - Independence 4: SPY intraday has never been examined.
  - Ops 4: simple.
- **SW-F:**
  - Same total as SW-A, but Independence 1 (SPY's 2016–2026 path is well known to the authors, and SPY is
    `fwd-gate2`'s B2).
  - Robustness 2: few signals, similar to the owner-rejected TOM case.
- **S1:**
  - Novelty 2: a trend filter (F3 mechanism) plus a pullback entry (F4 mechanism).
  - Independence 1: same universe and period as V2.

---

## 10. Recommended shortlist

### Swing track: SW-A, earnings-reaction drift (recommended)

- **Economic hypothesis:** investors underreact to quarterly earnings news. After a large positive
  market-adjusted price reaction to an earnings release, the stock tends to outperform for several weeks (§5).
- **Entry concept:**
  - The reaction window starts at the first regular session that can reflect the release, set by the PIT
    acceptance timestamp (BMO → same session; AMC → next session).
  - The reaction is measured as the market-adjusted return over that window, scaled by the stock's own
    pre-event volatility.
  - Only reactions in a predeclared top tail are eligible.
  - Entry is at the next session's open after the window closes, so the signal is fully observed before entry.
- **Exit concept:**
  - Fixed time exit strictly before the next expected announcement.
  - A protective stop that defines R for the 0.5% sizing rule.
  - No optimization of either parameter.
- **Required data:**
  - SIP daily raw bars and corporate actions for the universe and SPY (fresh snapshot);
  - a historical PIT earnings calendar from SEC 8-K Item 2.02 acceptance timestamps, built with the existing
    `earnings_calendar_sources.csv` method and its edge-case rules.
- **Main risks:**
  - decay in mega caps;
  - few events on 25 symbols (low power);
  - overlap with momentum;
  - EDGAR timing errors (release time ≠ acceptance time);
  - hindsight universe.
- **Why distinct:**
  - Signal source: an information event, not a price-rank or trend state (F3), a reversal (F4), a breakout (F6)
    or an intraday pattern (F1, F2).
  - No earnings-event work exists in the repo (only ORB *exclusion* of earnings sessions).
- **Falsified if:**
  1. In the pre-registered sample, the mean net-of-cost market-adjusted return of eligible events over the holding
     window is not positive (including INCONCLUSIVE because of insufficient n).
  2. The effect disappears after controlling for each stock's prior 12-1 momentum (it would then be a relabelled
     F3).
  3. The effect exists only before costs.
- **Minimum research prerequisites:**
  - the research hold is lifted;
  - the owner authorizes an EDGAR earnings-calendar data project and a fresh daily SIP snapshot;
  - a decision on the universe (25 frozen vs. broader with disclosed survivorship);
  - a decision on whether dates overlapping the Stage H period may be used through a fresh snapshot;
  - the PIT timing rule is frozen before any price is read;
  - a protocol and acceptance thresholds are committed before data.

### Day track: DT-A, market intraday momentum (conditional; research-only)

**Recommended only if the owner chooses to keep a research-only day track before D12 is ruled.** Otherwise the
recommendation is **no day-trading research for now**.

- **Economic hypothesis:** the early-session index return predicts the direction of the last half hour (§5).
- **Entry concept:**
  - At a predeclared late-session time, go long the index ETF if the predeclared early-session return is positive.
  - Decisions use only completed bars.
- **Exit concept:** flat at the close (last-bar or closing-auction convention, predeclared). A protective stop
  defines R.
- **Required data:**
  - SIP 5m bars for SPY (research instrument) and for a candidate Sharia-screened ETF (execution instrument);
  - a quote-based or otherwise credible spread estimate (currently NOT_AVAILABLE).
- **Main risks:**
  - the cost model decides the outcome;
  - the instrument with the documented effect (SPY) is not the instrument the project could trade;
  - post-publication decay;
  - long-only removes half of the hypothesis.
- **Why distinct:** single-instrument intraday **timing** driven by end-of-day flows. Not stock selection or
  trend-following around VWAP (F1), and not the opening range (F2).
- **Falsified if:**
  1. The predeclared long-only signal has a non-positive mean net return under the predeclared cost model on SPY.
  2. Or it is positive on SPY but not on the compliant ETF.
  3. Or it is positive only before costs.
- **Minimum prerequisites:**
  - the research hold is lifted;
  - an owner decision to run day research while D12 is open;
  - verification that SIP 5m bars and a spread source exist for both ETFs;
  - a decision on the ETF instrument's eligibility path;
  - no data dated ≥ 2026-10-08 before the hold is lifted.

---

## 11. Rejected candidates and reasons

| ID | Reason | Rule triggered |
|---|---|---|
| D1 / F1 variants | same family as DAY-01, which failed | no distinct hypothesis |
| DT-B ORB | same family F2; only a re-test on non-overlapping data is possible | no distinct hypothesis |
| DT-C catalyst momentum | no news or catalyst timestamps | insufficient data |
| DT-D gap-and-go, broad universe | no PIT universe; no premarket data; overlaps F1a | insufficient data |
| DT-E volatility compression | no economic mechanism | no distinct hypothesis |
| DT-F intraday leadership | no identified mispricing; close to F1b | no distinct hypothesis |
| DT-G earnings-day intraday | low n; D12; intraday costs | not recommended (not a hard rule) |
| SW-B announcement premium | stop-based 0.5% sizing cannot bound the earnings gap; would need a different risk model, which is an owner decision | unacceptable execution assumption under the current risk rule |
| SW-C momentum / RS / 52-week-high | V2-MOM family, locked (`day22 …:140-157`) | existing family |
| SW-D consolidation breakout | legacy F6 found no edge; weak mechanism | existing family |
| SW-E (S1) | combination of F3 and F4 mechanisms; Stage R not authorized; low independence | not ranked; stays an owner draft |
| SW-F index trend timing | SPY history known to the authors; SPY is `fwd-gate2`'s B2; few signals, so low power (the same reason the owner rejected TOM-SPY); ETF eligibility undecided | not recommended (no research independence) |
| SW-G reversal, SW-H low-vol, SW-I TOM | stopped / previously rejected / owner-rejected | existing decisions |
| SW-J overnight premium | ≈250 full-capital round trips a year; cost-dominated | costs |

---

## 12. Research roadmap

| Stage | SW-A | DT-A (if approved) | Blocked by the hold? |
|---|---|---|---|
| 1 Hypothesis definition | this report §5, §10 | same | no (design) |
| 2 Data feasibility | EDGAR access terms; 8-K Item 2.02 coverage 2016+; timing-class rules; SIP 1Day fresh snapshot plan | SPY and ETF 5m availability; spread source | **yes**, for any probe or API call |
| 3 Research protocol | universe, PIT timing rule, reaction measure, tail threshold, holding window, costs, metrics, sample-size rule; all frozen before data | instrument, signal window, decision time, exit convention, cost model | no (design), but **freeze and commit wait for the owner** |
| 4 Independent data split | development / validation / one-shot historical test on a fresh snapshot (period: owner decision); confirmatory forward test after the hold | historical SPY intraday never examined (period: owner decision); forward afterwards | **yes** |
| 5 Implementation | EDGAR calendar builder (fail-closed, provenance as in the existing CSV); event study engine | intraday single-asset engine | **yes** (no implementation before protocol approval) |
| 6 Unit tests | PIT timing (AMC/BMO, holidays, early closes); no-lookahead future-mutation test; corporate actions; exit before the next event | completed-bar timing; close convention; cash settlement | with stage 5 |
| 7 Backtest | event-level, costs 0/5/10 bps | costs under the predeclared spread model plus the 5/10 bps convention | **yes** |
| 8 Robustness | momentum control; year breakdown; ticker concentration; cost stress | regime and volatility breakdown; ETF vs. SPY | **yes** |
| 9 Forward validation | pre-registered forward window | same | **yes** |
| 10 Sharia review | Akinda screening rows; D10 purification ruling; D2 multi-day exit; D15 broker checklist | D12 ruling; ETF instrument eligibility; D11 | adviser and owner, independent of the hold |
| 11 Paper trading | after stages 9–10 | after D12 | **yes** |
| 12 Live authorization | separate owner decision | separate owner decision | — |

---

## 13. Open owner decisions

| ID | Decision | Options | REC | What it blocks |
|---|---|---|---|---|
| OD-1 | OPS-1 now covers **two** untracked files (`docs/d1-s1-research-design-2026-11-02.md` and this report); `acquisition/v2/stage_f.py:322-323` refuses capture with any untracked file | commit / delete / move, per file | resolve both before 2026-12-09 16:15 ET (see the OPS-1 memo) | `fwd-gate2` capture |
| OD-2 | Day track | (a) park until D12 is ruled; (b) DT-A as a research-only track | **(a)**, unless research value without a live path is wanted | DT-A |
| OD-3 | Swing priority | SW-A / S1 / none | **SW-A** | SW-A protocol |
| OD-4 | EDGAR earnings-calendar data project (after the hold) | authorize / defer | authorize after the hold, with terms of use verified first | SW-A stages 2–7 |
| OD-5 | SW-A universe | 25 frozen (disclosed survivorship, few events) / broader (needs a PIT universe that does not exist) | 25 frozen for the first test; low n declared in advance | SW-A protocol |
| OD-6 | SW-A data period | e.g. 2016–2025 via a fresh snapshot (overlaps Stage R/H **dates**, not their files) / only post-hold forward data | owner decision; a fresh snapshot keeps Stage H files untouched, but the period is not unknown to the authors | SW-A stage 4 |
| OD-7 | S1 disposition | keep as a draft / close | keep as a draft, not prioritized | — |
| OD-8 | Correction record | acknowledge that the earnings calendar has an SEC source file (memo §7 superseded on that point) | acknowledge | — |

---

## 14. Acceptance criteria results

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Existing families inventoried | PASS | §2 |
| 2 | Failed hypotheses not reintroduced under new names | PASS | §2 family rule; DT-B, SW-C/D/G rejected as existing families |
| 3 | Distinct economic explanations | PASS | §5 |
| 4 | Data feasibility documented | PASS | §6 |
| 5 | Execution costs and risks evaluated | PASS | §7 |
| 6 | Sharia blockers explicit | PASS | §8 |
| 7 | Transparent, evidence-based scores | PASS | §9 (rationale given; blockers override totals) |
| 8 | ≤ 2 per track | PASS | 1 swing, 1 conditional day |
| 9 | No candidate described as profitable | PASS | statement at top; §10 falsification rules |
| 10 | No acquisition or backtest | PASS | §15 |
| 11 | Forward-test protections intact | PASS | §15 |

---

## 15. Safety confirmation

- No data acquisition, no API or network call, no backtest, no optimization.
- No strategy implementation; no existing code, protocol or document changed. The D1/S1 design document was not
  modified.
- Stage R and Stage H files were not opened. `fwd-gate2` results, sealed P001, `paper_state/` and forward
  capture or evaluation artifacts were not accessed. The only forward-related reads were code-level window
  constants and protocol text, as in earlier tasks.
- Files read for this report: research reports, protocols, strategy and engine source, Sharia documents,
  `config/earnings_calendar.csv`, `config/earnings_calendar_sources.csv`, `reports/run_log.txt`.
- The only file written is this report. It is untracked (see OD-1). No commit, no push.
