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

    # High price: under the old unbounded formula tol = tol_frac * price = 5.03,
    # which would wrongly call this "near" a round number (distance 2.0 <= 5.03).
    # The capped formula limits tol to _ROUND_NUMBER_UNIT * 0.1 = 0.5, so
    # distance 2.0 > 0.5 correctly reports False.
    high_price_false_positive = _mk_bars([[502.0, 504.5, 501.5, 503.0]])  # nearest 5-multiple is 505
    assert near_round_number(high_price_false_positive, tol_frac=0.01) is False

    print("[ok] near_round_number")


def test_format_setup_alert_text() -> None:
    from signals.detectors import Setup, format_setup_alert_text

    setup = Setup(
        symbol="AAPL",
        triggers=["liquidity_sweep", "bullish_engulfing"],
        context=["uptrend", "near_round_number"],
        price=226.30,
        confluence=4,
    )
    text = format_setup_alert_text(setup, "2026-08-18")

    assert text == (
        "\U0001f50d <b>AAPL</b> — setup shakllandi, ko'rib chiq\n"
        "<b>Belgi:</b> liquidity sweep + bullish engulfing\n"
        "<b>Kontekst:</b> uptrend, $225 atrofida\n"
        "<b>Narx:</b> $226.30\n"
        "<b>Sana:</b> 2026-08-18\n"
        "<b>Kuchi:</b> 4 ta belgi\n"
        "\n"
        "<i>Savdo signali emas — chartni oching va o'zingiz qaror qiling.</i>"
    )

    print("[ok] format_setup_alert_text")


def test_format_setup_alert_text_no_context() -> None:
    from signals.detectors import Setup, format_setup_alert_text

    setup = Setup(
        symbol="MSFT",
        triggers=["bullish_pin"],
        context=[],
        price=99.99,
        confluence=1,
    )
    text = format_setup_alert_text(setup, "2026-08-18")

    assert "Kontekst:" not in text
    assert text == (
        "\U0001f50d <b>MSFT</b> — setup shakllandi, ko'rib chiq\n"
        "<b>Belgi:</b> bullish pin\n"
        "<b>Narx:</b> $99.99\n"
        "<b>Sana:</b> 2026-08-18\n"
        "<b>Kuchi:</b> 1 ta belgi\n"
        "\n"
        "<i>Savdo signali emas — chartni oching va o'zingiz qaror qiling.</i>"
    )

    print("[ok] format_setup_alert_text_no_context")


def test_format_setup_alert_text_emoji_and_no_separators() -> None:
    import re
    import unicodedata

    from signals.detectors import Setup, format_setup_alert_text

    setup = Setup(
        symbol="NVDA",
        triggers=["liquidity_sweep", "bullish_engulfing", "bullish_pin"],
        context=["uptrend", "near_fvg", "near_round_number"],
        price=101.20,
        confluence=6,
    )
    text = format_setup_alert_text(setup, "2026-08-18")

    # Exactly one emoji-category ("So" = Symbol, other) character anywhere in
    # the text, and it must be the single header magnifying-glass -- proves
    # "exactly one emoji, no other emoji anywhere".
    symbol_chars = [ch for ch in text if unicodedata.category(ch) == "So"]
    assert symbol_chars == ["\U0001f50d"]

    # No box-drawing characters (U+2500-U+257F) anywhere.
    assert not any("─" <= ch <= "╿" for ch in text)

    # No run of 3+ separator-ish characters (---, ===, ___, repeated dashes) --
    # the two single em-dashes the template itself uses are fine, a *run* of
    # 3+ is what breaks on narrow mobile screens.
    assert re.search(r"[-=_—–]{3,}", text) is None

    print("[ok] format_setup_alert_text_emoji_and_no_separators")


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
        assert "SCANNER: setup formed, go look — not a trade signal." in alert.sent[0].reason
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


def test_scanner_alert_formatted_text() -> None:
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
    )  # bar0 bearish, bar1 bullish engulf -> fires with drop_forming_bar=False;
    # only 2 bars -> EMA/ATR warmups never complete, so context is empty here.

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

        signal = alert.sent[0]
        text = signal.formatted_text
        assert text is not None
        assert text.startswith("\U0001f50d <b>AAPL</b>")
        assert "bullish engulfing" in text
        assert "Kontekst:" not in text
        assert "Savdo signali emas — chartni oching va o'zingiz qaror qiling." in text

        assert signal.reply_markup is not None
        keyboard = signal.reply_markup["inline_keyboard"]
        assert keyboard[0][0]["text"] == "\U0001f4c8 Chart"
        assert "AAPL" in keyboard[0][0]["url"]
        assert "callback_data" not in keyboard[0][0]  # chart button is a plain link
        assert keyboard[1][0]["callback_data"] == "j:T:AAPL:2024-01-02"
        assert keyboard[1][1]["callback_data"] == "j:S:AAPL:2024-01-02"

        # The pre-existing `reason` framing (asserted by
        # test_scanner_alert_on_change_and_state) must be untouched.
        assert "SCANNER: setup formed, go look — not a trade signal." in signal.reason
    finally:
        for p in (state_path, journal_path):
            if os.path.isfile(p):
                os.remove(p)

    print("[ok] scanner_alert_formatted_text")


def test_scanner_journal_failure_preserves_state() -> None:
    import os
    import shutil
    import tempfile

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

    state_path = _tmp_path(".json")
    # A directory in place of the journal file: opening it for append raises
    # OSError, simulating a journal write failure (e.g. disk full).
    bad_journal_dir = tempfile.mkdtemp()
    good_journal_path = _tmp_path(".csv")

    try:
        cfg = AppConfig(state_file=state_path)
        alert = _FakeAlert()
        scanner = Scanner(
            _FakeSource(df),
            alert,
            cfg,
            require_uptrend=False,
            journal_path=bad_journal_dir,
            state_path=state_path,
            drop_forming_bar=False,
        )

        raised = False
        try:
            scanner.process_symbol("AAPL")
        except OSError:
            raised = True
        assert raised
        # The journal write failed, so the bar must NOT be marked as alerted
        # -- otherwise the setup would be silently and permanently lost.
        assert scanner.state.get("AAPL") is None
        assert len(alert.sent) == 0

        # Point at a writable journal path and retry the same bar: it must
        # still fire, proving the failed attempt didn't consume the setup.
        scanner.journal_path = good_journal_path
        setup = scanner.process_symbol("AAPL")
        assert setup is not None
        assert scanner.state.get("AAPL") is not None
        assert len(alert.sent) == 1
        assert os.path.isfile(good_journal_path)
        with open(good_journal_path, encoding="utf-8") as f:
            content = f.read()
        assert "AAPL" in content
    finally:
        shutil.rmtree(bad_journal_dir, ignore_errors=True)
        for p in (state_path, good_journal_path):
            if os.path.isfile(p):
                os.remove(p)

    print("[ok] scanner_journal_failure_preserves_state")


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


def test_update_journal_decision() -> None:
    import csv
    import os

    from engine.scanner import update_journal_decision

    journal_path = _tmp_path(".csv")
    try:
        # no journal file yet -> nothing to update
        assert update_journal_decision(journal_path, "AAPL", "2026-08-18", "taken") is False

        with open(journal_path, "w", encoding="utf-8", newline="") as f:
            f.write(
                "scanned_at,bar_date,symbol,price,triggers,context,confluence,"
                "decision,outcome,notes\n"
                "2026-08-18T21:00:00+00:00,2026-08-18,AAPL,226.3,liquidity_sweep,"
                "uptrend,2,,,\n"
                "2026-08-18T21:00:00+00:00,2026-08-18,MSFT,410.0,bullish_pin,,1,,,\n"
            )

        assert update_journal_decision(journal_path, "AAPL", "2026-08-18", "taken") is True

        with open(journal_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["decision"] == "taken"
        assert rows[1]["symbol"] == "MSFT"
        assert rows[1]["decision"] == ""  # untouched

        # no row matches this symbol/bar_date -> False, file left as-is
        assert update_journal_decision(journal_path, "NVDA", "2026-08-18", "skipped") is False
    finally:
        if os.path.isfile(journal_path):
            os.remove(journal_path)

    print("[ok] update_journal_decision")


def test_format_setups() -> None:
    from scan_main import format_setups
    from signals.detectors import Setup

    assert format_setups([]) == "Skanerlandi, yangi setup yo'q."

    setups = [
        Setup(symbol="AAPL", triggers=["liquidity_sweep"], context=[], price=100.0, confluence=1),
        Setup(symbol="MSFT", triggers=["bullish_pin"], context=[], price=200.0, confluence=1),
    ]
    assert format_setups(setups) == "Skanerlandi: 2 ta setup topildi (AAPL, MSFT)."

    print("[ok] format_setups")


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


def main() -> int:
    tests = [
        test_atr,
        test_bullish_sweep,
        test_bullish_engulfing,
        test_bullish_pin,
        test_uptrend,
        test_near_round_number,
        test_format_setup_alert_text,
        test_format_setup_alert_text_no_context,
        test_format_setup_alert_text_emoji_and_no_separators,
        test_near_fvg,
        test_scanner_config_defaults,
        test_enricher_alone_not_actionable,
        test_scan_symbol_no_lookahead,
        test_scan_symbol_uptrend_gate,
        test_scanner_drop_forming_bar,
        test_scanner_alert_on_change_and_state,
        test_scanner_alert_formatted_text,
        test_scanner_journal_failure_preserves_state,
        test_scanner_corrupt_state_and_isolation,
        test_update_journal_decision,
        test_format_setups,
        test_scan_main_imports_and_builds,
    ]
    for t in tests:
        t()
    return 0


if __name__ == "__main__":
    sys.exit(main())
