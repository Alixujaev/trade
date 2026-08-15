"""Offline correctness checks (no network). See SPEC.md §16.

Run as: python -m tests.smoke_test
"""
from __future__ import annotations

import sys


def test_models() -> None:
    from core.models import OHLCV_COLUMNS, Action, Signal, Trade

    assert OHLCV_COLUMNS == ["open", "high", "low", "close", "volume"]

    assert Action.BUY.value == "BUY"
    assert Action.SELL.value == "SELL"
    assert Action.HOLD.value == "HOLD"

    sig = Signal(
        symbol="AAPL",
        timestamp="2024-01-02",
        target_position=1,
        action=Action.BUY,
        reason="test",
        price=100.0,
    )
    assert sig.symbol == "AAPL"
    assert sig.target_position == 1
    try:
        sig.symbol = "MSFT"  # type: ignore[misc]
        raise AssertionError("Signal must be frozen")
    except AttributeError:
        pass

    trade = Trade(
        symbol="AAPL",
        entry_time="2024-01-02",
        exit_time="2024-01-10",
        entry_price=100.0,
        exit_price=110.0,
        shares=10,
        commission=1.5,
    )
    assert trade.gross_pnl == (110.0 - 100.0) * 10
    assert trade.net_pnl == trade.gross_pnl - trade.commission
    expected_return_pct = (110.0 - 100.0) / 100.0 * 100
    assert abs(trade.return_pct - expected_return_pct) < 1e-9

    print("[ok] models")


def test_config() -> None:
    import os

    from core.config import AppConfig, BacktestConfig, IndicatorConfig

    ind = IndicatorConfig()
    assert ind.rsi_period == 14
    assert ind.rsi_oversold == 30
    assert ind.rsi_overbought == 70
    assert ind.macd_fast == 12
    assert ind.macd_slow == 26
    assert ind.macd_signal == 9
    assert ind.ema_fast == 50
    assert ind.ema_slow == 200

    bt = BacktestConfig()
    assert bt.initial_capital == 10000
    assert bt.position_fraction == 0.95
    assert bt.commission_bps == 5
    assert bt.slippage_bps == 3

    app = AppConfig()
    assert app.interval == "1d"
    assert app.lookback_days == 400
    assert app.state_file == "state.json"
    assert isinstance(app.indicators, IndicatorConfig)
    assert isinstance(app.backtest, BacktestConfig)

    # overridable in code
    custom = AppConfig(interval="1wk", indicators=IndicatorConfig(rsi_period=21))
    assert custom.interval == "1wk"
    assert custom.indicators.rsi_period == 21

    # env loading: picks up real env vars
    os.environ["TELEGRAM_BOT_TOKEN"] = "tok123"
    os.environ["TELEGRAM_CHAT_ID"] = "chat456"
    try:
        loaded = AppConfig.from_env()
        assert loaded.telegram_bot_token == "tok123"
        assert loaded.telegram_chat_id == "chat456"
    finally:
        del os.environ["TELEGRAM_BOT_TOKEN"]
        del os.environ["TELEGRAM_CHAT_ID"]

    # graceful degrade when python-dotenv is absent
    import sys

    sys.modules["dotenv"] = None  # type: ignore[assignment]
    try:
        AppConfig.from_env()  # must not raise
    finally:
        del sys.modules["dotenv"]

    print("[ok] config")


def test_indicators() -> None:
    import numpy as np
    import pandas as pd

    from indicators.indicators import crossover, crossunder, ema, macd, rsi, sma

    # sma: min_periods == period -> first (period-1) values NaN
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    period = 3
    r = sma(s, period)
    assert r.isna().sum() == period - 1
    assert r.iloc[period - 1] == 2.0
    assert r.iloc[-1] == 4.0
    assert not r.iloc[period:].isna().any()

    # ema: same warmup NaN count; constant series stays constant after warmup
    const = pd.Series([5.0] * 10)
    e = ema(const, period)
    assert e.isna().sum() == period - 1
    assert abs(e.iloc[-1] - 5.0) < 1e-9

    # rsi: Wilder smoothing, first `period` values NaN, bounded [0,100]
    rp = 14
    prices = pd.Series(np.linspace(100, 100 + 2 * (rp + 20), rp + 20 + 1))  # strictly increasing
    rsi_vals = rsi(prices, period=rp)
    assert rsi_vals.isna().sum() == rp
    valid = rsi_vals.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()
    # strictly increasing prices -> avg_loss == 0 -> RSI == 100
    assert (valid == 100).all()

    # random-walk-ish series stays within bounds too
    rng = np.random.default_rng(0)
    walk = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    rsi_walk = rsi(walk, period=rp).dropna()
    assert (rsi_walk >= 0).all() and (rsi_walk <= 100).all()

    # macd: returns DataFrame with macd/signal/hist columns
    long_series = pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)))
    macd_df = macd(long_series, fast=12, slow=26, signal=9)
    assert list(macd_df.columns) == ["macd", "signal", "hist"]
    assert len(macd_df) == len(long_series)
    valid_hist = macd_df["hist"].dropna()
    computed_hist = (macd_df["macd"] - macd_df["signal"]).dropna()
    assert np.allclose(valid_hist.values, computed_hist.values)

    # crossover / crossunder
    a = pd.Series([1, 2, 3, 2, 1, 2, 3])
    b = pd.Series([2, 2, 2, 2, 2, 2, 2])
    co = crossover(a, b)
    cu = crossunder(a, b)
    assert co.dtype == bool and cu.dtype == bool
    # a crosses above b at index 2 (3 > 2 while prev 2 <= 2)
    assert co.iloc[2] == True  # noqa: E712
    assert co.iloc[0] == False  # noqa: E712
    # a crosses below b at index 4 (1 < 2 while prev 2 >= 2)
    assert cu.iloc[4] == True  # noqa: E712

    print("[ok] indicators")


def test_data_source_validation() -> None:
    import pandas as pd

    from data.base import DataSource

    # empty -> rejected
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    try:
        DataSource._validate(empty)
        raise AssertionError("expected ValueError on empty data")
    except ValueError:
        pass

    # missing column -> rejected
    missing_col = pd.DataFrame(
        {"open": [1], "high": [1], "low": [1], "close": [1]},
        index=pd.to_datetime(["2024-01-01"]),
    )
    try:
        DataSource._validate(missing_col)
        raise AssertionError("expected ValueError on missing column")
    except ValueError:
        pass

    # duplicate timestamps dropped, unsorted rows sorted ascending, column order enforced
    idx = pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02", "2024-01-01"])
    raw = pd.DataFrame(
        {
            "volume": [100, 200, 300, 999],
            "close": [3.0, 1.0, 2.0, 1.5],
            "open": [3.0, 1.0, 2.0, 1.5],
            "high": [3.0, 1.0, 2.0, 1.5],
            "low": [3.0, 1.0, 2.0, 1.5],
            "extra": [0, 0, 0, 0],
        },
        index=idx,
    )
    result = DataSource._validate(raw)
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert list(result.index) == list(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    assert result.index.is_monotonic_increasing
    assert not result.index.duplicated().any()
    # first occurrence of the duplicate 2024-01-01 kept (volume 200, not 999)
    assert result.loc[pd.Timestamp("2024-01-01"), "volume"] == 200

    print("[ok] data_source_validation")


def test_yfinance_source_lazy_import() -> None:
    import importlib
    import sys

    sys.modules["yfinance"] = None  # type: ignore[assignment]  # forces ImportError if imported eagerly
    try:
        sys.modules.pop("data.yfinance_source", None)
        mod = importlib.import_module("data.yfinance_source")
        assert hasattr(mod, "YFinanceSource")
        source = mod.YFinanceSource()  # construction must not import yfinance either
        assert source is not None
    finally:
        del sys.modules["yfinance"]
        sys.modules.pop("data.yfinance_source", None)

    print("[ok] yfinance_source_lazy_import")


def test_strategy_base() -> None:
    import pandas as pd

    from signals.base import Strategy, _hold_between

    # Strategy is abstract
    try:
        Strategy()  # type: ignore[abstract]
        raise AssertionError("Strategy must be abstract")
    except TypeError:
        pass

    idx = pd.RangeIndex(8)
    entries = pd.Series([False, False, True, False, False, False, False, False], index=idx)
    exits = pd.Series([False, False, False, False, False, True, False, False], index=idx)
    pos = _hold_between(entries, exits)
    assert list(pos) == [0, 0, 1, 1, 1, 0, 0, 0]
    assert pos.index.equals(idx)
    assert pos.dtype.kind in "iu"

    # no entry -> always flat
    flat = _hold_between(pd.Series([False] * 5), pd.Series([False] * 5))
    assert list(flat) == [0, 0, 0, 0, 0]

    # re-entry after exit
    entries2 = pd.Series([True, False, False, True, False])
    exits2 = pd.Series([False, False, True, False, False])
    pos2 = _hold_between(entries2, exits2)
    assert list(pos2) == [1, 1, 0, 1, 1]

    print("[ok] strategy_base")


def _synthetic_close_series():
    import numpy as np
    import pandas as pd

    down = np.linspace(100, 80, 11)[1:]  # 10 steps down
    up = np.linspace(80, 140, 21)[1:]  # 20 steps strongly up
    back_down = np.linspace(140, 110, 11)[1:]  # 10 steps down
    prices = np.concatenate([[100], down, up, back_down])
    idx = pd.date_range("2023-01-02", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices}, index=idx)


def test_strategies() -> None:
    import pandas as pd

    from core.config import IndicatorConfig
    from indicators.indicators import crossover, crossunder, ema, macd, rsi
    from signals.base import Strategy, _hold_between
    from signals.strategies import (
        CombinedStrategy,
        EmaCrossStrategy,
        MacdStrategy,
        RsiStrategy,
    )

    df = _synthetic_close_series()
    cfg = IndicatorConfig(rsi_period=5, rsi_oversold=30, rsi_overbought=70)

    # RsiStrategy: entries on crossover(rsi, oversold), exits on crossunder(rsi, overbought)
    rsi_strat = RsiStrategy(cfg)
    pos = rsi_strat.target_position(df)
    assert set(pos.unique()).issubset({0, 1})
    assert pos.index.equals(df.index)
    r = rsi(df["close"], period=cfg.rsi_period)
    expected = _hold_between(
        crossover(r, pd.Series(cfg.rsi_oversold, index=df.index)),
        crossunder(r, pd.Series(cfg.rsi_overbought, index=df.index)),
    )
    assert list(pos) == list(expected)
    # warmup region forced to 0
    assert (pos.iloc[: cfg.rsi_period] == 0).all()
    # this synthetic series must produce at least one entry and one exit
    assert (pos.diff() == 1).any()
    assert (pos.diff() == -1).any()

    # MacdStrategy: long while macd line > signal line, warmup forced to 0
    macd_strat = MacdStrategy(cfg)
    macd_pos = macd_strat.target_position(df)
    assert set(macd_pos.unique()).issubset({0, 1})
    macd_df = macd(df["close"], fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal)
    warmup = macd_df["macd"].isna() | macd_df["signal"].isna()
    assert (macd_pos[warmup] == 0).all()
    assert (macd_pos[~warmup] == (macd_df["macd"] > macd_df["signal"])[~warmup].astype(int)).all()

    # EmaCrossStrategy: long while fast ema > slow ema, warmup forced to 0
    ema_cfg = IndicatorConfig(ema_fast=3, ema_slow=8)
    ema_strat = EmaCrossStrategy(ema_cfg)
    ema_pos = ema_strat.target_position(df)
    fast = ema(df["close"], ema_cfg.ema_fast)
    slow = ema(df["close"], ema_cfg.ema_slow)
    ema_warmup = fast.isna() | slow.isna()
    assert (ema_pos[ema_warmup] == 0).all()
    assert (ema_pos[~ema_warmup] == (fast > slow)[~ema_warmup].astype(int)).all()

    # CombinedStrategy: all / any / majority modes
    class _Fixed(Strategy):
        def __init__(self, values, name):
            self._values = values
            self.name = name

        def target_position(self, frame):
            return pd.Series(self._values, index=frame.index)

    idx6 = pd.RangeIndex(6)
    a = _Fixed([1, 1, 0, 0, 1, 0], "a")
    b = _Fixed([1, 0, 1, 0, 1, 0], "b")
    c = _Fixed([1, 0, 0, 1, 1, 1], "c")
    frame6 = pd.DataFrame({"close": [0] * 6}, index=idx6)

    all_combo = CombinedStrategy([a, b, c], mode="all")
    assert list(all_combo.target_position(frame6)) == [1, 0, 0, 0, 1, 0]
    assert "all" in all_combo.name

    any_combo = CombinedStrategy([a, b, c], mode="any")
    assert list(any_combo.target_position(frame6)) == [1, 1, 1, 1, 1, 1]

    majority_combo = CombinedStrategy([a, b, c], mode="majority")
    assert list(majority_combo.target_position(frame6)) == [1, 0, 0, 0, 1, 0]

    default_combo = CombinedStrategy([a, b, c])
    assert default_combo.mode == "all"

    try:
        CombinedStrategy([a, b], mode="bogus")
        raise AssertionError("expected ValueError for unknown mode")
    except ValueError:
        pass

    print("[ok] strategies")


def test_sharia_filter() -> None:
    import logging
    import os
    import tempfile

    from screening.sharia import ShariaFilter

    direct = ShariaFilter({"AAPL", "MSFT"})
    assert direct.is_allowed("AAPL")
    assert not direct.is_allowed("TSLA")
    assert direct.filter(["AAPL", "TSLA", "MSFT", "NVDA"]) == ["AAPL", "MSFT"]

    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("# comment line\n")
            f.write("AAPL\n")
            f.write("\n")
            f.write("  MSFT  \n")
            f.write("# another comment\n")

        loaded = ShariaFilter.from_file(path)
        assert loaded.is_allowed("AAPL")
        assert loaded.is_allowed("MSFT")
        assert not loaded.is_allowed("TSLA")

        # rejected symbols logged at WARNING
        logger = logging.getLogger("screening.sharia")
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            loaded.filter(["AAPL", "TSLA"])
        finally:
            logger.removeHandler(handler)
        assert any(r.levelno == logging.WARNING and "TSLA" in r.getMessage() for r in records)
    finally:
        os.remove(path)

    # missing file -> raises
    try:
        ShariaFilter.from_file(os.path.join(tempfile.gettempdir(), "does-not-exist-xyz.txt"))
        raise AssertionError("expected error on missing file")
    except (FileNotFoundError, OSError):
        pass

    # empty file -> raises
    fd2, empty_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd2)
    try:
        try:
            ShariaFilter.from_file(empty_path)
            raise AssertionError("expected error on empty whitelist file")
        except ValueError:
            pass
    finally:
        os.remove(empty_path)

    print("[ok] sharia_filter")


def test_telegram_alert_sink() -> None:
    import requests

    from alerts.base import AlertSink
    from alerts.telegram import TelegramAlertSink
    from core.models import Action, Signal

    try:
        AlertSink()  # type: ignore[abstract]
        raise AssertionError("AlertSink must be abstract")
    except TypeError:
        pass

    sig = Signal(
        symbol="AAPL",
        timestamp="2024-01-02",
        target_position=1,
        action=Action.BUY,
        reason="rsi crossed up out of oversold",
        price=123.45,
    )

    calls = []

    class _FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post_ok(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return _FakeResponse()

    sink = TelegramAlertSink(token="TOK", chat_id="CHAT")
    orig_post = requests.post
    requests.post = fake_post_ok
    try:
        sink.send(sig)
    finally:
        requests.post = orig_post

    assert len(calls) == 1
    url, payload, timeout = calls[0]
    assert "TOK" in url
    assert payload["chat_id"] == "CHAT"
    text = payload["text"]
    assert "AAPL" in text
    assert "123.45" in text
    assert "2024-01-02" in text
    assert "rsi crossed up out of oversold" in text
    assert "BUY" in text
    assert "signal only" in text.lower()
    assert "no order" in text.lower()

    # send failures must be swallowed, never raised
    def fake_post_fail(url, json=None, timeout=None):
        raise requests.exceptions.ConnectionError("boom")

    requests.post = fake_post_fail
    try:
        sink.send(sig)  # must not raise
    finally:
        requests.post = orig_post

    print("[ok] telegram_alert_sink")


def test_execution_adapter_is_seam_only() -> None:
    import os

    from broker.base import ExecutionAdapter

    try:
        ExecutionAdapter()  # type: ignore[abstract]
        raise AssertionError("ExecutionAdapter must be abstract")
    except TypeError:
        pass

    # v1.0 must not ship any concrete broker implementation (INV-9 / §18)
    broker_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "broker")
    files = [f for f in os.listdir(broker_dir) if f.endswith(".py")]
    assert set(files) == {"__init__.py", "base.py"}, f"unexpected broker files: {files}"

    print("[ok] execution_adapter_is_seam_only")


def _mk_ohlcv(opens, closes):
    import pandas as pd

    idx = pd.date_range("2023-01-02", periods=len(opens), freq="B")
    opens_s = pd.Series(opens, index=idx, dtype=float)
    closes_s = pd.Series(closes, index=idx, dtype=float)
    hi = opens_s.combine(closes_s, max) + 1
    lo = opens_s.combine(closes_s, min) - 1
    return pd.DataFrame(
        {"open": opens_s, "high": hi, "low": lo, "close": closes_s, "volume": 1_000_000},
        index=idx,
    )


def test_backtest_engine() -> None:
    import pandas as pd

    from core.config import BacktestConfig
    from engine.backtest import compute_metrics, run_backtest
    from signals.base import Strategy
    from signals.strategies import CombinedStrategy, MacdStrategy, RsiStrategy

    class _Fixed(Strategy):
        name = "fixed"

        def __init__(self, values):
            self._values = values

        def target_position(self, frame):
            return pd.Series(self._values, index=frame.index)

    # ---- FR-19/20/21/22 fill mechanics on one deterministic round trip ----
    opens = [100, 101, 102, 103, 104]
    closes = [100.5, 101.5, 102.5, 103.5, 104.5]
    df = _mk_ohlcv(opens, closes)
    strat = _Fixed([0, 1, 1, 0, 0])  # entry realized bar2 open, exit realized bar4 open

    zero_cfg = BacktestConfig(
        initial_capital=1000, position_fraction=1.0, commission_bps=0, slippage_bps=0
    )
    zero_result = run_backtest(df, strat, zero_cfg, symbol="T")
    eq0 = zero_result.equity_curve
    assert abs(eq0.iloc[0] - 1000) < 1e-9
    assert abs(eq0.iloc[1] - 1000) < 1e-9
    assert abs(eq0.iloc[2] - 1004.5) < 1e-6
    assert abs(eq0.iloc[3] - 1013.5) < 1e-6
    assert abs(eq0.iloc[4] - 1018.0) < 1e-6
    assert len(zero_result.trades) == 1
    t0 = zero_result.trades[0]
    assert abs(t0.entry_price - 102) < 1e-9
    assert abs(t0.exit_price - 104) < 1e-9
    assert t0.shares == 9
    assert abs(t0.commission - 0.0) < 1e-9

    cost_cfg = BacktestConfig(
        initial_capital=1000, position_fraction=1.0, commission_bps=100, slippage_bps=100
    )
    cost_result = run_backtest(df, strat, cost_cfg, symbol="T")
    eqc = cost_result.equity_curve
    assert abs(eqc.iloc[2] - 986.0482) < 1e-3
    assert abs(eqc.iloc[3] - 995.0482) < 1e-3
    assert abs(eqc.iloc[4] - 980.9218) < 1e-3
    tc = cost_result.trades[0]
    assert abs(tc.entry_price - 103.02) < 1e-6
    assert abs(tc.exit_price - 102.96) < 1e-6
    assert tc.shares == 9
    assert abs(tc.commission - 18.5382) < 1e-3

    # AC-3: nonzero costs strictly worse than zero costs, given >=1 trade
    assert len(cost_result.trades) >= 1
    assert eqc.iloc[-1] < eq0.iloc[-1]

    # ---- AC-2: no lookahead. Flip at bar k -> equity flat through k, changes from k+1 ----
    n = 12
    k = 5
    lk_opens = [100.0] * n
    lk_closes = [100.0] * (k + 1) + [110.0] * (n - k - 1)
    lk_df = _mk_ohlcv(lk_opens, lk_closes)

    class _FlipAt(Strategy):
        name = "flip"

        def target_position(self, frame):
            return pd.Series([0] * k + [1] * (len(frame) - k), index=frame.index)

    lk_cfg = BacktestConfig(
        initial_capital=10000, position_fraction=0.95, commission_bps=0, slippage_bps=0
    )
    lk_result = run_backtest(lk_df, _FlipAt(), lk_cfg, symbol="T")
    eq = lk_result.equity_curve
    assert (abs(eq.iloc[: k + 1] - lk_cfg.initial_capital) < 1e-9).all()
    assert abs(eq.iloc[k + 1] - lk_cfg.initial_capital) > 1e-6

    # ---- AC-4: CombinedStrategy runs, compute_metrics returns the full metric set ----
    close_series = _synthetic_close_series()["close"]
    big_opens = close_series.shift(1).bfill()
    big_df = pd.DataFrame(
        {
            "open": big_opens,
            "high": pd.concat([big_opens, close_series], axis=1).max(axis=1) + 0.5,
            "low": pd.concat([big_opens, close_series], axis=1).min(axis=1) - 0.5,
            "close": close_series,
            "volume": 1_000_000,
        },
        index=close_series.index,
    )
    combo = CombinedStrategy([RsiStrategy(), MacdStrategy()], mode="any")
    combo_result = run_backtest(big_df, combo, BacktestConfig(), symbol="COMBO")
    metrics = compute_metrics(combo_result)
    expected_keys = {
        "total_return_pct",
        "cagr_pct",
        "sharpe",
        "max_drawdown_pct",
        "num_trades",
        "win_rate_pct",
        "avg_win",
        "avg_loss",
        "expectancy_per_trade",
    }
    assert expected_keys.issubset(metrics.keys())
    for key in expected_keys:
        assert metrics[key] == metrics[key]  # not NaN

    print("[ok] backtest_engine")


def test_live_engine() -> None:
    import json
    import os
    import tempfile

    import pandas as pd

    from alerts.base import AlertSink
    from core.config import AppConfig
    from core.models import Action
    from data.base import DataSource
    from engine.live import LiveEngine
    from signals.base import Strategy

    class _FakeSource(DataSource):
        def __init__(self, df):
            self._df = df

        def get_history(self, symbol, lookback_days, interval="1d"):
            return self._df.copy()

    class _FlakySource(DataSource):
        def __init__(self, good_df):
            self._good_df = good_df

        def get_history(self, symbol, lookback_days, interval="1d"):
            if symbol == "BAD":
                raise RuntimeError("network down")
            return self._good_df.copy()

    class _FakeAlert(AlertSink):
        def __init__(self):
            self.sent = []

        def send(self, signal):
            self.sent.append(signal)

    class _ThresholdStrategy(Strategy):
        name = "threshold"

        def target_position(self, frame):
            return (frame["close"] >= 20).astype(int)

    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    df_high_last = pd.DataFrame(
        {
            "open": [9.0, 19.0, 29.0],
            "high": [11.0, 21.0, 31.0],
            "low": [8.0, 18.0, 28.0],
            "close": [10.0, 20.0, 30.0],
            "volume": [1, 1, 1],
        },
        index=idx,
    )

    def _tmp_state_path():
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)  # want a nonexistent path -> "no prior state" scenario
        return path

    # ---- FR-25: drop_forming_bar excludes the last (possibly still-forming) bar ----
    state_path_a = _tmp_state_path()
    try:
        cfg = AppConfig(state_file=state_path_a, lookback_days=100, interval="1d")
        source = _FakeSource(df_high_last)
        alert = _FakeAlert()
        engine = LiveEngine(source, _ThresholdStrategy(), alert, cfg, drop_forming_bar=True)
        sig = engine.process_symbol("AAPL")
        assert sig is not None
        assert sig.action == Action.BUY
        assert sig.price == 20.0  # forming bar (close=30) dropped; decision bar is close=20
        assert sig.timestamp == idx[1]
    finally:
        if os.path.isfile(state_path_a):
            os.remove(state_path_a)

    state_path_b = _tmp_state_path()
    try:
        cfg = AppConfig(state_file=state_path_b, lookback_days=100, interval="1d")
        source = _FakeSource(df_high_last)
        alert = _FakeAlert()
        engine = LiveEngine(source, _ThresholdStrategy(), alert, cfg, drop_forming_bar=False)
        sig = engine.process_symbol("AAPL")
        assert sig is not None
        assert sig.price == 30.0  # forming bar included
        assert sig.timestamp == idx[2]
    finally:
        if os.path.isfile(state_path_b):
            os.remove(state_path_b)

    # ---- FR-26/FR-27: alert-on-change, silent while holding, state persisted ----
    state_path_c = _tmp_state_path()
    try:
        cfg = AppConfig(state_file=state_path_c, lookback_days=100, interval="1d")
        source = _FakeSource(df_high_last)
        alert = _FakeAlert()
        engine = LiveEngine(source, _ThresholdStrategy(), alert, cfg, drop_forming_bar=True)

        sig1 = engine.process_symbol("AAPL")
        assert sig1 is not None and sig1.action == Action.BUY
        assert len(alert.sent) == 1

        sig2 = engine.process_symbol("AAPL")  # same data again -> holding, silent
        assert sig2 is None
        assert len(alert.sent) == 1

        df_low = pd.DataFrame(
            {
                "open": [4.0, 5.0, 6.0],
                "high": [5.0, 6.0, 7.0],
                "low": [3.0, 4.0, 5.0],
                "close": [4.0, 5.0, 6.0],
                "volume": [1, 1, 1],
            },
            index=idx,
        )
        source._df = df_low
        sig3 = engine.process_symbol("AAPL")
        assert sig3 is not None and sig3.action == Action.SELL
        assert len(alert.sent) == 2
    finally:
        if os.path.isfile(state_path_c):
            os.remove(state_path_c)

    # ---- FR-27: corrupt/missing state file tolerated, starts fresh, logs warning ----
    import logging

    fd, corrupt_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write("{not valid json")
    try:
        logger = logging.getLogger("engine.live")
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            cfg = AppConfig(state_file=corrupt_path, lookback_days=100, interval="1d")
            engine = LiveEngine(
                _FakeSource(df_high_last), _ThresholdStrategy(), _FakeAlert(), cfg
            )
        finally:
            logger.removeHandler(handler)
        assert engine.state == {}
        assert any(r.levelno == logging.WARNING for r in records)
    finally:
        os.remove(corrupt_path)

    # ---- FR-28: run_once isolates a per-symbol failure and still processes others ----
    state_path_d = _tmp_state_path()
    try:
        cfg = AppConfig(state_file=state_path_d, lookback_days=100, interval="1d")
        flaky = _FlakySource(df_high_last)
        alert = _FakeAlert()
        engine = LiveEngine(flaky, _ThresholdStrategy(), alert, cfg, drop_forming_bar=True)
        signals = engine.run_once(["BAD", "AAPL"])
        assert len(signals) == 1
        assert signals[0].symbol == "AAPL"

        assert os.path.isfile(state_path_d)
        with open(state_path_d, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved.get("AAPL") == 1
        assert "BAD" not in saved
    finally:
        if os.path.isfile(state_path_d):
            os.remove(state_path_d)

    print("[ok] live_engine")


def test_entry_points_import_and_share_strategy() -> None:
    import importlib

    from core.config import AppConfig
    from signals.base import Strategy

    backtest_main = importlib.import_module("backtest_main")
    live_main = importlib.import_module("live_main")

    assert hasattr(backtest_main, "build_strategy")
    # FR-33: live_main imports build_strategy from backtest_main -> exact same object
    assert live_main.build_strategy is backtest_main.build_strategy

    strategy = backtest_main.build_strategy(AppConfig())
    assert isinstance(strategy, Strategy)

    print("[ok] entry_points_import_and_share_strategy")


def test_backtest_main_helpers() -> None:
    import backtest_main

    rows = [
        (
            "AAPL",
            {
                "total_return_pct": 12.3,
                "cagr_pct": 6.7,
                "sharpe": 1.2,
                "max_drawdown_pct": -5.5,
                "num_trades": 3,
                "win_rate_pct": 66.7,
                "avg_win": 10.0,
                "avg_loss": -4.0,
                "expectancy_per_trade": 42.0,
            },
        ),
    ]
    table = backtest_main.format_metrics_table(rows)
    assert table.startswith("symbol\ttotal_return_pct\t")
    assert "AAPL\t12.30\t6.70\t1.20\t-5.50\t3\t66.70\t42.00" in table

    assert backtest_main.format_metrics_table([]) == "No results."

    assert callable(backtest_main.run_all_backtests)

    print("[ok] backtest_main_helpers")


def test_live_main_helpers() -> None:
    import live_main
    from core.models import Action, Signal

    assert live_main.format_signals([]) == "Tekshirildi, o'zgarish yo'q."

    sigs = [
        Signal(
            symbol="MSFT",
            timestamp="2024-01-02",
            target_position=1,
            action=Action.BUY,
            reason="x",
            price=1.0,
        ),
        Signal(
            symbol="NVDA",
            timestamp="2024-01-02",
            target_position=0,
            action=Action.SELL,
            reason="y",
            price=2.0,
        ),
    ]
    text = live_main.format_signals(sigs)
    assert text == "Tekshirildi: 2 ta signal (MSFT BUY, NVDA SELL)."

    assert callable(live_main.build_live_engine)

    print("[ok] live_main_helpers")


def test_telegram_bot_auth_and_parsing() -> None:
    import telegram_bot
    from core.config import AppConfig

    cfg = AppConfig(telegram_bot_token="TOK", telegram_chat_id="881912596")

    owner_update = {"message": {"chat": {"id": 881912596}, "text": "/status"}}
    stranger_update = {"message": {"chat": {"id": 111}, "text": "/status"}}
    assert telegram_bot._is_authorized(owner_update, cfg)
    assert not telegram_bot._is_authorized(stranger_update, cfg)
    # chat id as string still matches (Telegram sends ints; cfg stores str from env)
    assert telegram_bot._is_authorized(
        {"message": {"chat": {"id": "881912596"}, "text": "hi"}}, cfg
    )
    assert not telegram_bot._is_authorized({"edited_message": {}}, cfg)

    assert telegram_bot._command_text({"message": {"text": "/run"}}) == "/run"
    assert telegram_bot._command_text({"message": {"text": "/run@MyBot"}}) == "/run"
    assert (
        telegram_bot._command_text({"message": {"text": "/backtest now please"}})
        == "/backtest"
    )
    assert telegram_bot._command_text({"message": {}}) is None
    assert telegram_bot._command_text({"edited_message": {"text": "/run"}}) is None

    help_text = telegram_bot.handle_help()
    assert "/run" in help_text
    assert "/backtest" in help_text
    assert "/status" in help_text
    assert "/help" in help_text

    print("[ok] telegram_bot_auth_and_parsing")


def test_telegram_bot_api_wrappers() -> None:
    import requests

    import telegram_bot
    from core.config import AppConfig

    cfg = AppConfig(telegram_bot_token="TOK", telegram_chat_id="123")

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    # fetch_updates: parses the "result" list, passes offset/timeout through
    get_calls = []

    def fake_get(url, params=None, timeout=None):
        get_calls.append((url, params, timeout))
        return _FakeResp({"ok": True, "result": [{"update_id": 5}, {"update_id": 6}]})

    orig_get = requests.get
    requests.get = fake_get
    try:
        updates = telegram_bot.fetch_updates(cfg, offset=5, timeout=30)
    finally:
        requests.get = orig_get
    assert updates == [{"update_id": 5}, {"update_id": 6}]
    assert "TOK" in get_calls[0][0]
    assert get_calls[0][1] == {"offset": 5, "timeout": 30}

    # next_offset: advances past the highest update_id seen; unchanged when empty
    assert telegram_bot.next_offset([], 5) == 5
    assert telegram_bot.next_offset([{"update_id": 5}, {"update_id": 7}], 5) == 8

    # send_reply: posts to sendMessage; failures are swallowed, never raised
    post_calls = []

    def fake_post_ok(url, json=None, timeout=None):
        post_calls.append((url, json, timeout))
        return _FakeResp({"ok": True})

    orig_post = requests.post
    requests.post = fake_post_ok
    try:
        telegram_bot.send_reply(cfg, 123, "salom")
    finally:
        requests.post = orig_post
    assert post_calls[0][1] == {"chat_id": 123, "text": "salom"}

    def fake_post_fail(url, json=None, timeout=None):
        raise requests.exceptions.ConnectionError("boom")

    requests.post = fake_post_fail
    try:
        telegram_bot.send_reply(cfg, 123, "salom")  # must not raise
    finally:
        requests.post = orig_post

    # register_commands: posts setMyCommands with all four commands
    reg_calls = []

    def fake_post_register(url, json=None, timeout=None):
        reg_calls.append((url, json, timeout))
        return _FakeResp({"ok": True})

    requests.post = fake_post_register
    try:
        telegram_bot.register_commands(cfg)
    finally:
        requests.post = orig_post
    assert "setMyCommands" in reg_calls[0][0]
    assert {
        "command": "run",
        "description": "Bugungi signalni tekshirish",
    } in reg_calls[0][1]["commands"]

    # register_commands: failures swallowed too
    requests.post = fake_post_fail
    try:
        telegram_bot.register_commands(cfg)  # must not raise
    finally:
        requests.post = orig_post

    print("[ok] telegram_bot_api_wrappers")


def test_telegram_bot_dispatch_and_handlers() -> None:
    import requests

    import telegram_bot
    from core.config import AppConfig
    from core.models import Action, Signal

    cfg = AppConfig(telegram_bot_token="TOK", telegram_chat_id="123")

    class _FakeEngine:
        def __init__(self):
            self.state = {"AAPL": 1, "MSFT": 0}

        def run_once(self, symbols):
            return [
                Signal(
                    symbol="AAPL",
                    timestamp="t",
                    target_position=1,
                    action=Action.BUY,
                    reason="x",
                    price=1.0,
                )
            ]

    def fake_backtest_rows(cfg):
        return [
            (
                "AAPL",
                {
                    "total_return_pct": 1.0,
                    "cagr_pct": 1.0,
                    "sharpe": 1.0,
                    "max_drawdown_pct": -1.0,
                    "num_trades": 1,
                    "win_rate_pct": 100.0,
                    "avg_win": 1.0,
                    "avg_loss": 0.0,
                    "expectancy_per_trade": 1.0,
                },
            )
        ]

    orig_build_engine = telegram_bot.build_live_engine
    orig_run_backtests = telegram_bot.run_all_backtests
    orig_load_symbols = telegram_bot._load_symbols
    telegram_bot.build_live_engine = lambda cfg: _FakeEngine()
    telegram_bot._load_symbols = lambda: ["AAPL", "MSFT"]
    telegram_bot.run_all_backtests = fake_backtest_rows
    try:
        assert telegram_bot.handle_run(cfg) == "Tekshirildi: 1 ta signal (AAPL BUY)."

        status = telegram_bot.handle_status(cfg)
        assert "AAPL: long" in status
        assert "MSFT: flat" in status

        backtest_text = telegram_bot.handle_backtest(cfg)
        assert "AAPL" in backtest_text

        # ---- dispatch: authorization, routing, error isolation ----
        sent = []

        def fake_post(url, json=None, timeout=None):
            sent.append(json)

            class _R:
                def raise_for_status(self):
                    pass

            return _R()

        orig_post = requests.post
        requests.post = fake_post
        try:
            # unauthorized sender: dropped silently, no reply
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 999}, "text": "/status"}}, cfg
            )
            assert sent == []

            # authorized /status
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/status"}}, cfg
            )
            assert len(sent) == 1
            assert "AAPL: long" in sent[0]["text"]

            # authorized /run
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/run"}}, cfg
            )
            assert len(sent) == 2
            assert sent[1]["text"] == "Tekshirildi: 1 ta signal (AAPL BUY)."

            # authorized /backtest (still the working fake at this point)
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/backtest"}}, cfg
            )
            assert len(sent) == 3
            assert "AAPL" in sent[2]["text"]

            # unknown command
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/bogus"}}, cfg
            )
            assert sent[3]["text"] == "Noma'lum buyruq. /help"

            # /help
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/help"}}, cfg
            )
            assert "/run" in sent[4]["text"]

            # non-message update types are ignored (no reply)
            telegram_bot.dispatch(
                {"edited_message": {"chat": {"id": 123}, "text": "/status"}}, cfg
            )
            assert len(sent) == 5

            # handler error is caught, reported to the chat, dispatch doesn't raise
            def broken_backtests(cfg):
                raise RuntimeError("boom")

            telegram_bot.run_all_backtests = broken_backtests
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/backtest"}}, cfg
            )
            assert "Xatolik yuz berdi" in sent[5]["text"]
        finally:
            requests.post = orig_post
    finally:
        telegram_bot.build_live_engine = orig_build_engine
        telegram_bot.run_all_backtests = orig_run_backtests
        telegram_bot._load_symbols = orig_load_symbols

    print("[ok] telegram_bot_dispatch_and_handlers")


def main() -> int:
    tests = [
        test_models,
        test_config,
        test_indicators,
        test_data_source_validation,
        test_yfinance_source_lazy_import,
        test_strategy_base,
        test_strategies,
        test_sharia_filter,
        test_telegram_alert_sink,
        test_execution_adapter_is_seam_only,
        test_backtest_engine,
        test_live_engine,
        test_entry_points_import_and_share_strategy,
        test_backtest_main_helpers,
        test_live_main_helpers,
        test_telegram_bot_auth_and_parsing,
        test_telegram_bot_api_wrappers,
        test_telegram_bot_dispatch_and_handlers,
    ]
    for t in tests:
        t()
    return 0


if __name__ == "__main__":
    sys.exit(main())
