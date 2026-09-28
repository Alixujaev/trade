"""Backtest natijalaridan o'qiladigan metrikalar hisoblash.

Har bir funksiya mustaqil, kichik va sinaladigan — TradeResult ro'yxati (yoki
tegishli boshqa oddiy ma'lumot) qabul qiladi, bitta son qaytaradi.
"""

from __future__ import annotations

import pandas as pd

from backtest.types import TradeResult


def win_rate(trades: list[TradeResult]) -> float:
    """G'olib savdolar ulushi (0..1)."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.pnl > 0)
    return wins / len(trades)


def avg_r_multiple(trades: list[TradeResult]) -> float:
    """O'rtacha R-multiple (barcha savdolar bo'yicha)."""
    if not trades:
        return 0.0
    return sum(t.r_multiple for t in trades) / len(trades)


def expectancy_r(trades: list[TradeResult]) -> float:
    """Kutilayotgan natija (R'da): win_rate*o'rtacha_g'olib_R + loss_rate*o'rtacha_yutqazgan_R.

    Matematik jihatdan bu `avg_r_multiple` bilan AYNAN bir xil (guruhlar bo'yicha
    dekompozitsiya qilingan o'rtacha) — bu yerda alohida, tushunarli formula bilan
    hisoblangan, testda ikkalasi tengligi tasdiqlanadi (regressiya himoyasi sifatida).
    """
    if not trades:
        return 0.0
    wins = [t.r_multiple for t in trades if t.pnl > 0]
    losses = [t.r_multiple for t in trades if t.pnl <= 0]
    n = len(trades)
    win_component = (len(wins) / n) * (sum(wins) / len(wins)) if wins else 0.0
    loss_component = (len(losses) / n) * (sum(losses) / len(losses)) if losses else 0.0
    return win_component + loss_component


def profit_factor(trades: list[TradeResult]) -> float:
    """Yalpi foyda / yalpi zarar. Zarar yo'q va foyda bor bo'lsa cheksiz (inf)."""
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def max_drawdown_pct(equity_curve: list[float]) -> float:
    """Eng katta pasayish (%) — FAQAT yopilgan savdolardan keyingi capital nuqtalari
    bo'yicha ("yopilgan-savdo" drawdown). Bar-by-bar mark-to-market EMAS — ochiq
    pozitsiya davomidagi vaqtinchalik (intra-trade) pasayishlar bu yerda ko'rinmaydi
    (buning uchun har savdoning mae_r maydoniga qarang).
    """
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd * 100


def avg_hold_days(trades: list[TradeResult]) -> float:
    """O'rtacha ushlab turish muddati (kun)."""
    if not trades:
        return 0.0
    return sum(t.hold_duration_days for t in trades) / len(trades)


def buy_and_hold_return_pct(df: pd.DataFrame) -> float:
    """Butun davr bo'yicha shu symbol'ni ushlab turgan bo'lsang qancha bo'lardi (%)."""
    if len(df) < 2:
        return 0.0
    start = float(df["close"].iloc[0])
    end = float(df["close"].iloc[-1])
    if start == 0:
        return 0.0
    return (end - start) / start * 100


def compute_day_metrics(
    trades: list[Any],
    buy_and_hold_return: float = 0.0,
) -> dict[str, Any]:
    """Intraday DayBacktestTrade ro'yxatidan qat'iy statistik metrikalarni hisoblaydi."""
    import numpy as np

    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate": 0.0,
            "total_return_pct": 0.0,
            "average_return_pct": 0.0,
            "median_return_pct": 0.0,
            "average_R": None,
            "median_R": None,
            "total_R": None,
            "R_std": None,
            "max_drawdown_pct": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "buy_and_hold_return_pct": buy_and_hold_return,
        }

    wins = [t for t in trades if t.net_return > 0.0]
    losses = [t for t in trades if t.net_return < 0.0]
    evens = [t for t in trades if t.net_return == 0.0]

    win_rate_val = len(wins) / total_trades
    net_returns = [t.net_return * 100.0 for t in trades]

    # Geometrik yig'ma daromad: prod(1 + r) - 1
    compounded = 1.0
    for r in trades:
        compounded *= (1.0 + r.net_return)
    total_return_pct = (compounded - 1.0) * 100.0

    avg_return_pct = float(np.mean(net_returns))
    med_return_pct = float(np.median(net_returns))

    # R metrics
    r_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
    if r_vals:
        avg_r = float(np.mean(r_vals))
        med_r = float(np.median(r_vals))
        tot_r = float(np.sum(r_vals))
        std_r = float(np.std(r_vals)) if len(r_vals) > 1 else 0.0
    else:
        avg_r = None
        med_r = None
        tot_r = None
        std_r = None

    # Max Drawdown
    equity_curve = [100.0]
    curr_eq = 100.0
    for r in trades:
        curr_eq *= (1.0 + r.net_return)
        equity_curve.append(curr_eq)

    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        peak = max(peak, val)
        if peak > 0:
            max_dd = max(max_dd, (peak - val) / peak)
    max_dd_pct = max_dd * 100.0

    gross_gains = sum(t.net_return for t in wins)
    gross_losses = -sum(t.net_return for t in losses)

    if gross_losses == 0:
        pf = float("inf") if gross_gains > 0 else 0.0
    else:
        pf = gross_gains / gross_losses

    avg_win = float(np.mean([t.net_return for t in wins])) if wins else 0.0
    avg_loss = float(np.mean([abs(t.net_return) for t in losses])) if losses else 0.0
    loss_rate = len(losses) / total_trades
    expectancy = (win_rate_val * avg_win) - (loss_rate * avg_loss)

    return {
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": len(evens),
        "win_rate": win_rate_val,
        "total_return_pct": total_return_pct,
        "average_return_pct": avg_return_pct,
        "median_return_pct": med_return_pct,
        "average_R": avg_r,
        "median_R": med_r,
        "total_R": tot_r,
        "R_std": std_r,
        "max_drawdown_pct": max_dd_pct,
        "gross_profit": gross_gains * 100.0,
        "gross_loss": gross_losses * 100.0,
        "profit_factor": pf,
        "expectancy": expectancy * 100.0,
        "buy_and_hold_return_pct": buy_and_hold_return,
    }

