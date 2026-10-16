# ORB SIP diagnostic: trade excursions (descriptive; not independent evidence)

Source: `artifacts/orb/sip_diagnostic/trades.csv` (101 trades) joined to the hash-pinned Alpaca SIP raw 5m RTH
snapshot `research_20261006T095201Z`, research segment 2026-07-02 to 2026-09-25. Loaded with
`backtest/orb_snapshot_input.load_research_frames` (pinned `files.json`, `units.json`, `run.json` hashes and every
parquet file hash re-verified) inside `scripts/backtest_orb.no_network()`. No strategy engine, no backtest, no
network, no new data. One-off analysis code was kept outside the repository.

Files: `trade_excursions.csv` (one row per trade), `summary.json` (grouped statistics and provenance), this report.

## Validations (all passed; any failure would have stopped before writing)

- 101 trades in `trades.csv`, equal to `metrics.json` `trades`; exit reasons only STOP and FORCE_EXIT_1555.
- Per trade: session bars ordered, unique and contiguous at 5 minutes; recomputed opening range equals
  `or_high` / `or_low`; `signal_time`, `entry_time`, `exit_time` are bars of the trade's session;
  entry = signal + 5 minutes; entry bar open equals `entry_open`; `risk_per_share = entry_open - stop`;
  `stop = or_low`; `target = entry_open + 2R`.
- No bar before the exit bar touched the stop or reached the target (consistent with the engine's first-touch rule).
- FORCE_EXIT_1555: exit bar is the 15:55 ET bar and its open equals `exit_raw`.
- STOP: exit bar low reaches the stop and `exit_raw = min(open, stop)`; no stop occurred on the entry bar.
- Each recorded signal satisfies the strategy's own conditions on these bars: close above OR high, close above VWAP
  (`indicators/vwap.compute_vwap`, RTH), volume ratio >= 1.5 (`indicators/volume.volume_ratio`, 20-bar).
- Sum of `pnl` equals `metrics.json` `total_pnl`.

## Definitions

Price-path measures use raw prices relative to `entry_open`, with R = `risk_per_share`. They are not P&L and include
no costs. Realised results are `pnl_after_costs` / `r_multiple_after_costs`, copied from `trades.csv`.

- Window: STOP trades use bars from entry through the stop bar; FORCE_EXIT_1555 trades use bars from entry up to,
  but not including, the 15:55 bar, plus that bar's open (the exit price).
- MFE: highest high in the window. For STOP trades the stop bar's high is excluded (`mfe_R`) and reported
  separately (`stop_bar_high`, `mfe_R_incl_stop_bar`), because the order of events inside a 5-minute bar is unknown.
- MAE: lowest low in the window (includes the stop bar's low for STOP trades).
- Reached +1R / +2R: a high in the window at or above entry + 1R / the target.
- Give-back (forced exits): MFE_R minus the raw exit position in R.
- Signal bar: close minus OR high (USD, % of OR high, and in units of the trade's R), VWAP margin (USD, %),
  volume, 20-bar volume average and ratio, using the strategy's indicator functions on the same research frames.

## Results

| Measure | STOP (n=13) median [p25, p75] | FORCE_EXIT_1555 (n=88) median [p25, p75] |
|---|---|---|
| MFE (R) | 0.25 [0.11, 0.54] | 0.54 [0.26, 0.94] |
| MFE (USD, raw) | 61.04 [27.11, 128.87] | 129.82 [63.49, 229.92] |
| MAE (R) | -1.05 [-1.10, -1.03] | -0.42 [-0.64, -0.22] |
| Time to MFE (min) | 5 [0, 15] | 102.5 [18.75, 246.25] |
| Reached +1R | 2 of 13 | 18 of 88 |
| Reached +2R | 0 | 0 |
| Give-back (R) | n/a | 0.47 [0.23, 0.71] |
| Signal close - OR high (R) | 0.19 [0.08, 0.26] | 0.18 [0.09, 0.26] |
| Signal close - OR high (%) | 0.22 [0.14, 0.33] | 0.36 [0.24, 0.68] |
| VWAP margin (%) | 0.63 [0.59, 0.81] | 0.99 [0.67, 1.27] |
| Volume ratio | 1.83 [1.76, 2.12] | 2.06 [1.71, 2.40] |
| Realised P&L after costs (USD) | -262.24 [-265.38, -259.53] | 4.66 [-83.91, 94.27] |

- STOP trades: no stop bar's high reached +1R or +2R. 6 of 13 had their best price on the entry bar (time to MFE 0).
  The two that reached +1R (AMAT 2026-08-13, NVDA 2026-09-16) did so 205 and 70 minutes after entry.
- STOP MAE can be below -1R (minimum -1.40R) because the stop bar's low traded through the stop; the backtest
  fills the stop at the stop price (or the bar open if it gapped below), so intrabar slippage past the stop is not
  modelled. This is a property of the existing engine, recorded here, not changed.

## Limitations

- 5-minute bars only: intrabar event order is unknown; no 1-minute data was used or acquired.
- Small samples (13 vs 88); descriptive statistics only, no significance testing.
- Raw prices; no corporate-action data; the first session (2026-07-02) has no prior close.
- SIP volume may differ from yfinance volume. Not compared or pooled with any yfinance artifact.
- Descriptive diagnostic on sessions already examined; not independent evidence or strategy validation.
  No strategy, parameter or risk-rule change follows from this analysis.
