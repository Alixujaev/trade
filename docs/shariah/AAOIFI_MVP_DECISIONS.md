# AAOIFI SS 21: MVP decision register

| Field | Value |
|---|---|
| Date | 2026-10-15 |
| Scope | Decisions D1–D18 from `AAOIFI_SS21_METHODOLOGY_V1_DRAFT.md` §3 (rev 3), plus one supplementary row (S1) |
| Inputs read | `docs/shariah/AAOIFI_RESEARCH_NOTES.md` ("Notes"); `docs/shariah/AAOIFI_SS21_METHODOLOGY_V1_DRAFT.md` ("Draft"); `config/sharia_eligibility.csv` (header-only); `screening/eligibility.py`; `tests/test_sharia_eligibility.py` |
| External research | None. Every decision could be framed from the existing notes. Where the notes do not settle a question, the exact question is recorded instead. |
| Effect on code | None in this phase. `ACCEPTED_METHODOLOGIES` stays `frozenset()`, the registry CSV stays header-only, and no ticker is tradable. **Amended 2026-10-17 by owner decision D13-A** (`AKINDA_PROVIDER_DECISION.md`): `ACCEPTED_METHODOLOGIES = {AKINDA_COMPLIANCE_API_V1}`. The registry CSV is still header-only until validated Akinda rows are added. |

The registry file is `config/sharia_eligibility.csv`, spelled "sharia". The request named `config/shariah_eligibility.csv`, which does not exist.

## Status definitions

| Status | Meaning |
|---|---|
| `DECIDED` | An engineering or data-policy rule the project owns. It is already enforced, or is final for the MVP. It does not depend on a Shari'ah interpretation. |
| `PROVISIONAL` | A reversible engineering default chosen for the MVP. **It is not an AAOIFI requirement, not a fatwa, and not a verified reading of SS 21.** Where it touches interpretation, it takes the stricter option. Before go-live, the adviser must confirm it or replace it. |
| `ADVISER_REQUIRED` | A substantive Shari'ah question that the notes do not settle. No code may produce a COMPLIANT result that depends on it until a qualified adviser rules in writing. |

**Global rule:** no PROVISIONAL decision can make any ticker tradable. A COMPLIANT record loads only when its methodology is in `ACCEPTED_METHODOLOGIES` (`screening/eligibility.py`). That set stays empty until every `ADVISER_REQUIRED` row is closed (see the go/no-go checklist). **Exception, 2026-10-17 (D13-A):** the owner adopted Akinda's `/compliance` verdict (`AKINDA_COMPLIANCE_API_V1`) as the authoritative stock-level screen. Only that vendor methodology is in the set. The in-house `AAOIFI_SS21_V1` methodology is still not adopted.

**Terms used below:**
- **"Calculator"** means a future ratio-screening module that does not exist yet. It would compute T1–T3 and write registry rows.
- **"Registry"** means the existing loader in `screening/eligibility.py`.

## Decision register

| ID | Question | Proposed MVP decision | Status | Rationale and source | Confidence | Exact implementation consequence | What would change it |
|---|---|---|---|---|---|---|---|
| D1 | Market-cap valuation date for T1 and T2 | Market cap = listed shares outstanding (D6) × official closing price on the **last regular session on or before the filing's public-availability date** (`source_date`). No averaging. | PROVISIONAL | Notes 1.3 (3/4/2, 3/4/3) say the denominator is market capitalization of the company's shares, but give no date. Tying the price to `source_date` is point-in-time (no look-ahead, matching the registry rule `source_date <= valid_from`), reproducible, and uses one price per record. A trailing average would reduce flip-flopping but needs more price history and licensing. | MEDIUM | The calculator stores `mcap_price_date = last session ≤ source_date`, `mcap_price` and the price source in each record's `note`/audit output. **Blocked on data:** a licensed historical price source is still open (the Alpaca permission question is unresolved). Without one, the result is UNVERIFIED. | An adviser specifying a date or averaging window, or the official text of 3/4/2–3/4/3 doing so. |
| D2 | Grace period after a ratio breach | **No grace period.** From the first session a symbol is not COMPLIANT: no new entries. An open position is closed at the next regular session. | PROVISIONAL | Notes 1.3 (3/4/8): the conditions must hold throughout the holding period, a breach requires exit, and no grace period was identified. "Exit at next session" is the strictest workable reading. It is not a confirmed AAOIFI timeline. | MEDIUM | New entries are already blocked: `decide()` returns non-tradable for NON_COMPLIANT, UNVERIFIED and UNKNOWN. ORB positions are flat at every session close, so for ORB "next session" means a breach takes effect from the next day's decision. Exit logic for multi-day positions does not exist; any future swing runner must add it before using the registry. | An adviser allowing a defined exit window, for example N days to avoid a forced loss. |
| D3 | Does a ratio exactly at the threshold pass? | **Passes if ratio ≤ threshold** (30% / 30% / 5%), computed in exact decimal arithmetic from reported figures, with **no rounding** at any step. 30.0000…% passes; 30.0001% fails. | PROVISIONAL | Notes 1.3 report "must not exceed" for 3/4/2–3/4/4, which reads as ≤. Exact arithmetic avoids a rounding rule nobody has specified. | MEDIUM | The calculator uses `decimal.Decimal` and compares `numerator * 100 <= threshold * denominator`, with no float division. The tests need fixtures exactly at, just above and just below each threshold. | Verified Arabic wording showing a strict "<", or a prescribed rounding rule. |
| D4 | Is a 92-day validity window acceptable? | **Keep 92 days** for both `MAX_VALIDITY_DAYS` and `MAX_SOURCE_AGE_DAYS`. | PROVISIONAL | Already enforced in `screening/eligibility.py` and tested. It matches the US quarterly reporting cycle and 3/4/5's "latest statements" (Notes 1.3). It is a product default, not an AAOIFI period. | HIGH (as an engineering default) | No code change. With D18, a record never outlives the next filing. Worst case, data can be about 3 quarters old when a filing is late; the late-filer rule in D18 covers this. | An adviser setting a maximum data age, or evidence that 92 days lets stale data through in practice. |
| D5 | Annual or quarterly statements? Restatements? | **Balance-sheet items (T1, T2):** from the latest periodic report filed by `source_date` (10-Q or 10-K). **Income items (T3):** from the latest **10-K** fiscal year (audited). **Restatements:** use figures *as originally filed*; a restatement applies only from its own filing date, never backfilled. | PROVISIONAL | Notes 1.3 (3/4/5): ratios use the latest budget or **approved** financial statements. The audited 10-K is unambiguously "approved"; whether unaudited 10-Qs count is unclear. The latest balance sheet is the most current view of debt and deposits. Not backfilling restatements prevents look-ahead. | MEDIUM | The calculator records the form type, period end and accession for each input. T3 uses fiscal-year 10-K facts only. Restated values create a new record from the restatement's `source_date`. | An adviser ruling on whether unaudited quarterly statements are "approved", or preferring trailing-twelve-month income. |
| D6 | Share count and multiple share classes | **Basic** shares outstanding as reported on the filing cover page, per class. Market cap = Σ(listed class shares × that class's close). **Unlisted classes are excluded.** That gives a smaller denominator, which is stricter for T1 and T2. | PROVISIONAL | No guidance in the notes. Basic count is what is actually issued. Excluding unlisted classes is the conservative choice. | MEDIUM | The calculator needs per-class share counts and per-class prices. If a company's class structure can't be mapped, the result is UNVERIFIED. **Purification "total shares" is not decided here** (see D10). | An adviser or the official text specifying diluted or all-class capitalization. |
| D7 | Definition of interest-bearing debt (T1) and deposits (T2) | **T1 numerator:** short-term borrowings + commercial paper + current and non-current long-term debt + finance-lease liabilities + convertible notes. Operating-lease liabilities are **excluded**. Any debt line that can't be classified is **included**. **T2 numerator:** cash equivalents + short- and long-term interest-bearing investments (marketable debt securities, time deposits). Cash that can't be classified is **included**. | PROVISIONAL | Notes 1.3: 3/4/2 covers short- and long-term interest-bearing debt; 3/4/3 covers deposits across short, medium and long terms. "Include what can't be classified" is the conservative default from Draft 4.2. Leaving out operating leases is a judgement call (no explicit lending), so it is listed for the adviser. | MEDIUM (LOW for leases) | The calculator keeps an explicit mapping from accounting tags to T1/T2 buckets, with the mapping version recorded in each output. Unmapped material lines are counted as interest-bearing and noted. Tests cover each bucket. | An adviser ruling on operating leases, non-interest cash, or convertibles. |
| D8 | Denominator for T3 (5%) | **Total revenues as reported (top line).** Prohibited income (interest income plus identified prohibited-segment revenue) is the numerator even when it is reported outside revenue. It is **not** added to the denominator. | PROVISIONAL | Notes 1.3 (3/4/4): total revenue, reported Arabic term `إجمالي إيرادات الشركة` (gross revenue, not net profit). Leaving non-operating income out of the denominator makes the ratio higher, which is stricter. 3/4/4 also asks for further effort when a source of income isn't disclosed; the calculator cannot do that, so undisclosed sources mean UNVERIFIED. | MEDIUM | The calculator uses the fiscal-year total-revenue fact (D5). Numerator: interest and investment income plus any revenue in a segment on the prohibited list (D9). If the segment split isn't disclosed and the business mix suggests exposure, the result is UNVERIFIED and goes to a human reviewer. | Verified wording of 3/4/4 defining "total revenue" to include non-operating income. |
| D9 | Prohibited-activity list and "principal activity" | **Interim exclusion list (product-risk default, not an AAOIFI list):** conventional banking, lending, insurance and other interest-based finance; alcohol; pork; gambling; adult entertainment; tobacco. **Principal activity** = the segment with the largest share of revenue in the latest 10-K. If the principal activity is on the list, the result is NON_COMPLIANT. Smaller listed-category revenue counts toward T3. **3/4/1** (constitutional objectives) is checked by a human reviewer; if not checked, the result is UNVERIFIED. | PROVISIONAL | The notes give no list; 3/4/1 refers only to "interest or prohibited goods or services". The list above is a conservative product default. It errs toward exclusion and does not claim to be the AAOIFI definition. Defining principal activity by revenue is a common, auditable choice. | LOW (list content); MEDIUM (mechanism) | The calculator holds a versioned list and a mapping to industry codes, with the list version stored in each output. Segment data is required, and its absence means UNVERIFIED. The final list needs adviser confirmation before go-live. | An adviser's list, or an AAOIFI source that defines prohibited activities. |
| D10 | Purification: data sources, period, definitions | **No purification is implemented.** The reported formula is recorded verbatim, unchanged: `(total prohibited income / total shares) × shares held`. | ADVISER_REQUIRED | Notes 1.5: the obligation falls on holders at **fiscal period end**, but the notes don't define the period, the "total prohibited income" scope, or the "total shares" basis. Draft 6.2 withdrew the dividend-based formula. | — | No calculator, no reports of purification amounts, and no dividend-times-ratio substitute. Any position ledger must keep enough data (period-end holdings by symbol) to compute purification later, without computing it. | Written adviser guidance on the period, the definition of each input, and the share basis. |
| D11 | Do intraday gains create a purification obligation? | **Not decided.** As reported, 3/4/6 applies only to holders at period end, and ORB is flat at every session close. The draft does **not** infer from this that no obligation exists. | ADVISER_REQUIRED | Notes 1.5 and Draft 6.4. Applying a reported rule to intraday-only trading is a Shari'ah question, not an engineering one. | — | No code. ORB outputs carry no statement of "no purification due". | Adviser ruling. |
| D12 | Is day trading permissible given T+1 settlement and the possession and liability rules? | **Not decided.** ORB stays paper or research only; there is no live intraday trading. | ADVISER_REQUIRED | Notes 1.3 (3/7): resale is permitted once daman (liability) has passed, even before final settlement. Notes 2.2 (SS 18): constructive possession concepts, which don't explicitly cover shares. Whether US T+1 broker execution satisfies 3/7 is a Shari'ah question. | — | No order code may be added for live intraday trading. Paper simulation already places no orders, so it is not blocked. | Adviser ruling on 3/7 applied to the intended broker's settlement and custody model. |
| D13 | Third-party Shari'ah screens and indices | **Not accepted as COMPLIANT evidence.** They may be recorded only as UNVERIFIED rows with a note, or used as an internal cross-check. ETF or index membership (HLAL, SPUS) is never evidence. | DECIDED | Already the registry's design decision. A COMPLIANT row needs an allowlisted methodology, and no vendor methodology is listed. Notes 2.4 (SS 27 7): Islamic indices have their own Shari'ah boards, which shows the screens depend on each provider and are not this project's methodology. | HIGH | No change. The existing allowlist and tests enforce it. | An owner decision to adopt a named vendor methodology via `ACCEPTED_METHODOLOGIES`, with the adviser's sign-off. **AMENDED 2026-10-17 (D13-A, owner decision):** Akinda's `/compliance` verdict is adopted as the authoritative stock-level screen (`AKINDA_COMPLIANCE_API_V1`). No adviser sign-off is on file; the owner decision replaces that condition for Akinda only. Every other vendor or index screen, and any ETF membership, is still not COMPLIANT evidence. See `AKINDA_PROVIDER_DECISION.md`. |
| D14 | Missing data default | **Missing, stale, ambiguous or unmappable data → UNVERIFIED (not tradable). Never COMPLIANT.** | DECIDED | The fail-closed policy already in force (Draft 4.2; Notes §4). | HIGH | Already enforced: no record → UNKNOWN; UNVERIFIED and UNKNOWN are not tradable; unsourced decided rows fail to load. The calculator must emit UNVERIFIED, with the reason, whenever any input is missing. | None expected. |
| D15 | Licensed brokers and jurisdiction | **US SEC/FINRA-registered broker-dealer only. Cash account (no margin). Opted out of stock-lending programmes. No interest earned on idle cash** (disable or decline interest sweeps where possible). The question of interest-bearing cash deposits goes to the adviser. | PROVISIONAL | Notes 1.3 (3/5 margin, 3/8 licensed brokers, 3/9 and 3/15 no share lending); Notes 2.1 (SS 12 4/1/2/6–4/1/2/8, including the researcher's concern about interest-bearing deposits required by a broker). | MEDIUM | No live broker integration exists, and the MVP is paper only. Before any live account: a written broker checklist covering account type, lending opt-out and interest handling. Any future order path must refuse short, margin and derivative orders (Draft 7.3). | An adviser ruling on broker cash interest, or a different jurisdiction. |
| D16 | Preferred shares with dividend or liquidation priority | **Holding:** the project trades common shares only; preferred shares are never traded. **Issuer effect:** if an issuer has outstanding preferred shares with a financial preference, its result is **UNVERIFIED** pending the adviser's ruling. | ADVISER_REQUIRED | Notes 2.1 (SS 12 4/1/2/14): financial preference is prohibited and administrative preference permitted. Whether an issuer of such shares is affected is not settled by the notes (Draft 9.1). | — | The calculator checks for preferred-stock balances; if any are non-zero with a financial preference, or can't be classified, the result is UNVERIFIED. The universe stays common-stock only. | An adviser ruling on the issuer-level effect. |
| D17 | SS 21 3/19 tangible-assets threshold: 30% or one-third? | **Not decided.** The asset-composition test is **not implemented**, and no COMPLIANT result may depend on it. Interim option for the adviser to approve or reject: require ≥ one-third, which satisfies both readings, using market values where available. | ADVISER_REQUIRED | Notes 1.4: 30% in the 3/19 text versus one-third in the 3/1 explanatory note and Appendix B. There is also a data problem: 3/19 refers to **market value** of tangible assets, while filings give book values. | — | No code for 3/19. Until it is resolved, COMPLIANT is impossible for this methodology. That is already guaranteed by the empty `ACCEPTED_METHODOLOGIES`. | Adviser ruling on which threshold governs and on whether book value may stand in for market value. |
| D18 | Review frequency | **Re-screen on every new 10-Q or 10-K** (new record from its `source_date`; the previous record's `valid_until` = the day before) **and at least every 92 days** (D4). **Late filer:** if no new filing arrives within 92 days of the last `source_date`, the symbol becomes UNKNOWN (expired). | PROVISIONAL | Draft 8.1. Ties the registry to the real data cadence. Matches the registry's non-overlapping-window rule. | HIGH | The calculator generates contiguous, non-overlapping windows per symbol. The existing loader rejects overlaps and windows over 92 days. | An adviser requiring a different cadence, for example monthly price-driven re-screens because the market-cap denominator moves daily. |
| S1 | 3/19 financing-company qualification (supplementary; Draft 5.3–5.4) | **Conservative product-risk default (not a verified AAOIFI rule):** a company whose principal activity is debt or financing facilities is NON_COMPLIANT under this methodology. This overlaps with D9's finance exclusion. | ADVISER_REQUIRED | Notes 1.3 (3/19): reported gist only; the Arabic wording is not provided. The exclusion is stricter than the reported gist, which says debt-trading rules apply rather than a ban. It is chosen because a debt-trading assessment cannot be implemented. | — | Implemented through the D9 exclusion list. Labelled as a product-risk exclusion in the list's documentation. | Verified Arabic text and an adviser ruling on scope. |

## Status counts

| Status | Count | IDs |
|---|---|---|
| DECIDED | 2 | D13, D14 |
| PROVISIONAL | 11 | D1, D2, D3, D4, D5, D6, D7, D8, D9, D15, D18 |
| ADVISER_REQUIRED | 5 + S1 | D10, D11, D12, D16, D17 (+ S1) |
| Unclassified | 0 | — |

## Decisions that can go into code now

These can be built without making any ticker tradable, because the calculator's outputs are limited to `NON_COMPLIANT`, `UNVERIFIED` or UNKNOWN, and its methodology (`AAOIFI_SS21_V1_DRAFT`) is not in `ACCEPTED_METHODOLOGIES`. That set holds only `AKINDA_COMPLIANCE_API_V1` (D13-A), and the loader never accepts a `DRAFT` methodology.

1. **Already done:** D13 and D14 (registry, allowlist, fail-closed tests).
2. **A screening calculator that only writes non-COMPLIANT results** (new module; tests first):
   - D3: exact-decimal comparison;
   - D5: form and period selection, as-filed figures;
   - D6: basic per-class share count, unlisted classes excluded;
   - D7: versioned tag → T1/T2 mapping, with unclassifiable lines included;
   - D8: total revenue as the denominator;
   - D9: versioned exclusion list plus principal-activity rule, with 3/4/1 as a human-review field;
   - D18: contiguous windows.

   Its outputs may only be `NON_COMPLIANT` (with `methodology = AAOIFI_SS21_V1_DRAFT` and full provenance) or `UNVERIFIED`. It must never emit COMPLIANT.
3. **D1:** the code path only. The price input stays blocked until a licensed historical price source is confirmed, so results are UNVERIFIED until then.
4. **D2:** no-entry behaviour already exists. Exit logic is only needed if a multi-day runner is wired to the registry.
5. **D15:** a written pre-live broker checklist (documentation only); the order path refuses short, margin and derivative orders.

**Data prerequisite for item 2.** No fundamentals or SEC filing client exists in the repo. Adding one is a separate, approved data-acquisition task under the standing constraints: no data downloads without approval, and nothing new inside `data/`.

## Decisions blocked on a qualified Shari'ah adviser

D10, D11, D12, D16, D17 and S1. The adviser should also confirm or replace every PROVISIONAL row before go-live, with particular attention to the low-confidence D9 list and the D7 lease treatment.

## Minimum questions for the adviser

1. **3/19 threshold (D17):** which governs, 30% (clause text) or one-third (3/1 explanatory note, Appendix B)? May book value stand in for the "market value" of tangible assets?
2. **3/19 financing companies (S1):** what does the exact Arabic qualification say, and is excluding such companies outright acceptable?
3. **Day trading (D12):** under 3/7 (resale once daman passes), is intraday trading of compliant US shares under T+1 settlement through a US broker permissible?
4. **Purification (D10, D11):** for `(total prohibited income / total shares) × shares held`:
   - which period applies;
   - what counts as prohibited income (does it include interest income?);
   - which share count is used;
   - does a trader with no position at period end owe anything?
5. **Preferred shares (D16):** does an issuer with outstanding financial-preference preferred shares fail the screen, or only the preferred shares themselves?
6. **Confirm or replace the PROVISIONAL defaults:**
   - D1: market-cap date;
   - D2: no grace period;
   - D3: ≤ boundary;
   - D5: whether unaudited 10-Qs count as "approved";
   - D7: operating leases and non-interest cash;
   - D8: revenue denominator;
   - D9: prohibited list and principal-activity rule;
   - D15: interest on broker cash.

## MVP go/no-go checklist

**GO for building the non-COMPLIANT calculator (paper/research only):**
- [x] D13 and D14 enforced in code and tests.
- [ ] Written, approved plan for the SEC fundamentals data source (provenance, licensing, location outside `data/`).
- [ ] Calculator tests: D3 boundaries, D7 mapping, D9 list, D14 missing-data → UNVERIFIED, D18 windows. Plus a test that the calculator **cannot** emit COMPLIANT.
- [ ] Integrity check: V2-MOM config SHA unchanged; protected paths unchanged.

**Amendment 2026-10-17 (D13-A):** by owner decision, Akinda-sourced COMPLIANT records (`AKINDA_COMPLIANCE_API_V1`) are exempt from the stock-screening items below; the items below now govern only the in-house `AAOIFI_SS21_V1` methodology. The live-trading item (D12, D15, D2) still applies to everything.

**NO-GO for any COMPLIANT record, any non-empty `ACCEPTED_METHODOLOGIES`, or any live trading until all of these are done:**
- [ ] The adviser's written rulings on D10, D11, D12, D16, D17 and S1 are on file (name, credentials, date, scope).
- [ ] The adviser has confirmed or replaced every PROVISIONAL row (D1–D9, D15, D18).
- [ ] The Arabic text of 3/4/2–3/4/6, 3/4/8 and 3/19 has been verified against the official PDF, with page references.
- [ ] A licensed historical and current price source is confirmed for D1. The Alpaca permission question needs written confirmation.
- [ ] A methodology version is adopted in a separate owner decision record. Only then is `AAOIFI_SS21_V1` (not `_DRAFT`) added to `ACCEPTED_METHODOLOGIES`.
- [ ] For live trading only: the D15 broker checklist is complete; exit logic exists for any multi-day strategy (D2); D12 has been ruled permissible.
