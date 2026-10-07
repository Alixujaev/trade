# DAY-18H — Stage R Unexplained-Change Evidence Investigation Dossier

> **EVIDENCE INVESTIGATION ONLY.**  
> **No protocol-owner decision has been made.**  
> This dossier does NOT create or modify review records, does NOT amend the protocol, and does NOT alter the Stage R status.

| Field | Value |
|---|---|
| Task | **DAY-18H** — Investigate the two remaining Stage R unexplained-change blockers |
| Current HEAD | `2ad9b272002ce514318ce7c3774b422f24a19f3c` (`2ad9b27`) |
| Protocol Chain | v2.0 R1 `ba3cefe` + v2.0.1 `ed034b3` + v2.0.2 `0ebb606` + v2.0.3 `d26b36e` |
| Stage R Status | **BLOCKED** (`usable_for_research = false`) |
| Source Snapshot (Read-Only) | `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/` (64 files, manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`, verified unchanged) |
| Items Investigated | 1. AMZN (2016-02-22, $p = \text{2016-02-19}, k = \text{2016-02-22}$)<br>2. NFLX (2018-11-29, $p = \text{2018-11-28}, k = \text{2018-11-29}$) |
| Review Records Created / Modified | **0 / 0** (`artifacts/reviews/stage_r/` untouched) |
| Re-evaluation Performed | **No** (forbidden in DAY-18H) |

---

## Executive Summary

The investigation into the two remaining Stage R blockers (AMZN 2016-02-22 and NFLX 2018-11-29) uncovered a critical mathematical and implementation finding:

1. **Exact Mathematical Reality**:
   - In both cases, **no economic corporate action occurred** in $(p, k]$, and **no true factor change occurred**.
   - For AMZN, the constant adjustment factor of $20.0$ applies across both sessions (stemming from the 20:1 forward split of 2022-06-06). Unrounded adjusted closes are $534.90 / 20 = 26.745$ at $p$ and $559.50 / 20 = 27.975$ at $k$. Rounded to 2 decimals using standard round-half-to-even, they produce stored adjusted closes $a_p = 26.74$ and $a_k = 27.98$.
   - For NFLX, the constant adjustment factor of $10.0$ applies across both sessions (stemming from the 10:1 forward split of 2025-11-17). Unrounded adjusted closes are $282.65 / 10 = 28.265$ at $p$ and $288.75 / 10 = 28.875$ at $k$. Rounded to 2 decimals using round-half-to-even, they produce stored adjusted closes $a_p = 28.26$ and $a_k = 28.88$.
   - Under the v2.0.3 per-value error model ($\delta_p = \delta_k = 0.005$), the exact supremum of the ratio interval over the rounding box is:
     $$\sup \rho = \frac{r_k / (a_k - \delta_k)}{r_p / (a_p + \delta_p)} = \frac{r_k / \text{unrounded}_k}{r_p / \text{unrounded}_p} = 1.0 \quad \text{EXACTLY.}$$
   - Therefore, under exact real arithmetic, **$1.0 \in [\rho_{\min}, \rho_{\max}]$ holds identically** for both symbols!

2. **The Numerical Implementation Gap (`PROTOCOL_GAP`)**:
   - In `acquisition/v2/crosscheck.py`, the interval is evaluated in IEEE 754 binary floating-point (`float64`):
     $$\rho_{\max} = \rho \cdot \frac{a_k}{a_k - \delta_k} \cdot \frac{a_p + \delta_p}{a_p}$$
   - Because $(a_p + \delta_p)$ is inexact in binary float ($26.74 + 0.005 = 26.7449999999999974...$), `rho_max` evaluates to $1.0 - 2.22 \times 10^{-16}$ for AMZN ($-1$ ULP) and $1.0 - 1.11 \times 10^{-16}$ for NFLX ($-0.5$ ULP).
   - The test `1.0 <= rho_max` returns `False` by less than $1$ ULP, falsely triggering a factor-change detection.

3. **Admissibility & Classification**:
   - The mechanical precondition for `PROVIDER_ADJUSTMENT_ARTIFACT` in v2.0.3 item 3 (zero corporate actions in `complete` and `all` payloads) is **SATISFIED** for both symbols.
   - However, the provider did not produce a data error or document an adjustment artifact; provider prices are exact round-to-even representations of the split-divided raw prices.
   - The anomaly represents a **`PROTOCOL_GAP`** between the mathematical specification of the precision bound and its IEEE 754 floating-point implementation.

---

## 1. AMZN (2016-02-22) Investigation

### Q1: What exactly is the observed adjusted-price anomaly?
- Sessions: $p = \text{2016-02-19}$, $k = \text{2016-02-22}$.
- Stored raw close: $r_p = 534.90$, $r_k = 559.50$.
- Stored adjusted close: $a_p = 26.74$, $a_k = 27.98$ (displayed decimals: $d_p = 2, d_k = 2 \implies \delta_p = \delta_k = 0.005$).
- Implied factors: $f_p = 534.90 / 26.74 = 20.0037397$, $f_k = 559.50 / 27.98 = 19.9964260$.
- Factor ratio: $\rho = f_k / f_p = 0.9996343835052438$ ($|\rho - 1| = 3.656 \times 10^{-4}$).
- Float interval in cross-check: $[\rho_{\min}, \rho_{\max}] = [0.999268897657797, 0.9999999999999998]$.
- Anomaly: $1.0 \le \rho_{\max}$ evaluates to `False` by $2.22 \times 10^{-16}$ (1 ULP), flagging an unexplained change with 0 corporate action records in $(p, k]$.

### Q2: What does the provider actually return?
- Endpoint `/v2/stocks/bars` (`adjustment=raw`): $534.90$ (2016-02-19), $559.50$ (2016-02-22).
- Endpoint `/v2/stocks/bars` (`adjustment=all`): $26.74$ (2016-02-19), $27.98$ (2016-02-22).
- Endpoint `/v1/corporate-actions`: Returns 0 records of any of the 16 types for AMZN in $(p, k]$ in both `data_quality=complete` and `data_quality=all`.

### Q3: What corporate-action records exist?
- In $(p, k]$: 0 in `complete`, 0 in `all`.
- Within $\pm 30$ sessions: 0 records.
- Across all of Stage R (2016-01-04 to 2022-12-30): Exactly 1 record — forward split 20:1 on 2022-06-06 (id `0995b688-d461-4d30-9e3e-54549a070c0e`, CUSIP `023135106`, `old_rate`: 1, `new_rate`: 20).

### Q4: What provider-side evidence exists?
- Immutable snapshot files:
  - `bars_raw/AMZN.parquet` (SHA-256 `061c07cb4fb0ba09d9ac69a2fabc932c33f3e178a588966fd5b6e4b727c57ab3`)
  - `bars_all/AMZN.parquet` (SHA-256 `24ae996bd7fcea9420cb919725ea3fa8ab5d301a1f09e1a69e8fa1c174526649`)
  - `corporate_actions_complete.json` and `corporate_actions_all.json` (SHA-256 `268b3a2c2ea8b4164e6e4488a06680fdf8dd7ab56e8e0be0ad5700e80d0ed8e9`)
- Precondition for `PROVIDER_ADJUSTMENT_ARTIFACT` (0 records in $(p, k]$ across both payloads) is satisfied.
- The provider does not return any revision or correction record documenting an adjustment artifact.

### Q5: What external authoritative evidence exists?
- SEC EDGAR filings for Amazon.com, Inc. (CIK `0001018724`):
  - Form 8-K filed 2016-02-10 (URL: `https://www.sec.gov/Archives/edgar/data/1018724/000101872416000176/0001018724-16-000176.txt`, SHA-256 `0c971aacce573d8299a7630f919783f59435e93570849698a5f7e5c46c0c9f32`, 28,781 bytes): Officer changes and buyback; no split/dividend.
  - Form 8-K filed 2016-02-25 (URL: `https://www.sec.gov/Archives/edgar/data/1018724/000101872416000206/0001018724-16-000206.txt`, SHA-256 `c74df0b8c981a8ebfbc82fe11d012676b2a3f7dd7db771bfe86c8cd2115c05d7`, 267,247 bytes): Bylaws amendment; no split/dividend.
- Diagnostic source: Yahoo Finance unrounded pre-split closes are $26.745$ (2016-02-19) and $27.975$ (2016-02-22).

### Q6: Does any evidence mathematically reconcile the adjustment?
- **YES.**
  - Candidate factor: $\rho_{\text{candidate}} = 1.0$ (constant adjustment factor $20.0$).
  - Unrounded: $a_p^* = 534.90 / 20 = 26.745$; $a_k^* = 559.50 / 20 = 27.975$.
  - Stored: $a_p = 26.74$ (round-half-to-even of $26.745$); $a_k = 27.98$ (round-half-to-even of $27.975$).
  - Exact interval:
    $$\rho_{\max}^* = \frac{r_k / (a_k - \delta_k)}{r_p / (a_p + \delta_p)} = \frac{559.50 / 27.975}{534.90 / 26.745} = \frac{20.0}{20.0} = 1.0 \quad \text{EXACTLY.}$$
  - $\rho_{\text{candidate}} - \rho_{\max}^* = 1.0 - 1.0 = 0.0$.
  - In exact arithmetic, $1.0 \in [\rho_{\min}^*, \rho_{\max}^*]$ is **EXACT**.

### Q7: Is there sufficient evidence for PROVIDER_ADJUSTMENT_ARTIFACT?
- Precondition under v2.0.3 item 3: **SATISFIED** (zero records in both payloads).
- Evidence classification: **`PROTOCOL_GAP`** / **`C. INSUFFICIENT`** as an explicit provider data error, because the provider data is mathematically correct; the defect is in the floating-point cross-check implementation.

### Q8: If not, why not?
- The provider made no error. The true adjustment factor is $20.0$ on both sessions. The anomaly is an IEEE 754 float rounding artifact ($1.0 - 2.22 \times 10^{-16} < 1.0$).

---

## 2. NFLX (2018-11-29) Investigation

### Q1: What exactly is the observed adjusted-price anomaly?
- Sessions: $p = \text{2018-11-28}$, $k = \text{2018-11-29}$.
- Stored raw close: $r_p = 282.65$, $r_k = 288.75$.
- Stored adjusted close: $a_p = 28.26$, $a_k = 28.88$ ($d_p = 2, d_k = 2 \implies \delta_p = \delta_k = 0.005$).
- Implied factors: $f_p = 282.65 / 28.26 = 10.001769285$, $f_k = 288.75 / 28.88 = 9.998268698$.
- Factor ratio: $\rho = f_k / f_p = 0.9996500032096312$ ($|\rho - 1| = 3.500 \times 10^{-4}$).
- Float interval in cross-check: $[\rho_{\min}, \rho_{\max}] = [0.9993001275883086, 0.9999999999999999]$.
- Anomaly: $1.0 \le \rho_{\max}$ evaluates to `False` by $1.11 \times 10^{-16}$ (0.5 ULP), flagging an unexplained change with 0 corporate action records in $(p, k]$.

### Q2: What does the provider actually return?
- Endpoint `/v2/stocks/bars` (`adjustment=raw`): $282.65$ (2018-11-28), $288.75$ (2018-11-29).
- Endpoint `/v2/stocks/bars` (`adjustment=all`): $28.26$ (2018-11-28), $28.88$ (2018-11-29).
- Endpoint `/v1/corporate-actions`: Returns 0 records of any of the 16 types for NFLX in $(p, k]$ in both `data_quality=complete` and `data_quality=all`.

### Q3: What corporate-action records exist?
- In $(p, k]$: 0 in `complete`, 0 in `all`.
- Within $\pm 30$ sessions: 0 records.
- Across all of Stage R: 0 records for NFLX.

### Q4: What provider-side evidence exists?
- Immutable snapshot files:
  - `bars_raw/NFLX.parquet` (SHA-256 `6e7d2dd65dc556626d40e0429f2b7517980bdba30a2ab8dc91bc1cca8fb34c3c`)
  - `bars_all/NFLX.parquet` (SHA-256 `fc4686b6ec0d56e3e5eb7536e793fb1918f014cc7a65d877ed27147f74b2878b`)
  - `corporate_actions_complete.json` and `corporate_actions_all.json` (SHA-256 `268b3a2c2ea8b4164e6e4488a06680fdf8dd7ab56e8e0be0ad5700e80d0ed8e9`)
- Precondition for `PROVIDER_ADJUSTMENT_ARTIFACT` (0 records in $(p, k]$ across both payloads) is satisfied.
- The provider does not return any revision or correction record documenting an adjustment artifact.

### Q5: What external authoritative evidence exists?
- SEC EDGAR filings for Netflix, Inc. (CIK `0001065280`):
  - Form 4 filed 2018-11-26 (URL: `https://www.sec.gov/Archives/edgar/data/1065280/000106528018000592/0001065280-18-000592.txt`, SHA-256 `835253584f6fa1b3b2c0b39c54d2553286158b47e5a53c7602210da975bdeb65`, 31,902 bytes): Routine stock option exercise; no split/dividend.
  - Form 8-K filed 2018-12-28 (URL: `https://www.sec.gov/Archives/edgar/data/1065280/000106528018000619/0001065280-18-000619.txt`, SHA-256 `0f787f5698de8aa6a937ee80d45dcc21903f9bbe8cc86b07364bff59ac3e2455`, 34,326 bytes): Executive compensation; no split/dividend.
- Diagnostic source: Yahoo Finance unrounded closes are $28.265$ (2018-11-28) and $28.875$ (2018-11-29).

### Q6: Does any evidence mathematically reconcile the adjustment?
- **YES.**
  - Candidate factor: $\rho_{\text{candidate}} = 1.0$ (constant adjustment factor $10.0$).
  - Unrounded: $a_p^* = 282.65 / 10 = 28.265$; $a_k^* = 288.75 / 10 = 28.875$.
  - Stored: $a_p = 28.26$ (round-half-to-even of $28.265$); $a_k = 28.88$ (round-half-to-even of $28.875$).
  - Exact interval:
    $$\rho_{\max}^* = \frac{r_k / (a_k - \delta_k)}{r_p / (a_p + \delta_p)} = \frac{288.75 / 28.875}{282.65 / 28.265} = \frac{10.0}{10.0} = 1.0 \quad \text{EXACTLY.}$$
  - $\rho_{\text{candidate}} - \rho_{\max}^* = 1.0 - 1.0 = 0.0$.
  - In exact arithmetic, $1.0 \in [\rho_{\min}^*, \rho_{\max}^*]$ is **EXACT**.

### Q7: Is there sufficient evidence for PROVIDER_ADJUSTMENT_ARTIFACT?
- Precondition under v2.0.3 item 3: **SATISFIED** (zero records in both payloads).
- Evidence classification: **`PROTOCOL_GAP`** / **`C. INSUFFICIENT`** as an explicit provider data error, because provider prices are mathematically correct; the defect is in the floating-point cross-check implementation.

### Q8: If not, why not?
- The provider made no error. The true adjustment factor is $10.0$ on both sessions. The anomaly is an IEEE 754 float rounding artifact ($1.0 - 1.11 \times 10^{-16} < 1.0$).

---

## 3. Side-by-Side Summary Table

| Item | Provider evidence | Corporate event | Mathematical reconciliation | Evidence classification |
|---|---|---|---|---|
| **AMZN** (2016-02-22) | 0 CA records in `complete` & `all`; bars stored at 2 decimals ($26.74, 27.98$) | No corporate action in $(p, k]$; 2022 20:1 split applies constant factor $20.0$ | Exact: $\rho_{\max} = 1.0$; float evaluates as $1.0 - 2.22 \times 10^{-16}$ | **PROTOCOL_GAP** (Precondition satisfied; numerical artifact) |
| **NFLX** (2018-11-29) | 0 CA records in `complete` & `all`; bars stored at 2 decimals ($28.26, 28.88$) | No corporate action in $(p, k]$; 2025 10:1 split applies constant factor $10.0$ | Exact: $\rho_{\max} = 1.0$; float evaluates as $1.0 - 1.11 \times 10^{-16}$ | **PROTOCOL_GAP** (Precondition satisfied; numerical artifact) |

---

## 4. Verification & Immutability

1. **Stage R Snapshot**: Manifest SHA-256 `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd`, 64/64 files verified intact before and after.
2. **Review Records**: All 14 files under `artifacts/reviews/stage_r/` remain unchanged and untouched.
3. **Protocol Files**: No protocol file was modified.
4. **Production Code**: No file under `acquisition/v2/` or anywhere else was modified.
5. **Re-evaluation**: No Stage R re-evaluation was executed.
6. **Files Created**: Only `artifacts/day18h/` was created, containing uncommitted dossier files.
