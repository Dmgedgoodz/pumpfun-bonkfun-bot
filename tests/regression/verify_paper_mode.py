"""Offline checks for the paper bot. No network and no funds.

Confirms the liquidity and holder filters, the +50% / -20% exits, the CSV
columns, the equity-curve stats, and the refusal to send or to use a denied
wallet.

Usage:
    python tests/regression/verify_paper_mode.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paper.config import load_paper_config  # noqa: E402
from paper.filters import (  # noqa: E402
    passes_entry_filters,
    pool_is_candidate,
    top_holder_share,
)
from paper.guard import PaperSafetyError, assert_paper_config, refuse_send  # noqa: E402
from paper.journal import CSV_COLUMNS, append_trade  # noqa: E402
from paper.simulate import Candle, simulate_position  # noqa: E402
from paper.stats import summarize  # noqa: E402


def _bar(timestamp: int, open_: float, high: float, low: float) -> Candle:
    return Candle(timestamp=timestamp, open=open_, high=high, low=low, close=open_)


def check_filters() -> None:
    assert passes_entry_filters(10000, 0.19, 10000, 0.20) is False
    assert passes_entry_filters(10000.01, 0.199, 10000, 0.20) is True
    assert passes_entry_filters(50000, 0.20, 10000, 0.20) is False
    assert pool_is_candidate("pump-fun", "So11111111111111111111111111111111111111112", 10001, 10000)
    assert not pool_is_candidate(
        "raydium", "So11111111111111111111111111111111111111112", 50000, 10000
    )
    holders = [
        {"address": "curve", "amount": 800_000_000},
        {"address": "wallet", "amount": 150_000_000},
        {"address": "other", "amount": 10_000_000},
    ]
    share = top_holder_share(holders, 1_000_000_000, {"curve"})
    assert share == 0.15
    assert top_holder_share(holders, 1_000_000_000, set()) == 0.8


def check_exits() -> None:
    take_profit = simulate_position(
        [
            _bar(1, 1.0, 1.1, 0.95),
            _bar(2, 1.1, 1.6, 1.05),
        ],
        0.50,
        0.20,
    )
    assert take_profit is not None
    assert take_profit.reason == "take_profit"
    assert take_profit.exit_price == 1.5
    assert take_profit.return_fraction == 0.5

    stop = simulate_position(
        [
            _bar(1, 2.0, 2.1, 1.9),
            _bar(2, 1.9, 1.95, 1.5),
        ],
        0.50,
        0.20,
    )
    assert stop is not None
    assert stop.reason == "stop_loss"
    assert stop.exit_price == 1.6
    assert abs(stop.return_fraction - (-0.20)) < 1e-12

    both = simulate_position([_bar(1, 1.0, 1.7, 0.7)], 0.50, 0.20)
    assert both is not None
    assert both.reason == "stop_loss"

    assert simulate_position([_bar(1, 1.0, 1.2, 0.9)], 0.50, 0.20) is None


def check_stats_and_csv(tmp: Path) -> None:
    performance = summarize([0.5, -0.2, -0.2], 0.05, 10)
    assert performance.trades == 3
    assert performance.wins == 1
    assert abs(performance.win_rate - (1 / 3)) < 1e-12
    assert abs(performance.average_return - (0.5 - 0.2 - 0.2) / 3) < 1e-12
    # Equity: 10 -> 10.025 -> 10.015 -> 10.005. Peak 10.025.
    expected_dd = (10.025 - 10.005) / 10.025
    assert abs(performance.max_drawdown - expected_dd) < 1e-12

    deeper = summarize([-0.2, -0.2, 0.5], 0.05, 10)
    assert abs(deeper.max_drawdown - 0.002) < 1e-12

    from paper.simulate import PaperFill

    fill = PaperFill(1.0, 1.5, 1_700_000_000, 1_700_000_060, "take_profit")
    csv_path = tmp / "trades.csv"
    append_trade(csv_path, fill, "TEST", "mint", 0.05, 12000, 0.05)
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",")[:5] == list(CSV_COLUMNS[:5])
    assert "timestamp,token,entry,exit,pnl" in header


def check_guard() -> None:
    config = load_paper_config(PROJECT_ROOT / "config" / "paper-minimal.yaml")
    assert config["filters"]["min_liquidity_usd"] == 10000
    assert config["filters"]["max_top_holder_share"] == 0.20
    assert config["trade"]["take_profit_percentage"] == 0.50
    assert config["trade"]["stop_loss_percentage"] == 0.20
    assert config["mode"] == "paper"
    pubkey = assert_paper_config(config)
    assert pubkey == "8oqsV9kYxxwputd1cDgfHEtfUELWRYmwt6HxhxNaQXoX"
    try:
        refuse_send()
    except PaperSafetyError:
        pass
    else:
        raise AssertionError("refuse_send returned")
    denied = dict(config)
    denied["denied_pubkeys"] = [pubkey]
    try:
        assert_paper_config(denied)
    except PaperSafetyError:
        pass
    else:
        raise AssertionError("denied wallet was accepted")
    live = dict(config)
    live["private_key"] = "not-a-real-key"
    try:
        assert_paper_config(live)
    except PaperSafetyError:
        pass
    else:
        raise AssertionError("private key config was accepted")


def main() -> None:
    check_filters()
    check_exits()
    check_stats_and_csv(PROJECT_ROOT / "data" / "_paper_test")
    check_guard()
    test_dir = PROJECT_ROOT / "data" / "_paper_test"
    if test_dir.exists():
        for child in test_dir.iterdir():
            child.unlink()
        test_dir.rmdir()
    print("paper mode checks passed")


if __name__ == "__main__":
    main()
