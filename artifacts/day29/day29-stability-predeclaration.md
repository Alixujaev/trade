# DAY-29: V2-MOM active-day and ticker-recurrence stability diagnostics (predeclaration)

| Field | Value |
|---|---|
| Status | **FROZEN — NOT AUTHORIZED TO RUN** |
| Freeze | Frozen 2026-10-19 on owner approval of the methodology. Approved pre-freeze content SHA-256 (LF-normalised, §14): md `15c6a2e8ada173193bdce042008be9812c6997e3a01dfc9c533c71e2ad3b9a0c`. The only change from the approved content is this status and freeze record. The frozen file's SHA-256 is recorded in the freeze commit message (a file cannot contain its own hash). Any later change requires a new, separately approved version. Freezing does not authorize any implementation or run (§15). |
| Nature | **New DAY-29 document.** It is not a recovery or reconstruction of the DAY-28 supersession artifacts (`artifacts/day28/day25-supersession.md`, `artifacts/day28/day25-supersession-adoption.json`, commits `b0c06ebb…`, `ef0cdac9…`), which are absent from this repository, its reflogs and every ref advertised by `origin` (audits of 2026-10-19). It is also not a reconstruction of the earlier DAY-29 draft reported with SHA-256 `7af41cca…`, whose content is unavailable. |
| Drafted | 2026-10-19 on `feature/day-trading-research` at HEAD `f4a9743a8565004a07bd9272797f232d20d1b89a` |
| Family | V2-MOM, compared with B1 only |
| Authoritative form | **This Markdown file.** No JSON twin (owner decision, §12 A8). |
| Protocol label | **DERIVED FROM PRIOR OBSERVATION** (protocol v2 §14, as used by DAY-25B). Drafted after the DAY-19, DAY-21, DAY-25 and DAY-25B results had been published. |
| Evidence label | Every output carries: *"robustness diagnostic on reused historical data — not independent or forward evidence"* (DAY-25B wording). |
| Scope | T0–T3 and K1–K3 (§5, §6). No diagnostic may be added after approval. |

**Drafting constraints observed:** no diagnostic, test, backtest, simulation or data acquisition was run, and no performance number was computed or read for this draft. The drafting audit read source code, document text, file listings and JSON key names. It compared SHA-256 hashes of the 48 input files with their pins (§2), which reads file bytes but extracts no values. No F003, `fwd-gate2`, P001 or other sealed evaluation artifact was opened. No existing file was modified.

**Evidence classes used below:** **[V]** verified in the repository during the drafting audit, with a file reference; **[A]** decision previously approved by the owner (§12); **[C]** drafting choice decided by the owner on 2026-10-19 (§12); **[U]** unresolved (§12).

---

## 1. Why this exists and what it can and cannot do

DAY-19, DAY-21 and DAY-25B describe V2-MOM's result relative to B1 at the level of segments, years, symbols and universe subsets. DAY-29 asks two narrower descriptive questions:

1. **Active-day concentration (T0–T3):** how much of the daily active log return comes from a few sessions, and how the paired result looks when those sessions are removed.
2. **Ticker recurrence (K1–K3):** how often the same tickers are selected and held, using the existing decision, episode, fill and equity records.

Binding constraints:

1. **All outputs are descriptive.** No output carries a threshold, pass/fail rule, label, p-value or confidence interval. Nothing in DAY-29 changes V2-MOM's status, any gate, the forward plan, strategy selection, trading rules, risk limits, Sharia status, F003 or P001.
2. **Existing artifacts only.** No strategy is re-simulated, no market data is read, and no new data is acquired. Every input is a committed DAY-19 or DAY-21 artifact listed in §2.
3. **Nothing frozen changes.** `backtest/v2/*`, `artifacts/day16/*`, `artifacts/day19/*`, `artifacts/day21/*` and `artifacts/day25b/*` are read-only inputs.
4. **Reused historical data.** The research and holdout segments have both been evaluated before; the holdout is not blind. Only a genuinely prospective evaluation is independent evidence.

---

## 2. Inputs (verified)

**[V]** All paths below exist. Each file's raw SHA-256 equals its pin in the segment's `run_summary.json` → `result_files_sha256` (checked 2026-10-19; 48/48 files, no CR bytes). Each `run_summary.json` raw SHA-256 equals `run_summary_sha256` in the sibling `run_provenance.json`.

| Segment | Series | Primary (5 bps) | Secondary (10 bps) |
|---|---|---|---|
| Research (DAY-19) | V2-MOM | `artifacts/day19/v2/V2-MOM-R001/5bps/` | `artifacts/day19/v2/V2-MOM-R001/10bps/` |
| Research (DAY-19) | B1 | `artifacts/day19/v2/V2-B1-research/5bps/` | `artifacts/day19/v2/V2-B1-research/10bps/` |
| Holdout (DAY-21) | V2-MOM | `artifacts/day21/v2/V2-MOM-H001/5bps/` | `artifacts/day21/v2/V2-MOM-H001/10bps/` |
| Holdout (DAY-21) | B1 | `artifacts/day21/v2/V2-B1-holdout/5bps/` | `artifacts/day21/v2/V2-B1-holdout/10bps/` |

Each directory contains exactly `decisions.json`, `episodes.json`, `equity.csv`, `executions.json`, `fills.csv`, `metrics.json` **[V]**. Pins and segment definitions come from `artifacts/day19/v2/run_summary.json` and `artifacts/day21/v2/run_summary.json` **[V]**.

**Record semantics [V]**, from the code that wrote the files (`backtest/v2/run.py:359-373`, `backtest/v2/engine.py`, `backtest/v2/metrics.py`):

| File | Content and meaning |
|---|---|
| `equity.csv` | Header `session,equity,exposure,n_held`; one row per segment session (`run.py:371-373`). `equity` is E(k) at the close of session k; **the last row is post-liquidation E_T** (`engine.py:139`, `251-254`). `n_held` is the number of symbols with non-zero shares at that close (`engine.py:155-164`). Floats are written with Python `repr` (full precision, `run.py:120-125`). **There is no row for E_0**: E_0 = 100,000 is the engine constant `engine.E0` (`engine.py:25`). |
| `decisions.json` | List of `{"close": "YYYY-MM-DD", "targets": {ticker: weight}}` or `{"close": …, "discarded": reason}` (`engine.py:177`, `228`, `231`). `close` is a **session date with no time of day and no time zone**. A decision is made at that session's close, **after** that close's holdings and equity are recorded (`engine.py:225-229`), and executed at the next session's open. The first decision is at the session before the segment's first session (`signals.py:35-38`, §8.14). |
| `episodes.json` | List of `{"ticker", "start", "end", "outflow", "inflow", "final_net_mark"}` (`engine.py:101-103`, `92-95`, `127`). An episode starts at the open of a buy from zero shares and ends at the open of the sell that brings shares to exactly 0 (`engine.py:85`, `92-95`). For a position still open at the segment end, `end` is `"<last session> (segment end)"` (`engine.py:119-130`). Partial resizes do not end an episode. |
| `fills.csv` | Header `session,ticker,side,shares,price,notional,cost,lambda,slot` (`run.py:367-370`). Fills occur at the raw open. Empty field = `None`. Split adjustments to held shares (`engine.py:62-65`) are **not** recorded in `fills.csv`. |
| `executions.json` | One record per session with at least one fill: `session`, `E_open`, `turnover`, `lambda`, `fills` (`engine.py:211-213`, `222-224`). |
| `metrics.json` | Frozen §12 metrics. Used here only for exact-equality checks and for copying `cagr` (`metrics.py:86-89`, `158-160`). |

**Missing or substituted inputs:** none. Nothing outside this table is read.

---

## 3. Common specification

| Item | Rule |
|---|---|
| Segments | Research 2017-02-01 → 2022-12-30 (1,490 sessions) and holdout 2023-01-03 → 2026-06-02 (856 sessions), as recorded in each `run_summary.json` → `segment` **[V]**. **Analysed and reported separately; never pooled.** |
| Costs | **Primary analysis: 5 bps. Secondary cost-sensitivity analysis: 10 bps** **[C1]**. The 10 bps analysis is a separate analysis: it uses only 10 bps inputs, derives its own T1/T2 session sets, K2 tables and K3 comparisons, and is reported in a separate section labelled *"secondary cost sensitivity (10 bps) — not primary evidence"*. No output combines, pools, averages or compares within one figure 5 bps and 10 bps values, and no 10 bps output is cited as primary evidence. K2/K3 at 10 bps are labelled secondary diagnostics. The 0 bps runs are not used. |
| Pairing | Within one segment and one cost, V2-MOM and B1 are paired session by session on the `session` column of their `equity.csv`. |
| Daily simple return | `r_d = E(d)/E(d−1) − 1` with `E(0) = E_0 = 100,000`, so the first return spans E_0 to the first close (including first-open costs) and the last return includes the liquidation cost. This is exactly `backtest/v2/metrics.py::returns` (`metrics.py:3`, `25-27`) **[V]**. |
| Annualisation | 252 sessions per year (`metrics.py:17`, protocol §12) **[V]**. |
| Ties and ordering | Every ordering ties by **ascending session date**. Every ticker enumeration uses ascending ASCII order (Python `sorted`), as in DAY-25B §2. |
| Floating point | IEEE-754 float64 throughout. Inputs are parsed from their full-precision `repr` text. Equality checks in §4 are **exact**, with no tolerance or rounding. |
| Statistics | **None new.** No p-value, t-statistic, confidence interval, bootstrap or threshold is computed. |
| Determinism | No randomness. Two runs must produce byte-identical outputs; a mismatch aborts (S10). |
| Isolation | The future run script must refuse network sockets (pattern of `backtest/v2/run.py:95-96`, `270`), read only the §2 inputs and the §4 calendar, and write only under its own output directory (§15). |

---

## 4. Shared integrity and session-alignment checks (whole-run abort)

These checks run **first, as a separate stage, before any T or K computation**. The failure of **any** check, for any segment or cost, aborts the **entire DAY-29 run** (§7). No diagnostic output is created, and the run is not marked successful. A check is never relaxed, re-baselined or skipped automatically.

| # | Check |
|---|---|
| S1 | For each of the 48 §2 input files: SHA-256 of the file's **raw on-disk bytes, with no line-ending or other normalisation**, equals its pin in the segment's `run_summary.json` → `result_files_sha256` (key `"<experiment>/<cost>/<file>"`). This is the convention that produced the pins: `backtest/v2/run.py:99-107`, `120-125` and `359-373` hash exactly the bytes they write **[V]** **[C2]**. An LF-normalised match is **not** accepted (see the hash-convention note below). Every file is parsed from the same raw bytes that were hashed. |
| S2 | SHA-256 of each `run_summary.json`'s raw bytes equals `run_provenance.json` → `run_summary_sha256` (`run.py:426-431`) **[V]**. No normalisation. |
| S3 | `run_summary.json` → `segment` equals exactly: research `{first 2017-02-01, last 2022-12-30, sessions 1490}`; holdout `{first 2023-01-03, last 2026-06-02, sessions 856}`. |
| S4 | Every `equity.csv` has exactly the header `session,equity,exposure,n_held`, has as many data rows as S3's `sessions`, and has session dates that parse as ISO dates, are unique and strictly ascending, and start and end at S3's `first` and `last`. |
| S5 | Within a segment, the session column is **identical** across V2-MOM and B1 and across 5 bps and 10 bps. |
| S6 | **Mandatory prerequisite: `exchange_calendars==4.13.2`** **[C3]**. This version is pinned in `requirements.txt:9` and `paper/requirements.txt:13`, and recorded in both `run_provenance.json` → `environment.exchange_calendars` **[V]**. If the package cannot be imported, or `exchange_calendars.__version__` is not exactly `4.13.2`, the run aborts: no other version is substituted, and the mismatch is not downgraded to a warning. With the required version, the session column must equal the XNYS sessions in `[first, last]` from `exchange_calendars.get_calendar("XNYS")`. |
| S7 | Every `equity` value is finite and > 0, and every `1 + r_d` is > 0 (so `ln(1 + r_d)` is defined). |
| S8 | For each series: the last `equity` value equals `metrics.json` → `ending_equity` exactly, and the row count equals `metrics.json` → `sessions`. For each V2-MOM run: `metrics.json` → `b1_ending_equity` equals the last `equity` of the paired B1 run exactly. |
| S9 | Inputs are read only from §2 paths. Any attempt to open another data path, a network socket, or any forward, F003, `fwd-gate2` or P001 artifact aborts the run. |
| S10 | Determinism: a second in-process execution produces byte-identical outputs. |

**Hash-convention note [V] [C2]:** the repository uses two hash conventions, and DAY-29 keeps them apart:
- **Generated result files are pinned raw.** `backtest/v2/run.py` pins the exact bytes it writes. The DAY-25B run outputs are pinned the same way and protected from line-ending conversion by `.gitattributes` (`artifacts/day25b/run/** -text`).
- **Frozen text documents are hashed LF-normalised.** This covers documents only: `scripts/day25b_robustness.py::doc_sha256` (lines 114-116) and `backtest/v2/forward.py::lf_sha256` (lines 48-50).

No repository rule accepts an LF-normalised match for the DAY-19/DAY-21 result files. The only line-ending tolerance found applies to the DAY-15 baseline directories (`artifacts/day26d/protocol-v2.2-amendment.md:31`). S1 and S2 are therefore raw-only.

**Known operational risk:** there is no `.gitattributes` rule for `artifacts/day19/` or `artifacts/day21/`, and `core.autocrlf=true` is set on the drafting machine. A checkout that converts these files to CRLF would make S1 fail, and the run would abort, which is fail-closed. Adding a `.gitattributes` rule would be a separate owner decision and is not part of DAY-29.

The shared stage writes its own record (§15) whether it passes or fails. The record holds each check, the expected and observed values, and the environment fingerprint (Python, numpy and `exchange_calendars` versions). **A passing shared stage authorizes nothing.**

---

## 5. Active-day diagnostics (T0–T3)

Each runs per segment, after §4 passes: first at 5 bps (primary), then separately at 10 bps (secondary, §3). Every T output depends only on §4, so no K2/K3 outcome can block T0–T3. At 10 bps, the T1 best-k and worst-k sets are derived from the 10 bps `l_d` series. They are never taken from the 5 bps sets.

### T0 — Daily active log-return series
- **Definition:** for each paired session d, `l_d = ln(1 + r_MOM,d) − ln(1 + r_B1,d)`, with r as in §3.
- **Cumulative active log return:** `L = Σ_d l_d` over all N aligned sessions.
- **Outputs:** N; the full `(session, r_MOM, r_B1, l_d)` table; L; and, copied without recomputation, `metrics.json` → `cagr` for V2-MOM and for B1, with source path and pinned hash.
- **Reported identity (descriptive):** `ln(E_T,MOM / E_T,B1)` is reported beside L. Any difference is printed as a floating-point difference and is **not** a check or a gate.
- **Validation:** S4–S7 cover unique, ascending and identical session dates, valid logarithms and input integrity. T0 adds no tolerance.

### T1 — Best/worst active-day concentration
For each `k ∈ {5, 10, 20}` **[A]**:
- **Best-k set:** the k sessions with the largest `l_d`, ordered by `l_d` descending; ties are broken by ascending session date (the earlier date ranks first).
- **Worst-k set:** the k sessions with the smallest `l_d`, ordered by `l_d` ascending; ties are broken the same way.
- **Outputs:**
  - each set's dates and `l_d` values;
  - `Σ l_d` over the best-k set and over the worst-k set;
  - the counts `n_pos` (`l_d > 0`), `n_zero` (`l_d = 0`) and `n_neg` (`l_d < 0`);
  - **share of positive active days = `n_pos / N`**, where N is the number of aligned sessions in the segment, zero-active days included.
- **L is not used as a denominator** anywhere. L is reported only beside the sums, for context.
- **Insufficient observations:** if `N < 2k`, the best and worst sets would overlap. That (segment, cost, k) output is then reported as `undefined (insufficient observations: N < 2k)` and nothing is imputed.
- **Duplicate dates** cannot reach T1: they abort the run at S4.

### T2 — Descriptive tail removal
For each `k ∈ {5, 10, 20}`, separately for the T1 best-k set and the T1 worst-k set (R):
- Remove the sessions in R from **both** paired simple-return series. The same dates are removed from V2-MOM and from B1.
- **Remaining growth:** `G_X = Π_{d∉R} (1 + r_X,d)` for X ∈ {MOM, B1}. Report the remaining total return `G_X − 1`.
- **Annualised:** `CAGR_−R(X) = G_X^(252 / (N − k)) − 1` **[C4]**. This is the DAY-25B D4c convention, applied without changing its meaning.
  - **What D4c says [V]:** "Compound the remainder and annualise with the remaining session count: `CAGR_−y = Π(1 + r)^(252/N_−y) − 1`". Active is the strategy-minus-B1 difference (`artifacts/day25b/day25b-robustness-predeclaration.md:117-123`).
  - **What the executed implementation does [V]:** it masks the removed sessions from both series, which come from `metrics.returns`, and computes `np.prod(1 + r[keep]) ** (252 / nk) - 1`, where `nk` is the number of remaining sessions (`scripts/day25b_robustness.py:438`, `449-460`).
  - **Why they are compatible:**
    - both use the same daily-return definition (§3);
    - both remove the same session set from V2-MOM and B1;
    - both compound the remaining simple returns;
    - both annualise with exponent 252 / (remaining sessions), where `N − k` is the remaining count because the k removed dates are distinct;
    - both take the active difference of the two annualised values.
  - **Differences, which do not change the convention:** D4c removes one contiguous calendar year, chosen independently of outcomes, whereas T2 removes k non-contiguous sessions chosen by outcome. T2 reads r from `equity.csv` rather than from an in-process simulation. `repr` float text round-trips float64 exactly, so the r values are identical.
  - **Guard:** D4c's guard for no remaining session (`day25b_robustness.py:455-457`) cannot trigger in T2, because T2 is computed only when T1 is defined (`N ≥ 2k`). Otherwise T2 is reported `undefined (insufficient observations: N < 2k)`.
- **Active:** `CAGR_−R(MOM) − CAGR_−R(B1)`, plus the unannualised `(G_MOM − 1) − (G_B1 − 1)`.
- **Outputs:** both best-removed and worst-removed results for every k, beside the unremoved T0 CAGRs.
- **Disclosures printed with every T2 result:**
  - The return path is spliced; this is not a re-simulation and not a tradable strategy.
  - Removal is outcome-dependent by construction.
  - If the last session is in R, its liquidation cost is removed with it.
  - A change after tail removal is not, by itself, evidence of failure or of robustness.

### T3 — Monthly aggregation
- **Month key:** the session's `YYYY-MM`, exactly as `metrics.py::_period_returns` keys months (`metrics.py:53-57`, `121`) **[V]**.
- **Per month m:**
  - `R_X,m = Π_{d∈m} (1 + r_X,d) − 1` for X ∈ {MOM, B1};
  - **active_m = `R_MOM,m − R_B1,m`**, a simple difference, consistent with DAY-25B D4a and `metrics.py:150-153`;
  - also the month's log active `Σ_{d∈m} l_d`, and its session count `n_m`.
- **Month completeness:** month m is `full` if the segment contains every XNYS session of calendar month m (`exchange_calendars` 4.13.2, S6). Otherwise it is `partial (first..last)`, showing the first and last segment sessions in m.
- **Months to check:** the classification is computed at run time, not asserted here. The months at the segment boundaries (2017-02, 2022-12, 2023-01, 2026-06) must be shown with their label and `n_m`.
- **No month is dropped**, however few sessions it has.
- **Outputs:** the full monthly table per segment and cost; the count of months with active_m > 0, = 0 and < 0 out of all months; and the same counts restricted to `full` months.

---

## 6. Ticker-recurrence diagnostics (K1–K3)

**K2 and K3 cover V2-MOM only [C5].** No ticker-recurrence or holdings diagnostic is computed for B1, and B1's `decisions.json`, `episodes.json`, `fills.csv` and `executions.json` are not read by K2 or K3. B1 remains the comparator in T0–T3 and is used only there and in the shared checks (S4–S8); B1 has a single decision before the segment (`run.py:155-159`) **[V]**. K2 and K3 run per segment at 5 bps (primary) and separately at 10 bps (secondary diagnostics, §3).

### K1 — Existing DAY-25B concentration evidence (reference only)
- **[V]** DAY-25B was executed:
  - commit `8ef01f465b917ee74065d8375a9f03ac35175ca3`, "DAY-25B V2-MOM robustness diagnostics D1-D7 results";
  - `artifacts/day25b/run/run_summary.json` → `status` = `COMPLETED`, `authorization` = `DAY25B-D1-D7-RUN`, `descriptive_only` = `true`.
- **[V]** Raw SHA-256 of the cited outputs, each equal to its pin in that `run_summary.json`:

  | Output | Raw SHA-256 |
  |---|---|
  | `artifacts/day25b/run/d1.json` (D1 leave-one-symbol-out) | `9dfe44deb86c3d10164eda61f14b04c7d07f95a1c222bca461521c2b0b069670` |
  | `artifacts/day25b/run/d2.json` (D2 top-2 removal) | `541a9226c0ca1629767dfd1272b04d708e6163c73c24dfdf97df572fe2293bf5` |
  | `artifacts/day25b/run/d5.json` (D5 concentration) | `1738dd9eae9bb3e7d2af2e13c53a0b570ef3da11455708eca3d9f925ed43d864` |

- **Definitions** are those of the frozen DAY-25B predeclaration §3 D1, D2 and D5 (`day25b-robustness-predeclaration.md:57-80`, `125-132`) **[V]**.
- **Observation (as published).** The DAY-25B predeclaration states that the top-2 symbols produced 43% of absolute P&L on the holdout and 47% in research (`day25b-robustness-predeclaration.md:22`, citing DAY-19 and DAY-22). DAY-29 has **not** re-verified these figures.
- **No recomputation.** K1 is not recomputed or reinterpreted. The DAY-29 report cites these files by path and hash and checks their hashes. It does not restate, combine or rank their values.
- **Header note.** The DAY-25B predeclaration header still reads "NOT AUTHORIZED TO RUN" (line 5). That is its frozen text; the later run authorization is recorded in its `run_summary.json`.

### K2 — Selection, episode and holding counts
**Definitions** (per segment and cost; tickers in ASCII order):
- **Decision records:** the entries of `decisions.json` that have a `targets` object. Entries with `discarded` are counted separately and contribute no selections. The number of decision records, including the initial pre-segment decision, must equal `run_summary.json` → `decision_counts["V2-MOM"]` (`run.py:395`) **[V]** — check K2-C0.
- **Ticker-selection count `sel(x)`:** the number of decision records whose `targets` contain x with weight > 0. A weight ≤ 0 is not a selection.
- **Episode count `ep(x)`:** the number of `episodes.json` records with `ticker = x`.
- **Sessions held at close `h(x)`:** the number of segment sessions s at whose close x is held, from episodes:
  - **Normal episode** (`end` is a plain date): `start ≤ s < end` **[A]**. The full sell at the open of `end` means x is not held at that close (`engine.py:85`, `92-95`) **[V]**.
  - **Segment-end episode** (`end` ends with `" (segment end)"`): `start ≤ s ≤ last segment session`. The position is open at the last close, and the liquidation is a mark-based cost applied after that close (`engine.py:119-130`, `251-254`) **[V]** **[A]**.
- **Outputs:** the per-ticker table `sel(x)`, `ep(x)`, `h(x)`; totals; the number of distinct tickers selected and held; and the share of sessions held per ticker, `h(x)/N`.
- **No P&L.** K2 reports no P&L of any kind, by episode or by day (§11).

**Record checks** (exact, per segment and cost). The "Required by" column lists the diagnostics whose computation reads the records each check validates **[C7]**. A failed check blocks exactly the diagnostics in its "Required by" column, and nothing else.

| # | Check | Required by |
|---|---|---|
| K2-C0 | Decision-record count equals `run_summary.json` → `decision_counts["V2-MOM"]`. Every record has either `targets` or `discarded`. No target weight is negative or non-finite. | K2 (`sel`), K3 (`T`) |
| K2-C1 | Per ticker, episodes are ordered and non-overlapping, and every normal episode has `start < end`. At most one segment-end episode per ticker, and it is the ticker's last. | K2 (`ep`, `h`), K3 (`H`) |
| K2-C2 | For every segment session s: the number of tickers held at s (from the episode intervals above) equals `equity.csv` → `n_held` at s. | K2 (`h`), K3 (`H`) |
| K2-C3 | The number of episodes equals `metrics.json` → `position_episodes`. | K2 only |
| K2-C4 | Against `fills.csv`, for every episode of x: there is a `buy` fill of x at `start`; for a normal episode there is a `sell` fill of x at `end`; and no fill of x falls outside the union of x's `[start, end]` intervals. | K2 (`ep`, `h`), K3 (`H`) |

**Why K3 requires C0, C1, C2 and C4 [V]:** K3 reads the same decision records (C0) and builds its cross-check `H(s)` from the same episode intervals that C1, C2 and C4 validate. No other artifact identifies held tickers at a close: `equity.csv` has counts only, and `fills.csv` cannot net shares (see the limitation below). These are input dependencies, not an automatic cascade. A failure of K2-C3, or of any K2-only output, does not block K3.

**Limitation of K2-C4 [V]:** `fills.csv` does not record split adjustments (`engine.py:62-65`), so cumulative fill shares cannot reproduce held shares. `fills.csv` is therefore used only for event dates, never for share netting.

### K3 — Decision-target holdings reconstruction
- **Primary source [A]:** `decisions.json`.
- **Close-time boundary [V]:** decisions carry only a session date, made at that session's close after its holdings are recorded. So **`decision_time < session_close` is implemented as `decision close date < s`** (strictly earlier date). A decision dated s does not affect holdings at s's close. No time-zone conversion is applied: all dates are XNYS session dates as written.
- **Target holdings at the close of s:** `T(s)` = the tickers with weight > 0 in the latest decision record whose `close < s`.
  - **Before the segment:** for the close before the segment's first session, `T` is the empty set. The engine starts with cash E_0 and no shares (`engine.py:33-50`).
  - **Missing decision:** if no qualifying record exists for a segment session s, `T(s)` is `undefined (no prior decision)`, which is a K3 mismatch.
- **Cross-check representation:** `H(s)` = the tickers held at the close of s from the K2 episode intervals. It uses the same close boundary. K3 proceeds for a (segment, cost) only if the record checks it requires (K2-C0, C1, C2 and C4) pass for that unit.
- **Comparison:** for every segment session s, `T(s) = H(s)` as sets. Any difference is a **K3 mismatch** and is reported with the session, the ticker, and the direction (in T only, or in H only).
- **Known engine paths that would produce a difference [V].** These are listed, not reconciled; if any occurs, it is a mismatch:
  - a buy cancelled because of a missing open (`engine.py:192-197`);
  - a full sell deferred as a pending sell (`engine.py:193-194`, `214-221`);
  - a decision superseding pending sells (`engine.py:186`).
- **No rule is introduced to force agreement.** Cancelled and pending orders are not recorded in any artifact. They can only show up as differences, which are reported.
- **Reporting sessions [C6]:** prior-close and current-close holdings, as `T` and `H`, are reported for a session set fixed by the XNYS calendar and session order alone, with no artifact content involved:
  1. the first segment session;
  2. every segment session that immediately follows the last XNYS session of a calendar month, where that month-end session lies within `[first, last − 1]`;
  3. the last segment session.

  The set is the union of these, in ascending order.
  - **Rationale [V]:** V2-MOM decides at the session before the segment and at each month-end close in `[first, last − 1]`, and executes at the next open (`signals.py:24-27`, `35-38`; `engine.py:225-229`). Rule 2 is exactly the set of scheduled execution sessions, and rule 1 is the execution of the pre-segment decision.
  - **Outcome-independent:** the set is computed from `exchange_calendars` 4.13.2 (S6) and the segment boundaries. It does not use returns, P&L, fills, executions or tickers.
  - **Not a substitute for the full comparison:** the reporting set only chooses which sessions get the detailed table. The `T(s) = H(s)` comparison above covers every segment session, so unscheduled changes (for example a deferred pending sell) are still detected and listed.
  - **First session:** its prior close is the pre-segment close (empty `T` and `H`).
- **Outputs:** the diagnostic-session table; the count of sessions compared; and the count and full list of mismatching sessions (zero or more).

---

## 7. Failure policy and run statuses

| Level | Trigger | Effect | Run status |
|---|---|---|---|
| **Shared [A]** | Any S1–S10 failure, for any segment or cost | Entire run aborts. No T or K output is created; only the shared-stage record is written. | `ABORTED_SHARED_INTEGRITY` |
| **Record check [A] [C7]** | Any K2-C0…C4 failure for one (segment, cost) | Exactly the diagnostics in that check's "Required by" column (§6 K2) are blocked for that (segment, cost). A K2-C3 failure blocks K2 only. K3 is blocked only if a check it requires (C0, C1, C2 or C4) fails. Other units and all of T0–T3 proceed. | `COMPLETED_WITH_BLOCKED_DIAGNOSTICS` |
| **K3 [A]** | `T(s) ≠ H(s)` or `T(s)` undefined for any session of one (segment, cost) | K3 is blocked for that (segment, cost); its mismatch list is still reported. K2 is never blocked by a K3 mismatch. | `COMPLETED_WITH_BLOCKED_DIAGNOSTICS` |
| None | — | All outputs produced. | `COMPLETED` |

- A blocked unit produces no diagnostic values. It produces only the check that failed, with expected and observed values.
- No status here means "pass" in any economic sense.
- Failures are never resolved by editing inputs, frozen code or reference values.

---

## 8. Multiplicity and selection risks

- **Volume:** 2 segments × 2 costs × (T0, 3 k for T1, 6 T2 removals, T3, K2, K3). That gives 4 T0 series, 12 T1 results, 24 T2 results, 4 monthly tables, and up to 4 K2 and 4 K3 tables.
- **No individual row is evidence.** Results are reported in full (every k, both tails, both segments, both costs), and none is highlighted.
- **Outcome-dependent selection:** T1 and T2 select sessions by their realised `l_d`. This is labelled on every output.
- **No tests:** nothing is tested, so there is no multiple-testing correction to make.

---

## 9. Decision rules

**None.** DAY-29 has no thresholds, flags or pass/fail criteria, and none may be introduced after any DAY-29 output exists.

---

## 10. Interpretation limits

1. Holdout evidence is historical pseudo-out-of-sample. It is not equivalent to a genuinely blind prospective evaluation.
2. **Survivor-universe bias:** the frozen 25-symbol universe was chosen with present knowledge, and that bias applies to every T and K output.
3. Concentration diagnostics are descriptive and establish no statistical significance.
4. A result that changes after tail removal (T2) is not, by itself, proof of failure or of success.
5. Backtest performance does not establish live profitability.
6. Nothing in this document, or in any future DAY-29 output, changes strategy selection, trading rules, risk limits, Sharia status, F003 or P001. V2-MOM is **not** approved or selected by this document.

---

## 11. Exclusions

- Per-ticker daily P&L reconstruction **[A]**, and any per-ticker or per-episode P&L in K2/K3.
- New strategy development, variants or optimisation; parameter tuning on observed outcomes.
- New data acquisition, market data or external data.
- New significance tests, confidence intervals or decision thresholds.
- Any access to F003, `fwd-gate2`, P001, forward segments or other sealed evaluation artifacts.
- Running the diagnostics, backtests, simulations or test suites under this draft.
- Recomputing any DAY-25B result (K1).

---

## 12. Decisions, drafting choices and unresolved items

**Owner-approved decisions [A]** (as restated in the DAY-29 brief of 2026-10-19; the original approval records are not in this repository):

| # | Decision |
|---|---|
| A1 | Hash convention: use the repository's existing hash helper and run-summary convention (S1, S2, §14). |
| A2 | K3: decision targets are primary; `fills.csv` (and episodes) are cross-checks. |
| A3 | k ∈ {5, 10, 20}. |
| A4 | Per-ticker daily P&L reconstruction is excluded. |
| A5 | Draft the predeclaration only; do not execute. |
| A6 | A K2/K3 mismatch blocks the affected diagnostics only. |
| A7 | A shared integrity or session-alignment failure aborts the entire run. |
| A8 | Markdown is authoritative; no JSON twin. |
| A9 | Normal episode `start ≤ s < end`; segment-end episode includes the final session when the position is open at the close. |

**Owner decisions on drafting choices, 2026-10-19 [C]:**

| # | Decision | Where applied |
|---|---|---|
| C1 | 5 bps is the primary analysis. 10 bps is a separate secondary cost-sensitivity analysis, never mixed with or presented as primary evidence. K2/K3 at 10 bps are labelled secondary diagnostics. 0 bps is unused. | §3 Costs, §5, §6 |
| C2 | Strict hash convention grounded in verified repository behaviour: input result files and `run_summary.json` are verified raw-bytes only. LF-normalised hashing is used only for the predeclaration document itself. No interchangeable acceptance. | §4 S1, S2 and the hash-convention note; §14 |
| C3 | `exchange_calendars==4.13.2` is mandatory. An unavailable or different version aborts the whole run; no substitution. | §4 S6, §15 |
| C4 | T2 uses the DAY-25B D4c annualisation convention. Compatibility was verified against the D4c text and its executed implementation. | §5 T2 |
| C5 | K2/K3 cover V2-MOM only. B1 is a comparator in T0–T3 and the shared checks only. | §6 |
| C6 | K3 reporting sessions are fixed by calendar and session order (first session, sessions after month-end sessions, last session). The full T/H comparison still covers every session. | §6 K3 |
| C7 | No automatic K2→K3 cascade. Each record check blocks only the diagnostics that read the records it validates. | §6 K2, §7 |

**Unresolved [U]:**

| # | Item |
|---|---|
| U1 | **Closed by owner decision, 2026-10-19.** The original DAY-28 artifacts could not be recovered from the current environment (§13). No DAY-28 decisions are available in the accessible evidence, and none is inferred or assumed. This document proceeds on the currently available repository evidence and the decisions explicitly approved above. |
| U2 | Approval and freeze of this document (§14). Until then there is no approved hash. |
| U3 | The run-script entry point and output paths in §15 are proposals; none exists. |

---

## 13. Relation to earlier work

- **DAY-25B:** document conventions (header table, numbered sections, descriptive-only rule, preflight-before-diagnostics, three-part run authorization) are followed. DAY-25B results are only referenced (K1). Its frozen files are not modified.
- **DAY-28:** the original artifacts could not be recovered from the current environment. Searches covered the working tree, every local and remote-tracking ref, the reflogs, the objects without a branch, every ref advertised by `origin`, the local scratchpads, and the other local clones (audits of 2026-10-19). DAY-28 is not restored or reconstructed here, and its content is not inferred (header, U1).
- **Earlier DAY-29 draft (`7af41cca…`, 227 lines):** not available on this machine; this document is new and is not claimed to match that hash.

---

## 14. Hash and freeze convention

- **Hash:** SHA-256 of this file's bytes with CRLF normalised to LF, as computed by `backtest/v2/forward.py::lf_sha256` (`forward.py:48-50`) **[V]**. This is the convention used by the DAY-26B to DAY-27B adoption records (`adopted_files_sha256_lf`) and attributed there to DAY-25B. The file is stored as UTF-8 with LF line endings.
- **Freeze procedure (DAY-25B precedent):**
  1. The owner approves the content and the LF-normalised SHA-256 of that approved content.
  2. Only the Status and Freeze rows change: Status becomes `FROZEN — NOT AUTHORIZED TO RUN`, and Freeze records the approved pre-freeze hash.
  3. The frozen file is committed only with explicit approval. The commit message records the frozen file's LF-normalised SHA-256, because a file cannot contain its own hash.
  4. Any later change requires a new, separately approved version.

---

## 15. Implementation and run (NOT IMPLEMENTED; NOT AUTHORIZED)

- **Proposed, not existing:** an entry point `scripts/day29_stability.py` that imports nothing from `backtest/v2` except `forward.lf_sha256` and the constants it re-uses (`engine.E0`, `metrics.ANN`).
- **Proposed outputs:** under `artifacts/day29/run/`, with the shared-stage record written separately under `artifacts/day29/preflight/`. The run summary follows `backtest/v2/run.py` (`result_files_sha256` of every output, environment fingerprint, git commit) and records the SHA-256 of this predeclaration.
- **Before any run, all three are required:**
  1. this document approved and frozen (§14);
  2. a reviewed implementation, with synthetic-fixture tests for S1–S10, T0–T3 and K2/K3, including deliberate mismatch fixtures for each failure level in §7;
  3. a separate, explicit run authorization;
  4. a run environment with `exchange_calendars==4.13.2` installed (S6).

**This document does not authorize implementation or execution.** A passing shared stage does not authorize anything either. No DAY-29 result may be described as passing or failing anything.
