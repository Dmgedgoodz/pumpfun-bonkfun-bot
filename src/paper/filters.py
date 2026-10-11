"""Entry filters for the paper bot.

Liquidity is the pool's quote-side reserve in USD (GeckoTerminal
``reserve_in_usd``, or real SOL reserves times the SOL price on a bonding
curve). Top-holder share is the largest wallet balance divided by supply,
after known curve and pool accounts are removed.
"""

from __future__ import annotations

from typing import Any

PUMP_DEX_IDS = frozenset({"pump-fun", "pumpswap"})
WSOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_DECIMALS = 6


def passes_entry_filters(
    liquidity_usd: float,
    top_holder_share: float,
    min_liquidity_usd: float,
    max_top_holder_share: float,
) -> bool:
    """Return whether a launch is allowed to open a paper position."""
    return (
        liquidity_usd > min_liquidity_usd and top_holder_share < max_top_holder_share
    )


def pool_is_candidate(
    dex_id: str,
    quote_mint: str,
    liquidity_usd: float,
    min_liquidity_usd: float,
) -> bool:
    """Return whether a pool is a Pump.fun market above the liquidity floor."""
    return (
        dex_id in PUMP_DEX_IDS
        and quote_mint == WSOL_MINT
        and liquidity_usd > min_liquidity_usd
    )


def top_holder_share(
    holders: list[dict[str, Any]],
    supply_ui: float,
    excluded_addresses: set[str],
) -> float | None:
    """Largest holder as a fraction of supply.

    Holder amounts from the Pump.fun API are UI tokens. If a row is larger
    than supply it is treated as raw base units (6 decimals) once. The result
    is ``None`` when the figure is still not a plausible share, so the caller
    skips the coin instead of guessing.
    """
    if supply_ui <= 0:
        return None
    largest = 0.0
    saw_holder = False
    for holder in holders:
        address = str(holder.get("address", ""))
        if address in excluded_addresses:
            continue
        try:
            amount = float(holder.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount > supply_ui * 1.05:
            amount = amount / 10**TOKEN_DECIMALS
        if amount > supply_ui * 1.05 or amount < 0:
            return None
        saw_holder = True
        if amount > largest:
            largest = amount
    if not saw_holder:
        return None
    return largest / supply_ui
