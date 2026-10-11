"""Replay public Pump.fun pool history into paper fills.

No RPC transaction is built. Market data comes from GeckoTerminal and the
public Pump.fun holder endpoint. Liquidity and holder share are the latest
snapshot; the price path is the pool's 5-minute candles after that pool
appeared. See the module docstring in ``run`` for the bias this creates.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paper.filters import WSOL_MINT, pool_is_candidate, top_holder_share
from paper.journal import append_trade
from paper.simulate import Candle, PaperFill, simulate_position
from paper.stats import Performance, summarize

GECKO = "https://api.geckoterminal.com/api/v2"
PUMP = "https://frontend-api-v3.pump.fun"
GECKO_INTERVAL_SECONDS = 2.1
PUMP_INTERVAL_SECONDS = 0.25


@dataclass
class ClosedTrade:
    """One logged paper trade plus the return used for the equity curve."""

    token: str
    mint: str
    fill: PaperFill
    liquidity_usd: float
    holder_share: float


class MarketClient:
    """Polite JSON client. GeckoTerminal's public cap is about 30 calls/minute."""

    def __init__(self) -> None:
        self._next_gecko = 0.0
        self._next_pump = 0.0

    def get_json(self, url: str) -> Any:
        pause_until = self._next_gecko if "geckoterminal" in url else self._next_pump
        delay = pause_until - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json;version=20230302",
                "User-Agent": "pumpfun-paper-bot",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(5)
                return self.get_json(url)
            raise
        finally:
            now = time.monotonic()
            if "geckoterminal" in url:
                self._next_gecko = now + GECKO_INTERVAL_SECONDS
            else:
                self._next_pump = now + PUMP_INTERVAL_SECONDS
        return payload


def _mint_from_relationship(pool: dict[str, Any], side: str) -> str:
    token_id = pool["relationships"][side]["data"]["id"]
    prefix = "solana_"
    if token_id.startswith(prefix):
        return token_id[len(prefix) :]
    return token_id


def _symbol(pool: dict[str, Any]) -> str:
    name = str(pool["attributes"].get("name") or "")
    return name.split(" / ", 1)[0].strip() or "UNKNOWN"


def _supply_ui(pool: dict[str, Any]) -> float | None:
    attributes = pool["attributes"]
    try:
        fdv = float(attributes.get("fdv_usd") or 0)
        price = float(attributes.get("base_token_price_usd") or 0)
    except (TypeError, ValueError):
        return None
    if fdv <= 0 or price <= 0:
        return None
    supply = fdv / price
    if supply < 1_000_000 or supply > 1_000_000_000_000:
        return None
    return supply


def _candles_from_ohlcv(payload: dict[str, Any]) -> list[Candle]:
    rows = payload.get("data", {}).get("attributes", {}).get("ohlcv_list") or []
    candles = [
        Candle(
            timestamp=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
        )
        for row in rows
        if len(row) >= 5
    ]
    candles.sort(key=lambda candle: candle.timestamp)
    return candles


def _holder_rows(client: MarketClient, mint: str) -> list[dict[str, Any]] | None:
    try:
        payload = client.get_json(f"{PUMP}/coins/top-holders/{mint}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    holders = payload.get("topHolders") if isinstance(payload, dict) else None
    if not isinstance(holders, list) or not holders:
        return None
    return holders


def replay_until(
    config: dict[str, Any],
    csv_path: Path,
    client: MarketClient | None = None,
) -> tuple[list[ClosedTrade], Performance]:
    """Scan new Pump.fun pools, then PumpSwap pools, until enough trades close."""
    market = client or MarketClient()
    filters = config["filters"]
    trade = config["trade"]
    paper = config["paper"]
    min_liquidity = float(filters["min_liquidity_usd"])
    max_share = float(filters["max_top_holder_share"])
    take_profit = float(trade["take_profit_percentage"])
    stop_loss = float(trade["stop_loss_percentage"])
    buy_amount = float(trade["buy_amount_sol"])
    target = int(paper["target_closed_trades"])
    max_pages = int(paper.get("max_pool_pages", 8))
    candle_minutes = int(paper.get("candle_minutes", 5))
    if csv_path.exists():
        csv_path.unlink()

    closed: list[ClosedTrade] = []
    seen: set[str] = set()
    sources = [("new_pools", f"{GECKO}/networks/solana/new_pools?page={{page}}")]
    sources.append(
        (
            "pumpswap",
            f"{GECKO}/networks/solana/dexes/pumpswap/pools?page={{page}}",
        )
    )
    for source_name, url_template in sources:
        if len(closed) >= target:
            break
        for page in range(1, max_pages + 1):
            if len(closed) >= target:
                break
            print(f"{source_name} page {page} closed={len(closed)}", flush=True)
            try:
                listing = market.get_json(url_template.format(page=page))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue
            pools = listing.get("data") if isinstance(listing, dict) else None
            if not pools:
                break
            for pool in pools:
                if len(closed) >= target:
                    break
                trade_row = _consider_pool(
                    pool,
                    market,
                    seen,
                    min_liquidity,
                    max_share,
                    take_profit,
                    stop_loss,
                    candle_minutes,
                    source_name,
                )
                if trade_row is None:
                    continue
                append_trade(
                    csv_path,
                    trade_row.fill,
                    trade_row.token,
                    trade_row.mint,
                    buy_amount,
                    trade_row.liquidity_usd,
                    trade_row.holder_share,
                )
                closed.append(trade_row)
                print(
                    f"closed {len(closed)}/{target} {trade_row.token} "
                    f"{trade_row.fill.reason} {trade_row.fill.return_fraction:+.0%}",
                    flush=True,
                )
    if len(closed) < target:
        raise RuntimeError(
            f"paper replay closed {len(closed)} of {target} trades before data ran out"
        )
    performance = summarize(
        [row.fill.return_fraction for row in closed],
        buy_amount,
        float(paper["starting_bankroll_sol"]),
    )
    return closed, performance


def _consider_pool(
    pool: dict[str, Any],
    market: MarketClient,
    seen: set[str],
    min_liquidity: float,
    max_share: float,
    take_profit: float,
    stop_loss: float,
    candle_minutes: int,
    source_name: str,
) -> ClosedTrade | None:
    attributes = pool.get("attributes") or {}
    try:
        liquidity = float(attributes.get("reserve_in_usd") or 0)
    except (TypeError, ValueError):
        return None
    dex_id = str(
        (pool.get("relationships") or {}).get("dex", {}).get("data", {}).get("id", "")
    )
    if source_name == "pumpswap":
        dex_id = "pumpswap"
    try:
        quote_mint = _mint_from_relationship(pool, "quote_token")
        mint = _mint_from_relationship(pool, "base_token")
    except (KeyError, TypeError):
        return None
    if mint in seen or not pool_is_candidate(dex_id, quote_mint, liquidity, min_liquidity):
        return None
    if quote_mint != WSOL_MINT:
        return None
    seen.add(mint)
    supply = _supply_ui(pool)
    if supply is None:
        return None
    holders = _holder_rows(market, mint)
    if holders is None:
        return None
    pool_address = str(attributes.get("address") or "")
    share = top_holder_share(holders, supply, {pool_address})
    if share is None or share >= max_share:
        return None
    pool_address = pool_address or str(attributes.get("address") or "")
    if not pool_address:
        return None
    ohlcv_url = (
        f"{GECKO}/networks/solana/pools/{pool_address}/ohlcv/minute"
        f"?aggregate={candle_minutes}&limit=1000&currency=usd"
    )
    try:
        payload = market.get_json(ohlcv_url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    fill = simulate_position(_candles_from_ohlcv(payload), take_profit, stop_loss)
    if fill is None:
        return None
    symbol = _symbol(pool)
    meta_symbol = (
        payload.get("meta", {}).get("base", {}).get("symbol") if isinstance(payload, dict) else None
    )
    if isinstance(meta_symbol, str) and meta_symbol.strip():
        symbol = meta_symbol.strip()
    return ClosedTrade(
        token=symbol,
        mint=mint,
        fill=fill,
        liquidity_usd=liquidity,
        holder_share=share,
    )
