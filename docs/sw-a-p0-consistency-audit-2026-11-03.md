# SW-A P0 proposal: consistency audit of U6, X3 and S7 (2026-11-03)

> **Status: INDEPENDENT AUDIT — NOT APPROVED FOR EXECUTION.**
> - This audit challenges three recommendations in `docs/sw-a-p0-resolution-proposal-2026-11-03.md` ("the
>   proposal"). It approves nothing and does not modify the proposal.
> - Every correction below is a requirement or an owner decision. None has been applied.
> - No code, config or existing document was changed. No API call, network access, data acquisition, test,
>   backtest or simulation was run.
> - Stage R and Stage H data, `paper_state/`, sealed P001, `fwd-gate2` results and the DAY-26C incident record
>   were not opened.
> - **No claim is made that SW-A is profitable.**

**Independence limitation (read first).** This audit was written by the same agent, in the same session, that
wrote the proposal. Each claim was re-checked against the source files. That is not independent review in the
sense of a separate reviewer: shared blind spots are possible. **A separate human or agent review of the three
areas is recommended before the owner approves anything.**

**Verdict scale:**
- **SUPPORTED**: the proposal's statement matches the sources and is internally consistent.
- **PARTIALLY SUPPORTED**: correct in substance, but incomplete, imprecise or overstated.
- **UNSUPPORTED**: contradicted by a source, internally inconsistent, or mathematically wrong.

**Blocks:**
- **FREEZE**: the SW-A design cannot be frozen until the finding is resolved.
- **DA**: data acquisition.
- **PL**: paper or live trading.

**Labels:** FACT (read from a cited file and line), INF (an inference), ASSUMPTION (illustrative values, not data),
and LIT [UNVERIFIED] (literature from memory, not checked).

---

## 1. Summary of findings

| ID | Area | Finding (short) | Verdict | Blocks |
|---|---|---|---|---|
| U6-1 | U6 | Amendment chain and adoption status | SUPPORTED | — |
| U6-2 | U6 | 2027-01-07 is also in adopted v2.1 text, which v2.2 did not revoke; the proposal calls it a "superseded constant … in code" | PARTIALLY SUPPORTED | DA |
| U6-3 | U6 | Three different end conditions for the blind-period restriction inside the proposal | UNSUPPORTED (inconsistent) | FREEZE, DA |
| U6-4 | U6 | Historical events with `s*` in late 2025 need January–February 2026 data that the proposal both excludes and does not acquire | UNSUPPORTED (inconsistent) | FREEZE |
| U6-5 | U6 | The rules do not authorize access before the research hold, but an explicit precondition is missing | PARTIALLY SUPPORTED | DA |
| U6-6 | U6 | DAY-22 §3.2.4 / v2.1 C17 (no forward-guided proposals) is not addressed for SW-A design work done during the blind period | PARTIALLY SUPPORTED | FREEZE (governance) |
| X3-1 | X3 | Re-derivation of the stop formula | SUPPORTED (one wording correction) | — |
| X3-2 | X3 | Dividend ex-dates during the holding; broker treatment of resting stops | PARTIALLY SUPPORTED | FREEZE |
| X3-3 | X3 | Executable as a raw level, but tick rounding and the live order sequence for the X2 rule are missing | PARTIALLY SUPPORTED | FREEZE |
| X3-4 | X3 | Positive, negative and near-zero AR: an explicit guard is missing | PARTIALLY SUPPORTED | FREEZE |
| X3-5 | X3 | "No longer depends on the market's direction" holds only under β = 1, and not after entry | PARTIALLY SUPPORTED (overstated) | FREEZE |
| X3-6 | X3 | The notional cap is optional, risk overrun at the entry fill is uncontrolled, and there is no gap-risk control | UNSUPPORTED (incomplete design) | FREEZE, PL |
| X3-7 | X3 | The statistical estimands do not use `S` | SUPPORTED | — |
| S7-1 | S7 | Block length `2(H+1)` is a heuristic; about 25% of dependent pairs are split | PARTIALLY SUPPORTED | FREEZE |
| S7-2 | S7 | "Circular block bootstrap" conflicts with "assigned to the block" | UNSUPPORTED (ambiguous spec) | FREEZE |
| S7-3 | S7 | Cross-sectional dependence and overlap are preserved only within blocks | PARTIALLY SUPPORTED | FREEZE (disclosure) |
| S7-4 | S7 | The CI structure controls false PASS for "> 0" | SUPPORTED (with the disclosed few-block caveat) | — |
| S7-5 | S7 | `δ` is in acceptance only as a point-estimate test; `δ_β = δ/z0` ignores the intercept; no account-level meaning is given | PARTIALLY SUPPORTED | FREEZE |
| S7-6 | S7 | The power target (80%) does not match the PASS rule. At `n_min`, P(PASS when Δ₂ = δ) ≈ 50% | UNSUPPORTED (mathematical mismatch) | FREEZE |
| S7-7 | S7 | "About 220 events" is correctly marked illustrative, but it is optimistic in three ways | PARTIALLY SUPPORTED | FREEZE (wording) |

**Counts:** 4 SUPPORTED, 11 PARTIALLY SUPPORTED, 5 UNSUPPORTED (20 findings). 14 findings block the freeze;
U6-2 and U6-5 block data acquisition only. None of the findings changes the recommendation that SW-A stays
design-only.

---

## 2. U6: data isolation and date rules

### U6-1. Amendment chain and adoption status
- **Checked:** the status line or adoption record of every forward-relevant protocol document. Results and the
  DAY-26C incident record were not opened.
- **Evidence:**

  | Document | Status (FACT) | Forward-window effect | Source |
  |---|---|---|---|
  | DAY-16 protocol v2 §3.6 | frozen | 252 sessions after the freeze commit | `artifacts/day16/research-protocol-v2.md` §3.6 |
  | DAY-22 sign-off | signed off | 2026-10-08 → 2027-10-08 (252); §3.2 blind rules; §3.2.3 "No forward market data may be acquired into the research cache until the 252-session waiting period has concluded" | `artifacts/day22/…lockdown.md:132,138,154-155` |
  | DAY-24 | "PROPOSED AMENDMENT — NOT YET EFFECTIVE"; superseded on v2.1 adoption | (63 sessions, never effective) | `artifacts/day24/…design.md:9`; `artifacts/day26b/protocol-v2.1-amendment.md:39` |
  | DAY-26A | "PROPOSED — NOT EFFECTIVE"; superseded on v2.1 adoption | (21-session observation, never effective) | `artifacts/day26a/…draft.md:3`; v2.1 `:40` |
  | **v2.1** | **ADOPTED** 2026-10-10T12:52:51Z (`final_status: "ADOPTED"`) | 63 sessions, 2026-10-08 → 2027-01-07 (`fwd-diag` 1–21, `fwd-gate` 22–63). Replaces DAY-22 §3.1 (C13, E1). §3.2.3 becomes "per segment" (C16). §3.2.4 "unchanged and extended" (C17) | v2.1 `:11,13,17,111-120,204-208,288`; `protocol-v2.1-adoption.json`; adoption md `:16,23-26` |
  | **v2.2** | **ADOPTED** 2026-10-10T14:56:30Z | old `fwd-gate` "SUPERSEDED (protocol 2.2) — never acquired or evaluated". New `fwd-gate2` covers 2026-10-12 → 2026-12-09 (42 sessions); capture ≥ 2026-12-09 16:15 ET. Append-only: "the protocol 2.1 files … are not modified" | `artifacts/day26d/protocol-v2.2-amendment.md:4,9-12,24,32-34,58,68-69` |
  | **v2.3** | **ADOPTED** | P001 sealed until 2026-12-09 16:15 ET; "the experiment continues indefinitely" | `artifacts/day27/protocol-v2.3-amendment.md:12-13`; adoption json |
  | **v2.4** | **ADOPTED** | identity alias only; "No … calendar, sample, data-window … changes" | `artifacts/day27a/protocol-v2.4-amendment.md:3,13-18` |
  | v2.5 | `PROPOSED_NOT_ADOPTED` | paper-runner observability only | `artifacts/day27b/protocol-v2.5-adoption.json`; amendment `:3` |
  | code | `FORWARD_WINDOW = (2026-10-08, 2027-01-07, 63)`; `fwd-gate2 = (2026-10-12, 2026-12-09, 42)`; `EXPOSED_SESSIONS = (2026-10-08, 2026-10-09)` | — | `acquisition/v2/contract.py:112,118,120,122` |

- **Verdict: SUPPORTED.** The proposal's corrected facts (proposal §0.2 and §2.10, lines 636–645) match the
  chain:
  - DAY-22's 252-session window was replaced by v2.1;
  - v2.1's `fwd-gate` was superseded by v2.2;
  - `fwd-gate2` is the pending blind segment.

  v2.0.1–v2.0.4 contain corporate-action and identity rules, not forward-window rules, and were not traced
  further.
- **Correction:** none.
- **Blocks:** —

### U6-2. The source and meaning of 2027-01-07
- **Checked:** where the date appears, and whether anything revoked it.
- **Evidence (FACT):**
  - v2.1 header: "Forward window | 63 XNYS sessions, 2026-10-08 → 2027-01-07" (`:11`); "Earliest final gate
    evaluation | 2027-01-07 16:15 America/New_York" (`:17`).
  - v2.1 §6 permission rows:
    - `:118`: "2026-11-06 → 2027-01-07 16:15 America/New_York | any data dated ≥ 2026-11-06 | no | no | no";
    - `:119`: "after 2027-01-07 16:15 … data dated ≤ 2027-01-07 | once (Stage F-G)".
  - v2.1 C15 (`:206`): the no-peeking rule is "Binding for all `fwd-gate` data until 2027-01-07 16:15".
  - v2.2 supersedes only the `fwd-gate` **segment** (`:24`), and states that it is append-only and does not
    modify the v2.1 files (`:4`).
  - v2.2 D4 (`:34`) itself authorizes acquiring data dated up to 2026-12-09 at 2026-12-09, which conflicts with
    the literal v2.1 `:118` row. So v2.2 overrides that row at least for `fwd-gate2`.
  - `contract.py:112` keeps the 63-session constant.
- **Verdict: PARTIALLY SUPPORTED.**
  - The proposal describes 2027-01-07 as "the end of every forward window still defined in code" (proposal
    `:652`) and calls the constant "superseded" (`:644`).
  - The date is **also** in adopted protocol text (v2.1 §6 and C15), which no adopted document has textually
    revoked.
  - Whether v2.1 `:118–119` and C15 lapsed with the `fwd-gate` segment is **UNRESOLVED**. INF: their rationale
    (the blindness of `fwd-gate`) disappeared when `fwd-gate` was superseded, but the text remains.
- **Required owner or protocol decision:** record explicitly whether v2.1 §6 rows `:118–119` and C15 lapsed when
  v2.2 superseded `fwd-gate`. Until that is recorded, treat them as binding (fail-closed). The proposal's U6
  description should cite these lines, not only the code constant.
- **Blocks:** DA.

### U6-3. Inconsistent end conditions inside the proposal
- **Checked:** every statement in the proposal that bounds SW-A access to data dated 2026-10-08 or later.
- **Evidence (FACT, proposal):**

  | Location | Statement |
  |---|---|
  | `:112-113` (exec summary 10) | "no SW-A data dated on or after 2026-10-08 is **used** before **2027-01-07 16:15 ET**" |
  | `:651` (alternative a) | "after the `fwd-gate2` **capture and evaluation**" |
  | `:656-658` (R-U6-1) | "… dated inside any V2 segment whose status is PENDING, **until that segment's capture time has passed**" |
  | `:665` (zone X2) | "No SW-A acquisition of data dated here before 2026-12-09 16:15 ET (R-U6-1). **After that, formation history only**" |

- **Verdict: UNSUPPORTED (internally inconsistent).**
  - **(i) "Capture" is not the end of the blind obligation.** Under R-U6-1, SW-A could acquire `fwd-gate2`-dated
    prices after the capture but before the gate's evaluation is recorded. INF: on the same 25 symbols plus SPY,
    that data reveals much of the gate's outcome before the formal result exists.
  - **(ii) Zone X2 allows acquisition between 2026-12-09 and 2027-01-07.** That contradicts the reason for
    recommending option (b) in the first place, and the literal v2.1 `:118` row (U6-2).
  - **(iii) "Used" in the summary is weaker than "acquired, computed or inspected"**, the vocabulary of v2.1 §6.
- **Required correction (proposal text, before the freeze):**
  - R-U6-1 should end when "the segment's final evaluation is recorded and its status is no longer PENDING", not
    at capture.
  - Under option (b): "no SW-A acquisition, computation or inspection of any data dated ≥ 2026-10-08 before
    2027-01-07 16:15 ET". Zone X2 data is acquired only within the single forward acquisition (R-U6-4).
  - The summary should use the same three verbs.
- **Blocks:** FREEZE, DA.

### U6-4. Historical and 2026 boundary arithmetic
- **Checked:** whether the historical zone's data bounds cover the windows its events need.
- **Evidence (FACT, proposal):**
  - zone H: "events with `s*` ≤ 2025-12-31" (`:663`);
  - R-U6-3: "bars `end ≤ 2025-12-31`" (`:672`);
  - zone X1: "2026-01-02 → 2026-10-07 | never evaluated" (`:664`);
  - the exit session is `x = s*+1+H`, with `H` = 20 (proposal §2.0).
- **Verdict: UNSUPPORTED (inconsistent).** An event with `s*` in December 2025 has its entry and its exit at
  `x = s*+21` in January or February 2026 (INF, calendar arithmetic). That data is then:
  - needed for `D(e)`, Δ₂ and TE1–TE3;
  - needed for the collision filter (Item 2.02 filings up to `x`);
  - needed for placebo windows `[p, p+H]` near the end of 2025;
  - **excluded** by zone X1;
  - **not acquired** under R-U6-3.
- **Owner decision required:**
  - (a) historical eligibility requires `x ≤ 2025-12-31`, and placebo windows require `p+H ≤ 2025-12-31`. Drop
    the rest and count them. This extends the audit's S9 rule (P1) to the historical test;
  - (b) extend the bar and EDGAR bounds to the latest needed `x` (about the end of February 2026), and declare
    those sessions "exit-window reads only". This conflicts with the "never evaluated" wording of zone X1 and
    widens the overlap with Stage H dates.
- **Recommended:** (a), as simpler and consistent with zone X1. It is not adopted.
- **Blocks:** FREEZE.

### U6-5. Does the proposal authorize access before the research hold is lifted?
- **Checked:** whether any proposal rule could be read as permission, and the status of the hold.
- **Evidence:**
  - FACT: no owner memo establishing the hold exists in the repository. A grep for "research hold" and OPEN-G2
    finds only references to it, in `docs/strategy-discovery-report-2026-11-02.md:44,354,387,391` and
    `docs/d1-s1-research-design-2026-11-02.md:89,620`.
  - OPEN-G2 is listed as an undecided item (D1/S1 `:620`).
  - The evidence inventory (§10) recommends the hold.
  - Proposal zone H requires "GV1 and U5 authorization" (`:663`).
  - R-U6-1 and R-U6-3 (`:656`, `:668`) are written as conditions on acquisitions they assume will happen.
- **Verdict: PARTIALLY SUPPORTED.**
  - Nothing in the proposal explicitly authorizes acquisition.
  - But R-U6-1 read alone ("until … capture time has passed") can be taken as permission after 2026-12-09
    regardless of the hold.
  - The hold is named only in the forward-start formula, not as a precondition for historical access.
- **Required correction:** add a rule **R-U6-0**:
  > "None of R-U6-1 to R-U6-4 authorizes any request. No SW-A EDGAR or market-data request of any date is made
  > until (i) the owner decides OPEN-G2 and (ii) a GV1 or SW-D authorization is recorded in the repository."

  Also record the research hold itself as a committed owner decision, because today it exists only by reference.
- **Blocks:** DA.

### U6-6. Forward-guided-proposal rule during the blind period
- **Checked:** whether SW-A design work during `fwd-gate2`'s blind period interacts with the "no forward-guided
  mutations" rule.
- **Evidence (FACT):**
  - DAY-22 §3.2.4 (`:156-157`): "Observations of market conditions … during the blind period shall not be used
    to propose protocol changes, branch forks, or new strategy variants."
  - v2.1 C17 (`:208`): "Unchanged and extended."
  - DAY-22 §3.2.3 restricts acquisition "into the research cache" (`:155`). The proposal's separate SW-A data
    tree (GV3) must not be read as an escape from that scope.
  - R-U6-1 is path-independent, which is correct.
- **Verdict: PARTIALLY SUPPORTED.**
  - The proposal does not address the C17 rule.
  - The SW-A documents state that no prices were seen. INF: SW-A is a new family, not a V2-MOM variant, and the
    design cites no forward observation.
  - There is no formal attestation record.
- **Owner decision required:**
  - (a) commit an attestation that the SW-A design uses no observation from the blind period; or
  - (b) defer the SW-A freeze commit until after the `fwd-gate2` evaluation.

  Either choice must also leave the tree clean at capture (OPS-1).
- **Blocks:** FREEZE (governance).

---

## 3. X3: stop formula and position sizing

### X3-1. Re-derivation
- **Checked:** the formula `S = C_i(s*) − (C_i(s*−1)/q_i(s*)) · AR_i(s*)` (proposal `:509`), derived from the
  draft's definitions.
- **Derivation (from the draft's definitions):**
  - The draft defines `r_i(k) = (C_i(k)·q_i(k) + d_i(k)) / C_i(k−1) − 1`
    (`docs/sw-a-research-design-2026-11-02.md:193`).
  - Here `q` is new shares per old share, and `d` is per pre-split share (protocol v2 §3.4).
  - `AR = r_i − r_m`.
  - Let `P*` be the post-split raw price at which the stock's total return since `C(s*−1)` equals SPY's
    reaction-day return:

    ```
    (P*·q + d) / C(s*−1) − 1 = r_m      ⇒  P* = [C(s*−1)·(1 + r_m) − d] / q
    C(s*)                                =  [C(s*−1)·(1 + r_i) − d] / q
    C(s*) − P*                           =  C(s*−1)·(r_i − r_m) / q  =  (C(s*−1)/q) · AR
    ```

  - So `S = P*` exactly, and the dividend `d(s*)` cancels.
  - Units: `C/q` is a price per post-split share and `AR` is dimensionless, so `S` is a price.
  - `S > 0` iff `1 + r_m > d / C(s*−1)`, which holds except in absurd cases (INF).
- **Verdict: SUPPORTED**, with one wording correction. The proposal's "measured in pre-event share units"
  (`:516`) should read: "`C(s*−1)/q(s*)` is the pre-event close expressed in **post-split** share units".
  `S` is the price at which the stock's total return since the pre-release close equals SPY's reaction-day
  return. That is "abnormal gain given back, **assuming SPY stays at its `Close(s*)` level**".
- **Blocks:** — (a wording fix at the next revision).

### X3-2. Corporate actions during the holding
- **Checked:** splits and dividends after `s*`.
- **Evidence:**
  - Splits: proposal §2.5 step 1, `S ← S/q`, is correct.
  - Dividends: the draft says "The stop is not adjusted for dividends" (draft §4.7). The audit lists this as
    X8 (i), rated P2.
- **Verdict: PARTIALLY SUPPORTED.**
  - On an ex-date the raw price falls by `d` while the holder receives `d` in cash. An unadjusted `S` can
    therefore trigger on a move with no economic loss.
  - This is part of the stop definition, so it should be decided at the **freeze** (P1), not before data
    acquisition (P2).
  - LIT [UNVERIFIED]: some brokers adjust resting stop orders on ex-dividend dates. The simulation must match
    the broker's actual behaviour, or disclose the difference.
- **Owner decision required:** dividend treatment of `S`: (a) unadjusted, with dividend-triggered stops
  counted; (b) `S ← S − d` on the ex-date; (c) follow the broker's documented rule. Also re-rate X8 (i) from P2
  to P1.
- **Blocks:** FREEZE.

### X3-3. Is `S` an executable raw-price level?
- **Checked:** what is known when, and how the order would be expressed.
- **Evidence:**
  - All inputs (`C(s*−1)`, `q(s*)`, `d(s*)`, the SPY close and SPY's ex-date-`s*` dividend) are known after
    `Close(s*)` (protocol v2 §3.3 information timing). So `S` can be placed as a resting stop before `O(e)`.
  - The X2 rule (proposal `:421-424`) does not act on an entry-session breach during session `e`.
- **Verdict: PARTIALLY SUPPORTED.** Three points are missing:
  - **(i) Tick rounding.** `S` must be rounded to $0.01, and the direction is unspecified. **Recommended:** round
    down (away from the price) and compute `N` from the rounded `S`.
  - **(ii) The live order sequence for X2.** A resting stop placed before `O(e)` would fire during session `e`.
    That is exactly the same-session round trip X2 removes. To match X2:
    - no resting stop during session `e`;
    - after the close of `e`, if `L(e) ≤ S`, submit a market-on-open sell for `e+1`;
    - otherwise place the resting stop from `e+1` onward.
  - **(iii) Implementation and testing.** The formula is NOT YET IMPLEMENTED. It needs a future-mutation test:
    no bar after `Close(s*)` may change `S` or `N`.
- **Required correction:** add (i) and (ii) to the frozen text.
- **Blocks:** FREEZE.

### X3-4. Behaviour for positive, negative and near-zero AR
- **Checked:** the formula's domain.
- **Evidence:** the eligibility rule is `z ≥ z0` with `z0 = 2` (draft `:228`); the sensitivity values are
  `z0 ∈ {1, 2, 3}` (draft §7.6).
- **Analysis:**
  - **AR > 0:** the distance `(C(s*−1)/q)·AR` is positive.
  - **AR ≤ 0:** `S ≥ E_plan`, so the formula is invalid. It is excluded **only** because every declared `z0` is
    positive. A future variant with `z0 ≤ 0`, or a two-sided `|z|` rule, would be incompatible with this stop.
  - **Near-zero AR:** `AR ≥ z0·σ`, but σ has no floor.
    - ASSUMPTION, arithmetic only: `σ = 0.5%` with `z0 = 1` gives AR ≥ 0.5%, so the notional share is about
      `0.005 / 0.005 = 100%` of capital. With `z0 = 2` it is about 50%.
    - The proposal's "up to about 31%" example (`:527-528`) uses `σ = 0.8%` and `z0 = 2` only.
- **Verdict: PARTIALLY SUPPORTED.**
- **Required correction:**
  - add an explicit eligibility guard: `AR(s*) > 0` and `E_plan − S ≥` one tick;
  - state that the stop is defined only for `z0 > 0`.
  - The near-zero case makes the notional cap mandatory (X3-6).
- **Blocks:** FREEZE.

### X3-5. Market-direction selection bias
- **Checked:** the claim that the size "no longer depends on the market's direction" (proposal `:85`, `:519-520`).
- **Analysis (INF):**
  - Eligibility and stop distance both use `AR = r_i − r_m` with β = 1.
  - For a stock with true β ≠ 1, `AR` contains `(β_i − 1)·r_m`.
  - On market-up days, high-β names get a mechanically larger AR: they are more often eligible, with larger stop
    distances and therefore smaller sizes. On market-down days the reverse holds. Low-β names behave the
    opposite way.
  - After entry, `S` is a fixed raw level. Stop-outs therefore correlate with market declines during the
    holding (trading estimand only).
  - `GAP_AT_ENTRY` events correlate with overnight market drops.
- **Verdict: PARTIALLY SUPPORTED (overstated).** X3 removes the **raw**-return market dependence of the original
  draft. It does not remove dependence that comes from β misspecification, or from the post-entry path.
- **Required correction:**
  - Rephrase the claim: "independent of market direction under β = 1; residual dependence through β ≠ 1 and the
    post-entry path".
  - Predeclare diagnostics (reporting only): eligibility rate, mean size and stop-out rate by sign and tercile of
    `r_m(s*)` and of SPY's return over the holding.
  - **Owner decision:** whether β-estimated AR (a draft alternative, estimated over `[s*−250, s*−21]`) should
    become the baseline or stay a sensitivity run. The audit lists S1 (β) as P1.
- **Blocks:** FREEZE.

### X3-6. Missing position-size caps and gap-risk controls
- **Checked:** which controls bound the realized risk under the proposed X1–X3.
- **Evidence and analysis:**
  - **(i) The per-position notional cap is optional.** The proposal says it "remains useful" (`:528`). Under X3,
    notional ≈ `0.5% / AR` with no lower bound on AR beyond `z0·σ` (X3-4). The cap should be **mandatory**, with
    the value set by the owner (R3).
  - **(ii) Risk overrun at the entry fill is uncontrolled.**
    - Sizing uses `E_plan = C(s*)` (draft `:312`), but the fill is `O(e)`.
    - Risk at fill / planned risk = `1 + (O(e) − C(s*)) / ((C(s*−1)/q)·AR)`.
    - Arithmetic only: AR = 2% with a +2% overnight gap gives about 2×, so about 1% of capital is at risk instead
      of 0.5%.
    - The proposal does not mention this.
    - Options:
      - (a) accept it, and report the risk-at-fill distribution;
      - (b) size on a conservative assumed entry `C(s*)·(1+g)`, with `g` owner-set;
      - (c) a limit-on-open buy that caps the entry price. This introduces gap-based selection, so it needs a
        new sensitivity label.
  - **(iii) Gap-down losses are reported but not bounded.** Exits below `S` and the X2 entry-breach exit at
    `O(e+1)` are reported (TE2) but have no portfolio-level stress control. Positions in the same earnings
    season gap together (INF).
  - **(iv) There are no portfolio caps.** The open-risk cap (R2, P3) and the gross-exposure cap (OPEN-R2g) are
    undecided. Without them, every simulation must be labelled "uncapped" (draft §5).
- **Verdict: UNSUPPORTED** as a complete sizing design.
- **Required owner decisions:**
  - make the notional cap mandatory and set its value;
  - choose a risk-at-fill rule from (a)–(c);
  - predeclare a portfolio gap-stress report: Σ notional × an owner-set hypothetical gap, per week.
  - R2 and R2g remain P3 and PL items.
- **Blocks:** FREEZE (notional cap, risk-at-fill rule); PL (portfolio caps).

### X3-7. Separation from the statistical estimands
- **Checked:** whether `S` enters H1 or H2.
- **Evidence:** proposal §2.3.1 (`:213-247`) defines `D(e)`, `D_net` and Δ₂ without any stop.
- **Verdict: SUPPORTED.** X3 affects only TE1–TE3 and the S7 step-7 consistency condition.
- **Blocks:** —

---

## 4. S7: statistical inference and power

### S7-1. Is a block length of `2(H+1)` justified?
- **Checked:** the dependence argument in the proposal (`:281-284`) and the choice `L = 2(H+1)` (`:287`).
- **Analysis:**
  - The proposal's argument gives a dependence range of `H` sessions, from overlapping windows, if daily ARs are
    serially uncorrelated. The **factor of 2 is a heuristic margin, not a derivation.**
  - Two further dependence channels are not covered (INF):
    - **(a) The regressor `z` reaches back further.** `z` of one event uses AR from sessions `[s*−61, s*]`. These
      can fall inside another event's drift window, because peers' reaction days fall within the same earnings
      season. For H1, dependence between regressor and error can extend over about `H + 61` sessions. It is
      likely weak, because it runs through a variance estimate and a single reaction day.
    - **(b) Volatility clustering.**
  - **How many dependent pairs a block boundary splits** (ASSUMPTION: pair distances uniform on 1…H):
    - with random block starts, a dependent pair at entry distance `h` is split with probability `h/L`;
    - the average is `(H+1)/(2L)`, which is about **0.25** for `L = 42`;
    - about a quarter of dependent pairs are resampled as independent;
    - if within-pair correlations are positive, the variance is biased downward.
  - **The trade-off:** a larger `L` splits fewer pairs but leaves fewer blocks. INF: about 12 blocks in the
    504-session validation segment at `L = 42`, and about 8 at `L = 63`. There is no data-free optimum.
- **Verdict: PARTIALLY SUPPORTED.**
- **Owner decision required:**
  - (a) keep `L = 2(H+1)` with this disclosure;
  - (b) `L = 63` (about one quarter, covering a season plus `H`);
  - (c) a method designed for few clusters over fixed calendar blocks, for example a wild cluster bootstrap
    (LIT [UNVERIFIED]).

  Whatever is chosen is frozen before data.
- **Blocks:** FREEZE.

### S7-2. The bootstrap algorithm is ambiguous
- **Checked:** whether the specification is executable without further choices.
- **Evidence:**
  - proposal `:285`: "**circular** block bootstrap over the XNYS sessions";
  - proposal `:290`: "Each event and each placebo window is **assigned to the block** that contains its entry
    session".
- **Verdict: UNSUPPORTED (ambiguous).**
  - "Assigned to the block" implies a **fixed partition**, which is a non-overlapping block bootstrap.
  - A circular block bootstrap draws **random start points** with wrap-around, so a session belongs to many
    possible blocks.
  - These two procedures give different intervals.
  - Also unspecified:
    - the number of blocks drawn per replicate;
    - the wrap-around rule;
    - whether the placebo weights `w_i` (proposal §2.3.1) are recomputed per replicate from the resampled `E+`;
    - the RNG and seed format.
- **Required correction:** a single algorithm statement. For example, for a circular block bootstrap:
  - draw `⌈N_sessions / L⌉` start indices uniformly on the circular session index;
  - each drawn block contributes every event and placebo window whose entry session lies in it;
  - recompute `w_i`, `μ_P`, Δ₂, β₁ and the momentum model per replicate;
  - use a fixed `B` and seed.
- **Blocks:** FREEZE.

### S7-3. Preservation of cross-sectional dependence and overlap
- **Checked:** what the resampling unit keeps together.
- **Analysis (INF):**
  - Within a drawn block, all events of all symbols with entry sessions in that block stay together. That keeps
    same-day cross-sectional dependence and overlap within the block.
  - Events and placebo windows are resampled jointly, which keeps their covariance on shared days.
  - Across block boundaries, dependence is broken (S7-1).
  - An earnings season (about 30 sessions, INF) can straddle a boundary.
- **Verdict: PARTIALLY SUPPORTED.**
- **Required correction:** disclose this in the frozen text, alongside the few-block caveat already in the
  proposal (`:299-301`).
- **Blocks:** FREEZE (disclosure only).

### S7-4. Does the confidence interval support the PASS rule's ">0" part?
- **Checked:** the ladder's step 6 (`:366`).
- **Analysis:**
  - PASS requires both `LB(β₁) > 0` and `LB(Δ₂) > 0`, each a one-sided 95% bound.
  - Requiring both is an intersection-union test, so the false-PASS rate under either null is at most 5%
    (LIT [UNVERIFIED], standard result).
  - The few-block undercoverage caveat applies and is disclosed in the proposal.
- **Verdict: SUPPORTED** for the claim "Δ₂ > 0 and β₁ > 0". It does **not** support "Δ₂ ≥ δ" (S7-5, S7-6).
- **Blocks:** —

### S7-5. Is `δ` economically meaningful, and is it part of acceptance?
- **Checked:** the `δ` definition (`:333-341`), step 6b (`:367`, `:379`), and `δ_β` (`:312`).
- **Analysis:**
  - **(i) `δ` is in acceptance only as a point-estimate test.** Step 6b is `Δ̂₂ < δ` → fail. Together with
    step 6, PASS means "statistically above 0 **and** the point estimate is at least δ". It does not mean
    "confidently at least δ".
  - **(ii) `δ` has no account-level meaning.** It is defined per event and in abnormal terms.
    - The account's contribution per year is about `n_trades/yr × (0.005 / mean AR) × Δ₂` (INF, ignoring caps
      and overlap).
    - The owner should set `δ` knowing this translation.
    - The proposal gives no such translation.
  - **(iii) `δ_β = δ / z0` ignores the intercept.** The H1 model has an intercept `β₀`, so the drift implied at
    `z0` is `β₀ + β₁·z0`, not `β₁·z0`. H1 is an information hypothesis, so attaching `δ` to its slope is not
    natural.
- **Verdict: PARTIALLY SUPPORTED.**
- **Owner decisions required:**
  - choose the semantics of `δ` in acceptance (see S7-6);
  - either drop `δ` from H1 (keeping significance only, with `n_min,1` based on a separately declared slope of
    interest) or set `δ_β` directly;
  - add the account-level translation to the `δ` definition.
- **Blocks:** FREEZE.

### S7-6. The power target does not match the PASS rule
- **Checked:** the `n_min` formula (`:311`) against the ladder (steps 6 and 6b).
- **Analysis (normal approximation; no data):**
  - `n_min,2` is chosen so that `SE = δ / 2.487`. That gives 80% power for `LB(Δ₂) > 0` when the true `Δ₂ = δ`.
  - At that `n`, `1.645·SE ≈ 0.66·δ < δ`, so **step 6b is the binding condition**.
  - Then `P(PASS | Δ₂ = δ) = P(Δ̂₂ ≥ δ) ≈ 0.5`, for **any** `n`.
  - So the step-2 power check ("underpowered unless `n ≥ n_min`") certifies 80% power for a condition that is
    not the binding PASS condition.
- **Verdict: UNSUPPORTED (mathematical mismatch).**
- **Owner decision required** (one of):
  - **(a) Keep "LB > 0 and point ≥ δ".** Declare a design alternative `Δ_A > δ` (the drift the owner considers
    plausible and worth detecting). Size `n` so that both `1.645·SE ≤ δ` and
    `n ≥ DEFF·(0.842·σ_D / (Δ_A − δ))²`. Power is then stated at `Δ_A`, not at `δ`.
  - **(b) Use "LB(Δ₂) > δ".** Power 0.8 is reached at `Δ_A = δ + 2.487·SE`, so
    `n = DEFF·(2.487·σ_D / (Δ_A − δ))²`.
  - **(c) Drop step 6b**, and use `δ` only as the power design value. `δ` then leaves the acceptance rule, which
    reverses the audit's S7 requirement and so needs explicit owner acceptance.

  Under every option, the label "INCONCLUSIVE (underpowered)" must refer to the power of the **actual** PASS
  rule.
- **Blocks:** FREEZE.

### S7-7. Status of "about 220 events"
- **Checked:** the arithmetic and the labels at proposal `:100-101` and `:324`.
- **Evidence:**
  - `(2.487 × 6% / 1%)² ≈ 222.7` is correct.
  - The table is labelled "ASSUMPTION ONLY, not estimates, no data used" (proposal §2.4.2).
  - The summary says "ASSUMPTION-based arithmetic only".
  - The comparison bound "at most about 200 events" (25 × 4 × 2) is correctly marked INF.
- **Verdict: PARTIALLY SUPPORTED.** It is correctly presented as illustrative. It is optimistic in three ways:
  - `σ_D = 6%` has no source (ASSUMPTION);
  - `DEFF = 1` assumes no clustering inflation, while any positive within-block correlation raises `n`;
  - under S7-6, about 223 events gives about a 50% chance of PASS at `Δ₂ = δ`, not "detection" in the sense of
    the PASS rule.
- **Required correction:** relabel it as "an illustrative **lower bound** under `DEFF = 1`, for the `LB > 0`
  condition only; not a requirement". Recompute the illustration under whichever S7-6 option is chosen.
- **Blocks:** FREEZE (wording; the correction depends on S7-6).

---

## 5. Required corrections and owner decisions (consolidated)

| # | From | Type | Item |
|---|---|---|---|
| 1 | U6-2 | owner or protocol decision | Record whether v2.1 §6 rows `:118–119` and C15 lapsed with the `fwd-gate` supersession. Fail-closed until then |
| 2 | U6-3 | correction | R-U6-1 ends at "final evaluation recorded", not at capture. Under (b): no acquisition, computation or inspection of data dated ≥ 2026-10-08 before 2027-01-07 16:15 ET. Harmonize the summary wording |
| 3 | U6-4 | owner decision | Historical eligibility `x ≤ 2025-12-31` (recommended), or extended exit-window bounds |
| 4 | U6-5 | correction | Add R-U6-0 ("no rule authorizes; nothing is requested before OPEN-G2 and a GV1 or SW-D record"). Commit the research hold as an owner decision |
| 5 | U6-6 | owner decision | A blind-period attestation for the SW-A design, or deferring the SW-A freeze until after the `fwd-gate2` evaluation |
| 6 | X3-1 | wording | "post-split share units"; "assuming SPY stays at its `Close(s*)` level" |
| 7 | X3-2 | owner decision | Dividend treatment of `S`. Re-rate X8 (i) from P2 to P1 |
| 8 | X3-3 | correction | Tick-rounding rule; live order sequence matching X2 |
| 9 | X3-4 | correction | Guard `AR > 0` and a distance of at least one tick; stop defined only for `z0 > 0` |
| 10 | X3-5 | correction + owner decision | Rephrase the market-direction claim; predeclare diagnostics; β-estimated AR as baseline or sensitivity |
| 11 | X3-6 | owner decisions | Mandatory notional cap and its value; risk-at-fill rule; gap-stress reporting |
| 12 | S7-1 | owner decision | Block length / method: `2(H+1)`, 63, or a few-cluster method |
| 13 | S7-2 | correction | One executable bootstrap algorithm (start points, wrap, `w_i` per replicate, `B`, seed) |
| 14 | S7-3 | correction | Disclose dependence broken at block boundaries |
| 15 | S7-5 | owner decisions | `δ` semantics; `δ` on H1 or not; account-level translation |
| 16 | S7-6 | owner decision | Power-to-rule alignment: option (a), (b) or (c) |
| 17 | S7-7 | correction | Relabel the 220 illustration; recompute after #16 |

None of these is applied. The proposal file is unchanged.

---

## 6. Limitations of this audit

- **Same author as the proposal.** See the box at the top.
- **Code was not read beyond constants.** `acquisition/v2/contract.py` was inspected by grep only. Whether
  `FORWARD_WINDOW` (`:112`) is still read by any enforcement path is unknown. `stage_f.py` and
  `backtest/v2/forward.py` were not read.
- **Some files were checked only at the status line.** The v2.0.1–v2.0.4 amendments and the DAY-23 audit were
  checked for status or scope only, not traced in full.
- **The few-block arithmetic is approximate.** The ~25% split share (S7-1) assumes uniformly distributed pair
  distances. Normal approximations are used in S7-6.
- **No data was used.** Every numeric example is arithmetic on ASSUMPTION values.

## 7. Acceptance status

| Criterion (task brief) | Status |
|---|---|
| Each issue states what was checked, evidence and location, verdict, correction or decision, and blocking status | PASS (§2–§4) |
| The amendment chain is traced, adopted versus superseded | PASS (U6-1) |
| The source and meaning of 2027-01-07 are verified | PASS (U6-2) |
| Historical data, forward events and pending blind segments are distinguished | PASS (U6-3, U6-4) |
| Accidental pre-hold authorization is assessed | PASS (U6-5) |
| X3 re-derived; units, corporate actions, executability, sign behaviour, selection bias, caps | PASS (X3-1 to X3-6) |
| S7: block-length justification, dependence, CI versus PASS, `δ`, the 220 status | PASS (S7-1 to S7-7) |
| No silent modification or approval | PASS: the proposal, audit and draft are unchanged |

## 8. Safety confirmation

- Only this file was created. No code, config or existing document was modified. Nothing was staged, committed
  or pushed.
- No API call, network access, data acquisition, test, backtest, simulation or optimization was run.
- Not accessed: Stage R, H or F data, `paper_state/`, P001, `fwd-gate2` results, or the DAY-26C incident record.
- Files read for this audit: the three SW-A documents; DAY-16, DAY-22, DAY-24, DAY-26A, v2.1–v2.5 amendment and
  adoption texts and records (status and the relevant sections); the v2.0.1–v2.0.4 status lines; the
  `contract.py` constants (grep); and grep results for the research hold.
- **Operational:** this file, the audit and the proposal are untracked. `fwd-gate2` capture refuses untracked
  files (`stage_f.py:322-323`, as cited in D1/S1 §0.5). All three must be committed or removed before 2026-12-09
  16:15 ET.
