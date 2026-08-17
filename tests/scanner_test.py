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


def main() -> int:
    tests = [
        test_atr,
        test_bullish_sweep,
        test_bullish_engulfing,
        test_bullish_pin,
        test_uptrend,
        test_near_round_number,
        test_near_fvg,
        test_scanner_config_defaults,
        test_enricher_alone_not_actionable,
        test_scan_symbol_no_lookahead,
        test_scan_symbol_uptrend_gate,
    ]
    for t in tests:
        t()
    return 0


if __name__ == "__main__":
    sys.exit(main())
