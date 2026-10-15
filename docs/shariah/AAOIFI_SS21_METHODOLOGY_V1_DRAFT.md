# AAOIFI Shari'ah Standard No. 21: screening methodology v1 (DRAFT)

| Field | Value |
|---|---|
| Status | **DRAFT, NOT ADOPTED.** Documentation only. |
| Draft date | 2026-10-15 (revision 3) |
| Methodology id (proposed) | `AAOIFI_SS21_V1_DRAFT` (**not** added to `ACCEPTED_METHODOLOGIES`) |
| Source standard | AAOIFI Shari'ah Standard No. 21, "Financial Papers (Shares and Bonds)", official Arabic text |
| Source record for researcher findings | `docs/shariah/AAOIFI_RESEARCH_NOTES.md` (the notes file) |
| Independent verification | **None.** The author of this file did not open, read or verify the PDF. Every SS 21 rule below comes from the notes file. |

> This draft is not a fatwa and not a Shari'ah ruling. It makes no claim that any company or ticker is Shari'ah-compliant.

## Revision log

| Rev | Date | Change |
|---|---|---|
| 1 | 2026-10-15 | Initial draft: thresholds, 3/19 conflict, placeholders. |
| 2 | 2026-10-15 | Sub-clause numbers and supplied page locations. Dividend-based purification formula withdrawn. Placeholders for missing notes. |
| 3 | 2026-10-15 | Filled from the notes file: source identity (1.1); 3/4/1–3/4/8 content; 3/5–3/16; 3/17–3/20; sections 4–5 (bonds); Appendix B rationale; purification details; supporting standards SS 12, SS 18, SS 20 and SS 27; open decisions aligned with the notes file (section 3). The label `SOURCE_TEXT (per notes)` was renamed to `RESEARCHER-TRANSCRIBED`, so that it cannot be read as verified source text. |

## 0. Scope and effect

- This draft has **no effect** on the code.
  - `screening/eligibility.py` keeps `ACCEPTED_METHODOLOGIES = frozenset()`.
  - `config/sharia_eligibility.csv` stays header-only, so no ticker is tradable.
- Adopting this methodology needs three things, in this order:
  1. a qualified Shari'ah adviser's written review (section 11);
  2. resolution of every `PENDING_SHARIAH_REVIEW` and `UNRESOLVED` item below;
  3. a separate, owner-approved decision record.
- V2-MOM is unaffected. Any future use there is report-only unless a new protocol version is adopted.

## 1. Labels used in this document

| Label | Meaning |
|---|---|
| `RESEARCHER-TRANSCRIBED` | Short form of `RESEARCHER-TRANSCRIBED — NOT INDEPENDENTLY VERIFIED`: content taken from the notes file, which reports or paraphrases the researcher's reading of the Arabic PDF. It is **not** a verified quotation. |
| `IMPLEMENTATION_DECISION (proposed)` | How the project proposes to turn a rule into code or data. It is not part of SS 21 and needs owner approval. |
| `UNRESOLVED` | A methodology decision that is still open. Do not implement until it is decided. |
| `PENDING_SHARIAH_REVIEW` | A question that only a qualified Shari'ah adviser can resolve. |
| `VERIFY_EXACT_TEXT` | Must be checked word-for-word against the official Arabic text before use. |
| `NOT_PROVIDED` | Not present in the notes file, such as a page number or Arabic wording. Must not be guessed. |
| `ARABIC TEXT NOT PROVIDED — DO NOT QUOTE` | The Arabic wording was not supplied. Do not reconstruct or quote it. |

The draft contains **no verified quotations**.

## 2. Source identity and locations (`RESEARCHER-TRANSCRIBED`)

### 2.1 Source identity (reported; notes file 1.1)

- Official Arabic SS 21 PDF: https://aaoifi.com/wp-content/uploads/2020/08/21.pdf (URL as reported by the researcher).
- The researcher reports that the PDF is 28 pages, dated 10 August 2020, and that its text matches the 2004 standard.
- Not independently verified. Hijri edition date and file hash: `NOT_PROVIDED`.

### 2.2 Page locations (notes file 1.2)

- These are exactly the locations supplied. Nothing else is inferred, even where a PDF-to-printed offset looks consistent.

| Rule / clause | Topic | PDF page | Printed page |
|---|---|---|---|
| 3/1, explanatory note | Tangible-assets proportion: one-third (see 5.2) | 7 | 567 |
| 3/4/2 | Interest-bearing debt / market capitalization | 8 | `NOT_PROVIDED` (reported as "not identified") |
| 3/4/3, 3/4/4 | Deposits ratio; prohibited income ratio | 9 | 569 |
| 3/19 | Mixed assets; tangible-assets threshold; financing-company qualification | 13 | 573 |
| Appendix B | Rationale for 3/4; one-third threshold | 24 | 584 |
| All other clauses (3/1 body, 3/2, 3/3, 3/4/1, 3/4/5–3/4/8, 3/5–3/18, 3/20, sections 4–5) | — | `NOT_PROVIDED` | `NOT_PROVIDED` |

## 3. Open methodology decisions (`UNRESOLVED`; do not decide silently)

D1–D17 follow the numbering in section 3 of the notes file. D18 is specific to this draft.

| # | Decision | Where it bites |
|---|---|---|
| D1 | Market-cap valuation date: balance-sheet date, filing date, screening date or a trailing average | T1, T2 (4.1) |
| D2 | Grace period after a ratio breach. None was identified in the notes on 3/4/8 | 8.2 |
| D3 | Whether a value exactly at a threshold (30% or 5%) passes, and at what rounding precision | 4.1 |
| D4 | Whether the 92-day screening validity window is acceptable | 8.1 |
| D5 | Annual versus quarterly statements, and how restatements are treated (3/4/5) | 4.1 |
| D6 | Basic or diluted share count; multiple share classes | T1, T2, purification |
| D7 | Definition and classification of interest-bearing debt | T1 |
| D8 | Confirming from authoritative wording that total (gross) revenue is the 5% denominator | T3 |
| D9 | The list of prohibited activities, and the definition of "principal activity" | 4.1 |
| D10 | Data sources and reliability for purification; the exact purification period | 6 |
| D11 | Whether intraday capital gains create a purification obligation under the chosen interpretation | 6 |
| D12 | Whether day trading is permissible under SS 21, given T+1 settlement and the possession and liability rules (3/7; SS 18) | 7, 9.2 |
| D13 | How third-party Shari'ah screens are treated | 9.4, 11 |
| D14 | Missing data must default to `UNVERIFIED`, never `COMPLIANT` (proposed; already the registry's behaviour) | 4.2 |
| D15 | Conditions on licensed brokers (3/8; SS 12 4/1/2/8), and the relevant jurisdiction | 7 |
| D16 | Whether preferred shares with dividend priority need a hard exclusion or adviser review (SS 12 4/1/2/14) | 9.1 |
| D17 | Whether the 30% versus one-third conflict (5.2) can be settled from an authoritative AAOIFI source or needs a Shari'ah adviser | 5.2 |
| D18 | Review frequency beyond the 92-day maximum, for example re-screening on each new 10-Q or 10-K (draft-specific) | 8.1 |

## 4. Company activity and financial screening (clause 3/4)

### 4.1 `RESEARCHER-TRANSCRIBED` (notes file 1.3, 3/4)

- The principal activity must be permissible.
- The researcher reports exceptions and criteria for companies whose activity is permissible but that hold interest-bearing deposits or loans:

| Sub-clause | Content as reported |
|---|---|
| 3/4/1 | The company's constitutional documents must not list interest or prohibited goods or services as objectives. |
| 3/4/2 (T1) | Total interest-bearing debt, short- and long-term, **≤ 30% of market capitalization**. The standard reportedly still describes interest-bearing debt as prohibited in principle. |
| 3/4/3 (T2) | Interest-bearing deposits, across short, medium and long terms, **≤ 30%**. The Arabic reportedly refers to the market capitalization of the company's shares. The English phrase "market capitalization of total equity" may be ambiguous (`VERIFY_EXACT_TEXT`). |
| 3/4/4 (T3) | Income from prohibited sources **≤ 5% of the company's total revenue**. The Arabic term is reported as `إجمالي إيرادات الشركة`, meaning total or gross revenue, not net profit. This is the researcher's report, not a verified quotation (D8). The scope covers prohibited activities, ownership of prohibited assets, and other routes. If a source of income is not disclosed, further effort should be made to identify it. |
| 3/4/5 | Ratios are calculated from the latest budget or approved financial statements. |
| 3/4/6 | Purification. See section 6. |
| 3/4/7 | The conditions apply whether the institution trades for itself or for others, through a fund, as an agent, and so on. |
| 3/4/8 | The conditions must hold throughout the holding period. If they are violated, the investor must exit. **No grace period was identified in the notes** (D2). |

- **Boundary:** the notes give "must not exceed", which reads as ≤. Treatment of a value exactly at the threshold, and rounding, is D3.

### 4.2 `IMPLEMENTATION_DECISION (proposed)`

- **Constitutional-documents check (3/4/1) and principal-activity gate first.** A failure on either means NON_COMPLIANT, and no ratio is computed. Defining principal activity: D9.
- **All three ratios must pass.** A failure on any of T1, T2 or T3 means NON_COMPLIANT.
- **Missing inputs fail closed.** If any input is missing, stale or ambiguous, the result is UNVERIFIED, never COMPLIANT (D14).
  - That includes an undisclosed source of income where 3/4/4's "further effort" did not identify it.
- **Debt classification (D7).** Leases, convertible notes and similar items: `PENDING_SHARIAH_REVIEW`. If an item cannot be classified, the conservative default is to count it as interest-bearing.
- **Statement basis (3/4/5; D5).** Use the latest approved statements available at `valid_from`, never later ones. This is already enforced by `source_date <= valid_from`.
- **Precision.** No intermediate rounding. Record the inputs, the filing and its public-availability date in `source`, `source_ref` and `source_date`.
- **Scope (3/4/7).** The same conditions apply to every account the project might trade, including any future managed or agency account.

## 5. Asset composition and share trading (clauses 3/1, 3/17 – 3/20)

### 5.1 `RESEARCHER-TRANSCRIBED` (notes file 1.3)

| Clause | Content as reported |
|---|---|
| 3/1 | A share represents undivided ownership in the company's capital or assets, which may include tangible assets, usufructs and debts. An explanatory note says that where tangible assets exist alongside cash or debts, tangible assets must be at least **one-third**. The note reportedly says it was added in preparation for a later edition. |
| 3/17 | If a company's assets are only cash (for example during subscription, before operations or in liquidation), its shares are sold only at nominal value and subject to the handover condition. |
| 3/18 | If the assets are entirely debts, the rules on trading debts apply. |
| 3/19 | For mixed assets, the rule depends on the principal activity. If the company trades in goods, usufructs or rights, its shares may be sold without applying the sarf or debt rules, provided the market value of its tangible assets, usufructs and rights is at least **30% of total assets**. If its activity is gold, silver or currency, the sarf rules apply. |
| 3/20 | A company must not add a small amount of tangible assets merely to disguise a transaction that is in substance debt trading. |

### 5.2 Clause 3/19 threshold conflict (`UNRESOLVED`, `PENDING_SHARIAH_REVIEW`; D17)

| Location | Reported threshold | PDF / printed page |
|---|---|---|
| 3/19, clause text | 30% (of total assets) | 13 / 573 |
| 3/1, explanatory note | one-third | 7 / 567 |
| Appendix B | one-third | 24 / 584 |

- **Not resolved.** No value is chosen, and nothing may be implemented that depends on it.

### 5.3 Clause 3/19: financing-company qualification

- **Reported gist only:** where a company's principal activity is debt or financing facilities, trading its shares must follow the debt-trading rules.
- `ARABIC TEXT NOT PROVIDED — DO NOT QUOTE`. Before any use, the wording must be transcribed verbatim from PDF page 13 / printed page 573 (`VERIFY_EXACT_TEXT`). The adviser must confirm its scope.

### 5.4 `IMPLEMENTATION_DECISION (proposed)`

- The asset-composition test (3/17–3/20) is **not implemented** until 5.2 and 5.3 are resolved. No COMPLIANT record may rely on it.
- The proposed default is to treat companies whose principal activity is debt or financing as not eligible under this methodology until the adviser rules otherwise. This is also consistent with the 3/4 principal-activity gate.
- The 3/19 market value of tangible assets needs data the project does not have: market values, not book values, of tangible assets, usufructs and rights. Until that data is sourced, the result is UNVERIFIED.

## 6. Purification (clause 3/4/6)

### 6.1 `RESEARCHER-TRANSCRIBED` (notes file 1.5)

- **Who:** an investor or trader holding shares at the **end of the fiscal period**.
- **Not required** if the shares are sold before period end, whether the investment made a profit or a loss and whether or not dividends were paid.
- An intermediary, agent or manager does not purify its own commission.
- **Formula, exactly as reported:**

  ```
  (total prohibited income / total shares) × shares held
  ```

- The amount must not be used for any purpose, including paying taxes.
- Institutions reportedly purify their own and managed holdings. Intermediaries must explain the mechanism to clients and may offer it as a paid or free service.

### 6.2 Correction carried forward

- Revision 1 of this draft gave a dividend-based formula (dividend per share × prohibited income ÷ total revenue). The notes do not support it.
- It is **withdrawn** and must not be used as the SS 21 formula unless that interpretation is explicitly approved.

### 6.3 Implementation: BLOCKED

- No purification calculator is to be built. Implementation stays blocked until all of these are confirmed:
  1. the exact wording of 3/4/6 (`VERIFY_EXACT_TEXT`);
  2. the period (D10);
  3. the data definitions in 6.4;
  4. the share count (D6);
  5. the adviser's guidance.

### 6.4 Data definitions still open

| Input | Open definition or missing data |
|---|---|
| Total prohibited income | Scope, gross or net, and which fiscal period. No fundamentals or SEC filing client exists in the repo. Filings rarely itemise all prohibited income. |
| Total shares | Outstanding or weighted-average shares, share classes, and the as-of date (D6). |
| Shares held | Shares held at fiscal period end, per the reported rule. No position ledger is connected to this module. |
| Intraday positions | The project's ORB positions are flat at every session close, so under the reported "held at period end" rule they would typically hold nothing at period end. Whether that ends the obligation for intraday gains is D11, `PENDING_SHARIAH_REVIEW`. This draft does not decide it. |
| Unreported prohibited income | Treatment when it can only be estimated: `PENDING_SHARIAH_REVIEW`. |

## 7. Trading restrictions (clauses 3/2, 3/3, 3/5 – 3/16)

### 7.1 `RESEARCHER-TRANSCRIBED` (notes file 1.3)

| Clause | Content as reported |
|---|---|
| 3/2 | Shares in companies with permissible activities may be bought and sold for cash or for permissible deferred payment. Investment, and trading to benefit from price changes, are permitted under the stated conditions. |
| 3/3 | Participation intended to change a company's activity to Shari'ah-compliant applies to someone capable of making that change, such as a shareholder able to influence the first general meeting. |
| 3/5 | Margin trading funded by an interest-bearing loan is prohibited, and so is pledging shares for such a loan. |
| 3/6 | Short selling is prohibited. A broker's promise to lend shares for delivery does not change the ruling. |
| 3/7 | After a sale is concluded and liability (daman) has passed to the buyer, resale is permissible even if final settlement has not completed. |
| 3/8 | State regulators may organize share trading through licensed brokers. |
| 3/9 | Shares may not be lent as a qard. |
| 3/10 | Permissible shares may be pledged as collateral. |
| 3/11 – 3/14 | Salam, futures, options and swaps in shares are prohibited. The notes do not assign each contract type to a specific clause. 3/12–3/13 reportedly refer to SS 20 (see 9.3). |
| 3/15 | Leasing shares is prohibited, including arrangements like securities lending in which shares are sold and equivalent shares are returned later. |
| 3/16 | I'arah (a loan for use without compensation) is permitted for collateral or dividends. The recipient may sell only to enforce the collateral. |

### 7.2 `RESEARCHER-TRANSCRIBED`: bonds (SS 21 sections 4–5)

- Interest-bearing bonds, including zero-coupon and prize bonds, are reported as prohibited to issue, trade, pledge or endorse.
- The reported alternative is investment sukuk under SS 17. SS 17 is not covered by the notes.

### 7.3 `IMPLEMENTATION_DECISION (proposed)`

- The project has no order code. Any future order path:
  - must not use short selling (3/6), interest-funded margin (3/5), share lending or leasing (3/9, 3/15), or salam, futures, options or swaps (3/11–3/14);
  - must not trade interest-bearing bonds (sections 4–5);
  - must use a licensed broker (3/8; D15).
- **Intraday resale (3/7).** As reported, 3/7 permits resale once daman has passed, before final settlement. Whether T+1 equity trades through the project's broker satisfy that condition is D12, `PENDING_SHARIAH_REVIEW`. This draft does not conclude that day trading is permitted.

## 8. Review cadence and breaches

### 8.1 `IMPLEMENTATION_DECISION (proposed)`

- Each record covers at most 92 days (`MAX_VALIDITY_DAYS`). Its source must be no more than 92 days older than `valid_from` (`MAX_SOURCE_AGE_DAYS`). Both are already enforced in `screening/eligibility.py`.
- Acceptability under SS 21: D4. Re-screening frequency: D18.

### 8.2 Breach and exit (3/4/8; D2)

- As reported, the conditions must hold throughout the holding period, and a violation requires exit. **No grace period was identified in the notes.**
- The length of any exit period is `UNRESOLVED`. Candidates, listed but not chosen: exit at the next session; exit within N days; a hysteresis buffer.
- Until decided, the registry's fail-closed behaviour blocks new entries. Exit logic for open positions does not exist and is not specified here.

## 9. Supporting standards (context only; not SS 21 clauses)

- **Nothing in this section adds a clause or screening criterion to SS 21.**
- All entries are `RESEARCHER-TRANSCRIBED` (notes file, section 2).
- Sources, editions and page locations for these standards: `NOT_PROVIDED`.

### 9.1 SS 12: Sharikah (Musharakah) and Modern Corporations

| Clause | Content as reported |
|---|---|
| 4/1/2/6 | No purchase with an interest-bearing loan from a broker or anyone else, and no pledging of shares for such a loan (margin). |
| 4/1/2/7 | No selling shares one does not own. A broker's promise to lend is not ownership or possession. *Researcher's added concern:* an arrangement where the broker requires an interest-bearing cash deposit. |
| 4/1/2/8 | Trading through licensed brokers. |
| 4/1/2/11 | Pledging shares is permitted, subject to the company's rules. |
| 4/1/2/14 | Preferred shares with a **financial** preference, in liquidation or in profit distribution, are prohibited. An **administrative** preference, such as voting rights, is permitted. |
| 4/1/2/15 | Tamattu' shares are prohibited. |

- **Flag (`PENDING_SHARIAH_REVIEW`; D16):** preferred shares with dividend priority need separate review by a Shari'ah adviser. Whether a company that has issued such shares is affected is also open. Do not classify these without a documented interpretation.
- **Flag for the broker:** the researcher's concern under 4/1/2/7 about interest-bearing cash deposits required by a broker is relevant to choosing a broker (D15).

### 9.2 SS 18: Possession (Qabd)

| Clause | Content as reported |
|---|---|
| 3/1 | Possession is determined by custom. |
| 3/3 | Constructive possession applies when an item is identified and the holder can dispose of it without restriction. |
| 3/4 | Legal registration may replace physical possession. |
| 3/5 | Documents such as bills of lading or warehouse receipts may establish constructive possession when they identify the item and allow it to be disposed of. |

- **Scope:** these notes do not address shares explicitly. For shares, the contextual references are SS 21 3/7 and Appendix B. This draft does **not** state a direct SS 18 ruling on shares.
- **Reported discrepancies** (unverified; `VERIFY_EXACT_TEXT`):
  1. The acceptance date reads 1424 AH; the researcher reports it should be 1425 AH.
  2. Clause 5/1 reportedly cites SS 12 for Commercial Papers; the researcher believes the intended reference is SS 16.

### 9.3 SS 20: Sale of Commodities in Organized Markets

- **Scope:** reportedly does not cover financial papers or currencies.
- **Cross-reference discrepancy (`UNRESOLVED`, `VERIFY_EXACT_TEXT`):** SS 21 3/12–3/13 reportedly refer to SS 20 on futures and options, even though SS 20's stated scope excludes financial papers.

| Clause | Content as reported |
|---|---|
| 5/1 | Futures on commodities and on financial instruments are prohibited. |
| 5/2 | Options on shares, indices and similar are prohibited. |
| 5/2/3 | Reported alternatives: 'arbun with a right that cannot be traded; a contract with a right to cancel; a binding one-sided promise, also not tradable. |
| 5/3 | Swaps traded on an exchange are prohibited. |

### 9.4 SS 27: Indices

| Clause | Content as reported |
|---|---|
| 5/1 – 5/2 | Using an index to measure markets, assess risk, forecast or set a benchmark is permitted. |
| 5/6 | An agent or mudarib may tie transactions to an index value, for example an order triggered by an index level. |
| 6/1 | Paying or receiving money based only on an index level, without acquiring a real asset, is prohibited, even for hedging. |
| 6/2 – 6/3 | Index options and index-multiplier contracts are prohibited. |
| 6/4 | A sale contract may not be tied to an index. |
| 7 | An Islamic index must follow Shari'ah requirements and be supervised periodically by its own Shari'ah board. |

- **Context only:** SS 27 7 bears on D13, how third-party Shari'ah screens and indices are treated. It does not make any index's membership evidence for a single stock. The registry rule stays: ETF or index membership is not COMPLIANT evidence.

## 10. Appendix B rationale (`RESEARCHER-TRANSCRIBED`; context)

- The reported grounds for the 3/4 exception are:
  - removal of hardship (`raf' al-haraj`);
  - widespread prevalence (`umum al-balwa`);
  - the majority-part rule;
  - permissibility of dealing with something whose majority is lawful;
  - some jurists' `tafriq al-safqa`.
- Some rulings were reportedly adopted by majority, not unanimously.
- Appendix B also reportedly states the one-third threshold (5.2).

## 11. Checklist for a qualified Shari'ah adviser

- [ ] **Source identity.** Confirm that the reported PDF (28 pages, dated 10 August 2020, text matching the 2004 standard; compiled pagination 567–584) is the official, current SS 21.
- [ ] **3/19 conflict (D17).** Which threshold governs: 30% of total assets in 3/19, or one-third in the 3/1 explanatory note and Appendix B? Give the basis.
- [ ] **3/19 financing-company qualification.** Confirm the exact Arabic wording and its scope.
- [ ] **T1–T3.** Confirm 30% / 30% / 5%, the boundary (D3), the denominators (market capitalization of shares; total/gross revenue, D8) and the numerators (D7).
- [ ] **3/4/5 (D5).** Annual or quarterly statements, restatements, maximum data age (D4).
- [ ] **Market-cap date (D1) and share count (D6).**
- [ ] **Prohibited activities and principal activity (D9).**
- [ ] **3/4/8 exit (D2).** Is there any exit period after a breach, and does it differ for intraday versus multi-day positions?
- [ ] **Purification (3/4/6).** Confirm the formula `(total prohibited income / total shares) × shares held`, the period (D10), the input definitions, and whether intraday trading creates any obligation (D11).
- [ ] **Day trading (D12).** Does 3/7 (resale after daman passes) cover T+1 US equity trades through the intended broker? How do SS 18 possession concepts apply?
- [ ] **Brokers (D15).** Licensing and jurisdiction; the SS 12 4/1/2/7 concern about interest-bearing cash deposits.
- [ ] **Preferred shares (D16).** Dividend-priority preferred shares: hard exclusion or case-by-case?
- [ ] **Cross-reference and date discrepancies.** SS 21 3/12–3/13 → SS 20 scope; SS 18 acceptance date 1424 vs 1425 AH; SS 18 5/1 citing SS 12 vs SS 16.
- [ ] **Third-party screens (D13).** May a vendor or index screen that claims to follow AAOIFI be relied on, or must the project compute ratios from filings?
- [ ] **Missing data (D14).** Is "missing data → UNVERIFIED (not tradable)" acceptable?
- [ ] **Written approval.** The adviser's name, credentials, date and signed scope, to be recorded in the future adoption decision.
