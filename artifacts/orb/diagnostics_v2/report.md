# ORB diagnostics v2: entry features and conditional exit replay

Inputs: `artifacts/orb/smoke_test/` (trades, metrics, daily equity), `artifacts/orb/diagnostics/trade_excursions.csv`, bars `data/cache/<T>_5m.parquet`. No backtest rerun, no network, no strategy/config change. n = 95 executed trades over 60 yfinance-cache sessions: **descriptive only, no parameter is selected here.**

## 1. Entry features vs outcomes

Features use only bars <= the signal bar (volume ratio via `indicators.volume.volume_ratio`), plus the entry open for the %-of-price scalings. Spearman rank correlation; with n = 95 the two-sided 5% threshold is about |rho| >= 0.20, and 18 feature-outcome pairs are tested, so ~1 'significant' value is expected by chance alone.

| Feature | median | rho vs MFE_R | rho vs MAE_R | rho vs realised R |
|---|---|---|---|---|
| breakout_strength | 0.243 | -0.10 | +0.02 | -0.04 |
| volume_ratio | 1.938 | +0.07 | -0.07 | +0.11 |
| or_width_pct | 1.717 | -0.11 | -0.20 | +0.04 |
| stop_pct | 2.372 | -0.18 | -0.23 | +0.03 |
| signal_min | 15.000 | -0.08 | -0.01 | +0.11 |
| entry_min | 20.000 | -0.08 | -0.01 | +0.11 |

Tercile means (low / mid / high feature value; ~32 trades each):

| Feature | edges (min, q33, q67, max) | MFE_R | MAE_R | realised R |
|---|---|---|---|---|
| breakout_strength | 0.00308, 0.132, 0.302, 1.99 | 0.61 / 0.61 / 0.52 | 0.51 / 0.47 / 0.52 | -0.06 / 0.02 / -0.15 |
| volume_ratio | 1.52, 1.79, 2.1, 3.84 | 0.54 / 0.54 / 0.66 | 0.53 / 0.51 / 0.46 | -0.19 / -0.08 / 0.08 |
| or_width_pct | 0.489, 1.44, 2.35, 5.21 | 0.68 / 0.62 / 0.44 | 0.56 / 0.49 / 0.44 | -0.09 / -0.01 / -0.09 |
| stop_pct | 0.622, 1.83, 2.94, 6.1 | 0.61 / 0.71 / 0.42 | 0.65 / 0.40 / 0.44 | -0.22 / 0.13 / -0.09 |
| signal_min | 15, 15, 20, 85 | 0.53 / 0.66 / 0.55 | 0.52 / 0.48 / 0.50 | -0.22 / 0.05 / -0.01 |
| entry_min | 20, 20, 25, 90 | 0.53 / 0.66 / 0.55 | 0.52 / 0.48 / 0.50 | -0.22 / 0.05 / -0.01 |

Note: `signal_min` and `entry_min` differ by exactly 5 minutes for every trade, so they carry the same information.

## 2. Exit scenarios (conditional replay of the same 95 entries)

Replay calls the production `strategy.day.orb_rules.step_bar` and `close_trade` unchanged: STOP_FIRST, stop gap fills at the open, target fills at the target price, forced exit at the 15:55 open, 5 bps slippage and $0.005/share commission on both legs. Bars from the entry bar up to the first exit only. **Validation: the 2R variant reproduces all 95 smoke-test trades exactly (exit time, reason, P&L).**

| Variant | Net P&L | Net return | Total R | Mean R | Win rate | Max DD | STOP | TARGET | FORCE_EXIT | SESSION_END |
|---|---|---|---|---|---|---|---|---|---|---|
| target_1R | $-272 | -0.27% | -1.00 | -0.011 | 49.47% | -1.00% | 12 | 17 | 66 | 0 |
| target_1.5R | $-647 | -0.65% | -2.63 | -0.028 | 49.47% | -1.40% | 12 | 6 | 77 | 0 |
| target_2R_baseline | $-1,430 | -1.43% | -5.76 | -0.061 | 48.42% | -2.10% | 13 | 0 | 82 | 0 |
| no_target_1555 | $-1,430 | -1.43% | -5.76 | -0.061 | 48.42% | -2.10% | 13 | 0 | 82 | 0 |

**Caveat - this is not a backtest.** It holds the original 95 entries fixed. A different exit would change when capital and the 2-trade / -2R daily gate free up, and therefore which of the 59 rejected signals would have been taken; none of that portfolio-level substitution is modelled. Max DD is from the daily equity of these 95 trades only.

## 3. To freeze before an out-of-sample test

- Exit rule: one target multiple (or no target) and the 15:55 forced exit - chosen and written down before the test, not re-picked afterwards from these numbers.
- Same-bar signal ranking: one of the three point-in-time variants in `artifacts/orb/diagnostics/report.md` (or keep symbol order explicitly), with symbol order as the final tie-break.
- Entry filters: either none beyond the current rules, or a single filter with a threshold fixed in advance (no threshold taken from these terciles).
- Sample: a period that does not overlap 2026-07-02..2026-09-25, the data source (SIP preferred over the yfinance cache for volume), the 25-ticker universe, and a source-verified earnings calendar covering it.
- Costs (5 bps/side, $0.005/share/side), risk (0.25% of initial capital), daily limits, metrics and pass/fail criteria (including comparison with equal-weight buy & hold) defined before seeing the out-of-sample results.
