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
