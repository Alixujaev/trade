# SW-A: Earnings-reaction drift. Research specification (draft)

> **Status: DRAFT — NOT APPROVED FOR EXECUTION.**
> Design only. No data acquired, no API called, no backtest, no optimization, no implementation.
> Stage R, Stage H, `fwd-gate2`, sealed P001 and `paper_state/` were not opened.
> **No claim is made that SW-A is profitable.** The design aims to make the hypothesis easy to falsify.
> Every numeric value marked **PROPOSED** needs owner approval; **OPEN** items are owner decisions.

**Labels:**
- **FACT**: read directly from a cited repository file.
- **INF**: an inference.
- **HYP**: a hypothesis.
- **ASSUMPTION**: assumed, not verified.
- **LIT [UNVERIFIED]**: literature from prior knowledge, not repository evidence and not verified here.
- **UNRESOLVED**: cannot be settled from repository evidence.

---

## 0. Evidence audit

### 0.1 Documents read
- `docs/strategy-discovery-report-2026-11-02.md` (SW-A shortlist, §5, §6, §10)
- `docs/d1-s1-research-design-2026-11-02.md` (risk rule §3, Sharia §4, protocol conventions)
- `config/earnings_calendar.csv`, `config/earnings_calendar_sources.csv`, `data/earnings.py`
- `strategy/day/orb_rules.py:188-211` (how the calendar is consumed)
- commit `eb87c88` message
- `artifacts/orb/*` earnings references
- `artifacts/day16/research-protocol-v2.md` §3.4, §8, §9, §11.2 (price basis, execution, costs, corporate actions)
- `artifacts/day17/day17-data-blockers.md` §2–§5 (1Day semantics, entitlement, corporate actions)
- `docs/shariah/AAOIFI_DATA_PROVIDER_ASSESSMENT.md` (SEC EDGAR assessment)
- `docs/shariah/AAOIFI_MVP_DECISIONS.md`, `AKINDA_PROVIDER_DECISION.md`

### 0.2 SEC 8-K source: what the repository actually establishes

**FACT, `config/earnings_calendar_sources.csv`:**
- 26 data rows. Columns: `symbol, excluded_session, announcement_date, accepted_et, timing_class, timing_status,
  accession, index_url, exhibit_url, rule, note`.
- Coverage: 2026-07-02 → 2026-09-25 only (`config/earnings_calendar.csv`, all 25 rows).
- `timing_class`: 18 AMC, 6 BMO, 1 UNVERIFIED, 1 empty.
- `timing_status`: 23 VERIFIED, 1 UNVERIFIED, 1 NOT_EARNINGS, 1 VERIFIED_NO_EARNINGS_IN_WINDOW.
- `rule` strings: "AMC -> next XNYS session", "BMO -> same session", "not in calendar", "coverage only", and one
  owner decision.

**FACT, edge cases recorded in the `note` column:**
- **TSLA 2026-07-02:** an Item 2.02 filing that was a deliveries report, not quarterly results. "owner decision:
  excluded".
- **PEP:** "8-K accepted 2026-07-08 17:55:54 ET, EDGAR filing date 2026-07-09; release time not stated in exhibit
  99.1 - IR confirmation pending". Status UNVERIFIED. The owner excluded 2026-07-09, the session affected under
  either reading.
- **XOM:** "new CIK 2115436; old CIK 34088 checked".
- **MU:** "EDGAR submissions (recent list back to 2017-09-06): no 8-K Item 2.02 filed 2026-07-02..2026-09-25".

**FACT, commit and code:**
- The commit message calls the calendar "EDGAR-verified, with source audit table" (`eb87c88`).
- `data/earnings.py` is fail-closed on missing coverage. It stores dates only, not times or classes.

**What is NOT established (UNRESOLVED):**

| # | Question | Status |
|---|---|---|
| U1 | Does `accepted_et` equal the public release time? | **No evidence that it does.** `accepted_et` is the EDGAR acceptance time of the 8-K. PEP shows that acceptance and the release can be on different dates, and that the release time may be unstated |
| U2 | What evidence makes a row `VERIFIED`? | **Not documented anywhere** in the repository: no method document, no field definition. INF: PEP's note implies VERIFIED rows had a release time confirmed from the exhibit or IR, but this is not written down |
| U3 | Does EDGAR `submissions` cover 2016 onward? | **Partially UNRESOLVED.** The MU note says the "recent list" reached back to 2017-09-06. Earlier filings need further pages (INF). EDGAR access terms are [UNVERIFIED] (`AAOIFI_DATA_PROVIDER_ASSESSMENT.md:41-45`) |
| U4 | Is Item 2.02 always furnished at the time of the release? | **ASSUMPTION, not verified.** The filing deadline rules are not documented in the repository |
| U5 | How are non-results Item 2.02 filings (deliveries, preliminary results, guidance) classified? | Only one precedent, an owner decision (TSLA). No general rule |

**Consequence:** a historical SW-A calendar cannot simply copy the 2026 method. It needs a **written,
predeclared verification method** (§2.3) built before any price is read.

---

## 1. Hypothesis

### 1.1 Components (kept separate)

| Concept | Definition here | Observable in this project? |
|---|---|---|
| **Earnings surprise** | reported results minus market expectation | **No.** No consensus-estimate data. SW-A does **not** measure surprise |
| **Initial market reaction** | abnormal return over the first reaction session(s) after a confirmed release (§3) | yes, from prices and timing |
| **Post-event drift** | abnormal return from the first tradable open after the reaction window to a fixed horizon (§4.3) | yes |
| **Market effect** | the part of a return explained by the broad market | SPY as proxy (§3.2) |
| **Sector effect** | industry-wide news (for example a peer's earnings the same week) | **not removed**: no sector data (§6). It stays in the "abnormal" return |

### 1.2 Statements

- **H1 (primary):** conditional on a confirmed earnings event, the post-event drift is positively related to the
  standardized initial reaction: larger positive reactions are followed by larger subsequent abnormal returns.
- **H2 (trading):** for events whose standardized reaction is at least a predeclared threshold, the mean post-event
  drift net of trading costs is positive.
- **H0 (null, the default belief):** neither holds. The drift is zero, or it exists only before costs, or it is
  explained by prior momentum.

### 1.3 Why it could exist / why it could be gone

**Could exist (HYP; LIT [UNVERIFIED]):**
- limited investor attention;
- anchoring on prior expectations;
- slow incorporation of what current earnings imply for future earnings.

Ball & Brown (1968), Bernard & Thomas (1989, 1990), and price-based variants (Chan, Jegadeesh & Lakonishok 1996)
are cited from memory only.

**Could be gone (HYP; LIT [UNVERIFIED]):**
- decay after publication;
- faster information processing (algorithmic reading of releases, options-implied moves);
- concentration of the historical effect in small, illiquid stocks rather than mega caps.

Later studies, for example Martineau (2022), report that the drift has largely vanished. **For a 25-symbol
mega-cap universe, H0 is the prior expectation.** SW-A is worth testing only because the test is cheap, distinct
from earlier work, and decisive.

---

## 2. Event definition

### 2.1 Notation

- `s` indexes XNYS regular sessions (`exchange_calendars`, as in protocol v2).
- `Open(s)` = 09:30 ET; `Close(s)` = 16:00 ET, or 13:00 ET on early closes.
- `T_acc` = EDGAR acceptance datetime of the 8-K (ET).
- `T_rel` = public release datetime of the earnings press release (ET).

### 2.2 Event candidates

An **event candidate** is an 8-K (form `8-K`, not `8-K/A`) that lists **Item 2.02**, filed by the issuer's CIK.
The universe symbol → CIK mapping is point-in-time and covers CIK changes (XOM precedent).

**Classification `class(e)`** must be frozen before use. It is decided from the filing text by a written,
versioned rule set plus a review log:

| Class | Meaning | Baseline |
|---|---|---|
| `RESULTS` | quarterly or annual results release | included |
| `PRELIM` | preliminary results / pre-announcement | excluded (separate future hypothesis) |
| `OTHER_2_02` | operational data (e.g. deliveries), guidance-only, other | excluded (TSLA precedent) |
| `UNCLASSIFIABLE` | — | excluded, counted |

### 2.3 Release timestamp `T_rel` (verification method; PROPOSED)

`T_rel` is accepted only from evidence recorded with URL, retrieval date and SHA-256:
- **(a)** an explicit time or session statement in the press release (exhibit 99.x), e.g. "after market close";
- **(b)** the company investor-relations archive, with a timestamp.

Then:

```
timing_status(e) = VERIFIED    if (a) or (b) gives a time or session statement and it is consistent with T_acc
                                  (T_rel ≤ T_acc and T_acc − T_rel ≤ Δ_max)
                 = UNRESOLVED  otherwise (no evidence, conflicting sources, or inconsistency)
```

- `Δ_max` = 1 business day (PROPOSED; ASSUMPTION U4).
- **`T_acc` alone never sets `T_rel`.** Acceptance time is used only as a consistency bound.
- UNRESOLVED events are **excluded** from the baseline and counted.
- Sensitivity variant (not baseline): include them using the two-session window in §3.4.

### 2.4 Session class and the first reaction session `s*`

| Session class (from `T_rel`) | Condition | `s*` |
|---|---|---|
| `BMO` | `T_rel` < `Open(d)` on session day `d` | `d` |
| `AMC` | `T_rel` ≥ `Close(d)` on session day `d` | next session after `d` |
| `NON_SESSION` | `T_rel` on a weekend or holiday | next session after `T_rel` |
| `INTRA` | `Open(d)` ≤ `T_rel` < `Close(d)` | **excluded** (part of session `d` is pre-release); counted |

### 2.5 Deduplication, amendments, conflicts

- **Several Item 2.02 8-Ks for the same fiscal period:** the event is the **earliest** `RESULTS` filing for that
  period. Later ones are not new events.
- **`8-K/A`:** never a new event. If an amendment changes the release time or the classification, the event becomes
  UNRESOLVED (excluded).
- **Conflicting release dates between sources:** UNRESOLVED.
- **Missing timestamp:** UNRESOLVED.
- **Two `RESULTS` events for one symbol less than `H + 2` sessions apart:** both stay events, but §4.6 governs the
  positions.

### 2.6 Determinism

Given the frozen symbol→CIK map, the classification rule set, the review log and the evidence files, `s*(e)` is a
pure function. The event table is built and hashed **before any price data is read**.

---

## 3. Signal (reaction measurement)

### 3.1 Price basis (FACT-based conventions, protocol v2 §3.4)

- Execution and accounting use **raw** OHLC.
- Returns use a point-in-time (PIT) **total-return** series built from raw closes and the events effective by that
  date (splits `q`, cash dividends `d`):

  ```
  r_i(k) = (C_i(k) · q_i(k) + d_i(k)) / C_i(k−1) − 1
  ```

- Alpaca `adjustment=all` is **not** used for signals or fills. It embeds corporate actions after `k`, which is
  lookahead (protocol v2 §3.4).

### 3.2 Benchmark

- `r_m(k)` = SPY total return on the same basis.
- **Limitations:**
  - SPY is not Sharia-screened; it is used only as a measurement benchmark.
  - Market adjustment assumes β = 1. Mega-cap tech β ≠ 1 is left in AR.
  - The sector effect is not removed (§1.1).
  - SPY contains the universe stocks, so the event stock itself affects the benchmark.

### 3.3 Candidate measures (compared; no performance used)

| Measure | Formula | Pros | Cons |
|---|---|---|---|
| Overnight gap | `O_i(s*)/C_i(s*−1) − 1` | earliest information; isolates the release | ignores first-session price discovery; open is not the auction print (`day17 …:76`) |
| First-session return (raw) | `C_i(s*)/C_i(s*−1) − 1` (TR basis) | includes discovery | includes market move |
| **First-session abnormal return** | `AR_i(s*) = r_i(s*) − r_m(s*)` | removes the market move; one session | β = 1 assumption |
| Multi-session CAR | `Σ_{k=s*}^{s*+w−1} AR_i(k)` | robust to a one-session timing error | delays entry; overlaps with "drift" |

### 3.4 Baseline (PROPOSED) and standardization

```
σ_i(e) = sample standard deviation of AR_i(k), k ∈ [s*−61, s*−2]    (60 sessions; excludes s*−1)
z(e)   = AR_i(s*) / σ_i(e)
```

- Requires 60 valid sessions with no `RESULTS` event of the same symbol inside the window. Otherwise the event is
  excluded and counted.
- **Why standardize:** a 3% move means different things for KO and TSLA. `z` is a ratio, so it needs no threshold
  calibration across symbols.
- **Trading eligibility (H2):** `z(e) ≥ z0`, where `z0` = 2 (PROPOSED, a priori). This is a conventional "unusual
  move" level under the stock's own recent volatility. **It is not selected from data.**
- Alternatives (separate future hypotheses, not run with the baseline): overnight gap only; 2-session CAR; β
  estimated over `[s*−250, s*−21]`; percentile of the symbol's own past event reactions.

---

## 4. Entry and exit

### 4.1 Timeline

```
T_rel → s* (reaction session) → close of s* : z(e) known → order before Open(s*+1) → fill at O_i(s*+1)
```

The decision uses information up to `Close(s*)`. The fill is the first price after the decision (protocol v2
§8.5 analogue: no same-bar fill).

### 4.2 Entry

- **Earliest entry:** `Open(s*+1)`.
- **Price assumption:** `E = O_i(s*+1)` (raw), plus per-side cost `s`.
- Market-on-open; no limit.
- **Skip conditions:**
  - no bar at `s*+1` (cancel; no retry);
  - symbol not eligible (screening, data);
  - `E ≤ S` (§4.4).

### 4.3 Holding period and exit

- `H` = 20 sessions (PROPOSED; about one month, well below the ≈63-session gap between quarterly reports).
- **Exit:** market-on-open at `O_i(s*+1+H)`.
- Descriptively, the drift path `CAR(s*+1 … s*+60)` is reported, but **H is fixed for the gate**.

### 4.4 Protective stop (defines R; PROPOSED)

```
S = C_i(s*−1)        (the raw close before the release: a full reversal of the reaction)
R_ps = E − S
```

- **Rationale:** if price returns to its pre-release level, this event's reaction has been fully reversed and the
  event hypothesis is void.
- The stop needs no free parameter.
- Splits between `s*−1` and the exit: `S ← S / q` on each ex-date.

### 4.5 Daily-bar exit algorithm (sessions `t > s*+1`, then the entry session)

```
if O_i(t) ≤ S         → exit at O_i(t)     (gap through stop: loss can exceed 1R)
elif L_i(t) ≤ S       → exit at S          (stop assumed filled at S; optimistic intraday)
elif t = s*+1+H       → exit at O_i(t)     (time exit)
```

- On the **entry session** `s*+1`: if `L_i(s*+1) ≤ S` → exit at `S`. The intrabar order is unknown, so this is
  conservative for the loss.
- A stop fill at `S` is **not guaranteed**. Additional stop slippage is a sensitivity parameter (§7.6).

### 4.6 Overlap and new events during a position

- **One position per symbol.** A new event for a symbol already held does not add a position.
- **A new Item 2.02 filing** (any class) for a held symbol whose `T_acc` falls during the holding period → exit at
  the first open after `T_acc` (`O_i(t)` with `t` = the first session whose open is after `T_acc`).
  - This exit price already contains the gap. It is **not avoidable** without PIT knowledge of announcement dates,
    which the project lacks.
  - Such exits are counted as `EVENT_COLLISION`.
- A new `RESULTS` event is still evaluated on its own (it can create a new position after the exit).

### 4.7 Corporate actions and dividends

- On the ex-date of a split: `shares ← shares · q`; `S ← S/q`; no P&L effect.
- On the ex-date of a cash dividend: `cash += shares(k−1 close) · d` (protocol v2 §11.2). The stop is not adjusted
  for dividends; dividend-gap stop hits are counted.
- Any other corporate action during a position (merger, spin-off) → **BLOCKING data review**. Never ignored.

---

## 5. Risk

**Approved assumption, kept unchanged:**
```
RiskBudget = InitialResearchCapital × 0.005
N = floor( RiskBudget / (E_plan − S) )
```
- `E_plan = C_i(s*)`, because the order is sized before the open.
- `N` is capped by available cash (no margin).
- `N = 0` → no trade.
- The capital basis stays **fixed initial capital**. OPEN-R1 is not decided here; equity-based sizing is reported
  only if the owner approves it.

**Why the realized loss can exceed the planned risk:**
1. **Overnight gaps** through `S` fill at the open (§4.5), not at `S`.
2. **Unscheduled or early Item 2.02 events** during the holding period (§4.6) arrive as gaps.
3. **Intraday stop fills** at `S` are optimistic on daily bars.
4. **Costs and slippage.**
5. `E_plan ≠ E`: the open differs from the planned price, so `R_ps` differs from the sizing assumption.

**Suitability of 0.5% (assessment, not a change):**
- The stop distance equals the reaction size, which is large for `z ≥ 2` events, so per-position notional is small
  (INF).
- The risk is **clustering**: events concentrate in earnings season, so many positions open in the same weeks,
  with correlated, market-driven gaps. Total open risk could reach `n_open × 0.5%` with correlated tails.
- **0.5% per trade is workable only together with a portfolio open-risk cap (OPEN-R2).** Without it, the simulation
  must be labelled "uncapped".
- Also report the realized `R` distribution, especially `R < −1`.

---

## 6. Data feasibility

Statuses: **AV** = AVAILABLE_AND_VERIFIED, **ANV** = AVAILABLE_BUT_NOT_VERIFIED, **NA** = NOT_AVAILABLE,
**NP** = REQUIRES_NEW_PROVIDER (or new source integration).

| Field | Status | Evidence / note |
|---|---|---|
| PIT ticker universe | **NA** | `day16 …:79-80`: the 25-symbol list is hindsight-selected and not PIT |
| Symbol → CIK map (PIT, incl. CIK changes) | NP | XOM precedent in the sources CSV; no map file |
| Earnings event (8-K Item 2.02, `T_acc`, accession) | **NP** for 2016–2025 | method precedent for 2026-07..09 (`config/earnings_calendar_sources.csv`); EDGAR terms [UNVERIFIED]; pagination beyond the "recent list" (U3) |
| Release timestamp `T_rel` | **NP + method UNRESOLVED** | U1, U2; §2.3 method must be adopted first |
| Event classification | NP (rule set to be written) | U5 |
| Daily OHLCV, raw, SIP | **AV** (endpoint and entitlement) | `artifacts/day17/day17-data-blockers.md` §4; a **fresh snapshot** is required (Stage R/H not usable) |
| Corporate actions | **AV** (endpoint) | `day17 …` §5; Stage R normalisation precedent (code reusable, data not) |
| Benchmark SPY daily + dividends | **AV** (endpoint) | 26/26 incl. SPY probed (`day17 …` §4) |
| Sector classification | NP (optional) | SIC via EDGAR `submissions` [UNVERIFIED]; not required for the baseline |
| Historical Sharia screening | **NA** | Akinda gives current verdicts only; research results are unscreened |
| Momentum control feature (prior 12-1 return) | derivable from daily bars | a feature only; V2-MOM itself is neither run nor modified |

---

## 7. Research protocol (draft)

### 7.1 Universe
- `FROZEN_DAY_UNIVERSE` (25). OPEN-SW1: a broader universe needs a PIT universe that does not exist.
- Survivorship and hindsight bias are disclosed. Results are never described as survivorship-safe.

### 7.2 Split (by event `s*` date; PROPOSED; OPEN-SW2)

| Segment | Events with `s*` in | Role | Label |
|---|---|---|---|
| Warmup | needs 60 prior sessions (§3.4) | σ estimation only | — |
| Development | 2016-04 … 2019-12-31 | build and check the pipeline; descriptive only | in-sample |
| Validation | 2020-01-02 … 2021-12-31 | first H1/H2 evaluation | in-sample |
| Historical test | 2022-01-03 … 2025-12-31 | one-shot | **pseudo-OOS, not blind**: dates overlap V2 Stage R/H periods; the authors know the market history |
| Forward confirmation | `s*` ≥ the first session after **both** the protocol freeze commit **and** the end of the research hold (not earlier than after the `fwd-gate2` evaluation) | the only confirmatory test | true OOS |

- The 2026-01-02 … hold-lift period is **excluded** from historical research. It is close to protected forward
  periods.
- Data snapshots are **fresh** and write-once; Stage R and Stage H files are never read.
- Whether fresh data may cover Stage H **dates** is OPEN-SW2.

### 7.3 Leakage prevention
1. The event table (§2) is built and frozen with a hash before any price is loaded.
2. All features use data ≤ `Close(s*)`. `σ` excludes `s*−1` and `s*`.
3. PIT total-return series (§3.1); no `adjustment=all`.
4. Future-mutation test: changing any bar after `Close(s*)` must not change `z(e)`, eligibility or `N`.
5. Parameters (`z0`, `H`, stop rule, costs) are frozen in a committed config before validation data is read.
6. Segments are evaluated in order; the historical test runs once.

### 7.4 Overlapping events (statistics)
- Events cluster in earnings season, so returns are cross-sectionally correlated.
- Standard errors are **clustered by calendar week of `s*`**, or a **block bootstrap by quarter**.
- Per-symbol events are at least about a quarter apart, so own-symbol overlap is limited by `H` < 63.

### 7.5 Minimum sample size (method)

```
n_min = ((z_{1−α} + z_{1−β}) · σ_D / δ)²
```

- Inputs:
  - `σ_D` = standard deviation of the event-level net drift, estimated **on development only**;
  - `δ` = smallest drift worth trading;
  - `α` = 0.05 one-sided; power `1 − β` = 0.8 (conventional, PROPOSED).
- `δ` must exceed the round-trip cost `2s` (0.10% at 5 bps per side) by an owner-set margin (OPEN-SW3).
- Scale (INF, no data): 25 symbols × 4 events × years gives at most ≈ 100 events per year, and the `z ≥ 2` subset
  is a fraction of that. **H2 will likely be underpowered**, so H1 (all events, slope) is the primary test.
- If `n < n_min`, the result is **INCONCLUSIVE**, never PASS.

### 7.6 Metrics

**Primary:**
- **P1 (H1):** slope `β₁` in `D(e) = β₀ + β₁·z(e) + ε` over all eligible events, where
  `D(e) = Σ_{k=s*+1}^{s*+H} AR_i(k)` is the drift from entry to exit, excluding the reaction session.
  Clustered standard errors.
- **P2 (H2):** mean net drift for `z ≥ z0` events at 5 bps per side.

**Secondary:**
- `β₁` with prior 12-1 momentum added as a control (`D = β₀ + β₁ z + β₂ MOM + ε`);
- CAR path 1..60 sessions;
- hit rate;
- realized trade `R` distribution and `R < −1` count;
- `EVENT_COLLISION` and gap-stop counts;
- per-year and per-symbol breakdown;
- top-symbol share of P&L;
- simulated equity (fixed capital), max drawdown, open-risk profile by week;
- exclusion counts by reason (UNRESOLVED, INTRA, OTHER_2_02, insufficient σ window, missing bars).

**Costs:**
- 0 / 5 / 10 bps per side (project convention; 5 = primary, 10 = stress).
- Stop-fill extra slippage sensitivity: {0, 10, 25} bps (PROPOSED, reporting only).

**Sensitivity (reported, never used to select):**
- `z0` ∈ {1, 2, 3};
- `H` ∈ {10, 20, 40};
- with and without UNRESOLVED events (two-session CAR);
- β-adjusted AR.

### 7.7 Rejection criteria (structure; thresholds PROPOSED)

| Result | Condition |
|---|---|
| **REJECT** | validation or historical test: `β₁ ≤ 0`, or P2 ≤ 0 at 5 bps |
| **REJECT (momentum relabel)** | `β₁` loses significance once MOM is added and `β₂` carries the effect |
| **INCONCLUSIVE** | `n < n_min`, or the confidence interval includes 0 |
| **RESEARCH-PASSED (historical)** | `β₁ > 0` with a one-sided 95% clustered CI above 0, **and** P2 > 0 at 5 bps, **and** P2 ≥ 0 at 10 bps |
| **FORWARD** | the same tests, predeclared, on forward events only; the only path to "confirmed" |

A failed variant is not re-parameterized.

---

## 8. Sharia review

| Topic | Status |
|---|---|
| Long-only, cash-funded, no margin, no shorting, no derivatives | by design; order path must refuse anything else (D15 PROVISIONAL) |
| Stock screening | Akinda `/compliance` (D13-A); registry header-only today, so nothing is tradable; quota 10 a day; licence check before committing rows. Historical PIT screening impossible, so research is unscreened |
| Ownership and qabd | positions are held for weeks, well past T+1 settlement. D12 (day trading) does **not** apply. Whether ownership transfers with the broker's custody model is a D15 broker-checklist item |
| Settlement | cash account; no reuse of unsettled proceeds (broker rule NOT VERIFIED) |
| Dividend purification | positions may span ex-dates. **D10 ADVISER_REQUIRED.** The ledger must keep ex-date, shares and amount; no purification amount is computed |
| Status change during a position | D2 (PROVISIONAL): exit at the next session. **Multi-day exit logic does not exist yet** and is required before paper or live use |
| Earnings-related trading | trading on a **public** release after it is public; no non-public information. INF: no specific adviser question identified, but the adviser should confirm that event-driven multi-week holding raises no issue (OPEN-SH) |
| Live use | **BLOCKED_FOR_LIVE_USE** until screening rows, D2 exit logic, the D15 checklist and the D10 ruling exist |

The strategy is **not** labelled halal.

---

## 9. Open owner decisions

| ID | Decision |
|---|---|
| OPS-1 | **Three** untracked docs now exist (this file plus the D1/S1 design and the discovery report). `stage_f.py:322-323` refuses `fwd-gate2` capture with any untracked file. Resolve before 2026-12-09 16:15 ET |
| SW-0 | Approve SW-A as the swing research priority (or not) |
| SW-T | Adopt the §2.3 `T_rel` verification method and `Δ_max`; write down what `VERIFIED` means (U2). This applies retroactively to the 2026 file's semantics too |
| SW-C | Adopt the event classification rule set (U5) |
| SW-D | After the hold: authorize EDGAR access (terms verified first) and a fresh daily SIP + corporate-action snapshot |
| SW1 | Universe: 25 frozen vs. broader |
| SW2 | Data period: may fresh data cover Stage R/H **dates**? Confirm the split in §7.2 |
| SW3 | `δ` (minimum economically meaningful drift) and acceptance thresholds |
| SW4 | `z0`, `H`, stop rule (PROPOSED values) |
| R1/R2 | Capital basis (kept as fixed initial) and a portfolio open-risk cap (needed for this event-clustered setup) |
| SH | Adviser: D10 purification; confirmation on event-driven holding |

---

## 10. Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | SEC timestamp semantics verified or marked unresolved | PASS: U1–U5 marked UNRESOLVED; `T_acc ≠ T_rel` |
| 2 | Deterministic event definition | PASS: §2 (given frozen rules and evidence) |
| 3 | Reaction defined mathematically | PASS: §3.4 |
| 4 | Reproducible entry and exit | PASS: §4 |
| 5 | Explicit data requirements | PASS: §6 |
| 6 | Split protects against known historical bias | PASS: §7.2 (pseudo-OOS labelled; forward-only confirmation) |
| 7 | Explicit risk and gap exposure | PASS: §5, §4.5–4.6 |
| 8 | Sharia questions documented | PASS: §8 |
| 9 | No profitability claim | PASS |
| 10 | No data-dependent work | PASS: §11 |

## 11. Safety confirmation

- No API call, network access, data acquisition, backtest, optimization or implementation.
- Stage R and Stage H files, `fwd-gate2` results, sealed P001 and `paper_state/` were not accessed.
- No existing document or code was modified. The only file written is this draft. It is untracked; no commit or
  push.
