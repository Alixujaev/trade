"""Backtest natijalari uchun data modellari."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TradeResult:
    """Bitta simulyatsiya qilingan savdo natijasi."""

    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    entry_index_pos: int
    exit_index_pos: int
    shares: float
    exit_reason: str  # "stop" | "target" | "trailing_stop" | "end_of_data"
    r_multiple: float  # faqat narxlardan hisoblangan — shares/komissiya/slippage ta'sir qilmaydi
    pnl: float  # dollar — shares/komissiya/slippage hisobga olingan
    hold_duration_days: float
    mae_r: float  # ushlab turish davomidagi eng yomon (worst) unrealized R
    mfe_r: float  # ushlab turish davomidagi eng yaxshi (best) unrealized R — "give-back"ni ko'rish uchun
    # (r_multiple doim ORIGINAL stop masofasidan hisoblanadi, shuning uchun +5R'ga
    # ko'tarilib +0.3R'da yopilgan savdo bilan boshidan +0.3R'da yopilgan savdo bir
    # xil r_multiple ko'rsatadi — mfe_r shu farqni ko'rinadigan qiladi)


@dataclass(frozen=True)
class BacktestResult:
    """Butun backtest simulyatsiyasi natijasi."""

    trades: list[TradeResult]
    initial_capital: float
    final_capital: float
    metrics: dict  # backtest.metrics funksiyalari natijasi (win_rate, avg_r, va h.k.)
