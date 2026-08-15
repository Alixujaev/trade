from __future__ import annotations

import math

import pandas as pd

from core.config import BacktestConfig
from core.models import BacktestResult, Trade
from signals.base import Strategy


def run_backtest(
    df: pd.DataFrame, strategy: Strategy, cfg: BacktestConfig, symbol: str
) -> BacktestResult:
    """Long-only, single-position backtest. Decision from bar t-1 close fills at bar t open (INV-1)."""
    raw_target = strategy.target_position(df)
    effective_target = raw_target.shift(1).fillna(0).astype(int)

    cash = cfg.initial_capital
    shares_held = 0
    entry_price = 0.0
    entry_time = None
    entry_commission = 0.0

    trades: list[Trade] = []
    equity_values: list[float] = []

    for i, (ts, target) in enumerate(effective_target.items()):
        bar_open = df["open"].iloc[i]
        bar_close = df["close"].iloc[i]

        if target == 1 and shares_held == 0:
            fill_price = bar_open * (1 + cfg.slippage_bps / 1e4)
            notional_budget = cash * cfg.position_fraction
            shares = math.floor(
                notional_budget / (fill_price * (1 + cfg.commission_bps / 1e4))
            )
            if shares > 0:
                cost = shares * fill_price
                commission = cost * cfg.commission_bps / 1e4
                cash -= cost + commission
                shares_held = shares
                entry_price = fill_price
                entry_time = ts
                entry_commission = commission

        elif target == 0 and shares_held > 0:
            fill_price = bar_open * (1 - cfg.slippage_bps / 1e4)
            notional = shares_held * fill_price
            commission = notional * cfg.commission_bps / 1e4
            cash += notional - commission

            trades.append(
                Trade(
                    symbol=symbol,
                    entry_time=entry_time,
                    exit_time=ts,
                    entry_price=entry_price,
                    exit_price=fill_price,
                    shares=shares_held,
                    commission=entry_commission + commission,
                )
            )
            shares_held = 0
            entry_price = 0.0
            entry_time = None
            entry_commission = 0.0

        equity_values.append(cash + shares_held * bar_close)

    equity_curve = pd.Series(equity_values, index=df.index, name="equity")
    return BacktestResult(
        symbol=symbol,
        equity_curve=equity_curve,
        trades=trades,
        initial_capital=cfg.initial_capital,
    )


def compute_metrics(result: BacktestResult, periods_per_year: int = 252) -> dict:
    equity = result.equity_curve
    initial = result.initial_capital
    n = len(equity)
    final = equity.iloc[-1] if n else initial

    total_return_pct = (final / initial - 1) * 100 if initial else 0.0

    if n > 0 and initial > 0 and final > 0:
        cagr_pct = ((final / initial) ** (periods_per_year / n) - 1) * 100
    else:
        cagr_pct = 0.0

    returns = equity.pct_change().dropna()
    if len(returns) > 0 and returns.std() > 0:
        sharpe = returns.mean() / returns.std() * (periods_per_year**0.5)
    else:
        sharpe = 0.0

    if n > 0:
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_drawdown_pct = drawdown.min() * 100
    else:
        max_drawdown_pct = 0.0

    trades = result.trades
    num_trades = len(trades)
    net_pnls = [t.net_pnl for t in trades]
    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p <= 0]

    win_rate_pct = (len(wins) / num_trades * 100) if num_trades > 0 else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    expectancy_per_trade = (sum(net_pnls) / num_trades) if num_trades > 0 else 0.0

    return {
        "total_return_pct": total_return_pct,
        "cagr_pct": cagr_pct,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown_pct,
        "num_trades": num_trades,
        "win_rate_pct": win_rate_pct,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy_per_trade": expectancy_per_trade,
    }
