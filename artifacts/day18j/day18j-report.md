# DAY-18J — Protocol v2.0.4 Amendment Report (RECOVERED)

> **RECOVERED ARTIFACT.** This report and the two amendment files were recovered on 2026-10-08 from the authoritative DAY-18J handoff content. The original DAY-18J work was never committed and was missing from the working tree. **This is not a new protocol-owner decision.** No new semantics were introduced.

| Field | Value |
|---|---|
| Task | DAY-18J artifact recovery |
| HEAD (start = end) | `75c914f5226685f331cbb2e56a9c4db7c52b24b9` |
| Protocol parent | **v2.0.3** `d26b36ef802cf0810952b2e5c4e8e19d908b4555` |
| Recovered version | **v2.0.4** (`protocol_change`, `modified: true`, DRAFT — PENDING COMMIT) |
| Files created | `artifacts/day18j/protocol-v2.0.4-amendment.md`, `artifacts/day18j/protocol-v2.0.4-amendment.json`, `artifacts/day18j/day18j-report.md` |
| Files modified | none |
| Stage R status | **BLOCKED** (unchanged) |

## Summary
- **Parent protocol:** v2.0.3.
- **Defect:** v2.0.3 left its numerical evaluation semantics unspecified. The implementation evaluated the closed-interval rule in float64, which produced float64 false positives.
- **Fix:** exact rational evaluation is now authoritative. float64 is diagnostic only.
- **No mathematical rule change:** a change is detected iff `NOT (ρ_min ≤ 1 ≤ ρ_max)`, the interval is closed, and endpoint equality counts as containment.
- **No tolerance introduced:** no epsilon, no floating-point tolerance, no provider-specific tolerance.
- **No exceptions:** none for any symbol, date or provider. The anti-leakage scan found zero hits in the rule sections.
- **New classifications:**
  - `EXACT_EVALUATION_INVALID`: BLOCKING.
  - `NUMERICAL_FALSE_POSITIVE`: NON-BLOCKING; must be recorded in the evaluation evidence.
  - `NUMERICAL_FALSE_NEGATIVE`: exact detection is authoritative.
  - Both numerical classifications apply symmetrically.
- **Degenerate check:** the v2.0.3 PRECISION_DEGENERATE check (`a − δ ≤ 0` ⇒ BLOCKING) remains authoritative.
- **Review records:** no new decision type. A v2.0.3 record whose item is no longer detected under exact v2.0.4 evaluation becomes **MOOT** (not INVALID) and stays in history.
- **What this task did not do:** no research, no backtest, no holdout or forward-OOS access, no data acquisition, no network. The snapshot was not read for this task (only its manifest hash was re-checked) and was not modified. No review records were created or modified (the 14 DAY-18F records are unchanged). No production code was changed.
- **AMZN 2016-02-22 and NFLX 2018-11-29 remain unresolved** until the mechanical v2.0.4 re-evaluation in DAY-18K. They appear only as history and rationale.

## Open question raised during recovery
**OQ10 — raw-close conversion (OPEN).** The recovered content specifies shortest round-trip decimal → exact rational conversion only for stored *adjusted* closes. v2.0.3 says raw closes are "exact" but does not say how they become rationals, and the `ρ` formulas need them. Following the protocol owner's instruction, this was recorded as OPEN rather than decided. **It must be settled before DAY-18K implementation.**

## Observation (no rule change)
With the 2-decimal floor, any positive value displayed with `d` decimals is at least `10^−d`, which is always greater than `δ = 1/(2·10^max(d,2))`. PRECISION_DEGENERATE can therefore only be reached through non-positive inputs, and those inputs are also EXACT_EVALUATION_INVALID. Both statuses are BLOCKING, so precedence between them has no practical effect. Precedence is not specified, and this recovery does not specify it.

## Validation run (scratchpad script; no snapshot data)
1. **JSON syntax:** PASS.
2. **Structure vs. the v2.0.3 amendment JSON:** all 24 core top-level keys are present with matching JSON types. Version, type, parent and Stage R fields are correct. PASS.
3. **Parent-chain and evidence hashes:** 19 file hashes were checked against the committed git blobs at the cited commits, all 7 cited commits exist, and the R1/v2.0.1/v2.0.2 citations are identical to v2.0.3's. PASS.
   - The first run flagged three DAY-18H JSON files whose working-tree bytes differ from the committed blobs because of CRLF conversion (`core.autocrlf=true`, OQ5).
   - The amendment now cites committed-blob hashes and states this basis in `evidence_report.hash_basis`.
4. **Anti-leakage:** zero hits in the JSON rule sections and in MD §1–§4. The scan covered 32 symbols (universe plus related tickers), `YYYY-MM-DD` dates and provider names. PASS.
5. **Synthetic exact arithmetic** (made-up values, `fractions.Fraction`). PASS.

   | Case | Exact result |
   |---|---|
   | exact `ρ_max == 1` | NO DETECTION (float64 diagnostic agreed: `1.0000000000000002`) |
   | interval strictly containing 1 | NO DETECTION |
   | interval outside 1 | DETECTION |
   | NaN / zero / negative / non-convertible input | EXACT_EVALUATION_INVALID |
   | degenerate predicate (`a − δ = 0` and `< 0`) | BLOCKING |
   | non-degenerate predicate (`a − δ > 0`) | not degenerate |

6. **Post-checks:**
   - `git status` shows only `?? artifacts/day18j/`.
   - The snapshot manifest SHA-256 is still `aefef19d…006bd`.

## Notes
- `artifacts/day18i/` does not exist in this working tree, so there is nothing to keep uncommitted there.
- Nothing was committed or pushed.
- **DAY-18J is recovered and ready for DAY-18K**, subject to OQ10.
