"""signals/scanner.py uchun testlar (sintetik OHLCV, real pipeline, tarmoqsiz)."""

from __future__ import annotations

import pandas as pd
import pytest

from signals.payload import SignalContext, SignalMode, SignalPayload, HistoricalContext
from signals.scanner import _entry_zone, scan_symbol, scan_universe
from smc.types import StructureState, TradeSetup
from smc.zones import compute_atr

_COLUMNS = ["open", "high", "low", "close", "volume"]


def _make_df(rows: list[dict], *, start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    if "volume" not in df.columns:
        df["volume"] = 1000
    else:
        df["volume"] = df["volume"].fillna(1000)
    return df[_COLUMNS]


def _breakout_rows() -> list[dict]:
    """lookback=1, volume_ma_period=20 bilan haqiqiy breakout+retest signal beradigan seriya
    (tests/test_backtest_portfolio.py::_breakout_rows bilan bir xil ssenariy). idx20: breakout
    (volume 3000, flat 1000 baseline'ga nisbatan aniq spike). idx22: tasdiq/entry."""
    rows = [
        {"open": 96, "high": 98, "low": 95, "close": 97},
        {"open": 97, "high": 100, "low": 96, "close": 98},   # 1 swing high
        {"open": 98, "high": 97, "low": 94, "close": 95},
        {"open": 95, "high": 100, "low": 94, "close": 96},   # 3 swing high
        {"open": 96, "high": 97, "low": 93, "close": 94},
        {"open": 94, "high": 100, "low": 93, "close": 95},   # 5 swing high
        {"open": 95, "high": 96, "low": 92, "close": 93},    # 6 zona confirmed
    ]
    rows += [{"open": 95, "high": 98, "low": 93, "close": 96} for _ in range(13)]  # 7..19 baza
    rows += [
        {"open": 96, "high": 105, "low": 95, "close": 104, "volume": 3000},  # 20 breakout
        {"open": 104, "high": 106, "low": 100, "close": 101},                # 21 retest
        {"open": 101, "high": 108, "low": 100.5, "close": 107},              # 22 tasdiq/entry
        {"open": 107, "high": 115, "low": 106, "close": 113},                # 23
        {"open": 113, "high": 125, "low": 112, "close": 122},                # 24
        {"open": 122, "high": 135, "low": 120, "close": 133},                # 25 target ~132 tegadi
        {"open": 133, "high": 138, "low": 130, "close": 135},                # 26
        {"open": 135, "high": 140, "low": 132, "close": 138},                # 27
        {"open": 138, "high": 142, "low": 135, "close": 140},                # 28
        {"open": 140, "high": 145, "low": 138, "close": 143},                # 29
    ]
    return rows


_SCAN_KW = dict(lookback=1, min_rr=1.5, require_trend=False)


class _FakeProvider:
    def __init__(self, dfs: dict[str, pd.DataFrame | Exception]) -> None:
        self._dfs = dfs

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        result = self._dfs[symbol]
        if isinstance(result, Exception):
            raise result
        return result


# ======================================================================
# scan_symbol -- real kontekst bilan to'ldirish
# ======================================================================


def test_scan_symbol_fills_real_context() -> None:
    df = _make_df(_breakout_rows())
    payloads = scan_symbol(df, "AAPL", **_SCAN_KW)

    assert len(payloads) == 1
    payload = payloads[0]
    assert isinstance(payload, SignalPayload)
    assert payload.symbol == "AAPL"

    # entry_zone ATR bilan kengaytirilgan -- degenerativ (x, x) EMAS.
    low, high = payload.entry_zone
    assert low < high

    # trend/structure real hisoblangan qiymatlar (bo'sh/placeholder emas).
    assert payload.context.trend in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert payload.context.structure  # bo'sh string emas ("-" yoki haqiqiy BOS/CHOCH)

    # Breakout bari volume=3000, flat 1000 baseline'ga nisbatan aniq spike -> tasdiqlangan.
    assert payload.context.volume_confirmed is True

    assert payload.historical_context.expectancy_r != 0.0 or payload.historical_context.win_rate_pct != 0.0
    assert payload.data_freshness == df.index[-1].date()


def test_scan_respects_min_score() -> None:
    df = _make_df(_breakout_rows())
    baseline = scan_symbol(df, "AAPL", **_SCAN_KW)
    assert len(baseline) == 1
    score = baseline[0].score

    above = scan_symbol(df, "AAPL", min_score=score + 1.0, **_SCAN_KW)
    assert above == []

    below = scan_symbol(df, "AAPL", min_score=score - 1.0, **_SCAN_KW)
    assert len(below) == 1


# ======================================================================
# recency filtri -- live skaner faqat SO'NGGI setuplarni ko'rsatadi
# ======================================================================


def test_scan_symbol_filters_stale_setup_beyond_recency_window() -> None:
    """_breakout_rows()dagi setup (entry_index_pos=22) 20 ta qo'shimcha flat bar
    bilan endi oxirgi bardan 27 bar oldin -- default SIGNAL_RECENCY_BARS (10) bilan
    "eskirgan" hisoblanadi va chiqarib tashlanadi."""
    rows = _breakout_rows() + [{"open": 143, "high": 144, "low": 142, "close": 143} for _ in range(20)]
    df = _make_df(rows)

    payloads = scan_symbol(df, "AAPL", **_SCAN_KW)

    assert payloads == []


def test_scan_symbol_recency_bars_none_disables_filter() -> None:
    """recency_bars=None -- filtr o'chirilgan, eski setup ham qaytadi (test/tadqiqot
    uchun escape hatch)."""
    rows = _breakout_rows() + [{"open": 143, "high": 144, "low": 142, "close": 143} for _ in range(20)]
    df = _make_df(rows)

    payloads = scan_symbol(df, "AAPL", recency_bars=None, **_SCAN_KW)

    assert len(payloads) == 1


def test_scan_symbol_recency_boundary_respects_custom_value() -> None:
    """Asosiy _breakout_rows() df'ida setup oxirgi bardan 7 bar oldin -- default
    (10) bilan "yangi" (test_scan_symbol_fills_real_context'da tasdiqlangan), lekin
    recency_bars=5 (7>5) bilan "eskirgan" -- custom qiymat to'g'ri qo'llanadi."""
    df = _make_df(_breakout_rows())

    payloads = scan_symbol(df, "AAPL", recency_bars=5, **_SCAN_KW)

    assert payloads == []


def test_scan_symbol_no_lookahead() -> None:
    df_full = _make_df(_breakout_rows())
    # idx22 (entry) dan keyin bir nechta bar bilan kesamiz -- struktura/ATR/hajm konteksti
    # kelajak barlardan mustaqil bo'lishi kerak.
    df_trunc = df_full.iloc[:25]

    full = scan_symbol(df_full, "AAPL", **_SCAN_KW)
    trunc = scan_symbol(df_trunc, "AAPL", **_SCAN_KW)

    assert len(full) == 1 and len(trunc) == 1
    f, t = full[0], trunc[0]
    assert f.entry_zone == pytest.approx(t.entry_zone)
    assert f.context.trend == t.context.trend
    assert f.context.structure == t.context.structure
    assert f.context.volume_confirmed == t.context.volume_confirmed
    assert f.invalidation == pytest.approx(t.invalidation)


# ======================================================================
# _entry_zone -- ATR asosida
# ======================================================================


def test_entry_zone_from_atr() -> None:
    # Qo'lda qurilgan: har bar TR=2 (H-L=2), atr_period=3 -> ATR[j>=2] = 2.0 doimiy.
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 100},   # idx0
        {"open": 100, "high": 101, "low": 99, "close": 100},   # idx1
        {"open": 100, "high": 101, "low": 99, "close": 100},   # idx2 -- ATR endi valid (2.0)
        {"open": 100, "high": 101, "low": 99, "close": 100},   # idx3 -- entry shu yerda
    ]
    df = _make_df(rows)
    atr = compute_atr(df, 3)
    setup = TradeSetup(
        entry_ts=df.index[3], entry_price=100.0, stop_price=90.0, target_price=120.0,
        direction=StructureState.BULLISH, entry_index_pos=3, reason="BREAKOUT_RETEST@x",
    )

    low, high = _entry_zone(setup, atr, mult=0.25)
    assert low == pytest.approx(100.0 - 0.25 * 2.0)
    assert high == pytest.approx(100.0 + 0.25 * 2.0)


def test_entry_zone_from_atr_warmup_nan_is_degenerate() -> None:
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100} for _ in range(3)]
    df = _make_df(rows)
    atr = compute_atr(df, 14)  # 3 bar, period=14 -> hamma joyda NaN
    setup = TradeSetup(
        entry_ts=df.index[0], entry_price=100.0, stop_price=90.0, target_price=120.0,
        direction=StructureState.BULLISH, entry_index_pos=0, reason="BREAKOUT_RETEST@x",
    )

    low, high = _entry_zone(setup, atr, mult=0.25)
    assert low == pytest.approx(100.0)
    assert high == pytest.approx(100.0)


# ======================================================================
# scan_universe -- xato/yetarsiz data skip, sort, "setup yo'q" != skip
# ======================================================================


def test_scan_universe_skips_bad_symbol() -> None:
    good_df = _make_df(_breakout_rows())
    provider = _FakeProvider({
        "GOOD": good_df,
        "ERRORS_OUT": RuntimeError("provider yiqildi"),
        "TOO_SHORT": _make_df([{"open": 1, "high": 1, "low": 1, "close": 1}] * 2),
    })

    results, skipped = scan_universe(
        ["GOOD", "ERRORS_OUT", "TOO_SHORT"], provider, min_score=None, **_SCAN_KW,
    )

    assert "GOOD" in results and len(results["GOOD"]) == 1
    skipped_symbols = {row["symbol"] for row in skipped}
    assert skipped_symbols == {"ERRORS_OUT", "TOO_SHORT"}
    for row in skipped:
        assert row["reason"]  # bo'sh emas


def test_scan_universe_no_setup_is_not_a_skip() -> None:
    # Yetarli, valid, lekin butunlay tekis (setup'siz) seriya.
    flat_rows = [{"open": 100, "high": 100.5, "low": 99.5, "close": 100} for _ in range(40)]
    provider = _FakeProvider({"FLAT": _make_df(flat_rows)})

    results, skipped = scan_universe(["FLAT"], provider, min_score=None, **_SCAN_KW)

    assert results == {}
    assert skipped == []


def test_scan_universe_sorts_results_by_score_descending(monkeypatch) -> None:
    import signals.scanner as scanner_module

    ts = pd.Timestamp("2024-01-01", tz="UTC")

    def _fake_payload(score: float) -> SignalPayload:
        return SignalPayload(
            symbol="MULTI", mode=SignalMode.SWING, setup_type="breakout_retest",
            score=score, score_label="SETUP", direction=StructureState.BULLISH,
            entry_zone=(99.0, 101.0), invalidation=90.0, potential_target=120.0,
            risk_reward=2.0, context=SignalContext(trend="BULLISH", structure="BOS", volume_confirmed=True),
            historical_context=HistoricalContext(expectancy_r=0.5, win_rate_pct=50.0, period_label="2020-2026"),
            generated_at=ts.to_pydatetime(), timeframe="1d", data_freshness=ts.date(),
        )

    def _fake_scan_symbol(df, symbol, **kwargs):
        return [_fake_payload(30.0), _fake_payload(90.0), _fake_payload(60.0)]

    monkeypatch.setattr(scanner_module, "scan_symbol", _fake_scan_symbol)
    provider = _FakeProvider({"MULTI": _make_df([{"open": 1, "high": 1, "low": 1, "close": 1}] * 40)})

    results, skipped = scan_universe(["MULTI"], provider, min_score=None, **_SCAN_KW)

    assert skipped == []
    assert [p.score for p in results["MULTI"]] == [90.0, 60.0, 30.0]
