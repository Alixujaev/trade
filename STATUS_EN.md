# Project Status Report

_Date: 2026-08-18_

## 1. What This Project Is

**Swing Signal Bot** — a **signal-only** trading assistant for US equities. It never
places orders (paper or live). It backtests a strategy on historical data, runs the
same logic live to alert on Telegram when a position/setup changes, and only ever
touches symbols on a user-curated, sharia-compliant whitelist. Full technical spec:
`SPEC.md`. User-facing docs: `README.md`.

## 2. Current Architecture (as of commit `2a938e2` on `main`)

```
core/        - config (AppConfig, IndicatorConfig, BacktestConfig, ScannerConfig), models (Signal, Trade, Action)
data/        - DataSource abstraction + YFinanceSource implementation
indicators/  - RSI, MACD, EMA, ATR (pure functions over pandas Series/DataFrames)
signals/     - strategies.py (RSI/MACD/EMA/Combined) + detectors.py (price-action triggers/enrichers)
screening/   - ShariaFilter (whitelist gate)
alerts/      - AlertSink abstraction + TelegramAlertSink
broker/      - abstract seam only (base.py) — intentionally no concrete implementation, ever
engine/      - backtest.py, live.py, scanner.py
tests/       - smoke_test.py (19 checks), scanner_test.py (16 checks) — both offline, no network
backtest_main.py, live_main.py, scan_main.py, telegram_bot.py  - entry points
```

There are now **three parallel, independently runnable capabilities** built on the
same foundation:

| Entry point | Purpose | Status |
|---|---|---|
| `backtest_main.py` | Backtest RSI/MACD/EMA strategies on history | Built, but strategy has no proven edge (see §4) |
| `live_main.py` | Run RSI/MACD/EMA strategies live, alert on position change | Built |
| `scan_main.py` | **New:** scan whitelist daily for discretionary price-action setups | Built and merged |
| `telegram_bot.py` | Remote control bot: `/run`, `/backtest`, `/status`, `/help` | Built |

## 3. What Was Built, In Order

1. **Phase 1 (swing bot core)** — backtest engine (cost-aware, no-lookahead by
   construction), live engine (alert-on-change via `state.json`), three indicator
   strategies + `CombinedStrategy`, sharia whitelist filter.
2. **Telegram control bot** — `/run`, `/backtest`, `/status`, `/help`, hardened via
   code review (silent failure isolation, long-message chunking, auth).
3. **Reality check** (`reality_check.py`, uncommitted) — an independent script that
   pulled ~10 years of real daily data for every whitelist ticker + SPY, split each
   70/30 in-sample/out-of-sample with no parameter tuning, and compared the
   RSI/MACD/EMA strategy against plain buy-and-hold.
   - **Result: the strategy loses to buy-and-hold in 10/10 tickers out-of-sample**
     (strategy +21.55% avg vs. buy-and-hold +214.87% avg). SPY alone beat the
     strategy too. This is expected behavior for a trend-following strategy in a
     strong bull period, not a bug — but it means **no proven edge**, and the
     RSI/MACD/EMA stack was set aside rather than pushed toward Phase 2
     (walk-forward optimization).
4. **Price-Action Scanner (v1)** — the response to the reality check. Built via a
   7-task implementation plan
   (`docs/superpowers/plans/2026-08-17-price-action-scanner.md`, uncommitted) using
   subagent-driven development with a fresh implementer + reviewer per task, plus a
   final whole-branch review. **Merged to `main` on 2026-08-18.**

## 4. Why the Scanner Exists (Key Strategic Pivot)

The RSI/MACD/EMA strategies are **not what the underlying trading course actually
teaches** — the course teaches discretionary Smart-Money-Concepts price action
(liquidity sweeps, order blocks, FVG, BOS/CHOCH) plus candlestick patterns. That
kind of judgment cannot be fully mechanized. So instead of building another
auto-strategy, the project pivoted to building an **attention-router**: a scanner
that flags mechanical, unambiguous setups so a human can apply discretionary
judgment on top. An alert means *"a setup formed, go look"* — never *"this is a good
trade."* The scanner makes **no predictive-edge claim**.

### Architecture: Triggers vs. Enrichers (mandatory two-layer split)

- **Triggers** (can fire an alert alone): `bullish_sweep` (liquidity sweep +
  reclaim), `bullish_engulfing`, `bullish_pin`.
- **Enrichers** (context only, can never fire alone): `uptrend` (EMA fast >
  EMA slow), `near_fvg` (price sitting inside a recent bullish fair-value gap),
  `near_round_number` (price near a multiple of 5).

A scan only produces an actionable `Setup` when **at least one trigger** fires;
enrichers just add `context` and bump the `confluence` count. This was verified by
a dedicated test (`test_enricher_alone_not_actionable`) proving an enricher that
independently evaluates `True` still cannot, by itself, produce an alert.

### Hard invariants (all verified, end-to-end, by the final review)

- **No lookahead / no repainting** — the Scanner drops the forming (still-open) bar
  before any detector sees it; a bar's result never depends on future bars.
- **Long-only** — every trigger is bullish; sharia forbids shorting.
- **Sharia gate** — only whitelist symbols are ever scanned.
- **Signal-only** — no order execution anywhere; `broker/` remains seam-only
  (`__init__.py`, `base.py` — nothing else, confirmed by test and by review).
- **Reuse, don't duplicate** — no indicator math reimplemented outside
  `indicators/indicators.py` (the new `atr` function follows that file's existing
  Wilder-smoothing style).

### What the Scanner does per run

For each whitelist symbol: fetch history → drop the forming bar → run
`scan_symbol()` → if a trigger fired (and, by default, price is in an uptrend), it:
1. **Alerts on Telegram** via the existing `TelegramAlertSink`, with the reason
   string explicitly prefixed `"SCANNER: setup formed, go look — not a trade
   signal."` so the framing lands on the surface the user actually reads (this was
   a fix from the final review — the alert originally looked identical to an
   ordinary strategy BUY signal in the same chat).
2. **Journals the setup** to `journal.csv` with columns
   `scanned_at, bar_date, symbol, price, triggers, context, confluence, decision,
   outcome, notes` — `decision`/`outcome`/`notes` start blank for the user to fill
   in later. This journal is the actual point of the tool: it turns "does my
   discretionary read have edge?" into a measurable question over time.
3. **Deduplicates via state** (`scanner_state.json`) — the same bar is never
   re-alerted; a corrupt or missing state file is tolerated (starts fresh, logs a
   warning) rather than crashing.

Intended usage: **daily cron after the US close**, not an always-on process —
swing trading doesn't need one.

## 5. Quality Process Used for the Scanner (for context on confidence level)

Built with `superpowers:subagent-driven-development`: fresh implementer subagent
per task (mostly cheap-tier models, since the plan specified exact code), a
task-scoped spec+quality review after every task, and one broad whole-branch review
at the end on a top-tier model. The final review found:

- **0 Critical issues.**
- **4 Important issues**, all fixed before merge in one fix pass + one scoped
  re-review:
  1. Telegram alert read as an ordinary BUY signal → fixed with explicit
     "go look, not a trade signal" framing in the alert text itself.
  2. A journal write failure (e.g. disk full) could silently and permanently drop
     a setup (state was marked "alerted" before the journal write was confirmed
     to succeed) → fixed by reordering so state is only updated after the journal
     write and the alert both succeed.
  3. `README.md` never mentioned the scanner at all → fixed, now documents
     `scan_main.py`, the new `atr` indicator, `signals/detectors.py`,
     `engine/scanner.py`, and `journal.csv`.
  4. `near_round_number`'s tolerance scaled with price and became
     unconditionally `True` for any price above ~$250, silently degrading
     journal data quality for higher-priced names → fixed by capping the
     tolerance against the fixed round-number spacing instead of the price.
- **1 Minor issue parked deliberately** (not fixed): in the rare case where the
  journal write succeeds but the Telegram send then fails, the same bar can be
  retried on the next scan and get journaled a second time (a duplicate CSV row,
  not a duplicate alert or a lost setup). Judged an acceptable trade-off versus
  the alternative (permanent silent data loss), and cheap to fix later with a
  timestamp-keyed dedup check in the journal writer if it becomes a nuisance.

## 6. Test Status

Both suites are offline (no network) and green on `main`:

- `python -m tests.smoke_test` → **19/19 checks pass**, exit 0.
- `python -m tests.scanner_test` → **16/16 checks pass**, exit 0.
- `python -m py_compile` across every module → clean.
- `broker/` confirmed to contain only `__init__.py` and `base.py` — no execution
  code exists anywhere in the codebase.

## 7. Repository Housekeeping

- The scanner branch (`worktree-price-action-scanner`) was fast-forward merged
  into `main` on 2026-08-18 and then deleted, along with its worktree.
- Still **uncommitted** in the working tree (present but never added to git):
  `PROJECT_ANALYSIS.md`, `REALITY_CHECK_REPORT.md`, `STATUS_UZ.md`, this file,
  `docs/superpowers/plans/2026-08-17-price-action-scanner.md`, `reality_check.py`.
  These are documentation/analysis artifacts, not runtime code — commit them
  whenever you want them preserved in history.

## 8. Open Decision Points

1. **RSI/MACD/EMA strategy stack** — still exists (`backtest_main.py`,
   `live_main.py`, `signals/strategies.py`) but has no proven real-data edge per
   the reality check. Not removed, just not being pushed forward. No action
   required unless you want to revisit it (retune + fresh out-of-sample check,
   pivot strategy type, or retire it).
2. **Telegram bot parity** — `telegram_bot.py` currently exposes `/run` and
   `/backtest` but has no `/scan` command; the scanner is only reachable via cron
   right now. Worth adding if you want to trigger a scan on demand from the bot
   rather than waiting for the daily job.
3. **Real capital** — per `README.md`, no real money should be connected to this
   system. The scanner reinforces rather than changes that: it explicitly makes no
   predictive-edge claim and is a discretionary decision-support tool, not an
   automated strategy.
