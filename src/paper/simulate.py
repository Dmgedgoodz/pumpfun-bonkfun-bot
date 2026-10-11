"""Paper fills. Prices are walked locally. Nothing is signed or broadcast."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    """One OHLCV bar. Timestamp is unix seconds."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class PaperFill:
    """A closed paper round trip."""

    entry_price: float
    exit_price: float
    entry_timestamp: int
    exit_timestamp: int
    reason: str

    @property
    def return_fraction(self) -> float:
        return (self.exit_price / self.entry_price) - 1.0


def simulate_position(
    candles: list[Candle],
    take_profit_percentage: float,
    stop_loss_percentage: float,
) -> PaperFill | None:
    """Buy at the first bar's open and sell at +take-profit or -stop-loss.

    The entry signal is assumed to have already fired. When one bar trades
    through both barriers, the stop fills. That is the conservative reading
    of an OHLC bar, which does not say which price printed first. An open
    position at the end of the series returns ``None`` and is not a trade.
    """
    if not candles:
        return None
    entry_price = candles[0].open
    if entry_price <= 0:
        return None
    take_profit_price = entry_price * (1 + take_profit_percentage)
    stop_price = entry_price * (1 - stop_loss_percentage)
    for candle in candles:
        stopped = candle.low <= stop_price
        target_hit = candle.high >= take_profit_price
        if stopped and target_hit:
            return PaperFill(
                entry_price=entry_price,
                exit_price=stop_price,
                entry_timestamp=candles[0].timestamp,
                exit_timestamp=candle.timestamp,
                reason="stop_loss",
            )
        if stopped:
            return PaperFill(
                entry_price=entry_price,
                exit_price=stop_price,
                entry_timestamp=candles[0].timestamp,
                exit_timestamp=candle.timestamp,
                reason="stop_loss",
            )
        if target_hit:
            return PaperFill(
                entry_price=entry_price,
                exit_price=take_profit_price,
                entry_timestamp=candles[0].timestamp,
                exit_timestamp=candle.timestamp,
                reason="take_profit",
            )
    return None
