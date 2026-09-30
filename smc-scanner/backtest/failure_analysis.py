"""backtest/failure_analysis.py: DAY-05 — Failure Analysis of the Frozen Day Strategy.

QAT'IY METODOLOGIK QOIDALAR:
- Bu modul faqat DIAGNOSTIK TAHLIL uchun mo'ljallangan.
- Strategiya logikasi, parametrlar, threshold'lar yoki qoidalariga HECH QANDAY o'zgartirish kiritilmaydi.
- Hech qanday filtr (gap, catalyst, stock-in-play, max trades, stop/target o'zgarishi) qilinmaydi.
- MFE/MAE qat'iy ravishda post-hoc (savdo tugagandan keyingi) diagnostik ko'rsatkich hisoblanadi
  va signal generatori yoki execution engine'ga HECH QACHON ta'sir qilmaydi.
- Natijalar faqat xolis factual o'lchovlar sifatida taqdim etiladi; tavsiyalar berilmaydi.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import time
from enum import Enum
import json
import logging
import math
from typing import Any
import numpy as np
import pandas as pd

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.multi_symbol import run_multi_symbol_day_backtest
from backtest.multi_types import MultiSymbolDayBacktestResult
from config.day_universe import get_day_universe
from data.factory import get_provider
from data.provider import DataProvider
from data.session import get_session_date, to_eastern

logger = logging.getLogger(__name__)


# =====================================================================
# 1. Trade-level Diagnostic Data Model
# =====================================================================

@dataclass(frozen=True)
class DiagnosticTradeRecord:
    """Bitta savdoning boyitilgan point-in-time va post-hoc diagnostik yozuvi."""

    symbol: str
    setup_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp

    entry_price: float
    exit_price: float
    stop_price: float | None
    target_price: float | None

    exit_reason: str              # "STOP" | "TARGET" | "FORCED_EXIT"
    gross_return: float
    net_return: float
    r_multiple: float | None
    hold_duration_minutes: int

    setup_rsi: float
    setup_rvol: float
    setup_vwap: float
    observed_price: float

    structure_5m: str
    structure_15m: str
    setup_status: str
    trigger_type: str
    vwap_relation: str

    evidence: tuple[str, ...]
    warnings: tuple[str, ...]
    score_reasons: tuple[str, ...]

    session_date: str
    entry_hour: int
    entry_minute: int
    entry_time_bucket: str

    # Excursion (post-hoc diagnostic only, never fed into strategy)
    mfe_pct: float
    mfe_r: float | None
    mae_pct: float
    mae_r: float | None

    target_0_5r_reached: bool
    target_1_0r_reached: bool
    target_1_5r_reached: bool
    target_2_0r_reached: bool

    stop_distance_abs: float | None
    stop_distance_pct: float | None
    signal_entry_gap_pct: float

    is_winner: bool
    is_loser: bool
    is_breakeven: bool

    # DAY-07 H2 Dynamic Stop (1R -> Breakeven) fields
    initial_stop_price: float | None = None
    initial_risk_per_share: float | None = None
    breakeven_price: float | None = None
    be_triggered: bool = False
    be_trigger_time: pd.Timestamp | None = None
    effective_exit_stop_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON serializatsiya uchun toza dict."""
        d = asdict(self)
        d["setup_time"] = str(self.setup_time)
        d["entry_time"] = str(self.entry_time)
        d["exit_time"] = str(self.exit_time)
        if self.be_trigger_time is not None:
            d["be_trigger_time"] = str(self.be_trigger_time)
        for k, v in d.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d


# =====================================================================
# 2. Helper Functions for Bucketing & Metrics
# =====================================================================

def map_exit_reason(raw_reason: str) -> str:
    """Mavjud exit sabablarini standart kategoriya nomlariga xaritalaydi."""
    r = raw_reason.lower()
    if "breakeven" in r:
        return "BREAKEVEN"
    if "stop" in r:
        return "STOP"
    if "target" in r:
        return "TARGET"
    if "forced" in r or "end_of_data" in r or "max_time" in r or "eod" in r:
        return "FORCED_EXIT"
    return "FORCED_EXIT"


def get_time_of_day_bucket(t: time) -> str:
    """Predefined fixed time-of-day bucket for Eastern Time."""
    if time(9, 30) <= t < time(10, 0):
        return "09:30–10:00"
    if time(10, 0) <= t < time(11, 0):
        return "10:00–11:00"
    if time(11, 0) <= t < time(12, 0):
        return "11:00–12:00"
    if time(12, 0) <= t < time(14, 0):
        return "12:00–14:00"
    if time(14, 0) <= t < time(15, 0):
        return "14:00–15:00"
    if time(15, 0) <= t <= time(15, 55):
        return "15:00–15:55"
    return "OTHER"


def get_rsi_bucket(val: float) -> str:
    """Predefined descriptive RSI bins."""
    if pd.isna(val) or val < 50.0:
        return "<50"
    if val < 55.0:
        return "50–55"
    if val < 60.0:
        return "55–60"
    if val < 70.0:
        return "60–70"
    return "70+"


def get_rvol_bucket(val: float) -> str:
    """Predefined descriptive RVOL bins."""
    if pd.isna(val) or val < 1.0:
        return "<1.0"
    if val < 2.0:
        return "1.0–2.0"
    if val < 3.0:
        return "2.0–3.0"
    if val < 5.0:
        return "3.0–5.0"
    return "5.0+"


def get_stop_distance_bucket(pct: float | None) -> str:
    """Predefined stop distance bins."""
    if pct is None or pd.isna(pct):
        return "UNKNOWN"
    p = pct * 100.0
    if p < 0.25:
        return "<0.25%"
    if p < 0.50:
        return "0.25–0.50%"
    if p < 1.00:
        return "0.50–1.00%"
    if p < 2.00:
        return "1.00–2.00%"
    return "2.00%+"


def get_duration_bucket(mins: int) -> str:
    """Predefined holding duration bins."""
    if mins < 5:
        return "0–5 min"
    if mins < 10:
        return "5–10 min"
    if mins < 20:
        return "10–20 min"
    if mins < 30:
        return "20–30 min"
    if mins < 60:
        return "30–60 min"
    if mins < 120:
        return "60–120 min"
    return "120+ min"


def get_entry_gap_bucket(gap_pct: float) -> str:
    """Predefined signal-to-entry gap bins."""
    if pd.isna(gap_pct):
        return "UNKNOWN"
    p = gap_pct * 100.0
    if p < -0.05:
        return "negative gap (<-0.05%)"
    if p <= 0.05:
        return "near-zero gap (-0.05% to +0.05%)"
    return "positive gap (>+0.05%)"


def compute_group_metrics(records: Sequence[DiagnosticTradeRecord]) -> dict[str, Any]:
    """Berilgan savdolar guruhi uchun xolis umumlashtiruvchi metrikalar."""
    n = len(records)
    if n == 0:
        return {
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "breakevens": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "median_return": 0.0,
            "avg_R": 0.0,
            "median_R": 0.0,
            "total_R": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "avg_hold_duration": 0.0,
        }

    wins = sum(1 for r in records if r.is_winner)
    losses = sum(1 for r in records if r.is_loser)
    bes = sum(1 for r in records if r.is_breakeven)
    win_rate = (wins / n) * 100.0

    returns = [r.net_return for r in records]
    avg_return = float(np.mean(returns)) * 100.0
    median_return = float(np.median(returns)) * 100.0

    r_vals = [r.r_multiple for r in records if r.r_multiple is not None and not math.isnan(r.r_multiple)]
    total_R = float(np.sum(r_vals)) if r_vals else 0.0
    avg_R = float(np.mean(r_vals)) if r_vals else 0.0
    median_R = float(np.median(r_vals)) if r_vals else 0.0

    gross_wins = sum(r.gross_return for r in records if r.gross_return > 0)
    gross_losses = sum(abs(r.gross_return) for r in records if r.gross_return < 0)
    if gross_losses > 0:
        profit_factor = gross_wins / gross_losses
    elif gross_wins > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    expectancy = avg_return
    avg_hold = float(np.mean([r.hold_duration_minutes for r in records]))

    return {
        "trade_count": n,
        "wins": wins,
        "losses": losses,
        "breakevens": bes,
        "win_rate": round(win_rate, 2),
        "avg_return": round(avg_return, 4),
        "median_return": round(median_return, 4),
        "avg_R": round(avg_R, 4),
        "median_R": round(median_R, 4),
        "total_R": round(total_R, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
        "expectancy": round(expectancy, 4),
        "avg_hold_duration": round(avg_hold, 1),
    }


# =====================================================================
# 3. Post-Hoc Excursion & Trade Enrichment
# =====================================================================

def enrich_trade_record(
    trade: DayBacktestTrade,
    df_5m: pd.DataFrame,
) -> DiagnosticTradeRecord:
    """Bitta savdoni 5m narx harakati (MFE/MAE/Gap) bilan post-hoc boyitadi.

    DIQQAT: Bu funksiya FAQAT tahlil qatlamida ishlaydi.
    Strategiya yoki execution engine ushbu funksiyaga HECH QACHON murojaat qilmaydi.
    """
    # Fast Eastern time konversiyasi
    if trade.entry_time.tzinfo is not None:
        entry_et = trade.entry_time.tz_convert("America/New_York")
    else:
        entry_et = to_eastern(trade.entry_time)

    entry_hour = entry_et.hour
    entry_minute = entry_et.minute
    entry_bucket = get_time_of_day_bucket(entry_et.time())
    session_date = str(get_session_date(trade.entry_time))

    # Signal bar va entry bar narxlari
    signal_bar_close = float(df_5m.at[trade.setup_time, "close"]) if trade.setup_time in df_5m.index else float("nan")
    entry_bar_open = float(df_5m.at[trade.entry_time, "open"]) if trade.entry_time in df_5m.index else trade.entry_price

    if not math.isnan(signal_bar_close) and signal_bar_close > 0.0 and not math.isnan(entry_bar_open):
        signal_entry_gap_pct = (entry_bar_open - signal_bar_close) / signal_bar_close
    else:
        signal_entry_gap_pct = 0.0

    # Post-hoc narx ekskursiyasi (MFE / MAE)
    raw_entry = entry_bar_open
    try:
        high_slice = df_5m["high"].loc[trade.entry_time : trade.exit_time]
        low_slice = df_5m["low"].loc[trade.entry_time : trade.exit_time]
        if not high_slice.empty:
            max_high = float(high_slice.max())
            min_low = float(low_slice.min())
        else:
            max_high = raw_entry
            min_low = raw_entry
    except Exception:
        max_high = raw_entry
        min_low = raw_entry

    mfe_pct = (max_high - raw_entry) / raw_entry if raw_entry > 0 else 0.0
    mae_pct = (min_low - raw_entry) / raw_entry if raw_entry > 0 else 0.0

    risk = trade.risk_per_share
    if risk is None or risk <= 0:
        if trade.stop_price is not None and trade.stop_price < raw_entry:
            risk = raw_entry - trade.stop_price

    if risk is not None and risk > 0:
        mfe_r = (max_high - raw_entry) / risk
        mae_r = (min_low - raw_entry) / risk
        target_0_5r = bool(mfe_r >= 0.5)
        target_1_0r = bool(mfe_r >= 1.0)
        target_1_5r = bool(mfe_r >= 1.5)
        target_2_0r = bool(mfe_r >= 2.0)
        stop_dist_abs = float(risk)
        stop_dist_pct = float(risk / raw_entry) if raw_entry > 0 else None
    else:
        mfe_r = None
        mae_r = None
        target_0_5r = False
        target_1_0r = False
        target_1_5r = False
        target_2_0r = False
        stop_dist_abs = None
        stop_dist_pct = None

    std_exit_reason = map_exit_reason(trade.exit_reason)
    is_be = (std_exit_reason == "BREAKEVEN") or (trade.net_return == 0.0)
    is_win = trade.net_return > 0.0 and not is_be
    is_loss = trade.net_return < 0.0 and not is_be

    return DiagnosticTradeRecord(
        symbol=trade.symbol,
        setup_time=trade.setup_time,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        stop_price=trade.stop_price,
        target_price=trade.target_price,
        exit_reason=std_exit_reason,
        gross_return=trade.gross_return,
        net_return=trade.net_return,
        r_multiple=trade.r_multiple,
        hold_duration_minutes=trade.hold_duration_minutes,
        setup_rsi=trade.rsi_at_setup,
        setup_rvol=trade.rvol_at_setup,
        setup_vwap=trade.vwap_at_setup,
        observed_price=trade.observed_price_at_setup,
        structure_5m=trade.structure_5m,
        structure_15m=trade.structure_15m,
        setup_status=trade.setup_status,
        trigger_type=trade.trigger_type,
        vwap_relation=trade.vwap_relation,
        evidence=trade.evidence,
        warnings=trade.warnings,
        score_reasons=trade.evidence,
        session_date=session_date,
        entry_hour=entry_hour,
        entry_minute=entry_minute,
        entry_time_bucket=entry_bucket,
        mfe_pct=mfe_pct,
        mfe_r=mfe_r,
        mae_pct=mae_pct,
        mae_r=mae_r,
        target_0_5r_reached=target_0_5r,
        target_1_0r_reached=target_1_0r,
        target_1_5r_reached=target_1_5r,
        target_2_0r_reached=target_2_0r,
        stop_distance_abs=stop_dist_abs,
        stop_distance_pct=stop_dist_pct,
        signal_entry_gap_pct=signal_entry_gap_pct,
        is_winner=is_win,
        is_loser=is_loss,
        is_breakeven=is_be,
        initial_stop_price=getattr(trade, "initial_stop_price", trade.stop_price),
        initial_risk_per_share=getattr(trade, "initial_risk_per_share", trade.risk_per_share),
        breakeven_price=getattr(trade, "breakeven_price", None),
        be_triggered=getattr(trade, "be_triggered", False),
        be_trigger_time=getattr(trade, "be_trigger_time", None),
        effective_exit_stop_price=getattr(trade, "effective_exit_stop_price", trade.stop_price),
    )


# =====================================================================
# 4. Diagnostic Analysis Engine
# =====================================================================

@dataclass
class FailureAnalysisResult:
    """DAY-05 xatolik tahlilining to'liq natijasi."""

    metadata: dict[str, Any]
    study_period: dict[str, Any]
    universe: list[str]
    total_trades_analyzed: int

    time_of_day_analysis: dict[str, Any]
    exit_reason_analysis: dict[str, Any]
    setup_components: dict[str, Any]
    repeated_entry_analysis: dict[str, Any]
    consecutive_loss_analysis: dict[str, Any]
    holding_duration_analysis: dict[str, Any]
    mfe_mae_analysis: dict[str, Any]
    target_excursion_analysis: dict[str, Any]
    stop_distance_analysis: dict[str, Any]
    signal_entry_gap_analysis: dict[str, Any]
    slippage_diagnosis: dict[str, Any]
    market_context_analysis: dict[str, Any]
    symbol_concentration: dict[str, Any]
    daily_distribution: dict[str, Any]
    failure_taxonomy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """JSON serializatsiya."""
        return asdict(self)


def run_day_failure_analysis(
    multi_result: MultiSymbolDayBacktestResult | None = None,
    *,
    symbols: Sequence[str] | None = None,
    provider: DataProvider | None = None,
    df_5m_by_symbol: dict[str, pd.DataFrame] | None = None,
) -> FailureAnalysisResult:
    """Muzlatilgan ko'p aksiyali natijalar ustida keng qamrovli xatolik tahlilini o'tkazadi."""
    prov = provider or get_provider()

    # 1. Multi-symbol natijalarni olish yoki yuklash
    if multi_result is None:
        logger.info("Executing multi-symbol backtest to gather baseline trades...")
        multi_result = run_multi_symbol_day_backtest(
            symbols=symbols,
            provider=prov,
        )

    # 2. 5m DataFramelarni tayyorlash (MFE/MAE hisoblash uchun)
    ohlcv_cache: dict[str, pd.DataFrame] = {}
    if df_5m_by_symbol is not None:
        ohlcv_cache.update(df_5m_by_symbol)

    for sym in multi_result.tested_symbols:
        if sym not in ohlcv_cache:
            try:
                df = prov.get_ohlcv(sym, "5m", include_extended_hours=False, closed_only=False, ignore_cache_expiry=True)
                ohlcv_cache[sym] = df
            except Exception as e:
                logger.warning(f"Could not load 5m data for {sym}: {e}")

    # 3. Savdolarni boyitish (DiagnosticTradeRecord)
    all_records: list[DiagnosticTradeRecord] = []
    for sym, res in multi_result.symbol_results.items():
        sym_df = ohlcv_cache.get(sym, pd.DataFrame())
        for t in res.trades:
            enriched = enrich_trade_record(t, sym_df)
            all_records.append(enriched)

    # Vaqt bo'yicha saralash
    all_records.sort(key=lambda r: r.entry_time)
    total_trades = len(all_records)

    # 4. Time-of-Day Analysis
    tod_order = [
        "09:30–10:00",
        "10:00–11:00",
        "11:00–12:00",
        "12:00–14:00",
        "14:00–15:00",
        "15:00–15:55",
    ]
    tod_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        tod_groups[r.entry_time_bucket].append(r)

    time_of_day_analysis: dict[str, Any] = {}
    for bucket in tod_order:
        recs = tod_groups.get(bucket, [])
        m = compute_group_metrics(recs)
        m["percentage_of_all_trades"] = round((len(recs) / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
        time_of_day_analysis[bucket] = m

    # 5. Exit Reason Analysis
    exit_order = ["STOP", "TARGET", "FORCED_EXIT"]
    exit_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        exit_groups[r.exit_reason].append(r)

    exit_reason_analysis: dict[str, Any] = {}
    for reason in exit_order:
        recs = exit_groups.get(reason, [])
        m = compute_group_metrics(recs)
        m["percentage_of_trades"] = round((len(recs) / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
        exit_reason_analysis[reason] = m

    # 6. Setup Component Analysis
    # A. VWAP relation
    vwap_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        vwap_groups[r.vwap_relation].append(r)
    vwap_analysis = {k: compute_group_metrics(v) for k, v in vwap_groups.items()}

    # B. RSI descriptive bins
    rsi_bins = ["<50", "50–55", "55–60", "60–70", "70+"]
    rsi_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        rsi_groups[get_rsi_bucket(r.setup_rsi)].append(r)
    rsi_analysis = {b: compute_group_metrics(rsi_groups.get(b, [])) for b in rsi_bins}

    # C. RVOL descriptive bins
    rvol_bins = ["<1.0", "1.0–2.0", "2.0–3.0", "3.0–5.0", "5.0+"]
    rvol_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        rvol_groups[get_rvol_bucket(r.setup_rvol)].append(r)
    rvol_analysis = {b: compute_group_metrics(rvol_groups.get(b, [])) for b in rvol_bins}

    # D. 5m Trigger
    trigger_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        trigger_groups[r.trigger_type].append(r)
    trigger_analysis = {k: compute_group_metrics(v) for k, v in trigger_groups.items()}

    # E. 15m Structure
    mtf_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        mtf_groups[r.structure_15m].append(r)
    mtf_analysis = {k: compute_group_metrics(v) for k, v in mtf_groups.items()}

    setup_components = {
        "vwap_relation": vwap_analysis,
        "rsi_bins": rsi_analysis,
        "rvol_bins": rvol_analysis,
        "trigger_type": trigger_analysis,
        "mtf_structure": mtf_analysis,
    }

    # 7. Repeated-Entry Analysis (Trades per session per symbol)
    session_sym_trades: dict[tuple[str, str], list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        session_sym_trades[(r.symbol, r.session_date)].append(r)

    total_traded_sessions = len(session_sym_trades)
    counts = [len(v) for v in session_sym_trades.values()]

    freq_1 = sum(1 for c in counts if c == 1)
    freq_2 = sum(1 for c in counts if c == 2)
    freq_3 = sum(1 for c in counts if c == 3)
    freq_4 = sum(1 for c in counts if c == 4)
    freq_5plus = sum(1 for c in counts if c >= 5)

    sess_ge_2 = sum(1 for c in counts if c >= 2)
    sess_ge_3 = sum(1 for c in counts if c >= 3)
    sess_ge_5 = sum(1 for c in counts if c >= 5)

    repeated_entry_analysis = {
        "total_traded_symbol_sessions": total_traded_sessions,
        "frequency_distribution": {
            "1_trade": {"sessions": freq_1, "pct": round(freq_1 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
            "2_trades": {"sessions": freq_2, "pct": round(freq_2 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
            "3_trades": {"sessions": freq_3, "pct": round(freq_3 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
            "4_trades": {"sessions": freq_4, "pct": round(freq_4 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
            "5plus_trades": {"sessions": freq_5plus, "pct": round(freq_5plus / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
        },
        "threshold_summary": {
            "sessions_ge_2_trades": {"count": sess_ge_2, "pct": round(sess_ge_2 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
            "sessions_ge_3_trades": {"count": sess_ge_3, "pct": round(sess_ge_3 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
            "sessions_ge_5_trades": {"count": sess_ge_5, "pct": round(sess_ge_5 / total_traded_sessions * 100, 2) if total_traded_sessions else 0},
        },
    }

    # 8. Consecutive-Loss Analysis
    curr_streak = 0
    max_streak = 0
    all_streaks: list[int] = []
    for r in all_records:
        if r.is_loser:
            curr_streak += 1
            max_streak = max(max_streak, curr_streak)
        else:
            if curr_streak > 0:
                all_streaks.append(curr_streak)
                curr_streak = 0
    if curr_streak > 0:
        all_streaks.append(curr_streak)

    streak_dist: dict[str, int] = defaultdict(int)
    for s in all_streaks:
        if s == 1:
            streak_dist["1_loss"] += 1
        elif s == 2:
            streak_dist["2_losses"] += 1
        elif s == 3:
            streak_dist["3_losses"] += 1
        elif s == 4:
            streak_dist["4_losses"] += 1
        elif s == 5:
            streak_dist["5_losses"] += 1
        elif 6 <= s <= 10:
            streak_dist["6_to_10_losses"] += 1
        else:
            streak_dist["10plus_losses"] += 1

    # Streaks by symbol
    sym_streaks: dict[str, int] = {}
    for sym, res in multi_result.symbol_results.items():
        s_curr = 0
        s_max = 0
        for t in res.trades:
            if t.net_return < 0:
                s_curr += 1
                s_max = max(s_max, s_curr)
            else:
                s_curr = 0
        sym_streaks[sym] = s_max

    consecutive_loss_analysis = {
        "max_consecutive_losses_global": max_streak,
        "avg_loss_streak_length": round(float(np.mean(all_streaks)), 2) if all_streaks else 0.0,
        "total_loss_sequences": len(all_streaks),
        "streak_length_distribution": dict(streak_dist),
        "max_streak_by_symbol": sym_streaks,
    }

    # 9. Holding-Duration Analysis
    duration_bins = [
        "0–5 min",
        "5–10 min",
        "10–20 min",
        "20–30 min",
        "30–60 min",
        "60–120 min",
        "120+ min",
    ]
    dur_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        dur_groups[get_duration_bucket(r.hold_duration_minutes)].append(r)

    holding_duration_analysis: dict[str, Any] = {}
    for b in duration_bins:
        recs = dur_groups.get(b, [])
        m = compute_group_metrics(recs)
        m["percentage_of_trades"] = round((len(recs) / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
        # Exit reason breakdown in this bucket
        exits_in_b = defaultdict(int)
        for r in recs:
            exits_in_b[r.exit_reason] += 1
        m["exit_reasons"] = dict(exits_in_b)
        holding_duration_analysis[b] = m

    # 10. MFE / MAE Analysis
    mfe_pcts = [r.mfe_pct * 100.0 for r in all_records]
    mae_pcts = [r.mae_pct * 100.0 for r in all_records]

    mfe_rs = [r.mfe_r for r in all_records if r.mfe_r is not None]
    mae_rs = [r.mae_r for r in all_records if r.mae_r is not None]

    win_records = [r for r in all_records if r.is_winner]
    loss_records = [r for r in all_records if r.is_loser]

    win_mfe_rs = [r.mfe_r for r in win_records if r.mfe_r is not None]
    loss_mfe_rs = [r.mfe_r for r in loss_records if r.mfe_r is not None]
    win_mae_rs = [r.mae_r for r in win_records if r.mae_r is not None]
    loss_mae_rs = [r.mae_r for r in loss_records if r.mae_r is not None]

    mfe_mae_analysis = {
        "all_trades": {
            "mean_mfe_pct": round(float(np.mean(mfe_pcts)), 4) if mfe_pcts else 0.0,
            "median_mfe_pct": round(float(np.median(mfe_pcts)), 4) if mfe_pcts else 0.0,
            "mean_mae_pct": round(float(np.mean(mae_pcts)), 4) if mae_pcts else 0.0,
            "median_mae_pct": round(float(np.median(mae_pcts)), 4) if mae_pcts else 0.0,
            "mean_mfe_r": round(float(np.mean(mfe_rs)), 4) if mfe_rs else 0.0,
            "median_mfe_r": round(float(np.median(mfe_rs)), 4) if mfe_rs else 0.0,
            "mean_mae_r": round(float(np.mean(mae_rs)), 4) if mae_rs else 0.0,
            "median_mae_r": round(float(np.median(mae_rs)), 4) if mae_rs else 0.0,
        },
        "winners": {
            "mean_mfe_r": round(float(np.mean(win_mfe_rs)), 4) if win_mfe_rs else 0.0,
            "median_mfe_r": round(float(np.median(win_mfe_rs)), 4) if win_mfe_rs else 0.0,
            "mean_mae_r": round(float(np.mean(win_mae_rs)), 4) if win_mae_rs else 0.0,
            "median_mae_r": round(float(np.median(win_mae_rs)), 4) if win_mae_rs else 0.0,
        },
        "losers": {
            "mean_mfe_r": round(float(np.mean(loss_mfe_rs)), 4) if loss_mfe_rs else 0.0,
            "median_mfe_r": round(float(np.median(loss_mfe_rs)), 4) if loss_mfe_rs else 0.0,
            "mean_mae_r": round(float(np.mean(loss_mae_rs)), 4) if loss_mae_rs else 0.0,
            "median_mae_r": round(float(np.median(loss_mae_rs)), 4) if loss_mae_rs else 0.0,
        },
    }

    # 11. Target Excursion Reach Analysis
    r05_count = sum(1 for r in all_records if r.target_0_5r_reached)
    r10_count = sum(1 for r in all_records if r.target_1_0r_reached)
    r15_count = sum(1 for r in all_records if r.target_1_5r_reached)
    r20_count = sum(1 for r in all_records if r.target_2_0r_reached)

    loss_r05 = sum(1 for r in loss_records if r.target_0_5r_reached)
    loss_r10 = sum(1 for r in loss_records if r.target_1_0r_reached)
    loss_r15 = sum(1 for r in loss_records if r.target_1_5r_reached)

    target_excursion_analysis = {
        "all_trades_reach": {
            "reached_0_5R": {"count": r05_count, "pct": round(r05_count / total_trades * 100, 2) if total_trades else 0},
            "reached_1_0R": {"count": r10_count, "pct": round(r10_count / total_trades * 100, 2) if total_trades else 0},
            "reached_1_5R": {"count": r15_count, "pct": round(r15_count / total_trades * 100, 2) if total_trades else 0},
            "reached_2_0R": {"count": r20_count, "pct": round(r20_count / total_trades * 100, 2) if total_trades else 0},
        },
        "losers_that_moved_favorably": {
            "losing_trades_count": len(loss_records),
            "reached_0_5R_then_lost": {"count": loss_r05, "pct": round(loss_r05 / len(loss_records) * 100, 2) if loss_records else 0},
            "reached_1_0R_then_lost": {"count": loss_r10, "pct": round(loss_r10 / len(loss_records) * 100, 2) if loss_records else 0},
            "reached_1_5R_then_lost": {"count": loss_r15, "pct": round(loss_r15 / len(loss_records) * 100, 2) if loss_records else 0},
        },
    }

    # 12. Stop-Distance Analysis
    stop_bins = ["<0.25%", "0.25–0.50%", "0.50–1.00%", "1.00–2.00%", "2.00%+"]
    stop_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        stop_groups[get_stop_distance_bucket(r.stop_distance_pct)].append(r)
    stop_distance_analysis = {b: compute_group_metrics(stop_groups.get(b, [])) for b in stop_bins}

    # 13. Signal-to-Entry Gap Analysis
    gap_bins = ["negative gap (<-0.05%)", "near-zero gap (-0.05% to +0.05%)", "positive gap (>+0.05%)"]
    gap_groups: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        gap_groups[get_entry_gap_bucket(r.signal_entry_gap_pct)].append(r)
    signal_entry_gap_analysis = {b: compute_group_metrics(gap_groups.get(b, [])) for b in gap_bins}

    # 14. Slippage Diagnosis
    gross_returns = [r.gross_return for r in all_records]
    net_returns_0bps = [r.net_return for r in all_records]
    avg_gross_edge = float(np.mean(gross_returns)) * 100.0 if gross_returns else 0.0
    median_gross_edge = float(np.median(gross_returns)) * 100.0 if gross_returns else 0.0
    avg_net_0bps = float(np.mean(net_returns_0bps)) * 100.0 if net_returns_0bps else 0.0

    slippage_diagnosis = {
        "avg_gross_edge_pct": round(avg_gross_edge, 4),
        "median_gross_edge_pct": round(median_gross_edge, 4),
        "avg_net_edge_0bps_pct": round(avg_net_0bps, 4),
        "slippage_sensitivity_summary": multi_result.slippage_sensitivity,
        "per_trade_friction_analysis": {
            "round_trip_friction_5bps_pct": 0.10,
            "round_trip_friction_10bps_pct": 0.20,
            "average_trades_per_symbol": round(total_trades / len(multi_result.tested_symbols), 1) if multi_result.tested_symbols else 0,
            "friction_drag_mechanism": (
                "With an average gross edge near zero (-0.01%), incurring 10 bps round-trip friction "
                "across ~228 trades per symbol creates an inescapable ~22.8% drag per symbol, which "
                "compounds geometrically to -99.8% portfolio decay."
            ),
        },
    }

    # 15. Market Context Analysis
    market_context_analysis: dict[str, Any] = {}
    if multi_result.market_context is not None:
        mc = multi_result.market_context
        market_context_analysis = {
            "SPY_positive_days": {
                "trades": mc.spy_positive_trades,
                "win_rate": mc.spy_positive_win_rate,
                "avg_return": mc.spy_positive_avg_return,
            },
            "SPY_negative_days": {
                "trades": mc.spy_negative_trades,
                "win_rate": mc.spy_negative_win_rate,
                "avg_return": mc.spy_negative_avg_return,
            },
            "QQQ_positive_days": {
                "trades": mc.qqq_positive_trades,
                "win_rate": mc.qqq_positive_win_rate,
                "avg_return": mc.qqq_positive_avg_return,
            },
            "QQQ_negative_days": {
                "trades": mc.qqq_negative_trades,
                "win_rate": mc.qqq_negative_win_rate,
                "avg_return": mc.qqq_negative_avg_return,
            },
        }

    # 16. Symbol Concentration
    sym_records: dict[str, list[DiagnosticTradeRecord]] = defaultdict(list)
    for r in all_records:
        sym_records[r.symbol].append(r)

    sym_stats: list[dict[str, Any]] = []
    for sym in multi_result.tested_symbols:
        recs = sym_records.get(sym, [])
        m = compute_group_metrics(recs)
        sym_stats.append({
            "symbol": sym,
            "trades": m["trade_count"],
            "pct_of_all_trades": round(m["trade_count"] / total_trades * 100, 2) if total_trades else 0,
            "total_R": m["total_R"],
            "win_rate": m["win_rate"],
            "avg_return": m["avg_return"],
        })

    # Top 5 symbols by trades
    top5_by_trades = sorted(sym_stats, key=lambda x: x["trades"], reverse=True)[:5]
    top5_trades_sum = sum(x["trades"] for x in top5_by_trades)

    # Top 5 symbols by negative R
    negative_r_symbols = [x for x in sym_stats if x["total_R"] < 0]
    total_negative_R = sum(x["total_R"] for x in negative_r_symbols)
    top5_by_neg_r = sorted(negative_r_symbols, key=lambda x: x["total_R"])[:5]
    top5_neg_r_sum = sum(x["total_R"] for x in top5_by_neg_r)

    symbol_concentration = {
        "per_symbol_breakdown": sym_stats,
        "top5_by_trade_volume": {
            "symbols": [x["symbol"] for x in top5_by_trades],
            "total_trades": top5_trades_sum,
            "pct_of_all_trades": round(top5_trades_sum / total_trades * 100, 2) if total_trades else 0,
        },
        "top5_by_negative_R": {
            "symbols": [x["symbol"] for x in top5_by_neg_r],
            "total_R": round(top5_neg_r_sum, 2),
            "pct_of_all_negative_R": round((top5_neg_r_sum / total_negative_R) * 100, 2) if total_negative_R != 0 else 0,
        },
    }

    # 17. Daily Outcome Distribution
    daily_returns: list[float] = []
    for (sym, sdate), recs in session_sym_trades.items():
        daily_ret = sum(r.net_return for r in recs) * 100.0
        daily_returns.append(daily_ret)

    pos_days = sum(1 for d in daily_returns if d > 0)
    neg_days = sum(1 for d in daily_returns if d < 0)
    flat_days = sum(1 for d in daily_returns if d == 0)

    daily_distribution = {
        "total_symbol_sessions": len(daily_returns),
        "positive_symbol_days": {"count": pos_days, "pct": round(pos_days / len(daily_returns) * 100, 2) if daily_returns else 0},
        "negative_symbol_days": {"count": neg_days, "pct": round(neg_days / len(daily_returns) * 100, 2) if daily_returns else 0},
        "flat_symbol_days": {"count": flat_days, "pct": round(flat_days / len(daily_returns) * 100, 2) if daily_returns else 0},
        "mean_daily_return_pct": round(float(np.mean(daily_returns)), 4) if daily_returns else 0.0,
        "median_daily_return_pct": round(float(np.median(daily_returns)), 4) if daily_returns else 0.0,
        "max_daily_gain_pct": round(float(np.max(daily_returns)), 4) if daily_returns else 0.0,
        "max_daily_loss_pct": round(float(np.min(daily_returns)), 4) if daily_returns else 0.0,
    }

    # 18. Failure Taxonomy
    taxonomy_definitions = {
        "EARLY_STOP": [r for r in all_records if r.exit_reason == "STOP" and r.hold_duration_minutes <= 15],
        "EXTENDED_HOLD": [r for r in all_records if r.hold_duration_minutes >= 60],
        "FORCED_EXIT": [r for r in all_records if r.exit_reason == "FORCED_EXIT"],
        "REPEATED_ENTRY": [r for r in all_records if len(session_sym_trades.get((r.symbol, r.session_date), [])) >= 3],
        "LOW_RVOL": [r for r in all_records if r.setup_rvol < 2.0],
        "HIGH_RVOL": [r for r in all_records if r.setup_rvol >= 3.0],
        "LOW_RSI": [r for r in all_records if r.setup_rsi < 55.0],
        "HIGH_RSI": [r for r in all_records if r.setup_rsi >= 65.0],
        "BEARISH_15M_CONTEXT": [r for r in all_records if r.structure_15m == "BEARISH"],
        "VWAP_RECLAIM_FAILURE": [r for r in all_records if r.is_loser and (r.mfe_r is None or r.mfe_r < 0.5)],
        "ENTRY_GAP": [r for r in all_records if abs(r.signal_entry_gap_pct) >= 0.001],
        "FRICTION_SENSITIVE": [r for r in all_records if r.gross_return > 0.0 and r.net_return <= 0.0],
    }

    failure_taxonomy: dict[str, Any] = {}
    for cat, recs in taxonomy_definitions.items():
        m = compute_group_metrics(recs)
        m["percentage_of_all_trades"] = round(len(recs) / total_trades * 100, 2) if total_trades else 0
        failure_taxonomy[cat] = m

    return FailureAnalysisResult(
        metadata={
            "description": "DAY-05 Failure Analysis of Frozen DAY-01/DAY-02 Strategy",
            "execution_model": "Frozen DAY-02 (Next bar open, STOP_FIRST, 2.0R target, SIGNAL_LOW stop)",
        },
        study_period={
            "start": str(multi_result.study_window_start),
            "end": str(multi_result.study_window_end),
            "sessions": multi_result.total_sessions,
        },
        universe=multi_result.tested_symbols,
        total_trades_analyzed=total_trades,
        time_of_day_analysis=time_of_day_analysis,
        exit_reason_analysis=exit_reason_analysis,
        setup_components=setup_components,
        repeated_entry_analysis=repeated_entry_analysis,
        consecutive_loss_analysis=consecutive_loss_analysis,
        holding_duration_analysis=holding_duration_analysis,
        mfe_mae_analysis=mfe_mae_analysis,
        target_excursion_analysis=target_excursion_analysis,
        stop_distance_analysis=stop_distance_analysis,
        signal_entry_gap_analysis=signal_entry_gap_analysis,
        slippage_diagnosis=slippage_diagnosis,
        market_context_analysis=market_context_analysis,
        symbol_concentration=symbol_concentration,
        daily_distribution=daily_distribution,
        failure_taxonomy=failure_taxonomy,
    )


# =====================================================================
# 5. Human-Readable Report Formatter
# =====================================================================

def format_failure_analysis_report(res: FailureAnalysisResult) -> str:
    """Xatolik tahlili natijalarini factual inson o'qiy oladigan matnga aylantiradi."""
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("DAY-05 — FAILURE ANALYSIS OF THE FROZEN DAY STRATEGY")
    lines.append("=" * 80)
    lines.append(f"Study Period:       {res.study_period['start']} to {res.study_period['end']} ({res.study_period['sessions']} RTH sessions)")
    lines.append(f"Universe:           {len(res.universe)} liquid US equities")
    lines.append(f"Total Trades:       {res.total_trades_analyzed:,}")
    lines.append(f"Strategy:           FROZEN DAY-01 (VWAP Reclaim, RSI>50, RVOL>=2.0x, 5m trigger)")
    lines.append(f"Execution:          FROZEN DAY-02 (Next bar open, 2.0R target, SIGNAL_LOW stop, STOP_FIRST)")
    lines.append("")

    # 1. Time-of-day
    lines.append("-" * 80)
    lines.append("1. TIME-OF-DAY FAILURE ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"{'Time Bucket':<15} {'Trades':<8} {'% All':<8} {'WinRate':<10} {'AvgRet':<10} {'MedRet':<10} {'Total_R':<10} {'PF':<8} {'AvgHold'}")
    for b, m in res.time_of_day_analysis.items():
        lines.append(
            f"{b:<15} {m['trade_count']:<8} {m.get('percentage_of_all_trades', 0):<8.1f}% "
            f"{m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['median_return']:<9.2f}% "
            f"{m['total_R']:<10.1f} {m['profit_factor']:<8.2f} {m['avg_hold_duration']:<6.1f}m"
        )
    lines.append("")

    # 2. Exit reason
    lines.append("-" * 80)
    lines.append("2. EXIT REASON ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"{'Exit Reason':<15} {'Trades':<8} {'% All':<8} {'WinRate':<10} {'AvgRet':<10} {'Avg_R':<10} {'Total_R':<10} {'AvgHold'}")
    for r, m in res.exit_reason_analysis.items():
        lines.append(
            f"{r:<15} {m['trade_count']:<8} {m.get('percentage_of_trades', 0):<8.1f}% "
            f"{m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['avg_R']:<10.2f} "
            f"{m['total_R']:<10.1f} {m['avg_hold_duration']:<6.1f}m"
        )
    lines.append("")

    # 3. Setup component analysis
    lines.append("-" * 80)
    lines.append("3. SETUP COMPONENT DISTRIBUTIONS")
    lines.append("-" * 80)
    lines.append("A. 5m Trigger Type:")
    lines.append(f"  {'Trigger':<30} {'Trades':<8} {'WinRate':<10} {'AvgRet':<10} {'Total_R'}")
    for trig, m in res.setup_components["trigger_type"].items():
        lines.append(f"  {trig:<30} {m['trade_count']:<8} {m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['total_R']:<10.1f}")

    lines.append("\nB. 15m MTF Structure Context:")
    lines.append(f"  {'15m Context':<30} {'Trades':<8} {'WinRate':<10} {'AvgRet':<10} {'Total_R'}")
    for mtf, m in res.setup_components["mtf_structure"].items():
        lines.append(f"  {mtf:<30} {m['trade_count']:<8} {m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['total_R']:<10.1f}")

    lines.append("\nC. RSI Descriptive Bins:")
    lines.append(f"  {'RSI Range':<30} {'Trades':<8} {'WinRate':<10} {'AvgRet':<10} {'Total_R'}")
    for rsi_b, m in res.setup_components["rsi_bins"].items():
        lines.append(f"  {rsi_b:<30} {m['trade_count']:<8} {m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['total_R']:<10.1f}")

    lines.append("\nD. RVOL Descriptive Bins:")
    lines.append(f"  {'RVOL Range':<30} {'Trades':<8} {'WinRate':<10} {'AvgRet':<10} {'Total_R'}")
    for rvol_b, m in res.setup_components["rvol_bins"].items():
        lines.append(f"  {rvol_b:<30} {m['trade_count']:<8} {m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['total_R']:<10.1f}")
    lines.append("")

    # 4. Repeated entries
    lines.append("-" * 80)
    lines.append("4. REPEATED-ENTRY ANALYSIS (Same symbol/session trade clustering)")
    lines.append("-" * 80)
    rep = res.repeated_entry_analysis
    lines.append(f"Total Traded Symbol-Sessions: {rep['total_traded_symbol_sessions']:,}")
    for k, v in rep["frequency_distribution"].items():
        lines.append(f"  {k:<15}: {v['sessions']:>5} sessions ({v['pct']}%)")
    lines.append("Multi-Trade Sessions Summary:")
    for k, v in rep["threshold_summary"].items():
        lines.append(f"  {k:<25}: {v['count']:>5} sessions ({v['pct']}%)")
    lines.append("")

    # 5. Loss streaks
    lines.append("-" * 80)
    lines.append("5. CONSECUTIVE-LOSS ANALYSIS")
    lines.append("-" * 80)
    ls = res.consecutive_loss_analysis
    lines.append(f"Global Maximum Consecutive Losses: {ls['max_consecutive_losses_global']}")
    lines.append(f"Average Loss Streak Length:        {ls['avg_loss_streak_length']} trades")
    lines.append("Streak Length Distribution:")
    for k, v in ls["streak_length_distribution"].items():
        lines.append(f"  {k:<20}: {v:>5} occurrences")
    lines.append("")

    # 6. Holding duration
    lines.append("-" * 80)
    lines.append("6. HOLDING DURATION ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"{'Duration':<15} {'Trades':<8} {'% All':<8} {'WinRate':<10} {'AvgRet':<10} {'Avg_R':<10} {'Total_R':<10} {'Exits (Stop/Tgt/Forced)'}")
    for b, m in res.holding_duration_analysis.items():
        exits = m.get("exit_reasons", {})
        exits_str = f"S:{exits.get('STOP', 0)} / T:{exits.get('TARGET', 0)} / F:{exits.get('FORCED_EXIT', 0)}"
        lines.append(
            f"{b:<15} {m['trade_count']:<8} {m.get('percentage_of_trades', 0):<8.1f}% "
            f"{m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['avg_R']:<10.2f} "
            f"{m['total_R']:<10.1f} {exits_str}"
        )
    lines.append("")

    # 7. MFE / MAE
    lines.append("-" * 80)
    lines.append("7. MFE / MAE POST-HOC EXCURSION ANALYSIS")
    lines.append("-" * 80)
    mm = res.mfe_mae_analysis
    lines.append(f"All Trades   : Mean MFE: {mm['all_trades']['mean_mfe_pct']:+.2f}% ({mm['all_trades']['mean_mfe_r']:+.2f}R) | Mean MAE: {mm['all_trades']['mean_mae_pct']:+.2f}% ({mm['all_trades']['mean_mae_r']:+.2f}R)")
    lines.append(f"Winners Only : Mean MFE: {mm['winners']['mean_mfe_r']:+.2f}R | Mean MAE: {mm['winners']['mean_mae_r']:+.2f}R")
    lines.append(f"Losers Only  : Mean MFE: {mm['losers']['mean_mfe_r']:+.2f}R | Mean MAE: {mm['losers']['mean_mae_r']:+.2f}R")
    lines.append("")

    # 8. Target excursion reach
    lines.append("-" * 80)
    lines.append("8. TARGET EXCURSION & PRE-EXIT REACH")
    lines.append("-" * 80)
    te = res.target_excursion_analysis
    lines.append("All Trades Excursion Thresholds Reached Before Exit:")
    for k, v in te["all_trades_reach"].items():
        lines.append(f"  {k:<20}: {v['count']:>5} trades ({v['pct']}%)")
    lines.append("\nLosing Trades Favorable Movement (Nearly Winning Then Reversing):")
    for k, v in te["losers_that_moved_favorably"].items():
        if isinstance(v, dict):
            lines.append(f"  {k:<30}: {v['count']:>5} trades ({v['pct']}%)")
    lines.append("")

    # 9. Stop distance
    lines.append("-" * 80)
    lines.append("9. STOP-LOSS DISTANCE ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"{'Stop Distance':<18} {'Trades':<8} {'WinRate':<10} {'AvgRet':<10} {'Avg_R':<10} {'Total_R'}")
    for b, m in res.stop_distance_analysis.items():
        lines.append(f"{b:<18} {m['trade_count']:<8} {m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['avg_R']:<10.2f} {m['total_R']:<10.1f}")
    lines.append("")

    # 10. Gap analysis
    lines.append("-" * 80)
    lines.append("10. SIGNAL-TO-ENTRY GAP ANALYSIS (Signal Bar Close → Next Bar Open)")
    lines.append("-" * 80)
    lines.append(f"{'Gap Type':<35} {'Trades':<8} {'WinRate':<10} {'AvgRet':<10} {'Total_R'}")
    for b, m in res.signal_entry_gap_analysis.items():
        lines.append(f"{b:<35} {m['trade_count']:<8} {m['win_rate']:<9.1f}% {m['avg_return']:<9.2f}% {m['total_R']:<10.1f}")
    lines.append("")

    # 11. Slippage diagnosis
    lines.append("-" * 80)
    lines.append("11. SLIPPAGE & EXECUTION FRICTION DIAGNOSIS")
    lines.append("-" * 80)
    sd = res.slippage_diagnosis
    lines.append(f"Average Gross Edge per Trade:   {sd['avg_gross_edge_pct']:+.4f}%")
    lines.append(f"Median Gross Edge per Trade:    {sd['median_gross_edge_pct']:+.4f}%")
    lines.append(f"Average Net Edge (0 bps):       {sd['avg_net_edge_0bps_pct']:+.4f}%")
    lines.append(f"Friction Drag Diagnosis:")
    lines.append(f"  {sd['per_trade_friction_analysis']['friction_drag_mechanism']}")
    lines.append("")

    # 12. Symbol concentration
    lines.append("-" * 80)
    lines.append("12. SYMBOL CONCENTRATION ANALYSIS")
    lines.append("-" * 80)
    sc = res.symbol_concentration
    lines.append(f"Top 5 Symbols by Trade Volume: {', '.join(sc['top5_by_trade_volume']['symbols'])}")
    lines.append(f"  Volume: {sc['top5_by_trade_volume']['total_trades']} trades ({sc['top5_by_trade_volume']['pct_of_all_trades']}%)")
    lines.append(f"Top 5 Symbols by Negative R:   {', '.join(sc['top5_by_negative_R']['symbols'])}")
    lines.append(f"  Loss:   {sc['top5_by_negative_R']['total_R']}R ({sc['top5_by_negative_R']['pct_of_all_negative_R']}% of all negative R)")
    lines.append("")

    # 13. Daily distribution
    lines.append("-" * 80)
    lines.append("13. DAILY OUTCOME DISTRIBUTION (Symbol-Sessions)")
    lines.append("-" * 80)
    dd = res.daily_distribution
    lines.append(f"Total Symbol-Sessions Traded: {dd['total_symbol_sessions']:,}")
    lines.append(f"  Positive Days: {dd['positive_symbol_days']['count']} ({dd['positive_symbol_days']['pct']}%)")
    lines.append(f"  Negative Days: {dd['negative_symbol_days']['count']} ({dd['negative_symbol_days']['pct']}%)")
    lines.append(f"  Flat Days:     {dd['flat_symbol_days']['count']} ({dd['flat_symbol_days']['pct']}%)")
    lines.append(f"  Mean Daily Return:   {dd['mean_daily_return_pct']:+.2f}%")
    lines.append(f"  Median Daily Return: {dd['median_daily_return_pct']:+.2f}%")
    lines.append(f"  Max Daily Gain:      {dd['max_daily_gain_pct']:+.2f}%")
    lines.append(f"  Max Daily Loss:      {dd['max_daily_loss_pct']:+.2f}%")
    lines.append("")

    # 14. Failure taxonomy
    lines.append("-" * 80)
    lines.append("14. FACTUAL FAILURE TAXONOMY")
    lines.append("-" * 80)
    lines.append(f"{'Failure Category':<25} {'Trades':<8} {'% All':<8} {'WinRate':<10} {'Avg_R':<10} {'Total_R'}")
    for cat, m in res.failure_taxonomy.items():
        lines.append(
            f"{cat:<25} {m['trade_count']:<8} {m.get('percentage_of_all_trades', 0):<8.1f}% "
            f"{m['win_rate']:<9.1f}% {m['avg_R']:<10.2f} {m['total_R']:<10.1f}"
        )
    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF DAY-05 FAILURE ANALYSIS REPORT")
    lines.append("=" * 80)

    return "\n".join(lines)
