# DAY-23 — Audit of the Frozen 252-Session Forward OOS Requirement

| Field | Value |
|---|---|
| **Audit Objective** | Rigorous methodological audit of the frozen 252-session forward out-of-sample (OOS) requirement |
| **Audit Mandate** | Protocol-audit task only; no strategy evaluation; no forward data acquired, inspected, or calculated |
| **Audited Protocol** | Protocol 2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 (freeze commit `ba3cefe54ccf2fe14c62f1c609f143d8a0904221`) |
| **Active Strategy Subject** | V2-MOM (Cross-sectional momentum 12-1; frozen config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`) |
| **Starting HEAD** | `287e2caf08d1a72258959d6cd8f07a4e8298716e` (DAY-22 sign-off and forward lockdown) |
| **Core Question** | *"Why exactly is the forward OOS window 252 XNYS sessions, and is there a defensible methodological reason that requires 252 rather than a shorter predeclared window?"* |
| **Audit Classification** | **D (Conservative Design Choice) + E (Historical/Legacy Convention) + F (Insufficiently Justified for Standalone V2-MOM)** |
| **Governance Verdict** | **PROTOCOL AMENDMENT MAY BE WARRANTED** (Predeclared amendment recommended; protocol left unchanged in DAY-23) |

---

## 1. Executive Conclusion

1. **Origin of the 252 Requirement**: The 252-session forward duration originated in **commit `ba3cefe`** (2026-10-07) in `artifacts/day16/research-protocol-v2.md` §3.6. It was adopted as a conventional representation of "one calendar year of trading sessions" across a multi-strategy research portfolio comprising three heterogeneous families: V2-MOM (monthly), V2-STR (weekly), and V2-LRV (pairs trading with 126-session trading periods).
2. **Zero Technical Necessity**: There is **no technical, mechanical, or computational requirement** in V2-MOM or the backtest engine that requires 252 *future* sessions. V2-MOM requires a 252-session *lookback*, but this lookback is satisfied by pre-forward historical warmup bars (2025-01-02 to 2026-10-07). The monthly rebalancing loop, equity accounting, linear friction model, and CAGR formula $\text{CAGR} = (E_T / E_0)^{252 / N} - 1$ are mathematically well-defined for any session count $N \ge 1$.
3. **No Statistical Power Justification**: The protocol contains **no quantitative power calculation, sample size threshold, or minimum trade constraint** justifying 252 sessions. In fact, `research-protocol-v2.md` §20 (Q11) explicitly acknowledges that a one-year forward OOS has low statistical power ($N=12$ monthly decisions) and provides no statistical significance gate.
4. **Obsolescence of Multi-Strategy Sizing**: The 252-session window was originally sized so that V2-LRV could complete "exactly 2 relative-value trading periods" (2 × 126 = 252 sessions) and V2-STR could complete ~52 weekly cycles. Both V2-LRV (failed research in DAY-19) and V2-STR (failed holdout in DAY-21) are permanently stopped. Imposing a 252-session waiting period on V2-MOM alone is a legacy carry-over from rejected strategies.
5. **Anti-Snooping Guarantees Depend on Predeclaration, Not Duration**: Overfitting and data-snooping are prevented by freezing rules, parameters, and evaluation windows *ex ante* prior to observing data. A shorter forward OOS period (e.g. 63 sessions / 1 quarter or 126 sessions / 2 quarters) maintains identical blindness and anti-snooping rigor, provided the window is frozen before forward data is acquired or inspected.
6. **Governance Finding**: The current 252-session forward requirement is **insufficiently justified** for the surviving standalone V2-MOM strategy. **A protocol amendment may be warranted** to establish a shorter predeclared forward OOS window. In accordance with strict governance constraints, no protocol rule is altered in this task; any change must occur in a dedicated, subsequent amendment design task.

---

## 2. Earliest Origin of the 252-Session Requirement

| Property | Record |
|---|---|
| **Earliest Artifact** | `artifacts/day16/research-protocol-v2.md` (and companion `research-protocol-v2.json`, `research-checklist.json`) |
| **Earliest Commit** | `ba3cefe54ccf2fe14c62f1c609f143d8a0904221` ("docs: freeze DAY-16 research protocol v2", 2026-10-07 12:55:35 UTC) |
| **Exact Section** | Section 3.6 (Timeline Table and Rationale Item 5), Section 15 (Item 11), Section 20 (Q11) |
| **Checklist Item** | `TIME-05`: *"Forward OOS = 252 sessions after freeze-commit date (rule fixed)"* |

### Exact Documented Wording

In `research-protocol-v2.md` §3.6:
> *"Forward OOS (true OOS) | the 252 XNYS sessions starting at the first session strictly after the freeze-commit date | commit + 1 session | +251 sessions | 252 | final validation (§15)"*
>
> **Rationale 5**:
> *"Forward OOS is the only true OOS: its sessions do not exist when the protocol is frozen. 252 sessions ≈ one year: 12 momentum rebalances, ≈ 52 reversal rebalances, exactly 2 relative-value trading periods. It is short (§20 Q11); its length is fixed now and is never extended or shortened after looking. No data dated after the freeze commit may be acquired or inspected before the forward period has ended (§3.9)."*

In `research-protocol-v2.md` §15.11:
> *"FORWARD-PASSED = survived one year of genuinely unseen data — the only status labelled 'validated under v2', still subject to §20 (survivorship, single universe, short sample)."*

In `research-protocol-v2.md` §20 (Q11):
> *"Q11 | Statistical power: ≈ 71 monthly / ≈ 309 weekly rebalances in Research; forward OOS = 1 year; the families are correlated with each other and with B1 | NON-BLOCKING | diagnostic HAC + Holm reported; no significance gate"*

### Methodological Classification of Origin
The documented evidence demonstrates that the choice of 252 sessions was:
- **Mathematically derived?** **NO**. No formula, optimization, or variance bound generated 252.
- **Statistically justified?** **NO**. The protocol explicitly concedes in §20 Q11 that 252 sessions has low statistical power and deliberately omits a significance gate.
- **Inherited from another methodology?** **PARTIALLY**. 252 is the ubiquitous standard convention for trading days per calendar year in US equity markets ($252 \text{ XNYS sessions} \approx 1 \text{ year}$).
- **Chosen as a convention?** **YES**. It was selected as the conventional calendar unit of "one year".
- **Chosen for convenience?** **NO**. Imposing an 11-month live waiting period is operationally burdensome.
- **Chosen by protocol-owner judgment?** **YES**. Selected as a conservative heuristic to accommodate three heterogeneous strategies running concurrently.
- **Explained in protocol text?** Only as a calendar correspondence: 252 sessions = 12 monthly rebalances = ~52 weekly rebalances = exactly 2 relative-value pair trading cycles.

---

## 3. Technical Necessity Analysis

A rigorous distinction must be maintained between two entirely separate quantities:
1. **Historical Signal Lookback Length**: The number of historical bars required to compute the indicator ($L = 252$).
2. **Forward OOS Evaluation Duration**: The number of unobserved future sessions over which the strategy is simulated ($N$).

### 3.1 Lookback vs Forward Duration
- V2-MOM defines its signal as $r_{\text{mom}}(t) = \frac{TR(t-21)}{TR(t-252)} - 1$.
- To compute $r_{\text{mom}}(t)$ at decision close $t$, the algorithm requires total-return index values at $t-21$ and $t-252$.
- In the frozen protocol (§3.9), the data acquisition for forward evaluation (Stage F) explicitly mandates acquiring historical warmup data starting from **2025-01-02**:
  > *"Stage F (forward): bars and events 2025-01-02 → last forward session (≥ 252 sessions of lookback before any forward start in 2026 or later)."*
- Because the 252 historical lookback sessions are supplied by the pre-forward warmup data, **V2-MOM can execute its very first rebalance on session 1 of the forward OOS window**.
- The forward OOS window itself is **never** used to establish the 252-session lookback.

### 3.2 Evaluation of Engine Components Across Forward Length $N$

| Component | Code Implementation | Requirement on Forward Sessions $N$ | Technical Impact of $N < 252$ |
|---|---|---|---|
| **Signal Calculation** | `backtest.v2.signals.mom_targets` | Needs $TR(t-21)$ and $TR(t-252)$ from lookback | **NONE**: Sourced entirely from pre-forward warmup bars |
| **Monthly Rebalancing** | `backtest.v2.signals.month_end_flags` | Triggers on last XNYS session of each calendar month | **NONE**: Triggers on any month-end within the window |
| **Portfolio Sizing** | `backtest.v2.engine.simulate_targets` | Scales target weights ($w_i = 0.20$) to $E_{\text{open}}$ | **NONE**: Operates on an execution-by-execution basis |
| **Cash Constraint ($\lambda$)** | `_buy_all` ($\lambda = \min(1, \frac{K}{B(1+s)})$) | Solves cash budget at each open $t+1$ | **NONE**: Independent of total session count |
| **Cost Model** | Linear friction $s \cdot \sum \|\text{notional}\|$ | Deducted at each trade execution | **NONE**: Exact across any number of executions |
| **CAGR Calculation** | `mt.cagr(ending_equity, starting_capital, sessions)` | Evaluates $(E_T / E_0)^{252 / N} - 1$ | **NONE**: Formula algebraically normalizes by $N$ |
| **Benchmark Comparison** | B1 & B2 $(E_T / E_0)^{252 / N} - 1$ | Same formula over identical session slice | **NONE**: Identical time interval for strategy and benchmarks |
| **Gate 1 & Gate 2** | $\text{CAGR} \ge 0$ and $\text{CAGR} \ge \text{CAGR}_{B1}$ | Sign comparisons of unrounded float64 numbers | **NONE**: Gate logic operates identically for any $N \ge 1$ |
| **Anti-Lookahead Suite** | PIT mutation, truncation, fill checks | Evaluates sample sessions | **NONE**: Fully functional on any segment |
| **Determinism** | Bitwise file equality across runs | Hash comparison of outputs | **NONE**: Deterministic on any segment |

**Technical Conclusion**: **V2-MOM has ZERO technical necessity for 252 forward sessions.** The entire computational and mathematical pipeline functions seamlessly on any forward duration $N$.

---

## 4. Statistical Rationale Analysis

### 4.1 Absence of Protocol Power Calculations
An audit of `artifacts/day16/`, `artifacts/day17/`, `artifacts/day18/`, `artifacts/day19/`, `artifacts/day20/`, `artifacts/day21/`, and `artifacts/day22/` reveals:
- **No minimum observation count** derived from variance bounds.
- **No sample size calculation** for detecting active alpha over benchmark B1.
- **No Sharpe ratio standard error target** (e.g., Lo 2002 standard error $\text{SE}(\text{Sharpe}) \approx \sqrt{(1 + 0.5 \text{Sharpe}^2)/T}$).
- **No confidence interval precision bounds** on CAGR or drawdown.
- **No statistical significance gate**: The protocol explicitly rejected requiring statistical significance for passing gates. In §13, Gate 1 and Gate 2 are purely economic sign tests ($\text{CAGR} \ge 0$ and $\text{CAGR} \ge \text{CAGR}_{B1}$).
- Statistical diagnostics (HAC Newey–West and Holm adjustment) are explicitly designated as **non-gating diagnostics** (§12, §16) that *"cannot pass, fail, rank or rescue a family"*.

### 4.2 Statistical Power of 252 Sessions for Monthly Momentum
For V2-MOM, decisions occur only at calendar month-ends:
- In 252 trading sessions, there are exactly **12 monthly rebalance decisions**.
- In classical inferential statistics, a sample of $N = 12$ monthly returns has virtually no power to reject the null hypothesis of zero alpha ($H_0: \alpha = 0$) at $\alpha = 0.05$ against a benchmark like B1, unless the observed active Sharpe ratio is astronomically high ($\text{IR} > 1.2$).
- **Empirical Proof from DAY-21 Holdout**: In the DAY-21 historical holdout, V2-MOM evaluated across **856 sessions** (42 monthly rebalances) and outperformed B1 by **+18.01 percentage points** of net CAGR (71.25% vs 53.24%). Despite this enormous economic margin over 3.5 years, its Newey–West HAC $p$-value was **0.166** (not statistically significant).
- If 856 sessions (42 rebalances) cannot produce statistical significance, a 252-session forward window (12 rebalances) is statistically incapable of proving alpha.
- This was explicitly acknowledged in the protocol itself (`research-protocol-v2.md` §20 Q11):
  > *"Statistical power: ≈ 71 monthly / ≈ 309 weekly rebalances in Research; forward OOS = 1 year... diagnostic HAC + Holm reported; no significance gate."*

**Auditor Finding**: **252 sessions is frozen in the protocol text, but is NOT quantitatively or statistically justified.**

---

## 5. Historical Comparison with the 60-Session Design

To understand how the project arrived at 252 sessions, the historical evolution from Protocol v1.0 / v1.1 must be audited.

### 5.1 The Origin of the 60-Session Window (Protocol v1.0 / v1.1)
- In the initial day-trading phase of this project (Protocol v1.0), the research window was 60 sessions, and the OOS window was set to 60 sessions.
- **Source of Truth**: As documented in `artifacts/day15/day15d-oos-window-redesign.md` §4:
  > *"Research-window length: not required by the protocol. DAY-14 fixes 60 only for OOS ('equals the research-window length'); 60 for research came from the yfinance 60-day download."*
- The original 60-session window was an arbitrary artifact of Yahoo Finance's API limitation, which capped historical intraday 5-minute bar downloads to the trailing 60 calendar days.

### 5.2 The DAY-15D Staged OOS Redesign
- In DAY-15D, the project audited the calendar implications of a 60-session forward wait: waiting 60 future sessions required waiting 11 weeks until 2026-12-21.
- To eliminate this operational deadlock, DAY-15D explicitly proposed and recommended **Timeline T6 (Staged OOS)**:
  - **Stage 1 (Primary)**: **20 XNYS sessions** (2026-09-29 to 2026-10-26, arriving in ~3 weeks). Hard decision rule: if net return < 0, permanently REJECT.
  - **Stage 2 (Confirmation)**: **40 XNYS sessions** (2026-10-27 to 2026-12-22).
- DAY-15D proved that a shorter, predeclared window (20 sessions) was methodologically defensible when paired with a strict, frozen kill rule.

### 5.3 The Pivot to Protocol v2 (DAY-16)
- In DAY-16, the project abandoned intraday day-trading and pivoted to daily systematic equity research (Protocol v2) across 2016–2026.
- In this pivot, the research segment was expanded to 1,490 sessions (2017–2022), the historical holdout was introduced with 856 sessions (2023–2026), and forward OOS was defined as 252 sessions.
- **Why did forward OOS become 252 instead of 60?**
  1. The time scale shifted from intraday minutes to daily bars.
  2. The research portfolio contained **three concurrent families with radically different holding periods**:
     - V2-MOM: Monthly rebalance (~21 sessions).
     - V2-STR: Weekly rebalance (~5 sessions).
     - V2-LRV: Distance pairs trading with a **126-session trading period**.
  3. To evaluate V2-LRV at all, the forward period had to be at least 126 sessions; 252 sessions was chosen so that V2-LRV could complete "exactly 2 relative-value trading periods" (2 × 126 = 252).
- **The Critical Shift in Current State**:
  - V2-LRV failed research in DAY-19 and was stopped.
  - V2-STR failed holdout in DAY-21 and was stopped.
  - **V2-MOM is the sole surviving strategy**. The multi-cycle constraint of V2-LRV (126 sessions) is completely obsolete.

---

## 6. What Does Existing Evidence Already Provide?

Before evaluating forward OOS, we must account for the extensive empirical body of evidence already accumulated for V2-MOM:

| Empirical Phase | Period | Sessions | Calendar Duration | Monthly Decisions | V2-MOM Net CAGR (5 bps) | Primary Benchmark (B1) | Result |
|---|---|---|---|---|---|---|---|
| **Research (Stage R)** | 2017-02-01 → 2022-12-30 | 1,490 | ~6.0 years | 71 | **28.82%** | 18.44% (+10.38 pp) | **PASSED** |
| **Holdout (Stage H)** | 2023-01-03 → 2026-06-02 | 856 | ~3.5 years | 42 | **71.25%** | 53.24% (+18.01 pp) | **PASSED** |
| **Combined Historical** | 2017-02-01 → 2026-06-02 | **2,346** | **~9.5 years** | **113** | **Robust Outperformance** | — | **PASSED** |

### What Forward OOS Must Provide (Methodological Role)
The combined 9.5 years of historical testing has already demonstrated:
- Long-term factor drift across diverse macroeconomic environments (2017–2020 bull market, 2020 COVID crash, 2022 inflation/rate hikes, 2023–2026 tech rally).
- Resistance to 5 bps and 10 bps transaction costs.
- Complete algorithmic determinism and point-in-time data integrity.

However, historical data has two fundamental, irremediable limitations:
1. **Universe Hindsight Bias (Q5)**: The 25-stock universe represents modern mega-cap survivors selected with 2026 hindsight.
2. **Researcher Knowledge (Non-Blind Pseudo-OOS)**: Researchers and protocol authors possessed general knowledge of market trends during 2023–2026.

Therefore, the **sole methodological objective of forward OOS** is:
> **To verify that the frozen strategy executes and performs on data generated strictly after the freeze date, where researchers had zero hindsight, zero survivor knowledge, and zero opportunity to adapt the rules.**

### The Core Methodological Question
Does testing against unobserved, zero-hindsight data require waiting **252 sessions** (12 months), or does a shorter window of **63 sessions** (3 months) or **126 sessions** (6 months) deliver the exact same qualitative protection against hindsight and overfitting?

---

## 7. Alternative Forward-Window Methodology Analysis

The candidate forward-window durations are evaluated conceptually below, using only the frozen protocol mechanics and historical context (without accessing or simulating forward data):

| Window Length | Approx. Calendar Duration | V2-MOM Monthly Rebalances | Institutional / Practical Context | Methodological Evidence Provided | Limitations | Statistical Compatibility with Frozen Gates |
|---|---|---|---|---|---|---|
| **20 sessions** | ~1 month | 1 rebalance | ~1 calendar month; tested in DAY-15D T6 Stage 1 | Operational smoke test; verifies live MOO fills, split/dividend processing, cash non-negativity on unseen data | Single return draw; high noise; vulnerable to 1-month idiosyncratic shock | Fully compatible with CAGR formula; economically noisy |
| **40 sessions** | ~2 months | 2 rebalances | ~2 calendar months; tested in DAY-15D T6 Stage 2 | Verifies portfolio transition across consecutive rebalances | Highly sensitive to short-term sentiment; small sample | Fully compatible with CAGR formula |
| **60 sessions** | ~3 months | ~3 rebalances | Legacy protocol v1.0/v1.1 baseline; ~1 quarter | Spans a standard quarterly corporate earnings cycle; tests factor drift across 3 distinct months | Limited regime variation; small sample for $t$-tests | Direct historical continuity with DAY-14/15 standards |
| **63 sessions** | **Exactly 1 quarter** (252 / 4) | **3 rebalances** | **Standard institutional financial quarter**; standard hedge fund / asset management review cycle | Captures exactly one quarterly economic cycle; clean quarter boundary; tests portfolio through 3 full rebalances | Cannot observe multi-year macroeconomic regime changes | **Highly defensible institutional convention**; exact sub-multiple of 252 |
| **84 sessions** | ~4 months (252 / 3) | 4 rebalances | 1/3 of a trading year | Spans across two corporate earnings reporting seasons | Non-standard calendar interval | Fully compatible with CAGR formula |
| **126 sessions** | **Exactly 6 months** (252 / 2) | **6 rebalances** | **Semi-annual institutional cycle**; exactly 1 trading period of V2-LRV (§5.3) | Captures two full quarterly earnings cycles; spans multi-month factor drift; tests 6 consecutive portfolio rebalances | Extrapolates 6 months of data to annual CAGR via $(E_T/E_0)^2 - 1$ | **Strongest mid-term compromise**; already defined in protocol v2 |
| **252 sessions** | **1 full year** | **12 rebalances** | Current frozen requirement; 1 annual cycle | Full annual seasonal cycle; 12 monthly rebalances | Imposes 11 months of idle latency; still has low statistical power (§20 Q11) | Current frozen standard |

### Comparative Insights
- **63 sessions (1 quarter, 3 rebalances)** aligns with standard financial reporting and quarterly review cycles in institutional asset management. It eliminates 9 months of waiting while testing the strategy through a full earnings season.
- **126 sessions (2 quarters, 6 rebalances)** provides half a year of forward validation. Significantly, 126 sessions is already an established, formal time unit in Protocol v2 (the exact trading period length of V2-LRV in §5.3).
- Neither 63 nor 252 sessions achieves statistical significance ($p < 0.05$). The difference between 3 and 12 monthly rebalances is quantitative precision, not qualitative validation.

---

## 8. Blindness, Anti-Snooping, and Governance Guarantees

A critical question in protocol governance is whether shortening the forward window introduces data-snooping bias.

### 8.1 Sources of Data Snooping
In quantitative finance (White 2000, Bailey et al. 2014, Lopez de Prado 2018), data snooping and false discoveries occur through:
1. **Adaptive Early Stopping**: Halting the evaluation prematurely because interim performance happens to be positive.
2. **Post-Hoc Window Selection**: Trying windows of 20, 60, 126, and 252 sessions and publishing whichever yielded the highest return.
3. **Parameter Tweaking on OOS**: Observing poor OOS performance, modifying parameters, and re-running.
4. **Variant Selection**: Running multiple strategy variants on forward data and selecting the winner.

### 8.2 Why Predeclared Shortening Does NOT Weaken Blindness
If a forward duration amendment is adopted under strict governance:
- **Condition 1**: The amendment must occur **BEFORE any forward data is acquired, downloaded, or inspected**.
- **Condition 2**: The new duration $N^*$ must be **fixed and locked in code and protocol** prior to data access.
- **Condition 3**: The strategy configuration SHA-256 (`62827d70...`) must remain **100% frozen**.
- **Condition 4**: The evaluation must remain **one-shot**: evaluated exactly once when the $N^*$ sessions elapse.
- **Condition 5**: No interim performance may be inspected during the $N^*$ sessions.

Under these conditions, **a shorter forward OOS period preserves 100% of the anti-snooping and blindness guarantees**. The integrity of an out-of-sample test derives from the *predeclaration and immutability of the testing protocol*, not from the calendar length of the waiting period.

---

## 9. Separation of Distinct Conceptual Quantities

To prevent methodological confusion, the protocol audit explicitly separates three independent constructs:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. SIGNAL LOOKBACK (252 sessions)                                                              │
│    - Parameter of momentum formula: TR(t-21) / TR(t-252) - 1                                   │
│    - Requires historical data PRIOR to decision close t                                        │
│    - Sourced from pre-forward warmup data (Stage F lookback history)                           │
│    - DOES NOT REQUIRE OR DICTATE FORWARD DURATION                                              │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                ▲
                                                │ Independent
                                                ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. HISTORICAL HOLDOUT DURATION (856 sessions)                                                  │
│    - Historical pseudo-OOS segment: 2023-01-03 → 2026-06-02                                    │
│    - Bound by historical data boundaries (research cutoff 2022-12-30 to project data 2026-06-02)│
│    - Exhausts available uninspected historical data                                            │
│    - DOES NOT REQUIRE OR DICTATE FORWARD DURATION                                              │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                ▲
                                                │ Independent
                                                ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. FORWARD OOS DURATION (Currently 252 sessions)                                               │
│    - Policy choice determining duration of blind forward evaluation period                     │
│    - Originally sized for 3 concurrent strategies (including 126-session V2-LRV)               │
│    - Independent of signal lookback and historical holdout length                              │
│    - Freely configurable via formal protocol amendment without altering strategy mechanics    │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

The fact that V2-MOM utilizes a 252-session lookback does not imply, mathematically or methodologically, that forward validation must also span 252 sessions.

---

## 10. Audit Classification & Evaluation of Categories

The current 252-session requirement is evaluated against the standardized classification categories:

| Category | Applicable? | Audit Finding |
|---|---|---|
| **A. TECHNICALLY REQUIRED** | **NO** | No code, formula, rebalance loop, or accounting mechanic requires 252 future sessions. |
| **B. STATISTICALLY JUSTIFIED** | **NO** | No statistical power calculation or sample size threshold exists in the protocol. §20 Q11 concedes power is low and omits a significance gate. |
| **C. GOVERNANCE / ANTI-SNOOPING REQUIREMENT** | **PARTIALLY** | Predeclaring *a* fixed window is required for anti-snooping; but the specific quantity *252* is not required for anti-snooping. |
| **D. CONSERVATIVE DESIGN CHOICE** | **YES** | Chosen as a conservative calendar heuristic ("one full year") when drafting protocol v2. |
| **E. HISTORICAL / LEGACY CHOICE** | **YES** | Sized to accommodate 3 strategies, specifically V2-LRV's 126-session pair trading periods (2 × 126 = 252). With V2-LRV dead, it is a legacy relic. |
| **F. INSUFFICIENTLY JUSTIFIED** | **YES** | For standalone V2-MOM, requiring a 252-session forward freeze imposes an 11-month standstill without documented technical or statistical necessity. |

**Final Classification**:
$$\mathbf{D} \text{ (Conservative Design Choice)} + \mathbf{E} \text{ (Historical/Legacy Choice)} + \mathbf{F} \text{ (Insufficiently Justified for Standalone V2-MOM)}$$

---

## 11. Governance Recommendation & Amendment Assessment

### Protocol Amendment Verdict
$$\mathbf{PROTOCOL\ AMENDMENT\ MAY\ BE\ WARRANTED}$$

### Governance Rationale
1. **The Justification Deficit**: The 252-session forward window lacks technical and statistical necessity, and its original multi-strategy sizing rationale is obsolete following the elimination of V2-LRV and V2-STR.
2. **Defensibility of Shorter Predeclared Windows**: A shorter window—such as **63 sessions** (1 standard financial quarter, 3 monthly rebalances) or **126 sessions** (2 quarters / 6 months, 6 monthly rebalances)—provides equivalent blindness, regime testing, and anti-snooping protection, while reducing operational delay by 6 to 9 months.
3. **Preservation of Chain Integrity**: Under strict protocol governance rules, **DAY-23 makes NO amendment**. The protocol, the frozen V2-MOM configuration, and the repository state remain 100% unaltered.
4. **Procedure for Amendment**: Any revision to the forward OOS window must be executed as a formal, reviewed protocol amendment (e.g. Protocol v2.0.5 or v2.1) drafted and signed off in a separate governance task prior to any data acquisition.

---

## 12. Evidence Base Audited

This audit derived all findings directly from the committed source materials:
- `artifacts/day16/research-protocol-v2.md`: §3.6 (timeline & rationale 5), §3.9 (data stages), §4–§6 (strategy specifications), §13 (gates), §15 (OOS protocol), §16 (robustness), §20 (open questions & Q11).
- `artifacts/day16/research-protocol-v2.json`: Formal JSON schema and definitions.
- `artifacts/day16/research-checklist.json`: Items `TIME-05`, `TIME-06`, `TIME-07`.
- `artifacts/day15/day15d-oos-window-redesign.md`: §1–§8 (history of 60 sessions, yfinance limits, T6 staged 20+40 redesign).
- `artifacts/day19/day19-protocol-owner-signoff.md`: Research gate sign-off; rejection of V2-LRV.
- `artifacts/day21/day21-historical-holdout-report.md`: Historical holdout outcomes; rejection of V2-STR; V2-MOM pass at 71.25% CAGR.
- `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md`: DAY-21 sign-off and forward lockdown record.
- `backtest/v2/run.py`, `backtest/v2/engine.py`, `backtest/v2/signals.py`, `backtest/v2/metrics.py`: Codebase implementation.

---

## 13. Affirmation of What Was NOT Done

In strict adherence to the role constraints:
- [x] **ZERO forward market data was requested, downloaded, or acquired.**
- [x] **ZERO forward bars were inspected or read.**
- [x] **ZERO forward strategy returns or performance were computed.**
- [x] **ZERO backtests or simulations were executed.**
- [x] **V2-MOM strategy code and parameters were NOT modified.**
- [x] **V2-STR and V2-LRV were NOT reopened or modified.**
- [x] **Protocol rules were NOT amended in this task.**
- [x] **The 252-session requirement was NOT changed in this task.**
- [x] **No commits were pushed to remote.**
