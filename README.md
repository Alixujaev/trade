# Swing Signal Bot

A **signal-only, paper-first** trading assistant for US equities on a swing timeframe
(daily bars, positions held days-to-weeks). It backtests strategies with realistic
costs, runs the *same* strategy code live to detect entry/exit signals, and pushes
Telegram alerts. **It does not place orders.**

See `SPEC.md` for the full engineering specification; this document is the practical
setup/run guide. Where the two disagree, `SPEC.md` wins.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

Edit `whitelist.txt` and replace the placeholder tickers with your own
sharia-compliant universe (see "Sharia screening" below — this is not done for you).

## Run

```bash
python -m tests.smoke_test   # offline correctness checks, must be green before anything else
python backtest_main.py      # backtest the whitelist universe, print a metrics table
python live_main.py          # one-shot: fetch latest data, alert on any signal change
python scan_main.py          # one-shot: scan the whitelist for price-action setups, journal + alert
```

`live_main.py` is meant to run once per day after the US close, via cron — see
`SPEC.md` §12. It is not a long-running process.

`scan_main.py` is the price-action Scanner's cron entry point — like `live_main.py`,
it's meant for once-a-day cron use, not an always-on process (swing trading needs
no such thing). **A Scanner alert means "go look" — it is NOT a trade signal.** It
flags that a price-action setup has formed and appends a row to `journal.csv`; it
never asserts an edge and is not connected to the strategies backtested/traded above.

## Telegram control bot (optional)

Instead of running `backtest_main.py`/`live_main.py` from a terminal, you can run a
long-lived process that listens for Telegram commands and replies in the chat:

```bash
python telegram_bot.py
```

This is an always-on process — a deliberate exception to this project's usual "no
always-on process" design (see `SPEC.md` §12) — leave the terminal open, or run it
under a process manager, while you want to use it. It only responds to the
`TELEGRAM_CHAT_ID` configured in `.env`; every other sender is silently ignored.

Commands (also shown via Telegram's native "/" menu, and as a persistent
reply-keyboard row under the chat input, once the bot has started once):

- `/run` — run one live signal check now, same as `python live_main.py`.
- `/backtest` — run a backtest over the whitelist, same as `python backtest_main.py`.
- `/status` — show each whitelist symbol's current stored position, instantly, with
  no network call.
- `/help` — list the commands.

Each Scanner alert (from `scan_main.py`/`Scanner`) carries inline buttons: a
"📈 Chart" link (TradingView) and "✅ Oldim" / "⏭ O'tkazib yubordim" — tapping
the latter records your decision straight into that setup's `journal.csv` row
(via `engine.scanner.update_journal_decision`), so `python telegram_bot.py`
must be running for these buttons to work.

Design rationale and testing approach:
`docs/superpowers/specs/2026-08-16-telegram-control-bot-design.md` (note: its
"No inline-button UI" non-goal was superseded — see git history for the
inline-button/keyboard addition).

## Architecture

```
core/       shared dataclasses (Signal, Trade, BacktestResult) + config
data/       DataSource interface + yfinance implementation
indicators/ sma, ema, rsi (Wilder), macd, atr, crossover/crossunder — the one place indicator math lives
signals/    Strategy interface + RsiStrategy, MacdStrategy, EmaCrossStrategy, CombinedStrategy;
            detectors.py — pure-function price-action trigger/enricher detectors + scan_symbol
screening/  ShariaFilter — whitelist-based universe gate
alerts/     AlertSink interface + Telegram implementation
broker/     ExecutionAdapter interface — no implementation in v1.0, deliberately
engine/     backtest.py (run_backtest, compute_metrics), live.py (LiveEngine),
            and scanner.py (Scanner — journal, state, alert-on-change for price-action setups)
```

`journal.csv` (written by `Scanner`) is a user-maintained decision log, not an
automated record: each row is a detected setup plus empty `decision`/`outcome`
columns you fill in yourself. That's the point of the tool — it turns "eyeballing
a chart" into a measurable question you can review later, instead of asserting an
edge on your behalf.

Three seams keep the system broker/provider-agnostic (`DataSource`, `AlertSink`,
`ExecutionAdapter`): strategy and engine code depend only on these interfaces, never
on a concrete provider. Swapping data or execution providers later means writing one
new adapter, not touching `signals/` or `engine/`.

**Backtest/live parity:** `live_main.py` imports `build_strategy` from
`backtest_main.py` rather than redefining it, so the exact strategy logic that was
backtested is what runs live. Indicators and strategies exist in exactly one place
(`indicators/`, `signals/`) — never reimplemented elsewhere.

**No lookahead:** a strategy's `target_position(df)` may only use data through each
row's own bar. The backtest engine enforces the actual trading rule on top of that:
a decision computed from bar *t*'s close only fills at bar *t+1*'s open.

## Metrics that matter

`compute_metrics` reports `total_return_pct`, `cagr_pct`, `sharpe`, `max_drawdown_pct`,
`num_trades`, `win_rate_pct`, `avg_win`, `avg_loss`, and `expectancy_per_trade`.

**Expectancy (average net P&L per trade, after costs) is the headline number.** A
high win rate with a bad risk/reward ratio can still lose money; a low win rate with
strong asymmetric payoffs can be very profitable. Don't optimize for win rate.

## Before risking real money

1. **Phase 1 (this repo, current):** backtest + Telegram signals + sharia whitelist,
   signal-only. Confirms the pipeline is wired correctly, not that any edge is real.
2. **Phase 2 (not built yet):** walk-forward analysis, parameter-robustness /
   sensitivity testing, out-of-sample splits, benchmark comparison. Any backtest
   result from Phase 1 alone is **untrustworthy** — a single in-sample backtest on a
   handful of symbols is a high-overfitting-risk result, not evidence of an edge.
3. **Phase 3 (not built yet):** live execution via Interactive Brokers
   (`ib_async`, cash account only, no shorting/margin), only if Phase 2 justifies it.

Do not connect real capital to anything before Phase 2 exists and has been run.

## Sharia screening — read this

`whitelist.txt` ships with a handful of placeholder tickers **for wiring purposes
only — this is not a religious ruling and not investment advice.** Proper screening
needs both a business-activity screen and a financial-ratio screen (e.g. AAOIFI
interest-bearing-debt / market-cap thresholds), and ratios shift quarterly. This
system does **not** compute those ratios (see `SPEC.md` §14) — it is a whitelist
filter only. Source your own universe from a recognized standard (S&P Shariah / Dow
Jones Islamic Market constituents, a service such as Zoya or Musaffa) and/or a
qualified scholar, then replace `whitelist.txt` before using this for real decisions.

## Known limitations

- **Data:** `yfinance` is delayed/unofficial/rate-limited. Acceptable for swing
  signals and backtesting; not for intraday use or execution-grade pricing.
- **Backtest realism:** single position, long-only, next-open fills — realistic for
  swing trading, not for intraday microstructure.
- **No robustness tooling yet:** no walk-forward or parameter-sensitivity analysis
  exists in Phase 1. Treat any tuned parameters as unproven until Phase 2 exists.
- **Signal-only:** no order execution exists or is attempted anywhere in this repo.
- This software provides information, not financial or religious advice.
