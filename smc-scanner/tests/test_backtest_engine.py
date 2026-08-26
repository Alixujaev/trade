"""backtest/engine.py uchun testlar (qo'lda hisoblangan sintetik df + TradeSetup, real tarmoqsiz)."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engine import run_backtest
from config.settings import ATR_RISK_MULT
from smc.types import StructureState, TradeSetup


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Har bir bar uchun aniq open/high/low/close berilgan DataFrame yasaydi."""
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, index=index)
    df["volume"] = 1000
    return df[["open", "high", "low", "close", "volume"]]


def _setup(entry_index_pos: int, entry: float, stop: float, target: float, ts: pd.Timestamp) -> TradeSetup:
    return TradeSetup(
        entry_ts=ts,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        direction=StructureState.BULLISH,
        entry_index_pos=entry_index_pos,
        reason="FVG",
    )


def test_single_trade_clean_target_hit_fixed_pct() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry bar
        {"open": 100, "high": 105, "low": 95, "close": 102},  # idx1 no hit
        {"open": 102, "high": 125, "low": 98, "close": 118},  # idx2 target hit (125>=120)
    ]
    df = _make_df(rows)
    signal = _setup(0, entry=100.0, stop=90.0, target=120.0, ts=df.index[0])

    result = run_backtest(df, [signal], initial_capital=10_000, risk_model="fixed_pct", risk_pct=0.01)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.shares == pytest.approx(10.0)  # risk_amount=100, per_share_risk=10 -> 10 shares
    assert trade.exit_reason == "target"
    assert trade.exit_price == pytest.approx(120.0)
    assert trade.exit_index_pos == 2
    assert trade.r_multiple == pytest.approx(2.0)
    assert trade.pnl == pytest.approx(200.0)
    assert trade.mae_r == pytest.approx(0.5)  # min_low=95 -> (100-95)/10
    assert result.final_capital == pytest.approx(10_200.0)
    assert result.metrics["total_return_pct"] == pytest.approx(2.0)


def test_same_bar_stop_and_target_stop_wins() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 125, "low": 85, "close": 90},  # idx1 ikkalasi ham teksa
    ]
    df = _make_df(rows)
    signal = _setup(0, entry=100.0, stop=90.0, target=120.0, ts=df.index[0])

    result = run_backtest(df, [signal], risk_model="fixed_pct", risk_pct=0.01)

    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(90.0)
    assert trade.r_multiple == pytest.approx(-1.0)
    assert trade.mae_r == pytest.approx(1.5)  # min_low=85 -> (100-85)/10


def test_atr_risk_model_gives_different_share_count_than_fixed_pct() -> None:
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 100},  # idx0
        {"open": 100, "high": 101, "low": 99, "close": 100},  # idx1
        {"open": 100, "high": 101, "low": 99, "close": 100},  # idx2
        {"open": 100, "high": 101, "low": 99, "close": 100},  # idx3 entry bar (ATR[3]=2.0 bilan atr_period=3)
        {"open": 105, "high": 115, "low": 104, "close": 110},  # idx4 target hit
    ]
    df = _make_df(rows)
    signal = _setup(3, entry=100.0, stop=95.0, target=110.0, ts=df.index[3])

    fixed_result = run_backtest(df, [signal], risk_model="fixed_pct", risk_pct=0.01, atr_period=3)
    atr_result = run_backtest(df, [signal], risk_model="atr", risk_pct=0.01, atr_period=3)

    # fixed_pct: risk_amount=100, per_share_risk=entry-stop=5 -> 20 shares
    assert fixed_result.trades[0].shares == pytest.approx(20.0)
    # atr: risk_amount=100, per_share_risk=ATR_RISK_MULT*ATR[3]=ATR_RISK_MULT*2.0
    expected_atr_shares = 100.0 / (ATR_RISK_MULT * 2.0)
    assert atr_result.trades[0].shares == pytest.approx(expected_atr_shares)
    assert atr_result.trades[0].shares != pytest.approx(fixed_result.trades[0].shares)
    # R-multiple ikkalasida ham BIR XIL bo'lishi kerak — faqat narxdan hisoblanadi
    assert fixed_result.trades[0].r_multiple == pytest.approx(atr_result.trades[0].r_multiple)


def test_capital_constraint_shrinks_position() -> None:
    rows = [
        {"open": 1000, "high": 1000, "low": 1000, "close": 1000},  # idx0 entry
        {"open": 1000, "high": 1010, "low": 995, "close": 1005},  # idx1 target hit
    ]
    df = _make_df(rows)
    signal = _setup(0, entry=1000.0, stop=990.0, target=1005.0, ts=df.index[0])

    # risk_pct=0.5, capital=100 -> risk_amount=50, shares=50/10=5, lekin 5*1000=5000 > 100
    result = run_backtest(df, [signal], initial_capital=100.0, risk_model="fixed_pct", risk_pct=0.5)

    assert result.trades[0].shares == pytest.approx(0.1)  # capital/entry = 100/1000


def test_one_position_at_a_time() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 S1 entry
        {"open": 100, "high": 105, "low": 95, "close": 102},  # idx1 S2 (skipped) entry / S1 no hit
        {"open": 102, "high": 112, "low": 98, "close": 110},  # idx2 S1 target hit
        {"open": 103, "high": 103, "low": 103, "close": 103},  # idx3 S3 entry
        {"open": 103, "high": 115, "low": 100, "close": 113},  # idx4 S3 target hit
    ]
    df = _make_df(rows)
    s1 = _setup(0, entry=100.0, stop=90.0, target=110.0, ts=df.index[0])
    s2 = _setup(1, entry=101.0, stop=91.0, target=111.0, ts=df.index[1])  # S1 ochiq — skip bo'lishi kerak
    s3 = _setup(3, entry=103.0, stop=93.0, target=113.0, ts=df.index[3])  # S1 yopilgach — olinishi kerak

    result = run_backtest(df, [s1, s2, s3], risk_model="fixed_pct", risk_pct=0.01)

    assert len(result.trades) == 2
    assert result.trades[0].entry_price == pytest.approx(100.0)
    assert result.trades[1].entry_price == pytest.approx(103.0)


def test_capital_exhaustion_halts_further_entries() -> None:
    # stop_price=0 va risk_pct=1.0 ataylab tanlangan: shares*entry aynan capital'ga
    # teng bo'ladi (kapital cheklovi ishga tushmaydi, "> capital" emas "== capital"),
    # shuning uchun stop-out butun kapitalni ANIQ nolgacha yutqizadi — kapital
    # cheklovi mexanizmi (shrink) bilan aralashmasdan "capital<=0" holatini sinash uchun.
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 S1 entry
        {"open": 100, "high": 50, "low": 0, "close": 10},  # idx1 S1 stop hit -> capital=0
        {"open": 90, "high": 90, "low": 90, "close": 90},  # idx2 S2 entry (olinmasligi kerak)
        {"open": 90, "high": 150, "low": 89, "close": 140},  # idx3 S2 target bo'lardi, lekin capital yo'q
    ]
    df = _make_df(rows)
    s1 = _setup(0, entry=100.0, stop=0.0, target=200.0, ts=df.index[0])  # target yetib bo'lmaydigan
    s2 = _setup(2, entry=90.0, stop=80.0, target=100.0, ts=df.index[2])

    result = run_backtest(df, [s1, s2], initial_capital=10_000.0, risk_model="fixed_pct", risk_pct=1.0)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop"
    assert result.final_capital == pytest.approx(0.0)


def test_end_of_data_closes_open_position_at_last_close() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 105, "low": 95, "close": 102},  # idx1 hit yo'q
        {"open": 102, "high": 108, "low": 96, "close": 106},  # idx2 (oxirgi bar) hit yo'q
    ]
    df = _make_df(rows)
    signal = _setup(0, entry=100.0, stop=50.0, target=200.0, ts=df.index[0])  # ikkalasi ham yetib bo'lmaydi

    result = run_backtest(df, [signal], risk_model="fixed_pct", risk_pct=0.01)

    trade = result.trades[0]
    assert trade.exit_reason == "end_of_data"
    assert trade.exit_index_pos == 2
    assert trade.exit_price == pytest.approx(106.0)


def test_mae_r_tracks_worst_low_before_target() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # idx0 entry
        {"open": 100, "high": 105, "low": 85, "close": 95},  # idx1 chuqur pasayish (stop=80'ga yetmaydi)
        {"open": 95, "high": 125, "low": 90, "close": 120},  # idx2 target hit
    ]
    df = _make_df(rows)
    signal = _setup(0, entry=100.0, stop=80.0, target=120.0, ts=df.index[0])

    result = run_backtest(df, [signal], risk_model="fixed_pct", risk_pct=0.01)

    assert result.trades[0].mae_r == pytest.approx(0.75)  # min_low=85 -> (100-85)/20


def test_empty_signals_returns_empty_trades_no_crash() -> None:
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100}] * 3
    df = _make_df(rows)

    result = run_backtest(df, [])

    assert result.trades == []
    assert result.final_capital == result.initial_capital
    assert result.metrics["num_trades"] == 0
    assert result.metrics["win_rate"] == 0.0
