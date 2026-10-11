"""Refuse anything that could move funds or use a denied wallet."""

from __future__ import annotations

import os
from typing import Any


class PaperSafetyError(RuntimeError):
    """Raised when a paper run is asked to do something live."""


def refuse_send(*_args: object, **_kwargs: object) -> None:
    """Stand-in for every transaction submit path. Always raises."""
    raise PaperSafetyError("paper mode does not send transactions")


def assert_paper_config(config: dict[str, Any]) -> str:
    """Validate the public wallet identity and return its pubkey.

    The private key in ``.env`` is intentionally ignored. A Fomo app wallet
    is rejected when its pubkey is listed in ``denied_pubkeys`` or in the
    ``FOMO_WALLET_PUBKEY`` environment variable.
    """
    mode = str(config.get("mode", "")).lower()
    if mode != "paper":
        raise PaperSafetyError("refusing to run because mode is not paper")
    if config.get("private_key") or config.get("send_transactions"):
        raise PaperSafetyError("paper config must not carry a key or a send flag")
    pubkey = str(config.get("wallet_pubkey", "")).strip()
    if not pubkey:
        raise PaperSafetyError("paper config is missing wallet_pubkey")
    denied = {str(item).strip() for item in config.get("denied_pubkeys") or []}
    fomo_pubkey = os.environ.get("FOMO_WALLET_PUBKEY", "").strip()
    if fomo_pubkey:
        denied.add(fomo_pubkey)
    if pubkey in denied:
        raise PaperSafetyError("refusing denied wallet (Fomo app wallets are denied)")
    return pubkey
