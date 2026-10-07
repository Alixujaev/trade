# OOS Protocol — TEMPLATE (protocol v1.0)

> Copy to `artifacts/<EXP-ID>/protocol.md`, fill **every** field, and **commit before any OOS snapshot is merged or read beyond the structural checks** (`data-expansion-spec.md` §5).
> Leave a field as `NOT PREDEFINED` rather than filling it in after results. A field that is not filled blocks the OOS gate (`research-protocol.md` §11).

## 0. Freeze record
| Field | Value |
|---|---|
| Experiment ID | `EXP-YYYYMMDD-n` |
| Family ID | e.g. F-FREQ / F-BE / new |
| Protocol version | v1.0 (`artifacts/day14/research-protocol.md`, SHA-256: ______) |
| Protocol commit SHA | ______ (must precede every results artifact) |
| Frozen at (UTC) | ______ |
| Author | ______ |
| Working tree clean at freeze | yes / no (list files) |

## 1. What information was known before this experiment?
- Prior artifacts viewed (paths): ______
- Prior observations that motivated this candidate: ______
- Provenance: PREDECLARED / DERIVED FROM PRIOR OBSERVATION / MIXED / UNKNOWN
- Family's cumulative variant count on the research window (including failures): ______
- In-sample result of the candidate after costs, with its artifact path. It must be non-negative at the cost scenario used for acceptance (`research-protocol.md` §11): ______

## 2. Hypothesis
- Statement: ______
- Rationale: ______
- Expected observable mechanism: ______

## 3. Exact rule (code identity)
- Signal module and commit: ______
- Valid setup statuses: {DETECTED, CONFIRMED} / other: ______
- All signal parameters: ______
- Filters / gates (exact): ______
- Full `ExecutionConfig` (serialised JSON): ______
- Stop: ______ Target: ______ Same-bar rule: STOP_FIRST / ______
- Forced exit: ______ Position limit: ______ Direction: long-only
- Execution-model differences from the frozen baseline: none / list. (Any difference = separate experiment, `research-protocol.md` §8.)

## 4. Parameters and variants
| Variant | Parameters | Why included |
|---|---|---|
| | | |
- Total variants: ______
- **Selection rule** (write it before data): "All listed variants are evaluated and reported; none is retained unless it meets §7." / other: ______
- Stopping rule: one OOS run; no re-runs except a documented technical failure. A re-run uses the identical frozen configuration and is reported.

## 5. Data
- Universe (exact list, frozen): ______
- OOS rule: first 60 NYSE sessions after 2026-09-25 (`data-expansion-spec.md` §3)
- Snapshot manifests (paths and digests): ______
- Merge report path: ______
- Warmup: research-window bars as indicator history only; trades only in OOS sessions
- Missing-data exclusions (rule): symbol-sessions failing the structural checks are excluded from both strategy and benchmark and listed

## 6. Costs and metrics
- Cost scenarios: 0 / 5 / 10 bps per side, formula `(1+g)(1−s)/(1+s)−1` on every exit
- Primary metric: mean net trade return at 5 bps per side
- Secondary metrics: as in `research-protocol.md` §12
- Benchmark: equal-weight per-symbol buy & hold over the same OOS sessions

## 7. Acceptance conditions (fill or mark NOT PREDEFINED)
| Criterion | Threshold | Status |
|---|---|---|
| Primary metric sign | ≥ 0 | PREDEFINED |
| Primary metric magnitude | ______ | NOT PREDEFINED unless justified here |
| Minimum OOS trades | ______ | NOT PREDEFINED unless justified here |
| Max drawdown | ______ | NOT PREDEFINED unless justified here |
| Symbol breadth (share positive) | ______ | NOT PREDEFINED unless justified here |
| Concentration (top-2 share) | ______ | NOT PREDEFINED unless justified here |
| Benchmark margin | ______ | NOT PREDEFINED unless justified here |
| Data integrity | all structural checks pass, hashes match | PREDEFINED |
| PIT mutation test | passes | PREDEFINED |
| Reproducibility block | complete | PREDEFINED |

## 8. Exclusion criteria
- ______ (e.g. sessions missing in the provider, flagged corporate-action conflicts)

## 9. Outputs
- `artifacts/<EXP-ID>/results.json` (with the `reproducibility` block), `report.txt`, `trades.csv`, `manifest_before_after.json`, test command and counts

## 10. Gate checklist (all must be YES before the OOS run)
- [ ] rule fully specified
- [ ] parameters frozen
- [ ] execution semantics frozen
- [ ] costs frozen
- [ ] selection rule committed before OOS acquisition/merge
- [ ] OOS data not inspected beyond structural checks
- [ ] no OOS-specific tuning planned
- [ ] in-sample cost-adjusted result non-negative at the acceptance cost scenario
