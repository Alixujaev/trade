# SW-A: Independent review of the P0 resolution proposal and its self-audit (2026-11-03)

INDEPENDENT REVIEW — NOT APPROVED FOR EXECUTION

> - Reviewed: `docs/sw-a-p0-resolution-proposal-2026-11-03.md` ("the proposal") and
>   `docs/sw-a-p0-consistency-audit-2026-11-03.md` ("the self-audit"), against the draft
>   `docs/sw-a-research-design-2026-11-02.md` ("the draft"), the gap audit
>   `docs/sw-a-decision-gap-audit-2026-11-03.md` ("the gap audit") and the primary protocol, decision and code files
>   listed in §9.
> - The proposal, the self-audit and the gap audit were treated as claims to check, not as evidence.
> - This review approves nothing, makes no owner decision and makes no profitability claim.
> - No code was run. No data, price, API, test, preflight, acquisition, backtest or simulation was used. Every
>   number below is algebra or arithmetic on values labelled ASSUMPTION.
> - The only file written is this one. It is untracked. `acquisition/v2/stage_f.py:322-323` refuses the
>   `fwd-gate2` capture while any untracked file exists, so this file adds to OPS-1 (see §7, B0).

**Labels:**
- **FACT**: read in the cited file and line.
- **DERIVATION**: the reviewer's own algebra or arithmetic.
- **JUDGMENT**: the reviewer's opinion.
- **RECOMMENDATION**: a proposed change. Nothing here is adopted.
- **ASSUMPTION**: an illustrative value, not data.
- **UNVERIFIED**: could not be checked from accessible files. **LIT [UNVERIFIED]** marks general or literature
  knowledge from memory.

**Verdict scale (for claims):** SUPPORTED / PARTIALLY SUPPORTED / CONTRADICTED / UNVERIFIABLE.

---

## 1. Executive verdict

1. **The SW-A design is not ready to freeze.** The proposal improves the draft considerably, and it corrects the gap
   audit's main factual error on U6. Several of its resolutions are still incomplete, and two contain errors that
   the self-audit did not find.
2. **Verified as correct:**
   - the adopted amendment chain DAY-16 → v2.0.1–v2.0.4 → DAY-22 → v2.1 → v2.2 → v2.3 → v2.4, with v2.5 not adopted
     (§3.1, table A1);
   - the X3 stop formula `S = C(s*) − (C(s*−1)/q(s*))·AR(s*)`. It equals
     `[C(s*−1)·(1 + r_m(s*)) − d(s*)] / q(s*)` (§3.2);
   - the X1 ordering defect and its correction, and the X2 finding that the draft's entry-session stop contradicts
     the draft's own D12 statement;
   - the separate `SWA_*` timing vocabulary (T1), which leaves the 2026 calendar files untouched;
   - a standalone SW-A protocol (GV3).
3. **New problems that neither the proposal nor the self-audit reports:**
   - **The acceptance rule passes a true effect of exactly `δ` with probability at most 0.5 in each segment.** The
     sequence requires two historical PASSes, so the probability is at most 0.25. With the forward gate added, it is
     at most 0.125 (DERIVATION, §3.3.3). The self-audit found the 0.5 per segment but not the compounding.
   - **The forward confirmation is probably not reachable within a few years.** Under stated assumptions,
     reaching `n_min` with forward events takes about 2.5 to more than 20 years (§3.3.4). The draft calls the
     forward test "the only path to 'confirmed'" (draft `:443`).
   - **The proposal's open-to-open return `R^oo` handles splits and dividends incorrectly** when both fall inside
     the 20-session window. It copies the protocol v2 §3.4 dividend carry formula, which does not match protocol v2
     §11.2 share accounting over multi-event intervals (DERIVATION, §3.3.2).
   - **The GV3 inheritance list includes protocol v2 §3.9 "overlap control".** Applied to a 2016–2025 SW-A snapshot,
     that rule means reading Stage R and Stage H files, which the draft forbids (§2, GV3).
   - **The placebo filter is asymmetric, and it conditions on future filings** (§3.3.2).
   - **The U6 rules leave three gaps:**
     - no rule on `paper_state/` (V2-MOM-P001) market data;
     - no defined record that ends `fwd-gate2`'s PENDING status;
     - a forward boundary that differs from the D1/S1 design's boundary (§3.1).
   - **The draft's collision rule can produce an entry and an exit at the same open** when an Item 2.02 filing is
     accepted after `Close(s*)` and before `Open(s*+1)` (§2, X1/X2).
4. **The self-audit is mostly accurate.** Of its 20 findings:
   - 17 are supported;
   - 2 are partly overstated (S7-2, S7-5(iii));
   - 1 is incomplete (S7-6).

   Its status line says "INDEPENDENT AUDIT" (self-audit `:3`), but the text says the proposal's author wrote it
   (`:13-16`). It is a self-review.
5. **No document reviewed authorizes any data acquisition.** The research hold (OPEN-G2) and the scope of SW-A
   approval (GV2) are undecided. Neither has a committed owner record (§3.1.5).

---

## 2. Review of the 11 P0 items

| ID | Proposal resolution (proposal line) | Reviewer verdict | Main reason | Blocks freeze? |
|---|---|---|---|---|
| GV2 | design-only approval (`:147-156`) | SUPPORTED as framing | the hold's scope (research vs acquisition) is undefined | yes, owner decision |
| S2 | H1 on `AR^oo(e,x)` (`:182-193`) | PARTIALLY SUPPORTED | window alignment correct; `R^oo` dividend/split accounting wrong | yes |
| S4 | `Δ₂` minus a symbol-matched placebo (`:213-246`) | PARTIALLY SUPPORTED | asymmetric filters; future-filing conditioning; time mismatch | yes |
| S7 | decision ladder, bootstrap, `n_min` (`:279-405`) | PARTIALLY SUPPORTED; power claim CONTRADICTED | P(PASS at `δ`) ≤ 0.5 per segment and ≤ 0.25 over two; ambiguous algorithm | yes |
| X1 | corrected algorithm (`:418-449`) | SUPPORTED | correct; one gap (a filing between `Close(s*)` and `Open(e)`) | yes (text) |
| X2 | breach on `e` → exit at `O(e+1)` (`:462-488`) | SUPPORTED | no same-session round trip, except the pre-open collision case | yes (text, adviser for PL) |
| X3 | abnormal-reaction stop (`:508-538`) | PARTIALLY SUPPORTED | formula correct; controls incomplete; market-direction claim overstated | yes |
| T1 | `SWA_VERIFIED` V1–V6 (`:556-574`) | PARTIALLY SUPPORTED | V4 too strict for near-simultaneous filings | yes |
| T2 | tiers 1a/1b/2/3/C (`:604-622`) | PARTIALLY SUPPORTED | tier-3 access and licence UNVERIFIED; tier-C conflict handling unstated | yes |
| U6 | forward after 2027-01-07; R-U6-1..4 (`:650-695`) | PARTIALLY SUPPORTED | chain correct; end condition, zones and gaps inconsistent | yes |
| GV3 | standalone `SWA-1.0` (`:705-743`) | PARTIALLY SUPPORTED | right choice; rationale misplaced; inheritance list conflicts | yes |

### GV2: SW-A priority
- **FACT:** the gap audit lists GV2 as an owner choice (`:909-911`). The discovery report recommends SW-A (OD-3,
  `docs/strategy-discovery-report-2026-11-02.md:441`). No owner decision was found (§8).
- **FACT:** the evidence inventory recommends holding "all new strategy research and experiments" until the
  `fwd-gate2` evaluation (`docs/strategy-evidence-inventory-2026-10-17.md:158-159`). The D1/S1 design reads the hold
  as covering acquisitions and runs only (`docs/d1-s1-research-design-2026-11-02.md:91-93`).
- **JUDGMENT:** the proposal's option (a), "design completion only", is a sound framing. It is consistent with the
  hold only if the owner states that design work is outside it. Classification: **SUPPORTED** as framing; the hold
  scope is a missing dependency (§6, O2).

### S2: drift window versus traded window
- **FACT:** the draft defines `D(e) = Σ_{k=s*+1}^{s*+H} AR_i(k)` (`:410`), with close-to-close daily returns
  (`:193`, `:214`). The trade runs from `O(s*+1)` to `O(s*+1+H)` (`:248-259`).
- **DERIVATION:** `AR(s*+1)` covers `C(s*) → C(s*+1)`, and `AR(s*+H)` covers `C(s*+H−1) → C(s*+H)`. So `D(e)` spans
  `C(s*) → C(s*+H)`. It includes the untradable overnight move `C(s*) → O(s*+1)` and omits the traded overnight move
  `C(s*+H) → O(s*+H+1)`. The gap audit (`:384-400`) is correct.
- **JUDGMENT:** moving H1 to the traded window is defensible. It changes H1 from "does drift exist after the
  decision close" to "does tradable drift exist". The owner should choose this knowingly (proposal `:192-193` says
  so).
- **Problem:** `R^oo` (proposal `:134-135`) mis-credits dividends when a split and a dividend fall in the same
  window (§3.3.2). Classification: **PARTIALLY SUPPORTED**.

### S4: H2 estimand and baseline
- **FACT:** the draft's P2 quantity is undefined (`:412`). Protocol v2 states that on these survivors a long-only
  mean is expected to be positive without skill (`artifacts/day16/research-protocol-v2.md:457`). The gap audit
  (`:417-438`) is correct.
- **JUDGMENT:** a symbol-matched placebo is a reasonable control for symbol-level survivorship. Six defects are
  listed in §3.3.2. Classification: **PARTIALLY SUPPORTED**.

### S7: acceptance logic
- See §3.3. The ladder fixes the draft's missing interval, precedence and sequencing rules.
- **CONTRADICTED:** the proposal's power check (`:311`, `:362`) certifies 80% power for "`LB > 0`". The binding
  PASS condition is "point estimate ≥ `δ`" (`:367`, `:379`), whose power at `Δ₂ = δ` is 50%.
- Classification: **PARTIALLY SUPPORTED** overall.

### X1: exit ordering
- **FACT:** the draft's order is `O ≤ S` → `L ≤ S` → time exit (`:277-279`).
- **DERIVATION:** on `t = x`, if `O(x) > S` and `L(x) ≤ S`, the draft records an exit at `S`. The market-on-open sell
  has already filled at `O(x) > S`, so the recorded loss is too large by `O(x) − S` per share. The gap audit
  (`:567-575`) is correct. The proposal's algorithm (`:420-434`) removes the low check on `x`.
- **Gap (new):** the draft's collision rule exits "at the first open after `T_acc`" (`:289-291`). If a new
  Item 2.02 filing is accepted after `Close(s*)` and before `Open(e)`, that open is `O(e)`, the entry open itself.
  The proposal's trading algorithm flags only triggers "during e" (`:423`). Its statistical filter `E+` (`:216`)
  covers this case for H2 only.
- **RECOMMENDATION:** cancel the entry order when such a filing exists. This is executable, because the filing is
  known before the open. Classification: **SUPPORTED**, with this addition.

### X2: entry-session handling and D12
- **FACT:** D12 asks whether day trading is permissible under T+1 and the possession rules; status ADVISER_REQUIRED
  (`docs/shariah/AAOIFI_MVP_DECISIONS.md:42`). The draft says D12 "does not apply" (`:455`), but its entry-session
  rule sells at `S` on the purchase session (`:282`). The gap audit's X2 (`:577-591`) is correct, and the draft's
  statement is **CONTRADICTED** for those trades.
- **DERIVATION:** under the proposal's option (c) (`:462`, `:421-424`), every exit is priced at `O(t)` or `S` with
  `t ≥ e+1`. No simulated position is bought and sold in one session, except in the pre-open collision case above.
- **FACT:** D12's rationale records a reading that "resale is permitted once daman (liability) has passed, even
  before final settlement" (`:42`). It is not a ruling. The proposal states that D12 is not settled for a sale at
  `O(e+1)` (`:476-481`). That is correct.
- **JUDGMENT:** live execution must match: no resting stop during `e` (self-audit X3-3(ii), `:272-275`).
  Classification: **SUPPORTED**.

### X3: stop and sizing
- See §3.2. The formula is correct. Controls are missing, and the market-direction claim (`:519-520`) is overstated.
  Classification: **PARTIALLY SUPPORTED**.

### T1: definition of `VERIFIED`
- **FACT:** `config/earnings_calendar_sources.csv` has 26 data rows (lines 2–27):
  - `timing_class`: 18 AMC, 6 BMO, 1 UNVERIFIED (PEP, line 23), 1 empty (MU, line 14);
  - `timing_status`: 23 VERIFIED, 1 UNVERIFIED, 1 NOT_EARNINGS (TSLA, line 8), 1 VERIFIED_NO_EARNINGS_IN_WINDOW.

  These match draft §0.2 (`:36-42`). No column records release-time evidence, and the 23 VERIFIED rows have empty
  notes.
- **DERIVATION:**
  - The 18 AMC rows have `accepted_et` between 16:01:35 (QCOM, line 12) and 16:35:52 (TSLA, line 9).
  - The 5 VERIFIED BMO rows have `accepted_et` between 06:30:38 (JPM, line 26) and 07:49:04 (JNJ, line 25).
  - For every VERIFIED row, the class equals the class implied by `accepted_et` alone. The file cannot show whether
    `VERIFIED` meant anything more.
  - This supports draft U2 (`:62`) and the case for a separate vocabulary. The discovery report's statement that a
    point-in-time "data method … already exists" (`:33-34`) is **PARTIALLY SUPPORTED**: the timestamps exist, but a
    `T_rel` method does not.
- **Problem (V4, proposal `:564`):** V4 requires `T_acc ≥ T_rel`. AMC acceptances in the CSV come as early as
  16:01:35. A release stating "4:05 p.m." filed at 16:01 would fail V4 and be excluded. LIT [UNVERIFIED]: an 8-K is
  publicly disseminated at or shortly after acceptance. If so, the information became public at the earlier of the
  two times.
- **RECOMMENDATION:** classify the session from `T_pub = min(T_rel, T_acc)`. Mark an event UNRESOLVED only when the
  two times imply different session classes, and count those cases.
- **Minor:** draft U1 says "PEP shows that acceptance and the release can be on different dates" (`:61`). The CSV
  note (line 23) shows acceptance (07-08) against the EDGAR **filing** date (07-09), with an unknown release time. It
  does not show that the release date differs: **PARTIALLY SUPPORTED**.
- Classification of the proposal's T1: **PARTIALLY SUPPORTED**.

### T2: evidence tiers
- **JUDGMENT:** the precedence rule "fills absence; never overrides a contradiction" (proposal `:612-614`) is sound.
  Two points remain:
  - historical access to newswire timestamps, and their licence, are UNVERIFIED (the proposal says so, `:624-625`);
  - the text does not say what a disagreement with a tier-C item (call time) does. Only `T_acc` has a rule (V4).
- Classification: **PARTIALLY SUPPORTED**.

### U6: data isolation
- See §3.1. Classification: **PARTIALLY SUPPORTED**.

### GV3: protocol home and inheritance
- **FACT:**
  - "v2 governs only the v2 families defined here" (`artifacts/day16/research-protocol-v2.md:11`).
  - §14 lists three families and defines every change as a new experiment (`:472-476`).
- **FACT:** the capture preflight runs these checks:
  - `check_forward_access` (`acquisition/v2/stage_f.py:320`);
  - a clean tree (`:322-323`);
  - `protocol_identity()` (`:324`);
  - the v2.0.4 files diffed against their commit (`:325-327`).

  v2.2 describes the identity check as "DAY-16 + v2.0.1–v2.0.3 at their commits"
  (`artifacts/day26d/protocol-v2.2-amendment.json:50`). `check_config_sha` hashes blocks of the DAY-16 JSON
  (`backtest/v2/forward.py:166-174`).
- **DERIVATION:**
  - Editing any of those existing files would make the capture refuse.
  - A new file in a new folder is not checked by the code read here. `protocol_identity()` lives in `stage_r.py`,
    which was not read, so this is UNVERIFIED.
  - The proposal's "could interfere" (`:711-713`) holds for edits, not for an append-only new file.
- **JUDGMENT:** a standalone protocol is still the right choice. The stronger reasons are DAY-16 `:11` and §14 (family
  list, trial count), not the preflight.
- **Problems in the inheritance list (proposal `:724-733`):**
  - **(i) §3.9 overlap control conflicts with the no-read rule.** It compares overlapping ranges of different stages
    "cell by cell" (`research-protocol-v2.md:199`). The code precedent compares Stage F with the Stage H snapshot
    (`stage_f.py:180-181`, `:231`). An SW-A 2016–2025 snapshot overlaps Stage R and Stage H dates. Inherited
    unchanged, §3.9 would require reading Stage R/H files, which the draft forbids (`:375`). The inheritance must
    restrict overlap control to SW-A's own snapshots.
  - **(ii) §3.4's dividend carry formula** is defective over multi-event intervals (§3.3.2).
  - **(iii) v2.4 rule 2** applies a pin only if "`new_symbol` is a Stage R entity" (`protocol-v2.4-amendment.md:37`).
    Whether that entity set is a constant or is read from Stage R data is UNVERIFIED. Reuse must not read Stage R
    data.
- Classification: **PARTIALLY SUPPORTED**.

---

## 3. Detailed analysis

### 3.1 U6: data isolation

#### 3.1.1 Amendment chain (table A1)

| Step | Status evidence (FACT) | Date and forward effect (FACT) | Classification |
|---|---|---|---|
| DAY-16 v2.0 R1 | banner "REVISED DRAFT — PENDING REVIEW AND COMMIT" (`day16/research-protocol-v2.md:7`); frozen at `ba3cefe` (`acquisition/v2/contract.py:3,19`; DAY-22 `:12`) | forward = 252 sessions after the freeze (`:160-162`); "No data dated after the freeze commit may be acquired or inspected before the forward period has ended" (`:169`); Stage R/H/F ranges (`:195-197`) | ADOPTED (the banner is stale). Forward length and the `:169` data rule SUPERSEDED by v2.1 (C1, C3, E1, E3). Stage R/H ranges in force |
| v2.0.1 | banner "DRAFT — PENDING COMMIT" (`day17a/…:6`); commit `ed034b3` (`contract.py:4,20`) | corporate-action window, identity, dividend basis C3 (`:97-99`); no date change (`:15`) | ADOPTED (banner stale) |
| v2.0.2 | banner DRAFT (`day18a/…:7`); commit `0ebb606` (`contract.py:21`) | precision rule; no date change (`:20`) | ADOPTED |
| v2.0.3 | banner DRAFT (`day18c/…:7`); commit `d26b36e` (`contract.py:26`) | precision, review records; no date change (`:19`) | ADOPTED |
| v2.0.4 | banner DRAFT (`day18j/…:9`); commit `71dbfa2` (`contract.py:31`); "v2.0.4 accepted as finalized" (`day18l/…:11`) | exact evaluation; no date change | ADOPTED |
| DAY-22 | signed off 2026-10-08 (`day22/…:5-6`) | §3.1 2026-10-08 → 2027-10-08 (`:132-135`); §3.2.1–§3.2.4 (`:138-157`) | §3.1 SUPERSEDED (v2.1 C13, E1). §3.2.2 amended (C15). §3.2.3 amended "per segment" (C16). §3.2.1 unchanged (C14). §3.2.4 "unchanged and extended" (C17), so it is in force |
| DAY-23 | audit, "protocol left unchanged" (`day23/…:13`) | — | not a rule |
| DAY-24 | "PROPOSED AMENDMENT — NOT YET EFFECTIVE" (`day24/…:3-4`) | 63 sessions | UNADOPTED; superseded (v2.1 `:39`, C21 `:212`) |
| DAY-26A | "PROPOSED — NOT EFFECTIVE" (`day26a/…:3`) | 21 sessions | UNADOPTED; superseded (v2.1 `:40`, C22 `:213`) |
| v2.1 | ADOPTED 2026-10-10T12:52:51Z (`day26b/protocol-v2.1-amendment.md:3`; adoption md `:5-9`; adoption json `:5`) | window 2026-10-08 → 2027-01-07 (`:11`); §6 permissions (`:113-120`); C3, C13, C15–C17 (`:194`, `:204-208`); after the incident, `fwd-diag` INVALID and `fwd-gate` PENDING (`:317-318`) | ADOPTED. `fwd-diag` INVALID (final). `fwd-gate` SUPERSEDED by v2.2. §6 rows `:118-119` and C15 not textually revoked (§3.1.2) |
| v2.2 | ADOPTED 2026-10-10T14:56:30Z (`day26d/protocol-v2.2-amendment.md:3`; adoption json `:5`); append-only (`:4`; json `:13`) | `fwd-gate` "SUPERSEDED … never acquired or evaluated" (`:24`); `fwd-gate2` 2026-10-12 → 2026-12-09, capture ≥ 2026-12-09 16:15 ET (`:11-12`, `:41-50`); Stage F 2025-01-02 → 2026-12-09 (`:34`) | ADOPTED, in force |
| v2.3 | ADOPTED 2026-10-10T15:47:33Z (`day27/…:3`; json `:4`) | P001 sealed to 2026-12-09 16:15 ET (`:13`); "continues indefinitely" (`:12`); early disclosure invalidates `fwd-gate2` (`:26`) | ADOPTED, in force |
| v2.4 | ADOPTED 2026-10-13T07:05:10Z (`day27a/…:3`; json `:4`) | identity alias only; no data-window change (`:14`) | ADOPTED, in force |
| v2.5 | "DRAFT — NOT ADOPTED" (`day27b/…:3`); `PROPOSED_NOT_ADOPTED` (json `:4`) | paper-runner observability only | UNADOPTED |

**Related facts:**
- The v2.1 adoption JSON still records `fwd-gate` as PENDING, with "next data acquisition: Stage F-G after
  2027-01-07 16:15" (`protocol-v2.1-adoption.json:135-139`). The v2.2 record overrides that (`protocol-v2.2-adoption.json:28-32`).
- The code reads v2.1 first and then overlays v2.2 (`backtest/v2/forward.py:114-122`).
- Classification of the proposal's and the self-audit's chain (proposal `:54-58`, `:636-645`; self-audit U6-1): **SUPPORTED**.
- Classification of the gap audit's "three statements … disagree" (`:104-111`, `:749-758`): **CONTRADICTED**. The
  disagreement is resolved by the adopted v2.1 (C13, C16) and v2.2. The gap audit's fail-closed default of 2027-10-08
  (`:767-768`) has no current basis.

#### 3.1.2 v2.1's 2027-01-07 rules, v2.2, and the code
- **FACT (v2.1):**
  - row `:118`: "2026-11-06 → 2027-01-07 16:15 … any data dated ≥ 2026-11-06 | no | no | no";
  - row `:119`: Stage F-G once after 2027-01-07 16:15;
  - C3 (`:194`): "Data dated ≥ 2026-11-06: after 2027-01-07 16:15";
  - C15 (`:206`): "Binding for all `fwd-gate` data until 2027-01-07 16:15".
- **FACT (v2.2):** supersedes the **segment** `fwd-gate` (`:24`). It does not modify the v2.1 files (`:4`; json
  `:13`). D4 authorizes acquiring data dated up to 2026-12-09, at 2026-12-09 (`:34`).
- **DERIVATION:** D4 permits acquiring, on 2026-12-09, data dated 2026-11-06 → 2026-12-09. The literal row `:118`
  forbids that until 2027-01-07. Because v2.2 was adopted later, it overrides row `:118` at least for the
  `fwd-gate2` capture (INF, later rule prevails). v2.2 says nothing about data dated 2026-12-10 → 2027-01-07, nor
  about C15.
- **Conclusion:** v2.2 **superseded** the segment. It **overrode in part** row `:118`. It **left textually in force**
  rows `:118-119`, C3 and C15. Whether those lapsed is **UNRESOLVED** until the owner records it. The self-audit's
  U6-2 is **SUPPORTED**.
- **Code (FACT):**
  - `FORWARD_WINDOW = (2026-10-08, 2027-01-07, 63)` (`contract.py:112`) is imported at `forward.py:28`.
  - It is used only in `forward_split()` (`forward.py:59-69`).
  - `check_forward_access` refuses `fwd-diag` (`:221-223`), and refuses any segment whose status does not start with
    PENDING (`:224-226`). `fwd-gate` is SUPERSEDED.
  - `forward_split()` is called only for segments other than `fwd-gate2` (`:232-233`).
- **DERIVATION:** within these three files, no reachable path enforces the 63-session constant. It is inert. Other
  modules (`backtest/v2/run.py`, `data.py`, `paper/`, tests) were not read: UNVERIFIED. This resolves the open point
  in proposal `:691` and self-audit `:527-529`, within the files read.
- **FACT:** these guards protect only V2 Stage F capture, validation and runs. No code guards another family's
  acquisition. For SW-A, enforcement is procedural.
- **JUDGMENT on jurisdiction:** v2 binds only V2 families (`research-protocol-v2.md:11`). The V2 rules reach SW-A
  through the shared data: the same 25 symbols plus SPY.
  - If SW-A acquired bars dated inside `fwd-gate2`, that would be an acquisition of the gate's data.
  - v2.2 says "Nothing is acquired, computed or inspected during the blind period" (`:58`).
  - v2.1 defines the breach status by the data, not by who acquired it (`:169`). It is carried to `fwd-gate2` by the
    v2.2 labels (`:32`). INF.

#### 3.1.3 Date boundaries relevant to SW-A

| Kind | Boundary | Source (FACT) |
|---|---|---|
| Historical | SIP 1Day history starts 2016-01-04 | `artifacts/day17/day17-data-blockers.md:93` |
| Historical | Stage R bars and events 2016-01-04 → 2022-12-30; research segment 2017-02-01 → 2022-12-30 | `research-protocol-v2.md:195`, `:157`; `contract.py:51-52` |
| Historical | Stage H 2021-01-04 → 2026-06-02; holdout 2023-01-03 → 2026-06-02 | `:196`, `:158`; `contract.py:64-65` |
| Historical | Excluded period 2026-06-03 → freeze-commit date (2026-10-07); `STAGE_H_ASOF` 2026-10-07 | `:159`, `:167`; `contract.py:72` |
| Historical (SW-A draft) | development 2016-04 → 2019-12-31 (Stage R dates); validation 2020-01-02 → 2021-12-31 (R dates; 2021 also H); test 2022-01-03 → 2025-12-31 (2022 in R∩H; 2023–2025 holdout dates); 2026-01-02 → hold lift excluded | draft `:363-375` |
| Blind | exposed sessions 2026-10-08, 2026-10-09 | `contract.py:122`; v2.2 D3 `:33` |
| Blind | `fwd-diag` 2026-10-08 → 2026-11-05: INVALID (final) | v2.1 `:317`; v2.2 `:23` |
| Blind | `fwd-gate2` sample 2026-10-12 → 2026-12-09; capture ≥ 2026-12-09 16:15 ET; Stage F 2025-01-02 → 2026-12-09 | v2.2 `:11-12`, `:34`, `:48-49` |
| Blind | P001 from 2026-10-12, sealed to 2026-12-09 16:15 ET, continues indefinitely, own live-data path | v2.3 `:12-13`, `:23` |
| Blind | the citing document says P001 stores raw bars under `paper_state/data/…` (not opened; **UNVERIFIED**) | v2.5 `:103-104` |
| Textual | old `fwd-gate` 2026-11-06 → 2027-01-07 SUPERSEDED, but v2.1 row `:118` and C15 still name 2027-01-07 16:15 | v2.2 `:24`; v2.1 `:118`, `:206` |
| Future | SW-A forward: draft "after the freeze and the end of the hold, not earlier than after the `fwd-gate2` evaluation" | draft `:371` |
| Future | SW-A forward: proposal "first session after max(freeze, 2027-01-07, hold-lift)" | proposal `:666` |
| Future | D1/S1: no data ≥ 2026-10-08 before the `fwd-gate2` evaluation; after that, OPEN-G2 | D1/S1 `:87-89` |

- **DERIVATION:** the proposal (2027-01-07) and D1/S1 (the `fwd-gate2` evaluation) set different boundaries for
  non-V2 families. One project-level rule should cover both (§5, C3).

#### 3.1.4 Four milestones that must not be confused
1. **Capture completion:** the Stage F snapshot is written once. Earliest 2026-12-09 16:15 ET (v2.2 `:49`, `:59`). The
   code checks time ≥ 16:15 on the last session (`forward.py:72-83`).
2. **Validation:** offline validation must return `READY_FOR_FORWARD_EVALUATION` (v2.2 `:34`, `:60`). It can instead
   return `BLOCKED (pending protocol-owner review records)` (`stage_f.py:253`). INF: that could delay evaluation by
   days.
3. **Final evaluation:** the gate run, "after a successful capture and READY … validation" (v2.2 `:50`, `:61`). The
   v2.1 precedent runs it twice (`:254`).
4. **Formal result recording:** the v2.1 precedent has a status, a registry entry and a report (S10, `:255`), then an
   owner sign-off (S11, `:256`). v2.2 does not restate these steps.
   - **FACT:** the code reads status from the adoption JSONs (`forward.py:114-122`). `fwd-gate2` stays "PENDING" until
     a new committed record changes it.
   - **UNRESOLVED:** no document defines that terminal-status record.

- **JUDGMENT:** SW-A's isolation obligation should end at milestone 4 (a committed terminal status), not at capture.
  Proposal R-U6-1 ends it at capture (`:656-658`). Under a fail-closed reading it also cannot end before
  2027-01-07 16:15 ET, unless the owner records that v2.1 rows `:118-119` and C15 have lapsed. The self-audit's U6-3
  (`:121-145`) is **SUPPORTED**.

#### 3.1.5 Missing owner decisions and memos
- **OPEN-G2 (research hold):** undecided (D1/S1 `:620`). It exists as a recommendation (inventory `:158`) and as
  references to an "owner memo" (discovery `:44`, `:55`, `:174`). A filename listing and a `grep -l` of `docs/` found
  no memo file (§8).
- **Jurisdiction:** no written rule says whether V2 blind-period restrictions bind other families. DAY-16 `:11` says
  v2 governs only v2 families.
- **DAY-22 §3.2.4 / v2.1 C17:** in force (`day22/…:156-157`; v2.1 `:208`). All SW-A documents are dated 2026-11-02/03,
  inside the `fwd-gate2` sample. There is no attestation that no blind-period observation shaped them (self-audit
  U6-6, **SUPPORTED**).
- **v2.1 rows `:118-119` and C15:** no record of whether they lapsed.
- **`paper_state/` and P001 data:** no rule forbids another family from using them (v2.3 P1 `:23` separates them only
  from `fwd-gate2` evidence).
- **EDGAR access (SW-D, OD-4):** no authorization record.
- **FACT:** no date rule authorizes acquisition. v2.1 permits access only when "adopted, preflight passed, authorised"
  (`:117`, `:119`), and proposal zone H requires GV1 and U5 authorization (`:663`). The self-audit's R-U6-0 (`:185-189`)
  is **SUPPORTED**.

#### 3.1.6 Comparison
- **Proposal U6:**
  - chain: SUPPORTED;
  - option (b) as the fail-closed default: SUPPORTED;
  - R-U6-1 ending at capture: CONTRADICTED by its own purpose (§3.1.4);
  - zone X2 permitting acquisition after 2026-12-09: inconsistent with option (b) (self-audit U6-3);
  - zone H ending at `s*` ≤ 2025-12-31 while exit windows run into 2026: inconsistent (self-audit U6-4).
- **Additions to the self-audit:**
  - **U6-4 applies at every segment boundary**, not only the last one. Validation events late in 2021 read
    January 2022 prices, which belong to the historical-test segment. The gap audit's S9 default covers development
    only (`:547-548`).
  - The three gaps in §3.1.5 (paper_state, terminal record, D1/S1 boundary) are not raised by either document.

### 3.2 X3: stop and sizing

#### 3.2.1 Derivation
**FACT, definitions:**
- `r_i(k) = (C_i(k)·q_i(k) + d_i(k)) / C_i(k−1) − 1` (draft `:193`);
- `AR = r_i − r_m`, with `r_m` = SPY's total return (`:201`, `:214`);
- `σ`, `z` (`:219-221`);
- entry `E = O(s*+1)` (`:249`);
- sizing `N = floor(RiskBudget / (E_plan − S))` with `E_plan = C(s*)` (`:310-312`).

**DERIVATION.** Write `P = C_i(s*−1)`, `C = C_i(s*)`, `q = q_i(s*)`, `d = d_i(s*)`, `r_m = r_m(s*)`.
```
r_i = (C·q + d)/P − 1            ⇒  C = [P·(1 + r_i) − d] / q
define S by (S·q + d)/P − 1 = r_m ⇒  S = [P·(1 + r_m) − d] / q
C − S = P·(r_i − r_m)/q = (P/q)·AR(s*)      ⇒  S = C(s*) − (C(s*−1)/q(s*))·AR(s*)
```
- This matches proposal `:509`. The dividend `d(s*)` cancels in `C − S`.
- **Price level:** `S` is the pre-release close, moved by SPY's reaction-day total return, net of any `s*` dividend,
  in post-split share units. Equivalently, it is the `s*` close at which the stock would have matched SPY.
- **Meaning after entry:** the abnormal reaction is fully given back **if SPY stays at its `Close(s*)` level**. The
  self-audit's wording correction (`:238-241`) is **SUPPORTED**. The proposal's "pre-event share units" (`:516`) is
  wrong: `P/q` is in post-split units.

#### 3.2.2 Units, split and dividend basis, tick
- **Units:** `P/q` is USD per post-split share, and `AR` has no unit. So `S` is in USD per current share, the same unit
  as `C(s*)` and `O(e)`.
- **Split basis:** `q` = new shares per old share (`research-protocol-v2.md:127`).
- **Dividend basis:** `d` is per share held at the previous close, on a pre-split basis when a split shares the
  ex-date (`:128`). v2.0.1 C3 confirms the declared, unadjusted rate (`day17a/…:97-98`). The formula is consistent with
  both.
- **Dividends during the holding (FACT):** the draft does not adjust the stop (`:299`). The holder is credited
  `shares(k−1 close)·d(k)` (`research-protocol-v2.md:388`).
- **DERIVATION:** on an ex-date `u` the raw price drops by about `d(u)`, while the position gains that amount in cash.
  An unadjusted `S` can therefore trigger without any economic loss.
- **Consistent adjustment:** `S ← (S − d(u)) / q(u)`, subtracting `d` first because `d` is pre-split on a same-day
  split. This is an owner choice; the self-audit's X3-2 (`:257-259`) is **SUPPORTED**.
- **Tick rounding:**
  - **RECOMMENDATION:** round `S` down to $0.01, compute `N` from the rounded `S`, and round again after a split.
    LIT [UNVERIFIED]: US order prices above $1 are in whole cents.
  - Rounding down keeps `C − S > 0`.

#### 3.2.3 Sign tests
- **`AR > 0`:** `C − S = (P/q)·AR > 0`. Sizing is defined.
- **`AR ≤ 0`:** `S ≥ C`, and sizing is undefined. Such events are excluded only because the declared `z0` values are
  all positive (draft `:228`, `:430`) and `σ > 0`. The D1/S1 rule already requires a positive distance
  (`d1-s1-…:394`).
- **RECOMMENDATION:** state the guards in the frozen text:
  - `σ > 0`;
  - `C − S ≥ $0.01` after rounding;
  - the stop is defined only for `z0 > 0`.
- **Near-zero `AR`:**
  - DERIVATION: notional / capital ≈ `0.005·C / ((P/q)·AR) = 0.005·(1 + r_i)/AR`.
  - ASSUMPTION `AR = 0.5%` gives about 100% of capital. Only cash caps it (draft `:313`).
- **`S ≤ 0`:** happens only if `P·(1 + r_m) ≤ d`, which is implausible. A guard costs nothing.

#### 3.2.4 Beta exposure and market-direction bias
**ASSUMPTION model:** `r_i = α_i + β_i·r_m + ε_i`. Then `AR = α_i + (β_i − 1)·r_m + ε_i`. The draft discloses
`β = 1` (`:204`).
- **Eligibility:**
  - DERIVATION: `z ≥ z0` becomes easier for `β > 1` on up-market days and for `β < 1` on down-market days.
  - Arithmetic only: `β = 1.5`, `r_m = +2%` adds 1% to AR. With `σ = 1.5%` that is `+0.67` in `z`.
- **Size:** the stop distance is `∝ AR`, so a β-inflated AR gives a **smaller** position.
- **Drift:**
  - `D` contains `(β_i − 1)·R_m(window)`, whose mean is `(β_i − 1)·μ_m·H`.
  - ASSUMPTION `μ_m = 0.04%` per session, `β = 1.5`, `H = 20`: +0.40% per event. That is the same order as a
    plausible `δ`.
  - DERIVATION: the symbol-matched placebo subtracts the same symbol's `(β_i − 1)·μ_m·H` only if market drift in event
    windows equals market drift in placebo windows. It is a partial offset. TE1 (proposal `:252`) has no offset at all.
- **After entry:**
  - `S` is a fixed raw level. A market fall of about `AR/β` triggers it, whatever the abnormal return.
  - ASSUMPTION daily SPY σ 1% gives about 4.5% over 20 sessions, against AR of 2–6%. Market-driven stop-outs would be
    common (INF).
  - So TE1–TE3 contain a market-timing component, and `GAP_AT_ENTRY` events coincide with overnight market drops.
- **JUDGMENT:** the proposal's "no longer depends on the market's direction" (`:85`, `:519-520`) is true only for the
  mapping from a given AR to size. The self-audit's X3-5 (`:311-319`) is **SUPPORTED**.

#### 3.2.5 Missing controls (RECOMMENDATION; no price data used)
- **(a) Position-notional cap (mandatory):**
  - `N = min( floor(0.005·K/(E_plan − S)), floor(c_max·K/(E_plan·(1+s))), floor(Cash_avail/(E_plan·(1+s))) )`.
  - `c_max` is set by the owner (R3 / OPEN-R2g, D1/S1 `:428`).
  - Report how often the cap binds. TE2's `R` uses the capped planned risk `N·(E_plan − S)`.
- **(b) Entry-gap overrun:**
  - DERIVATION: risk at fill / planned risk = `(O(e) − S)/(E_plan − S) = 1 + (O(e) − C(s*)) / ((P/q)·AR)`.
  - Arithmetic only: `AR = 2%` with a +2% gap gives about 2.0, so about 1% of capital is at risk instead of 0.5%.
  - Options, frozen before data (self-audit X3-6):
    - (i) accept and report the ratio's distribution;
    - (ii) size on `C(s*)·(1+g)`, with `g` set by the owner;
    - (iii) a limit-on-open buy. This one adds gap selection.
  - A down-gap `O(e) ≤ S` is filled and exited at `O(e+1)` (proposal `:439-445`). Its loss is unbounded, so it is
    counted separately.
- **(c) Stop execution, consistent with X2:**
  - Before `Open(e)`: cancel the entry if a new Item 2.02 filing has `T_acc` in `(Close(s*), Open(e))`.
  - During `e`: no resting stop.
  - After `Close(e)`: if `L(e) ≤ S`, place a market-on-open sell for `e+1`. Otherwise, from `e+1`, a resting sell-stop
    at `S` for regular hours only. This matches the daily low, which extended-hours trades do not update (day17
    `:76-77`).
  - Cancel and replace the stop on split ex-dates, and on dividend ex-dates if (S ← S − d) is adopted.
  - Cancel the stop before the market-on-open time exit at `x`.
  - Whether the broker adjusts resting stops on ex-dates is UNVERIFIED.
- **(d) Overrun metrics (reporting, frozen):**
  - per trade: `R`, with counts of `R < −1` and `R < −2`;
  - the distribution of the risk-at-fill ratio;
  - summed planned open risk at each open;
  - weekly realized loss as a share of capital;
  - a gap-stress figure: summed notional × an owner-set hypothetical gap;
  - the label "uncapped" while R2 is open (draft `:330-331`).
- **Dividend rule of the stop:** re-rate from P2 to P1 (self-audit X3-2).

### 3.3 S7: statistical acceptance

#### 3.3.1 The draft's estimands (FACT)
- **H1:** drift is positively related to the standardized reaction (`:86-87`). Gated as the slope `β₁` in
  `D = β₀ + β₁·z + ε` over all eligible events, with `D` close-based (`:409-411`). PASS needs a one-sided 95%
  clustered CI above 0 (`:442`).
- **H2:** for `z ≥ z0`, the mean drift net of costs is positive (`:88-89`). Gated as "P2 > 0 at 5 bps and ≥ 0 at
  10 bps" on point estimates (`:442`). `n_min` is a formula for a mean (`:393-404`). `δ` enters only `n_min`
  (`:399-401`).

#### 3.3.2 The proposal's redefinitions
**Open-to-open window (S2):**
- **JUDGMENT:** sound in principle. `AR^oo` is a buy-and-hold difference over 20 sessions, not a sum of daily ARs.
  The difference is small at this horizon.
- The SIP open is the first eligible trade, not the auction print (day17 `:69`). That adds noise at both ends.

**DERIVATION: `R^oo` dividend accounting is wrong for multi-event windows.**
- The proposal sets `D_i(a,b) = Σ_{u∈(a,b]} d(u)·Π_{v∈(u,b]} q(v)` (`:134`), "as in protocol v2 §3.4". The protocol
  TR formula is the same (`research-protocol-v2.md:135`; JSON `:707`).
- For one share bought at `O(a)`, protocol §11.2 credits `shares(u−1 close)·d(u) = d(u)·Π_{v∈(a,u)} q(v)` at each
  ex-date `u` (`:388`; v2.0.1 C3 `:97-98`).
- The correct carry is therefore `D*(a,b) = Σ_u d(u)·Π_{v∈(a,u)} q(v)`, which uses the splits **before** `u`, not
  after it. The two forms agree only when no split falls in `(a,b]` other than on `u` itself.
- **Example (ASSUMPTION):** a dividend of 0.2% of price followed by a 4-for-1 split inside the window. The
  proposal's form credits 0.8%, so `R^oo` is overstated by 0.6 percentage points. If the split comes first, the
  dividend is understated.
- **INF:** in the TR index the issue can bind only across missing bars, because `p` is the previous bar. DAY-22
  reports 0 missing bars in Stage H (`day22/…:35`), so it is latent there.
- **RECOMMENDATION:**
  - define `R^oo` by explicit share-count accounting (protocol §11.2);
  - ask the protocol owner to check §3.4's carry factor;
  - add a unit test with a dividend followed by a split, and a split followed by a dividend.

**Symbol-matched placebo (S4), JUDGMENT:**
1. **Benefit:** it removes symbol-level average abnormal returns, the main survivorship channel.
2. **Time mismatch:**
   - `P_i` spans the whole segment, while `E+` events cluster in time.
   - A symbol's unusually strong years are not removed.
   - Symbol × year matching (proposal `:238`) is closer but has thin cells. Owner choice.
3. **Asymmetric filters:**
   - `E+` excludes "any other Item 2.02 filing … `T_acc` in (Close(s*), Open(x))" (`:216`).
   - `P_i` excludes only Item 2.02 **events** (`s*'`) (`:219`).
   - The text says the filter "applies … alike" (`:230-231`). The formulas do not.
4. **Conditioning on future filings:**
   - The collision exclusion uses information from after entry.
   - If unscheduled filings (for example pre-announcements) correlate with later drift, `Δ₂` is biased, in an
     unknown direction.
   - **RECOMMENDATION:** an intention-to-treat primary, with all `E+` events over the full window. Keep the exclusion
     as a sensitivity run.
5. **Pre-announcement windows:**
   - Placebo windows may end just before an announcement.
   - LIT [UNVERIFIED]: a pre-announcement premium (discovery SW-B, `:150-154`) would raise `μ_P`, which is
     conservative.
   - It also means the null is joint: "no event effect **and** no difference between post-season and other windows".
6. **Segment ends:** placebo windows near the end of a segment cross the boundary (§3.1.6).

#### 3.3.3 `δ`, the intervals, `n_min`, and P(PASS)
**DERIVATION (normal approximation).** Let `SE = σ_D·√(DEFF/n)`.
- The H2 part of the ladder passes when all of these hold:
  - `Δ̂₂ > 0` (step 3);
  - `Δ̂₂(10 bps) ≥ 0` (step 5). This is implied when `δ ≳ 0.10%`, by proposal `:338-340`;
  - `Δ̂₂ − 1.645·SE > 0` (step 6);
  - `Δ̂₂ ≥ δ` (step 6b).
```
P(PASS_H2 | Δ₂) = 1 − Φ( (max(δ, 1.645·SE) − Δ₂) / SE )
```
- **At `Δ₂ = δ`:**
  - P = 0.5 whenever `δ ≥ 1.645·SE`, and below 0.5 otherwise.
  - At `n = n_min,2` (`:311`), `SE = δ/2.487`, so **P = 0.5**.
- **At `Δ₂ = 0` and `n = n_min,2`:** `1 − Φ(2.487) ≈ 0.0064`. The rule is very strict at the null and weak at `δ`.
- **H1 part:** at `n_min,1` it has power 0.8 at `δ_β` for `LB(β₁) > 0`.
- **Per segment:**
  - P(PASS) ≤ min(0.5, 0.8) = 0.5;
  - about 0.4 if the two parts were independent (ASSUMPTION).
- **Over the sequence** (`:386-393`; validation and historical test must both PASS on separate samples):
  - ≤ 0.25 at `δ` (about 0.16 under independence);
  - with the forward gate, ≤ 0.125.
- **Conclusion:** step 2's "underpowered" label refers to 80% power for a condition that does not decide PASS. The
  self-audit's S7-6 (`:458-478`) is **SUPPORTED** but stops at one segment.
- **Fix:** declare a design alternative `Δ_A > δ` and state power at `Δ_A` for the whole rule. When the `LB`
  condition binds, `n = DEFF·(2.487·σ_D/Δ_A)²`. This is valid while `Δ_A ≥ 1.512·δ`, so that `1.645·SE ≥ δ`.
  - ASSUMPTION `σ_D = 6%`, `δ = 0.5%`, `Δ_A = 1.5%`: `n ≈ 99·DEFF`.
  - Check: `SE ≈ 0.60%`, `1.645·SE ≈ 0.99% ≥ δ`, and P(PASS | `Δ_A`) = Φ(0.842) = 0.80.
- **`δ_β = δ/z0` (`:312-313`):**
  - The wording "the slope at which the drift predicted at the threshold `z0` equals `δ`" is exact only if `β₀ = 0`.
  - The formula is defensible as "the slope at which the predicted drift **difference** between `z = 0` and
    `z = z0` equals `δ`".
  - Constant costs and the baseline do not affect a slope.
  - So the self-audit's S7-5(iii) ("ignores the intercept") is **PARTIALLY SUPPORTED**: fix the wording; the formula
    can stand.
- **Arithmetic re-checked:**
  - proposal table `:321-325` (e.g. `(2.487·6/1)² ≈ 222.7`);
  - gap audit MDE table `:474-478`;
  - X3 notional examples `:518-519`, `:527`.

  All correct as arithmetic.

#### 3.3.4 Feasibility of the forward confirmation (DERIVATION, ASSUMPTION inputs)
- **Event rate:** the draft caps events at about 100 per year (`:402`). ASSUMPTION: 10–40% have `z ≥ z0`, giving
  10–40 forward `E+` events per year. There is no data on this share.
- **Years to reach `n_min`, with `DEFF = 1`:**
  - `n = 99` (`σ_D` 6%, `Δ_A` 1.5%): 2.5–10 years;
  - `n = 223` (`σ_D` 6%, `δ = Δ_A = 1%`): 5.6–22 years.

  `DEFF > 1` lengthens both.
- The historical validation segment alone (≤ 200 events, 20–80 `E+` under the same assumption) is likely
  INCONCLUSIVE. That agrees with proposal `:327-331`.
- **JUDGMENT:** the owner should decide, before data, whether a confirmation that is probably years away is
  acceptable. Neither the proposal nor the self-audit quantifies this.

#### 3.3.5 Block bootstrap (circular, `L = 2(H+1)`)
- **Dependence channels:**
  - overlapping windows, where entries are within `H` sessions of each other;
  - residual common factors within earnings seasons. The `β = 1` residual and sector clusters both contribute; the
    gap audit lists 7 semiconductor names (`:802-804`);
  - the regressor `z` reaching back 61 sessions (self-audit `:367-371`);
  - volatility clustering.
- **Split share:**
  - DERIVATION: assume pair distances are uniform on 1..H and block starts are random. Then a pair at distance `h` is
    split with probability `h/L`, and the mean is `(H+1)/(2L) = 21/84 = 0.25` at `L = 42`.
  - The self-audit's arithmetic is **SUPPORTED**.
  - Same-session pairs are never split, and same-week clustering lowers the share.
- **Few blocks:**
  - about 504/42 ≈ 12 blocks in a 2-year segment;
  - about 1,000/42 ≈ 24 in 2022–2025.
  - LIT [UNVERIFIED]: percentile intervals from that few units tend to undercover.
  - The effective number of independent units is closer to the number of earnings seasons: about 8 in two years
    (gap audit `:445`).
- **Wrap-around:** the circular scheme joins the segment's end to its start. This is an artificial adjacency (minor).
- **Algorithm text:** "assigned to the block that contains its entry session" (`:290`) is workable under random
  starts if read as "each drawn block contributes the events whose entry session it contains". The ambiguity is
  real but not a contradiction. The self-audit's S7-2 "UNSUPPORTED" is overstated: **PARTIALLY SUPPORTED**.

#### 3.3.6 What a PASS shows, and what it does not
- **It shows**, if every assumption holds, that in that historical segment and on these 25 hindsight-selected names:
  - events with `z ≥ z0` had a mean net, SPY-relative, stop-free open-to-open 20-session return above the same
    symbols' non-event mean, at nominal one-sided 95%;
  - that return's point estimate was at least `δ`;
  - the slope of drift on `z` was positive at nominal 95%;
  - the momentum-relabel condition did not fire;
  - the mean simulated TE1 was positive.
- **It does not show:**
  - that `Δ₂ ≥ δ` with confidence;
  - portfolio profitability (TE3 is not gated);
  - persistence (decay is the stated prior, draft `:108-109`);
  - freedom from survivorship bias;
  - β-neutrality;
  - attribution to earnings information rather than sector news (draft `:82`);
  - realistic fills (open is not the auction; intraday stop fills are optimistic);
  - nominal coverage with few blocks;
  - control of project-level multiplicity (S8);
  - any Sharia status;
  - forward validity.
- **The momentum-relabel rule is narrower than the falsification statement:**
  - The rule (proposal `:348-351`) fires only if `β₂`'s interval excludes 0.
  - If collinearity makes the controlled slope insignificant while `β₂` is also insignificant, PASS can proceed.
  - The discovery report's falsification 2 says "disappears after controlling" (`:350-351`).
  - **RECOMMENDATION:** require `LB(β₁ᴹ) > 0` for PASS, or have the owner adopt the narrower rule knowingly.

#### 3.3.7 A defensible design (RECOMMENDATION; with limitations)
1. **Segments:**
   - development 2016-04 → 2019-12: pipeline checks, `σ_D`, `DEFF`, descriptive only;
   - **one** confirmatory historical segment 2020-01 → 2025-12. This pools validation and the test, gap audit S6
     option (b), and is an owner choice;
   - then the forward test.
   - Every segment drops events and placebo windows that extend past its end, and counts them.
2. **Estimands:**
   - `Δ₂` as intention-to-treat on corrected `R^oo` (primary);
   - the H1 slope on the sample the owner picks under S3, all events or `z > 0`;
   - momentum-controlled slope required.
3. **Inference (one method, frozen):**
   - Cluster by earnings season. Define seasons from the event table before any price is read.
   - Use a small-cluster correction and `t` with `G − 1` degrees of freedom, or a wild cluster bootstrap
     (LIT [UNVERIFIED]).
   - That gives `G ≈ 24` for 2020–2025.
   - Report the block bootstrap at `L ∈ {42, 63}` and a calendar-time Newey–West mean as diagnostics only.
4. **Acceptance:** PASS iff all of these hold:
   - `LB(Δ₂) > 0`;
   - `Δ̂₂ ≥ δ_min`;
   - `Δ̂₂(10 bps) ≥ 0`;
   - `LB(β₁) > 0`;
   - `LB(β₁ᴹ) > 0`;
   - mean TE1 > 0.
5. **Power, stated for the whole rule at `Δ_A`:**
   - P(PASS) is tabulated at `Δ ∈ {0, δ_min, Δ_A}` in the frozen text.
   - The power check uses event counts and a pre-outcome dispersion proxy, for example `√H × rms(σ_i(e))` from the
     pre-event windows, which already exist for `z`. Combine it with the development `DEFF`. This is JUDGMENT: post-
     event volatility may be higher, so the proxy is optimistic.
6. **Limitations, disclosed:**
   - hindsight universe;
   - `β = 1`;
   - few clusters;
   - a period the authors know;
   - low `n`;
   - a forward confirmation that is likely years away.

---

## 4. Classification of reviewed claims

| # | Claim (source) | Verdict | Basis |
|---|---|---|---|
| 1 | Amendment chain and adoption status (proposal `:54-58`, `:636-645`; self-audit U6-1) | SUPPORTED | §3.1.1 |
| 2 | "Three statements … disagree" on forward rules (gap audit `:104-111`, `:749-758`) | CONTRADICTED | resolved by v2.1 C13/C16 and v2.2 |
| 3 | Fail-closed default "after V2-MOM 252 sessions" (gap audit `:767-768`) | CONTRADICTED | superseded by v2.1 E1 (`:288`) |
| 4 | 2027-01-07 rows and C15 not revoked by v2.2 (self-audit U6-2) | SUPPORTED | §3.1.2 |
| 5 | `FORWARD_WINDOW` usage "not checked" / "unknown" (proposal `:691`; self-audit `:527-529`) | resolved: inert within the three files read | `forward.py:59-69`, `:221-233` |
| 6 | R-U6-1 ends at capture (proposal `:656-658`) | CONTRADICTED (by its own purpose) | §3.1.4 |
| 7 | Inconsistent end conditions (self-audit U6-3) | SUPPORTED | proposal `:112-113`, `:651`, `:656`, `:665` |
| 8 | Historical boundary inconsistency (self-audit U6-4) | SUPPORTED; applies at every boundary | §3.1.6 |
| 9 | Missing R-U6-0 (self-audit U6-5) | SUPPORTED | §3.1.5 |
| 10 | C17 not addressed (self-audit U6-6) | SUPPORTED | DAY-22 `:156-157`; v2.1 `:208` |
| 11 | "v2 rules bind SW-A" (implicit in all three documents) | PARTIALLY SUPPORTED | DAY-16 `:11`; binding only through shared data |
| 12 | Stop formula (proposal `:509`; self-audit X3-1) | SUPPORTED | §3.2.1 |
| 13 | "pre-event share units" (proposal `:516`) | CONTRADICTED | `P/q` is in post-split units |
| 14 | Size "no longer depends on the market's direction" (proposal `:85`, `:519-520`) | PARTIALLY SUPPORTED | §3.2.4 |
| 15 | Notional cap "remains useful" (optional) (proposal `:527-528`) | PARTIALLY SUPPORTED | must be mandatory (§3.2.5) |
| 16 | Self-audit X3-2 to X3-7 | SUPPORTED | §3.2 |
| 17 | Gap audit X3 example "`E ≤ S` likely" (`:598`) | PARTIALLY SUPPORTED | `C(s*) < S`, so sizing refuses with certainty (D1/S1 `:394`) |
| 18 | `E ≤ S` skip is non-executable for a market-on-open order (proposal `:439-445`) | SUPPORTED | the condition depends on the fill itself; conditional order types UNVERIFIED |
| 19 | X1 defect (gap audit `:567-575`) | SUPPORTED | §2 X1 |
| 20 | Draft: D12 "does not apply" (`:455`) | CONTRADICTED | `:282`; AAOIFI `:42` |
| 21 | Option (c) removes same-session round trips (proposal `:474-475`) | PARTIALLY SUPPORTED | except a pre-open collision on `e` (§2 X1) |
| 22 | H1 window misaligned (gap audit S2) | SUPPORTED | §2 S2 |
| 23 | `R^oo` dividend term "as in protocol v2 §3.4" (proposal `:134`) | CONTRADICTED (by §11.2 accounting) | §3.3.2 |
| 24 | Symbol-matched placebo as survivorship control (proposal `:204-246`) | PARTIALLY SUPPORTED | §3.3.2 |
| 25 | Collision filter "applies … alike" (proposal `:230-231`) | CONTRADICTED | `:216` vs `:219` |
| 26 | Power check certifies adequate power (proposal `:311`, `:362`, `:371-376`) | CONTRADICTED | §3.3.3 |
| 27 | Self-audit S7-6 (≈50% at `δ`) | SUPPORTED, incomplete | compounding over segments |
| 28 | Self-audit S7-1 (≈25% of dependent pairs split) | SUPPORTED (under its assumption) | §3.3.5 |
| 29 | Self-audit S7-2 "UNSUPPORTED (ambiguous)" | PARTIALLY SUPPORTED | ambiguous, not contradictory |
| 30 | Self-audit S7-5(iii) "ignores the intercept" | PARTIALLY SUPPORTED | wording fix; formula defensible |
| 31 | Self-audit S7-3, S7-4, S7-7 | SUPPORTED | §3.3 |
| 32 | Proposal power tables and arithmetic (`:321-325`, `:518-519`, `:527`) | SUPPORTED (arithmetic) | §3.3.3 |
| 33 | CSV counts in draft §0.2 (`:36-42`) | SUPPORTED | CSV lines 2–27 |
| 34 | Draft U1 "PEP shows acceptance and release can be on different dates" (`:61`) | PARTIALLY SUPPORTED | CSV line 23 |
| 35 | "A PIT data method … already exists" (discovery `:33-34`) | PARTIALLY SUPPORTED | §2 T1 |
| 36 | V4 consistency rule (proposal `:564`) | PARTIALLY SUPPORTED | §2 T1 |
| 37 | 2026 calendar coverage lies inside the SW-A excluded period (proposal `:577-579`) | SUPPORTED | draft `:373`; CSV dates |
| 38 | Preflight checks protocol identity and v2.0.4 (proposal `:711-712`) | SUPPORTED | `stage_f.py:324-327` |
| 39 | Amending v2 "could interfere" with the gate (proposal `:712-713`) | PARTIALLY SUPPORTED | edits yes; a new file not checked in the code read |
| 40 | Inherit §3.9 overlap control (proposal `:728`) | CONTRADICTED (by draft `:375`) | §2 GV3 |
| 41 | `stage_f.py:322-323` refuses capture with untracked files (proposal `:816-819`) | SUPPORTED | also refuses modified tracked files |
| 42 | Self-audit described as "INDEPENDENT AUDIT" (`:3`) | CONTRADICTED | same author (`:13-16`) |
| 43 | "Its expected cost is small" for option (b) (proposal `:114`, `:681-683`) | UNVERIFIABLE | depends on unknown December events; INF only |
| 44 | `protocol_identity()` checks only the DAY-16 and v2.0.1–v2.0.3 files | UNVERIFIABLE | `stage_r.py` not read |
| 45 | P001 stores raw bars under `paper_state/` (v2.5 `:103-104`) | UNVERIFIABLE | restricted path; citing document only |

---

## 5. Recommended corrections

- **C1 (U6):** end R-U6-1 when `fwd-gate2` has a committed terminal status (§3.1.4). Under option (b), state that
  nothing dated ≥ 2026-10-08 is acquired, computed or inspected before 2027-01-07 16:15 ET. Use those three verbs
  throughout. Delete the zone X2 acquisition permission.
- **C2 (U6):** add R-U6-0 (self-audit `:185-189`).
- **C3 (U6):** one project-level forward-data rule for all non-V2 families, so that D1/S1 `:87-89` and SW-A agree.
- **C4 (U6):** forbid any SW-A use of `paper_state/` or V2-MOM-P001 data, at any date. SW-A forward data comes only
  from its own single acquisition (R-U6-4).
- **C5 (U6, S9):** at every segment end, drop the events and placebo windows whose exit or window extends past that
  end, and count them. This covers development, validation, the historical test, and the end of 2025.
- **C6 (S2, S4):** define `R^oo` by protocol §11.2 share accounting. Add tests for a dividend then a split, and a
  split then a dividend. Ask the protocol owner to check the §3.4 carry factor.
- **C7 (S4):**
  - make the event and placebo filters symmetric;
  - make intention-to-treat `Δ₂` primary, with collision exclusion as a sensitivity run;
  - recompute `w_i` in each bootstrap replicate;
  - state that the null is joint.
- **C8 (S5):** one executable inference algorithm, or the season-cluster design of §3.3.7. State the number of draws,
  the wrap rule, the seed and the RNG.
- **C9 (S6, S7):**
  - declare `δ_min` and `Δ_A`;
  - state power for the whole PASS rule at `Δ_A`;
  - tabulate P(PASS) at 0, `δ_min` and `Δ_A`;
  - state P(PASS over the whole sequence);
  - quantify forward feasibility (§3.3.4);
  - fix the `δ_β` wording.
- **C10 (momentum):** require `LB(β₁ᴹ) > 0`, or adopt the narrower rule explicitly.
- **C11 (X1, X2):** cancel the entry on a filing in `(Close(s*), Open(e))`. Add the live order sequence (§3.2.5 (c)).
- **C12 (X3):**
  - guards `σ > 0` and `C − S ≥ $0.01`;
  - tick rounding down;
  - a dividend rule for `S`, re-rated from P2 to P1;
  - a mandatory notional cap;
  - a risk-at-fill rule;
  - the overrun metrics;
  - the β and market-direction diagnostics, with β-adjusted AR as a sensitivity run at minimum.
- **C13 (T1, T2):** session class from `T_pub = min(T_rel, T_acc)`, with a class-disagreement flag. State what a
  tier-C disagreement does.
- **C14 (GV3):**
  - cite DAY-16 `:11` and §14 as the main rationale;
  - restrict §3.9 overlap control to SW-A's own snapshots;
  - do not inherit the §3.4 carry formula unchecked;
  - confirm that v2.4 reuse reads no Stage R data.
- **C15 (labels):** rename the self-audit's status "SELF-REVIEW". Correct the proposal's "pre-event share units".
  Correct the draft's §8 D12 sentence and its stale OPS-1 text (gap audit GV5).

---

## 6. Decisions only the owner can make

| ID | Decision |
|---|---|
| O1 | GV2: approve SW-A at all, and at which scope (design only / full) |
| O2 | OPEN-G2: whether a research hold exists, its scope (design, acquisition, runs) and its lift condition, as a committed record |
| O3 | Whether V2 blind-period rules bind non-V2 families, and the single forward boundary for them (C3) |
| O4 | Whether v2.1 §6 rows `:118-119` and C15 lapsed with `fwd-gate`; until recorded, treat them as binding |
| O5 | What record ends `fwd-gate2`'s PENDING status, and who commits it |
| O6 | C17 attestation for the SW-A design documents, or defer the SW-A freeze until after the `fwd-gate2` record |
| O7 | S2: H1 on the traded window (proposal) or close-based |
| O8 | S3: H1 sample (all events or `z > 0`) |
| O9 | S4: placebo matching (symbol, symbol × year); intention-to-treat or collision-excluded primary |
| O10 | S5: inference method (season clusters, block length, few-cluster correction) |
| O11 | S6: segment structure (separate validation and test, or pooled 2020–2025) |
| O12 | `δ_min`, `Δ_A`, and the acceptance semantics (`LB > 0 and point ≥ δ`, or `LB > δ`) |
| O13 | Momentum-relabel rule (`LB(β₁ᴹ) > 0` required or not) |
| O14 | Forward length (U6-L), and acceptance of a forward confirmation that may take years |
| O15 | X2: option (c) or (d); adviser question on D12 for sales at `O(e+1)` |
| O16 | X3: dividend treatment of `S`; notional cap value `c_max`; risk-at-fill rule; gap-stress `g` |
| O17 | β = 1 baseline or estimated-β baseline |
| O18 | T1/T2: `Δ_max`; the `T_pub` rule; tier set; evidence storage and licensing |
| O19 | U5: whether fresh data may cover Stage R/H dates; snapshot location |
| O20 | SW-D: EDGAR access, terms, contact identity; fresh price snapshot authorization |
| O21 | OPS-1: commit or remove each untracked file before 2026-12-09 16:15 ET (this file included) |
| O22 | Adviser items: D10, D12, D15, D2 multi-day exits, SH6 (paper and live only) |

---

## 7. Design-freeze blockers

The SW-A protocol cannot be frozen until each of these has a committed resolution.

- **B0 (operational, not a design item):** untracked files at the `fwd-gate2` capture. At least the three SW-A
  documents shown untracked at the start and this review. The capture refuses them (`stage_f.py:322-323`).
- **B1:** O1 (GV2) and O2 (OPEN-G2 record and scope).
- **B2:** O3–O6 (forward boundary, v2.1 lapse, terminal record, C17), with C1–C5.
- **B3:** GV3 protocol home, with the inheritance list corrected (C14).
- **B4:** S2/S4 estimands with corrected `R^oo` (C6) and placebo rules (C7).
- **B5:** S5, one executable inference method (C8).
- **B6:** S6/S7 acceptance, with power aligned to the PASS rule, the segment structure and a forward-feasibility
  statement (C9, O11–O14).
- **B7:** momentum-relabel rule (C10).
- **B8:** X1/X2 text with the pre-open collision rule and the live order sequence (C11, O15).
- **B9:** X3 guards, rounding, dividend rule, mandatory cap, risk-at-fill rule, metrics (C12, O16, O17).
- **B10:** T1/T2 definitions, including `T_pub` and tier-C handling (C13, O18).
- **B11:** every P1 item in the gap audit's §10 table (`:960-989`) that the proposal leaves open, for example C1–C7,
  S1, S3, S8, S10, X4–X7, X9, R3, R5, U1–U3, GV4, SH2-L.

No blocker is resolved by this review.

---

## 8. Reviewer limitations and inaccessible sources

- **Not read (restricted):**
  - `data/` (including `oos_cache`, `cache`);
  - `paper_state/`;
  - `artifacts/day26c/`;
  - `screening_evidence/`;
  - all `stage_r` / `stage_h` / `stage_f_` paths;
  - `fwd-gate2` outputs;
  - run-result folders (`artifacts/*/v2/`, `artifacts/day21`, `artifacts/day25b/run`).

  Claims citing them are marked UNVERIFIED (for example v2.5 `:103-104`).
- **Not read (outside the permitted list):**
  - `acquisition/v2/stage_r.py` (`protocol_identity()`);
  - `backtest/v2/run.py`, `data.py`, `paper/`, tests;
  - `docs/shariah/AAOIFI_DATA_PROVIDER_ASSESSMENT.md`;
  - `artifacts/day19/day19-research-report.md`, `artifacts/day18j/day18j-report.md`.

  So whether `FORWARD_WINDOW` is used elsewhere, and exactly what `protocol_identity()` checks, are UNVERIFIED.
- **Partly read:**
  - v2.0.1–v2.0.4, DAY-18I, DAY-18L, DAY-19, DAY-23, DAY-24, DAY-26A: headers and searched lines only;
  - the DAY-16 JSON and the adoption JSONs: searched lines and short ranges;
  - D1/S1 (mostly Uzbek): §0.5, §3, §4 and searched lines.
- **Owner-memo search:** a `grep -l` over `docs/` for "OPEN-G2", "research hold" and "owner memo" scanned every file
  there. It displayed only the names of matching files, and no content. Matches were limited to the D1/S1 design, the
  discovery report and the three SW-A documents plus the draft. A memo outside `docs/`, or outside the repository,
  cannot be excluded.
- **Method limits:**
  - power figures use normal approximations and ASSUMPTION inputs;
  - the 25% split share assumes uniform pair distances;
  - the `R^oo` finding is algebra on the stated formulas and was not tested on data.
- **Independence:** this reviewer did not write any of the reviewed documents. It runs on the same model family as
  their author, so shared blind spots remain possible. A human review of §3.3.2 (`R^oo`) and §3.3.3 (P(PASS)) is
  worth having.

---

## 9. Files read

Content read (full unless noted):
1. `docs/sw-a-research-design-2026-11-02.md`
2. `docs/sw-a-decision-gap-audit-2026-11-03.md`
3. `docs/sw-a-p0-resolution-proposal-2026-11-03.md`
4. `docs/sw-a-p0-consistency-audit-2026-11-03.md`
5. `docs/strategy-discovery-report-2026-11-02.md`
6. `docs/d1-s1-research-design-2026-11-02.md` (lines 77–94 and 385–462, plus searched lines)
7. `docs/strategy-evidence-inventory-2026-10-17.md`
8. `docs/shariah/AAOIFI_MVP_DECISIONS.md`
9. `docs/shariah/AKINDA_PROVIDER_DECISION.md`
10. `artifacts/day16/research-protocol-v2.md`
11. `artifacts/day16/research-protocol-v2.json` (searched lines only)
12. `artifacts/day17/day17-data-blockers.md`
13. `artifacts/day17a/protocol-v2.0.1-amendment.md` (header and searched lines)
14. `artifacts/day18a/protocol-v2.0.2-amendment.md` (header and searched lines)
15. `artifacts/day18c/protocol-v2.0.3-amendment.md` (header and searched lines)
16. `artifacts/day18j/protocol-v2.0.4-amendment.md` (header and searched lines)
17. `artifacts/day18j/oq10-raw-close-resolution.md` (header)
18. `artifacts/day18i/day18i-protocol-owner-decision.md` (header)
19. `artifacts/day18l/day18l-protocol-owner-signoff.md` (header)
20. `artifacts/day19/day19-protocol-owner-signoff.md` (header)
21. `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md`
22. `artifacts/day23/day23-forward-oos-252-session-audit.md` (header)
23. `artifacts/day24/day24-forward-oos-duration-amendment-design.md` (header)
24. `artifacts/day26a/day26a-forward-21-session-observation-amendment-draft.md` (header)
25. `artifacts/day26b/protocol-v2.1-amendment.md`
26. `artifacts/day26b/protocol-v2.1-adoption.md`
27. `artifacts/day26b/protocol-v2.1-adoption.json` (status lines; lines 28–40, 130–140)
28. `artifacts/day26d/protocol-v2.2-amendment.md`
29. `artifacts/day26d/protocol-v2.2-amendment.json`
30. `artifacts/day26d/protocol-v2.2-adoption.md`
31. `artifacts/day26d/protocol-v2.2-adoption.json` (status lines; lines 25–47)
32. `artifacts/day27/protocol-v2.3-amendment.md`
33. `artifacts/day27/protocol-v2.3-adoption.json` (status lines; lines 18–30)
34. `artifacts/day27a/protocol-v2.4-amendment.md`
35. `artifacts/day27a/protocol-v2.4-adoption.json` (status lines)
36. `artifacts/day27b/protocol-v2.5-amendment.md`
37. `artifacts/day27b/protocol-v2.5-adoption.json` (status lines)
38. `config/earnings_calendar_sources.csv`
39. `config/day_universe.py`
40. `acquisition/v2/contract.py`
41. `acquisition/v2/stage_f.py`
42. `backtest/v2/forward.py`

Metadata only (no content displayed):
- line counts (`wc -l`) of the files above and of the other permitted protocol files in `day17a`–`day27b`;
- a top-level, non-recursive listing of file names in `artifacts/day16, day17, day17a, day18a, day18c, day18i,
  day18j, day18l, day19, day22, day23, day24, day26a, day26b, day26d, day27, day27a, day27b`. The `day19/v2/`
  subdirectory name appeared and was not opened;
- the file names in `docs/` and `docs/shariah/`;
- `grep -l` over `docs/` (matching file names only; see §8).

Nothing restricted was opened. Nothing was run, staged, committed or pushed. No existing file was changed. The only
file created is this review.
