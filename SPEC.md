# Technical Specification (TZ) — Swing Signal Bot

**Document type:** Engineering specification, written to be executed by an autonomous coding agent (Claude Code).
**Version:** 1.0
**Status:** Authoritative source of truth for the project. Where code and this document disagree, this document wins — reconcile the code to it.

---

## 0. How to use this document (instructions for the coding agent)

- Work **phase by phase** (see §17). Do not attempt the whole roadmap at once.
- After every change, run the test suite (§16). A phase is not done until its acceptance criteria pass.
- **Edit files directly** in the repository. Do not dump large code blocks into chat as the deliverable.
- Treat the **Hard Invariants (§4)** as non-negotiable. If a requested change would violate one, stop and flag it instead of silently complying.
- Prefer clean, DRY, well-separated code. When you find issues in existing code, **rank them by severity** (Critical / High / Medium / Low) before fixing.
- If a requirement is ambiguous or underspecified, ask a focused question rather than guessing.
- Do **not** implement anything on the "Non-goals" (§3) or "Do NOT" (§18) lists without an explicit new instruction.

---

## 1. Overview & purpose

A **signal-only, paper-first** trading assistant for **US equities** on a **swing timeframe** (daily bars, positions held days-to-weeks).

The system:
1. Backtests trading strategies against historical data with realistic costs.
2. Runs the *same* strategy logic live to detect entry/exit signals and pushes **Telegram alerts**.
3. Restricts its universe to a **user-maintained sharia-compliant whitelist**.

The system **does not place orders**. Real execution (via Interactive Brokers) is an explicitly future, isolated phase (§17, Phase 3) and must not be built now.

**Target user:** a solo developer running the bot on a local laptop first, later on a Contabo VPS (Ubuntu 24.04) via cron.

---

## 2. Glossary

- **Swing trading:** holding positions for days to weeks on daily (`1d`) bars. Contrast with intraday.
- **Parity:** the guarantee that backtest and live use identical indicator + strategy code, so a backtested edge can actually reproduce live.
- **Lookahead bias:** a backtest bug where a decision uses information not yet available at decision time. Fatal; invalidates results.
- **Expectancy:** average net profit-and-loss per trade, after costs. The primary quality metric.
- **Riba:** interest. Forbidden — hence cash account only, no margin.
- **Sharia screen:** filtering the tradable universe for compliance (business activity + financial ratios).

---

## 3. Goals & non-goals

### Goals
- G1. Correct, cost-aware, lookahead-free backtesting.
- G2. Backtest/live parity via shared strategy code.
- G3. Broker-agnostic architecture (swap data or execution provider without touching strategy/engine).
- G4. Telegram signal alerts, alert-on-change only (no spam while holding).
- G5. Enforced sharia whitelist as a real pipeline step.
- G6. Runnable on laptop now, VPS-via-cron later, with no always-on process required.

### Non-goals (explicitly out of scope for v1.0)
- N1. Order execution / broker connectivity of any kind.
- N2. Intraday / real-time data.
- N3. Automated AAOIFI financial-ratio computation (see §14).
- N4. Portfolio optimization, position sizing beyond a fixed equity fraction.
- N5. A web UI or dashboard.
- N6. Multi-asset support (options, futures, forex, crypto). US spot equities only.

---

## 4. Hard invariants (must never be violated)

- **INV-1 (No lookahead):** A strategy decision computed from bar *t* may only use data up to and including bar *t*. Execution occurs at the **open of bar *t+1***. The backtest engine enforces this by construction.
- **INV-2 (Parity):** Indicators and strategies exist in exactly one place and are imported by both backtest and live. No reimplementation of indicator math anywhere else (no parallel Pine Script, no duplicated formula).
- **INV-3 (Long-only):** No short positions anywhere. Target position ∈ {0, 1}.
- **INV-4 (Cash only / no riba):** No margin, no leverage, no interest-bearing mechanics. (Relevant when execution is eventually added: cash account only.)
- **INV-5 (Sharia gate):** The tradable universe is always the intersection of requested symbols and the whitelist. A symbol not on the whitelist is never scanned, backtested for live intent, or alerted on.
- **INV-6 (Costs modeled):** Every backtest fill applies both slippage and commission. Cost-free backtests are for internal tests only, never for evaluation.
- **INV-7 (Secrets in env):** Telegram token, chat id, and any future API keys come from environment / `.env`. Never hardcoded, never committed. `.env` and `state.json` are gitignored.
- **INV-8 (Decoupled seams):** `DataSource`, `AlertSink`, and `ExecutionAdapter` are abstract interfaces. Strategy and engine code depend only on the interfaces, never on a concrete provider.
- **INV-9 (Signal-only):** The system emits alerts; it must not submit, simulate submitting, or prepare live orders in v1.0.

---

## 5. Technology stack (pinned)

- **Language:** Python ≥ 3.10 (type hints required; use `from __future__ import annotations`).
- **Core libs:** `pandas` ≥ 2.0, `numpy` ≥ 1.24.
- **Data:** `yfinance` ≥ 0.2.40 (historical + delayed daily bars).
- **Alerts:** `requests` ≥ 2.31 (Telegram Bot API directly; no heavyweight SDK).
- **Config:** `python-dotenv` ≥ 1.0 (optional at runtime; degrade gracefully if absent).
- **Future (Phase 3 only, do not add now):** `ib_async` (NOT the deprecated `ib_insync`), `IBC`/`IBeam` for gateway session management.
- No ORM, no web framework, no test framework dependency required (plain assert-based smoke tests acceptable; `pytest` optional).

---

## 6. Repository structure

```
trading-bot/
├── core/
│   ├── models.py          # shared dataclasses/enums (Signal, Trade, Action, BacktestResult) + OHLCV_COLUMNS
│   └── config.py          # AppConfig, IndicatorConfig, BacktestConfig; env loading
├── data/
│   ├── base.py            # DataSource ABC + OHLCV validation
│   └── yfinance_source.py # yfinance implementation
├── indicators/
│   └── indicators.py      # sma, ema, rsi (Wilder), macd, crossover, crossunder
├── signals/
│   ├── base.py            # Strategy ABC + entry/exit -> held-position helper
│   └── strategies.py      # RsiStrategy, MacdStrategy, EmaCrossStrategy, CombinedStrategy
├── screening/
│   └── sharia.py          # ShariaFilter (whitelist-based)
├── alerts/
│   ├── base.py            # AlertSink ABC
│   └── telegram.py        # TelegramAlertSink
├── broker/
│   └── base.py            # ExecutionAdapter ABC (empty of implementations in v1.0)
├── engine/
│   ├── backtest.py        # run_backtest + compute_metrics
│   └── live.py            # LiveEngine (poll, drop forming bar, state, alert-on-change)
├── tests/
│   └── smoke_test.py      # offline correctness checks (no network)
├── backtest_main.py       # backtest entry point
├── live_main.py           # live entry point (reuses build_strategy from backtest_main → parity)
├── whitelist.txt          # user-maintained sharia universe (one symbol per line)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Every package directory contains `__init__.py`.

---

## 7. Data contracts

- **OHLCV DataFrame:** columns exactly `["open","high","low","close","volume"]` (lowercase), `DatetimeIndex` ascending, no duplicate timestamps, prices **split/dividend adjusted**. Defined once as `OHLCV_COLUMNS`.
- **`Signal`** (frozen dataclass): `symbol`, `timestamp`, `target_position ∈ {0,1}`, `action ∈ {BUY,SELL,HOLD}`, `reason: str`, `price: float|None`. `action` is derived by the engine from the change in `target_position`; strategies never set it.
- **`Trade`** (dataclass): a completed round-trip: `symbol`, `entry_time`, `exit_time`, `entry_price`, `exit_price`, `shares`, `commission`; computed properties `gross_pnl`, `net_pnl`, `return_pct`.
- **`BacktestResult`:** `symbol`, `equity_curve: pd.Series`, `trades: list[Trade]`, `initial_capital`.

---

## 8. Functional requirements

### Data (`data/`)
- **FR-1.** `DataSource` is an ABC with `get_history(symbol, lookback_days, interval) -> DataFrame` honoring the OHLCV contract (§7).
- **FR-2.** `DataSource._validate` rejects empty results, enforces column presence/order, drops duplicate timestamps, sorts ascending.
- **FR-3.** `YFinanceSource` fetches via `yfinance.download` with `auto_adjust=True`; flattens `MultiIndex` columns; lowercases column names; returns validated OHLCV.
- **FR-4.** Import of `yfinance` is lazy (inside the class), so the rest of the system imports without the dependency present.

### Indicators (`indicators/`)
- **FR-5.** `sma(series, period)` — simple moving average, `min_periods == period`.
- **FR-6.** `ema(series, period)` — `ewm(span=period, adjust=False, min_periods=period)`.
- **FR-7.** `rsi(series, period=14)` — **Wilder's smoothing** (RMA via `ewm(alpha=1/period, adjust=False)`). First `period` values NaN. `avg_loss == 0 → RSI = 100`.
- **FR-8.** `macd(series, fast=12, slow=26, signal=9)` returns a DataFrame with columns `macd`, `signal`, `hist`.
- **FR-9.** `crossover(a,b)` / `crossunder(a,b)` return boolean Series true on the bar where `a` crosses above / below `b`.

### Strategies (`signals/`)
- **FR-10.** `Strategy` ABC: `target_position(df) -> pd.Series` in {0,1}, aligned to `df.index`, stateless, obeying INV-1 (no future data).
- **FR-11.** Helper `_hold_between(entries, exits)` converts discrete entry/exit boolean events into a held 0/1 position (enter → stay long until exit), vectorized.
- **FR-12.** `RsiStrategy` — mean reversion: enter when RSI crosses up out of oversold, exit when RSI crosses down out of overbought; hold between.
- **FR-13.** `MacdStrategy` — long while MACD line > signal line; warmup region forced to 0.
- **FR-14.** `EmaCrossStrategy` — long while fast EMA > slow EMA; warmup region forced to 0.
- **FR-15.** `CombinedStrategy(strategies, mode)` — combine sub-strategies with `mode ∈ {all, any, majority}`. Default `all`. `name` reflects mode + members.

### Sharia screening (`screening/`)
- **FR-16.** `ShariaFilter(whitelist: set[str])`; `from_file(path)` loads one symbol per line, ignoring blank lines and `#` comments; raises on missing/empty file.
- **FR-17.** `is_allowed(symbol)` and `filter(symbols) -> list[str]`; rejected symbols are logged at WARNING.

### Backtest engine (`engine/backtest.py`)
- **FR-18.** `run_backtest(df, strategy, cfg, symbol) -> BacktestResult`. Long-only, single position at a time.
- **FR-19.** Execution timing per INV-1: decision from bar *t-1* close fills at bar *t* open.
- **FR-20.** Buy fill = `open * (1 + slippage_bps/1e4)`; sell fill = `open * (1 - slippage_bps/1e4)`. Commission = `notional * commission_bps/1e4`, applied on both sides, recorded on the resulting `Trade`.
- **FR-21.** Position sizing: deploy `cfg.position_fraction` of current cash on entry, sized so commission does not overdraw.
- **FR-22.** Equity marked-to-market at each bar's close.
- **FR-23.** `compute_metrics(result, periods_per_year=252)` returns: `total_return_pct`, `cagr_pct`, `sharpe` (annualized, rf=0), `max_drawdown_pct`, `num_trades`, `win_rate_pct`, `avg_win`, `avg_loss`, `expectancy_per_trade`. **Expectancy is the headline metric.** Do not present win rate as a primary success measure.

### Live engine (`engine/live.py`)
- **FR-24.** `LiveEngine(data, strategy, alert, cfg, drop_forming_bar=True)`.
- **FR-25.** For each symbol: fetch history, **drop the last (possibly still-forming) bar** when `drop_forming_bar`, compute target position, compare the latest completed bar's target vs persisted state.
- **FR-26.** Emit a `Signal` **only when the target position changed** vs stored state (alert-on-change; silent while holding). Action = BUY if position increased, SELL if decreased.
- **FR-27.** Persist per-symbol position to `state.json`; tolerate a corrupt/missing state file by starting fresh (log a warning).
- **FR-28.** `run_once(symbols)` iterates all symbols; a failure on one symbol is caught, logged, and must not abort the others.

### Alerts (`alerts/`)
- **FR-29.** `AlertSink` ABC with `send(signal)`.
- **FR-30.** `TelegramAlertSink(token, chat_id)` posts to the Bot API `sendMessage` with HTML formatting, an action emoji, symbol, price, date, reason, and a "signal only — no order placed" footer.
- **FR-31.** Send failures are logged, never raised (a missed alert must not crash the run).

### Entry points
- **FR-32.** `backtest_main.py`: load whitelist → build strategy → run backtest per symbol → print a metrics table.
- **FR-33.** `live_main.py`: **import `build_strategy` from `backtest_main`** (enforces parity) → construct `LiveEngine` → `run_once`.
- **FR-34.** Both are runnable as `python backtest_main.py` / `python live_main.py`.

---

## 9. Configuration

`.env` (secrets): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

`IndicatorConfig`: `rsi_period=14`, `rsi_oversold=30`, `rsi_overbought=70`, `macd_fast=12`, `macd_slow=26`, `macd_signal=9`, `ema_fast=50`, `ema_slow=200`.

`BacktestConfig`: `initial_capital=10000`, `position_fraction=0.95`, `commission_bps=5`, `slippage_bps=3`.

`AppConfig`: `interval="1d"`, `lookback_days=400`, `state_file="state.json"`, plus Telegram creds and nested configs.

All parameters overridable in code; no parameter hardcoded inside logic modules.

---

## 10. Error handling, logging, resilience

- Use the `logging` module (not `print`) inside library modules; entry points may format a human-readable table.
- Network/data errors on one symbol are isolated (FR-28); the run continues.
- Telegram failures are swallowed-and-logged (FR-31).
- No bare `except:`; catch specific exceptions where practical, `except Exception` only at the per-symbol isolation boundary.

---

## 11. Security & compliance constraints

- Secrets only via env (INV-7).
- `.gitignore` must exclude `.env`, `state.json`, `__pycache__/`, `*.pyc`.
- The shipped `whitelist.txt` tickers are **placeholders, not a religious ruling**; this must be stated in the file and README.
- The system provides information, **not financial or religious advice**; keep disclaimers in README and Telegram footer.

---

## 12. Scheduling / deployment

- Swing needs **no always-on process**. Live runs **once per trading day after the US close** via cron.
- Example (Asia/Tashkent): `30 2 * * 1-5 cd /path/to/trading-bot && /usr/bin/python live_main.py`.
- Laptop first; Contabo VPS later. No code change required to move — only the cron host changes.

---

## 13. Indicator correctness notes (for the agent)

- RSI **must** use Wilder's smoothing; a simple-moving-average RSI is a common silent bug and breaks parity with TradingView.
- Warmup regions (leading NaNs) must never produce trades; strategies force them to 0.
- Do not use `center=True` in rolling windows (that peeks into the future).

---

## 14. Sharia screening — scope limit (read carefully)

Proper screening = (1) business-activity screen + (2) financial-ratio screen (e.g. AAOIFI: interest-bearing debt / market cap and interest-income thresholds), and ratios change quarterly.

**v1.0 does NOT compute ratios.** It is a whitelist filter only. The user sources and maintains the list from a recognized standard (S&P Shariah / Dow Jones Islamic constituents, or a service such as Zoya / Musaffa) and/or a scholar. The agent must **not** hardcode which tickers are compliant and must **not** claim any ticker is halal. Automated ratio screening is a possible future phase, gated on a chosen standard and fundamental-data source.

---

## 15. Backtest realism boundaries (known, accepted for v1.0)

- Single position, long-only, next-open fills — realistic for swing, not for intraday microstructure.
- yfinance data is delayed/unofficial/rate-limited — acceptable for swing signals and backtests, unacceptable for intraday or execution.
- No walk-forward / parameter-robustness tooling yet → high overfitting risk. Any tuned parameter set is untrustworthy until Phase 2 exists.

---

## 16. Testing & acceptance criteria

`tests/smoke_test.py` runs **offline** (synthetic data, no network) and must pass:

- **AC-1 (indicators):** RSI stays within [0,100]; correct number of warmup NaNs; MACD returns the three expected columns.
- **AC-2 (no lookahead):** a strategy that goes long at bar *k* leaves equity exactly flat through bar *k* and only changes from bar *k+1* — asserts INV-1 by construction.
- **AC-3 (costs hurt):** identical strategy/data with nonzero costs ends with lower equity than with zero costs (given ≥1 trade).
- **AC-4 (metrics + combiner):** `CombinedStrategy` runs and `compute_metrics` returns the full metric set without error.

Definition of "green": `python -m tests.smoke_test` exits 0 and prints all `[ok]` lines. Every future change must keep these passing and add tests for new behavior.

Additional required checks: `python -m py_compile` across all modules succeeds; `backtest_main` and `live_main` import cleanly with dependencies installed.

---

## 17. Roadmap / phases

- **Phase 1 — v1.0 (current):** everything above. Backtest + Telegram signals + sharia whitelist. Signal-only. **This is the whole current scope.**
- **Phase 2 — Robustness (before any real money):** walk-forward analysis, parameter-robustness/sensitivity tooling, out-of-sample splits, multi-symbol/multi-period reporting, optional benchmark (buy-and-hold) comparison. Goal: distinguish real edge from overfit.
- **Phase 3 — Live execution (only if Phase 2 justifies it):** implement `broker/ibkr.py` against `ExecutionAdapter` using `ib_async`; IB Gateway + IBC/IBeam session management; **cash account only, spot only, no shorting** (INV-3/4). Nothing in `signals/` or `engine/` should change to add this — that is the payoff of INV-8.

Do not begin a later phase without an explicit instruction.

---

## 18. Do NOT (explicit boundaries for the agent)

- Do **not** implement order execution, paper or live, in v1.0 (INV-9).
- Do **not** add `ib_insync` (deprecated/unmaintained); if execution is ever added, use `ib_async`.
- Do **not** compute or assert sharia compliance for specific tickers (§14).
- Do **not** introduce shorting, margin, or leverage (INV-3/4).
- Do **not** reimplement any indicator or strategy outside `indicators/` / `signals/` (INV-2).
- Do **not** let a strategy read same-bar or future data (INV-1).
- Do **not** hardcode secrets or commit `.env` / `state.json` (INV-7).
- Do **not** build intraday support, a web UI, or additional asset classes (§3 non-goals).
- Do **not** silently "fix" a failing acceptance test by weakening the test.

---

## 19. Deliverables & Definition of Done

- All modules per §6 implemented to §8 and passing §16.
- `README.md` documenting setup, run commands, architecture, metrics that matter, the pre-real-money order, and known limitations.
- `requirements.txt`, `.env.example`, `.gitignore`, `whitelist.txt` (with placeholder disclaimer) present.
- All Hard Invariants (§4) hold. `python -m tests.smoke_test` is green.

**Done means:** a clean checkout can `pip install -r requirements.txt`, add `.env` + a real `whitelist.txt`, and run `backtest_main.py` and `live_main.py` successfully, with backtest/live parity intact and no order-execution code present.
