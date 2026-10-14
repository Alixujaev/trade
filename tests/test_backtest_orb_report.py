"""scripts/backtest_orb.py: report provenance yorlig'i (network yo'q, backtest yo'q)."""

from __future__ import annotations

from config.settings import CACHE_DIR
import scripts.backtest_orb as bo

YF_CACHE = "yfinance (documented provenance; not recorded per file)"


def _metrics(data_source: str | None, sessions: int = 60) -> dict:
    inputs = {"cache_dir": "data/cache", "network": "blocked", "earnings_calendar": "e.csv"}
    if data_source is not None:
        inputs["data_source"] = data_source
    return {
        "range": {"start": "2026-07-02", "end": "2026-09-25", "sessions": sessions},
        "universe": {"count": 1, "symbols_with_trades": []},
        "trades": 0, "win_rate": bo.NA, "net_return": bo.NA, "cagr": bo.NA, "max_drawdown": bo.NA,
        "sharpe": bo.NA, "sortino": bo.NA, "exits": {}, "skips": {}, "earnings_skipped_symbol_sessions": 0,
        "costs": {"commission_total": 0.0, "slippage_total": 0.0, "note": ""},
        "benchmarks": {"equal_weight_buy_and_hold": {}, "capital_constrained_buy_and_hold": {"reason": "n/a"}},
        "inputs": inputs, "checks": [],
    }


def test_repo_cache_is_labelled_documented_yfinance():
    assert bo.data_source_label(str(CACHE_DIR), None) == YF_CACHE


def test_other_cache_dir_is_unknown_not_yfinance(tmp_path):
    label = bo.data_source_label(str(tmp_path), None)
    assert label.startswith("UNKNOWN/UNVERIFIED")
    assert "yfinance" not in label


def test_provider_labels_follow_the_provider():
    assert "yfinance" in bo.data_source_label(None, "yfinance")
    alpaca = bo.data_source_label(None, "alpaca")
    assert "IEX" in alpaca and "yfinance" not in alpaca
    assert bo.data_source_label(None, "other").startswith("UNKNOWN/UNVERIFIED")


def test_report_line_uses_recorded_source_and_session_count():
    report = bo.render_report(_metrics(YF_CACHE, sessions=42))
    assert f"- Smoke test on 42 sessions of {YF_CACHE} 5m data" in report
    assert "IEX" not in report


def test_report_without_recorded_source_says_unknown():
    report = bo.render_report(_metrics(None))
    assert "sessions of UNKNOWN/UNVERIFIED 5m data" in report
