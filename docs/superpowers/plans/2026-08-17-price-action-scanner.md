# Price-Action Scanner (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a signal-only price-action **Scanner** on top of the existing swing bot:
pure-function detectors that flag mechanical, unambiguous bullish setups (liquidity
sweeps, bullish engulfing, bullish pin bars) on completed daily bars, an engine that
runs them across the sharia whitelist, alerts on Telegram, and journals every fired
setup to CSV. An alert means "a setup formed, go look" — never "this is a good
trade". This does **not** replace or modify the existing RSI/MACD/EMA
backtest/live strategy stack; it is an additive, parallel capability.

**Architecture:** Two-layer detection in `signals/detectors.py` — **triggers**
(`bullish_sweep`, `bullish_engulfing`, `bullish_pin`) that can fire an alert on their
own, and **enrichers** (`uptrend`, `near_fvg`, `near_round_number`) that only add
context to a setup a trigger already produced. `scan_symbol()` aggregates both into a
`Setup`. `engine/scanner.py`'s `Scanner` reuses the existing `DataSource`,
`AlertSink`, and the `LiveEngine`'s state-file / drop-forming-bar / per-symbol
isolation patterns, adding only a CSV journal on top. `scan_main.py` wires it up for
daily cron use, exactly like `live_main.py` does for the existing live engine.

**Tech Stack:** Python ≥ 3.10, `pandas`, existing project stack — no new
dependencies.

**Spec:** `SPEC.md` (base project spec — this plan layers the Scanner on top of it
as a v1 addition; no separate design doc was authored for this feature, so the full
functional brief lives in this plan's Global Constraints and per-task descriptions
below).

## Global Constraints

- Every new/modified module starts with `from __future__ import annotations`
  (existing project convention — see any file under `core/`, `signals/`, `engine/`).
- No bare `except:`. `except Exception` is reserved for isolation boundaries only
  (per-symbol in `Scanner.run_once`, matching `engine/live.py`'s `run_once`).
- No new dependencies — reuse `pandas`, the existing `indicators/indicators.py`,
  `data/yfinance_source.py`, `alerts/telegram.py`, `screening/sharia.py`.
- **INV-A (no lookahead):** every detector reads only `df.iloc[-1]` (and a bounded
  window before it) as "the last closed bar" — the caller (`Scanner`) is responsible
  for dropping the forming bar before calling `scan_symbol`, exactly like
  `LiveEngine.process_symbol` does today (`engine/live.py:50-51`).
- **INV-B (long-only):** every trigger is bullish-only. No short/bearish detector is
  implemented in this plan.
- **INV-C (sharia gate):** `scan_main.py` scans only `ShariaFilter.filter(...)`
  output, exactly like `live_main.py` and `backtest_main.py` do today.
- **INV-D (signal-only):** `Scanner` never places, simulates, or prepares an order.
  It emits a `Signal` to the existing `AlertSink` and appends a CSV row. Nothing else.
- **INV-E (reuse, don't duplicate):** all indicator math lives in
  `indicators/indicators.py` — including the one new indicator this plan needs
  (ATR), added there rather than inlined into a detector. No indicator formula is
  ever written a second time anywhere else.
- Tests are offline only, in a **new** file `tests/scanner_test.py` (per explicit
  task instruction — the existing `tests/smoke_test.py` is not touched by this
  plan), following `tests/smoke_test.py`'s existing style: plain `assert`-based, one
  `test_xxx()` function per concern, each ending with `print("[ok] <name>")`, all
  registered in a `tests` list inside `main()`, runnable via
  `python -m tests.scanner_test`. No `pytest` dependency (confirmed not installed in
  this environment).
- Definition of done for every task: `python -m tests.scanner_test` exits 0 and
  prints `[ok]` for every test written so far, `python -m tests.smoke_test` still
  exits 0 (existing tests untouched), and
  `python -m py_compile <every changed/new .py file>` succeeds.
- Run all commands from the repo root: `C:\Users\Admin\Desktop\own\trade`. `python`
  is confirmed on `PATH` in this environment (`python --version` → 3.12.10).

## Design Decisions & Resolved Ambiguities

Ranked by severity — these are choices made to keep the spec's prose fully
concrete. Flag any of these to the user if they'd prefer a different call; none of
them change an invariant.

1. **(Medium) ATR does not exist yet.** `near_fvg`'s "gap > atr_frac×ATR" needs an
   ATR indicator, and none exists in `indicators/indicators.py` today. Per INV-E the
   only compliant place to add it is that same shared module (Task 1) — not inlined
   into `signals/detectors.py`. It follows the file's existing Wilder-smoothing
   style (see `rsi`).
2. **(Medium) "near" for `near_fvg` is defined as price sitting inside the gap
   zone.** A 3-bar bullish FVG leaves a price zone `[high[i-2], low[i]]`; "near
   current price" is implemented as `gap_low <= current_price <= gap_high`. This
   correctly matches the real use case (an FVG formed a few bars back, price has
   since pulled back into it) — a same-bar FVG's own close is structurally at or
   above `gap_high` (its `low` *is* `gap_high`), so it will essentially never
   self-qualify, which is intended: proximity means "revisited", not "just formed".
3. **(Low) Round-number base unit is 5.** "…5, 10, 50, 100…" is read as: the levels
   are multiples of 5 (which already includes the 10/50/100 marks as a subset), so
   `near_round_number` rounds to the nearest multiple of 5 and checks
   `tol_frac`-relative distance.
4. **(Low) `bullish_pin`'s "small body" threshold.** The spec parameterizes the
   wick fraction but not the body threshold. Implemented as a fixed `body/range <=
   0.3`, applied alongside the wick-fraction check — both conditions must hold.
5. **(Low) `uptrend` takes `IndicatorConfig`, not a new scanner-specific EMA pair.**
   The spec's enricher signature is `uptrend(df, cfg)`; since `IndicatorConfig`
   already carries `ema_fast`/`ema_slow` (`core/config.py:15-16`) and the mandate is
   to reuse existing config, `uptrend` takes `cfg: IndicatorConfig` and
   `scan_symbol` passes `cfg.indicators` (where `cfg: AppConfig`).
6. **(Low) New `ScannerConfig` dataclass.** The sweep/pin/FVG/round-number
   thresholds need a home. Added as `ScannerConfig` in `core/config.py`, following
   the exact pattern of `IndicatorConfig`/`BacktestConfig`, wired into `AppConfig`
   as `AppConfig.scanner`. This is config, not indicator math, so it doesn't
   interact with INV-E.
7. **(Low) State/journal file defaults.** `scanner_state.json` and `journal.csv` are
   relative paths written to the working directory, matching `state.json`'s
   existing convention (`core/config.py:31`). Both should be added to `.gitignore`
   alongside `state.json` (Task 6, alongside `scan_main.py`).

---

## Task 1: ATR indicator

**Files:**
- Modify: `indicators/indicators.py`
- Test: `tests/scanner_test.py` (new file, created by this task)

**Interfaces:**
- Produces: `atr(df: pd.DataFrame, period: int = 14) -> pd.Series` — Wilder-smoothed
  Average True Range. Requires `df` to have `high`, `low`, `close` columns.
  `min_periods=period` like the rest of the module, so the first `period - 1` values
  are `NaN` (True Range itself has no leading NaN — unlike `rsi`'s `delta.diff()`,
  `pd.concat([...]).max(axis=1)` skips the single resulting NaN from the missing
  previous close on the first row and falls back to `high - low`).

- [ ] **Step 1: Write the failing test**

Create `tests/scanner_test.py` with this content:

```python
"""Offline correctness checks for the price-action Scanner (no network).

Run as: python -m tests.scanner_test
"""
from __future__ import annotations

import sys

import pandas as pd


def _mk_bars(rows: list[list[float]]) -> pd.DataFrame:
    """rows: list of [open, high, low, close]. Returns an OHLCV df."""
    idx = pd.date_range("2024-01-02", periods=len(rows), freq="B")
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])
    df["volume"] = 1_000_000
    return df


def test_atr() -> None:
    from indicators.indicators import atr

    n = 20
    period = 14
    df = _mk_bars([[100.0, 102.0, 98.0, 100.0]] * n)

    result = atr(df, period=period)
    assert result.isna().sum() == period - 1
    # constant high-low range with no prior-close jump -> TR is constant 4.0
    # for every bar, so the EMA of TR converges to 4.0 by the last bar.
    assert abs(result.iloc[-1] - 4.0) < 1e-9

    print("[ok] atr")


def main() -> int:
    tests = [
        test_atr,
    ]
    for t in tests:
        t()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ImportError: cannot import name 'atr' from 'indicators.indicators'`

- [ ] **Step 3: Add `atr` to `indicators/indicators.py`**

Open `indicators/indicators.py` and add this function at the end of the file:

```python
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m tests.scanner_test`
Expected: `[ok] atr` printed, exit 0.

- [ ] **Step 5: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile indicators/indicators.py tests/scanner_test.py
```
Expected: both succeed (`smoke_test` prints all its `[ok]` lines and exits 0;
`py_compile` produces no output and exits 0).

- [ ] **Step 6: Commit**

```bash
git add indicators/indicators.py tests/scanner_test.py
git commit -m "feat: add ATR indicator for scanner FVG detection"
```

---

## Task 2: Trigger detectors — `bullish_sweep`, `bullish_engulfing`, `bullish_pin`

**Files:**
- Create: `signals/detectors.py`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: nothing new (pure `pandas` operations on OHLCV columns).
- Produces:
  - `bullish_sweep(df: pd.DataFrame, lookback: int = 20, reclaim_frac: float = 0.5) -> bool`
  - `bullish_engulfing(df: pd.DataFrame) -> bool`
  - `bullish_pin(df: pd.DataFrame, wick_frac: float = 0.6) -> bool`

  All three read only `df.iloc[-1]` (and, for `bullish_sweep`, the `lookback` bars
  immediately before it) and return a native Python `bool`.

- [ ] **Step 1: Write the failing tests**

Add these functions to `tests/scanner_test.py`, right before `def main() -> int:`:

```python
def test_bullish_sweep() -> None:
    from signals.detectors import bullish_sweep

    prior = [[100, 101, 95, 100]] * 5  # 5 flat prior bars, low=95 each
    sweep_bar = [97, 99, 90, 98]  # dips below 95, reclaims, closes at 98
    df = _mk_bars(prior + [sweep_bar])
    assert bullish_sweep(df, lookback=5, reclaim_frac=0.5) is True

    plain_down_bar = [98, 99, 96, 97]  # never dips below the prior window low of 95
    df2 = _mk_bars(prior + [plain_down_bar])
    assert bullish_sweep(df2, lookback=5, reclaim_frac=0.5) is False

    print("[ok] bullish_sweep")


def test_bullish_engulfing() -> None:
    from signals.detectors import bullish_engulfing

    prior_bearish = [105, 106, 99, 100]  # bearish: close(100) < open(105)
    last_engulf = [99, 107, 98, 106]  # bullish: body [99,106] engulfs [100,105]
    df = _mk_bars([prior_bearish, last_engulf])
    assert bullish_engulfing(df) is True

    prior_bullish = [100, 106, 99, 105]  # prior is bullish -> no engulfing setup
    last_bar = [99, 107, 98, 106]
    df2 = _mk_bars([prior_bullish, last_bar])
    assert bullish_engulfing(df2) is False

    print("[ok] bullish_engulfing")


def test_bullish_pin() -> None:
    from signals.detectors import bullish_pin

    pin_bar = [100.2, 100.6, 92.0, 100.1]  # long lower wick, small body
    df = _mk_bars([pin_bar])
    assert bullish_pin(df, wick_frac=0.6) is True

    no_pin_bar = [100.0, 101.0, 99.5, 100.8]  # normal bullish bar, no long lower wick
    df2 = _mk_bars([no_pin_bar])
    assert bullish_pin(df2, wick_frac=0.6) is False

    print("[ok] bullish_pin")
```

Add `test_bullish_sweep`, `test_bullish_engulfing`, `test_bullish_pin` to the `tests`
list inside `main()`, after `test_atr,`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.detectors'`

- [ ] **Step 3: Create `signals/detectors.py`**

```python
from __future__ import annotations

import pandas as pd


def bullish_sweep(df: pd.DataFrame, lookback: int = 20, reclaim_frac: float = 0.5) -> bool:
    if len(df) < lookback + 1:
        return False

    prior = df.iloc[-(lookback + 1):-1]
    last = df.iloc[-1]
    prior_low = float(prior["low"].min())
    last_low = float(last["low"])
    last_high = float(last["high"])
    last_close = float(last["close"])

    if not (last_low < prior_low):
        return False
    if not (last_close > prior_low):
        return False

    bar_range = last_high - last_low
    if bar_range <= 0:
        return False

    recovery = (last_close - last_low) / bar_range
    return bool(recovery >= reclaim_frac)


def bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False

    prior = df.iloc[-2]
    last = df.iloc[-1]

    prior_bearish = prior["close"] < prior["open"]
    last_bullish = last["close"] > last["open"]
    if not (prior_bearish and last_bullish):
        return False

    prior_body_low = min(prior["open"], prior["close"])
    prior_body_high = max(prior["open"], prior["close"])
    last_body_low = min(last["open"], last["close"])
    last_body_high = max(last["open"], last["close"])

    engulfs = last_body_low <= prior_body_low and last_body_high >= prior_body_high
    return bool(engulfs)


def bullish_pin(df: pd.DataFrame, wick_frac: float = 0.6) -> bool:
    if len(df) < 1:
        return False

    last = df.iloc[-1]
    bar_range = float(last["high"] - last["low"])
    if bar_range <= 0:
        return False

    body = abs(float(last["close"] - last["open"]))
    lower_wick = float(min(last["open"], last["close"]) - last["low"])

    wick_ok = (lower_wick / bar_range) >= wick_frac
    body_ok = (body / bar_range) <= 0.3
    return bool(wick_ok and body_ok)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m tests.scanner_test`
Expected: `[ok] atr`, `[ok] bullish_sweep`, `[ok] bullish_engulfing`, `[ok] bullish_pin`
printed, exit 0.

- [ ] **Step 5: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile signals/detectors.py tests/scanner_test.py
```
Expected: both succeed.

- [ ] **Step 6: Commit**

```bash
git add signals/detectors.py tests/scanner_test.py
git commit -m "feat: add scanner trigger detectors (sweep, engulfing, pin)"
```

---

## Task 3: Enricher detectors — `uptrend`, `near_fvg`, `near_round_number`

**Files:**
- Modify: `signals/detectors.py`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: `ema` and `atr` from `indicators.indicators` (Task 1);
  `core.config.IndicatorConfig` (existing, unmodified).
- Produces:
  - `uptrend(df: pd.DataFrame, cfg: IndicatorConfig) -> bool`
  - `near_fvg(df: pd.DataFrame, atr_frac: float = 0.3, lookback: int = 10) -> bool`
  - `near_round_number(df: pd.DataFrame, tol_frac: float = 0.01) -> bool`

- [ ] **Step 1: Write the failing tests**

Add these functions to `tests/scanner_test.py`, right after `test_bullish_pin` and
before `def main() -> int:`:

```python
def test_uptrend() -> None:
    from core.config import IndicatorConfig
    from signals.detectors import uptrend

    cfg = IndicatorConfig(ema_fast=3, ema_slow=5)

    rising = _mk_bars([[c, c + 1, c - 1, c] for c in [100, 102, 104, 106, 108, 110]])
    assert uptrend(rising, cfg) is True

    falling = _mk_bars([[c, c + 1, c - 1, c] for c in [110, 108, 106, 104, 102, 100]])
    assert uptrend(falling, cfg) is False

    # insufficient data for the slow EMA to warm up -> not an uptrend
    short = _mk_bars([[100, 101, 99, 100]] * 3)
    assert uptrend(short, cfg) is False

    print("[ok] uptrend")


def test_near_round_number() -> None:
    from signals.detectors import near_round_number

    on_round = _mk_bars([[99.6, 100.4, 99.4, 100.0]])  # close exactly 100
    assert near_round_number(on_round, tol_frac=0.01) is True

    off_round = _mk_bars([[102.5, 103.5, 102.0, 103.0]])  # nearest 5-multiple is 105
    assert near_round_number(off_round, tol_frac=0.01) is False

    print("[ok] near_round_number")


def test_near_fvg() -> None:
    from signals.detectors import near_fvg

    filler = [[99.0, 101.0, 98.0, 99.5]] * 14  # ATR warmup (period=14)
    fvg_bars = [
        [97, 100, 96, 99],  # bar i-2: high=100 -> gap floor
        [100, 103, 99, 102],  # middle bar
        [104, 108, 106, 107],  # bar i: low=106 -> gap ceiling; gap=[100,106]
    ]
    pullback_bars = [
        [106, 107, 103, 104],
        [104, 105, 102, 103],
        [103, 104, 101, 102.5],  # last close=102.5 sits back inside [100,106]
    ]
    df = _mk_bars(filler + fvg_bars + pullback_bars)
    assert near_fvg(df, atr_frac=0.3, lookback=10) is True

    flat = _mk_bars(filler + filler[:6])  # no gap ever forms
    assert near_fvg(flat, atr_frac=0.3, lookback=10) is False

    print("[ok] near_fvg")
```

Add `test_uptrend`, `test_near_round_number`, `test_near_fvg` to the `tests` list
inside `main()`, after `test_bullish_pin,`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ImportError: cannot import name 'uptrend' from 'signals.detectors'`

- [ ] **Step 3: Add the enrichers to `signals/detectors.py`**

Add these imports at the top of `signals/detectors.py` (replacing the existing
`import pandas as pd`-only import block):

```python
from __future__ import annotations

import pandas as pd

from core.config import IndicatorConfig
from indicators.indicators import atr, ema
```

Then add these functions after `bullish_pin` (still before nothing else exists yet
in the file):

```python
def uptrend(df: pd.DataFrame, cfg: IndicatorConfig) -> bool:
    fast = ema(df["close"], cfg.ema_fast)
    slow = ema(df["close"], cfg.ema_slow)
    if pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]):
        return False
    return bool(fast.iloc[-1] > slow.iloc[-1])


def near_fvg(df: pd.DataFrame, atr_frac: float = 0.3, lookback: int = 10) -> bool:
    if len(df) < 3:
        return False

    atr_series = atr(df, period=14)
    current_price = float(df["close"].iloc[-1])
    start = max(2, len(df) - lookback)

    for i in range(start, len(df)):
        gap_low = float(df["high"].iloc[i - 2])
        gap_high = float(df["low"].iloc[i])
        gap_size = gap_high - gap_low
        if gap_size <= 0:
            continue

        atr_i = atr_series.iloc[i]
        if pd.isna(atr_i) or gap_size <= atr_frac * atr_i:
            continue

        if gap_low <= current_price <= gap_high:
            return True

    return False


_ROUND_NUMBER_UNIT = 5.0


def near_round_number(df: pd.DataFrame, tol_frac: float = 0.01) -> bool:
    if len(df) < 1:
        return False

    price = float(df["close"].iloc[-1])
    nearest = round(price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT
    tol = tol_frac * price
    return bool(abs(price - nearest) <= tol)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m tests.scanner_test`
Expected: all `[ok]` lines so far printed (`atr`, `bullish_sweep`,
`bullish_engulfing`, `bullish_pin`, `uptrend`, `near_round_number`, `near_fvg`),
exit 0.

- [ ] **Step 5: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile signals/detectors.py tests/scanner_test.py
```
Expected: both succeed.

- [ ] **Step 6: Commit**

```bash
git add signals/detectors.py tests/scanner_test.py
git commit -m "feat: add scanner enricher detectors (uptrend, near_fvg, near_round_number)"
```

---

## Task 4: `ScannerConfig`, `Setup`, and `scan_symbol` aggregation

**Files:**
- Modify: `core/config.py`
- Modify: `signals/detectors.py`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: `bullish_sweep`, `bullish_engulfing`, `bullish_pin`, `uptrend`,
  `near_fvg`, `near_round_number` (Tasks 2–3); `core.config.AppConfig`,
  `core.config.IndicatorConfig` (existing).
- Produces:
  - `core.config.ScannerConfig` dataclass with fields `sweep_lookback: int = 20`,
    `sweep_reclaim_frac: float = 0.5`, `pin_wick_frac: float = 0.6`,
    `fvg_atr_frac: float = 0.3`, `fvg_lookback: int = 10`,
    `round_number_tol_frac: float = 0.01`.
  - `core.config.AppConfig.scanner: ScannerConfig` (new field, default-factory
    constructed, same pattern as `AppConfig.indicators`/`AppConfig.backtest`).
  - `signals.detectors.Setup` frozen-free dataclass: `symbol: str`,
    `triggers: list[str]`, `context: list[str]`, `price: float`,
    `confluence: int`, plus `is_actionable` property.
  - `signals.detectors.scan_symbol(df: pd.DataFrame, symbol: str, cfg: AppConfig, require_uptrend: bool = True) -> Setup | None`
    — later consumed by `engine/scanner.py` (Task 5).

- [ ] **Step 1: Write the failing tests**

Add these functions to `tests/scanner_test.py`, right after `test_near_fvg` and
before `def main() -> int:`:

```python
def test_scanner_config_defaults() -> None:
    from core.config import AppConfig, ScannerConfig

    cfg = ScannerConfig()
    assert cfg.sweep_lookback == 20
    assert cfg.sweep_reclaim_frac == 0.5
    assert cfg.pin_wick_frac == 0.6
    assert cfg.fvg_atr_frac == 0.3
    assert cfg.fvg_lookback == 10
    assert cfg.round_number_tol_frac == 0.01

    app = AppConfig()
    assert isinstance(app.scanner, ScannerConfig)

    print("[ok] scanner_config_defaults")


def test_enricher_alone_not_actionable() -> None:
    from core.config import AppConfig
    from signals.detectors import near_round_number, scan_symbol

    filler = [[99.0, 101.0, 98.0, 99.5]] * 2
    last_bar = [100.2, 100.6, 99.7, 100.0]  # small body, short lower wick, on 100
    df = _mk_bars(filler + [last_bar])

    assert near_round_number(df, tol_frac=0.01) is True  # enricher alone is true...

    result = scan_symbol(df, "TEST", AppConfig(), require_uptrend=False)
    assert result is None  # ...but no trigger fired, so no actionable setup

    print("[ok] enricher_alone_not_actionable")


def test_scan_symbol_no_lookahead() -> None:
    from core.config import AppConfig, ScannerConfig
    from signals.detectors import scan_symbol

    prior = [[100, 101, 95, 100]] * 5
    sweep_bar = [97, 99, 90, 98]
    df_base = _mk_bars(prior + [sweep_bar])  # 6 bars

    cfg = AppConfig(scanner=ScannerConfig(sweep_lookback=5, sweep_reclaim_frac=0.5))

    result_base = scan_symbol(df_base, "TEST", cfg, require_uptrend=False)
    assert result_base is not None
    assert "liquidity_sweep" in result_base.triggers

    future_rows = [[98, 99, 97, 98.5]] * 4
    df_extended = _mk_bars(prior + [sweep_bar] + future_rows)

    # same bar position, more data appended after it -> identical result
    result_same_slice = scan_symbol(df_extended.iloc[:6], "TEST", cfg, require_uptrend=False)
    assert result_same_slice is not None
    assert result_same_slice.triggers == result_base.triggers
    assert result_same_slice.context == result_base.context
    assert result_same_slice.price == result_base.price

    # evaluating the full extended df looks at a genuinely different last bar
    result_full = scan_symbol(df_extended, "TEST", cfg, require_uptrend=False)
    assert result_full is None

    print("[ok] scan_symbol_no_lookahead")


def test_scan_symbol_uptrend_gate() -> None:
    from core.config import AppConfig, IndicatorConfig, ScannerConfig
    from signals.detectors import scan_symbol

    closes = [140, 135, 130, 125, 120, 115, 110]
    rows = [[c + 1, c + 2, c - 2, c] for c in closes]
    sweep_bar = [97, 114, 100, 112]  # dips to 100, reclaims, closes 112
    df = _mk_bars(rows + [sweep_bar])

    cfg = AppConfig(
        indicators=IndicatorConfig(ema_fast=3, ema_slow=5),
        scanner=ScannerConfig(sweep_lookback=5, sweep_reclaim_frac=0.5),
    )

    gated = scan_symbol(df, "TEST", cfg, require_uptrend=True)
    assert gated is None

    ungated = scan_symbol(df, "TEST", cfg, require_uptrend=False)
    assert ungated is not None
    assert "liquidity_sweep" in ungated.triggers
    assert "uptrend" not in ungated.context

    print("[ok] scan_symbol_uptrend_gate")
```

Add `test_scanner_config_defaults`, `test_enricher_alone_not_actionable`,
`test_scan_symbol_no_lookahead`, `test_scan_symbol_uptrend_gate` to the `tests`
list inside `main()`, after `test_near_fvg,`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ImportError: cannot import name 'ScannerConfig' from 'core.config'`

- [ ] **Step 3: Add `ScannerConfig` to `core/config.py`**

Open `core/config.py`. Add this class after `BacktestConfig` and before
`AppConfig`:

```python
@dataclass
class ScannerConfig:
    sweep_lookback: int = 20
    sweep_reclaim_frac: float = 0.5
    pin_wick_frac: float = 0.6
    fvg_atr_frac: float = 0.3
    fvg_lookback: int = 10
    round_number_tol_frac: float = 0.01
```

Then add a `scanner` field to `AppConfig`, right after `backtest: BacktestConfig =
field(default_factory=BacktestConfig)`:

```python
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
```

- [ ] **Step 4: Add `Setup` and `scan_symbol` to `signals/detectors.py`**

Change the top-of-file import block to also import `AppConfig`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.config import AppConfig, IndicatorConfig
from indicators.indicators import atr, ema
```

Then append this to the end of `signals/detectors.py`:

```python
@dataclass
class Setup:
    symbol: str
    triggers: list[str]
    context: list[str]
    price: float
    confluence: int

    @property
    def is_actionable(self) -> bool:
        return len(self.triggers) > 0


def scan_symbol(
    df: pd.DataFrame, symbol: str, cfg: AppConfig, require_uptrend: bool = True
) -> Setup | None:
    if df.empty:
        return None

    scanner_cfg = cfg.scanner
    triggers: list[str] = []
    if bullish_sweep(
        df, lookback=scanner_cfg.sweep_lookback, reclaim_frac=scanner_cfg.sweep_reclaim_frac
    ):
        triggers.append("liquidity_sweep")
    if bullish_engulfing(df):
        triggers.append("bullish_engulfing")
    if bullish_pin(df, wick_frac=scanner_cfg.pin_wick_frac):
        triggers.append("bullish_pin")

    if not triggers:
        return None

    is_uptrend = uptrend(df, cfg.indicators)
    if require_uptrend and not is_uptrend:
        return None

    context: list[str] = []
    if is_uptrend:
        context.append("uptrend")
    if near_fvg(df, atr_frac=scanner_cfg.fvg_atr_frac, lookback=scanner_cfg.fvg_lookback):
        context.append("near_fvg")
    if near_round_number(df, tol_frac=scanner_cfg.round_number_tol_frac):
        context.append("near_round_number")

    price = float(df["close"].iloc[-1])
    return Setup(
        symbol=symbol,
        triggers=triggers,
        context=context,
        price=price,
        confluence=len(triggers) + len(context),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m tests.scanner_test`
Expected: all `[ok]` lines so far printed, exit 0.

- [ ] **Step 6: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile core/config.py signals/detectors.py tests/scanner_test.py
```
Expected: both succeed.

- [ ] **Step 7: Commit**

```bash
git add core/config.py signals/detectors.py tests/scanner_test.py
git commit -m "feat: add ScannerConfig, Setup, and scan_symbol aggregation"
```

---

## Task 5: Scanner engine (`engine/scanner.py`)

**Files:**
- Create: `engine/scanner.py`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: `data.base.DataSource`, `alerts.base.AlertSink`, `core.config.AppConfig`
  (existing, unmodified), `core.models.Action`/`Signal` (existing, unmodified),
  `signals.detectors.Setup`/`scan_symbol` (Task 4).
- Produces:
  - `engine.scanner.Scanner(data: DataSource, alert: AlertSink, cfg: AppConfig, require_uptrend: bool = True, journal_path: str = "journal.csv", state_path: str = "scanner_state.json", drop_forming_bar: bool = True)`
  - `Scanner.process_symbol(symbol: str) -> Setup | None`
  - `Scanner.run_once(symbols: list[str]) -> list[Setup]`
  - `Scanner.state: dict` (symbol -> last-alerted bar timestamp string)

- [ ] **Step 1: Write the failing tests**

Add these functions to `tests/scanner_test.py`, right after
`test_scan_symbol_uptrend_gate` and before `def main() -> int:`:

```python
def _tmp_path(suffix: str) -> str:
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    os.remove(path)  # want a nonexistent path -> "no prior state/journal" scenario
    return path


class _FakeSource:
    def __init__(self, frame):
        self._frame = frame

    def get_history(self, symbol, lookback_days, interval="1d"):
        return self._frame.copy()


class _FakeAlert:
    def __init__(self):
        self.sent = []

    def send(self, signal):
        self.sent.append(signal)


def test_scanner_drop_forming_bar() -> None:
    import os

    from core.config import AppConfig
    from engine.scanner import Scanner

    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0, 105.0, 99.0],
            "high": [101.0, 106.0, 107.0],
            "low": [99.0, 99.0, 98.0],
            "close": [100.0, 100.0, 106.0],
            "volume": [1_000_000] * 3,
        },
        index=idx,
    )

    # drop_forming_bar=True: the engulfing pattern lives on the dropped bar -> no setup
    state_a, journal_a = _tmp_path(".json"), _tmp_path(".csv")
    try:
        cfg = AppConfig(state_file=state_a)
        scanner = Scanner(
            _FakeSource(df),
            _FakeAlert(),
            cfg,
            require_uptrend=False,
            journal_path=journal_a,
            state_path=state_a,
            drop_forming_bar=True,
        )
        setup = scanner.process_symbol("AAPL")
        assert setup is None
        assert not os.path.isfile(journal_a)
    finally:
        for p in (state_a, journal_a):
            if os.path.isfile(p):
                os.remove(p)

    # drop_forming_bar=False: the same engulfing pattern is now the last bar -> fires
    state_b, journal_b = _tmp_path(".json"), _tmp_path(".csv")
    try:
        cfg = AppConfig(state_file=state_b)
        alert = _FakeAlert()
        scanner = Scanner(
            _FakeSource(df),
            alert,
            cfg,
            require_uptrend=False,
            journal_path=journal_b,
            state_path=state_b,
            drop_forming_bar=False,
        )
        setup = scanner.process_symbol("AAPL")
        assert setup is not None
        assert "bullish_engulfing" in setup.triggers
        assert len(alert.sent) == 1
        assert alert.sent[0].action.value == "BUY"
        assert os.path.isfile(journal_b)
        with open(journal_b, encoding="utf-8") as f:
            content = f.read()
        assert "bullish_engulfing" in content
        assert "AAPL" in content
        assert content.startswith(
            "scanned_at,bar_date,symbol,price,triggers,context,confluence,decision,outcome,notes"
        )
    finally:
        for p in (state_b, journal_b):
            if os.path.isfile(p):
                os.remove(p)

    print("[ok] scanner_drop_forming_bar")


def test_scanner_alert_on_change_and_state() -> None:
    import json
    import os

    from core.config import AppConfig
    from engine.scanner import Scanner

    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    df = pd.DataFrame(
        {
            "open": [105.0, 99.0],
            "high": [106.0, 107.0],
            "low": [99.0, 98.0],
            "close": [100.0, 106.0],
            "volume": [1_000_000] * 2,
        },
        index=idx,
    )  # bar0 bearish, bar1 bullish engulf -> fires with drop_forming_bar=False

    state_path, journal_path = _tmp_path(".json"), _tmp_path(".csv")
    try:
        cfg = AppConfig(state_file=state_path)
        alert = _FakeAlert()
        scanner = Scanner(
            _FakeSource(df),
            alert,
            cfg,
            require_uptrend=False,
            journal_path=journal_path,
            state_path=state_path,
            drop_forming_bar=False,
        )

        setups = scanner.run_once(["AAPL"])
        assert len(setups) == 1
        assert len(alert.sent) == 1
        with open(journal_path, encoding="utf-8") as f:
            rows_after_first = f.read().count("\n")

        # same bar again -> already alerted, no re-alert, no new journal row
        setups2 = scanner.run_once(["AAPL"])
        assert setups2 == []
        assert len(alert.sent) == 1
        with open(journal_path, encoding="utf-8") as f:
            rows_after_second = f.read().count("\n")
        assert rows_after_second == rows_after_first

        assert os.path.isfile(state_path)
        with open(state_path, encoding="utf-8") as f:
            saved = json.load(f)
        assert "AAPL" in saved
    finally:
        for p in (state_path, journal_path):
            if os.path.isfile(p):
                os.remove(p)

    print("[ok] scanner_alert_on_change_and_state")


def test_scanner_corrupt_state_and_isolation() -> None:
    import os
    import tempfile

    from core.config import AppConfig
    from engine.scanner import Scanner

    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    good_df = pd.DataFrame(
        {
            "open": [105.0, 99.0],
            "high": [106.0, 107.0],
            "low": [99.0, 98.0],
            "close": [100.0, 106.0],
            "volume": [1_000_000] * 2,
        },
        index=idx,
    )

    class _FlakySource:
        def __init__(self, good):
            self._good = good

        def get_history(self, symbol, lookback_days, interval="1d"):
            if symbol == "BAD":
                raise RuntimeError("network down")
            return self._good.copy()

    fd, corrupt_state = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write("{not valid json")
    journal_path = _tmp_path(".csv")

    try:
        cfg = AppConfig(state_file=corrupt_state)
        scanner = Scanner(
            _FlakySource(good_df),
            _FakeAlert(),
            cfg,
            require_uptrend=False,
            journal_path=journal_path,
            state_path=corrupt_state,
            drop_forming_bar=False,
        )
        assert scanner.state == {}

        setups = scanner.run_once(["BAD", "AAPL"])
        assert len(setups) == 1
        assert setups[0].symbol == "AAPL"
    finally:
        for p in (corrupt_state, journal_path):
            if os.path.isfile(p):
                os.remove(p)

    print("[ok] scanner_corrupt_state_and_isolation")
```

Add `test_scanner_drop_forming_bar`, `test_scanner_alert_on_change_and_state`,
`test_scanner_corrupt_state_and_isolation` to the `tests` list inside `main()`,
after `test_scan_symbol_uptrend_gate,`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.scanner'`

- [ ] **Step 3: Create `engine/scanner.py`**

```python
from __future__ import annotations

import csv
import datetime
import json
import logging
import os

from alerts.base import AlertSink
from core.config import AppConfig
from core.models import Action, Signal
from data.base import DataSource
from signals.detectors import Setup, scan_symbol

logger = logging.getLogger(__name__)

_JOURNAL_HEADER = [
    "scanned_at",
    "bar_date",
    "symbol",
    "price",
    "triggers",
    "context",
    "confluence",
    "decision",
    "outcome",
    "notes",
]


class Scanner:
    def __init__(
        self,
        data: DataSource,
        alert: AlertSink,
        cfg: AppConfig,
        require_uptrend: bool = True,
        journal_path: str = "journal.csv",
        state_path: str = "scanner_state.json",
        drop_forming_bar: bool = True,
    ) -> None:
        self.data = data
        self.alert = alert
        self.cfg = cfg
        self.require_uptrend = require_uptrend
        self.journal_path = journal_path
        self.state_path = state_path
        self.drop_forming_bar = drop_forming_bar
        self.state: dict = self._load_state()

    def _load_state(self) -> dict:
        if not os.path.isfile(self.state_path):
            logger.warning("scanner state file %s not found; starting fresh", self.state_path)
            return {}
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "scanner state file %s is corrupt or unreadable; starting fresh",
                self.state_path,
            )
            return {}

    def _save_state(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f)

    def _append_journal(self, setup: Setup, bar_date: str, scanned_at: str) -> None:
        is_new = not os.path.isfile(self.journal_path)
        with open(self.journal_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(_JOURNAL_HEADER)
            writer.writerow(
                [
                    scanned_at,
                    bar_date,
                    setup.symbol,
                    setup.price,
                    "|".join(setup.triggers),
                    "|".join(setup.context),
                    setup.confluence,
                    "",
                    "",
                    "",
                ]
            )

    def _to_signal(self, setup: Setup, timestamp) -> Signal:
        reason = (
            f"triggers={','.join(setup.triggers)} "
            f"context={','.join(setup.context)} "
            f"confluence={setup.confluence}"
        )
        return Signal(
            symbol=setup.symbol,
            timestamp=timestamp,
            target_position=1,
            action=Action.BUY,
            reason=reason,
            price=setup.price,
        )

    def process_symbol(self, symbol: str) -> Setup | None:
        df = self.data.get_history(symbol, self.cfg.lookback_days, self.cfg.interval)
        if self.drop_forming_bar:
            df = df.iloc[:-1]

        setup = scan_symbol(df, symbol, self.cfg, require_uptrend=self.require_uptrend)
        if setup is None:
            return None

        latest_ts = df.index[-1]
        ts_key = str(latest_ts)

        if self.state.get(symbol) == ts_key:
            return None  # already alerted this bar

        self.state[symbol] = ts_key

        scanned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._append_journal(setup, ts_key, scanned_at)

        self.alert.send(self._to_signal(setup, latest_ts))
        return setup

    def run_once(self, symbols: list[str]) -> list[Setup]:
        setups: list[Setup] = []
        for symbol in symbols:
            try:
                setup = self.process_symbol(symbol)
                if setup is not None:
                    setups.append(setup)
            except Exception:
                logger.exception("scanner failed processing symbol %s", symbol)
        self._save_state()
        return setups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m tests.scanner_test`
Expected: all `[ok]` lines so far printed, exit 0.

- [ ] **Step 5: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile engine/scanner.py tests/scanner_test.py
```
Expected: both succeed.

- [ ] **Step 6: Commit**

```bash
git add engine/scanner.py tests/scanner_test.py
git commit -m "feat: add Scanner engine with journal and alert-on-change state"
```

---

## Task 6: Entry point (`scan_main.py`) and gitignore

**Files:**
- Create: `scan_main.py`
- Modify: `.gitignore`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: `engine.scanner.Scanner` (Task 5), `data.yfinance_source.YFinanceSource`,
  `alerts.telegram.TelegramAlertSink`, `screening.sharia.ShariaFilter`,
  `core.config.AppConfig` (all existing, unmodified).
- Produces: `scan_main.build_scanner(cfg: AppConfig) -> Scanner`,
  `scan_main.WHITELIST_PATH: str`, `scan_main.main() -> None`.

- [ ] **Step 1: Write the failing test**

Add this function to `tests/scanner_test.py`, right after
`test_scanner_corrupt_state_and_isolation` and before `def main() -> int:`:

```python
def test_scan_main_imports_and_builds() -> None:
    import importlib

    from core.config import AppConfig
    from engine.scanner import Scanner

    scan_main = importlib.import_module("scan_main")

    assert callable(scan_main.build_scanner)
    scanner = scan_main.build_scanner(AppConfig())
    assert isinstance(scanner, Scanner)
    assert scan_main.WHITELIST_PATH == "whitelist.txt"

    print("[ok] scan_main_imports_and_builds")
```

Add `test_scan_main_imports_and_builds` to the `tests` list inside `main()`, after
`test_scanner_corrupt_state_and_isolation,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ModuleNotFoundError: No module named 'scan_main'`

- [ ] **Step 3: Create `scan_main.py`**

```python
"""Daily price-action scanner entry point.

Flags mechanical, unambiguous BULLISH price-action setups (liquidity sweeps,
bullish engulfing candles, bullish pin bars — see signals/detectors.py) on the
sharia whitelist. An alert means "a setup formed, go look" — it is NOT a trade
signal and makes no claim of predictive edge. All entry/exit/sizing decisions
remain fully discretionary (Smart Money Concepts price-action reading is not
mechanizable and is intentionally not automated here). This module places no
orders, paper or live, and never will (INV-D) — it only sends a Telegram alert
and appends a row to journal.csv for the user to later fill in with their
decision and outcome.

Swing needs no always-on process. Intended to run once per trading day after
the US close via cron, exactly like live_main.py, e.g. (Asia/Tashkent):
    30 2 * * 1-5 cd /path/to/trade && /usr/bin/python scan_main.py
"""
from __future__ import annotations

import logging

from alerts.telegram import TelegramAlertSink
from core.config import AppConfig
from data.yfinance_source import YFinanceSource
from engine.scanner import Scanner
from screening.sharia import ShariaFilter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

WHITELIST_PATH = "whitelist.txt"


def build_scanner(cfg: AppConfig) -> Scanner:
    source = YFinanceSource()
    alert = TelegramAlertSink(cfg.telegram_bot_token, cfg.telegram_chat_id)
    return Scanner(source, alert, cfg)


def main() -> None:
    cfg = AppConfig.from_env()
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    scanner = build_scanner(cfg)
    setups = scanner.run_once(symbols)

    if not setups:
        print("Scanned, no setups.")
        return
    for setup in setups:
        print(
            f"{setup.symbol}: triggers={setup.triggers} "
            f"context={setup.context} confluence={setup.confluence}"
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add scanner state/journal files to `.gitignore`**

Read the current `.gitignore`, then add two lines to it (alongside the existing
`state.json` entry) so the new runtime files never get committed:

```
scanner_state.json
journal.csv
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m tests.scanner_test`
Expected: all `[ok]` lines printed, exit 0.

- [ ] **Step 6: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile scan_main.py tests/scanner_test.py
```
Expected: both succeed.

- [ ] **Step 7: Commit**

```bash
git add scan_main.py .gitignore tests/scanner_test.py
git commit -m "feat: add scan_main.py entry point for the price-action scanner"
```

---

## Task 7: Full-suite verification

**Files:** none changed — verification only.

**Interfaces:** none new.

- [ ] **Step 1: Run the new scanner test suite**

Run: `python -m tests.scanner_test`
Expected: exit 0, one `[ok]` line per test — `atr`, `bullish_sweep`,
`bullish_engulfing`, `bullish_pin`, `uptrend`, `near_round_number`, `near_fvg`,
`scanner_config_defaults`, `enricher_alone_not_actionable`,
`scan_symbol_no_lookahead`, `scan_symbol_uptrend_gate`,
`scanner_drop_forming_bar`, `scanner_alert_on_change_and_state`,
`scanner_corrupt_state_and_isolation`, `scan_main_imports_and_builds`.

- [ ] **Step 2: Run the existing smoke test suite (must be untouched and green)**

Run: `python -m tests.smoke_test`
Expected: exit 0, every pre-existing `[ok]` line still present, none removed or
weakened.

- [ ] **Step 3: Compile-check every module in the repo**

Run:
```bash
python -m py_compile core/config.py core/models.py data/base.py data/yfinance_source.py indicators/indicators.py signals/base.py signals/strategies.py signals/detectors.py screening/sharia.py alerts/base.py alerts/telegram.py broker/base.py engine/backtest.py engine/live.py engine/scanner.py backtest_main.py live_main.py scan_main.py telegram_bot.py tests/smoke_test.py tests/scanner_test.py
```
Expected: no output, exit 0.

- [ ] **Step 4: Confirm no order-execution code was introduced**

Run: `python -c "import os; print(sorted(f for f in os.listdir('broker') if f.endswith('.py')))"`
Expected: `['__init__.py', 'base.py']` — matches `tests/smoke_test.py`'s
`test_execution_adapter_is_seam_only` assertion; the Scanner work must not have
added any concrete broker implementation.

- [ ] **Step 5: Report to the user**

Summarize: both test suites green, `py_compile` clean, `broker/` still seam-only.
Restate the "Design Decisions & Resolved Ambiguities" section above as the set of
judgment calls made while turning the spec's prose into exact code, so the user can
redirect any of them before real trading use. Remind the user this scanner makes no
predictive-edge claim and is signal-only — no code path in this plan places orders.

No commit for this task (verification only).

---

## Self-Review Notes

- **Spec coverage:** every functional requirement in the task brief has a task —
  triggers (Task 2), enrichers (Task 3), `Setup`/`scan_symbol` (Task 4), `Scanner`
  engine incl. alert-on-change/journal/state-tolerance/run_once-isolation (Task 5),
  `scan_main.py` incl. cron documentation and "go look" docstring (Task 6), and the
  five required test assertions (sweep fires/doesn't, engulfing fires, enricher
  alone is not actionable, no-lookahead, uptrend gate) all appear verbatim in Task 4
  / Task 2's tests.
- **Do-NOT list respected:** no execution code (`broker/` untouched, checked
  explicitly in Task 7 Step 4), no bearish detectors, no forming-bar evaluation (the
  `Scanner` drops it before calling `scan_symbol`, verified by
  `test_scanner_drop_forming_bar`), no indicator math outside
  `indicators/indicators.py` (ATR added there, not inlined), no existing test
  weakened (`tests/smoke_test.py` is never modified by this plan), no Telegram
  inline-button journaling (CSV only, via `csv.writer`).
- **Type/signature consistency check:** `scan_symbol`'s `cfg: AppConfig` parameter
  (Task 4) matches how `Scanner.process_symbol` calls it in Task 5
  (`scan_symbol(df, symbol, self.cfg, require_uptrend=self.require_uptrend)` where
  `self.cfg` is the `AppConfig` passed into `Scanner.__init__`). `Setup`'s field
  names (`triggers`, `context`, `price`, `confluence`) are used identically in
  `Scanner._to_signal` and `Scanner._append_journal`. `ScannerConfig` field names
  match between their definition (Task 4 Step 3) and every read site
  (`scan_symbol`, Task 4 Step 4).
