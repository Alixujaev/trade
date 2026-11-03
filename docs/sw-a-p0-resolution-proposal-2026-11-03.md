# SW-A: P0 resolution proposal (2026-11-03)

> **Status: PROPOSAL — OWNER DECISIONS REQUIRED — NOT APPROVED FOR EXECUTION.**
> - Design only. Nothing in this document is adopted. Every "recommended default" is a proposal, and the owner may
>   accept, change or reject it.
> - No code, config, existing document or protocol was changed.
> - No API call, network access, data acquisition, test, backtest or optimization was run.
> - Stage R and Stage H data, `paper_state/`, sealed P001 and `fwd-gate2` results were not opened.
>
> **No claim is made that SW-A is profitable.** The aim is to make the hypothesis cleanly falsifiable.

**Inputs:**
- `docs/sw-a-research-design-2026-11-02.md`, called "the draft" (committed in `80e94ad`);
- `docs/sw-a-decision-gap-audit-2026-11-03.md`, called "the audit" (untracked at the time of writing);
- `docs/strategy-discovery-report-2026-11-02.md`;
- protocol documents listed in §0.2.

**Labels:**
- **FACT**: read from a cited repository file.
- **INF**: an inference.
- **ASSUMPTION**: assumed, not verified.
- **LIT [UNVERIFIED]**: literature from memory, not checked.
- **PROPOSED**: a recommendation that has not been approved.

---

## 0. Scope and evidence

### 0.1 The P0 set, read from the audit

The audit's §10 table, rows marked `P0` (FACT, audit lines 949–959), contains exactly these 11 items:

| # | ID | Audit wording (verbatim) | Audit section |
|---|---|---|---|
| 1 | GV2 | "Approve SW-A as the swing priority" | §9 GV2 |
| 2 | S2 | "Drift window ≠ traded window" | §4 S2 |
| 3 | S4 | "H2 estimand and non-event baseline" | §4 S4 |
| 4 | S7 | "Acceptance logic: P2 interval, `δ`, momentum rule, precedence, sequencing" | §4 S7 |
| 5 | X1 | "Exit-order defect on the time-exit day" | §5 X1 |
| 6 | X2 | "Entry-session stop → same-day round trips" | §5 X2 |
| 7 | X3 | "Raw stop on a market-adjusted signal" | §5 X3 |
| 8 | T1 | "Definition of `VERIFIED`" | §2 T1 |
| 9 | T2 | "Evidence tiers and precedence" | §2 T2 |
| 10 | U6 | "Forward-data rule that binds SW-A" | §6 U6 |
| 11 | GV3 | "SW-A protocol home, freeze and registry" | §9 GV3 |

The task brief also asks about **S5, S6 and GV4**. The audit rates these **P1**, not P0. They are covered in §3
because S7 and T1 cannot be specified without them. They keep their P1 rating.

### 0.2 Documents read for this proposal (beyond the audit's own evidence list)

| File | What it settles |
|---|---|
| `artifacts/day26b/protocol-v2.1-amendment.md` (status, §1, §6) | ADOPTED 2026-10-10T12:52:51Z. It replaces the DAY-22 252-session window with a 63-session window (2026-10-08 → 2027-01-07). Its §6 has the acquire/compute/inspect table |
| `artifacts/day26d/protocol-v2.2-amendment.md` (status, §1–§6) | ADOPTED 2026-10-10T14:56:30Z. The old `fwd-gate` is "SUPERSEDED (protocol 2.2) — never acquired or evaluated". `fwd-gate2` covers 42 sessions, 2026-10-12 → 2026-12-09, with earliest capture 2026-12-09 16:15 ET. The preflight checks "a clean tree, the protocol identity" (§6) |
| `artifacts/day27/protocol-v2.3-amendment.md` (status, header table) | P001 is sealed until 2026-12-09 16:15 ET. The experiment "continues indefinitely" |
| `artifacts/day27a/protocol-v2.4-amendment.md`, `artifacts/day27b/protocol-v2.5-amendment.md` (headers) | v2.4 (FB→META alias) is ADOPTED. v2.5 is DRAFT — NOT ADOPTED. Neither changes forward windows |
| `acquisition/v2/contract.py` lines 59–122 (constants only, via grep) | `:112 FORWARD_WINDOW = (2026-10-08, 2027-01-07, 63)`; `:118` comment "superseded; a new clean 42-session gate"; `:120 fwd-gate2 = (2026-10-12, 2026-12-09, 42)`; `:122 EXPOSED_SESSIONS = (2026-10-08, 2026-10-09)`; `:72 STAGE_H_ASOF = "2026-10-07"` |

Not opened: `artifacts/day26c` (the forward-data incident record), every Stage R, H and F directory, run
outputs, `paper_state/`, and P001.

**Correction to the audit (no edit made to it).** The audit's U6 treated the DAY-22 §3.2.3 252-session rule as
possibly binding until 2027-10-08. It was replaced by the adopted v2.1 amendment. v2.1 line 4: "from 2026-10-08
until then, the 252-session rules … governed". The 63-session `fwd-gate` was then superseded by v2.2. §2.10
uses the corrected picture.

---

## 1. Executive summary

1. **All 11 P0 items have a proposed resolution (§2).** None is adopted. Two are corrections with no real
   alternative: X1, and the ordering part of X2. The other nine are genuine owner choices.
2. **The statistical estimands and the trading estimands are now separate:**
   - **Statistical:** H1 and H2 are fixed-horizon, stop-free, open-to-open abnormal returns over exactly the
     traded window (S2, S4). They are the gated hypotheses.
   - **Trading:** the simulation with stops, sizing, caps and collisions (X1–X3). It is reported, and it must
     pass one consistency condition (S7 step 7). It is not the hypothesis test.
3. **S2:** H1 moves to the traded window `[O(s*+1), O(s*+1+H)]`. The overnight return between the signal close
   and the entry open is reported separately and never counted as drift.
4. **S4:** H2 is defined as the net-of-cost open-to-open abnormal drift of `z ≥ z0` events **minus a
   symbol-matched non-event baseline**. This guards against the hindsight-universe effect.
5. **X3:** the stop is moved onto the same abnormal-return basis as the signal:
   `S = C(s*) − (C(s*−1)/q(s*)) · AR(s*)`. The stop distance then equals the abnormal reaction, which is always
   positive for eligible events. The size becomes about `0.5% / AR(s*)` of capital and no longer depends on the
   market's direction on the reaction day.
6. **X1 and X2:**
   - The scheduled exit at the open takes precedence over the intraday-low check.
   - No exit of any kind happens on the entry session. A breach on the entry session is executed at the next
     open.
   - This removes same-session round trips by construction. It does **not** settle D12 for sales on the
     session after entry; that question goes to the adviser.
7. **S7 (with S5 and S6):** the proposal sets out:
   - one primary inference method: a circular block bootstrap over calendar sessions with block length
     `2(H+1)`, fixed before data;
   - an explicit, ordered decision ladder (methodological fail → power → sign → momentum → cost → interval and
     `δ` → trading consistency → PASS);
   - an operational momentum-relabel test;
   - a power check that is completed **before** outcome statistics are computed.
8. **Power warning (ASSUMPTION-based arithmetic only, §2.4):** if the 20-session abnormal-drift dispersion is
   about 6%, detecting `δ = 1%` needs about 220 effective events in the `z ≥ z0` subset. The 2-year validation
   segment holds at most about 200 events of **all** reactions. With any small `δ`, INCONCLUSIVE is the likely
   outcome unless the owner chooses a design option in S6.
9. **T1, T2 and GV4:** a new, SW-A-only vocabulary (`SWA_VERIFIED` / `SWA_UNRESOLVED`) is proposed, with:
   - tiered evidence (exhibit > IR page > newswire);
   - "precedence fills absence but never overrides a contradiction";
   - `T_acc` used as a bound only.

   The 2026 calendar files are never modified or reinterpreted. FACT: their coverage (2026-07-02 → 2026-09-25)
   lies inside SW-A's excluded period anyway.
10. **U6:** the DAY-22 conflict is resolved by the adopted amendments. The remaining choice is the boundary for
    SW-A forward data. The recommendation is the fail-closed one: no SW-A data dated on or after 2026-10-08 is
    used before **2027-01-07 16:15 ET**, the end of the last forward window still present in code. Its expected
    cost is small (INF). Separately, a standing rule bars SW-A from data inside any PENDING V2 blind segment,
    because SW-A uses the same 25 symbols plus SPY.
11. **GV2 and GV3:** approve SW-A for **design completion only**. Host it in a **standalone SW-A protocol**, not
    in a protocol v2 amendment: the `fwd-gate2` preflight checks the v2 protocol identity (FACT, v2.2 §6).

---

## 2. P0 items

### 2.0 Shared notation (PROPOSED)

| Symbol | Meaning |
|---|---|
| `s*` | first reaction session (draft §2.4) |
| `e = s*+1` | entry session; entry fill at `O_i(e)` |
| `x = s*+1+H` | scheduled exit session; exit fill at `O_i(x)`. `H` = 20 (draft, PROPOSED, SW4) |
| `O, L, C` | raw open, low, close (protocol v2 series A) |
| `q_i(k)`, `d_i(k)` | split ratio and cash dividend with ex-date `k`, effective before the open of `k` (protocol v2 §3.3) |
| `r_i(k)`, `AR_i(k)`, `σ_i(e)`, `z(e)` | as in draft §3.1–§3.4 (close-to-close total-return basis; `AR = r_i − r_SPY`) |
| `Q_i(a,b)` | product of `q_i` over ex-dates in `(a, b]` |
| `D_i(a,b)` | Σ over ex-dates `u ∈ (a,b]` of `d_i(u) · Π_{ex-dates v ∈ (u,b]} q_i(v)` (dividend cash in end-of-window share units, as in protocol v2 §3.4) |
| `R^oo_i(a,b)` | open-to-open total return `= (O_i(b)·Q_i(a,b) + D_i(a,b)) / O_i(a) − 1` |
| `AR^oo_i(a,b)` | `R^oo_i(a,b) − R^oo_SPY(a,b)` (β = 1, as in the draft) |
| `κ(s)` | net round-trip factor `(1 − s)/(1 + s)`, with `s` the per-side cost |

`R^oo` is **NOT YET IMPLEMENTED**. It needs the same truncation and future-mutation tests as protocol v2 §7.

---

### 2.1 GV2: approve SW-A as the swing priority

- **Issue (audit §9 GV2):** "SW-A is not yet approved as the swing priority" (SW-0, OD-3).
- **Effect:** every other decision in this document is only worth making if SW-A goes ahead.
- **Alternatives:**
  - (a) approve SW-A for **design completion only**: decide the P0 and P1 items and draft the protocol, with no
    data or EDGAR access;
  - (b) approve SW-A fully, including data acquisition once GV1 and U6 allow it;
  - (c) prioritize S1 instead (discovery report OD-3, OD-7);
  - (d) park all new swing research until after the `fwd-gate2` evaluation.
- **Recommended default: (a).**
  - Design work does not touch data. It is consistent with the research-hold recommendation (evidence inventory
    §10) and with the D1/S1 position that the hold restricts acquisition and runs.
  - Data authorization stays a separate decision (GV1, U6).
- **Assumptions and unresolved evidence:** OPEN-G2 (the research hold) is undecided. The discovery report's
  recommendation for SW-A rests on mechanism and data feasibility, not on evidence of an edge.
- **Owner approval:** required (choice).
- **Downstream:** all other items.

---

### 2.2 S2: align the H1 drift with the traded window

- **Issue (audit §4 S2):**
  - "P1 defines `D(e) = Σ_{k=s*+1}^{s*+H} AR_i(k)`, which runs close-to-close from `Close(s*)` to
    `Close(s*+H)`."
  - "The trade runs from `O(s*+1)` to `O(s*+1+H)`."
  - So `D(e)` includes the overnight `C(s*) → O(s*+1)` move, which cannot be traded, and excludes the final
    overnight move, which the trade bears.
- **Effect on the estimand:**
  - The draft's H1 measures drift from the decision close, not from the earliest fill.
  - LIT [UNVERIFIED]: fast information processing would concentrate any continuation in the first overnight
    period.
  - P1 could therefore pass on a component no market-on-open order can earn.
- **Alternatives:**
  - (a) keep the close-based `D^cc` for H1 and label it an information estimand (the audit's earlier default);
  - (b) **move H1 to the traded window**: `D(e) := AR^oo_i(e, x)`, gross;
  - (c) gate on both (a) and (b);
  - (d) a multi-session close-based CAR starting at `C(s*+1)`. It is still misaligned with the fill.
- **Recommended default: (b), with a reported decomposition.**
  - H1 primary statistic: the slope `β₁` in `D(e) = β₀ + β₁ z(e) + ε`, where `D(e) = AR^oo_i(e, x)`, with no
    stops and no costs. A constant cost does not change a slope.
  - Report, never gate:
    - the overnight abnormal return `G(e) = [O_i(e)·q_i(e) + d_i(e)] / C_i(s*) − [same for SPY]`;
    - the close-based `D^cc(e)` from the draft.

    These are not claimed to add up to `D(e)`, because returns compound.
  - Reasoning: SW-A is a trading hypothesis. A statistical estimand whose window is the traded window ties the
    "does drift exist" question to the only window that can be monetized. It also errs on the conservative side.
  - **This replaces the audit's earlier default (a), following the task brief's direction to align H1.** The
    owner may still choose (a) or (c).
- **Assumptions and unresolved evidence:**
  - The SIP daily `open` is the first eligible trade, not necessarily the auction print (FACT, day17 §3). This
    adds noise to both ends of `D(e)`.
  - The H sensitivity values {10, 40} are applied with the same window construction.
- **Owner approval:** required (choice).
- **Downstream:** S4 (same window), S5 and S6 (the variance of `D`), S7, the momentum test (same `D`), S3 (H1
  sample, P1), and the draft's descriptive CAR path (which should be labelled close-based if kept).

---

### 2.3 S4: H2 estimand and the non-event baseline

- **Issue (audit §4 S4):**
  - P2 is "mean net drift for `z ≥ z0` events at 5 bps", and that quantity is undefined.
  - "On this universe a positive long-only mean is expected without any event effect" (protocol v2 §13.B
    rationale, §2).
- **Effect on the estimand:** without a baseline, H2 can pass because these 25 surviving names outperformed
  SPY in general, not because of earnings news.

#### 2.3.1 Statistical estimand (gated)

```
E+        = { e : z(e) ≥ z0, bars exist at e and x, no other Item 2.02 filing of i with T_acc in (Close(s*), Open(x)) }
D_net(e)  = [ (1 + R^oo_i(e,x)) · κ(s) − 1 ] − R^oo_SPY(e,x)            (net abnormal drift, traded window, no stop)
P_i       = placebo entry sessions p for symbol i in the same segment such that:
              • no Item 2.02 event of i has s*' in [p − H − 2, p + H]      (not inside or just after a prior event's drift window,
                                                                            and no event inside the placebo window)
              • bars exist at p and p + H
D_P(p)    = R^oo_i(p, p+H) − R^oo_SPY(p, p+H)                           (gross; the cost is charged once, on the event side)
μ_P       = Σ_i w_i · mean_{p ∈ P_i} D_P(p),   w_i = (#events of i in E+) / |E+|     (symbol-matched baseline)
Δ₂        = mean_{e ∈ E+} D_net(e) − μ_P                                  (the H2 estimand, at s = 5 bps; also at 10 bps)
```

- **Interpretation:** after a large positive abnormal reaction, Δ₂ is the abnormal return over the traded window
  after the 5 bps round trip, in excess of what the **same stocks** earned in abnormal terms over non-event
  windows of the same length.
- **Collision exclusion:** the condition excluding another Item 2.02 filing inside the window applies to events
  and placebo windows alike. It uses event-table information after `s*`, so it is a measurement filter, not a
  trading rule. The trading estimand (§2.3.2) handles collisions as forced exits instead. Excluded events are
  counted.
- **Alternatives:**
  - (a) no baseline, as drafted;
  - (b) an unmatched pooled placebo;
  - (c) **a symbol-matched placebo (recommended)**;
  - (d) a symbol × year-matched placebo. It would be more precise, but the cells are small;
  - (e) a within-event contrast (high `z` against low `z`). That is essentially H1 and adds nothing new;
  - (f) the audit's earlier default: per-trade returns **with stops** relative to the placebo.
- **Why (c) and not (f):**
  - The stop is defined by the reaction (X3), and a placebo window has no reaction. Stops cannot be applied
    symmetrically to both sides.
  - A stop-path estimand also depends on the optimistic intraday-fill assumption (draft §4.5).
  - Stops therefore belong to the trading estimand.
  - **This refines the audit's S4 default.**

#### 2.3.2 Trading estimands (simulation; reported, plus one consistency condition)

| ID | Definition |
|---|---|
| TE1 | per-trade net return under the X1–X3 rules (raw fills, cash dividends, 5 bps), minus SPY's total return over the **actual** holding interval of that trade |
| TE2 | realized `R` = trade P&L / planned risk `N·(E_plan − S)`; its distribution; the count of trades with `R < −1` |
| TE3 | fixed-capital portfolio simulation (`E_0` per X9, P1). Net total return, max drawdown, exposure. Compared with SPY buy-and-hold, an **exposure-matched SPY** (the daily invested fraction × SPY return) and B1 (equal-weight 25) |

- TE1–TE3 are not hypothesis tests. S7 step 7 uses only the sign of the mean of TE1.
- **Assumptions and unresolved evidence:**
  - β = 1 (S1, P1).
  - The placebo exclusion distance `H + 2` before the window is ASSUMPTION. It keeps a placebo window from
    starting inside the previous event's holding window (`H + 1` sessions) or its reaction session.
  - The placebo count per symbol can be computed from the event table before prices are read.
- **Owner approval:** required (choice).
- **Downstream:** S5 (Δ₂ needs an inference method that handles overlapping placebo windows), S6 (`σ` of
  `D_net`), S7, U2 (the survivorship control is met through this baseline), X9 and R1 (TE3 accounting).

---

### 2.4 S7: acceptance and rejection logic (with P1 items S5 and S6)

- **Issue (audit §4 S7):**
  - "P2 has no interval requirement";
  - "`δ` is not in the acceptance rule";
  - the momentum-relabel rejection is undefined;
  - "Precedence is unstated";
  - "Sequencing is unstated";
  - "the segment requirement is unclear".
- **Effect:** an incomplete rule leaves room to read the result after it is known.

#### 2.4.1 Inference method (S5, P1): proposed primary

- **Dependence structure (INF):**
  - Two events, or two placebo windows, share calendar sessions only if their entry sessions are within `H`
    sessions of each other.
  - If daily ARs are serially uncorrelated, events whose windows share no session share no daily shock.
  - Weekly clustering (as drafted) treats overlapping windows in adjacent weeks as independent.
- **Primary (PROPOSED):** a **circular block bootstrap over the XNYS sessions of the evaluated segment.**
  - Block length `L = 2(H+1)` sessions, which is 42 for `H = 20`.
  - `B = 10,000` replicates, with a seed fixed in the frozen config. This is a recorded seed; protocol v2's "no
    seeds" assertion does not apply to SW-A.
  - Each event and each placebo window is assigned to the block that contains its entry session.
  - Every statistic (β₁, Δ₂, the momentum model) is recomputed on each replicate.
  - Intervals: percentile, one-sided 95% lower bound `LB(·)`.
- **Reported, never gating:**
  - `L ∈ {H+1, 63}`;
  - week-clustered standard errors with a small-sample correction;
  - earnings-season-clustered `t` with `G − 1` degrees of freedom;
  - a calendar-time portfolio mean with Newey–West at lag `H`. LIT [UNVERIFIED]: a standard long-horizon
    event-study method.
- **Limitation (disclosed in advance):** a 2-year validation segment has about 504 sessions, so only about 12
  blocks. LIT [UNVERIFIED]: bootstrap intervals with few blocks can undercover. This is a reason for caution in
  reading a PASS. It is not a reason to change the method after results.

#### 2.4.2 Power and `n_min` (S6, P1): proposed method

- **Estimated on development data only, and committed before any validation price is read:**
  - `σ_D` = the standard deviation of `D_net(e)` over the development `E+`;
  - `σ_u` = the residual standard deviation of the H1 regression;
  - `sd_z` = the standard deviation of `z`;
  - `DEFF` = the bootstrap variance of the mean divided by the naive variance `σ²/n`.
- **Formulas:**
  - H2: `n_min,2 = DEFF · ((z_{0.95} + z_{0.80}) · σ_D / δ)²`.
  - H1: `n_min,1 = DEFF · ((z_{0.95} + z_{0.80}) · σ_u / (sd_z · δ_β))²`, with `δ_β = δ / z0`. This is the slope
    at which the drift predicted at the threshold `z0` equals `δ`.
- **The power check runs before outcomes.** Event counts `|E+|` and the number of all-eligible events are fixed
  by the event table and the pre-event σ windows. They are recorded, and the power verdict is committed, before
  any `D` value of the segment is computed. This step reads entry and exit-window prices only to confirm that
  bars exist.
- **Illustration (ASSUMPTION ONLY, not estimates, no data used).** With `z_{0.95} + z_{0.80} ≈ 2.487` and
  `DEFF = 1`, the effective `n_min,2` is:

  | assumed `σ_D` | `δ` = 0.5% | `δ` = 1% | `δ` = 2% |
  |---|---|---|---|
  | 4% | ≈ 396 | ≈ 99 | ≈ 25 |
  | 6% | ≈ 891 | ≈ 223 | ≈ 56 |
  | 8% | ≈ 1,583 | ≈ 396 | ≈ 99 |

  - The upper bound on available events is about 200 in validation and about 400 in the historical test (INF;
    audit S6). That counts **all** reactions, before exclusions.
  - `E+` is a subset of that.
  - Unless `σ_D` is small or `δ` is large, **H2 will be INCONCLUSIVE.** The owner should decide this knowingly,
    before data (S6 options: accept it; pool validation and the historical test; wait for forward events).

#### 2.4.3 `δ`: definition and placement

- **Definition (PROPOSED):** `δ` is the smallest **net, baseline-differenced** abnormal drift per event over the
  traded window (Δ₂ at 5 bps) that the owner regards as worth trading.
- **Placement:** `δ` enters both the power check and acceptance (step 6 below).
- **Floor (arithmetic, not a recommendation of a value):** the 10 bps condition (step 5) is
  `Δ₂(10 bps) ≥ 0`, which is approximately `Δ₂(5 bps) ≥ 0.10%`. A `δ` above 0.10% makes that condition
  redundant at the point estimate.
- **Value:** **no default is proposed.** It is owner-set (SW3) and must be fixed before any price is read.

#### 2.4.4 Operational momentum-relabel test

- `MOM(e) = TR_i(s*−22) / TR_i(s*−253) − 1`. This is the prior 12-1 return measured at `s*−1`, so it excludes the
  reaction session.
- The controlled model is `D(e) = β₀ + β₁ᴹ z(e) + β₂ MOM(e) + ε`, on the same sample and inference as H1.
- **The relabel condition holds iff all three hold:**
  - `LB(β₁) > 0` in the uncontrolled H1 model;
  - `LB(β₁ᴹ) ≤ 0`;
  - the two-sided 95% bootstrap interval of `β₂` excludes 0.
- **Availability:** `MOM` needs about 253 prior sessions, so it is undefined for events before about 2017-01
  (audit S10). It is available for validation (2020 onward) and the historical test.
- A momentum control for H2 is reported (Δ₂ recomputed within MOM terciles of `E+`), but it is not gated.
  Terciles of a small `E+` are too thin to gate on.

#### 2.4.5 Decision ladder (per gated segment; first matching row wins)

| Step | Condition | Outcome |
|---|---|---|
| 1 | Any hard fail: look-ahead tests (future-mutation, truncation, fill-source, `R^oo` index), data or structural failure, unresolved BLOCKING review, non-determinism, incomplete reproducibility block | `FAILED (methodological)`. No statistics are interpreted |
| 2 | Power check (pre-outcome, §2.4.2): `n_eff,1 < n_min,1` **or** `n_eff,2 < n_min,2` | `INCONCLUSIVE (underpowered)` |
| 3 | `β̂₁ ≤ 0` **or** `Δ̂₂(5 bps) ≤ 0` | `REJECT (sign)` |
| 4 | Momentum-relabel condition (§2.4.4) | `REJECT (momentum relabel)` |
| 5 | `Δ̂₂(10 bps) < 0` | `REJECT (cost-fragile)` |
| 6 | `LB(β₁) ≤ 0` **or** `LB(Δ₂) ≤ 0` | `INCONCLUSIVE (interval includes 0)` |
| 6b | `Δ̂₂(5 bps) < δ` | `FAILED (economically immaterial)` |
| 7 | Mean TE1 at 5 bps ≤ 0 (trading consistency: stops and sizing must not reverse the sign) | `FAILED (trading)` |
| 8 | otherwise | `PASS` for that segment |

- **Why power comes first (step 2 before step 3):**
  - A sign reversal in an underpowered sample is weak evidence against the hypothesis. Labelling it REJECT
    would overstate it.
  - Both labels stop progression.
  - Neither permits re-testing on the same data.
  - Because step 2 is decided before outcomes are computed, its label cannot be chosen after seeing them.
- **Alternative:** REJECT before INCONCLUSIVE, as the draft's ordering implies. It is stricter in name, but
  identical in consequence.
- **The δ test (step 6b) uses the point estimate together with a significant LB > 0** (audit option "LB > 0 and
  point estimate ≥ δ"). The stricter alternative `LB(Δ₂) > δ` is listed for the owner. Under the power
  arithmetic above it would almost never pass.

#### 2.4.6 Sequencing and segment requirements

```
Development (descriptive; computes σ_D, σ_u, sd_z, DEFF, n_min; commits them)  →
Validation gate (ladder)  ──PASS──▶  Historical-test gate (ladder, one-shot)  ──PASS──▶  RESEARCH-PASSED (historical, pseudo-OOS)
                                                                                         ──▶ Forward gate (same ladder, §2.10 dates) ──PASS──▶ FORWARD-PASSED
```

- Any non-PASS outcome **stops** the sequence. A segment is never re-run under a changed rule. INCONCLUSIVE can
  only be revisited with **new** forward events, under the same frozen rules.
- `RESEARCH-PASSED (historical)` requires PASS in **both** validation and the historical test.
- Optional label (owner choice; **recommended not to adopt**): "H1-SUPPORTED / H2-INCONCLUSIVE — not trading
  evidence". It would report a pass of the information hypothesis without advancing. It is not recommended
  because it invites being read as a partial pass.
- Multiple testing (S8, P1): PASS requires every condition at once (an intersection-union structure), so false
  passes are not inflated within SW-A (INF). A project-level trial count is disclosed.

- **Assumptions and unresolved evidence:** the bootstrap's few-block behaviour; the asymptotic normal
  approximation in the `n_min` formulas; the `MOM` definition (an analogue of V2-MOM's lookback, PROPOSED).
- **Owner approval:** required (choice) for S7, and for S5 and S6 as P1 items. The `δ` value is required from
  the owner (SW3).
- **Downstream:** the protocol gate section (GV3), the forward gate (U6), the run order (power check before
  outcomes), and the reporting templates.

---

### 2.5 X1: correct the ordering of the stop and the scheduled exit

- **Issue (audit §5 X1):** "§4.5 evaluates `O(t) ≤ S` → `L(t) ≤ S` → `t = s*+1+H`, in that order. On the
  time-exit session the position is closed at `O(t)`. A later intraday low is irrelevant, yet the algorithm can
  record a stop fill at `S` instead."
- **Effect:** the trading estimands TE1–TE3 overstate losses and miscount stop exits on exit days. Statistical
  estimands are unaffected, because they are stop-free.
- **Alternatives:** none of substance. This is a correction. The only freedom is how to label coinciding
  triggers.
- **Recommended corrected algorithm (PROPOSED text; it also includes the X2 default):**

  ```
  t = e (entry session):   buy at O_i(e) (market-on-open, always filled if a bar exists)
                           no exit of any kind is executed at a price of session e (X2)
                           if L_i(e) ≤ S (this includes O_i(e) ≤ S), or a forced-exit trigger occurs during e
                             → flag PENDING_EXIT

  for t = e+1, …, x:
     0. if t has no bar → carry any due exit as a pending sell to the next session with a bar (protocol v2 §8.6; X4, P1)
     1. apply corporate actions with ex-date t (split: shares·q, S ← S/q; dividend: cash)
     2. if PENDING_EXIT or a forced exit is due (collision, D2 status change) → exit at O_i(t)
     3. elif t = x                       → exit at O_i(t)            (time exit; label GAP_AT_EXIT if O_i(t) ≤ S)
     4. elif O_i(t) ≤ S                  → exit at O_i(t)            (gap through stop)
     5. elif L_i(t) ≤ S                  → exit at S · (1 − slip)    (intraday stop; slip ∈ {0, 10, 25} bps, report-only)
     6. else hold
  ```

  - **Precedence for labelling** when several triggers coincide: forced > time > gap > intraday. The fill price
    is `O_i(t)` for every open-based exit, so the label changes no number.
  - There is no low check on session `x`.
  - **A further correction:** the draft's entry skip "`E ≤ S`" (§4.2) cancels a market-on-open order based on
    the price at which it would fill. That is not executable: a buy order cannot be conditioned on its own
    opening print being above a level.
    - The proposed text fills the order and treats `O_i(e) ≤ S` as an entry-session breach, so the exit is at
      `O_i(e+1)`.
    - Such trades are counted as `GAP_AT_ENTRY`.
    - The alternative is to keep the draft's skip, labelled non-executable, as a sensitivity run only.
- **Assumptions and unresolved evidence:** an intraday stop fill at `S` is optimistic on daily bars (draft
  §4.5). The intrabar order of events is unknown.
- **Owner approval:** required (freeze): approval of the corrected text.
- **Downstream:** TE1–TE3, X4 (P1), X6 (P1), the unit tests for exit-day behaviour.

---

### 2.6 X2: entry-session handling and D12

- **Issue (audit §5 X2):** "on `s*+1` the position is bought at the open, and the rule '`L(s*+1) ≤ S` → exit at
  `S`' sells it the same session". Draft §8 says D12 "does **not** apply". For these trades that is wrong.
- **Effect:** simulated loss on entry-day reversals, and the Sharia status of the strategy design.
- **Alternatives:**
  - (a) keep the draft's rule: a same-session round trip, research only, counted;
  - (b) the audit's earlier default: ignore the entry-session low, and run the first stop check at
    `O(e+1)` / `L(e+1)`;
  - (c) **breach on the entry session → exit at `O(e+1)` unconditionally.** If `L(e) ≤ S`, the position is
    closed at the next open whether or not price has recovered;
  - (d) no exit of any kind before session `e+2`. Every sale then follows completed T+1 settlement of the
    purchase (INF; broker rule NOT VERIFIED);
  - (e) a close-based exit on session `e`. It is still a same-session round trip, so it is rejected.
- **Recommended default: (c).**
  - The draft's stop rationale is that touching `S` voids the event hypothesis. (c) keeps that logic and only
    defers execution to the first price that does not create a same-session round trip.
  - (b) ignores a breach the draft treats as decisive.
  - (d) adds a full extra session of unprotected exposure.
  - **This refines the audit's default (b).**
- **D12 implications (no ruling given):**
  - Under (c), no simulated position is bought and sold in the same session, by construction. That holds for
    collisions and D2 exits too (X1 step 2).
  - **D12 is not fully settled.** A sale at `O(e+1)` may occur on the purchase's settlement day under US T+1
    (INF).
  - FACT: D12 records that "resale is permitted once daman (liability) has passed, even before final
    settlement", and asks whether US T+1 broker execution satisfies 3/7. Whether a sale on the settlement day is
    permissible is part of that adviser question.
  - If the adviser requires settlement first, (d) is the fallback. It must be chosen **before** the freeze,
    never after results.
  - Cash-account good-faith rules for that sale are a broker question (R6, P4).
- **Assumptions and unresolved evidence:** broker settlement and good-faith rules (NOT VERIFIED); D12 adviser
  ruling (ADVISER_REQUIRED); how often `L(e) ≤ S` occurs (unknown before data).
- **Owner approval:** required (choice) + adviser (D12).
- **Downstream:** X1 (the algorithm text), SH4 (P4), R6 (P4), TE2 (entry-day breaches produce `R < −1` when
  `O(e+1) < S`; counted separately).

---

### 2.7 X3: consistent price basis for signal, stop and sizing

- **Issue (audit §5 X3):** "eligibility uses `AR(s*)`, but `S = C(s*−1)` and the sizing
  `N = RiskBudget / (C(s*) − S)` use the **raw** reaction". Trade selection and size then depend on the
  market's direction on the reaction day.
- **Effect:** a market-timing component enters TE1–TE3:
  - with a falling market on `s*`, a large AR comes with a tiny raw stop distance (a huge notional) or a
    negative one (a skip);
  - with a rising market, the stop distance overstates the abnormal reaction.

  The statistical estimands are unaffected.
- **Alternatives:**
  - (a) keep the raw `S = C(s*−1)`, and add a notional cap and reporting (the audit's earlier default);
  - (b) a relative stop: exit when the stock's SPY-relative return since `C(s*−1)` reaches ≤ 0. This is
    consistent, but it is not a resting price level, so it cannot bound raw risk. It is incompatible with the
    approved 0.5% price-stop sizing;
  - (c) **an abnormal-reaction stop at a fixed raw level**:
    `S = C_i(s*) − (C_i(s*−1)/q_i(s*)) · AR_i(s*)`;
  - (d) a volatility stop `S = C(s*) − k·σ·C(s*−1)`. It adds the parameter `k` and is unrelated to the reaction;
  - (e) a raw-return signal. It contradicts the H1 design, so it is rejected.
- **Recommended default: (c).**
  - Then `E_plan − S = (C_i(s*−1)/q_i(s*)) · AR_i(s*)` exactly, which is positive for every eligible event
    because `z ≥ z0 > 0` implies `AR > 0`.
  - Interpretation: `S` is the raw price at which the reaction-day **abnormal** gain would be fully given back,
    measured in pre-event share units. That is the draft's "full reversal" idea on the signal's own basis.
  - Sizing under the unchanged approved rule: `N = floor(0.005 · Capital_basis / (E_plan − S))`. The notional
    share is then about `0.5% / AR_i(s*)` of capital.
  - Arithmetic only: `AR = 4%` gives about 12.5%, and `AR = 2%` gives about 25%.
  - The size now depends on the abnormal reaction, not on the market's move that day.
  - `S` is a fixed raw level after `Close(s*)`. It can be placed as a resting stop and is adjusted only for
    splits (`S/q`).
  - Market moves after entry can still reach it. That is disclosed: it is a price stop, not a relative stop.
- **Remaining consequences:**
  - An entry open at or below `S` is now possible only if the entry open gaps through `S`. Under §2.5 such
    trades are filled and exited at `O(e+1)` (`GAP_AT_ENTRY`), not skipped.
  - Very low-σ names can still give large notionals: `AR ≥ z0 · σ`, so with `σ = 0.8%` and `z0 = 2`, the notional
    is up to about 31%. A per-position notional cap (R3, P1) remains useful. Its value is the owner's.
  - Dividend ex-dates during the holding still move the raw price relative to `S`. That is X8 (i), P2.
- **Assumptions and unresolved evidence:**
  - β = 1 (the stop inherits it).
  - SPY total return on `s*` comes from the PIT series. A dividend of stock `i` with ex-date `s*` enters `AR`
    through `r_i` (draft §3.1 formula).
  - The formula is **NOT YET IMPLEMENTED**. It needs a future-mutation test: changing any bar after `Close(s*)`
    must not change `S` or `N`.
- **Owner approval:** required (choice). The draft's stop rule is a PROPOSED item under SW4.
- **Downstream:** X2 (the entry-session breach uses this `S`), X1, R2 (open-risk definition), R3 (notional cap),
  TE2 (the meaning of R), and SH1 (D2 exits are unaffected).

---

### 2.8 T1: definition of `VERIFIED` (with P1 item GV4)

- **Issue (audit §2 T1):** "no repository file defines what evidence makes a row `VERIFIED`". The draft's SW-T
  would apply a new definition "retroactively to the 2026 file's semantics too". GV4 notes that the 2026 file is
  consumed by ORB (`strategy/day/orb_rules.py:188-211`, per draft §0.1).
- **Effect:** `s*` sets the reaction session, `z`, the entry date, the stop and the sizing all at once. An
  unclear definition is a hidden free parameter.
- **Alternatives:**
  - (a) adopt the draft's §2.3 as written;
  - (b) **a new SW-A vocabulary with an explicit definition (below)**;
  - (c) redefine `VERIFIED` in the 2026 files. This is rejected under GV4, because it changes the meaning of an
    input already consumed by ORB.
- **Recommended default: (b).**

  ```
  swa_timing_status(e) = SWA_VERIFIED  iff all of:
    V1  class(e) = RESULTS (C1)
    V2  at least one tier-1..3 evidence item (T2) states, for the public release, either
          an explicit time            → instant T_rel, or
          an explicit session phrase  → interval I_rel (T3 mapping: "before the market opens" on d → [00:00, Open(d));
                                         "after the market closes" on d → [Close(d), 24:00))
    V3  date agreement: the evidence date d_rel satisfies d_rel ≤ ET-date(T_acc) ≤ d_rel + Δ_max (business days)
    V4  consistency with acceptance: T_acc ≥ T_rel (instant) or T_acc ≥ start(I_rel) (interval)
    V5  no tier-1..3 item implies a different session class (BMO / AMC / NON_SESSION / INTRA)
    V6  the evidence record is complete: URL, retrieval time (UTC), SHA-256 of the raw bytes, verbatim quote, tier,
          reviewer, rule-set version
  otherwise swa_timing_status(e) = SWA_UNRESOLVED with one reason code from
    {NO_EVIDENCE, CONFLICT, INCONSISTENT_TACC, DATE_MISMATCH, AMENDED, UNCLASSIFIED, RECORD_INCOMPLETE}
  ```

  - Session class follows draft §2.4, from `T_rel`, or from `I_rel` when the interval lies within one class.
  - The fields `swa_timing_status`, `swa_timing_basis`, `swa_session_class` and `swa_reason` live only in the
    future SW-A event table, inside the SW-A data tree (GV3).
- **GV4 (P1), linked:**
  - `config/earnings_calendar.csv`, `config/earnings_calendar_sources.csv` and `data/earnings.py` are **never
    modified, re-labelled or reinterpreted** by SW-A.
  - FACT: their coverage (2026-07-02 → 2026-09-25) falls inside SW-A's excluded 2026 period (draft §7.2), so
    SW-A has no need to use them.
  - Optional (owner choice): after acquisition is authorized, run the SW-A method over the 2026 rows' filings as
    a **pipeline agreement check**. It would report agreement counts only and read no prices. The audit lists
    this as a separate, descriptive record of what the 2026 `VERIFIED` meant.
- **Assumptions and unresolved evidence:**
  - `Δ_max` is still PROPOSED at 1 business day (T3, P1).
  - LIT [UNVERIFIED]: Item 2.02 allows up to four business days. Some genuine events will be `DATE_MISMATCH`, and
    they are counted.
  - The ET semantics of the EDGAR acceptance field are unverified (T4, P1).
- **Owner approval:** required (choice) (SW-T, replacing its "retroactive" clause).
- **Downstream:** T3–T6 (P1), C1–C7 (P1), the event-table hash (draft §2.6), S6 (event counts), GV4.

---

### 2.9 T2: evidence tiers and precedence

- **Issue (audit §2 T2):** the draft allows exhibit statements and timestamped IR pages but "does not rank them,
  and it does not say whether newswire distribution timestamps or conference-call times count".
- **Effect:** the exclusion rate and its unevenness by period. Older IR archives may be incomplete (INF),
  which would remove more early events.
- **Alternatives:**
  - the tier set could be {exhibit}, {exhibit, IR}, {exhibit, IR, newswire} or {… + `T_acc`-only};
  - conflict handling could be "precedence overrides a conflict" or "a conflict always means UNRESOLVED".
- **Recommended default:**

  | Tier | Evidence | Role |
  |---|---|---|
  | 1a | exhibit 99.x: explicit time of release | sets `T_rel` |
  | 1b | exhibit 99.x: explicit session phrase | sets `I_rel` |
  | 2 | issuer IR page or archive entry with a timestamp | sets `T_rel` if tier 1 is silent |
  | 3 | newswire distribution timestamp (the issuer's release on a wire service) | sets `T_rel` if tiers 1–2 are silent |
  | C | conference-call time; `T_acc` | **corroboration and bounds only; never sets `T_rel`** |

  - **Rule: precedence fills absence; it never overrides a contradiction.** The highest available tier sets
    `T_rel` or `I_rel`. Every other tier-1–3 item is still checked, and any class disagreement gives
    `CONFLICT → SWA_UNRESOLVED` (V5).
  - **A `T_acc`-only classification is excluded from the baseline.** It is reported as the sensitivity variant
    `TACC_ONLY`:
    - AMC if `T_acc ≥ Close(d)` and the exhibit dateline is `d`;
    - BMO if `T_acc < Open(d)` and the dateline is `d`;
    - otherwise unresolved.

    Its known failure: a 07:00 release filed after the close would be classed AMC, so the reaction would be
    measured one session late.
- **Assumptions and unresolved evidence:**
  - Historical availability of tier-3 sources is unknown until access is authorized (T7, P2).
  - Licensing of stored copies is a T6 (P1) question; the repository is public (FACT, audit T6).
- **Owner approval:** required (choice).
- **Downstream:** T1 (V2, V5), T5 (exclusion threshold, P1), T6 (record format, P1), T7 (sources to access, P2),
  S6 (counts).

---

### 2.10 U6: data-access dates for SW-A without weakening V2-MOM isolation

- **Issue (audit §6 U6):** three statements were thought to conflict: DAY-22 §3.2.3 (252 sessions, to
  2027-10-08), `contract.py:112` (2026-10-08 → 2027-01-07), and draft §7.2 (forward confirmation after the
  `fwd-gate2` evaluation).
- **Corrected facts (§0.2):**
  - The DAY-22 252-session window was **replaced** by the adopted v2.1 amendment (63 sessions,
    2026-10-08 → 2027-01-07).
  - The v2.1 `fwd-gate` was **superseded** by the adopted v2.2 amendment, "never acquired or evaluated".
  - The only PENDING blind V2 segment is **`fwd-gate2`** (2026-10-12 → 2026-12-09, capture no earlier than
    2026-12-09 16:15 ET).
  - P001's seal ends at the same time.
  - `contract.py:112` still defines the superseded 63-session `FORWARD_WINDOW` constant. Which code paths still
    read it was **not checked** (no code paths were read beyond the grep).
- **Effect:** the SW-A forward confirmation is the only confirmatory test (draft §7.2). Starting it under the
  wrong boundary could touch V2-MOM's blind data.
  - INF: SW-A uses the same 25 symbols and SPY. Any SW-A price data dated inside a V2 blind segment would reveal
    much of that segment's outcome, even without computing V2 metrics.
- **Alternatives (for the SW-A forward-sample start):**
  - (a) the first session after the `fwd-gate2` capture and evaluation;
  - (b) **the first session after 2027-01-07**, the end of every forward window still defined in code;
  - (c) after 2027-10-08, the superseded DAY-22 rule. It is maximally conservative but has no current basis;
  - (d) another date set by the protocol owner.
- **Recommended default: (b), plus standing rules R-U6-1 to R-U6-4.**
  - **R-U6-1 (standing isolation rule):** SW-A never acquires, computes on or inspects market data, or EDGAR
    filings, dated inside any V2 segment whose status is PENDING, until that segment's capture time has passed.
    This covers `fwd-gate2` now, and any future V2 forward segment the owner declares.
  - **R-U6-2 (zones):**

    | Zone | Dates | SW-A use |
    |---|---|---|
    | H (historical) | events with `s*` ≤ 2025-12-31; data from 2016-01-04 | development, validation and historical test (draft §7.2), after GV1 and U5 authorization, in a fresh separate snapshot |
    | X1 | 2026-01-02 → 2026-10-07 | **never evaluated**. FACT: 2026-01-02 → 2026-06-02 are Stage H dates; 2026-06-03 onward was seen by day-trading research (protocol v2 §3.6). Formation history only, read mechanically for forward-event σ and MOM windows |
    | X2 | 2026-10-08 → 2027-01-07 | **never evaluated**. No SW-A acquisition of data dated here before 2026-12-09 16:15 ET (R-U6-1). After that, formation history only |
    | F (forward) | events with `s*` ≥ the first session after max(SW-A freeze-commit date, 2027-01-07, the hold-lift date) | the SW-A forward gate (§2.4 ladder) |

  - **R-U6-3 (incidental records):** a historical acquisition may return records dated after its range, such as
    corporate-action rows by `process_date`, or EDGAR `submissions` lists that include recent filings. Records
    dated ≥ 2026-10-08 are dropped in memory before persistence, and only their count is kept. This is the day17
    C1 option (i) pattern.
    - Request bounds: bars `end ≤ 2025-12-31`; corporate-action `process_date` upper bound strictly before
      2026-10-08.
    - `asof`: a date ≤ 2026-10-07, following the `STAGE_H_ASOF` precedent.
  - **R-U6-4 (forward acquisition):** the SW-A forward data is acquired **once, after a predeclared forward
    period ends**, as in protocol v2 §3.9 Stage F. Nothing is computed or inspected in between. The forward
    length is an owner decision taken at the freeze (§4, U6-L).
- **Reasoning for (b) over (a):**
  - (b) needs no judgement about whether the superseded constant is still active.
  - It cannot conflict with any forward window present in code.
  - Its cost is only SW-A events with `s*` between about 2026-12-10 and 2027-01-07. INF: mostly a few
    off-calendar fiscal-year reporters in December, since the main fourth-quarter season starts mid-to-late
    January.
  - (a) is defensible if the owner confirms the 63-session window is inert.
- **This does not weaken V2-MOM isolation:**
  - (b) is a strict superset of the existing V2 restrictions.
  - Nothing in it changes `fwd-gate2`, P001 or any V2 file.
  - No SW-A process writes under `data/oos_cache/protocol_v2/` (GV3).
- **Assumptions and unresolved evidence:**
  - Whether the owner plans further V2-MOM forward segments after `fwd-gate2`. R-U6-1 covers them automatically.
  - Whether `FORWARD_WINDOW` is still read by code (unverified).
  - The research hold, OPEN-G2 (GV1, P2).
- **Owner approval:** required (choice). It is a protocol-ownership decision.
- **Downstream:** GV1 (P2), U5 (P2), the S7 forward gate, X8 (P2; corporate-action query bounds), T7 (P2; EDGAR
  bounds), U6-L (forward length).

---

### 2.11 GV3: protocol home, freeze and registry

- **Issue (audit §9 GV3):** "SW-A is not a protocol v2 family (v2 §14 lists exactly three)". It needs its own
  frozen protocol, a config hash, experiment IDs, a registry, and a statement of which v2 conventions it
  inherits.
- **Effect:** without a protocol home, the P0 decisions above cannot be frozen, hashed or enforced.
- **Alternatives:**
  - (a) **a standalone SW-A protocol** with its own version line, a document plus machine-readable twin plus
    checklist, separate paths, and a separate registry;
  - (b) a protocol v2 amendment adding a fourth family;
  - (c) informal: design docs only, with no freeze.
- **Recommended default: (a).**
  - Against (b): the `fwd-gate2` capture preflight checks "the protocol identity" and the unchanged v2.0.4
    amendment (FACT, v2.2 §6). Amending v2 files during the blind period could interfere with the gate (INF).
    It would also mix SW-A into V2's trial count.
  - Against (c): it gives no enforceable freeze.
- **Proposed contents:**
  - Version `SWA-1.0`, frozen by a commit. The commit SHA and SHA-256 values of the protocol files are recorded
    by the first SW-A data task.
  - Experiment IDs: `SWA-D001` (development, descriptive), `SWA-V001` (validation), `SWA-T001` (historical
    test), `SWA-F001` (forward).
  - Strategy-config SHA-256 over a canonical JSON of the frozen parameters, including `z0`, `H`, the stop rule,
    costs, `L`, `B`, the seed, `δ` and `Δ_max`.
  - Paths: a separate artifact folder; a separate write-once data tree outside `data/oos_cache/protocol_v2/`;
    an append-only SW-A experiment registry.
  - **Inherited by explicit reference** (pinned by file SHA-256):
    - protocol v2 §3.3 (calendar and session index);
    - §3.4 (raw execution and PIT total-return basis);
    - §3.8 (data-quality checks);
    - §3.9 (write-once snapshots and overlap control);
    - §7 (no-lookahead tests, extended to `R^oo`, `S` and the event table);
    - §9 (cost scenarios);
    - §17 (reproducibility, plus the bootstrap seed);
    - v2.4 (the FB→META identity alias).
  - **Not inherited:** v2 §13 (replaced by the §2.4 ladder), §10 (benchmarks, replaced by TE3), §8.9 ("no
    stop-loss"), §11.8 (position counts).
  - **Decided anew for SW-A:** the day17 C1–C4 corporate-action questions (X8, P2).
  - Commit timing: SW-A files may be committed at any time. INF: the tree must be clean at the `fwd-gate2`
    capture (OPS-1), and no SW-A file may sit in a V2 data path.
- **Assumptions and unresolved evidence:** whether committing new files under new paths during the blind period
  affects any V2 check. INF: it does not, provided the tree is clean at capture. The preflight code itself was
  not read.
- **Owner approval:** required (choice).
- **Downstream:** S7 (the gate lives here), U6 (the access rules live here), T1 (the vocabulary lives here), GV1,
  and all P1 freeze items.

---

## 3. Dependencies between decisions

```
GV2 ─┬─▶ GV3 ─┬─▶ (freeze of every item below)
     │        └─▶ U6 ──▶ GV1(P2), U5(P2), T7(P2), X8(P2), forward gate in S7
     │
     ├─▶ T2 ──▶ T1 ──▶ C1–C7(P1) ──▶ event table hash ──▶ S6 counts
     │           └─▶ GV4(P1)
     │
     ├─▶ S2 ──▶ S4 ──▶ S5(P1) ──▶ S6(P1) ──▶ S7 ◀── δ (owner value, SW3)
     │                                  ▲
     │                     S10(P1: MOM availability) ──┘
     │
     └─▶ X3 ──▶ X2 ──▶ X1 ──▶ TE1–TE3 ──▶ S7 step 7
          ├─▶ R3(P1 notional cap), R2(P3 open-risk definition)
          └─ X2 ──▶ SH4/D12 (adviser, P4), R6 (broker, P4)
```

**Ordering constraints:**
1. GV2 first.
2. S2 must be decided before S4, and S4 before S5 and S6. The inference method depends on which estimand is
   being inferred.
3. X3 must be decided before X2, because X2's breach test uses `S`.
4. `δ` must be fixed before any price is read, because it determines `n_min`.
5. T2 before T1.
6. U6 before any acquisition request is drafted.

---

## 4. Compact owner decision table (P0)

Every row is **PROPOSED — not approved**.

| # | ID | Decision requested | Recommended default | Main alternatives | Approval | Blocks |
|---|---|---|---|---|---|---|
| 1 | GV2 | SW-A as swing priority | approve for design completion only | full approval; S1; park | owner (choice) | everything |
| 2 | S2 | H1 window | open-to-open traded window `AR^oo(e, x)`; overnight `G(e)` and `D^cc` reported | close-based (labelled); both | owner (choice) | DC |
| 3 | S4 | H2 estimand | `Δ₂` = mean net `AR^oo` of `E+` − symbol-matched non-event baseline; stop-free; TE1–TE3 for trading | no baseline; pooled baseline; stop-inclusive | owner (choice) | DC |
| 4 | S7 | acceptance logic | ladder §2.4.5; power check pre-outcome; `LB > 0` and point ≥ `δ`; operational momentum test; non-PASS stops | REJECT-first; `LB > δ`; H1-only label | owner (choice) | DC |
| 4a | S7-δ | `δ` value | **no default**; owner sets it before data; >0.10% makes the 10 bps check redundant | — | owner (value) | DC |
| 5 | X1 | exit ordering | corrected algorithm §2.5 | — (correction) | owner (freeze) | DC |
| 6 | X2 | entry-session handling | no exit on session `e`; breach → exit at `O(e+1)`; adviser on D12 | draft rule; ignore the breach; earliest exit `e+2` | owner (choice) + adviser | DC; PL |
| 7 | X3 | stop basis | `S = C(s*) − (C(s*−1)/q)·AR(s*)` | raw `C(s*−1)` + cap; volatility stop | owner (choice) | DC |
| 8 | T1 | `VERIFIED` definition | `SWA_VERIFIED` V1–V6; 2026 files untouched | draft §2.3 as is; redefine 2026 (rejected) | owner (choice) | DC |
| 9 | T2 | evidence tiers | 1a/1b exhibit > 2 IR > 3 newswire; call time and `T_acc` corroborate only; conflict ⇒ UNRESOLVED | fewer tiers; `T_acc`-only baseline | owner (choice) | DC |
| 10 | U6 | SW-A data dates | forward `s*` after max(freeze, 2027-01-07, hold-lift); rules R-U6-1 to R-U6-4 | after `fwd-gate2`; after 2027-10-08 | owner (choice) | DA; PL |
| 10a | U6-L | forward-period length | **no default**; fixed at the freeze; acquired once at its end | — | owner (value) | forward gate |
| 11 | GV3 | protocol home | standalone `SWA-1.0` + twin + registry; inherit named v2 sections by SHA | v2 amendment; informal | owner (choice) | DC |

**Linked P1 items specified here (still P1, still owner decisions):**
- **S5:** circular block bootstrap, `L = 2(H+1)`, `B = 10,000`, fixed seed.
- **S6:** the `n_min` formulas with `DEFF`, estimated on development.
- **GV4:** the 2026 calendar files are not reinterpreted.

---

## 5. Remaining non-P0 issues that must be resolved before execution

From the audit's §10 table, with priority unchanged. Items marked * are partly specified in this proposal but
not approved.

| Priority | Items | Blocks |
|---|---|---|
| P1: design | T3 (session intervals, `Δ_max`)\*, T4 (time zones; EDGAR field semantics), T5 (exclusion threshold), T6 (audit trail, licensing); C1–C7 (classification, completeness, fiscal period, `8-K/A`, boundary cases, INTRA/collisions, σ-window exclusion); S1 (ddof, missing SPY, β), S3 (H1 sample), S5\*, S6\*, S8 (project trial count), S9 (segment-boundary leakage), S10 (MOM availability)\*; X4 (missing bars)\*, X5 (simultaneous signals), X6 (collision disclosure), X7 (slippage on gap and collision exits), X9 (accounting, `E_0`, integer shares); R3 (notional cap value), R5 (gap-risk reporting); U1 (universe), U2 (via S4)\*, U3 (screened-subset reporting); GV4\*; SH2-L (D10 ledger fields) | design completion |
| P2: data | T7 (EDGAR terms, pagination, contact identity); U4 (PIT symbol→CIK/CUSIP map); U5 (fresh data over Stage R/H dates; separate tree); X8 (dividend-stop rule, acquirer-side merger records, day17 C1–C4 for SW-A); GV1 (research hold, authorization) | data acquisition |
| P3: backtest | R1 (capital basis), R2 (open-risk cap definition and value; needs the X3 decision), R4 (sector concentration) | backtest |
| P4: paper or live | R6 (settlement), SH1 (D2 exit logic, refresh cadence, quota), SH2 (D10 ruling), SH3 (D15 broker checklist, cash interest), SH4 (D12, including the X2 next-session sale), SH5 (Akinda licence, registry rows), SH6 (event-driven holding) | paper or live |
| — | GV5 (stale OPS-1 text in the draft) | nothing |

**Operational:**
- This proposal and the audit are both **untracked** at the time of writing.
- `fwd-gate2` capture refuses any untracked file (`stage_f.py:322-323`, per D1/S1 §0.5 and the discovery
  report). Both files must be committed or removed before 2026-12-09 16:15 ET.

---

## 6. Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | All 11 P0 items accounted for | PASS: GV2, S2, S4, S7, X1, X2, X3, T1, T2, U6 and GV3 (§2.1–§2.11), matched against the audit's §10 P0 rows (§0.1) |
| 2 | No decision silently treated as approved | PASS: every item is PROPOSED with "owner approval required"; `δ` and the forward length have no default |
| 3 | Statistical and trading estimands distinguished | PASS: §1 point 2, §2.3.1 (statistical: β₁, Δ₂, stop-free), §2.3.2 (trading: TE1–TE3); S7 step 7 is the only link |
| 4 | No profitability claim | PASS |
| 5 | No existing file or protocol modified | PASS: only this file was created |

## 7. Safety confirmation

- Only this file was written. No code, config, existing document or protocol was changed. Nothing was staged,
  committed or pushed.
- No API call, network access, data acquisition, test, backtest or optimization was run.
- Not opened: Stage R, H and F data; `paper_state/`; sealed P001; `fwd-gate2` results; and the DAY-26C incident
  record.
- Code was not read beyond a constant listing of `acquisition/v2/contract.py`, obtained by grep. Only
  constants were read; no data path was touched.
