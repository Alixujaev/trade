# DAY-24 — Design of Predeclared Forward OOS Duration Amendment

> **NOTICE: PROPOSED AMENDMENT — NOT YET EFFECTIVE**  
> This artifact represents a formal protocol amendment proposal. In strict accordance with systematic governance constraints, **no protocol rule is modified in this task**. This amendment design is submitted for protocol-owner review and requires formal sign-off and adoption in a separate commit before taking effect.

| Field | Value |
|---|---|
| **Document Purpose** | Formal design and justification of a predeclared forward OOS duration amendment for V2-MOM |
| **Amendment Status** | **PROPOSED AMENDMENT — NOT YET EFFECTIVE** |
| **Design Mandate** | Protocol design only; zero forward data acquired, inspected, or calculated; zero strategy code modified |
| **Target Strategy** | V2-MOM (Cross-sectional momentum 12-1; frozen config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`) |
| **Source of Truth** | DAY-23 Audit commit `409b771467da3b95579d4a9e5965fcae36dc4707` |
| **Starting HEAD** | `409b771467da3b95579d4a9e5965fcae36dc4707` |
| **Proposed Replacement Window** | **63 XNYS sessions** (Single Blind Window; exactly 1 standard financial quarter) |
| **Target Calendar Dates** | **2026-10-08 → 2027-01-07** (Single one-pass evaluation on 2027-01-07 after 16:15 ET) |
| **Alternative Evaluated** | 126 XNYS sessions (Semi-annual cycle; 2 quarters; 2026-10-08 → 2027-04-09) |

---

## 1. Executive Summary & Context

1. **The Justification Deficit of 252 Sessions**: The DAY-23 audit established conclusively that the frozen 252-session forward out-of-sample (OOS) duration lacks technical necessity, lacks quantitative statistical power justification, and represents an obsolete multi-strategy artifact. The original 252-session duration was chosen in DAY-16 to accommodate three heterogeneous strategies running concurrently, specifically to allow the pairs-trading strategy (V2-LRV) to complete two full 126-session trading periods ($2 \times 126 = 252$). Because V2-LRV failed research in DAY-19 and V2-STR failed holdout in DAY-21, **V2-MOM is the sole surviving strategy**. Imposing an 11-month idle standstill on a standalone monthly factor strategy is methodologically unjustified.
2. **Core Governance Objective**: The purpose of forward OOS is **not** to amass dozens of rebalance observations (which were already accumulated across 2,346 historical sessions, spanning 113 monthly decisions over 9.5 years in research and holdout). Rather, the singular methodological purpose of forward OOS is to serve as an **independent, zero-hindsight sanity check on truly unseen data**, completely eliminating the survivorship bias (Q5) and researcher hindsight inherent in historical data.
3. **Recommended Architecture**: A **Single Blind Window of 63 XNYS sessions** (exactly one standard financial quarter, $252 / 4 = 63$).
   - Spans **2026-10-08 to 2027-01-07**.
   - Contains **3 distinct monthly rebalances** following the initial portfolio construction.
   - Spans a full corporate earnings cycle and quarterly rebalancing period.
   - Reduces idle latency from 12 months down to 3 months, aligning with standard institutional financial review cycles.
   - Evaluated under a single, blind, one-pass procedure that completely eliminates the risks of interim peeking, adaptive early stopping, and complex staged decision rules.
4. **Preservation of Scientific Integrity**: Anti-snooping and blindness guarantees derive from freezing the window length, decision rules, and strategy configuration *ex ante* prior to observing data. By adopting this amendment strictly before any forward data is acquired, the protocol maintains 100% methodological rigor.

---

## 2. Candidate Window Comparison

In accordance with protocol design standards, seven candidate forward-window lengths were evaluated across objective methodological dimensions. In strict compliance with safety rules, **no strategy returns or simulated performances were calculated**.

| Candidate Window | Calendar Duration | End Date (Start: 2026-10-08) | Monthly Decisions (V2-MOM) | Methodological Characteristics | Limitations | Governance & Latency Assessment |
|---|---|---|---|---|---|---|
| **20 sessions** | ~1 month | 2026-11-04 | 1 rebalance | Operational smoke test; tests live MOO fills, split/dividend processing, cash constraints | Single observation; extreme vulnerability to idiosyncratic 1-month noise | **REJECTED**: Insufficient rebalance depth; 1 rebalance cannot evaluate factor drift |
| **40 sessions** | ~2 months | 2026-12-03 | 2 rebalances | Tests transition between two consecutive monthly portfolios | Crosses an arbitrary intra-quarter boundary; high short-term noise | **REJECTED**: Arbitrary calendar boundary; sample too small |
| **60 sessions** | ~3 months | 2027-01-04 | ~3 rebalances | Legacy baseline from DAY-14/DAY-15; roughly one quarter | Inherits arbitrary 60-day limit from Yahoo Finance API download constraints | **REJECTED**: Arbitrary non-standard session count |
| **63 sessions** | **Exactly 1 quarter** (252 / 4) | **2027-01-07** | **3 rebalances** | **Standard institutional financial quarter**; clean quarter division; spans a full corporate earnings cycle; tests 3 monthly rebalances | Cannot observe multi-year macroeconomic regime changes | **RECOMMENDED**: Optimal balance of institutional convention, rebalance depth, and latency reduction |
| **84 sessions** | ~4 months (252 / 3) | 2027-02-08 | 4 rebalances | Spans across two earnings seasons (1/3 of a trading year) | Non-standard calendar interval; awkward reporting period | **REJECTED**: Non-standard financial interval |
| **126 sessions** | **Exactly 2 quarters** (252 / 2) | **2027-04-09** | **6 rebalances** | Semi-annual institutional cycle; spans two full earnings cycles; native duration from protocol v2 (§5.3) | Extrapolates 6 months to annual CAGR; requires 6 months of latency | **STRONG RUNNER-UP**: Highly defensible conservative alternative |
| **252 sessions** | 1 full year | 2027-10-08 | 12 rebalances | Full annual seasonal cycle; 12 monthly rebalances | Imposes 11-month idle latency; still has low statistical power (§20 Q11) | **SUPERSEDED**: Obsolete multi-strategy legacy requirement |

---

## 3. Methodological Distinctions: What "Sufficiency" Means

A critical methodological failure in quantitative research is conflating different definitions of sample "sufficiency". The protocol owner explicitly distinguishes four distinct concepts:

| Dimension | 20 Sessions | 63 Sessions (Proposed) | 126 Sessions | 252 Sessions (Frozen) | Methodological Finding |
|---|---|---|---|---|---|
| **A. Sufficient to Preserve Blindness** | **YES** | **YES** | **YES** | **YES** | Blindness is a property of *precommitment and data isolation*, not calendar duration. Any duration frozen before observing data is 100% blind. |
| **B. Sufficient to Test Economic Survivability** | NO | **YES** | **YES** | **YES** | Testing economic survivability requires multiple portfolio rebalances across a corporate reporting cycle to verify that positive drift exceeds costs. 63 sessions (3 rebalances) satisfies this; 20 sessions does not. |
| **C. Sufficient for Statistical Significance ($p < 0.05$)** | NO | NO | NO | NO | Neither 63 nor 126 nor 252 sessions has statistical power to prove alpha on monthly data. In holdout, 856 sessions (42 rebalances) with +18.01 pp CAGR over B1 yielded HAC $p = 0.166$. The protocol explicitly omits a significance gate. |
| **D. Sufficient for Deployment Confidence** | NO | **YES** | **YES** | **YES** | Deployment confidence rests on the cumulative weight of 9.5 years of historical evidence (2,346 sessions, 113 rebalances) confirmed by an uncompromised, blind quarterly forward validation. |

**Key Finding**: Demanding 252 forward sessions under the guise of "statistical sufficiency" is scientifically invalid, because 252 sessions (12 monthly data points) does not achieve statistical significance anyway. The value of forward OOS is qualitative (verifying blindness and execution on unobserved data), which is fully delivered by 63 sessions.

---

## 4. Architecture Evaluation: Staged vs. Single Blind Window

The protocol owner evaluated two alternative implementation architectures:

### Architecture A: Single Blind Window (63 XNYS Sessions)
- **Mechanics**: The strategy configuration is frozen. Exactly 63 XNYS sessions elapse (2026-10-08 to 2027-01-07). On 2027-01-07 after 16:15 ET, Stage F data is acquired in a single pass. The strategy is simulated once. Gates 1, 2, A, and C are evaluated.
- **Blindness**: Absolute. Zero data acquired or inspected prior to completion.
- **Anti-Snooping**: Total. Zero opportunity for adaptive early stopping or interim intervention.
- **Governance Complexity**: Minimal. Exactly one evaluation date, one dataset acquisition, one gate outcome.
- **Decision Rule Complexity**: Identical to frozen Protocol v2 §13. No new formulas or intermediate thresholds.
- **Peeking Risk**: Zero.

### Architecture B: Predeclared Staged Blind Window (e.g. 20 + 40 or 30 + 33 Sessions)
- **Mechanics**: Stage 1 evaluates after session 20 or 30; if a kill threshold is breached, the strategy stops; otherwise Stage 2 continues to session 63.
- **Analysis of DAY-15D Precedent**: In DAY-15D, staged OOS was designed for an intraday mean-reversion strategy with hundreds of daily trades, where a negative net return over 20 sessions indicated fatal failure.
- **Fatal Flaw for Monthly Momentum**: V2-MOM rebalances monthly. In a 20-session initial stage, there is exactly **one monthly rebalance**. Equity momentum routinely experiences volatile single-month drawdowns even during exceptional multi-year bull runs (for example, V2-MOM experienced a -11.3% drawdown in March 2025 during historical holdout, yet finished the holdout period with +71.25% net CAGR).
- Imposing a negative-return kill rule on a single monthly rebalance would create an unacceptably high rate of false-positive rejections.
- Conversely, running an intermediate checkpoint *without* a kill rule is merely "interim peeking", which violates the fundamental blind evaluation mandate.
- Staged evaluation also introduces substantial governance friction: requiring two separate data acquisition snapshots, two validation reviews, and complex conditional gate logic.

**Architectural Decision**: **Architecture A (Single Blind Window) is unequivocally recommended.** It maximizes simplicity, eliminates interim peeking risks, avoids uncalibrated intermediate kill rules, and preserves the pristine gate logic of Protocol v2.

---

## 5. Justification of the Recommended Window (63 Sessions)

The recommendation of **63 XNYS sessions** is justified on objective, protocol-level criteria established independently of V2-MOM performance:

1. **Exact Institutional Quarter**: In US equity markets, 252 trading sessions divide cleanly into four quarters of exactly **63 sessions** ($252 / 4 = 63$). This aligns the evaluation window with standard institutional performance reporting periods (Q1–Q4), quarterly corporate earnings announcements, and quarterly macroeconomic reviews.
2. **Adequate Monthly Rebalance Depth**: With monthly rebalancing occurring on the last trading session of each calendar month, a 63-session window starting on 2026-10-08 captures:
   - Initial portfolio construction: Executed at the open of session 1 (2026-10-08).
   - Rebalance 1: October 2026 month-end (2026-10-30 close, execute 2026-11-02 open).
   - Rebalance 2: November 2026 month-end (2026-11-30 close, execute 2026-12-01 open).
   - Rebalance 3: December 2026 month-end (2026-12-31 close, execute 2027-01-04 open).
   - Final liquidation: Executed at the close of session 63 (2027-01-07).  
   This provides **three distinct rebalancing transitions** across four distinct monthly portfolio allocations.
3. **Elimination of Arbitrary API Artifacts**: Protocol v1.0 used 60 sessions because Yahoo Finance restricted intraday downloads to 60 days. Replacing 60 with 63 formalizes the evaluation into a precise calendar-based financial quarter.
4. **Resolution of Operational Deadlock**: A 252-session forward window requires waiting until October 2027 (an 11-month standstill). 63 sessions concludes on **January 7, 2027**—a latency reduction of 75%—providing a timely, actionable validation milestone without sacrificing scientific rigor.
5. **Why 63 is Preferable to 126**: While 126 sessions (6 months, 6 rebalances) is a valid conservative option, it still imposes half a year of idle latency. Given that V2-MOM already demonstrated factor persistence over 113 historical rebalances across 9.5 years, a 1-quarter blind sanity check (63 sessions) is fully sufficient to verify execution integrity and absence of hindsight bias.

---

## 6. Formal Protocol Amendment Specification (Proposed)

```
================================================================================
PROPOSED AMENDMENT: PROTOCOL v2.0.5 — FORWARD OOS DURATION FOR V2-MOM
STATUS: PROPOSED AMENDMENT — NOT YET EFFECTIVE
TARGET: artifacts/day16/research-protocol-v2.md (§3.6, §15.11)
================================================================================
```

### Specification 1: Replacement Forward-OOS Duration
For strategy family **V2-MOM only**, the forward out-of-sample duration is hereby amended from 252 XNYS sessions to **63 XNYS sessions**.

### Specification 2: Exact Session-Count Definition
The forward evaluation window shall consist of exactly **63 consecutive trading sessions** of the New York Stock Exchange (`XNYS`), as resolved by `exchange_calendars` version 4.13.2.

### Specification 3: Start-Date Rule
The forward window starts at the first XNYS session strictly following the protocol freeze commit date (`ba3cefe54ccf2fe14c62f1c609f143d8a0904221`), which is **2026-10-08**.

### Specification 4: End-Date Rule
The forward window ends on the 63rd XNYS session, which is **2027-01-07** (inclusive). Final liquidation of all positions occurs at the close of 2027-01-07.

### Specification 5: Permitted Data Acquisition (Stage F)
- Stage F market data acquisition shall be executed **strictly after 16:15 ET on 2027-01-07**.
- Data acquired: Series A (raw OHLC bars) and Alpaca corporate actions for the 25 universe symbols and SPY spanning **2025-01-02 to 2027-01-07** (providing $\ge 252$ historical sessions of lookback prior to forward start).
- Data acquisition must occur in a **single, idempotent pass** into `data/oos_cache/protocol_v2/stage_f/`.

### Specification 6: Prohibited Data and Inspection
- Zero forward market data dated after 2026-10-07 shall be acquired, queried, or inspected prior to the conclusion of the 63rd session.
- Operational feeds, if active, must strictly isolate raw ingestion and must never calculate or expose forward strategy performance during the blind evaluation window.

### Specification 7: Interim Evaluation Prohibition
- **Interim performance evaluations are strictly prohibited.**
- No intermediate checkpoints, calculations, dashboards, reports, or logs of forward CAGR, Sharpe, Drawdown, or returns shall be generated during the 63-session period.

### Specification 8: Final Evaluation Trigger
The forward evaluation shall be triggered exactly once, following the completion of session 63 (after 2027-01-07 16:15 ET), contingent upon Stage F data validation passing all structural integrity checks (`missing_bars == 0`, monotonic timestamps, event consistency).

### Specification 9: Decision & Gate Rules
The evaluation gates remain **100% identical to frozen Protocol v2 §13**, evaluated at the primary 5 bps cost scenario using unrounded float64 arithmetic:
- **Gate 1 (Economic Viability)**: Net CAGR at 5 bps $\ge 0.0$.
- **Gate 2 (Benchmark Outperformance)**: Net CAGR at 5 bps $\ge$ Primary Benchmark B1 Net CAGR at 5 bps over the identical 63 sessions.
- **Gate A (Integrity)**: All point-in-time checks, fill-source checks, execution-timing checks, and deterministic reproduction must pass.
- **Gate C (Completeness)**: Complete reporting of all §16 robustness items across 0, 5, and 10 bps friction.
- **Graduation Status**:
  - If Gates 1, 2, A, and C pass $\rightarrow$ **`FORWARD-PASSED` (Validated under Protocol v2)**.
  - If Gate 2 fails $\rightarrow$ **`FORWARD-FAILED (economic)`**.
  - If Gate 1 fails $\rightarrow$ **`FORWARD-FAILED (negative return)`**.

### Specification 10: Treatment of Partial Calendar Years
Because the 63-session window spans 2026-10-08 to 2027-01-07 (Q4 2026 plus 5 sessions in 2027), the CAGR calculation:
$$\text{CAGR} = \left(\frac{E_T}{E_0}\right)^{\frac{252}{63}} - 1 = \left(\frac{E_T}{E_0}\right)^4 - 1$$
algebraically annualizes the quarterly holding period return. In §16 diagnostic reporting, subperiods for 2026 and 2027 shall be explicitly labelled as "partial" (correcting procedural deviation P1 by design).

### Specification 11: Determinism Requirement
Two independent backtest executions across the 63 forward sessions must produce byte-identical fill logs, execution logs, equity curves, and metrics.

### Specification 12: Reproducibility Requirement
The run artifact must contain a complete §17 reproducibility block recording platform details, Python version, package hashes, snapshot manifest SHA-256, engine code SHA-256s, and the frozen strategy configuration SHA-256.

### Specification 13: Operational Failure Protocol
- **Unscheduled Market Closures**: If an unscheduled market closure occurs, the calendar automatically advances until exactly 63 completed sessions are observed.
- **Data Ingestion Failures**: If missing bars exceed the 2% review threshold (§3.8), evaluation halts immediately for protocol-owner review; no imputation or synthetic data is permitted.

### Specification 14: Scope of Amendment
This amendment applies **exclusively to V2-MOM** (`V2-MOM-F001`). V2-LRV and V2-STR remain permanently STOPPED and are not revived or modified.

### Specification 15: Absolute Strategy Parameter Invariance
**No parameter of V2-MOM is modified.** Lookback (252), lag (21), ranking rule (descending), universe (25 stocks), portfolio size (5 stocks), weighting (20%), execution rule (MOO $t+1$), and cost models (0/5/10 bps) remain 100% identical. Strategy configuration SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` is invariant.

---

## 7. Strict Affirmation of Protocol Integrity

The protocol designer certifies that during the execution of DAY-24:
- [x] **ZERO forward market data was acquired, requested, downloaded, or loaded.**
- [x] **ZERO forward bars were inspected or read.**
- [x] **ZERO forward strategy returns, CAGR, Sharpe, Drawdown, or metrics were computed.**
- [x] **ZERO backtests or simulations were executed.**
- [x] **V2-MOM strategy code and parameters were NOT modified.**
- [x] **V2-STR and V2-LRV were NOT reopened, resurrected, or modified.**
- [x] **Protocol v2.0 files (`research-protocol-v2.md`, `research-protocol-v2.json`) were NOT modified.**
- [x] **The working tree remains clean of uncommitted changes.**
