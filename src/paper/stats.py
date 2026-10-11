"""Win rate, average return, and max drawdown for a fixed-stake paper book."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Performance:
    """Summary of closed paper trades."""

    trades: int
    wins: int
    win_rate: float
    average_return: float
    max_drawdown: float
    ending_equity_sol: float


def summarize(
    returns: list[float],
    buy_amount_sol: float,
    starting_bankroll_sol: float,
) -> Performance:
    """Summarize fractional returns.

    Each trade stakes ``buy_amount_sol`` of a bankroll that starts at
    ``starting_bankroll_sol``. Max drawdown is the largest peak-to-trough
    decline of that equity curve, divided by the peak.
    """
    if not returns:
        raise ValueError("no closed trades to summarize")
    if buy_amount_sol <= 0 or starting_bankroll_sol <= 0:
        raise ValueError("stake and bankroll must be positive")
    equity = starting_bankroll_sol
    peak = equity
    max_drawdown = 0.0
    wins = 0
    for fractional_return in returns:
        if fractional_return > 0:
            wins += 1
        equity += buy_amount_sol * fractional_return
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown = (peak - equity) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    count = len(returns)
    return Performance(
        trades=count,
        wins=wins,
        win_rate=wins / count,
        average_return=sum(returns) / count,
        max_drawdown=max_drawdown,
        ending_equity_sol=equity,
    )
