# DAY-27A — Protocol v2.4 Amendment: pinned historical identity alias `FB → META`

> **STATUS: ADOPTED — 2026-10-13T07:05:10Z** (decision record `artifacts/day27a/protocol-v2.4-adoption.json`). It takes effect only from the commit that contains this amendment and its adoption record, not earlier. It is append-only.
>
> These stay unchanged:
> - protocols 2.1, 2.2 and 2.3 and their adoption records;
> - the DAY-26C incident record and its quarantine;
> - the V2-MOM config (SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`);
> - the `fwd-gate2` calendar (2026-10-12 → 2026-12-09, 42 sessions), its status (PENDING) and its sample.

| Field | Value |
|---|---|
| Protocol version | **2.4** (`… + 2.1 + 2.2 + 2.3 + 2.4`) |
| Scope | Corporate-action **entity identity** only (v2.0.1 C2). No strategy, cost, calendar, sample, data-window or validation threshold changes. |
| Affects | `fwd-gate2` Stage F capture/validation; `V2-MOM-P001` paper runner; Stage H recompute (no-op, byte-identical) |

## 1. Why

v2.0.1 C2 rule 2 derives an alias only from a `name_changes` record **inside the acquired window**. `fwd-gate2` Stage F and `V2-MOM-P001` acquire from **2025-01-02** (`STAGE_F_FIRST_SESSION`, `HISTORY_START`), so the `FB → META` name change of 2022-06-09 falls outside that window.

Meanwhile the ticker `FB` was reissued to an unrelated issuer, CUSIP `74349Y613`. Cash dividends under that ticker are returned for the frozen query alias `CA_QUERY_ALIASES = ("FB",)`. With no alias and no CUSIP owner, they become `unassigned_records`. That makes the paper runner fail closed (v2.3 P5, `DataFailClosed: corporate-action identity conflicts`, 2026-10-13). The same rule (`identity_no_conflicts`) is expected to fail the `fwd-gate2` Stage F validation.

Stage H's window started in 2021 and included the name change. It classified the same records as foreign-entity records under rule 4 (`artifacts/day20/day20-holdout-acquisition-report.json:780`).

## 2. Rule A1: pinned historical alias

`acquisition/v2/contract.py: PINNED_ALIASES` holds exactly one entry:

| old_symbol | new_symbol | cusip | source record id | name_change_date |
|---|---|---|---|---|
| `FB` | `META` | `30303M102` | `ed6f16b1-fc46-443e-8dba-898ed9007a7a` | 2022-06-09 |

`identity.resolve` processes pinned aliases after record-derived aliases:

1. **Already derived from an in-window record:** the pin is a no-op. If that record maps the old ticker to a different entity, the result is conflict `pinned_alias_mismatch`, which fails closed.
2. **Applied:** only if all of these hold:
   - `new_symbol` is a Stage R entity;
   - `old_symbol` is a frozen query key;
   - the pinned CUSIP is in the entity's CUSIP set computed **from the acquired records** (rule 3 anchor and chain closure).

   Records under `old_symbol` then follow the existing rules unchanged. A CUSIP inside the set means the record is assigned. A CUSIP outside the set means rule 4: a foreign-entity record, excluded, listed, review status `RESOLVED_EXCLUDED`. An empty CUSIP with a foreign entity present means conflict (b).
3. **Not verifiable:** the pin is **not applied** and is listed in `identity.pinned_aliases_not_applied`. Records under the old ticker stay `unassigned`, which still fails closed. An unverifiable pin is not itself a conflict, so a window without any such records is not blocked.
4. `identity.pinned_aliases_applied` / `pinned_aliases_not_applied` are emitted only when non-empty. Snapshots whose window contains the name change therefore recompute byte-identically.

No other alias may be pinned without a further amendment. No record is dropped, no corporate action is skipped, and no validation is relaxed. Unassigned records and every conflict still fail closed in paper P5 and in the Stage F/H `identity_no_conflicts` check.

## 3. Evidence (pre-forward, pinned)

| Snapshot | manifest.json SHA-256 | Pinned in |
|---|---|---|
| Stage R `data/oos_cache/protocol_v2/stage_r/stage_r_20261007T093410Z/` | `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` | `artifacts/day18/day18-stage-r-report.json`, `artifacts/day18a/protocol-v2.0.2-amendment.json` |
| Stage H `data/oos_cache/protocol_v2/stage_h/stage_h_20261008T100604Z/` | `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34` | `artifacts/day20/day20-holdout-acquisition-report.json`, `artifacts/day20a/…`, `artifacts/day22/…` |

`corporate_actions_complete.json`, identical to `corporate_actions_all.json`, matches each manifest:
- Stage R `268b3a2c2ea8b4164e6e4488a06680fdf8dd7ab56e8e0be0ad5700e80d0ed8e9`
- Stage H `9e54583c2b3a579d368ca4cd0f8e61ef10bfd0e34d4da0a640618e38f89c35b8`

Both contain the source record, byte-identical in content:
`{"ca_type":"name_changes","event_date":"2022-06-09","process_date":"2022-06-09","id":"ed6f16b1-fc46-443e-8dba-898ed9007a7a","old_symbol":"FB","old_cusip":"30303M102","new_symbol":"META","new_cusip":"30303M102"}`.

In Stage H, `identity.json` (`d0ce3264fce0e479022c94b70ef1c1e61f80a27b0d0cefbabd317ac5dab41924`) has `aliases = {"FB":"META"}` and META's CUSIP set is `["30303M102"]`. FB dividends `1ab26fcd…`, `dd73e539…` and `282f080d…` (CUSIP `74349Y613`) are `foreign_entity_records`. All 9 META dividends carry `30303M102`.

## 4. Evidence disclosure

The failure was diagnosed on 2026-10-13 with an in-memory, **corporate-actions-only** fetch, using the paper runner's guarded data client and its exact window: process dates 2025-01-01 → 2026-10-12, event dates 2025-01-02 → 2026-10-12. No bars, prices or performance were fetched or computed, and nothing was written to disk. It returned 146 records: 141 assigned by CUSIP, and 5 unassigned FB/`74349Y613` dividends with event dates 2025-09-24, 2025-12-24, 2026-03-25, 2026-06-24 and 2026-09-23, all before `fwd-gate2` session 1.

This amendment is justified by the pre-forward Stage R/H evidence in §3. It does not depend on any forward observation.

## 5. Guards

From adoption onwards:
- `fwd-gate2` access (`backtest/v2/forward.py: check_forward_access`) requires `check_adoption_24`, which checks the v2.4 pins and commit and then the 2.2 → 2.1 chain.
- The paper runner (`paper/runner.py: check_adoption_23`) requires the same chain.

Adoption must be committed before the `fwd-gate2` Stage F capture, which is not before 2026-12-09 16:15 America/New_York.

## 6. Verification required before adoption

- `tests/test_day27a_identity_pin.py` (18 tests) passes. The existing Stage R/H, gate2, paper and incident suites pass, except the gate2 "all guards pass when committed" test. That test passes only once this amendment and its adoption record are committed, which is intended.
- Stage H `identity.json` recompute stays byte-identical.
- The pin never assigns a non-`30303M102` record to META.
