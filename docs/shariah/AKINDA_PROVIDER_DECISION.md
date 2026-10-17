# D13-A: Akinda as the authoritative stock-level Shariah screening provider

| Field | Value |
|---|---|
| Decision date | 2026-10-17 |
| Decided by | Project owner (explicit instruction: "Akinda will be the primary and authoritative provider for stock-level Shariah screening. We will accept Akinda's screening decisions rather than building a separate manual screening process.") |
| Amends | D13 in `AAOIFI_MVP_DECISIONS.md` (third-party screens), for Akinda only |
| Methodology id | `AKINDA_COMPLIANCE_API_V1` in `screening/eligibility.py` `ACCEPTED_METHODOLOGIES` (constant `AKINDA_COMPLIANCE_METHODOLOGY`) |
| Adviser sign-off | **Not on file.** D13's original condition ("with the adviser's sign-off") is replaced by this owner decision. |

## Scope

This is a **provider-selection decision for stock-level screening**. Akinda's `/compliance` verdict is accepted as the project's evidence for whether a single stock is Shariah-compliant.

It does **not** decide anything else. It does not decide:
- whether day trading is permissible (D12);
- purification (D10, D11);
- broker conditions (D15);
- preferred shares (D16);
- the 3/19 threshold (D17).

It also does not change any trading risk control. Live trading stays blocked by the existing go/no-go checklist items that are not about stock screening (D12, D15, D2 exit logic).

Akinda describes its own output as "Informational screening based on reported financial data. Not a fatwa; does not replace a qualified scholar." It also states: "Akinda is not affiliated with, endorsed by, or licensed by AAOIFI."

## Vendor contract used

From https://b2b.akinda.io/developer/docs, read 2026-10-17. No API call was made.

- **Endpoint:** `GET https://b2b-api.akinda.io/api/v1/compliance/{TICKER}`. Auth header `X-API-Key`.
  - The query-parameter form `?apikey=` is documented but is not used, so the key never appears in URLs.
- **Fields:**
  - `ticker`: "Uppercase ticker symbol echoed back from the request";
  - `company_name`, `halal_status`, `listing_country`, `reporting_currency`;
  - `last_scanned`: "When the Shariah audit last ran for this ticker. null means never audited";
  - `last_updated`: "When the market data behind this payload was last refreshed".
- **Example dates** look like `"Aug 06, 2026"`.
- **Documented `halal_status` values:**
  - `HALAL`, `NOT HALAL` (with a space), `DOUBTFUL`;
  - `UNQUALIFIED` (never audited);
  - `ERROR_DATA` and `INCOMPLETE_DATA` ("data unavailable, not a verdict").
  - `HARAM` is **not** a documented value.
- **Methodology statement:** the status is "a single AAOIFI-aligned status string"; "AAOIFI is Akinda's primary methodology"; thresholds "debt 30% · liquidity 30% · income 5%". No version field is published, so `AKINDA_COMPLIANCE_API_V1` is a project label for "the `/api/v1/compliance` verdict".
- **Errors:**
  - 401 "Invalid or missing API key";
  - 403 "Your plan does not include this endpoint";
  - 404 not in coverage;
  - 429 "Rate limit or bandwidth quota exceeded".
- **Quota:** `/compliance` "10 / day" on the Basic plan. The reset time is not documented.
- **Licence:**
  - "You may not redistribute the raw response data as a competing dataset";
  - commercial licence "Required for any monetised app, paid feature, or partner integration";
  - redistribution rights via contact@akinda.io.

## Mapping into the registry (`acquisition/akinda/normalize.py`)

| Akinda response | Registry row |
|---|---|
| `HALAL` with `last_scanned` parseable, not after retrieval, and at most `MAX_SOURCE_AGE_DAYS` (92) days old | `COMPLIANT` |
| `NOT HALAL` with the same date conditions | `NON_COMPLIANT` |
| `DOUBTFUL`, `UNQUALIFIED`, `ERROR_DATA`, `INCOMPLETE_DATA` | `UNVERIFIED` (not tradable) |
| Any other status string (including `HARAM`, lower case, or padded) | `UNVERIFIED` with an "unrecognised" note |
| `HALAL` / `NOT HALAL` whose `last_scanned` is null, unparseable, in the future or stale | `UNVERIFIED`, with an empty `source_date` |
| Not JSON, a missing documented field, a wrong type, or a ticker echo that doesn't match the request | No record |
| HTTP 404 or any other non-200 | No record |

### Field rules

- **`source_date`:**
  - It is Akinda's `last_scanned`, the vendor's screening date.
  - It is never the retrieval time.
  - It is never `last_updated`, which is only a market-data refresh date.
- **`valid_from` and `reviewed_on`:**
  - Both are the retrieval date (America/New_York).
  - There is no backfilling: a verdict never covers a session before it was retrieved.
- **`valid_until`:**
  - It is `valid_from + valid_days - 1`.
  - `valid_days` is a **required operator argument** (1..92, the registry's existing limit).
  - The project has not fixed a refresh cadence, so no default is assumed.
- **`reviewer`:**
  - It is `akinda-sync (automated; owner provider decision D13-A)`.
  - This is an automated acceptance under this decision, not a human per-ticker review.
- **Freshness:**
  - Freshness is enforced by the existing registry rules, which are unchanged: the source can be at most 92 days old at `valid_from`, the validity window is at most 92 days, and dates must be point-in-time.
  - Since 2026-10-17 the registry also requires `valid_until − source_date ≤ 92`, and the sync caps `valid_until` at `last_scanned + 92`. A record therefore never stays valid after its screening is 92 days old. (This closes the earlier gap, where a record could be used until the screening was 92 + N − 1 days old.)

## Operation

- **Command:** `python -m acquisition.akinda.sync --tickers T1 [T2 ...] --valid-days N`.
- **Limits:**
  - at most 10 tickers per run, with no default universe;
  - every HTTP attempt is logged before it is sent, and the run is refused if the rolling 24-hour count would exceed 10;
  - 401, 403 and 429 stop the batch, with no retry;
  - 5xx and network errors get at most 2 attempts;
  - redirects are refused (`allow_redirects=False` in `acquisition/akinda/client.py`). A 3xx response is never followed and gets no record, so the `X-API-Key` header can never be forwarded to another host.
- **Key:** `AKINDA_API_KEY`, read from the environment or the git-ignored `.env`. It is sent only in the header and redacted from every output and stored body.
- **Evidence:**
  - written to the git-ignored `screening_evidence/akinda/runs/<run_id>/`: the redacted raw bodies, `summary.json` (retrieval time, raw status, raw `last_scanned` and `last_updated`, body SHA-256, attempts), and `proposed.csv`;
  - `proposed.csv` is validated by `load_registry` under production defaults.
- **The tool never edits `config/sharia_eligibility.csv`.** Copying validated rows there is the step that makes tickers tradable for `paper_orb`.
  - **Check the licence first:** the repository is public, and committed rows republish vendor verdicts.
