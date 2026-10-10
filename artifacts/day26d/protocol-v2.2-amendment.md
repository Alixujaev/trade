# DAY-26D — Protocol v2.2 Amendment: Retire the Legacy-Cache Preflight Dependency; Clean 42-Session Gate `fwd-gate2`

> **STATUS: ADOPTED — 2026-10-10T14:56:30Z** (decision record `artifacts/day26d/protocol-v2.2-adoption.json`).
> It takes effect from the commit that contains this amendment and its adoption record, not earlier. It is append-only: the protocol 2.1 files, their adoption record and the DAY-26C incident record are not modified. Machine-readable twin: `protocol-v2.2-amendment.json`. Calendar values come from `scripts/day26d_gate_calendar.py` and are checked by `tests/test_day26d_gate2.py`.

| Field | Value |
|---|---|
| Protocol version | **2.2** (`2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 + 2.1 + 2.2`) |
| Authorisation | Explicit protocol-owner instruction "DAY-26D — RESOLVE BLOCKERS, COMMIT, START A CLEAN FORWARD GATE" (2026-10-10) |
| New gate | **`fwd-gate2`**: experiment **`V2-MOM-F003`**; benchmarks `V2-B1-fwd-gate2`, `V2-B2-fwd-gate2` |
| Sample | **42 XNYS sessions, 2026-10-12 → 2026-12-09** |
| Earliest capture and evaluation | **2026-12-09 16:15 America/New_York (EST, UTC−05:00) = 21:15 UTC** |
| Strategy | V2-MOM unchanged; config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0` |

## 1. Disclosures

1. **The DAY-15 legacy cache is unrecoverable.** The 305 frozen files under `data/cache` (`artifacts/day15/integrity-baseline.json`) were searched for on 2026-10-10 in:
   - git history (all refs);
   - the research-data vault (release `protocol-v2-historical-v1` holds only stage_r, stage_h, evidence and the manifest; the DAY-26 report says `data/cache` was intentionally not vaulted);
   - local disks (Desktop, Downloads, Documents, six folder levels).

   The only candidate, `trade/smc-scanner/data/cache`, matched **0/305** SHA-256. No replacement was downloaded or regenerated.
2. **`fwd-diag` stays `FWD-DIAG-INVALID (protocol-breach)`** (DAY-26C). This is final, and it is never relabelled.
3. **The old `fwd-gate`** (2026-11-06 → 2027-01-07) is **`SUPERSEDED (protocol 2.2)`**. It was never acquired or evaluated.
4. The 54 DAY-26C incident files stay quarantined outside every active data path. Their SHA-256 inventory is enforced in code (`check_quarantine`).

## 2. Decisions

| ID | Decision |
|---|---|
| **D1** | **Stage F preflight without the legacy cache.** The Stage F capture preflight (`acquisition/v2/stage_f.preflight`) no longer requires DAY-15 `data/cache`. Every other DAY-15 frozen directory (`artifacts/day04` … `artifacts/day14`) is still enforced: the file set must be identical, and each file must equal its baseline SHA-256 up to line endings only (raw, LF- or CRLF-normalised; DAY-25B precedent, because the baseline itself mixes LF and CRLF files). Retained: forward access checks, a clean git tree, frozen protocol identity, the unchanged v2.0.4 amendment, and the committed DAY-20 decisions. |
| **D2** | **New clean gate `fwd-gate2`.** First XNYS session strictly after the DAY-26D commit day, then 42 consecutive sessions. The §13 gate (A/B/C) is applied unchanged, once, after the final session. Labels: `FORWARD42-PASSED`, `FORWARD42-FAILED (economic \| methodological \| incomplete)`, `FORWARD42-INVALID (protocol-breach)`, `FORWARD42-ABANDONED`. `FORWARD-PASSED` and "validated under v2" are not available. |
| **D3** | **Sample separation.** 2026-10-08 and 2026-10-09 (exposed in DAY-26C), and every earlier session, are never part of the `fwd-gate2` sample. They are formation history only, read mechanically by the frozen rules. The invalid `fwd-diag` never enters `fwd-gate2` metrics or benchmarks. Warm-up and lookback data come only from the single fresh Stage F acquisition (D4), never from quarantined files. |
| **D4** | **Fresh, immutable snapshot.** One Stage F acquisition for `fwd-gate2` (`stage_f_fwd-gate2_<UTC>`), covering 2025-01-02 → 2026-12-09: Alpaca SIP raw and `all` bars plus corporate actions. It is write-once and read-only, with its own manifest and per-file SHA-256. Offline validation must return `READY_FOR_FORWARD_EVALUATION`. The loader and validator refuse a writable snapshot. Acquisition parameters are as in the v2.1 adoption record: asof = last session; CA Q1 process_date [2025-01-01, 2026-12-09]; event_date boundary [2025-01-02, 2026-12-09]; no assets endpoint. |
| **D5** | **Invariants.** Unchanged: V2-MOM rules and parameters (config SHA above); `FROZEN_DAY_UNIVERSE` (25 stocks) + SPY; B1 equal-weight buy-and-hold and B2 SPY; market-on-open t+1 at the raw open; costs 0/5/10 bps (5 primary); §13 thresholds; the §7 no-lookahead tests; E_0 = 100,000, starting flat and liquidating at the last close. |

## 3. Declared calendar (before any gate data exists)

| Item | Value |
|---|---|
| Sessions | 42: 2026-10-12 → 2026-12-09 (holiday 2026-11-26; early close 2026-11-27 at 13:00) |
| Exposed sessions in the sample | none (2026-10-08 and 2026-10-09 excluded) |
| First ranking | Close of **2026-10-09** (§8.14). It reads TR closes of 2026-09-10 (t−21) and 2025-10-08 (t−252); bar t itself is not used. |
| First fills | Open of **2026-10-12** |
| Month-end decision 1 | Close of 2026-10-30, executed at the 2026-11-02 open (reads 2026-10-01 and 2025-10-29) |
| Month-end decision 2 | Close of 2026-11-30, executed at the 2026-12-01 open (reads 2026-10-29 and 2025-11-26) |
| Final session / liquidation | Close of **2026-12-09** |
| Stage F range | 2025-01-02 → 2026-12-09: 486 sessions, of which 444 are lookback before the sample |
| Earliest capture | **2026-12-09 16:15 America/New_York = 2026-12-09 21:15 UTC** |
| Earliest final evaluation | After a successful capture and `READY_FOR_FORWARD_EVALUATION` validation, never before the earliest capture time |

The full 42-session list is in the JSON `calendar.sessions`.

## 4. Acquisition schedule

| Step | When | Command / action |
|---|---|---|
| now | Commit | The gate's sessions begin on 2026-10-12. Nothing is acquired, computed or inspected during the blind period. |
| S7 | ≥ 2026-12-09 16:15 America/New_York | `python -m acquisition.v2.stage_f --capture --segment fwd-gate2 --authorization <reference>` |
| S8 | After S7 | `python -m acquisition.v2.stage_f --validate <stage_f_fwd-gate2_snapshot> --segment fwd-gate2 --expect-manifest-sha256 <sha>` |
| S9 | After `READY_FOR_FORWARD_EVALUATION` | `python -m backtest.v2.run --segment fwd-gate2 --out artifacts/day27/v2 --snapshot <id> --expect-manifest-sha256 <sha> --authorization <reference>` |

## 5. Segment status

| Segment | Status |
|---|---|
| `fwd-diag` | `FWD-DIAG-INVALID (protocol-breach)` |
| `fwd-gate` | `SUPERSEDED (protocol 2.2) — never acquired or evaluated` |
| `fwd-gate2` | `PENDING — blind, not evaluated` |

## 6. Enforcement (fail-closed)

`backtest/v2/forward.check_forward_access` and `acquisition/v2/stage_f.preflight` refuse, before any data path, credential or client is touched, unless all of the following hold:
- the segment status is PENDING;
- the time is at or after the segment's earliest capture time;
- the v2.2 and v2.1 adoption records are ADOPTED, their pinned SHA-256 values match, and they are committed unchanged (the DAY-26C incident record included);
- the V2-MOM config SHA is unchanged;
- the calendar gives exactly the declared 42 sessions with no exposed session;
- no quarantined file is in any data path.

The capture preflight additionally checks the DAY-15 baseline (D1), a clean tree, the protocol identity, v2.0.4 and DAY-20.

## 7. Evidence disclaimer

A 42-session forward gate is weak long-term evidence. It does not by itself authorise real-money trading.

## 8. Implementation

- `acquisition/v2/contract.py`: the `fwd-gate2` window, the expected Stage F session count (486), `EXPOSED_SESSIONS`, `PROTOCOL_VERSION_22`.
- `backtest/v2/forward.py`: effective segment status, `check_adoption_22`, `check_config_sha`, `check_segment_calendar`, `check_snapshot_immutable`.
- `acquisition/v2/stage_f.py`: `preflight()` (D1), `frozen_baseline_check`, `eol_equivalent_sha`; validation refuses a mutable snapshot.
- `backtest/v2/data.py`: `load_stage_f` refuses a mutable snapshot.
- `backtest/v2/run.py`: `SEGMENTS["fwd-gate2"]`; protocol version per segment.
- `scripts/day26d_gate_calendar.py`, `tests/test_day26d_gate2.py`.
