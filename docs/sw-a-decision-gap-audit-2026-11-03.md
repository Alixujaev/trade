# SW-A: Decision-gap audit of the research specification (2026-11-03)

> **Status: AUDIT — NOT APPROVED FOR EXECUTION.**
> This audit lists decisions. It makes none of them.
> - No code was changed and no existing document was edited.
> - No API call, network access, data acquisition, backtest or optimization was run.
> - Stage R and Stage H data, `paper_state/`, sealed P001 and `fwd-gate2` results were not opened.
> - `fwd-gate2` and its preflight were not run.
>
> **No claim is made that SW-A is profitable.** Every "recommended default" below is a proposal for the owner
> to accept or reject. None of them is adopted.

**Audited document:** `docs/sw-a-research-design-2026-11-02.md` (status DRAFT — NOT APPROVED FOR EXECUTION).
It was committed in `80e94ad`. The repository HEAD at the time of this audit is
`80e94ada6f8c576fc4d7bceb71664234eb98dcdd`, on branch `feature/day-trading-research`.

**Labels** (the same vocabulary as the SW-A draft):
- **FACT**: read directly from a cited repository file.
- **INF**: an inference.
- **ASSUMPTION**: assumed, not verified.
- **LIT [UNVERIFIED]**: literature or regulatory knowledge from memory. It is not repository evidence and was not
  checked here.
- **DEFECT**: an internal inconsistency or error in the draft text, as opposed to a decision that is merely open.

**Tracks.** Each gap is assigned to one track, so that research-design work is kept apart from execution and
Sharia approval:
- **RD**: research design (what is measured and how it is judged);
- **EX**: simulation and execution mechanics;
- **RK**: risk limits;
- **SH**: Sharia and adviser items;
- **GV**: governance and protocol process.

**"Blocks" uses the earliest gate a gap blocks.** Blocking an earlier gate implies blocking every later one.

| Code | Gate |
|---|---|
| **DC** | design completion: the protocol cannot be frozen |
| **DA** | data acquisition: EDGAR evidence, or price and corporate-action snapshots |
| **BT** | backtest: event study or trading simulation |
| **PL** | paper or live trading |

**"Owner approval"** is one of three values:
- **Yes (choice)**: a genuine owner choice between options.
- **Yes (freeze)**: there is no real choice, but the text must be approved as part of the protocol freeze.
- **Adviser**: needs a qualified Shari'ah adviser, not only the owner.

---

## 0. Evidence read for this audit

| File | Used for |
|---|---|
| `docs/sw-a-research-design-2026-11-02.md` | the audited specification, read in full |
| `docs/strategy-discovery-report-2026-11-02.md` §1, §5 (SW-A), §8, §10, §12, §13 | SW-A rationale, falsification statements, owner decisions OD-1 to OD-8 |
| `docs/d1-s1-research-design-2026-11-02.md` §0.5, §3, §4, §7 | protected periods, the 0.5% risk rule, OPEN-R1/R2a–g/R3, Sharia table, OPEN-G2 |
| `artifacts/day16/research-protocol-v2.md` §0, §2, §3, §7–§15, §20 | price basis, execution, costs, gate, multiple testing, segment dates |
| `artifacts/day17/day17-data-blockers.md` §3–§5, §8 | 1Day bar semantics, coverage, corporate-action blockers C1–C6 |
| `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md` §3.1–§3.2 | forward blind-period rules |
| `docs/strategy-evidence-inventory-2026-10-17.md` §6, §10 | `fwd-gate2` schedule, research-hold recommendation |
| `docs/shariah/AAOIFI_MVP_DECISIONS.md` (rows D2, D10, D12, D13, D15) | Sharia decision status |
| `docs/shariah/AKINDA_PROVIDER_DECISION.md` (quota, `valid_days`, licence lines) | screening constraints |
| `config/earnings_calendar_sources.csv` (header and edge-case rows) | the 2026 verification precedent |
| `config/sharia_eligibility.csv` (header only) | registry state: header only, no rows |

Stage R and Stage H snapshots, run outputs, `paper_state/`, P001 and every `fwd-gate2` artifact were **not**
opened. The V2-MOM holdout concentration document was also not opened. It is referred to only by its file name.

---

## 1. Executive summary

1. **The draft is not ready to freeze.** The §10 table has 57 decision rows. Eleven are rated **P0**: they change
   what is being tested, or they are defects in the draft text.
2. **Four DEFECTS need correcting before any freeze:**
   - **S2:** the H1 drift window `D(e)` (close-to-close, starting at `Close(s*)`) is not the traded window (open
     `s*+1` to open `s*+1+H`). A PASS on P1 therefore does not show that the drift is tradable.
   - **X1:** the exit algorithm (§4.5) checks the intraday low **before** the time exit. On the exit session this
     can record a stop fill at `S` that happens after the position is already closed at the open.
   - **X2:** the entry-session stop (§4.5) creates **same-session round trips**. This contradicts the draft's
     §8 statement that D12 (day trading) "does not apply".
   - **X3:** the signal is market-adjusted (`AR`), but the stop and the sizing use **raw** prices
     (`S = C(s*−1)`). When the market falls on the reaction day, a qualifying event can have a near-zero raw stop
     distance (very large notional) or a negative one (skipped). Which events are traded then depends on the
     market's direction.
3. **The H2 estimand is undefined.** "Mean net drift" could mean any of the following:
   - market-adjusted `AR` minus costs, which a long-only trader cannot earn;
   - the per-trade raw return with stops;
   - the portfolio return compared with a benchmark.

   On a hindsight-selected universe of survivors, a long-only mean is expected to be positive even with **no**
   event effect (protocol v2 §13.B rationale). H2 needs a non-event baseline (S4).
4. **The meaning of `VERIFIED` is still undocumented (T1).** The 2026 file uses the word without a definition.
   The draft proposes applying a new definition "retroactively", which would change the meaning of a config file
   that ORB consumes (GV4). A separate SW-A status vocabulary avoids that.
5. **The inference method does not fit the overlap structure (S5).** Weekly clustering does not cover
   20-session drift windows that overlap across weeks. The draft also leaves the choice open ("clustered by week
   **or** block bootstrap"). One primary method must be fixed before any data is seen.
6. **The acceptance logic is incomplete (S7):**
   - P2 passes on a point estimate alone, with no interval requirement.
   - `δ` enters only the power calculation, not the acceptance rule.
   - The "momentum relabel" rejection has no operational definition.
   - The precedence of REJECT over INCONCLUSIVE is not stated.
   - It is not stated whether a validation failure stops the historical test.
7. **The governance boundary is unresolved (U6, GV1).** Sources in the repository do not agree on when new
   forward-dated data may be acquired:
   - DAY-22 §3.2: no forward market data in the research cache until the 252-session V2-MOM period ends
     (2027-10-08);
   - `acquisition/v2/contract.py`, as cited in D1/S1 §0.5: forward window 2026-10-08 → 2027-01-07;
   - the SW-A draft: forward confirmation "not earlier than after the `fwd-gate2` evaluation".

   This blocks the SW-A forward confirmation and any acquisition of data dated 2026-10-08 or later.
8. **Power is likely low.** This is INF from counts, not data: at most about 200 events in the 2-year validation
   segment before exclusions, and fewer in the `z ≥ 2` subset. An illustrative minimum detectable effect (§4, S6)
   is of the order of 1–3% per event over 20 sessions, under assumed dispersions. H2 is likely to be
   INCONCLUSIVE unless the design changes.
9. **The Sharia items block paper or live trading only, not research:**
   - D2: multi-day exit logic does not exist, and no screening refresh cadence has been set.
   - D10: purification is ADVISER_REQUIRED.
   - D15: there is no broker checklist. The cash-interest question matters more for SW-A because the strategy is
     mostly in cash (INF).
   - D12: it applies to the round trips created by X2.

   This audit does not issue a ruling and does not label SW-A halal.

**Separation of tracks** (counts from the 57 rows in §10):
- research design (RD): 30, including U6, which is shared with GV;
- execution and simulation (EX): 9, including X2, which is shared with SH;
- risk (RK): 6;
- Sharia (SH): 7, including the SH2-L ledger row;
- governance (GV): 5.

Only the P4 rows (SH1–SH6 and R6) block paper or live trading alone. Every RD gap blocks design completion or
data acquisition.

---

## 2. Earnings release-time verification (track RD)

### T1. Definition of `VERIFIED`
- **Issue:** no repository file defines what evidence makes a row `VERIFIED` (FACT: SW-A U2; the
  `earnings_calendar_sources.csv` header has `timing_status` but no method document). The draft's §2.3 formula is
  PROPOSED only.
- **Why it matters:** the event table determines `s*` for every event. A loose definition places the reaction
  window on the wrong session. That corrupts `z(e)`, the entry date and the stop at the same time.
- **Options:**
  - (a) adopt the §2.3 formula as written;
  - (b) §2.3 with the evidence tiers in T2 and the session-interval mapping in T3;
  - (c) a weaker rule that allows `T_acc` alone as evidence (rejected by the draft; see T2(e)).
- **Recommended default:** (b). Use a **new SW-A-specific vocabulary**, for example
  `SWA_VERIFIED / SWA_UNRESOLVED`, so that the existing `timing_status` values in
  `config/earnings_calendar_sources.csv` keep their current, undocumented meaning and are not redefined after
  the fact (see GV4).
- **Owner approval:** Yes (choice) (SW-T). **Blocks:** DC.

### T2. Required evidence and source precedence
- **Issue:** the draft allows only (a) an explicit time or session statement in exhibit 99.x and (b) a
  timestamped issuer IR archive. It does not rank them, and it does not say whether newswire distribution
  timestamps or conference-call times count.
- **Why it matters:**
  - Many releases state only a dateline date. LIT [UNVERIFIED]: mega-cap releases often give the call time
    (sometimes in PT) rather than the release time.
  - Historical IR archives for 2016–2019 may be incomplete. Strict sources therefore raise the exclusion rate,
    possibly unevenly by period (T5).
- **Options (tiers):**
  - (a) exhibit 99.x explicit time or session statement;
  - (b) timestamped issuer IR page;
  - (c) newswire distribution timestamp (third-party primary distribution);
  - (d) conference-call time, as corroboration only, never as `T_rel`;
  - (e) `T_acc` outside regular hours plus a matching exhibit dateline date, which classifies by `T_acc`.
- **Recommended default:**
  - Precedence (a) > (b) > (c). A lower tier is used only when the higher ones are silent.
  - (d) is allowed as corroboration only.
  - (e) is **not** used in the baseline, and is reported only as a sensitivity variant. Its failure mode is
    serious: a 07:00 release filed at 16:05 would be classed AMC, so the reaction would be measured one session
    late.
  - Whether (c) is accessible historically is UNRESOLVED until acquisition is authorized.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### T3. Session statements, the consistency bound, and `Δ_max`
- **Issue (DEFECT, minor):** §2.3 tests `T_rel ≤ T_acc and T_acc − T_rel ≤ Δ_max`, but (a) may give only a
  **session statement** ("after market close") and no timestamp. The draft has no rule for turning a statement
  into a time that can be compared.
- **Why it matters:** without a rule, two reviewers can reach different verdicts on the same evidence, which
  breaks the determinism claimed in §2.6.
- **Options:**
  - map each statement to an interval:
    - "before market open" on day `d` → `[00:00, Open(d))`;
    - "after market close" on day `d` → `[Close(d), 24:00)`;
    - "during" → INTRA;
  - the statement is consistent if `T_acc ≥` the interval start, and `T_acc` minus the interval start is at most
    `Δ_max`.
  - `Δ_max` options: 1 business day (draft PROPOSED), the same calendar day, or a longer bound.
- **Recommended default:** adopt the interval mapping. Keep `Δ_max` PROPOSED pending U4.
  - LIT [UNVERIFIED]: Item 2.02 allows furnishing within four business days. A 1-business-day bound will
    therefore mark some genuine events as UNRESOLVED.
  - That is acceptable if the count is reported (T5).
- **Owner approval:** Yes (choice) for `Δ_max`; Yes (freeze) for the mapping. **Blocks:** DC.

### T4. Time-zone normalization
- **Issue:** these points are not specified:
  - the time zone of `T_acc`;
  - conversion of statements given in PT or other zones;
  - DST handling;
  - releases quoted in a non-ET zone whose ET date differs from the dateline date.
  
  Also, the derivation of the existing `accepted_et` column is undocumented (INF).
- **Why it matters:** a one-hour or one-date error moves a release across `Open(d)`, `Close(d)` or midnight,
  which changes `s*`.
- **Options and requirements:**
  - Normalize every time to `America/New_York` with the IANA tz database. Store the original string, the
    original zone and the converted value.
  - **Never use the EDGAR filing date as the event date.** The PEP row shows acceptance on 2026-07-08 17:55:54
    with a filing date of 2026-07-09 (FACT, CSV note). LIT [UNVERIFIED]: EDGAR assigns the next business day to
    late filings.
  - Verify the time-zone semantics of the EDGAR acceptance field against the filing index page before use.
    UNRESOLVED: LIT [UNVERIFIED] suggests the JSON field may carry a UTC-style suffix while denoting ET.
- **Recommended default:** all three, as written.
- **Owner approval:** Yes (freeze). **Blocks:** DC for the rule; DA for verifying the field semantics.

### T5. Conflicting or missing evidence
- **Issue:** the draft excludes UNRESOLVED events and counts them. It does not set a level of exclusion at
  which the sample itself is in doubt.
- **Why it matters:** if exclusions concentrate in early years (older IR archives) or in particular issuers,
  the sample is no longer comparable across segments, and the exclusion becomes a source of selection bias.
- **Options:**
  - (a) count only;
  - (b) count plus a predeclared BLOCKING-review threshold, set per segment and per symbol, decided before any
    price is read;
  - (c) (b) plus the draft's two-session-window sensitivity variant.
- **Recommended default:** (c). The threshold value is an owner choice, and this audit proposes no number. The
  review uses the event table only, never prices.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### T6. Audit trail and exclusion counts
- **Issue:** the draft requires URL, retrieval date and SHA-256 per evidence item. It does not specify:
  - storage location;
  - a second-review procedure;
  - the review-log format;
  - the licensing of third-party press-release copies.

  FACT: the repository is public (`AKINDA_PROVIDER_DECISION.md`, licence lines).
- **Why it matters:** the event table must be reproducible and hashed before prices are read (§2.6, §7.3).
  Committing copyrighted exhibit text to a public repository may raise terms-of-use questions (INF).
- **Options:** raw evidence git-ignored and write-once, with hashes, quotes and the review log committed; or
  everything committed; or an external store.
- **Recommended default:**
  - Raw evidence goes in a git-ignored, write-once tree.
  - Commit the evidence manifest: URL, retrieval time in UTC, SHA-256, the quoted sentence, tier, reviewer and
    rule-set version.
  - Commit an append-only review log.
  - Commit exclusion counts by reason × symbol × year.
  - Commit the event-table SHA-256 before any price acquisition.
  - A second-pass review of a predeclared sample of rows.
- **Owner approval:** Yes (choice) for storage and licensing. **Blocks:** DC.

### T7. EDGAR access, coverage and identity of the requester
- **Issue:**
  - EDGAR terms of access are [UNVERIFIED] (FACT: SW-A U3, citing `AAOIFI_DATA_PROVIDER_ASSESSMENT.md:41-45`).
  - The `submissions` "recent list" reached back only to 2017-09-06 for MU (FACT, CSV note), so earlier filings
    need further pages.
  - LIT [UNVERIFIED]: the SEC asks automated clients to declare a contact identity and to limit request rates.
- **Why it matters:** the development segment starts in 2016. Incomplete pagination would silently drop early
  events.
- **Options:** authorize EDGAR access after the hold with the terms verified first (SW-D); or defer.
- **Recommended default:**
  - Verify the terms first.
  - The owner chooses the declared contact identity.
  - Add a completeness check: an expected number of RESULTS events per symbol per fiscal year (see C2).
- **Owner approval:** Yes (choice). **Blocks:** DA.

---

## 3. Event classification (track RD)

### C1. Item 2.02 classification rule set
- **Issue:** the classes RESULTS / PRELIM / OTHER_2_02 / UNCLASSIFIABLE are named, but no criteria are written.
  The only precedent is one owner decision (TSLA deliveries, FACT, CSV).
- **Why it matters:** the classification decides which filings become events and which are excluded. It is a
  free parameter until it is written down.
- **Options:**
  - (a) criteria-based: RESULTS if the exhibit reports financial results for a **completed** fiscal period
    (an income statement or equivalent); PRELIM if the results or ranges are for a period not yet formally
    reported; OTHER for operational metrics or guidance only; anything ambiguous is UNCLASSIFIABLE;
  - (b) human judgement with a log only;
  - (c) a keyword classifier plus human review.
- **Recommended default:** (a), with every ambiguous case logged. Classification reads filing text only.
- **Owner approval:** Yes (choice) (SW-C). **Blocks:** DC.

### C2. Results not furnished under Item 2.02, and missing quarters
- **Issue:** the event definition requires Item 2.02. A quarter whose results appear only under another item,
  or without an 8-K, is silently missing.
- **Why it matters:** an event is lost without trace, and the loss is not random.
- **Options:**
  - (a) Item 2.02 only, with a completeness check (one RESULTS event per symbol per fiscal quarter, gaps
    listed);
  - (b) also accept Items 7.01 and 8.01 with an explicit rule;
  - (c) no check.
- **Recommended default:** (a). Missing quarters are counted and reviewed from filing metadata only.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### C3. Fiscal-period identification, duplicates and pre-announcements
- **Issue:** the "earliest RESULTS filing for that period" rule (§2.5) needs:
  - a rule for identifying the fiscal period (several universe issuers have non-calendar fiscal years, INF);
  - a decision on a RESULTS event that follows a PRELIM for the same period.
- **Why it matters:** after a PRELIM, the RESULTS reaction is diluted, because part of the news is already out.
- **Options for RESULTS events preceded by a PRELIM:** include them; include them but flag; exclude them.
- **Recommended default:**
  - The fiscal period is taken from the exhibit's stated period-end date.
  - RESULTS events preceded by a PRELIM are included but flagged, with a flag-excluded sensitivity variant.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### C4. Amendments (`8-K/A`) and the date of information
- **Issue:** §2.5 turns an event to UNRESOLVED when an `8-K/A` changes the time or the class. It does not
  restrict *when* the amendment was filed.
- **Why it matters:** an amendment filed months after `s*` is used to exclude an event retroactively.
  - Correcting a data error is legitimate.
  - The problem is that the exclusion is applied without a log of when it became known.
- **Options:** (a) any amendment, logged with its filing date; (b) only amendments accepted before
  `Open(s*+1)`; (c) (a) plus a sensitivity run on rule (b).
- **Recommended default:** (c).
- **Owner approval:** Yes (choice). **Blocks:** DC.

### C5. BMO/AMC boundary rules
- **Issue:** §2.4 covers BMO, AMC, NON_SESSION and INTRA. The boundary cases are implied but not stated:
  - a release at exactly 16:00 counts as AMC, because the rule is `≥ Close`;
  - on an early-close day, `Close = 13:00`, so a 14:00 release is AMC;
  - a release after midnight ET before the session is BMO for that session;
  - a release on the evening before a holiday maps to the next session.
- **Why it matters:** determinism (§2.6), and the unit tests listed in discovery report §12, stage 6.
- **Recommended default:** write the cases explicitly into the frozen text, together with the matching unit
  tests.
- **Owner approval:** Yes (freeze). **Blocks:** DC.

### C6. Releases during market hours (INTRA)
- **Issue:** INTRA events are excluded and counted. That is decided. One inconsistency remains:
  - The collision rule (§4.6) uses `T_acc` to time the forced exit for a held symbol.
  - §2.3 says "`T_acc` alone never sets `T_rel`".
  - For collisions, `T_acc` therefore acts as a release time.
- **Why it matters:** suppose a held symbol releases at 07:00 and files at 09:45. The simulated exit is the next
  day's open, a full session after the price reacted. The draft already notes the gap exposure; the timing
  inconsistency is not stated.
- **Options:**
  - (a) keep `T_acc` for collisions, labelled conservative;
  - (b) use the same `T_rel` method for collisions where one is available;
  - (c) (a), plus a count of collisions where `T_rel` (if verified) precedes `T_acc` by at least one session.
- **Recommended default:** (c).
- **Owner approval:** Yes (choice). **Blocks:** DC.

### C7. The σ-window exclusion rule may remove many events
- **Issue:** §3.4 requires that no RESULTS event of the same symbol falls inside `[s*−61, s*−2]`. Quarterly
  events are about 63 sessions apart (draft §4.3), so the gap between some consecutive reports can be shorter
  than 61 sessions.
  - INF: this is likely for a quarter reported quickly after a late annual report.
  - Those events would be **excluded entirely**, possibly in a pattern tied to particular quarters.
- **Why it matters:** this is a silent, systematic reduction of a sample that is already small.
- **Options:**
  - (a) keep the rule;
  - (b) keep the event, but drop the prior event's reaction sessions (`s'*`, `s'*+1`) from the σ sample and
    require at least a minimum number of valid AR observations;
  - (c) use a fixed window that ends earlier.
- **Recommended default:** (b). In addition, the number of events affected under (a) can be computed from the
  event table alone, **before any price is read**, and reported before the choice is frozen.
- **Owner approval:** Yes (choice). **Blocks:** DC.

---

## 4. Statistical design (track RD)

### S1. Abnormal return and volatility denominator
- **Issue:** the definitions are specified (draft §3.4: `AR = r_i − r_SPY` on the PIT total-return basis, and
  `σ` = the sample standard deviation over 60 sessions `[s*−61, s*−2]`). Three points are not:
  - **ddof** is not stated. Protocol v2 uses `ddof = 1` elsewhere (FACT, §12).
  - The handling of a missing SPY bar is not stated.
  - The β = 1 baseline is PROPOSED, not approved.
  - Also, the universe stock is itself a constituent of SPY (disclosed in the draft, but its effect is
    unquantified).
- **Why it matters:** σ scales every `z(e)`. The SPY overlap slightly reduces AR for the largest names (INF).
- **Recommended default:**
  - `ddof = 1`.
  - A missing stock or SPY bar in the window makes that observation invalid, with no imputation.
  - β = 1 baseline, with the estimated-β variant as a sensitivity run (as drafted).
- **Owner approval:** Yes (freeze) (part of SW4). **Blocks:** DC.

### S2. DEFECT: the drift window is not the traded window
- **Issue:**
  - P1 defines `D(e) = Σ_{k=s*+1}^{s*+H} AR_i(k)`, which runs close-to-close from `Close(s*)` to `Close(s*+H)`.
  - The trade runs from `O(s*+1)` to `O(s*+1+H)` (§4.2–§4.3).
  - So `D(e)` **includes** the overnight return `C(s*) → O(s*+1)`, which no market-on-open order can capture.
  - It also **excludes** the last overnight `C(s*+H) → O(s*+1+H)`, which the trade bears.
- **Why it matters:** if much of the post-reaction move happens overnight, P1 can pass while the trade earns
  nothing. Discovery report §10 states the falsification test as "the mean net-of-cost market-adjusted return of
  eligible events **over the holding window**". That points at the traded window.
- **Options:**
  - (a) keep the close-based `D(e)` for H1, labelled an **information** estimand, and define H2 strictly on the
    traded open-to-open window;
  - (b) move H1 to the traded window too;
  - (c) report both windows for both hypotheses, and gate on one.
- **Recommended default:** (a). H1 tests whether the drift exists; H2 tests whether it can be traded. The
  label must say which is which.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### S3. H1 estimand
- **Issue:** H1 is stated as "larger **positive** reactions are followed by larger drift". P1 regresses over
  **all** eligible events, negative `z` included. It does not state whether there is an intercept or fixed
  effects.
- **Why it matters:** a slope driven by the negative tail (drift after bad news) supports H1 as worded on all
  events. It is irrelevant to a long-only strategy that trades only `z ≥ z0`.
- **Options:**
  - (a) all events, pooled OLS with intercept (as drafted);
  - (b) `z > 0` events only;
  - (c) (a) as primary, plus (b) and a by-sign split reported;
  - (d) add season (quarter) fixed effects, to absorb market-wide drift that the β = 1 adjustment leaves in.
- **Recommended default:** (c), with (d) as a sensitivity run. The draft's wording of H1 should match the
  chosen sample.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### S4. H2 estimand and its null baseline
- **Issue:** P2 is "mean net drift for `z ≥ z0` events at 5 bps". The quantity is not defined. The candidates
  are:
  - (i) `D(e) − 2s` on AR, which is market-hedged and cannot be earned long-only;
  - (ii) the per-trade net return on the traded window, with stops and costs;
  - (iii) (ii) minus SPY's return over the identical window;
  - (iv) a portfolio-level result against a benchmark, which is protocol v2's approach (B1, §10, §13.B).

  The null is "≤ 0", but on this universe a positive long-only mean is expected without any event effect.
  FACT: protocol v2 §13.B rationale and §2 survivorship rows.
- **Why it matters:** without a non-event baseline, a PASS can reflect hindsight universe selection or market
  drift rather than an earnings effect.
- **Options for the baseline:**
  - (a) none (as drafted);
  - (b) the same symbols' mean AR over predeclared non-event windows of the same length H, at least a fixed
    number of sessions away from any event;
  - (c) SPY-relative returns only.
- **Recommended default:**
  - Gate on (iii), measured as the difference from baseline (b).
  - Report (ii) and the portfolio simulation descriptively.
  - The placebo window rule must be frozen before prices are read.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### S5. Inference: weekly clustering, overlap and few clusters
- **Issue:**
  - §7.4 offers "clustered by calendar week **or** a block bootstrap by quarter". No primary method is chosen.
  - Twenty-session drift windows of events in **adjacent** weeks overlap by up to about 15 sessions and share
    sector and market shocks. Clustering by week treats those weeks as independent.
  - Clustering by quarter gives very few clusters: 8 in the 2-year validation segment.
- **Why it matters:** standard errors that are too small turn noise into a PASS. Choosing the method after
  seeing the results is a form of p-hacking.
- **Options:**
  - (a) calendar-time portfolio: a daily mean AR of all stocks inside a drift window, then a time-series mean
    with a HAC lag of at least H. LIT [UNVERIFIED]: this is a standard approach for long-horizon event
    studies. It suits H2;
  - (b) week clusters with a wild cluster bootstrap;
  - (c) a moving-block bootstrap over calendar time with block length at least H sessions, which suits the H1
    slope;
  - (d) two-way clustering (symbol × week).
- **Recommended default:**
  - (a) for H2 and (c) for H1. Each is fixed as **the** primary method before data.
  - (b) and (d) are reported only.
  - Disclose that 25 correlated mega caps give limited effective independence.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### S6. Minimum detectable effect and sample-size assumptions
- **Issue:** these are not addressed:
  - The `n_min` formula (§7.5) is for a **mean** (H2). There is no formula for the H1 **slope**, which depends
    on `Var(z)`.
  - `n` is counted in events, not in effective independent units, although clustering (S5) inflates the
    variance.
  - `σ_D` is estimated on development data. That is acceptable only if frozen before validation, which §7.3
    already requires.
  - `δ` must not be informed by the development data.
- **Illustration (ASSUMPTION ONLY; not a data estimate; no data was used).** One-sided α = 0.05 and power 0.8
  give `z_{1−α} + z_{1−β} ≈ 1.645 + 0.842 = 2.487`, so `MDE = 2.487 · σ_D / √n`:

  | assumed `σ_D` (20-session AR) | n = 50 | n = 100 | n = 200 |
  |---|---|---|---|
  | 4% | 1.41% | 0.99% | 0.70% |
  | 6% | 2.11% | 1.49% | 1.05% |
  | 8% | 2.81% | 1.99% | 1.41% |

  - Multiply by `√DEFF` for clustering.
  - Upper bound on counts (INF, from the draft's own arithmetic): 25 symbols × 4 events per year ≤ 100 events
    per year. That gives ≤ 200 in validation (2020–2021) and ≤ 400 in the historical test (2022–2025), before
    exclusions. The `z ≥ z0` subset is a fraction of that, and the fraction is unknown.
- **Why it matters:** if the plausible MDE is larger than any plausible drift, H2 is INCONCLUSIVE by
  construction, and the test is not "decisive" as the draft hopes (§1.3).
- **Options:**
  - (a) accept a low-power H2 and make H1 primary (as drafted);
  - (b) pool validation and the historical test into one confirmatory historical segment (more power, one fewer
    stage);
  - (c) widen the universe (blocked by U1);
  - (d) keep it as drafted and accept INCONCLUSIVE as the likely outcome.
- **Recommended default:**
  - Add a slope MDE formula.
  - Express `n_min` in effective units.
  - Fix the option before data. The choice among (a), (b) and (d) is the owner's.
- **Owner approval:** Yes (choice) (SW3). **Blocks:** DC.

### S7. Acceptance and rejection logic
- **Issue:** the §7.7 table has several unstated points:
  - **P2 has no interval requirement:** it passes on a point estimate > 0, while P1 requires a CI above 0.
  - **`δ` is not in the acceptance rule.** It is only a power input, so an economically trivial drift can pass.
  - **The "momentum relabel" rejection is undefined.** "β₁ loses significance … β₂ carries the effect" gives no
    test, level or decision rule.
  - **Precedence is unstated.** For example, with `n < n_min` and `β₁ ≤ 0`, is the result REJECT or
    INCONCLUSIVE?
  - **Sequencing is unstated.** Does a validation REJECT or INCONCLUSIVE stop the historical test, as protocol v2
    §15.3 does?
  - **The segment requirement is unclear.** "RESEARCH-PASSED (historical)" does not say whether validation must
    also pass.
- **Why it matters:** an incomplete rule leaves room to interpret it after the results are known.
- **Options and recommended default:**
  - Fix the precedence: methodological FAIL → INCONCLUSIVE (`n < n_min`) → REJECT → PASS.
  - P2 requires a one-sided 95% interval above `δ`, or above 0 with the point estimate at least `δ`. The owner
    chooses between these.
  - Momentum relabel: REJECT if the lower bound of the one-sided 95% interval for `β₁` in the controlled
    regression is ≤ 0 **and** the interval for `β₂` excludes 0.
  - A validation result other than PASS stops the sequence (no historical test).
  - The historical test PASS requires the validation PASS.
- **Owner approval:** Yes (choice) (SW3). **Blocks:** DC.

### S8. Multiple testing
- **Issue:**
  - SW-A has several inferential results: P1, P2 and the momentum test, in up to two segments.
  - PASS requires all of them (an intersection-union structure), which does not inflate false PASSes within
    SW-A (INF).
  - But SW-A is one of several families proposed or tested in this project. Protocol v2 §14 keeps a cumulative
    trial count and applies Holm diagnostics. The SW-A draft has no such provision.
  - The sensitivity grid (`z0` × `H` = 9 cells, plus variants) is report-only as drafted.
- **Why it matters:** repeated family-level tests on the same universe inflate the chance that at least one
  family passes by chance.
- **Options:** (a) the SW-A α stands alone, with a disclosed project-level trial count; (b) Holm across
  concurrently evaluated new families (for example SW-A and DT-A); (c) a stricter α.
- **Recommended default:**
  - (a) plus disclosure.
  - Restate in the frozen text that no sensitivity cell can replace the baseline.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### S9. Segment boundaries and leakage
- **Issue:** events are assigned to a segment by their `s*` date. A development event with `s*` late in 2019 has
  a drift and exit window that reads validation-period prices. The draft is also silent on whether each
  simulation segment starts flat and is liquidated at its end (protocol v2 §11.6 does both).
- **Why it matters:** development work would see validation-period prices, a small but avoidable leak.
- **Options:**
  - (a) exclude events whose exit falls after their segment's end;
  - (b) embargo the first `H+1` sessions of each later segment;
  - (c) allow the overlap and disclose it.
- **Recommended default:** (a), applied to development only, with the count reported. Segments start flat (as
  in protocol v2).
- **Owner approval:** Yes (choice). **Blocks:** DC.

### S10. Early-sample feature availability
- **Issue:**
  - The 12-1 momentum control needs about 252 sessions of history.
  - The estimated-β variant needs a window of `[s*−250, s*−21]` sessions.
  - SIP daily data starts on 2016-01-04 (FACT, day17 §4).
  - So neither is available for 2016 development events.
- **Why it matters:** the momentum test is a **rejection** criterion. It must be computable in every gated
  segment. It is, for 2020 onward (INF).
- **Recommended default:** state in the frozen text that both features are undefined before about 2017-01, and
  that development reporting marks them `undefined (reason)`.
- **Owner approval:** Yes (freeze). **Blocks:** DC.

---

## 5. Trading simulation (track EX)

### X1. DEFECT: exit order on the time-exit session
- **Issue:** §4.5 evaluates `O(t) ≤ S` → `L(t) ≤ S` → `t = s*+1+H`, in that order. On the time-exit session the
  position is closed at `O(t)`. A later intraday low is irrelevant, yet the algorithm can record a stop fill at
  `S` instead.
- **Why it matters:** it biases the loss upward and miscounts stop exits. The effect is small but systematic.
- **Correction (no real choice):** on `t = s*+1+H`, exit at `O(t)`, which is a gap-through-stop exit if
  `O(t) ≤ S`. The low check applies only to `t < s*+1+H`. Also clarify the wording "sessions `t > s*+1`, then the
  entry session".
- **Owner approval:** Yes (freeze). **Blocks:** DC.

### X2. DEFECT: the entry-session stop creates same-session round trips
- **Issue:** on `s*+1` the position is bought at the open, and the rule "`L(s*+1) ≤ S` → exit at `S`" sells it
  the same session.
- **Why it matters:**
  - This is intraday buy-and-sell.
  - Draft §8 says D12 (day trading) "does **not** apply". For these trades, that statement is wrong.
  - D12 is ADVISER_REQUIRED (FACT, `AAOIFI_MVP_DECISIONS.md`).
  - Cash-account settlement adds a further question: selling on the purchase day. Broker rules are NOT VERIFIED.
- **Options:**
  - (a) keep the rule, research only, and count these trades;
  - (b) first stop check at `O(s*+2)`, so an entry-day breach exits at the next open;
  - (c) refer to the adviser and broker.
- **Recommended default:** (b) as the baseline, because no position then closes on its entry session. Report (a)
  as a sensitivity run. Ask the adviser regardless (SH4).
- **Owner approval:** Yes (choice) + Adviser. **Blocks:** DC (design choice); PL (ruling).

### X3. DEFECT: the raw stop sits on top of a market-adjusted signal
- **Issue:** eligibility uses `AR(s*)`, but `S = C(s*−1)` and the sizing `N = RiskBudget / (C(s*) − S)` use the
  **raw** reaction.
  - Arithmetic illustration only (not data): market −3% and stock +0.5% on `s*` give AR +3.5%, which can have
    `z ≥ 2`. The raw stop distance is then about 0.5%, so the notional is about 100% of capital, capped by cash.
  - Market −4% and stock −1% give AR +3%, but `E ≤ S` is likely, so the event is skipped.
- **Why it matters:** which events are traded, and how large each position is, depend on the market's direction
  on the reaction day. Cash capping then decides the realized risk. This mixes a market-timing effect into the
  event test.
- **Options:**
  - (a) keep it, and report cash-capped and skipped counts;
  - (b) a maximum notional per position (R3);
  - (c) a minimum stop-distance floor, for example a multiple of σ. This adds a parameter;
  - (d) skip events whose raw reaction is below a stated fraction of their AR.
- **Recommended default:** (a) + (b). The cap value is the owner's. Report the sizing distribution.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### X4. Missing bars at the exit, stop or collision session
- **Issue:** the draft cancels an entry when there is no bar at `s*+1`. It does not say what happens when an
  exit session has no bar.
- **Why it matters:** determinism, and a potential silent extension of a holding.
- **Options:** (a) protocol v2 §8.6, a pending sell retried at each subsequent open; (b) exit at the next
  available open, with the gap counted.
- **Recommended default:** (a), which is the existing convention.
- **Owner approval:** Yes (freeze). **Blocks:** DC.

### X5. Simultaneous signals and cash allocation
- **Issue:** events cluster in earnings season, and many entries can share one open. The draft caps `N` by cash
  but gives no ordering or allocation rule. OPEN-R3 in D1/S1 §3 is the same gap.
- **Why it matters:** different rules give different trades, and the choice is not neutral.
- **Options:**
  - (a) ascending ticker order, which is deterministic and independent of results;
  - (b) pro-rata scaling (`λ` as in protocol v2 §8.4);
  - (c) rank by `z`. This adds a selection rule and must be frozen as part of the strategy.
- **Recommended default:** (b), or (a) if integer shares are kept (X9). Count the scaled or skipped events.
- **Owner approval:** Yes (choice) (R3). **Blocks:** DC.

### X6. Collision exits
- **Issue:** see C6. In addition, the collision rule covers only the held symbol's own Item 2.02 filings. A peer's
  results in the same week (a sector shock) are not a collision, which is correct but undisclosed.
- **Recommended default:** disclose this; count collisions by class.
- **Owner approval:** Yes (freeze). **Blocks:** DC.

### X7. Execution costs and fill realism
- **Issue:**
  - Costs of 0/5/10 bps per side and a stop-slippage grid of {0, 10, 25} bps are PROPOSED.
  - FACT, day17 §3: the SIP daily `open` is the first eligible trade, which is "not guaranteed" to be the auction
    print.
  - The draft applies no extra slippage to gap-through-stop or collision exits at volatile opens.
- **Why it matters:** collision and gap exits happen at the most volatile opens. Fill realism is weakest exactly
  where losses are largest.
- **Options:** (a) as drafted; (b) apply the stop-slippage grid to gap and collision exits too.
- **Recommended default:** (b), reporting only. The primary result stays at 5 bps.
- **Owner approval:** Yes (choice) (SW4). **Blocks:** DC.

### X8. Dividends and corporate actions
- **Issue:**
  - (i) The stop is not adjusted for dividends (draft §4.7). This is stated, not labelled PROPOSED. S1's
    equivalent is an open decision (OPEN-S5).
  - (ii) "Any other corporate action → BLOCKING review" would also fire on **acquirer-side** merger records.
    FACT, day17 §5: for example CRM←WORK, AMD←XLNX, MSFT←NUAN. These do not change the acquirer's shares.
  - (iii) Day17 blockers C1–C4 apply equally to an SW-A snapshot:
    - C1: the `process_date` query window;
    - C2: CUSIP identity (the META ticker previously named an ETF);
    - C3: the per-share basis of a dividend that shares its ex-date with a split;
    - C4: `data_quality`.
- **Why it matters:** (ii) can stall the pipeline on irrelevant records, and (iii) left undecided corrupts the
  total-return series.
- **Options:** for (ii), classify acquirer-side records as non-events with a log, or review each one.
- **Recommended default:**
  - Label (i) PROPOSED and approve or reject it explicitly.
  - Treat (ii) records as logged non-events unless the record changes the holder's share count or cash.
  - (iii) needs the same decisions as day17 §8, taken for SW-A's own snapshot. They are not inherited
    automatically from protocol v2.
- **Owner approval:** Yes (choice). **Blocks:** DA.

### X9. Accounting conventions
- **Issue:** these are not set:
  - the `InitialResearchCapital` value;
  - integer (`floor`, the draft and D1/S1 §3) versus fractional shares (protocol v2 §11.9);
  - interest on cash (protocol v2 uses 0%);
  - start-flat and end-liquidation rules per segment.
- **Why it matters:** integer shares plus a fixed capital make results depend on the capital level.
- **Recommended default:**
  - `E_0` = 100,000 (the protocol v2 convention).
  - Integer shares, as drafted.
  - Cash earns 0%.
  - Segments start flat and are liquidated at the end.
- **Owner approval:** Yes (choice). **Blocks:** DC.

---

## 6. Universe and bias (track RD)

### U1. Point-in-time universe
- **Issue:** FACT: there is no point-in-time universe (protocol v2 §2; draft §6). The 25-symbol list is
  hindsight-selected (OPEN-SW1).
- **Options:** (a) the 25 frozen symbols, with the bias disclosed (discovery report REC, OD-5); (b) a broader
  universe, which requires a PIT source that does not exist.
- **Recommended default:** (a) for the first test.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### U2. Survivorship and selection bias in the SW-A estimands
- **Issue:** the bias is disclosed, but no design element limits it. Survivors that later did well show
  positive average AR in any window. That inflates H2 and, more mildly, H1's intercept (INF).
- **Recommended default:** the non-event baseline in S4. Never describe results as survivorship-safe (as
  drafted).
- **Owner approval:** covered by S4. **Blocks:** DC.

### U3. Historical Sharia-screen availability
- **Issue:**
  - FACT: Akinda gives current verdicts only.
  - FACT: the registry `config/sharia_eligibility.csv` is header-only.
  - Historical results are therefore unscreened. They may include names a screen would exclude; this is not
    verified for any symbol here.
- **Options:**
  - (a) unscreened research only (as drafted);
  - (b) also report a subset screened with **current** verdicts. This is hindsight screening and must be
    labelled so. It is limited by the quota of 10 a day and needs a licence check (FACT,
    `AKINDA_PROVIDER_DECISION.md`).
- **Recommended default:** (a). (b) is the owner's choice.
- **Owner approval:** Yes (choice). **Blocks:** DC (if (b) is chosen, the subset is predeclared).

### U4. Symbol-to-issuer identity
- **Issue:** a point-in-time symbol → CIK map is needed, covering:
  - the XOM CIK change (FACT, CSV note: "new CIK 2115436");
  - the FB → META ticker change;
  - the GOOGL share class against the single Alphabet issuer;
  - CUSIP identity for corporate actions (X8 (iii)).

  None of these is frozen.
- **Recommended default:** a committed map with a source per row, frozen before EDGAR acquisition.
- **Owner approval:** Yes (freeze). **Blocks:** DA.

### U5. Stage R and Stage H contamination boundaries
- **Issue:**
  - A fresh SW-A snapshot for 2016–2025 would cover the **dates** of Stage R (2016-01-04 → 2022-12-30) and
    Stage H (2021-01-04 → 2026-06-02). FACT: protocol v2 §3.9.
  - The project has already run and documented V2-MOM holdout work on the same 25 symbols. FACT: a holdout
    daily-concentration document exists. Its content was not opened here.
  - The SW-A historical test (2022–2025) is therefore **not blind**. The draft already labels it pseudo-OOS.
  - These points are still open (OPEN-SW2, OD-6):
    - (i) whether fresh data may cover those dates at all;
    - (ii) the snapshot location;
    - (iii) a prohibition on reading Stage R and Stage H files.
- **Options for (i):**
  - (a) allow it with a fresh, separate snapshot;
  - (b) allow only pre-2021 dates;
  - (c) forward-only.
- **Recommended default:**
  - (i) is the owner's choice. The audit notes that (b) leaves about 4 years (2016–2020) in total, which worsens
    power (S6).
  - (ii) a separate write-once tree, never under `data/oos_cache/protocol_v2/`.
  - (iii) an explicit prohibition in the frozen text. Code reuse is allowed; reuse of data files is not.
- **Owner approval:** Yes (choice). **Blocks:** DA.

### U6. The excluded 2026 period and the start of the forward confirmation
- **Issue:** three statements in the repository disagree (FACT for each):
  - DAY-22 §3.2.3: "No forward market data may be acquired into the research cache until the 252-session waiting
    period has concluded" (V2-MOM: 2026-10-08 → 2027-10-08, §3.1).
  - D1/S1 §0.5: it cites `acquisition/v2/contract.py:112` for a forward window of 2026-10-08 → 2027-01-07, and
    `fwd-gate2` evaluation no earlier than 2026-12-09 16:15 ET.
  - SW-A §7.2: forward confirmation from "the end of the research hold (not earlier than after the `fwd-gate2`
    evaluation)".

  Which rule binds a **different** family's acquisition of data dated 2026-10-08 or later is not documented. It
  was not resolved here; `contract.py` was not read in this task.
- **Why it matters:** the SW-A forward test is the **only** confirmatory test (draft §7.2, §7.7). Starting it
  under the wrong rule could breach V2-MOM's blind period, and DAY-22 §3.2.4 forbids forward-guided proposals.
- **Options:**
  - (a) SW-A forward data only after the V2-MOM 252-session period ends;
  - (b) after the `fwd-gate2` evaluation, with an explicit protocol statement that the DAY-22 restriction does not
    bind other families;
  - (c) another date set by the protocol owner.
- **Recommended default:** none. This is a protocol-ownership decision. Until it is made, treat (a) as binding
  (fail-closed).
- **Owner approval:** Yes (choice). **Blocks:** DA (forward); PL.

---

## 7. Risk (track RK)

The 0.5% per-trade risk rule is an approved owner decision (D1/S1 §3; SW-A §5). This audit does **not**
reopen it. The gaps below concern how it is applied.

### R1. Capital basis and its value
- **Issue:** OPEN-R1 (fixed initial capital or current equity) is undecided. The draft keeps a fixed initial
  capital, pending decision, and the value is unset (X9).
- **Recommended default:** fixed initial capital as the primary basis, with equity-based sizing reported only if
  the owner approves it (as drafted).
- **Owner approval:** Yes (choice). **Blocks:** BT.

### R2. Portfolio-wide open-risk limit
- **Issue:** OPEN-R2b. The draft itself says 0.5% "is workable only together with a portfolio open-risk cap".
  Neither its definition nor its value is set:
  - planned risk at entry, `Σ N_j (E_plan,j − S_j)`;
  - or mark-based risk, `Σ N_j · max(0, mark_j − S_j)`.
- **Why it matters:** in earnings season, total open risk can reach `n_open × 0.5%`, with correlated gaps.
- **Options:** (a) an uncapped run labelled "uncapped" (as drafted); (b) a cap on planned risk at entry, used for
  admission; (c) a cap on mark-based risk.
- **Recommended default:** (b) for admission, with mark-based risk reported. The value is the owner's.
- **Owner approval:** Yes (choice). **Blocks:** BT if a capped run is required; PL in any case.

### R3. Per-position notional and gross exposure
- **Issue:** OPEN-R2g. There is no notional cap beyond available cash. See X3.
- **Recommended default:** a per-position notional cap. The owner sets the value.
- **Owner approval:** Yes (choice). **Blocks:** DC (it enters the sizing rule).

### R4. Correlated event concentration
- **Issue:** OPEN-R2d/e/f. The universe has industry clusters. INF from general knowledge (there is no sector
  data in the repository): NVDA, AVGO, AMD, QCOM, INTC, MU and AMAT are commonly classed as semiconductors, and
  they report in the same weeks. The draft has no sector map and no concentration limit.
- **Options:**
  - (a) report only (weekly open-risk profile, top-symbol share, as drafted);
  - (b) a static, committed sector map plus a per-sector position cap;
  - (c) a correlation-based limit.
- **Recommended default:** (a) + a static map for **reporting**. A cap is the owner's choice.
- **Owner approval:** Yes (choice). **Blocks:** BT (if capped); PL.

### R5. Gap risk beyond the nominal stop
- **Issue:** the draft lists why realized loss can exceed 1R and reports `R < −1`. No stress metric or tolerance
  is predeclared.
- **Recommended default:**
  - Report the realized R distribution, the worst single-trade R, the worst week of combined realized loss as a
    share of capital, and the gap and collision exit counts.
  - Keep these as reporting only, with no threshold added after results.
- **Owner approval:** Yes (freeze). **Blocks:** DC.

### R6. Cash-account settlement in the simulation
- **Issue:** D1/S1 §3 proposes that buys are limited to settled cash (broker rule NOT VERIFIED). The SW-A draft
  is silent. A stop exit and a new entry at the same open would reuse unsettled proceeds.
- **Options:** (a) ignore settlement in research and disclose it; (b) a settled-cash rule in the simulation.
- **Recommended default:** (b) if it is cheap to implement, otherwise (a) with disclosure. Broker confirmation is
  needed before paper or live trading.
- **Owner approval:** Yes (choice) + broker confirmation. **Blocks:** PL (BT if (b) is chosen).

---

## 8. Sharia (track SH): unresolved requirements only

**This section is not a fatwa. It does not label SW-A, or any instrument, halal or compliant.** It lists what
the repository records as unresolved.

### SH1. D2: status change during a multi-day position
- **FACT:** D2 is PROVISIONAL: no grace period, and an open position is closed at the next regular session.
  "Exit logic for multi-day positions does not exist"; any swing runner must add it before using the registry
  (`AAOIFI_MVP_DECISIONS.md` D2).
- **Additional gap:**
  - No screening **refresh cadence** has been fixed. FACT: `valid_days` is an operator argument from 1 to 92, and
    "no default is assumed".
  - The Akinda Basic quota is 10 `/compliance` calls a day (FACT).
  - A 20-session holding needs a rule for how often held names are re-checked.
- **Needs:** owner (cadence, quota plan) + adviser (whether "next session" is the required timeline).
- **Blocks:** PL.

### SH2. D10: purification
- **FACT:** ADVISER_REQUIRED. No calculator exists. The ledger must keep period-end holdings so that purification
  can be computed later. The period, the "total prohibited income" scope and the share basis are undefined. The
  dividend-based formula was withdrawn in Draft 6.2.
- **Additional gap:**
  - Whether typical SW-A positions span the relevant period end depends on the undefined period. INF only: entry
    follows a results release and H is 20 sessions, so many positions may close before the next fiscal quarter
    end. This is **not** a ruling.
  - The SW-A ledger schema must record the ex-dates, shares and amounts of dividends received, and period-end
    holdings.
- **Needs:** adviser. The ledger fields are a design item (Yes (freeze)).
- **Blocks:** PL (ruling); DC (ledger fields only).

### SH3. D15: broker and account conditions
- **FACT:** PROVISIONAL. The requirements are:
  - a US SEC/FINRA broker-dealer;
  - a cash account with no margin;
  - opting out of stock lending;
  - no interest on idle cash, with the interest question referred to the adviser;
  - a written broker checklist before any live account;
  - an order path that refuses short, margin and derivative orders.

  No checklist or order path exists.
- **Additional gap (INF):** SW-A is mostly in cash between earnings seasons, so the idle-cash interest question
  matters more for SW-A than for a fully invested strategy.
- **Needs:** owner + adviser + broker.
- **Blocks:** PL.

### SH4. D12: same-session round trips
- **FACT:** D12 (whether day trading is permissible under T+1 and the possession rules) is ADVISER_REQUIRED.
- **Gap:** X2 shows that the draft's entry-session stop produces same-day round trips, contrary to draft §8. If
  X2 option (b) is adopted, no position closes on its entry session. D12 then remains relevant only if another
  path closes a position on its entry day.
- **Needs:** owner (X2) + adviser.
- **Blocks:** PL.

### SH5. D13-A: screening source and licence
- **FACT:**
  - Akinda `/compliance` is the adopted stock-level screen.
  - The vendor states it is "Not a fatwa".
  - The registry has no rows.
  - The licence must be checked before committing rows, because the repository is public.
- **Needs:** owner (licence, rows).
- **Blocks:** PL.

### SH6. Event-driven holding (OPEN-SH)
- **FACT (draft §8):** no specific adviser question has been identified. The draft asks the adviser to confirm
  that event-driven multi-week holding on public information raises no issue.
- **Needs:** adviser.
- **Blocks:** PL.

---

## 9. Governance (track GV)

### GV1. Research hold and authorization
- **Issue:** the evidence inventory (§10) recommends holding all new research until the `fwd-gate2` evaluation
  (not before 2026-12-09 16:15 ET). OPEN-G2 is undecided. EDGAR access and the price snapshot need explicit
  authorization (SW-D, OD-4).
- **Owner approval:** Yes (choice). **Blocks:** DA.

### GV2. SW-A priority (SW-0, OD-3)
- **Issue:** SW-A is not yet approved as the swing priority.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### GV3. Protocol home, freeze and registry
- **Issue:**
  - SW-A is not a protocol v2 family (v2 §14 lists exactly three).
  - It needs its own frozen protocol: a document plus a machine-readable twin, a freeze commit, a config SHA-256,
    experiment IDs and a registry path (cf. OPEN-G5).
  - It also needs a statement of which protocol v2 conventions it inherits: price basis, execution, costs,
    reproducibility.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### GV4. Retroactive redefinition of the 2026 calendar
- **Issue:** SW-T says the `VERIFIED` definition "applies retroactively to the 2026 file's semantics too".
  FACT, SW-A §0.1: that file is consumed by ORB (`strategy/day/orb_rules.py:188-211`). Redefining its status
  values would alter the meaning of an existing input after its use.
- **Recommended default:** leave the 2026 file's semantics as recorded, use separate SW-A status values (T1), and
  document separately what the 2026 `VERIFIED` meant, if it can be reconstructed.
- **Owner approval:** Yes (choice). **Blocks:** DC.

### GV5. Stale operational text in the SW-A draft
- **Issue:** FACT: draft §9 OPS-1 and §11 say the file "is untracked; no commit or push". All three documents
  were committed in `80e94ad`. The text was not edited in this task, as instructed.
- **Recommended default:** correct it in the next revision of the draft.
- **Owner approval:** no. **Blocks:** nothing.

---

## 10. Prioritized decision table

Priority levels:
- **P0**: a defect, or a decision that changes what is tested;
- **P1**: required to finish the design;
- **P2**: required before data acquisition;
- **P3**: required before a backtest;
- **P4**: required before paper or live trading.

| Pri | ID | Decision | Track | Owner approval | Blocks | Recommended default (proposal only) |
|---|---|---|---|---|---|---|
| P0 | GV2 | Approve SW-A as the swing priority | GV | Yes (choice) | DC | — |
| P0 | S2 | Drift window ≠ traded window | RD | Yes (choice) | DC | H1 close-based (labelled); H2 on the traded window |
| P0 | S4 | H2 estimand and non-event baseline | RD | Yes (choice) | DC | SPY-relative traded return minus a non-event placebo |
| P0 | S7 | Acceptance logic: P2 interval, `δ`, momentum rule, precedence, sequencing | RD | Yes (choice) | DC | as in §4 S7 |
| P0 | X1 | Exit-order defect on the time-exit day | EX | Yes (freeze) | DC | time exit before the low check |
| P0 | X2 | Entry-session stop → same-day round trips | EX/SH | Yes (choice) + Adviser | DC | first stop check at `O(s*+2)` |
| P0 | X3 | Raw stop on a market-adjusted signal | EX | Yes (choice) | DC | report + per-position notional cap |
| P0 | T1 | Definition of `VERIFIED` | RD | Yes (choice) | DC | §2.3 + T2/T3; separate SW-A vocabulary |
| P0 | T2 | Evidence tiers and precedence | RD | Yes (choice) | DC | exhibit > IR > newswire; no `T_acc`-only baseline |
| P0 | U6 | Forward-data rule that binds SW-A | GV/RD | Yes (choice) | DA, PL | none; fail-closed to the DAY-22 rule until decided |
| P0 | GV3 | SW-A protocol home, freeze and registry | GV | Yes (choice) | DC | separate protocol + JSON twin + registry |
| P1 | T3 | Session-statement intervals; `Δ_max` | RD | Yes (choice) | DC | interval mapping; `Δ_max` PROPOSED |
| P1 | T4 | Time-zone normalization; never filing date | RD | Yes (freeze) | DC, DA | IANA ET; verify the EDGAR field |
| P1 | T5 | Missing or conflicting evidence threshold | RD | Yes (choice) | DC | counts + predeclared review threshold + sensitivity |
| P1 | T6 | Audit trail and evidence storage | RD | Yes (choice) | DC | git-ignored raw; committed manifest and log |
| P1 | C1 | Classification rule set | RD | Yes (choice) | DC | completed-period criteria; ambiguous = UNCLASSIFIABLE |
| P1 | C2 | Non-2.02 results and missing quarters | RD | Yes (choice) | DC | 2.02 only + completeness check |
| P1 | C3 | Fiscal period; PRELIM-then-RESULTS | RD | Yes (choice) | DC | include and flag + sensitivity |
| P1 | C4 | `8-K/A` information date | RD | Yes (choice) | DC | any amendment, logged + sensitivity |
| P1 | C5 | BMO/AMC boundary cases | RD | Yes (freeze) | DC | explicit text + tests |
| P1 | C6 | INTRA and collisions by `T_acc` | RD | Yes (choice) | DC | keep, with counts |
| P1 | C7 | σ-window exclusion of prior events | RD | Yes (choice) | DC | drop prior reaction sessions; count from the event table first |
| P1 | S1 | AR / σ details (ddof, missing SPY, β) | RD | Yes (freeze) | DC | ddof 1; no imputation; β = 1 baseline |
| P1 | S3 | H1 sample and specification | RD | Yes (choice) | DC | all events primary + by-sign report |
| P1 | S5 | Primary inference method | RD | Yes (choice) | DC | calendar-time HAC (H2); block bootstrap (H1) |
| P1 | S6 | MDE / `n_min` (slope, effective n, `δ` pre-data) | RD | Yes (choice) | DC | add slope MDE; owner picks a power option |
| P1 | S8 | Multiple testing at project level | RD | Yes (choice) | DC | standalone α + disclosed trial count |
| P1 | S9 | Segment-boundary leakage | RD | Yes (choice) | DC | drop development events whose exit falls past the segment end |
| P1 | S10 | Early-sample feature availability | RD | Yes (freeze) | DC | mark `undefined` before about 2017-01 |
| P1 | X4 | Missing bars at exits | EX | Yes (freeze) | DC | protocol v2 §8.6 pending sell |
| P1 | X5 | Simultaneous signals and cash allocation | EX | Yes (choice) | DC | pro-rata or ticker order |
| P1 | X6 | Collision scope disclosure | EX | Yes (freeze) | DC | disclose; count by class |
| P1 | X7 | Costs; slippage on gap and collision exits | EX | Yes (choice) | DC | 5 bps primary; slippage grid on all gap exits (report) |
| P1 | X9 | Accounting conventions | EX | Yes (choice) | DC | `E_0` 100k; integer shares; cash 0%; flat segments |
| P1 | R3 | Per-position notional cap | RK | Yes (choice) | DC | cap; owner sets the value |
| P1 | R5 | Gap-risk reporting | RK | Yes (freeze) | DC | report-only stress metrics |
| P1 | U1 | Universe | RD | Yes (choice) | DC | 25 frozen, disclosed |
| P1 | U2 | Survivorship control | RD | via S4 | DC | non-event baseline |
| P1 | U3 | Screened-subset reporting | RD | Yes (choice) | DC | unscreened only |
| P1 | GV4 | Do not redefine the 2026 calendar | GV | Yes (choice) | DC | separate vocabulary |
| P1 | SH2-L | Ledger fields for D10 | SH | Yes (freeze) | DC | record dividends and period-end holdings |
| P2 | T7 | EDGAR access, pagination, contact identity | RD | Yes (choice) | DA | verify terms first |
| P2 | U4 | Point-in-time symbol → CIK/CUSIP map | RD | Yes (freeze) | DA | committed map with sources |
| P2 | U5 | Fresh data over Stage R/H dates; separate tree | RD | Yes (choice) | DA | owner choice; separate write-once tree |
| P2 | X8 | Corporate-action decisions for the SW-A snapshot | EX | Yes (choice) | DA | explicit decisions as in day17 C1–C4; acquirer records as non-events |
| P2 | GV1 | Research hold; authorization | GV | Yes (choice) | DA | — |
| P3 | R1 | Capital basis | RK | Yes (choice) | BT | fixed initial |
| P3 | R2 | Open-risk cap definition and value | RK | Yes (choice) | BT/PL | planned-risk cap for admission |
| P3 | R4 | Sector concentration | RK | Yes (choice) | BT/PL | static map for reporting |
| P4 | R6 | Settlement rule | RK | Yes (choice) + broker | PL | disclose, or a settled-cash rule |
| P4 | SH1 | D2 exit logic; refresh cadence | SH | Owner + Adviser | PL | — |
| P4 | SH2 | D10 purification ruling | SH | Adviser | PL | — |
| P4 | SH3 | D15 broker checklist; cash interest | SH | Owner + Adviser + broker | PL | — |
| P4 | SH4 | D12 for any same-day exits | SH | Adviser | PL | — |
| P4 | SH5 | Akinda licence and registry rows | SH | Owner | PL | — |
| P4 | SH6 | Event-driven holding confirmation | SH | Adviser | PL | — |
| — | GV5 | Stale OPS-1 text in the draft | GV | no | — | fix in the next revision |

**Count:** 57 rows: RD 29, EX 8, EX/SH 1, RK 6, SH 7, GV 5, GV/RD 1. SH2 appears twice: SH2-L for the ledger
design and SH2 for the ruling. RD includes U2, which has no separate approval.

---

## 11. Acceptance criteria for this audit

| # | Criterion | Status |
|---|---|---|
| 1 | Every unresolved SW-A decision is listed | PASS: §2–§9 and the §10 table cover every OPEN, PROPOSED and UNRESOLVED item in the draft (SW-0, SW-T, SW-C, SW-D, SW1–SW4, R1/R2, SH; U1–U5), plus the gaps and defects found here |
| 2 | No unsupported assumption presented as fact | PASS: repository statements are cited as FACT. Regulatory and literature points are LIT [UNVERIFIED]. The MDE table is labelled ASSUMPTION ONLY |
| 3 | Research design separated from execution and Sharia | PASS: tracks RD / EX / RK / SH / GV, and §8 contains only Sharia items |
| 4 | No profitability claim | PASS |
| 5 | Existing files and the forward-test protocol unchanged | PASS: only this file was created |

## 12. Safety confirmation

- Only this file was written. No existing document, config or code was modified. Nothing was staged, committed
  or pushed.
- No API call, network access, data acquisition, backtest, optimization or preflight was run.
- Stage R and Stage H data, `paper_state/`, sealed P001 and `fwd-gate2` results were not opened.
  `acquisition/v2/contract.py` and `stage_f.py` were not read; they are cited only as quoted in other documents.
- **Operational note:** this file is **untracked** when created. Per D1/S1 §0.5, `stage_f.py:322-323` refuses
  `fwd-gate2` capture with any untracked file. The owner must commit or remove it before 2026-12-09 16:15 ET.
