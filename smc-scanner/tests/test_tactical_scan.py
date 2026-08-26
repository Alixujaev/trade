"""scripts/tactical_scan.py uchun testlar (Phase 5'ning tekshirilgan signal ssenariysi qayta ishlatiladi)."""

from __future__ import annotations

import pandas as pd
import pytest

import scripts.tactical_scan as scan_module
from scripts.tactical_scan import build_scan_row, run_scan

# Phase 3/5'da tekshirilgan: bearish BOS'lar, keyin bullish CHoCH idx=11'da (level=5).
_TREND_REVERSAL = [10, 12, 11, 14, 13, 16, 15, 18, 17, 20, 18, 15, 12]
_MIRRORED_BEARISH_TO_BULLISH = [22 - v for v in _TREND_REVERSAL]

# idx13: bullish displacement; idx14: FVG (top=15.6,bottom=10.0); idx16: retest -> signal.
_RETEST_ROWS = [
    {"open": 10, "high": 15.5, "low": 9.8, "close": 15},
    {"open": 16, "high": 17, "low": 15.6, "close": 16.5},
    {"open": 16.5, "high": 18, "low": 16, "close": 17.5},
    {"open": 17.5, "high": 18, "low": 14, "close": 16},
]


def _make_df(values: list[float], extra_rows: list[dict] | None = None) -> pd.DataFrame:
    extra_rows = extra_rows if extra_rows is not None else []
    rows = [{"open": v, "high": v, "low": v, "close": v} for v in values] + extra_rows
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[["open", "high", "low", "close", "volume"]]


def test_build_scan_row_identifies_active_setup_fixed_mode() -> None:
    """Signal eng oxirgi barda trigger bo'lsa (bars_ago=0), faol deb belgilanishi kerak."""
    df = _make_df(_MIRRORED_BEARISH_TO_BULLISH, extra_rows=_RETEST_ROWS)

    row = build_scan_row("TST", df, lookback=1, mult=1.0, exit_mode="fixed")

    assert row["ERROR"] is None
    assert row["SETUP_REASON"] == "FVG"
    assert row["HAS_ACTIVE_SETUP"] is True
    assert row["SETUP_BARS_AGO"] == 0
    assert row["SETUP_ENTRY"] == pytest.approx(15.6)
    assert row["STRUCTURE_STATE"] == "BULLISH"
    # R:R = (target-entry)/(entry-stop), barchasi generate_signals'dan olingan qiymatlar
    expected_rr = round((row["SETUP_TARGET"] - row["SETUP_ENTRY"]) / (row["SETUP_ENTRY"] - row["SETUP_STOP"]), 2)
    assert row["SETUP_RR"] == pytest.approx(expected_rr)


def test_build_scan_row_trailing_mode_reports_na_rr() -> None:
    df = _make_df(_MIRRORED_BEARISH_TO_BULLISH, extra_rows=_RETEST_ROWS)

    row = build_scan_row("TST", df, lookback=1, mult=1.0, exit_mode="trailing")

    assert row["SETUP_TARGET"] is None
    assert row["SETUP_RR"] == "N/A (trailing — maqsad yo'q)"
    assert row["SETUP_STOP"] == pytest.approx(9.74, abs=0.01)  # boshlang'ich stop hali ko'rsatiladi


def test_build_scan_row_no_signal_at_all() -> None:
    """Zona/displacement yo'q holatda (faqat flat bearish->bullish struktura) signal yo'q — crash yo'q."""
    df = _make_df(_MIRRORED_BEARISH_TO_BULLISH)

    row = build_scan_row("TST", df, lookback=1, mult=1.0, exit_mode="fixed")

    assert row["ERROR"] is None
    assert row["SETUP_REASON"] is None
    assert row["HAS_ACTIVE_SETUP"] is False
    assert row["SETUP_BARS_AGO"] is None


def test_build_scan_row_old_setup_marked_inactive() -> None:
    """Setup 10 bardan ko'proq oldin trigger bo'lsa, HAS_ACTIVE_SETUP=False bo'lishi kerak,
    lekin baribir tarixiy kontekst sifatida qaytarilishi kerak (yo'qolib ketmasligi kerak)."""
    stale_tail = [{"open": 16, "high": 16, "low": 15.9, "close": 16}] * 15  # 15 ta qo'shimcha flat bar
    df = _make_df(_MIRRORED_BEARISH_TO_BULLISH, extra_rows=_RETEST_ROWS + stale_tail)

    row = build_scan_row("TST", df, lookback=1, mult=1.0, exit_mode="fixed")

    assert row["SETUP_REASON"] == "FVG"  # setup hali qaytariladi (tarixiy kontekst)
    assert row["SETUP_BARS_AGO"] > 10
    assert row["HAS_ACTIVE_SETUP"] is False


class _FakeProvider:
    def __init__(self, df: pd.DataFrame | None = None, error: Exception | None = None) -> None:
        self._df = df
        self._error = error

    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        if self._error is not None:
            raise self._error
        return self._df


def test_run_scan_continues_after_one_symbol_fails(monkeypatch) -> None:
    good_df = _make_df(_MIRRORED_BEARISH_TO_BULLISH, extra_rows=_RETEST_ROWS)

    def fake_get_provider(name: str | None) -> _FakeProvider:
        return _FakeProvider(df=good_df)

    call_count = {"n": 0}

    def fake_get_provider_with_failure(name: str | None) -> _FakeProvider:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FakeProvider(error=RuntimeError("tarmoq xatosi"))
        return _FakeProvider(df=good_df)

    monkeypatch.setattr(scan_module, "get_provider", fake_get_provider_with_failure)

    rows = run_scan(["BAD", "GOOD"], "1d", None, lookback=1, mult=1.0)

    assert len(rows) == 2
    assert "ERROR" in rows[0] and rows[0]["ERROR"] is not None
    assert rows[1].get("ERROR") is None
    assert rows[1]["SETUP_REASON"] == "FVG"


def test_run_scan_handles_empty_data(monkeypatch) -> None:
    monkeypatch.setattr(scan_module, "get_provider", lambda name: _FakeProvider(df=pd.DataFrame()))

    rows = run_scan(["EMPTY"], "1d", None)

    assert len(rows) == 1
    assert rows[0]["ERROR"] is not None
