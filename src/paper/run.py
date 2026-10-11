"""Run the minimal Pump.fun bot in paper mode.

Paper mode simulates entries and exits and writes a CSV. It does not import
the live trader, does not read ``SOLANA_PRIVATE_KEY`` or
``PAPER_WALLET_PRIVATE_KEY``, and does not build or send transactions.

The wallet pubkey in the config is a keypair created for this repo. It is
not a Fomo app wallet. The matching secret stays in the gitignored ``.env``
and is unused, because paper fills never need a signature.

Replay method, and its limits:

- Universe: recently listed Pump.fun pools, then PumpSwap pools, from the
  public GeckoTerminal API.
- Entry signal: liquidity (reserve USD) above the configured floor and
  top-holder share under the configured cap. Both figures are the latest
  snapshot, not a point-in-time reading at the first candle.
- Fill: buy the first 5-minute candle's open. Sell at +50% or -20%. If one
  candle trades through both prices, the stop is filled.
- Trades that never reach either barrier are left open and are not counted.
- No fees and no slippage. With those rules, every closed return is exactly
  +50% or -20%, so the average return is determined by the win rate. Max
  drawdown still depends on the order of wins and losses.

Usage, from the repository root:

    python src/paper/run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paper.config import load_paper_config  # noqa: E402
from paper.guard import assert_paper_config  # noqa: E402
from paper.replay import replay_until  # noqa: E402


def main() -> None:
    """Load the paper config, refuse live sending, and replay until the target."""
    config_path = PROJECT_ROOT / "config" / "paper-minimal.yaml"
    config = load_paper_config(config_path)
    pubkey = assert_paper_config(config)
    csv_path = PROJECT_ROOT / str(config["paper"]["csv_path"])
    _closed, performance = replay_until(config, csv_path)
    summary = {
        "mode": "paper",
        "wallet_pubkey": pubkey,
        "transactions_sent": 0,
        "closed_trades": performance.trades,
        "wins": performance.wins,
        "win_rate": performance.win_rate,
        "average_return": performance.average_return,
        "max_drawdown": performance.max_drawdown,
        "ending_equity_sol": performance.ending_equity_sol,
        "csv": str(csv_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    summary_path = csv_path.with_name("paper_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
