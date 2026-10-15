# AAOIFI screening: financial-data provider assessment (Phase 2A)

| Field | Value |
|---|---|
| Date | 2026-10-15 |
| Status | **ASSESSMENT ONLY. No provider is approved.** |
| Method | Repository inspection plus prior knowledge. **No network access, no downloads, no API calls (SEC or Alpaca), no caches.** |
| Verification | Every external fact (endpoints, terms, rate limits, dataset contents) is from prior knowledge, marked **[UNVERIFIED]**, and must be checked against the official page before approval. |
| Inputs | `AAOIFI_MVP_DECISIONS.md` (D1–D18, S1), `AAOIFI_SS21_METHODOLOGY_V1_DRAFT.md` rev 3, `screening/eligibility.py`, `config/sharia_eligibility.csv` (header-only) |

## 1. What the repo already has

| Item | Finding |
|---|---|
| Fundamentals client | **None.** `data/` has price providers only: `yfinance_provider.py`, `alpaca_provider.py`, plus `earnings.py` (a CSV loader). `requirements.txt` has no SEC or fundamentals library. |
| SEC precedent | SEC EDGAR is already used, **manually**, as an evidence source. `config/earnings_calendar_sources.csv` records accession numbers, `accepted_et` timestamps and `sec.gov/Archives` index URLs. `artifacts/day18h/day18h-evidence-report.md` cites EDGAR filings with SHA-256 hashes and byte counts. The project's provenance convention (accession + URL + hash) fits SEC data directly. |
| Registry fields that need provenance | `methodology`, `source`, `source_ref`, `source_date` (≤ `valid_from`, at most 92 days old), `note` (required for UNVERIFIED). |

## 2. Required inputs, split into SEC filing facts and derived classifications

**Filing facts** are values a filing reports. **Derived classifications** are project judgements built from facts using a versioned mapping (D7, D8, D9). No source supplies "interest-bearing debt" or "prohibited income" as a label. The tag names below are *candidate* US-GAAP/DEI concepts **[UNVERIFIED]**. Issuers vary, and the mapping is a project artefact, not a source field.

| # | Input (decision) | Filing facts needed (candidate concepts) | Derived by the project | Obtainable without estimates? |
|---|---|---|---|---|
| F1 | Filing identity and timing (D1, D5, D18; registry `source_date`) | CIK, accession number, form type (10-K/10-Q/amendments), period end, filing date, **acceptance datetime** | `source_date` = filing date (or the next session after an after-hours acceptance; policy to be fixed in code) | Yes |
| F2 | Interest-bearing debt, T1 (D7) | `ShortTermBorrowings`, `CommercialPaper`, `LongTermDebtCurrent`, `LongTermDebtNoncurrent`, `LongTermDebt`, `FinanceLeaseLiability*`, `ConvertibleNotesPayable*`, … | **"Interest-bearing debt"** = sum per the D7 mapping; unmapped material debt lines are included | Facts: mostly. Classification: derived. Overlapping tags (total versus components) need de-duplication rules. |
| F3 | Interest-bearing cash and investments, T2 (D7) | `CashAndCashEquivalentsAtCarryingValue`, `ShortTermInvestments`, `AvailableForSaleSecuritiesDebtSecurities*`, `MarketableSecurities*`, … | **"Interest-bearing deposits"** per D7; cash that can't be classified is included | Facts: yes. Whether a given balance actually earns interest is **not reported**, so classification relies on the conservative D7 default. |
| F4 | Total revenue, T3 denominator (D8) | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, … (fiscal year, from the 10-K) | Choosing the single "total revenue" fact per issuer | Yes, with a tag-priority rule |
| F5 | Prohibited income, T3 numerator (D8, D9) | `InvestmentIncomeInterest`, `InterestIncomeOther`, `InterestAndDividendIncomeOperating`, …; **segment revenue** (dimensional facts) | **"Prohibited income"** = interest income + revenue from segments on the D9 list | **Partially.** Interest income is usually tagged. Prohibited revenue inside a segment is often not disclosed separately, so the result is UNVERIFIED (D8/D14). |
| F6 | Principal activity (D9, S1) | SIC code (filer metadata); segment revenue (dimensional) | Principal activity = largest-revenue segment; check against the exclusion list | SIC: yes. Segments: dimensional data only (see §3). |
| F7 | Shares outstanding per class (D6) | `dei:EntityCommonStockSharesOutstanding` (cover page; **per class through a dimension** for multi-class issuers), class trading symbols | Listed-class sum (D6) | Single class: yes. **Multi-class: only from dimensional data.** |
| F8 | Preferred stock (D16) | `PreferredStockValue`, `PreferredStockSharesOutstanding` | Whether there is a "financial preference" | Amounts: yes. **Preference terms are narrative text**, so a human review or an UNVERIFIED result. |
| F9 | Closing price per class (D1) | Not in SEC data | Market cap = F7 × price | **Separate price source required.** Alpaca permission is unresolved; out of scope here. |
| F10 | 3/4/1 constitutional objectives | Charter/bylaws exhibits (text) | Human review | Not structured; human only |
| F11 | 3/19 market value of tangible assets (D17) | Book values only (`PropertyPlantAndEquipmentNet`, `InventoryNet`, …) | Not derivable; filings carry book values | **No.** Blocked on the adviser (D17) |

## 3. Candidate sources

| Criterion | **A. SEC EDGAR XBRL APIs** (`data.sec.gov`: `submissions`, `companyfacts`, `companyconcept`, `frames`) | **B. SEC Financial Statement (and Notes) Data Sets** (quarterly bulk ZIPs) | C. Raw EDGAR XBRL / iXBRL per filing (`sec.gov/Archives`) | D. Commercial point-in-time fundamentals (e.g. Sharadar/Nasdaq Data Link, Intrinio, FactSet, S&P Capital IQ) | E. yfinance fundamentals | F. Alpaca |
|---|---|---|---|---|---|---|
| Access | HTTPS JSON, no key. A declared User-Agent with contact details is required. Fair-access limit of about 10 requests/s **[UNVERIFIED]** | HTTPS ZIP per quarter, tab-separated files (`sub`, `num`, `tag`, `pre`; the Notes variant adds dimensional data) **[UNVERIFIED]** | HTTPS per-filing documents | Paid API or bulk files with an API key | Scrapes Yahoo pages | Broker/data API |
| Terms of use and storage | US government public data. Usage governed by SEC fair-access policy and the website terms. **Terms to verify** before use. No licence fee expected **[UNVERIFIED]** | Same as A **[UNVERIFIED]** | Same as A | Licensed. Redistribution and storage limits vary; contract required | Yahoo terms; not licensed for this use | Unresolved; **must not be called** |
| Coverage | XBRL filers. Full financial-statement XBRL for all US operating companies from about 2011 (phased in 2009–2011) **[UNVERIFIED]**. **`companyfacts` reportedly omits dimensional facts** **[UNVERIFIED]** | Same filers, from 2009. **The Notes variant reportedly includes dimensional facts** (segments, share classes) **[UNVERIFIED]** | Complete, including dimensions and extensions | Broad. Gaps vary by vendor | Recent years only | No issuer financial statements **[UNVERIFIED]** |
| As-filed history | **Yes.** Each fact carries the `accn`, `form` and `filed` of the filing that reported it, so restated values appear as separate facts from later filings. Point-in-time selection = "facts filed ≤ date" | **Yes.** Each submission is a snapshot as filed | Yes, by construction | Varies. Some offer as-reported with filing date (e.g. Sharadar "ARQ"/`datekey`) **[UNVERIFIED]**; others are restated or standardised | **No.** Latest restated only | — |
| Filing timestamps | `filed` date per fact. **Acceptance datetime per filing in `submissions`** **[UNVERIFIED]** | `sub.accepted` timestamp **[UNVERIFIED]** | Header acceptance datetime | Usually a filing date; acceptance time rarely given | None | — |
| Share classes | **Gap:** per-class cover-page shares are dimensional, so they are reportedly missing from `companyfacts` for multi-class issuers (e.g. GOOGL/GOOG) | Likely available in the Notes variant (dimensional) **[UNVERIFIED]** | Available | Varies; often a single total | Single total | — |
| Segments (D9) | Gap (dimensional) | Likely available (Notes variant) **[UNVERIFIED]** | Available | Often a standardised segment feed (vendor-derived) | No | — |
| Values without estimates? | Reported facts: yes. Classifications: derived by the project | Yes | Yes | Mostly. **Standardised fields such as "totalDebt" are vendor derivations, not filing facts**, so they would need mapping documentation | No; mixed provenance | — |
| Effort | Low: small JSON per issuer; fits about 25–100 symbols | Medium: about 50–100 MB+ per quarter **[UNVERIFIED]**; needs a filter step | High: iXBRL parsing | Low to medium, plus procurement | — | — |
| Verdict | **Recommended primary** (subject to §4) | **Recommended fallback and supplement** for dimensional facts | Last resort, for single-filing audits only | Only if A and B prove insufficient; requires licence review and budget | **Rejected**: no as-filed history or filing dates, licensing unclear | **Rejected for fundamentals**; not in scope |

## 4. Recommendation (not an approval)

- **Primary: A, the SEC EDGAR XBRL APIs.** Use `submissions` for F1 (form, filing date, acceptance time, SIC) and `companyfacts` for F2–F5 and F8. It is official and as-filed (each fact is tied to an accession), has no licence fee, and matches the repo's existing accession + URL + SHA-256 provenance convention.
- **Fallback: B, the SEC Financial Statement and Notes Data Sets.** Use them for what A cannot supply: per-class shares (F7) and segment revenue (F5, F6). They are also an independent as-filed cross-check of A.
- **Gaps no candidate closes:**
  - F9 price (separate licensed source; Alpaca permission unresolved);
  - F10 charter objectives (human review);
  - F11 market value of tangible assets (filings give book values; D17 blocked on the adviser);
  - the "financial preference" terms of preferred shares (F8, text; human or UNVERIFIED);
  - whether cash actually earns interest (F3; D7's conservative default applies).
- **Neither A nor B is approved yet.** Before approval, all of these are needed:
  1. **Read and record the SEC terms:**
     - "Accessing EDGAR Data" (fair access, User-Agent, rate limit; expected at `https://www.sec.gov/os/accessing-edgar-data` **[UNVERIFIED URL]**);
     - the EDGAR API documentation page;
     - the Financial Statement (and Notes) Data Sets page.
  2. **Confirm** that `companyfacts` omits dimensional facts and that the Notes data sets include them.
  3. **Owner approval** for network access to `sec.gov`/`data.sec.gov`, a contact User-Agent string, and a storage location **outside `data/`**, git-ignored, with SHA-256 per downloaded file (consistent with `artifacts/day18h`).

## 5. Smallest concrete unblocking action

**Approve a one-issuer, read-only SEC pilot.** The owner decides:
- which issuer: preferably one multi-class (GOOGL) **or** one single-class (MSFT);
- the User-Agent contact string;
- the storage directory outside `data/`.

Then fetch exactly two JSON files, `submissions/CIK##########.json` and `api/xbrl/companyfacts/CIK##########.json`, after first reading and recording the SEC access terms. Hash them, and produce a field-availability table for F1–F8 against the latest 10-K and 10-Q. The table must show which concepts exist, their `accn`/`filed` values, and whether per-class shares are absent.

That pilot gives a factual yes or no on the primary provider. Nothing is cached beyond those two hashed files, and no code is written.
