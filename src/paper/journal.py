"""CSV trade log. Required columns: timestamp, token, entry, exit, pnl."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from paper.simulate import PaperFill

CSV_COLUMNS = (
    "timestamp",
    "token",
    "entry",
    "exit",
    "pnl",
    "mint",
    "return_pct",
    "exit_reason",
    "liquidity_usd",
    "top_holder_share",
)


def iso_utc(timestamp: int) -> str:
    """Format a unix timestamp as an ISO-8601 UTC string."""
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_trade(
    path: Path,
    fill: PaperFill,
    token: str,
    mint: str,
    buy_amount_sol: float,
    liquidity_usd: float,
    holder_share: float,
) -> None:
    """Append one closed trade. ``pnl`` is in SOL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    pnl_sol = buy_amount_sol * fill.return_fraction
    row = {
        "timestamp": iso_utc(fill.exit_timestamp),
        "token": token,
        "entry": f"{fill.entry_price:.12g}",
        "exit": f"{fill.exit_price:.12g}",
        "pnl": f"{pnl_sol:.12g}",
        "mint": mint,
        "return_pct": f"{fill.return_fraction * 100:.6f}",
        "exit_reason": fill.reason,
        "liquidity_usd": f"{liquidity_usd:.2f}",
        "top_holder_share": f"{holder_share:.6f}",
    }
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
