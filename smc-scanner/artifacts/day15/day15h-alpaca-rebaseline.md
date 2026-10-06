# DAY-15H — Alpaca SIP Research Re-baseline of the DAY-04 Baseline

## Research gate: **FAIL**

| Item | Value |
|---|---|
| Primary metric (protocol v1.1 §12, §21) | mean net trade return at **5 bps per side** |
| Value | **−0.1076 %** per trade |
| Condition | ≥ 0 → **not met** |
| Hard requirements | data integrity PASS; PIT PASS; determinism PASS; reproducibility PASS |
| Decision | **FAIL**: the frozen DAY-04 baseline does not pass the predefined v1.1 research gate. Under protocol v1.1 §21 no OOS bar is acquired for this candidate. |

No other threshold was applied. Trade count, drawdown, breadth, concentration and benchmark margin are reported descriptively only. No variant was selected, no parameter was changed, and no further hypothesis was run.

**No OOS data was downloaded or evaluated.**

---

## 1. Protocol version
v1.1, `artifacts/day15/protocol-v1.1.md` (SHA-256 `2b096cb5dd372d23cccda5e21ab410842730638c4dd7104a87383fa0e7746592`, commit `57f4ecef`), §20 candidate and §21 research re-baseline gate. Family F-BASE; provenance PREDECLARED.

## 2. Commit
- **HEAD:** `57f4ecefc5861476d1b5ce43611cafe810843fb3`.
- **Working tree:** dirty by instruction (no commit). The uncommitted files and their SHA-256 are recorded in `day15h-alpaca-rebaseline.json → reproducibility.uncommitted_files`:
  - `data/v11_research_loader.py` — `d0faaf60…`;
  - `backtest/v11_rebaseline.py` — `e836b540…`;
  - `scripts/rebaseline_day15h.py` — `72efb42a…`;
  - `tests/test_day15h_rebaseline.py` — `fc0d623a…`;
  - the DAY-15G report and integrity JSON, and the pre-existing tar.
- **Strategy and engine:** unchanged. `strategy/day/vwap_momentum.py` SHA-256 `22b63764…`, last commit `dcebe47`.

## 3. Dataset
- **Snapshot:** `data/oos_cache/protocol_v1.1/research/snapshots/research_20261006T095201Z/` (DAY-15G, 4,050 / 4,050 units).
  - `files.json` SHA-256 `b43b8996d1e45a58c61aba74bc8bc83b173809e554f4c0c125c0f4f5f6b95139`;
  - `units.json` SHA-256 `6a0466192a87ce53cb27d8b5e55a4fb510f8e790d8cc75548b6e9987a3b76b74`.
- **Integrity:** every data file was re-hashed before use, and again after the run (unchanged).

## 4. Provider / feed / adjustment
Alpaca Market Data v2 historical stock bars, `feed=sip`, `adjustment=raw`, 5Min + 15Min. Inputs were OHLCV only; `provider_vwap` and `trade_count` were dropped by the loader.

## 5. Research range
2026-07-02 → 2026-09-25: 60 XNYS sessions, all present for all 25 symbols (78 × 5m / 26 × 15m per session, calendar grid exact).

## 6. Warmup range
- 2026-06-03 → 2026-07-01: 20 sessions.
- Passed to the engine as indicator history in one continuous series with the research bars.
- Warmup trades are simulated by the unchanged engine but **never evaluated**. Only signals whose signal bar is in a research session count.

## 7. Embargo treatment
- 2026-09-28 is classified as EMBARGO in the snapshot.
- **It was never loaded into the engine.** No signal, trade, metric or benchmark involves it. Evaluated embargo trades: **0**.
- The last bar given to the engine is `2026-09-25T19:55:00Z`.

## 8. Universe
The frozen 25: AAPL, ADBE, AMAT, AMD, AMZN, AVGO, COST, CRM, CSCO, GOOGL, INTC, JNJ, JPM, KO, META, MSFT, MU, NFLX, NVDA, ORCL, PEP, QCOM, TSLA, WMT, XOM. All 25 were tested; none was excluded.

## 9. Strategy configuration (unchanged DAY-04)
DAY-01 VWAP momentum (`strategy/day/vwap_momentum.py`), fast causal engine `backtest/day_engine.py::run_day_backtest(use_fast_engine=True)`:
- valid statuses: {DETECTED, CONFIRMED};
- RSI(14), RVOL with 20-session lookback and `min_sessions=1`, project VWAP from OHLCV, 15m structure context;
- no H1 / H3 / H4 / H5 / H6, no breakeven, no alternative exit.

## 10. Execution configuration (`ExecutionConfig()` defaults)
- SIGNAL_LOW stop (VWAP / 0.99 fallbacks); 2.0R target; STOP_FIRST;
- forced exit at the 15:55 ET bar close; entry at the next 5m bar OPEN; long-only; one position per symbol;
- `slippage_bps` 0, `commission_per_share` 0, with costs applied post hoc;
- `max_trades_per_session` None, `entry_window` None, `breakeven_trigger_r` None, `atr_stop_multiplier` None.

## 11. Full metrics (pooled over all research trades, entry order)

| Metric | Value |
|---|---|
| Trades | 5,850 |
| Wins / losses / breakevens | 1,768 / 4,079 / 3 |
| Win rate (0 bps) | 30.22 % |
| Profit factor (0 bps) | 0.944 |
| Expectancy (mean trade return, 0 bps) | −0.0077 % |
| Average R | −0.132 R |
| Median R | −1.00 R |
| Total R | −771.84 R |
| R standard deviation | 1.430 |
| Setup status of trades | DETECTED 5,721 / CONFIRMED 129 |
| Exit reasons | stop 3,894 / target 1,494 / forced EOD 462 |

**Integrity counters** (research sessions only = warmup+research run minus warmup-only run):
- candidate signals 21,907;
- skipped (position open) 15,703;
- insufficient data 0;
- same-bar ambiguity 729;
- `simulation_none` 354;
- cap / window rejects 0 / 0;
- research sessions evaluated: 60 per symbol;
- embargo excluded: 1 session (never loaded).

## 12. Per-symbol metrics

| Symbol | Trades | WR % | Strat 0 bps % | 5 bps % | 10 bps % | B&H % | PF | Total R | Max DD % |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | 296 | 33.8 | +10.44 | −17.86 | −38.90 | +15.95 | 1.37 | −23.3 | 2.54 |
| ADBE | 206 | 35.0 | +12.85 | −8.16 | −25.25 | +9.28 | 1.40 | −2.4 | 6.53 |
| AMAT | 175 | 25.7 | −14.32 | −28.08 | −39.62 | −26.17 | 0.67 | −42.4 | 19.26 |
| AMD | 155 | 38.1 | +5.65 | −9.52 | −22.51 | +17.07 | 1.17 | +20.3 | 6.10 |
| AMZN | 269 | 28.3 | −11.95 | −32.72 | −48.59 | +3.30 | 0.61 | −53.5 | 12.69 |
| AVGO | 238 | 28.6 | −6.07 | −25.96 | −41.64 | −3.53 | 0.83 | −41.4 | 10.41 |
| COST | 262 | 27.5 | −7.75 | −29.01 | −45.37 | −0.44 | 0.69 | −59.7 | 9.05 |
| CRM | 166 | 32.5 | +8.23 | −8.32 | −22.35 | +43.59 | 1.32 | −11.9 | 5.39 |
| CSCO | 205 | 28.3 | −4.22 | −21.97 | −36.43 | −8.89 | 0.86 | −41.5 | 9.58 |
| GOOGL | 248 | 26.2 | −3.44 | −24.65 | −41.20 | −4.37 | 0.89 | −60.7 | 5.57 |
| INTC | 182 | 29.1 | −6.09 | −21.71 | −34.74 | −4.68 | 0.88 | −19.4 | 18.73 |
| JNJ | 241 | 33.2 | +0.91 | −20.70 | −37.68 | +6.02 | 1.04 | −19.2 | 5.07 |
| JPM | 318 | 30.8 | −7.19 | −32.47 | −50.87 | +1.47 | 0.72 | −42.5 | 7.73 |
| KO | 262 | 32.1 | +3.51 | −20.34 | −38.70 | +7.57 | 1.19 | −20.1 | 2.42 |
| META | 177 | 29.4 | −6.72 | −21.85 | −34.53 | +23.77 | 0.76 | −20.1 | 8.24 |
| MSFT | 242 | 30.2 | −2.60 | −23.54 | −39.97 | +34.23 | 0.91 | −46.3 | 6.24 |
| MU | 186 | 28.5 | −0.99 | −17.79 | −31.74 | +3.88 | 0.99 | −48.0 | 8.67 |
| NFLX | 246 | 29.3 | +1.48 | −20.65 | −37.95 | −5.41 | 1.06 | −41.8 | 5.58 |
| NVDA | 227 | 29.1 | +0.16 | −20.18 | −36.39 | +14.16 | 1.01 | −36.0 | 7.25 |
| ORCL | 224 | 26.8 | −13.05 | −30.50 | −44.45 | −4.33 | 0.71 | −45.5 | 13.16 |
| PEP | 323 | 31.9 | −4.16 | −30.62 | −49.77 | −10.24 | 0.84 | −25.2 | 6.33 |
| QCOM | 234 | 31.2 | −8.88 | −27.89 | −42.94 | +10.85 | 0.81 | −10.2 | 15.15 |
| TSLA | 186 | 27.4 | +5.02 | −12.80 | −27.60 | −13.10 | 1.16 | −11.9 | 6.75 |
| WMT | 296 | 29.4 | +3.90 | −22.72 | −42.52 | −1.24 | 1.16 | −45.0 | 2.94 |
| XOM | 286 | 32.9 | +1.19 | −23.98 | −42.89 | +17.07 | 1.05 | −24.2 | 3.93 |

Per-symbol counters (candidates, skipped, ambiguity, `simulation_none`) and mean net trade returns are in the JSON.

**Distribution:**
- positive strategy return at 0 bps: **11 / 25**; negative: 14;
- positive at 5 bps: **0 / 25**;
- outperforming buy & hold: **8 / 25**;
- positive total R: 1 / 25 (AMD);
- median / mean symbol strategy return: −2.60 % / −1.76 %;
- top-2 share of total R: not meaningful (total R negative).

## 13. Benchmark
- **Method:** equal-weight per-symbol buy & hold from the first research RTH open (2026-07-02 09:30 ET) to the last research RTH close (2026-09-25), on the same Alpaca SIP raw data, the same 25 symbols and the same 60 sessions.
- **Equal-weight benchmark return: +5.03 %** (median +3.30 %).
- **Strategy:**
  - mean symbol return (0 bps) −1.76 %, strategy minus benchmark −6.79 pp;
  - pooled compounded 0 bps −39.86 %.
- The yfinance benchmark was not used as input.

## 14. Transaction-cost results (formula `(1+g)(1−s)/(1+s) − 1` on every trade)

| Per side (≈ round trip) | Compounded return | Mean net trade return | Median net trade return | Win rate | PF | Max DD (pooled, entry order) |
|---|---|---|---|---|---|---|
| 0 bps (0) | −39.86 % | −0.0077 % | −0.0498 % | 30.22 % | 0.944 | 58.05 % |
| **5 bps (≈ 10 bps)** | **−99.83 %** | **−0.1076 %** | −0.1497 % | 24.12 % | 0.485 | 99.84 % |
| 10 bps (≈ 20 bps) | −99.9995 % | −0.2074 % | −0.2495 % | 17.59 % | 0.280 | 99.9995 % |

Compounding all 5,850 trades sequentially at one unit is not a portfolio simulation (research-protocol §7, limitation 1). The pooled max drawdown is defined on that chain.

**Time-of-day breakdown** (mean net trade return at 5 bps):
- 09:30–10:00: −0.101 % (870 trades);
- 10:00–11:00: −0.095 % (752);
- 11:00–12:00: −0.128 % (641);
- 12:00–14:00: −0.102 % (1,553);
- 14:00–15:00: −0.115 % (910);
- 15:00–16:00: −0.111 % (1,124).

**Monthly breakdown** (mean net trade return at 5 bps):
- July: −0.101 % (2,036 trades);
- August: −0.103 % (2,173);
- September: −0.122 % (1,641).

All of this is descriptive only.

## 15. Old DAY-04 comparison — HISTORICAL REFERENCE — NOT CURRENT GATE RESULT

| Metric | Old DAY-04 yfinance (**historical reference**) | New Alpaca SIP v1.1 (**authoritative**) | Difference (new − old) |
|---|---|---|---|
| Trades | 5,691 | 5,850 | +159 |
| Candidate signals | 21,087 | 21,907 | +820 |
| Skipped signals | 15,057 | 15,703 | +646 |
| Same-bar ambiguity | 693 | 729 | +36 |
| Win rate | 30.42 % | 30.22 % | −0.20 pp |
| Profit factor | 0.939 | 0.944 | +0.005 |
| Average R | −0.130 | −0.132 | −0.002 |
| Median R | −1.00 | −1.00 | 0 |
| Total R | −738.98 | −771.84 | −32.86 |
| R std | 1.430 | 1.430 | 0.000 |
| Mean net trade return, 0 bps | −0.0083 % | −0.0077 % | +0.0007 pp |
| **Mean net trade return, 5 bps** | −0.1083 % | **−0.1076 %** | +0.0007 pp |
| Mean net trade return, 10 bps | −0.2081 % | −0.2074 % | +0.0007 pp |
| Compounded 0 / 5 / 10 bps | −41.19 / −99.80 / −99.9993 % | −39.86 / −99.83 / −99.9995 % | +1.33 / −0.03 / ≈0 pp |
| Positive symbols (0 bps) | 11 / 25 | 11 / 25 | 0 |
| Outperformed B&H | 9 / 25 | 8 / 25 | −1 |
| Mean symbol strategy return | −1.86 % | −1.76 % | +0.10 pp |
| Benchmark (equal-weight B&H) | +5.05 % | +5.03 % | −0.02 pp |

**Interpretation (data / methodology only):**
- The two baselines agree closely on every aggregate. The sign and the gate conclusion are identical: both are negative after 5 bps per side.
- Per-symbol trade counts differ by up to ±35 trades (e.g. PEP 351 → 323, TSLA 162 → 186).
- The differences are attributable to the documented changes only:
  1. **Provider and volume construction** (SIP consolidated, condition-filtered vs. yfinance): it changes the RVOL ≥ 2.0 classification and VWAP weights.
  2. **20-session warmup** (new in v1.1): the old run had thin RVOL baselines in early July. The warmup-mutation check below shows that research decisions depend on warmup history, as expected.
  3. **Raw vs. `auto_adjust=True` prices:** this matters only for scaling. No adjustment comparison was done.
- No attempt was made to reconcile the numbers, and nothing was tuned.

## 16. PIT tests

| Test | Result |
|---|---|
| **Future mutation:** all bars on/after 2026-09-14 for all 25 symbols mutated (prices ×1.3 with open/close swapped, volume ×3); re-run | **PASS**: 4,929 research trades before 2026-09-14 field-identical (0 symbols changed). The mutation was effective: later trades changed in 25 / 25 symbols. |
| **Warmup prefix:** the warmup-only run reproduces the full-run warmup trades | **PASS** (25 / 25). This validates the research-counter subtraction. |
| **Warmup mutation** (descriptive) | 3,900 of 5,850 research trades identical; 1,900 changed or new. This is a legitimate dependence through RVOL / RSI / structure history; not a gate condition. |
| **Embargo** | Not loaded; 0 evaluated embargo trades; the last loaded bar is 2026-09-25 19:55Z. |
| **Unit tests** | `tests/test_day15h_rebaseline.py`: 11 passed. The loader rejects ≥ 2026-09-29 bars, hash mismatches, `adj_close` and non-universe symbols; plus the cost formula and the gate rule. |

## 17. Deterministic re-run
**PASS.** The full baseline was run twice: trades SHA-256 `1757b91538e0a89167b8be2075857c94333a87dd9dd01214bcea5215041ccc3c` both times, and the pooled metrics were identical.

## 18. Research gate decision
**FAIL.** The primary metric is −0.1076 % < 0. All hard requirements passed, so the failure is solely the predefined sign condition. The candidate does not proceed to OOS under protocol v1.1, and no OOS acquisition is triggered.

## 19. Limitations / discrepancies
1. **Dirty tree:** the re-baseline code is uncommitted (by instruction). Its files are hashed in the JSON reproducibility block.
2. **Evaluation gate:** the engine has no native trade-window gate. Evaluation is restricted after simulation. This is exact here because positions never cross sessions and the session cap is off, and it was validated by the warmup-prefix check.
3. **Warmup is new:** the re-baseline differs from DAY-04 by provider and warmup together. Their individual contributions were not separated, because that would be an additional experiment.
4. **Inherited limitations** (research-protocol §7):
   - one-unit sequential compounding;
   - gap-through fills at level;
   - intrabar order unresolved, with 729 same-bar ambiguities resolved STOP_FIRST;
   - no spread or impact model.
5. **Universe selection date UNKNOWN** (inherited).
6. **Raw prices:** no corporate-action event check was performed for the window (protocol §18: disclosed only).
7. **Memory note:** the full offline pytest suite was attempted once in DAY-15G and terminated by the environment for memory pressure at about 45%, with no failure observed. Focused tests were used.

## 20. Statement
**No OOS data was downloaded or evaluated.**
- No request was made to any market-data endpoint in DAY-15H.
- No bar dated on or after 2026-09-28 was read by the engine.
- Neither `data/cache/` nor `data/oos_cache/protocol_v1.0/` was used, and both are unchanged (checked against `integrity-baseline.json` before and after the run).

---

**Artifacts:**
- `artifacts/day15/day15h-alpaca-rebaseline.json` (full results);
- this report;
- the trade list in the session scratchpad only (`day15h_trades.csv`, not in the repo).

**Command:** `python scripts/rebaseline_day15h.py`. It ran from 2026-10-06T11:08:47Z to 11:14:57Z.
