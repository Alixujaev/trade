"""Portfolio-darajali backtest — bitta umumiy kapital, yagona xronologik kalendar.

Muammo: `scripts/backtest_breakout_retest.py::portfolio_equity_curve` barcha
symbol savdolarini `entry_ts` bo'yicha bittalab kompaundlaydi — bir vaqtda ochiq
pozitsiyalarni hisobga olmaydi, shuning uchun equity (~22x) va max drawdown (~4%)
norealistik. Bu modul haqiqiy portfelni simulyatsiya qiladi: bir vaqtda ko'pi
bilan `MAX_CONCURRENT_POSITIONS` pozitsiya, ochiq riskning yig'indisi
`MAX_PORTFOLIO_RISK_PCT` bilan cheklangan, leverage yo'q, har bar mark-to-market
equity → haqiqiy max DD / CAGR / Sharpe / Sortino.

Asosiy insight: `engine.py::_simulate_fixed_exit`/`_simulate_trailing_exit` chiqish
bari/narxi FAQAT o'sha symbolning kelajakdagi barlariga + signal stop/target
darajasiga bog'liq (kapitalga EMAS). Shuning uchun pozitsiyaning to'liq chiqishi
entry paytida bir marta oldindan hisoblanadi — engine bilan bit-parity. Timeline
faqat "qaysi barda ochiladi/yopiladi"ni jadvalga qo'yadi.

Lookahead YO'Q: qat'iy xronologik yurish; entry faqat tasdiqlangan barда; har bar
predikati faqat o'sha bar (yoki oldingi) ma'lumotidan foydalanadi.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backtest.engine import _simulate_fixed_exit, _simulate_trailing_exit
from backtest.metrics import (
    avg_hold_days,
    avg_r_multiple,
    expectancy_r,
    max_drawdown_pct,
    profit_factor,
    win_rate,
)
from backtest.types import TradeResult
from backtest.window import slice_date_range
from config.settings import (
    ATR_PERIOD,
    ATR_RISK_MULT,
    MAX_CONCURRENT_POSITIONS,
    MAX_PORTFOLIO_RISK_PCT,
    MIN_BREAKOUT_RR,
    RISK_PCT_PER_TRADE,
    SWING_LOOKBACK,
    TRAIL_ATR_MULT,
)
from smc.types import TradeSetup
from smc.zones import compute_atr
from strategy.breakout_retest import generate_breakout_retest_signals
from strategy.scoring import apply_scores, filter_by_score

_EPS = 1e-9

# Yillashtirish koeffitsienti (Sharpe/Sortino). Interval bo'yicha qat'iy lookup —
# union-timeline notekis oraliqli bo'lgani uchun median oraliqdan chiqarishdan mustahkam.
_PERIODS_PER_YEAR: dict[str, float] = {"1d": 252.0, "1wk": 52.0, "4h": 1512.0, "1h": 1638.0}


# ======================================================================
# Dataclass'lar
# ======================================================================


@dataclass(frozen=True)
class PortfolioConfig:
    """Portfel simulyatori sozlamalari."""

    initial_capital: float = 100_000.0
    risk_pct: float = RISK_PCT_PER_TRADE
    max_concurrent_positions: int = MAX_CONCURRENT_POSITIONS
    max_portfolio_risk_pct: float = MAX_PORTFOLIO_RISK_PCT
    risk_model: str = "fixed_pct"  # "fixed_pct" | "atr"
    exit_mode: str = "fixed"  # "fixed" | "trailing"
    commission_pct: float = 0.0
    slippage_pct: float = 0.0
    atr_period: int = ATR_PERIOD
    trail_atr_mult: float = TRAIL_ATR_MULT
    interval: str = "1d"
    periods_per_year: float | None = None  # None -> intervaldan
    risk_free_rate: float = 0.0  # yillik; Sharpe/Sortino
    one_position_per_symbol: bool = True  # engine bilan mos
    active_span_only_concurrency: bool = True


@dataclass(frozen=True)
class SymbolData:
    """Bitta symbolning oyna ichidagi OHLCV + lookahead'siz signal'lari."""

    symbol: str
    df: pd.DataFrame  # tz-aware UTC, open/high/low/close/volume
    signals: list[TradeSetup]  # entry_index_pos bo'yicha saralangan


@dataclass(frozen=True)
class PortfolioCandidate:
    """Signal + OLDINDAN hisoblangan chiqish (kapitalga bog'liq emas)."""

    symbol: str
    setup: TradeSetup
    entry_ts: pd.Timestamp
    entry_index_pos: int  # symbol-lokal
    entry_price: float
    stop_price: float
    exit_index_pos: int  # symbol-lokal
    exit_ts: pd.Timestamp
    exit_price: float
    exit_reason: str  # "stop"|"target"|"trailing_stop"|"end_of_data"
    min_low: float
    running_high: float
    sizing_per_share_risk: float  # risk_model'ga qarab (narx yoki ATR)


@dataclass(frozen=True)
class OpenPosition:
    """Ochiq pozitsiya — chiqishi allaqachon ma'lum, faqat sana kelishini kutadi."""

    symbol: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    exit_k: int  # chiqish barining timeline'dagi pozitsiyasi
    entry_index_pos: int
    exit_index_pos: int
    entry_price: float
    stop_price: float
    exit_price: float
    exit_reason: str
    shares: float
    effective_entry: float  # entry_price*(1+slippage_pct)
    planned_risk_dollars: float  # shares*(entry_price-stop_price)
    min_low: float
    running_high: float


@dataclass(frozen=True)
class SkippedEntry:
    """Kirmasdan o'tkazib yuborilgan signal (sababi bilan)."""

    symbol: str
    entry_ts: pd.Timestamp
    reason: str  # "equity<=0"|"symbol_already_open"|"max_concurrent"
    # |"portfolio_risk_cap"|"insufficient_capital"|"degenerate_setup"


@dataclass(frozen=True)
class BenchmarkResult:
    """Bitta benchmark — teng-vazn buy&hold yoki bitta ticker buy&hold."""

    name: str
    equity_curve: list[float]  # timeline bilan 1:1
    metrics: dict
    error: str | None = None


@dataclass(frozen=True)
class PortfolioResult:
    """Butun portfel simulyatsiyasi natijasi."""

    trades: list[TradeResult]
    trade_symbols: list[str]  # trades bilan 1:1 (TradeResult symbol saqlamaydi)
    skipped: list[SkippedEntry]
    timeline: list[pd.Timestamp]
    equity_curve: list[float]  # bar-by-bar MTM, timeline bilan 1:1
    concurrency_samples: list[int]  # timeline bilan 1:1
    initial_capital: float
    final_capital: float
    metrics: dict
    benchmarks: list[BenchmarkResult]
    # ESKI usul: BARCHA signallar (cap'siz) entry_ts bo'yicha ketma-ket kompaund
    # (1.0 boshlanish). Yonma-yon solishtiruv uchun.
    naive_all_signals_curve: list[float] = field(default_factory=list)


# ======================================================================
# Sof metrika helper'lari
# ======================================================================


def _periods_per_year_for(interval: str) -> float:
    """Interval -> yiliga davrlar soni (noma'lum -> 252)."""
    return _PERIODS_PER_YEAR.get(interval, 252.0)


def periodic_returns(equity_curve: list[float]) -> list[float]:
    """r_k = E[k]/E[k-1] - 1 (k=1..N). E[k-1] == 0 -> 0.0. <2 element -> []."""
    if len(equity_curve) < 2:
        return []
    out: list[float] = []
    for k in range(1, len(equity_curve)):
        prev = equity_curve[k - 1]
        out.append((equity_curve[k] / prev - 1.0) if prev != 0 else 0.0)
    return out


def curve_return_pct(equity_curve: list[float]) -> float:
    """(E[-1] - E[0]) / E[0] * 100. <2 element yoki E[0] <= 0 -> 0.0."""
    if len(equity_curve) < 2 or equity_curve[0] <= 0:
        return 0.0
    return (equity_curve[-1] - equity_curve[0]) / equity_curve[0] * 100.0


def cagr_pct(equity_curve: list[float], timeline: list[pd.Timestamp]) -> float:
    """Kalendar-vaqt asosidagi CAGR (%). Degenerate holatlar -> 0.0."""
    if len(equity_curve) < 2 or len(timeline) < 2:
        return 0.0
    years = (timeline[-1] - timeline[0]).total_seconds() / (365.25 * 86400)
    e0, e1 = equity_curve[0], equity_curve[-1]
    if years <= 0 or e0 <= 0 or e1 <= 0:
        return 0.0
    return ((e1 / e0) ** (1.0 / years) - 1.0) * 100.0


def sharpe_ratio(
    equity_curve: list[float], *, periods_per_year: float, risk_free_rate: float = 0.0
) -> float:
    """Yillashtirilgan Sharpe (rf davriylashtiriladi, namunaviy std ddof=1). Aniqlanmasa 0.0."""
    returns = periodic_returns(equity_curve)
    n = len(returns)
    if n < 2:
        return 0.0
    rf_p = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess = [r - rf_p for r in returns]
    mean = sum(excess) / n
    var = sum((x - mean) ** 2 for x in excess) / (n - 1)
    sd = var**0.5
    if sd <= 0:
        return 0.0
    return (mean / sd) * (periods_per_year**0.5)


def sortino_ratio(
    equity_curve: list[float], *, periods_per_year: float, risk_free_rate: float = 0.0
) -> float:
    """Yillashtirilgan Sortino — downside deviation BUTUN N ga bo'linadi (standart). Aniqlanmasa 0.0."""
    returns = periodic_returns(equity_curve)
    n = len(returns)
    if n < 2:
        return 0.0
    rf_p = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess = [r - rf_p for r in returns]
    mean = sum(excess) / n
    downside = [min(x, 0.0) for x in excess]
    dd = (sum(x * x for x in downside) / n) ** 0.5
    if dd <= 0:
        return 0.0
    return (mean / dd) * (periods_per_year**0.5)


def avg_concurrent_positions(
    concurrency_samples: list[int], *, active_span_only: bool = True
) -> float:
    """O'rtacha bir vaqtdagi ochiq pozitsiyalar. active_span_only -> birinchi/oxirgi
    nolmas namuna orasidagi oraliq bo'yicha o'rtacha (bo'sh "sovuq boshlanish"/"tugash"
    davrlari hisobga olinmaydi)."""
    if not concurrency_samples:
        return 0.0
    if active_span_only:
        nz = [i for i, c in enumerate(concurrency_samples) if c > 0]
        if not nz:
            return 0.0
        span = concurrency_samples[nz[0] : nz[-1] + 1]
    else:
        span = concurrency_samples
    return sum(span) / len(span)


def max_concurrent_positions(concurrency_samples: list[int]) -> int:
    """Bir vaqtda ochiq bo'lgan eng ko'p pozitsiya soni."""
    return max(concurrency_samples) if concurrency_samples else 0


def curve_metrics(
    equity_curve: list[float],
    timeline: list[pd.Timestamp],
    *,
    periods_per_year: float,
    risk_free_rate: float = 0.0,
) -> dict:
    """Portfel VA benchmark egri chiziqlari uchun bir xil 5 metrika to'plami."""
    return {
        "return_pct": curve_return_pct(equity_curve),
        "cagr_pct": cagr_pct(equity_curve, timeline),
        "max_drawdown_pct": max_drawdown_pct(equity_curve),
        "sharpe": sharpe_ratio(
            equity_curve, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate
        ),
        "sortino": sortino_ratio(
            equity_curve, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate
        ),
    }


# ======================================================================
# Benchmark egri chiziqlari
# ======================================================================


def _ffill_to_timeline(close: pd.Series, timeline: list[pd.Timestamp]) -> np.ndarray:
    """close seriyasini timeline'ga reindex + forward-fill (tarixdan oldin NaN)."""
    return close.reindex(pd.DatetimeIndex(timeline), method="ffill").to_numpy()


def single_ticker_buy_hold_curve(
    df: pd.DataFrame,
    timeline: list[pd.Timestamp],
    *,
    initial_capital: float,
    commission_pct: float,
    slippage_pct: float,
) -> list[float]:
    """Bitta ticker'ni birinchi bardan oxirigacha ushlab turgan equity egri chizig'i.

    Ticker universe'da bo'lmasligi mumkin — timeline'da uning bari yo'q nuqtalarda
    forward-fill; birinchi bar'gacha kapital naqd turadi.
    """
    if df is None or len(df) < 1 or not timeline:
        return []
    first_close = float(df["close"].iloc[0])
    if first_close <= 0:
        return [initial_capital] * len(timeline)
    invest = initial_capital * (1.0 - commission_pct)
    shares = invest / (first_close * (1.0 + slippage_pct))
    close_ff = _ffill_to_timeline(df["close"], timeline)
    return [
        initial_capital if np.isnan(close_ff[k]) else shares * float(close_ff[k])
        for k in range(len(timeline))
    ]


def equal_weight_buy_hold_curve(
    symbols: list[SymbolData],
    timeline: list[pd.Timestamp],
    *,
    initial_capital: float,
    commission_pct: float,
    slippage_pct: float,
) -> list[float]:
    """Teng-vazn buy&hold: kapital symbol'lar orasida teng bo'linadi, har biri o'z
    birinchi baridan oxirigacha ushlanadi. Kech boshlangan symbol ulushi naqd turadi;
    delisted symbol oxirgi close'da muzlaydi. Qayta balanslash YO'Q."""
    if not timeline:
        return []
    n = len(symbols)
    if n == 0:
        return [initial_capital] * len(timeline)
    alloc = initial_capital / n
    invest = alloc * (1.0 - commission_pct)

    legs: list[tuple[float, np.ndarray]] = []
    for sym in symbols:
        first_close = float(sym.df["close"].iloc[0])
        shares = invest / (first_close * (1.0 + slippage_pct)) if first_close > 0 else 0.0
        legs.append((shares, _ffill_to_timeline(sym.df["close"], timeline)))

    curve: list[float] = []
    for k in range(len(timeline)):
        total = 0.0
        for shares, close_ff in legs:
            c = close_ff[k]
            total += alloc if np.isnan(c) else shares * float(c)
        curve.append(total)
    return curve


# ======================================================================
# Yig'ish / oldindan hisoblash
# ======================================================================


def _build_timeline(symbols: list[SymbolData]) -> list[pd.Timestamp]:
    """Barcha symbol df.index'lari union (o'sish tartibida) — portfel "soati"."""
    if not symbols:
        return []
    idx = symbols[0].df.index
    for sym in symbols[1:]:
        idx = idx.union(sym.df.index)
    return list(idx)


def _ffill_close_matrix(
    symbols: list[SymbolData], timeline: list[pd.Timestamp]
) -> dict[str, np.ndarray]:
    """{symbol: close'lar timeline'ga ffill qilingan np massiv}."""
    return {sym.symbol: _ffill_to_timeline(sym.df["close"], timeline) for sym in symbols}


def _sizing_per_share_risk(setup: TradeSetup, *, cfg: PortfolioConfig, atr: pd.Series) -> float:
    """Bir aksiya uchun risk: fixed_pct -> entry-stop; atr -> ATR_RISK_MULT*ATR[entry]."""
    if cfg.risk_model == "atr":
        a = atr.iloc[setup.entry_index_pos] if 0 <= setup.entry_index_pos < len(atr) else float("nan")
        if not pd.isna(a):
            return ATR_RISK_MULT * float(a)
    return setup.entry_price - setup.stop_price


def _precompute_candidate(
    sym: SymbolData,
    setup: TradeSetup,
    *,
    cfg: PortfolioConfig,
    atr: pd.Series,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    n: int,
) -> PortfolioCandidate | None:
    """Signal uchun to'liq chiqishni engine funksiyasi bilan oldindan hisoblaydi.

    entry_price - stop_price <= 0 (degenerativ) -> None.
    """
    if setup.entry_price - setup.stop_price <= 0:
        return None

    if cfg.exit_mode == "fixed":
        exit_index_pos, exit_price, exit_reason, min_low, running_high = _simulate_fixed_exit(
            sym.df, setup, closes, highs, lows, n
        )
    else:  # "trailing"
        exit_index_pos, exit_price, exit_reason, min_low, running_high = _simulate_trailing_exit(
            sym.df, setup, atr, closes, highs, lows, n, cfg.trail_atr_mult
        )

    return PortfolioCandidate(
        symbol=sym.symbol,
        setup=setup,
        entry_ts=setup.entry_ts,
        entry_index_pos=setup.entry_index_pos,
        entry_price=setup.entry_price,
        stop_price=setup.stop_price,
        exit_index_pos=exit_index_pos,
        exit_ts=sym.df.index[exit_index_pos],
        exit_price=exit_price,
        exit_reason=exit_reason,
        min_low=min_low,
        running_high=running_high,
        sizing_per_share_risk=_sizing_per_share_risk(setup, cfg=cfg, atr=atr),
    )


def build_candidates(
    symbols: list[SymbolData], *, cfg: PortfolioConfig
) -> tuple[list[PortfolioCandidate], list[SkippedEntry]]:
    """Barcha symbol signal'larini nomzodlarga aylantiradi, (entry_ts, symbol) bo'yicha
    saralaydi. Degenerativ setup'lar alohida `SkippedEntry` ro'yxatida qaytadi."""
    candidates: list[PortfolioCandidate] = []
    degenerate: list[SkippedEntry] = []
    for sym in symbols:
        atr = compute_atr(sym.df, cfg.atr_period)
        closes = sym.df["close"].to_numpy()
        highs = sym.df["high"].to_numpy()
        lows = sym.df["low"].to_numpy()
        n = len(sym.df)
        for setup in sym.signals:
            cand = _precompute_candidate(
                sym, setup, cfg=cfg, atr=atr, closes=closes, highs=highs, lows=lows, n=n
            )
            if cand is None:
                degenerate.append(SkippedEntry(sym.symbol, setup.entry_ts, "degenerate_setup"))
            else:
                candidates.append(cand)
    candidates.sort(key=lambda c: (c.entry_ts, c.symbol))
    return candidates, degenerate


# ======================================================================
# Entry gate / yopish
# ======================================================================


def _plan_entry(
    cand: PortfolioCandidate,
    *,
    equity: float,
    free_cash: float,
    open_risk: float,
    n_open: int,
    symbol_open: bool,
    cfg: PortfolioConfig,
) -> tuple[float, float, float, str]:
    """Kirish rejasi: (shares, planned_risk_dollars, effective_entry, reason).

    reason == "ok" bo'lsagina pozitsiya ochiladi; aks holda o'tkazib yuboriladi.
    Sizing va risk-cap REALIZED `equity` bazasida (MTM emas).
    """
    if equity <= 0:
        return 0.0, 0.0, 0.0, "equity<=0"
    if cfg.one_position_per_symbol and symbol_open:
        return 0.0, 0.0, 0.0, "symbol_already_open"
    if n_open >= cfg.max_concurrent_positions:
        return 0.0, 0.0, 0.0, "max_concurrent"

    entry_price = cand.entry_price
    psr = cand.sizing_per_share_risk
    if psr <= 0:
        return 0.0, 0.0, 0.0, "degenerate_setup"

    shares = (cfg.risk_pct * equity) / psr
    if shares * entry_price > equity:  # equity-cap (engine bilan bir xil, xom entry)
        shares = equity / entry_price
    if shares <= _EPS:
        return 0.0, 0.0, 0.0, "degenerate_setup"

    price_risk = entry_price - cand.stop_price
    planned_risk = shares * price_risk
    if open_risk + planned_risk > cfg.max_portfolio_risk_pct * equity:
        return 0.0, 0.0, 0.0, "portfolio_risk_cap"

    if shares * entry_price > free_cash:  # leverage YO'Q — bo'sh naqdga moslab kichraytiriladi
        shares = free_cash / entry_price if entry_price > 0 else 0.0
        planned_risk = shares * price_risk
        if shares <= _EPS:
            return 0.0, 0.0, 0.0, "insufficient_capital"

    effective_entry = entry_price * (1.0 + cfg.slippage_pct)
    return shares, planned_risk, effective_entry, "ok"


def _realize(pos: OpenPosition, *, cfg: PortfolioConfig) -> tuple[TradeResult, float]:
    """Ochiq pozitsiyani yopadi. Qaytaradi (TradeResult, cash_in) —
    cash_in = shares*effective_exit - commission (naqdga qaytadigan mablag').

    Formulalar engine.py 222-237 bilan AYNAN bir xil.
    """
    effective_exit = pos.exit_price * (1.0 - cfg.slippage_pct)
    gross_pnl = pos.shares * (effective_exit - pos.effective_entry)
    commission = cfg.commission_pct * pos.shares * (pos.effective_entry + effective_exit)
    pnl = gross_pnl - commission

    actual_risk = pos.entry_price - pos.stop_price
    r_multiple = (pos.exit_price - pos.entry_price) / actual_risk
    mae_r = (pos.entry_price - pos.min_low) / actual_risk
    mfe_r = (pos.running_high - pos.entry_price) / actual_risk
    hold_days = (pos.exit_ts - pos.entry_ts).total_seconds() / 86400

    trade = TradeResult(
        entry_ts=pos.entry_ts,
        exit_ts=pos.exit_ts,
        entry_price=pos.entry_price,
        exit_price=pos.exit_price,
        entry_index_pos=pos.entry_index_pos,  # symbol-lokal
        exit_index_pos=pos.exit_index_pos,  # symbol-lokal
        shares=pos.shares,
        exit_reason=pos.exit_reason,
        r_multiple=r_multiple,
        pnl=pnl,
        hold_duration_days=hold_days,
        mae_r=mae_r,
        mfe_r=mfe_r,
    )
    return trade, pos.shares * effective_exit - commission


# ======================================================================
# Yadro
# ======================================================================


def _empty_metrics() -> dict:
    """Bo'sh universe / savdosiz holat uchun neytral metrikalar."""
    return {
        "num_trades": 0,
        "win_rate": 0.0,
        "avg_r_multiple": 0.0,
        "expectancy_r": 0.0,
        "profit_factor": 0.0,
        "avg_hold_days": 0.0,
        "total_return_pct": 0.0,
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "num_skipped": 0,
        "skipped_by_reason": {},
        "avg_concurrent_positions": 0.0,
        "max_concurrent_positions": 0,
    }


def simulate_portfolio(symbols: list[SymbolData], *, cfg: PortfolioConfig) -> PortfolioResult:
    """Butun universe signal'larini yagona kalendar bo'ylab, umumiy kapital bilan simulyatsiya qiladi."""
    timeline = _build_timeline(symbols)
    if not timeline:
        return PortfolioResult(
            trades=[], trade_symbols=[], skipped=[], timeline=[], equity_curve=[],
            concurrency_samples=[], initial_capital=cfg.initial_capital,
            final_capital=cfg.initial_capital, metrics=_empty_metrics(), benchmarks=[],
        )

    close_ffill = _ffill_close_matrix(symbols, timeline)
    candidates, degenerate_skips = build_candidates(symbols, cfg=cfg)
    ts_to_k = {ts: k for k, ts in enumerate(timeline)}
    entries_by_k: dict[int, list[PortfolioCandidate]] = {}
    for cand in candidates:
        entries_by_k.setdefault(ts_to_k[cand.entry_ts], []).append(cand)

    equity = cash = cfg.initial_capital
    open_positions: list[OpenPosition] = []
    open_by_symbol: set[str] = set()
    open_risk = 0.0
    closed_trades: list[TradeResult] = []
    trade_symbols: list[str] = []
    skipped: list[SkippedEntry] = list(degenerate_skips)
    equity_curve: list[float] = []
    concurrency: list[int] = []

    for k, ts in enumerate(timeline):
        # 1-faza: ENTRY (exit'dan OLDIN — bugun chiqadigan pozitsiya hali slot/naqdni band qiladi)
        for cand in entries_by_k.get(k, []):
            shares, planned_risk, eff_entry, reason = _plan_entry(
                cand, equity=equity, free_cash=cash, open_risk=open_risk,
                n_open=len(open_positions), symbol_open=(cand.symbol in open_by_symbol), cfg=cfg,
            )
            if reason != "ok":
                skipped.append(SkippedEntry(cand.symbol, ts, reason))
                continue
            pos = OpenPosition(
                symbol=cand.symbol, entry_ts=cand.entry_ts, exit_ts=cand.exit_ts,
                exit_k=ts_to_k[cand.exit_ts], entry_index_pos=cand.entry_index_pos,
                exit_index_pos=cand.exit_index_pos, entry_price=cand.entry_price,
                stop_price=cand.stop_price, exit_price=cand.exit_price,
                exit_reason=cand.exit_reason, shares=shares, effective_entry=eff_entry,
                planned_risk_dollars=planned_risk, min_low=cand.min_low,
                running_high=cand.running_high,
            )
            open_positions.append(pos)
            open_by_symbol.add(pos.symbol)
            open_risk += planned_risk
            cash -= shares * eff_entry

        # 2-faza: konkurentlik namunasi (kunning "peak heat"i)
        concurrency.append(len(open_positions))

        # 3-faza: EXIT
        for pos in [p for p in open_positions if p.exit_k == k]:
            trade, cash_in = _realize(pos, cfg=cfg)
            closed_trades.append(trade)
            trade_symbols.append(pos.symbol)
            cash += cash_in
            equity += trade.pnl
            open_risk -= pos.planned_risk_dollars
            open_positions.remove(pos)
            open_by_symbol.discard(pos.symbol)

        # 4-faza: mark-to-market equity (exit'lardan KEYIN)
        mtm = cash + sum(p.shares * float(close_ffill[p.symbol][k]) for p in open_positions)
        equity_curve.append(mtm)

    # Himoya: har exit_ts timeline ichida bo'lgani uchun bu bo'sh bo'lishi kerak.
    if open_positions:
        for pos in list(open_positions):
            trade, cash_in = _realize(pos, cfg=cfg)
            closed_trades.append(trade)
            trade_symbols.append(pos.symbol)
            cash += cash_in
            equity += trade.pnl
            open_positions.remove(pos)
        equity_curve[-1] = cash

    ppy = cfg.periods_per_year or _periods_per_year_for(cfg.interval)
    metrics = {
        "num_trades": len(closed_trades),
        "win_rate": win_rate(closed_trades),
        "avg_r_multiple": avg_r_multiple(closed_trades),
        "expectancy_r": expectancy_r(closed_trades),
        "profit_factor": profit_factor(closed_trades),
        "avg_hold_days": avg_hold_days(closed_trades),
        "total_return_pct": curve_return_pct(equity_curve),
        "cagr_pct": cagr_pct(equity_curve, timeline),
        "max_drawdown_pct": max_drawdown_pct(equity_curve),
        "sharpe": sharpe_ratio(equity_curve, periods_per_year=ppy, risk_free_rate=cfg.risk_free_rate),
        "sortino": sortino_ratio(equity_curve, periods_per_year=ppy, risk_free_rate=cfg.risk_free_rate),
        "num_skipped": len(skipped),
        "skipped_by_reason": dict(Counter(s.reason for s in skipped)),
        "avg_concurrent_positions": avg_concurrent_positions(
            concurrency, active_span_only=cfg.active_span_only_concurrency
        ),
        "max_concurrent_positions": max_concurrent_positions(concurrency),
    }

    return PortfolioResult(
        trades=closed_trades,
        trade_symbols=trade_symbols,
        skipped=skipped,
        timeline=timeline,
        equity_curve=equity_curve,
        concurrency_samples=concurrency,
        initial_capital=cfg.initial_capital,
        final_capital=equity,
        metrics=metrics,
        benchmarks=[],
    )


# ======================================================================
# Orkestratsiya
# ======================================================================


def build_symbol_data(
    symbol: str,
    df: pd.DataFrame,
    *,
    start: str | None,
    end: str | None,
    lookback: int = SWING_LOOKBACK,
    min_rr: float = MIN_BREAKOUT_RR,
    require_trend: bool = True,
    min_score: float | None = None,
    atr_period: int = ATR_PERIOD,
) -> SymbolData | None:
    """Xom OHLCV -> oyna kesilib, lookahead'siz breakout+retest signal'lari (+ixtiyoriy ball filtri).

    Yetarsiz data (bo'sh yoki len < 2*lookback+1) -> None.
    """
    df = slice_date_range(df, start, end)
    if df is None or len(df) < 2 * lookback + 1:
        return None
    signals = generate_breakout_retest_signals(
        df, lookback=lookback, min_rr=min_rr, require_trend=require_trend
    )
    if min_score is not None:
        signals = filter_by_score(
            apply_scores(df, signals, lookback=lookback, min_rr=min_rr), min_score
        )
    return SymbolData(symbol=symbol, df=df, signals=signals)


def naive_all_signals_curve(symbols: list[SymbolData], *, cfg: PortfolioConfig) -> list[float]:
    """ESKI usul: universe'ning BARCHA signali (cheklovsiz) entry_ts bo'yicha bittalab
    kompaundlanadi — `equity *= (1 + risk_pct * r_multiple)`, 1.0 dan boshlanadi.

    Bu `scripts/backtest_breakout_retest.py::portfolio_equity_curve` bilan bir xil
    mantiq, lekin butun universe signal to'plami ustida — norealistik "22x" bazasi.
    """
    candidates, _ = build_candidates(symbols, cfg=cfg)
    pairs: list[tuple[pd.Timestamp, float]] = []
    for c in candidates:
        risk = c.entry_price - c.stop_price
        if risk > 0:
            pairs.append((c.entry_ts, (c.exit_price - c.entry_price) / risk))
    pairs.sort(key=lambda p: p[0])

    equity = 1.0
    curve = [equity]
    for _, r in pairs:
        equity *= 1.0 + cfg.risk_pct * r
        curve.append(equity)
    return curve


def run_portfolio(
    symbols: list[SymbolData],
    *,
    cfg: PortfolioConfig,
    benchmark_df: pd.DataFrame | None,
    benchmark_ticker: str,
) -> PortfolioResult:
    """simulate_portfolio + 2 benchmark + ESKI (cap'siz ketma-ket kompaund) egri chizig'i."""
    result = simulate_portfolio(symbols, cfg=cfg)
    timeline = result.timeline
    ppy = cfg.periods_per_year or _periods_per_year_for(cfg.interval)

    ew_curve = equal_weight_buy_hold_curve(
        symbols, timeline, initial_capital=cfg.initial_capital,
        commission_pct=cfg.commission_pct, slippage_pct=cfg.slippage_pct,
    )
    ew = BenchmarkResult(
        name="equal_weight_buy_hold",
        equity_curve=ew_curve,
        metrics=curve_metrics(ew_curve, timeline, periods_per_year=ppy, risk_free_rate=cfg.risk_free_rate)
        if ew_curve else {},
    )

    if benchmark_df is None:
        bh = BenchmarkResult(
            name=f"buy_hold:{benchmark_ticker}", equity_curve=[], metrics={},
            error=f"{benchmark_ticker} yuklanmadi",
        )
    else:
        bh_curve = single_ticker_buy_hold_curve(
            benchmark_df, timeline, initial_capital=cfg.initial_capital,
            commission_pct=cfg.commission_pct, slippage_pct=cfg.slippage_pct,
        )
        bh = BenchmarkResult(
            name=f"buy_hold:{benchmark_ticker}",
            equity_curve=bh_curve,
            metrics=curve_metrics(bh_curve, timeline, periods_per_year=ppy, risk_free_rate=cfg.risk_free_rate)
            if bh_curve else {},
        )

    return dataclasses.replace(
        result, benchmarks=[ew, bh], naive_all_signals_curve=naive_all_signals_curve(symbols, cfg=cfg)
    )
