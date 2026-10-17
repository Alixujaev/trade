# Strategy evidence inventory: 2026-10-17

This is a read-only consolidation of evidence already in the repository. No experiment was run, no artifact
was modified, and no sealed forward-test data was opened.

**Labels used in this report:**
- **FACT:** quoted or read directly from the cited file.
- **OBS:** an observation across files.
- **INF:** an inference.
- **REC:** a recommendation.
- **NOT FOUND:** no repository evidence located.

## 1. Repository state

| Item | Value |
|---|---|
| Working directory | `C:/Users/Admin/Desktop/own/trade` |
| Branch | `feature/day-trading-research` (3 commits ahead of `origin`, 0 behind) |
| HEAD | `f6d628692f2faa35e41df7e1c59dd1e8d98851e8`, "ORB paper runner: enforce Sharia eligibility gate before market data" (2026-10-17) |
| Working tree before this report | Clean: nothing staged, no untracked files |
| Recent commits | `f6d6286`, `b81cbfc`, `7a9b939` (2026-10-17: eligibility gate, Akinda, screening policy); `e935d07`…`eb87c88` (2026-10-13 to 16: ORB) |

## 2. Search scope and method

- **Directories checked:**
  - all 50 `artifacts/*` directories, with their last-commit dates (most `day04`–`day18h` were bulk-committed on
    2026-10-07; `day19` and later between 2026-10-08 and 10-16);
  - `artifacts/orb/`, `artifacts/reviews/`, `reports/`, `experiments/`, `docs/shariah/`;
  - every tracked `.md` and `.txt` file outside `artifacts/`;
  - forward-test protocols and adoption records;
  - the paper runner's **health metadata only**.
- **Read method:** files were read with `grep`, `sed` and read-only JSON and CSV parsing. Nothing was written
  except this report.
- **Not used as repository evidence:**
  - the root CSVs (`backtest_results.csv`, `portfolio_backtest_results.csv`, `breakout_retest_results.csv`) are
    git-ignored and untracked (`git ls-files` → 0);
  - analyses done in chat sessions but not saved (section 7).

## 3. Inventory of key reports and artifacts

| Area | Path | Date | Role |
|---|---|---|---|
| Intraday VWAP | `artifacts/day13/research-synthesis.md`, `oos-gate.md`, `research-matrix.json` | 2026-10-07 commit | Synthesis of DAY-01 to DAY-12B and the out-of-sample gate decision |
| Intraday VWAP | `artifacts/day15/day15h-alpaca-rebaseline.md` / `.json`, `protocol-v1.1.md` | 2026-10-07 commit | Re-baseline on SIP data under protocol v1.1 |
| ORB | `artifacts/orb/smoke_test/`, `diagnostics/`, `diagnostics_v2/`, `sip_diagnostic*/`, `sip_diagnostic_decision.md`, `provenance_correction.md` | 2026-10-13 to 16 | Smoke test and diagnostics |
| V2 protocol | `artifacts/day16/research-protocol-v2.md` | 2026-10-07 commit | Segments, gates, metrics, limitations (Q5, Q11) |
| V2 research | `artifacts/day19/day19-research-report.md`, `day19-protocol-owner-signoff.md`, `day19/v2/*` | 2026-10-08 | Research gate |
| V2 holdout | `artifacts/day21/day21-historical-holdout-report.md`, `day21/v2/*/{0,5,10}bps/` (daily `equity.csv`, `fills.csv`, `episodes.json`, `metrics.json`) | 2026-10-08 | Historical holdout |
| V2 governance | `artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md` | 2026-10-08 | Post-holdout status |
| V2 forward design | `artifacts/day23/…`, `artifacts/day24/…` (superseded) | 2026-10-08 | Forward-duration audit and proposal |
| V2 robustness | `artifacts/day25/day25-robustness-report.md` | 2026-10-08 | Parameter, universe and rolling-window study (not predeclared) |
| V2 robustness | `artifacts/day25b/day25b-robustness-predeclaration.md`, `run/d1.json`–`d7.json`, `run_summary.json` | 2026-10-10 | Predeclared descriptive diagnostics D1–D7 |
| Forward protocols | `artifacts/day26b` (v2.1), `day26c` (incident), `day26d` (v2.2), `day27` (v2.3), `day27a` (v2.4), `day27b` (v2.5 draft) | 2026-10-10 to 14 | Forward gates, the seal, the incident |
| Legacy daily | `reports/run_log.txt`, `reports/exit_research_full.csv`, `experiments/*.json` (18 files) | 2026-10-07 commit; runs 2026-09-04 | Exit and selection research |

## 4. Strategy evidence matrix

| Strategy | Latest evidence | Test type | Universe / period | Performance | Robustness | Gate / status | Limitations | Conflicts |
|---|---|---|---|---|---|---|---|---|
| **Intraday VWAP momentum** (DAY-01 signal, DAY-02 execution) | `day13/oos-gate.md:5`; `day15h-alpaca-rebaseline.md:3` | In-sample; SIP re-baseline | 25 symbols; 2026-07-02 → 09-25 (60 sessions), 5m bars | yfinance: 5,691 trades, PF 0.9388, −738.98R, 5 bps compounded −99.80% (`research-synthesis.md:55,99`). SIP: WR 30.22%, PF 0.944, mean net trade at 5 bps −0.1076% (`day15h:75-76,148`) | None of 38 variant rows non-negative at 5 or 10 bps; best mean gross trade +0.0288% against a round trip of about 0.10% (`:95,113-115`) | **DAY-13 OOS gate: NO** (no candidate qualified). **DAY-15H research gate: FAIL**; no OOS data acquired | One 60-session window reused across 40 variants; no predeclaration for DAY-06 to 12; 50.4% single-bar trades; optimistic stop fills | DAY-07A and DAY-08B text vs tables (resolved in DAY-13 `:42-49`) |
| **ORB** (`strategy/day/orb.py`, `orb_rules.py`) | `orb/sip_diagnostic_decision.md:71-73`; `orb/diagnostics_v2/sip_availability.md:101`; `orb/sip_diagnostic/metrics.json` | Smoke test and diagnostics (same sample) | 25 symbols; same 60 sessions; yfinance and SIP | yfinance: 95 trades, WR 48.42%, net −1.43%. SIP: 101 trades, WR 48.51%, net −1.54%, total R −6.22; exits STOP 13 / TARGET 0 / FORCE 88; costs included; equal-weight buy-and-hold +4.66% | Exit replays all negative; feature screens exploratory | **No formal gate.** "Not evidence of an edge" (`smoke_test/report.md:6`); "not independent evidence and not strategy validation"; **"Ready for the next ORB test: no"** | Same sessions as VWAP; small n; no corporate-action data; rules and results in one commit (`eb87c88`); predeclaration NOT FOUND | Data source mislabelled IEX, corrected to yfinance (`provenance_correction.md`) |
| **V2-MOM** (252/21 momentum, top 5 at 20%, monthly) | `day19…:48,160`; `day21…:19,45,53,67,73`; `day22…:8,118`; `day25b/run/*.json` | Research; historical **pseudo-OOS** holdout; forward test pending | 25 hindsight-selected mega caps. Research 2017-02-01 → 2022-12-30 (1,490 sessions); holdout 2023-01-03 → 2026-06-02 (856) | Research 5 bps CAGR **28.82%** vs B1 18.44%; max DD 36.0%; 435 trades. Holdout **71.25%** vs B1 **53.24%** (+18.01 pp); max DD 26.9%; 253 trades; cost drag 0.53 pp | HAC t 1.38, **p 0.166** (not significant). Top-2 share of P&L 0.43. Trails B1 in 2023 and 2025. D1: all 25 leave-one-out runs positive. D2: holdout +10.75 pp vs B1-sub / +0.56 pp vs B1. D4c: holdout excluding 2026 −2.55 pp (spliced). D5: top-1/2/3/5 share 26/43/58/77% | **RESEARCH-PASSED · HOLDOUT-PASSED · FROZEN FOR FORWARD OOS**; `fwd-gate2` **PENDING** | Survivorship (Q5); holdout not blind (protocol `:168`); low power (Q11); data reused across 680 D-runs | C1–C5 |
| **V2-STR** (5-day reversal) | `day19…:51,96`; `day21…:22,46,54`; `day22…:8,119` | Research; holdout | Same | Research 24.98%; holdout **22.19% vs B1 53.24%**; cost drag 5.04 pp at 5 bps | HAC t −2.05, p 0.040 (Holm 0.080) | **RESEARCH-PASSED → HOLDOUT-FAILED (economic) → STOPPED** | Very cost-sensitive (turnover about 40× per year) | none found |
| **V2-LRV** | `day19…:54,97,162`; `day22…:8` | Research | Same | 13.34% < B1 18.44% | NOT FOUND (not run further) | **RESEARCH-FAILED (economic) → STOPPED**; never run on the holdout | | none found |
| **Legacy daily** (SMC / exit models / selection) | `reports/run_log.txt:21-29`; `experiments/*.json` | In-sample research (no protocol) | Daily yfinance universe; OOS from 2023 per run log; details partly NOT FOUND | Six exit models, all "INCONCLUSIVE (baseline low sample)"; **"NO SELECTION EDGE"** (Selection-BH Sharpe 0.915 vs equal-weight 1.456, 182 trades); **"NO EXIT EDGE FOUND"** | NOT FOUND | **No formal gate → INSUFFICIENT EVIDENCE**; documented findings negative or inconclusive | Low sample; no predeclaration; results CSVs untracked | C8 |

**Next steps justified by the evidence:**
- **VWAP momentum:** none without a new, separately approved protocol and non-overlapping data.
- **ORB:** none until new non-overlapping data, a source-verified earnings calendar and rules frozen in advance
  (`sip_availability.md:101`).
- **V2-MOM:** wait for the `fwd-gate2` evaluation, not before 2026-12-09 16:15 ET.
- **V2-STR and V2-LRV:** none. Both are stopped, with no rerun or rescue (§15.10).
- **Legacy daily:** none. No candidate qualifies.

## 5. Metric and status conflicts

| # | Conflict | Sources | Status |
|---|---|---|---|
| C1 | Research CAGR stated as **28.22%** in DAY-25 against the official **28.82%** | `day25/day25-robustness-report.md:43` ("official DAY-19 research CAGR is 28.22%") vs `day19/day19-research-report.md:48,160` | **UNRESOLVED.** INF: probably a transcription error; DAY-25's own reference run is 28.17% (`:39,178`). |
| C2 | DAY-25 reference run vs official reports: MOM **28.17% / 71.54%** vs 28.82% / 71.25%; B1 **18.40% / 53.88%** vs 18.44% / 53.24% | `day25…:39-40,178-179` vs `day19…:48`, `day21…:19,30` | **UNRESOLVED.** DAY-25 attributes the gap to "absence of the in-process determinism second-pass" (`:43`); that explanation is not verified. The official values are the DAY-19 and DAY-21 gate harness outputs. |
| C3 | DAY-25 verdict "**broad pre-forward robustness** … genuine cross-regime persistence" vs DAY-21 §8 "excess uneven by year and concentrated in a few symbols" and DAY-25B D4c (holdout excluding 2026 → −2.55 pp) | `day25…:204-210` vs `day21…:99-102`, `day25b/run/d4.json` | **Interpretive disagreement.** DAY-25B is later, predeclared and descriptive; DAY-25 was not predeclared. Both kept. |
| C4 | Removing the top two contributors leaves **+0.56 pp** or **+10.75 pp** (holdout, 5 bps) | `day25b/run/d2.json` (`active_vs_b1` vs `active_vs_b1_sub`) | **Explained by the comparator:** the predeclared primary comparator is B1-sub (predeclaration `:44`). Both are outcome-dependent stress tests. |
| C5 | The DAY-25B predeclaration banner reads "**FROZEN — NOT AUTHORIZED TO RUN**", yet `run_summary.json` is `COMPLETED` with `"authorization": "DAY25B-D1-D7-RUN"` | `day25b-robustness-predeclaration.md:5`; `run/run_summary.json:2,79` | **UNRESOLVED (documentation).** A separate authorization record was NOT FOUND. |
| C6 | `sip_availability.md` says the SIP snapshot was used for the "DAY-15H **V2-MOM** re-baseline"; DAY-15H re-baselines the **DAY-04 VWAP** baseline | `orb/diagnostics_v2/sip_availability.md:20` vs `day15/day15h-alpaca-rebaseline.md:1` | Mislabel in the ORB document; DAY-15H's title is authoritative. |
| C7 | Forward window of **252 sessions** (2026-10-08 → 2027-10-08) vs the **42-session `fwd-gate2`** | `day21…:107`, `day22…:9` vs `day26b/protocol-v2.1-amendment.md:26,39`, `day26d/protocol-v2.2-amendment.md:10-12` | **Resolved by later adopted amendments** (2.1 adopted 2026-10-10T12:52:51Z; 2.2 adopted 2026-10-10T14:56:30Z). |
| C8 | Legacy exit-research verdicts differ between batches: "ALPHA: exit value qo'shdi" (7), "NO EDGE" (4), "INCONCLUSIVE" (7) | `experiments/20260904_{072530,093838,110549}_*.json` (commits `5651b10`, `a406a17`) vs `reports/run_log.txt:21-29` | **UNRESOLVED.** OBS: the latest batch (110549) is all INCONCLUSIVE and matches the run log. The earlier "ALPHA" verdicts were not reproduced. |
| C9 | DAY-21 artifacts label 2026 (to 06-02) as a "full" year | `day21…:95` (deviation P1) | Documented as cosmetic. |

## 6. Forward-test status and protocol restrictions

**Status: running, with evaluation PENDING. No results recorded.**

- **Gate:** `fwd-gate2`, experiment `V2-MOM-F003`, covering **42 XNYS sessions from 2026-10-12 to 2026-12-09**.
  - Earliest capture and evaluation: **2026-12-09 16:15 America/New_York** (`day26d/protocol-v2.2-amendment.md:10-12`).
  - The §13 gate is applied once, after the last session, with outcomes labelled `FORWARD42-*`.
- **Documented status:** PENDING (`day27a/protocol-v2.4-amendment.md:9`; `day27b/protocol-v2.5-amendment.md:8`).
  - FACT: no Stage F directory exists under `data/oos_cache/protocol_v2/` (directory listing only).
  - INF: on 2026-10-17 the sample period is in progress, about the 5th of 42 sessions.
- **Other segments:**
  - `fwd-diag` is **FWD-DIAG-INVALID (protocol-breach)**, final (`day26c…:67`, `day26d…:23`);
  - the old `fwd-gate` is **SUPERSEDED** (`day26d…:24`).
- **Sealed paper experiment `V2-MOM-P001`:**
  - the ledger is encrypted until 2026-12-09 16:15 ET (`day27/protocol-v2.3-amendment.md:13`);
  - **any decryption or disclosure before then is a protocol breach that makes `fwd-gate2`
    `FORWARD42-INVALID`** (`:26`, P4).
  - Health metadata: 1 processed session (`2026-10-12`), last run 2026-10-13T08:15:32Z, 1 sealed file.
  - Whether it runs anywhere else is UNCONFIRMED.
- **Rule against early inspection:** "Nothing from them is acquired, computed, inspected, monitored or visualized
  before the end" of the gate sessions (`day26b/protocol-v2.1-amendment.md:46`).
- **Protocol versions:**
  - v2.4 is ADOPTED (`day27a/protocol-v2.4-adoption.json`: `final_status: ADOPTED`);
  - v2.5 is `PROPOSED_NOT_ADOPTED` (`day27b/protocol-v2.5-adoption.json`).
- **This report:** no forward or sealed data was opened.

## 7. Evidence produced outside the repository

**This is NOT repository evidence.** On 2026-10-17, a read-only chat session analysed the saved DAY-21 holdout
daily equity (`day21/v2/V2-MOM-H001/5bps/equity.csv` and `V2-B1-holdout/5bps/equity.csv`) and reported:

- **Total:** a net additive active contribution of +1.954. That is (E_MOM − E_B1) / 100,000, equal to the
  +195.4 pp total-return difference.
- **Best days:** the 10 largest positive days (9 of them in 2026) sum to +2.125, so the remainder is −0.171.
- **April–May 2026:** these two months contribute +1.939.

These results are not saved as an artifact. They should be treated as an unpersisted observation until they are
reproduced and recorded.

## 8. Overall assessment

- **FACT: no strategy is validated by forward evidence.**
- **FACT: V2-MOM is the only active candidate.** It passed research and a historical pseudo-OOS holdout that
  was not blind (DAY-21 §8). Its edge over B1 is not statistically significant (p 0.166).
- **OBS: V2-MOM's holdout advantage is concentrated.**
  - By symbol: the top two account for 43% of P&L, although the edge survives against B1-sub.
  - By period: excluding 2026 makes it negative (D4c), and the unpersisted analysis in section 7 points to April
    and May 2026.
- **OBS: no intraday strategy survived.**
  - VWAP momentum failed its research gate.
  - ORB has no evidence of an edge and is not ready for another test.
  - V2-STR and V2-LRV are stopped.
  - The legacy daily work found no edge or was inconclusive.
- **FACT: none of these results is Sharia-screened.** The eligibility registry is header-only, and day-trading
  permissibility (D12) needs an adviser (`docs/shariah/AAOIFI_MVP_DECISIONS.md:42`).

## 9. Remaining information gaps

1. Forward evidence for V2-MOM: none until 2026-12-09.
2. The daily-concentration analysis is not saved in the repository (section 7).
3. The effect of removing three or more tickers would need a re-simulation (NOT FOUND).
4. The authorization record for the DAY-25B run (C5) was NOT FOUND.
5. Whether the paper runner operates outside this machine is UNCONFIRMED.
6. There is no non-overlapping intraday dataset for VWAP or ORB.
7. Legacy daily results are only in untracked CSVs and inconsistent experiment JSONs (C8).
8. There is no point-in-time universe; survivorship bias is unsolved (Q5).

## 10. Recommended next decision

**REC:** the owner decides to **hold all new strategy research and experiments until the `fwd-gate2` evaluation
(not before 2026-12-09 16:15 ET), keeping V2-MOM as the only active candidate.** This is supported by:

- **No intraday candidate qualifies for further validation**, and none can without new non-overlapping data:
  `day13/oos-gate.md:5`, `day15h…:3`, `orb/diagnostics_v2/sip_availability.md:101`.
- **V2-MOM's decisive evidence is the blind forward gate**, which must not be inspected early:
  `day22…:8`, `day26d…:10-12`, `day27…:26`.
- **The historical evidence is not significant and is concentrated:** `day21…:53,67`, `day25b/run/d4.json`.

The only optional low-cost action before then is to persist the section 7 daily-concentration result as a dated,
descriptive artifact, with owner approval. It cannot change any status.
