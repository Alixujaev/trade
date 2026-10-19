# DAY-30: V2-MOM day-by-ticker attribution of active return (predeclaration)

| Field | Value |
|---|---|
| Status | **FROZEN — NOT AUTHORIZED TO RUN** |
| Freeze | Frozen 2026-10-19. Approved pre-freeze LF-normalised SHA-256 `5f25ae08c43de2faef836b27a5c20b81fb71a1b44c690fe9fa1ec14adbc818b4`. Owner approval: "Tasdiqlayman" (2026-10-19). Freeze authorization: owner brief "DAY-30 — Freeze, Commit, Then Execute" (2026-10-19). The frozen file's SHA-256 is in the freeze commit message (§12). |
| Nature | New DAY-30 document. It is not a recovery of DAY-28 or of any earlier draft. |
| Drafted | 2026-10-19 on `feature/day-trading-research` at HEAD `fb41dac695949b2ff82c6661bf04e5d56610d4d1` |
| Family | V2-MOM, attributed against B1 |
| Kind | **Descriptive accounting attribution of the existing DAY-19/DAY-21 portfolio paths.** No engine run, re-simulation, replay or counterfactual portfolio of any kind. |
| Authoritative form | This Markdown file; no JSON twin (DAY-29 precedent). |
| Protocol label | **DERIVED FROM PRIOR OBSERVATION** (protocol v2 §14). Drafted after the DAY-19, DAY-21, DAY-25B and DAY-29 results were seen. |
| Evidence label | Every output carries: *"descriptive attribution on reused historical data — outcome-dependent day and ticker sets — survivor-universe — not independent or forward evidence"*. |
| Conditional label | Every output also carries: *"G7/G8 reconciliation is conditional on unproven premises A1 (IEEE-754 platform arithmetic) and A4 (bit-identical reconstructed share/price state); see §6A"*. |

**Drafting constraints observed:** no study, replay, simulation, backtest or data acquisition was run, and no attribution value was computed. The drafting audit read code, document text, key names, the published DAY-25B D2/D5 and DAY-29 outputs, and file hashes. One arithmetic check was made on existing pinned files: the flow-sum identity in §2. No snapshot was opened. No F003, `fwd-gate2`, P001 or sealed artifact was accessed. No existing file was modified. The 2026-10-19 OD-1 revisions (§6A) read only:
- `backtest/v2/engine.py`, `metrics.py` and `run.py`;
- the header and first data rows of one I1 `fills.csv` and one I1 `equity.csv`;
- the first records of one I1 `episodes.json`.

They also ran one synthetic `sum()` check (A3). They computed no bound, residual or attribution value.

**Evidence classes:** **[V]** verified in the repository during drafting, with a reference; **[D]** design rule set by this document; **[OD]** open owner decision (§11).

---

## 1. Question and limits

**Decision question.** On the DAY-29 best-k and worst-k active days, how much of the summed daily simple active return is attributable to the DAY-25B D2 top-two tickers, compared with all other tickers and with all other days?

The question separates three things:
- **H1, day concentration:** the day axis of the table.
- **H2, ticker concentration:** the ticker axis of the table.
- **Their overlap:** the best-days × top-two cell.

DAY-29 could not separate them. Its T1/T2 diagnostics see only the portfolio series, and K2 counts holding, not contribution. DAY-25B D1/D2 could not either, because they are re-simulations in which other symbols replace the removed ones.

**Predeclared design, fixed before any run:**

| Element | Fixed value |
|---|---|
| Segments | Research (DAY-19 V2-MOM-R001 vs V2-B1-research) and holdout (DAY-21 V2-MOM-H001 vs V2-B1-holdout) |
| Costs | 5 bps, primary; 10 bps, secondary cost sensitivity (§2) |
| Day sets | DAY-29 T1 best-k and worst-k sessions for k ∈ {5, 10, 20}, taken from the T1 file of the same cost (I3) |
| Ticker sets | DAY-25B D2: research {TSLA, NVDA}, holdout {MU, AMD}, the same at both costs (I4) |
| Comparison | O1: {day set, other days} × {D2 top-two, other tickers, engine residual}; O2: per ticker (§5) |
| Decision rule | **None.** No outcome triggers any action, status change or gate (constraint 1) |

**Binding constraints:**
1. **Descriptive only.** No thresholds, pass/fail rules, p-values, confidence intervals or rankings. Nothing in DAY-30 changes V2-MOM's status, any gate, the forward plan, trading rules, risk limits, Sharia status, F003 or P001.
2. **No counterfactual.** Contributions are accounting components of the realised DAY-19/21 paths. A contribution is not "what would have happened without the ticker" and is not causal.
3. **Fixed sets.** The day sets (DAY-29) and the ticker sets (DAY-25B D2) are taken from pinned published files and are never re-selected or changed with DAY-30 results.
4. **Simple, not log, returns.** Contributions add up to the daily simple active return `r_MOM,d − r_B1,d`, not to DAY-29's log active return `l_d`. Because `ln` is strictly increasing and `1 + r > 0` (DAY-29 S7), `sign(l_d) = sign(r_MOM,d − r_B1,d)` on every day **[V]**. Cross-day sums of simple contributions are descriptive totals and are not CAGR or log-return attribution.

---

## 2. Inputs (verified; nothing else is read)

| # | Input | Identity |
|---|---|---|
| I1 | DAY-19/21 V2-MOM and B1 run artifacts at 5 bps and 10 bps: `equity.csv`, `fills.csv`, `episodes.json`, `metrics.json` under `artifacts/day19/v2/{V2-MOM-R001,V2-B1-research}/{5bps,10bps}/` and `artifacts/day21/v2/{V2-MOM-H001,V2-B1-holdout}/{5bps,10bps}/` | Raw SHA-256 equal to the pins in `artifacts/day19/v2/run_summary.json` and `artifacts/day21/v2/run_summary.json` → `result_files_sha256`, and each run summary's raw SHA-256 equal to `run_provenance.json` → `run_summary_sha256`. This is the DAY-29 S1/S2 rule; all 48 DAY-29 inputs matched raw on 2026-10-19 **[V]**. |
| I2 | Stage R and Stage H snapshots, read **only** through `backtest/v2/data.py::load_stage_r` and `load_stage_h`, the existing verifying loaders. They supply `open`, `close`, `q` (split ratio at ex-date) and `d` (cash dividend per share at ex-date) (`data.py:40-46`) **[V]** | The loader-verified `manifest_sha256` and `tree_sha256` must equal the DAY-19/21 `run_summary.json` → `reproducibility.data` values exactly. Research: snapshot `stage_r_20261007T093410Z`, manifest `aefef19d…6bd`, tree `c5d78635…590`. Holdout: snapshot `stage_h_20261008T100604Z`, manifest `eff95959…a34`, tree `8a51463b…556`. Both record `missing_bars: 0` **[V]**. |
| I3 | DAY-29 T1 day sets: `artifacts/day29/run/5bps/t1.json` and `artifacts/day29/run/10bps/t1.json`, fields `by_k[k].best.sessions` and `by_k[k].worst.sessions` for k ∈ {5, 10, 20} | Raw SHA-256 `f02769bf…7f58` (5 bps) and `5025aa6d…3f73` (10 bps). These equal the pins in `artifacts/day29/run/run_summary.json`, whose raw SHA-256 is `d7795bb91ebad4bf371f9f7254491a76378b4a0ed551b17519dc13c5134cdfc9` **[V]**. Committed unchanged in `067295f1e82e9d1c2dc8282e6c702fd09263a22c` ("Pin DAY-29 stability study outputs"); the committed blob SHA-256 of every DAY-29 output equals its raw working-file SHA-256 and its run-summary pin **[V]** (OD-2, §11). |
| I4 | DAY-25B D2 ticker sets: `artifacts/day25b/run/d2.json` → `results[segment].removed[].ticker` | Raw SHA-256 `541a9226c0ca1629767dfd1272b04d708e6163c73c24dfdf97df572fe2293bf5`, equal to its pin in `artifacts/day25b/run/run_summary.json` **[V]**. The sets are **research {TSLA, NVDA}, holdout {MU, AMD}**, with `same_symbols_at_all_costs: true` **[V]**. The same two tickers are used at 5 and 10 bps (D2 ranks at 5 bps only). |

**Already-verified accounting facts [V]:**
- `metrics.json` → `symbol_pnl_contribution` holds per-symbol net cash flows (`engine.py:43`, `81-111`, `119-130`), and is identical to DAY-25B D5 `flows_signed` at both costs.
- Its fsum equals `ending_equity − 100,000` to within 4.1e-10 dollars in all four V2-MOM runs (relative error about 1e-15). This is the segment-level form of the identity that §4 applies daily.

The 10 bps analysis uses the 10 bps T1 sets (DAY-29 derived its sets per cost). It is reported separately and labelled *"secondary cost sensitivity (10 bps) — not primary evidence"* (DAY-29 C1).

---

## 3. Reconstruction of the daily state (exact)

For each segment, cost and series (V2-MOM and B1), the per-ticker state is rebuilt from I1 + I2 by applying the engine's own float operations in the engine's order (`backtest/v2/engine.py:53-68`, `81-111`, `113-117`, `180-225`, `251-254`) **[V]**. The engine itself is not run. The state values `S`, `S'`, `M'` and `M` are float64 values intended to equal the engine's bit for bit. This is assumption A4 of §6A: it is verified exactly only at the G5a–G5d checkpoints, with the limits stated in §6A.6. §4 then evaluates the accounting on these values exactly. No other engine-internal value (cash, buy totals, running flows) is reconstructed.

At each segment session k, for each universe ticker j:
1. **Corporate actions** (before the open):
   - `div_j,k = S_j,k−1 · d[k,j]`, using pre-split shares.
   - If `q[k,j] ≠ 1`: `S ← S · q` and, for any ticker with a non-NaN mark carry, `M ← M / q`.
   - Write `S'_j,k` and `M'_j,k−1` for the post-split values.
2. **Open value:** `V_j,k = open[k,j]` if it is not NaN, else `M'_j,k−1`.
3. **Trades** at the open, from `fills.csv` for session k, sells before buys:
   - a sell sets `S ← 0.0` if `qty == S`, else `S ← S − qty`;
   - a buy sets `S ← S + shares`, using the recorded `shares` value, which is the engine's `notional/px`.
   - The result is `S_j,k`.
4. **Close mark:** `M_j,k = close[k,j]` if it is not NaN, else `M'_j,k−1`.
5. **Initial state:** at the session before the first segment session, `S = 0` for every ticker and E(0) = E_0 = 100,000 (`engine.py:25`).

`fills.csv` float cells are read with the DAY-29 parser rule: a finite `repr` literal, bare or wrapped as `np.float64(…)`, and nothing else (`scripts/day29_stability.py::_float_cell`) **[V]**.

---

## 4. Accounting and attribution

**Per-ticker daily P&L [D]** (V2-MOM and B1 alike), on session k:

`pnl_j,k = div_j,k + S'_j,k·(V_j,k − M'_j,k−1) + S_j,k·(M_j,k − V_j,k) − cost_j,k − [k = last]·s·S_j,k·M_j,k`

- `cost_j,k` is the sum of the `cost` column of j's fills at k.
- `s` is the run's per-side cost: the exact binary value of the engine's float64 `0.0005` or `0.001`, not the decimal fraction.
- The last term is the segment-end liquidation cost, which the engine charges as `s × Σ shares × mark` (`engine.py:119-131`, `251-254`).

**Why it adds up [V] (algebraic identity, from the engine's cash rules):**
- Δcash on day k = Σ div − Σ_j (S_j,k − S'_j,k)·V_j,k − Σ cost. Trades exchange cash for shares at the open price, and costs are charged separately.
- `S_j,k−1·M_j,k−1 = S'_j,k·M'_j,k−1`, because a split scales shares by q and the mark by 1/q.
- Therefore `Σ_j pnl_j,k = E(k) − E(k−1)` exactly in real arithmetic.
- **Missing open:** the engine values a held ticker at its mark carry, cancels buys and defers full sells (`engine.py:189-197`), so `S_j,k = S'_j,k` and the open term is 0. With `missing_bars: 0` this branch is not expected to occur, but it is defined.

**Contributions [D]:**
- `c_j,k = pnl^MOM_j,k / E_MOM(k−1)` and `b_j,k = pnl^B1_j,k / E_B1(k−1)`, where E comes from `equity.csv` and E(0) = 100,000.
- **Active contribution:** `a_j,k = c_j,k − b_j,k` for every one of the 25 universe tickers. A ticker V2-MOM does not hold contributes `−b_j,k`.
- **Engine rounding residual:** `ε_k = (E(k) − E(k−1)) − Σ_j pnl_j,k`. It is computed separately for V2-MOM and B1 and is never assigned to a ticker.
- **Daily residual term:** `e_k = ε^MOM_k / E_MOM(k−1) − ε^B1_k / E_B1(k−1)`.

**Exact evaluation [D]:** every quantity in §4 (and every bound in §6A) is evaluated in exact rational arithmetic on the float64 values of §3 and I1 (`fractions.Fraction` of each float64 input), following the v2.0.4 convention of exact rational evaluation (`acquisition/v2/crosscheck.py:7`, `106-147`) **[V]**. Results are converted to float64 only for output. As a result, by construction and without any tolerance:

`Σ_j a_j,k + e_k = (E_MOM(k) − E_MOM(k−1)) / E_MOM(k−1) − (E_B1(k) − E_B1(k−1)) / E_B1(k−1)`

**Simple-return note [V]:** the right-hand side is the exact rational value of the DAY-29 simple active return. The float64 `r_d = E(d)/E(d−1) − 1` used by DAY-29 and `metrics.returns` can differ from it by float64 rounding only. DAY-30 reports the exact-rational totals and does not compare them with DAY-29's float or log totals.

---

## 5. Outputs (per segment × cost × k ∈ {5, 10, 20} × day set ∈ {best, worst})

**O1. Overlap table.** Rows: {DAY-29 day set, all other segment sessions}. Columns: {D2 top-two tickers, all other universe tickers, engine residual}. Each cell is `Σ_k Σ_j a_j,k` (or `Σ_k e_k`) over its rows and columns.
- The six cells add up **exactly** to `Σ_k (exact daily simple active return)` over the segment, and that total is reported.
- Every cell is shown both as a sum and as a share of the reported total. The total is the denominator only for these shares; it is printed so the shares can be checked.

**O2. Per-ticker table** (all 25 tickers, ASCII order, no ranking):
- per ticker: `Σ a_j,k` over the day set, over the other days and over the whole segment;
- the V2-MOM-side `Σ c_j,k` and B1-side `Σ b_j,k` over the same three spans.

**O3. Reconciliation report:** per series, the maximum `|ε_k|`, the session where it occurs, and the G7/G8 results (§6).

All outputs carry:
- the evidence label and the conditional label from the header;
- an outcome-dependence label (day sets selected by realised `l_d`, ticker sets selected by realised P&L);
- the survivor-universe label.

O1–O3 depend on G7/G8 having passed, and so inherit their conditional status.

---

## 6. Integrity gates

**Exact checks: any failure aborts the whole run, and no output is written.**

| # | Check |
|---|---|
| G1 | I1: raw-byte pins and run-summary pins, as in DAY-29 S1/S2. |
| G2 | I2: the loaders verify the snapshots, and `manifest_sha256` and `tree_sha256` equal the DAY-19/21 `reproducibility.data` values exactly. The `equity.csv` sessions equal the loaded segment sessions. `exchange_calendars==4.13.2` (DAY-29 S6). |
| G3 | I3 and I4: tracked in git at HEAD, with blob bytes equal to the working file and raw SHA-256 equal to §2. The I3 files equal their pins in the DAY-29 `run_summary.json`. The I4 file equals its DAY-25B pin, and the D2 ticker sets read from it equal §2. |
| G4 | Data–artifact identity: every fill's `price` equals `open[session, ticker]` exactly (the DAY-19 fill-source rule, `backtest/v2/run.py:218-230`), and every fill session lies in the segment. No ticker has more than one fill in a session. No `open` is NaN on any session where the ticker is held or traded (`missing_bars` covers closes only, §6A.6 V6). |
| G5 | Share path: the §3 reconstruction never yields negative shares. At every close, the number of tickers with `S ≠ 0` equals `equity.csv` → `n_held`, and the held set equals the DAY-29 K2 episode-interval set (normal `start ≤ s < end`; segment-end through the last session). State checkpoints G5a–G5d (§6A.6) hold bit for bit:<br>• **G5a:** at each full sell, recorded `shares` = reconstructed `S'`;<br>• **G5b:** at each buy, recorded `shares` = float64 `notional/price`;<br>• **G5c:** at each segment-end episode, `final_net_mark` = float64 `S_T·M_T·(1 − s)` in the engine's order;<br>• **G5d:** for each ticker, the float64 replication of the flows chain = `symbol_pnl_contribution`. |
| G6 | Reads come only from I1–I4 and the frozen document; network sockets are refused; two in-process executions produce byte-identical outputs. |

**Floating-point reconciliation checks: any failure aborts the whole run.** The tolerances τ_k and τ_j are defined in §6A. They are **conditional bounds**: valid only under the unproven premises A1 and A4. A pass of G7/G8 is therefore consistency evidence under those premises, not proof of exact reconstruction.

| # | Check |
|---|---|
| G7 | Daily: for each series and session, `|ε_k| ≤ τ_k`. |
| G8 | Per ticker: for each series and ticker, `|Σ_k pnl_j,k − symbol_pnl_contribution_j| ≤ τ_j`, where `symbol_pnl_contribution` comes from I1 `metrics.json`. This catches mis-assignment *between* tickers, which G7 cannot see. A ticker absent from `symbol_pnl_contribution` (never held) has the value 0 and no rounding operations, so `τ_j = 0` and G8 requires `Σ_k pnl_j,k = 0` exactly. |

G1–G6 compare identities and must hold exactly; no tolerance ever applies to them. G7 and G8 compare an exact-rational attribution with the engine's float64 accounting, so they need a bound by nature. The two kinds of check are never merged. G7 and G8 run only after G1–G6 have passed; in particular the §6A paths rely on G4 (fill price = open).

---

## 6A. Tolerances for G7 and G8 (OD-1; conditional bounds)

**Status: conditional bounds.** τ_k and τ_j are upper bounds on the float64 discrepancy that are **valid only if A1 and A4 hold**. The derivation omits no term, so they are not first-order approximations. But A1 (platform arithmetic) is an assumption, and A4 (bit-identical share and price state at every step) **is not proven** from the recorded artifacts (§6A.6). They must therefore not be described as rigorous without both premises.

Notation: `u = 2⁻⁵³`; `γ_n = n·u / (1 − n·u)` for `n·u < 1`; `s` is the engine's float64 per-side cost taken exactly, `Fraction(0.0005)` or `Fraction(0.001)`. These are binary values, not 1/2000 or 1/1000.

### 6A.1 Lemmas (standard IEEE-754 results)

- **L1, one operation.** Let `x = a ∘ b` exactly, with float64 operands a and b and ∘ ∈ {+, −, ×, ÷}, and let `r = fl(x)` be the correctly rounded result (round-to-nearest). If no overflow occurs, and for × and ÷ if x = 0 or |x| ≥ 2⁻¹⁰²², then:
  - `|r − x| ≤ u·|x|` (exact-operand form);
  - `|r − x| ≤ u·|r|` (result form);
  - hence `|r| ≤ (1+u)·|x|` and `|x| ≤ |r| / (1−u)`.

  For + and −, no range condition is needed below overflow: with gradual underflow, a sum or difference whose exact value is subnormal is computed exactly. In every case, x = 0 implies r = 0.

  Source: Higham, *Accuracy and Stability of Numerical Algorithms* (2nd ed., 2002), Theorem 2.2 and the model (2.4)–(2.5).
- **L2, recursive summation.** Computing a sum of m float64 values by m − 1 successive rounded additions, in any order, satisfies `|Ŝ − S| ≤ γ_{m−1}·Σ|x_i|`. This is rigorous and includes every higher-order term (Higham §3.1 and §4.2).
- **L3, magnitude of a value not recorded in I1.** If `|c| ≤ U`, then `|fl(c + x)| ≤ (U + |x|)·(1+u)`. This follows from L1.

**Cancellation, zero results and division.**
- Each lemma bounds only the local rounding error of its own operation. An exact-zero result has zero error.
- No error inherited by an operand is ever bounded relative to a later result. Every local error enters ε through the exact identities below with an explicit weight, so cancellation amplifies nothing.
- The one division whose error reaches ε is `shares = notional/px`. Through the exact-operand form it gives `|shares·px − notional| ≤ u·notional`.
- The compound expressions are the λ step, the split and the liquidation proceeds. Each is expanded algebraically into single operations, and the products of two local errors are kept.

### 6A.2 Assumptions

| # | Assumption | Evidence / enforcement |
|---|---|---|
| A1 | Every engine operation on these paths is one correctly rounded IEEE-754 binary64 operation, round-to-nearest-even, with no fused multiply-add and no extended precision. | Python `float` and numpy float64 scalar arithmetic on x86-64 (DAY-29 integrity record: CPython 3.12.10, numpy 2.5.2, Windows x86-64). This is an assumption about the platform and is not checked by the run. |
| A2 | No value on these paths is non-finite. Every exact × or ÷ result on these paths is 0 or has magnitude ≥ 2⁻¹⁰²². | Checked at run time on every recorded and reconstructed value, and on the positive lower bounds of the values not recorded in I1 (`B̂ ≥ max n_i`, `P̂ ≥ B̂`). A violation is a G7/G8 failure, and the run aborts. |
| A3 | Every built-in `sum()` on these paths (`engine.py:159`, `:122`, `:236`) adds numpy float64 scalars. CPython therefore adds them one by one, left to right, and L2 applies. | **[V]** The summands are products or differences of numpy float64 array elements (`engine.py:158`, `:122`, `:198`, `:202-204`). CPython 3.12 uses compensated (Neumaier) summation only for exact `float` items. Synthetic check on 2026-10-19 in the project `.venv`: `sum` of `[1e16, 1.0, -1e16]` gives `0.0` for numpy float64 and `1.0` for Python floats. The recorded cells carry `np.float64(…)` (`run.py:120-125`).<br>**Paths and counts [V]:**<br>• `engine.py` uses only built-in `sum()` and no numpy reduction (`np.sum` / `.sum()`). The on-path sums are :159 (h_k items, `h_k` = `n_held`), :122 (h_T items) and :236 (m items, m = buy fills in the session).<br>• Each sum starts from the int 0, and `0 + x = x` exactly, so m items take exactly m − 1 rounded additions. That gives γ_{m−1}.<br>• L2 holds for any order, so the dict and ticker orders need not be reproduced.<br>• The `cash + Σ̂` addition is the separate ρ term. |
| A4 | The §3 state values `S`, `S'`, `M` and `M'` equal the engine's float64 values bit for bit, after every state transition. | **Premise; not proven.** §6A.6 separates the proven parts from the unobservable transitions. The checkpoints G5a–G5d are integrity checks, not a proof. |

**Values that are not claimed to be bit-identical.** The engine's cash, `K`, `n_i` when λ < 1, `B̂`, `P̂`, the running `flows`, the position sums and the pre-liquidation equity are not recorded in I1. They are **not reconstructed** for the bound. The bound uses only exact upper bounds on their magnitudes, derived from recorded values through L1–L3 (§6A.3).

### 6A.3 Exact values and bounds used

Per series and close k (exact rationals):

| Symbol | Definition | Kind |
|---|---|---|
| `Σ_k` | `Σ_j |S_j,k·M_j,k|` | exact, from §3 state |
| `σ̄_k` | `(u + (1+u)·γ_{h_k−1})·Σ_k`, where `h_k` = number of tickers held at close k, and `γ_0 = 0` | bound on the close position sum (L1 for products, L2 for the sum) |
| `C̄_k` (k < T) | `|E(k) − Σ_j S_j,k·M_j,k| + σ̄_k + u·|E(k)|` | bound on engine cash at close k, derived from `E(k) = fl(c_k + Σ̂_k)` |
| `C̄_0` | `E_0 = 100000` exactly (`engine.py:25`, `:36`) | exact |
| `Pre_T` | `|E_T| / (1−u) + (1+u)·s·(Σ_T + σ̄_T)` | bound on pre-liquidation equity, from `E_T = fl(pre − Ĉ)` |
| `C̄_T` | `(1+u)·Pre_T + Σ_T + σ̄_T` | bound on engine cash at the last close |
| `U` chain | `U ← (U + |x|)·(1+u)` from `U = C̄_{k−1}`, for each cash credit x, with `|x| ≤ (1+u)·|S·d|` or `(1+u)·|N − C|` (L3) | bound on intermediate cash values within the session |

### 6A.4 Daily path (G7)

**Exact identity** (algebra on `engine.py`):

`ε_k = (ρ_k + σ_k) − (ρ_{k−1} + σ_{k−1}) + Σ_div(α + β) + Σ_split χ + Σ_sell(ν + μ + π·V + β) + Λ_k + L_T`

Here ρ is the rounding of `cash + Σ̂`, σ is the rounding of `Σ̂` relative to `Σ S·M`, Λ_k is the buy step, and L_T applies on the last session only. For k = 1, the k − 1 terms are 0, because E(0) = E_0 exactly and nothing is held.

| # | Operation (`engine.py`) | Local error and exact bound |
|---|---|---|
| D1 | `amt = S·d` (:57) | `α = amt − S·d`: `|α| ≤ u·|S·d|` (exact-operand form) |
| D2 | `cash += amt` (:71) | `|β| ≤ u·U` after the update (result form + L3) |
| D3 | split `S' = S·q`, `M' = M/q` (:64-65) | `S'·M' − S·M = S·q·χ_M + χ_S·M/q + χ_S·χ_M`, where `|χ_S| ≤ u·|S·q|` and `|χ_M| ≤ u·|M/q|`. Hence `|·| ≤ (2u + u²)·|S·M|` |
| D4 | sell `N = qty·px` (:83) | `|ν| ≤ u·|qty·px|` |
| D5 | `net = N − C` (:87) | `|μ| ≤ u·|N − C|`, with N and C as recorded; the recorded C enters both sides identically |
| D6 | `cash += net` (:207, :220) | `|β| ≤ u·U` after the update |
| D7 | partial sell `S_k = S' − qty` (:85) | `|π| ≤ u·|S' − qty|`, weight V = px (G4). Full sells set `0.0` with `qty = S'`, so π = 0 |
| D8–D14a | **buys, recorded λ = 1.0.** Here `notional_i = n_i` exactly; `B = Σn_i`; `B̂ = B + ω_B` (:236); `ŝ = fl(1+s)`; `P̂ = fl(B̂·ŝ)`; `cash = fl(K − P̂)` (:243) | Exact identity: `Λ = −B·ω_s − ŝ·ω_B − ω_P + β_b + Σ_i(φ_i + π_i·V + κ_i)`. Bounds: `|ω_s| ≤ u(1+s)`; `|ω_B| ≤ γ_{m−1}·B` (all n_i > 0); `ŝ ≤ (1+u)(1+s)`; `|ω_P| ≤ u·(1+u)(1+s)(1+γ_{m−1})·B`; `|β_b| ≤ u·C̄_k`, because the cash after buys is the cash at close k; `|φ_i| ≤ u·notional_i`; `|π_i| ≤ u·|S' + shares_i|`; `|κ_i| ≤ u·s·notional_i` |
| D14b–c | **buys, recorded λ < 1.** `λ = fl(K/P̂)` (:240), `notional_i = fl(λ·n_i)` (:242), `cash ← 0.0` exactly (:243) | Exact identity: `Λ = −λ(B·ω_s + ŝ·ω_B + ω_P) + P̂·ω_λ + (1+s)·Σω_i + Σ_i(κ_i + φ_i + π_i·V)`. Since `n_i` is not recorded, use `B ≤ B̄ = Σ notional_i / (λ(1−u))` (L1 on `notional_i`). Bounds: `|ω_B| ≤ γ_{m−1}·B̄`; `|P̂| ≤ P̄ = (1+u)²(1+s)(1+γ_{m−1})·B̄`; `|ω_P| ≤ u·P̄`; `|ω_λ| ≤ u·λ`; `|ω_i| ≤ u·notional_i`; `|κ_i| ≤ u·cost_i`; φ_i and π_i as for λ = 1 |
| D15–D17 | close: `pos = S·M` (:158), `Σ̂` (:159), `E = cash + Σ̂` (:159) | `|σ_k| ≤ σ̄_k`; `|ρ_k| ≤ u·|E(k)|` for k < T; the same terms at k − 1 |
| D19 | last session (:122-123, :254): `Ĝ = Σ̂'`, `Ĉ = fl(Ĝ·s)`, `E_T = fl(pre − Ĉ)` | Exact identity: `ρ_T + σ_T − s·σ'_T − κ_L + ρ_L` replaces `ρ_T + σ_T`. Bounds: `|σ_T|, |σ'_T| ≤ σ̄_T`; `|ρ_T| ≤ u·Pre_T`; `|κ_L| ≤ u·s·(Σ_T + σ̄_T)`; `|ρ_L| ≤ u·|E_T|` |

- `m` is the number of buy fills in the rebalance.
- A missing open or a missing close copies a carried value and adds no operation.
- E_open, targets and turnover (:187-204, :210-213) change no state that enters ε.
- Fills on the pending-sell path (:217-221) use D4–D7.

**τ_k is the sum of all the bounds above for session k.**

### 6A.5 Per-ticker path (G8)

**Exact identity.** `Σ_k pnl_j,k` telescopes exactly (§4 uses the same `S` and `M` on consecutive sessions, and S = 0 before the segment). It differs from the engine's `flows[j]` (`metrics.py:126`, `:138`; written with `repr`, `run.py:103-118`) by exactly the sum of the local errors below. Recorded costs enter both sides identically. The running flows value `F` is bounded by L3 from F = 0 (`flows.get(j, 0.0)`).

| # | Operation (`engine.py`) | Local error and exact bound |
|---|---|---|
| P1–P2 | `amt = S·d` (:57); `F += amt` (:60) | `u·|S·d|`; `u·F̄` after the update, with `F̄ ← (F̄ + (1+u)|S·d|)(1+u)` |
| P3 | split (:64-65) | `(2u + u²)·|S·M|` |
| P4–P7 | sell: `N = qty·px` (:83), `net = N − C` (:87), `F += net` (:88), partial `S − qty` (:85) | `u·|qty·px|`; `u·|N − C|`; `u·F̄` after the update, with `F̄ ← (F̄ + (1+u)|N − C|)(1+u)`; `u·|S' − qty|·V` (0 for a full sell) |
| P8–P11 | buy: `shares = N/px` (:104), `S + shares` (:104), `F − N`, then `− C` (:106) | `u·N`; `u·|S' + shares|·V`; `u·Ḡ` with `Ḡ = (F̄ + N)(1+u)`; `u·F̄` with `F̄ ← (Ḡ + C)(1+u)` |
| P12–P15 | liquidation, if held at segment end: `p = S·M` (:125), `ŝ⁻ = fl(1−s)`, `net_L = fl(p·ŝ⁻)`, `F += net_L` (:129) | With `e₁ = p − S·M`, `e₂ = ŝ⁻ − (1−s)`, `e₃ = net_L − p·ŝ⁻`: `net_L − (1−s)·S·M = S·M·e₂ + e₁(1−s) + e₁e₂ + e₃`, so `|·| ≤ u(1−s)|S·M|·(2 + u + (1+u)²)`. The final addition is bounded by `u·|symbol_pnl_contribution_j|` (result form; the recorded value is that result) |

**τ_j is the sum of these bounds over the segment.** For a ticker that was never held, τ_j = 0.

### 6A.6 A4: state equivalence, evidence and gap

**Proven facts [V].**
- **V1, engine source identity.** The current `backtest/v2/engine.py` raw SHA-256 `35b43d95…c59e` equals `reproducibility.engine_sha256` in both the DAY-19 and DAY-21 run summaries.
- **V2, loader source identity.** `backtest/v2/data.py` at `fee0e9e` and `5ed3d0a` hashes to the DAY-19 (`e4c6d3ce…`) and DAY-21 (`20134c90…`) recorded values. Later commits only added to `data.py`: an import and `load_stage_f`. The source of `load_stage_r`, `load_stage_h`, `load_events` and `MarketData` is unchanged at the AST level. Their helpers are unchanged or changed by additions only: `verify_snapshot` and `acquisition/contract.py` are unchanged, and `acquisition/v2/sessions.py` has additions only.
- **V3, exact records.** Every recorded float round-trips exactly. `run.py:120-125` writes `repr`, and `run.py:103-105` writes JSON floats as `repr`.
- **V4, entry state is observed.** A buy into a zero position sets `S = 0.0 + shares = shares` exactly, so the state after every entry equals the recorded `shares`.
- **V5, pre-exit state is observed.** A full sell passes `qty = book.shares[j]` (`engine.py:199-200`, `:219-220`), so the recorded `qty` is the engine's `S'` immediately before the exit.
- **V6, closes are complete.** `missing_bars` counts NaN closes over the whole loaded array (`data.py:135`, `:212`). It is 0 for both snapshots, so `M_k = close[k,j]` at every close. Opens are **not** covered by `missing_bars`, so G4 and an explicit NaN-open check are required.

**State transitions (`engine.py`) and the evidence for each:**

| Transition | Operation | State after it is recorded? | Equality with the engine |
|---|---|---|---|
| T1 entry buy (S' = 0) | `S ← 0.0 + fl(N/px)` (:104) | **Yes** (V4) | Proven from the records |
| T2 add-on buy (S' ≠ 0) | `S ← fl(S' + fl(N/px))` (:104) | No | Deduced only (D below) |
| T3 partial sell | `S ← fl(S' − qty)` (:85) | No | Deduced only |
| T4 full sell | `S ← 0.0` (:85) | Pre-state yes (V5), post-state exact | Proven at this point (G5a) |
| T5 split, held | `S ← fl(S·q)` (:64) | No | Deduced only |
| T6 split, mark | `M' ← fl(close_{k−1}/q)` (:65) | No | Deduced only; one operation on recorded or snapshot operands |
| T7 close mark | `M ← close[k,j]` (:113-117) | Snapshot value | Holds if the loader arrays equal the engine's (D3) |
| T8 segment end | — | `final_net_mark` (non-injective) | Integrity check only (G5c) |

**Deduction D.** If D1–D3 all hold, the reconstruction equals the engine after every transition, because a correctly rounded operation is a function of its operands.
- **D1, A1 on both platforms.** This is an assumption. The DAY-25B exact reproduction of 36 outputs supports deterministic behaviour on this platform class, but does not prove IEEE conformance.
- **D2, same transitions in the same order with the same operands.**
  - Which transitions occur comes from the recorded fills (session, ticker, side, `shares`) and from `q ≠ 1` on a held ticker.
  - The operations are those of `engine.py` (V1).
  - At most one fill per ticker per session is checked exactly at run time.
  - Whether the reconstruction code implements these operations correctly is an implementation property. Review and synthetic tests can establish it; the data cannot.
- **D3, same input arrays.** The snapshot bytes are pinned by G2 and the loader source by V2. But the loaded arrays themselves were never recorded, and the library versions used by DAY-19/21 are not recorded alongside them. The only exact data checks are G4 (opens at traded cells) and, indirectly, G5a–G5d.

**Gap (unresolved).**
- T2, T3, T5 and T6 leave no recorded post-state. G5a–G5d test the chain only at entries, exits, the segment end and through aggregate flows, and the aggregate checks are non-injective. They are integrity checks, not proof of equality at every step.
- Bounding the reconstruction error instead does not help. Under D1–D3 the error is exactly 0. If D2 or D3 fails, nothing recorded bounds it.
- So A4 is a premise of τ, not a proven fact. The only way to observe these intermediate states would be to record them by re-running the engine, which is outside DAY-30's no-replay methodology.

**Checkpoints retained as integrity checks (G5):**
- **G5a:** at each full sell, recorded `shares` = reconstructed `S'`.
- **G5b:** at each buy, recorded `shares` = float64 `notional/price`.
- **G5c:** `final_net_mark` = float64 `fl(fl(S_T·M_T)·fl(1 − s))`.
- **G5d:** the float64 flows-chain replication = `symbol_pnl_contribution`.

**Runtime checks added (in G4):** at most one fill per ticker per session, and no NaN open on any session where a ticker is held or traded.

**`γₙ` scope.** The `γₙ` summation bounds (L2, A3) cover the engine's summation rounding only. They do not resolve A1, A4 or D3.

### 6A.7 Evaluation (specification)

- **Exact side.** Every float64 input becomes `fractions.Fraction(x)`, the exact binary value:
  - recorded cells are parsed by the DAY-29 rule (§3);
  - snapshot arrays are read through the I2 loaders;
  - `s`, `E_0`, `u` and γ are exact.
- **Exact computations.** ε_k, every bound, τ_k, τ_j and every G7/G8 comparison are computed in `Fraction`. No float operation enters a gate decision.
- **Float side.** Float64 arithmetic is used only for (i) the §3 state updates and (ii) the G5a–G5d checkpoint recomputations, which are compared with `==`.
- **Reporting.** O3 reports, per session, `ε_k` and `τ_k` in a CSV, and per series the maximum `|ε_k|/τ_k` with its session. For every ticker it reports `τ_j` and the G8 difference.
- **Nothing evaluated yet.** No bound has been evaluated on real artifacts, and nothing in this document predicts its size.

---

## 7. Interpretation limits

1. Holdout evidence is historical pseudo-out-of-sample, not a blind prospective evaluation.
2. **Survivor-universe bias:** the frozen 25-symbol universe was chosen with present knowledge.
3. **Both sets are outcome-dependent:** the day sets were selected by realised `l_d`, and the ticker sets by realised P&L. Large shares in O1 are partly mechanical.
4. Attribution is accounting, not causation. A ticker's contribution says nothing about the portfolio without that ticker; that was DAY-25B D1/D2's counterfactual question.
5. Cross-day sums of daily simple contributions do not compound and do not decompose CAGR or `L`.
6. No significance is tested. DAY-30 results are not evidence of strategy robustness, statistical significance, profitability, live performance or Sharia compliance.
7. **Conditional reconciliation.** G7/G8, and every output that depends on them, are conditional on the unproven premises A1 and A4 (§6A). D3, the identity of the loaded input arrays with the engine's, is likewise not proven. G5a–G5d are integrity checks, not proof of bit-identical state at every step.

## 8. Exclusions

- Re-running DAY-29, DAY-25B or the engine.
- Any replay or simulation.
- Re-selecting day or ticker sets, or ranking tickers by DAY-30 results.
- New strategies, parameters, data acquisition or thresholds.
- Any F003, `fwd-gate2`, P001, forward or sealed data.

## 9. Relation to earlier work

- **DAY-29:** supplies the day sets (I3), the input-pinning rules (G1), the float-cell parser rule (§3) and the K2 interval convention (G5).
- **DAY-25B:** supplies the D2 ticker sets (I4); D5 `flows_signed` equals I1 `symbol_pnl_contribution` **[V]**.
- Neither study is changed.

## 10. Implementation and run (NOT IMPLEMENTED; NOT AUTHORIZED)

- **Proposed:** `scripts/day30_attribution.py`, with outputs under `artifacts/day30/run/` written atomically and never overwriting, and the gate record under `artifacts/day30/preflight/`, written once.
- **Interpreter:** the project `.venv` (Python 3.12.10, numpy 2.5.2, `exchange_calendars` 4.13.2).
- **Run command** (from the repository root; valid only after every item below is met):

  `.venv/Scripts/python.exe -m scripts.day30_attribution --authorization DAY30-ATTRIBUTION-RUN`

  The script refuses before reading any input if:
  - the `--authorization` value is not exactly `DAY30-ATTRIBUTION-RUN`;
  - this document's LF-normalised SHA-256 differs from the approved hash in §12.

  The token is recorded in the run summary. The token alone authorizes nothing; it is valid only together with item 4 below.
- **Before any run, all of the following are required:**
  1. OD-1 and OD-2 decided (§11);
  2. this document approved and frozen (§12);
  3. a reviewed implementation with synthetic tests, including a hand-checked attribution on a fixture with a split, a dividend, a resize, a full sell, a missing open and the segment-end liquidation, plus a mis-assignment fixture that G8 must catch. Synthetic tests must also check each §6A exact identity: on fixtures with rebalances at λ = 1 and λ < 1, a split, a dividend and the liquidation, the identity's local-error sum reproduces ε exactly when the engine's unrecorded intermediates are known;
  4. a separate, explicit run authorization.

## 11. Owner decisions

| # | Decision | Status, evidence and proposal |
|---|---|---|
| **OD-1** | **Tolerances τ_k (G7) and τ_j (G8).** | **Decided by the owner (2026-10-19): G7/G8 use the §6A conditional bounds, valid only under A1 and A4.**
- A1 and A4 are not proven by the current artifacts, and A4 is not to be pursued through engine replay.
- G5a–G5d are integrity checks only.
- The `γₙ` bounds do not resolve A1, A4 or D3.
- DAY-30 results are labelled conditional and descriptive (header, §5, §7).

**History:** The 2026-10-19 first-order version is withdrawn. Its claimed bound on the omitted second-order terms and its surrogate claim had no derivation, and its Neumaier-dominance argument was unsupported. All three are replaced by §6A.1–§6A.6. The owner's `n·u·Σ|operands|` form is used with multiplier 1.0 in its rigorous instances: `u·|x|` per single operation (n = 1), `γ_{m−1}·Σ|x_i|` per m-term sum (γ_n = n·u/(1 − n·u), the derived constant, not a safety factor), and explicit (1+u) factors and error products. **Repository evidence:**<br>• Protocol v2 compares reproductions exactly with no tolerance (DAY-25B preflight `equality`: "exact float64 (==); no tolerance, rounding or re-baselining") **[V]**.<br>• v2.0.4 evaluates comparisons in exact rationals over precision-derived intervals, with no fixed constant (`crosscheck.py:7`, `46-50`) **[V]**.<br>• The only fixed numeric tolerances belong to unrelated v1 code (`backtest/exit_decomposition.py:61`, `breakeven_05.py:287`, `portfolio.py:57`) **[V]**.<br>• No repository convention covers reconciling exact attribution against float64 engine accounting; §6A follows v2.0.4 in using exact rationals and derived, not chosen, bounds. |
| **OD-2** | **Pin the DAY-29 outputs.** | **Resolved (2026-10-19).**<br>• Committed unchanged in `067295f1e82e9d1c2dc8282e6c702fd09263a22c`.<br>• The commit holds 15 files: `artifacts/day29/run/{k1.json, run_summary.json}`, `artifacts/day29/run/{5bps,10bps}/{t0,t1,t2,t3,k2,k3}.json` and `artifacts/day29/preflight/shared_integrity_record.json`.<br>• For each file, blob SHA-256 = raw working-file SHA-256 = its pin in `run_summary.json` **[V]**. |

No other methodological item is open. A1, A4 and D3 remain unproven premises (§6A.6); they are disclosed, not resolved.

## 12. Owner approval and freeze

**Approval.** The owner approves this document by quoting the exact LF-normalised SHA-256 of this file as presented for approval. Any edit after that requires a new hash and a new approval.

**Freeze procedure** (DAY-25B / DAY-29 §14 convention; a separate commit authorization is required):
1. Verify that the file's LF-normalised SHA-256 equals the approved hash.
2. Change only:
   - the Status row to **FROZEN — NOT AUTHORIZED TO RUN**;
   - the Freeze row to the approved pre-freeze hash, the freeze date and the approval reference.
3. Commit this file alone. Record the frozen file's SHA-256 in the commit message.

**What approval and freezing do not authorize:** implementation review, synthetic tests, or running `scripts/day30_attribution.py`. Each of these needs its own explicit owner authorization (§10).
