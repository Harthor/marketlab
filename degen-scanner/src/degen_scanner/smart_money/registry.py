"""Wallet registry — loads and provides access to tracked wallets."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

Tier = Literal["A", "B", "C"]

# Polling intervals per tier (seconds)
TIER_POLL_INTERVALS: dict[str, int] = {
    "A": 300,     # 5 min
    "B": 900,     # 15 min
    "C": 3600,    # 1 hour
}


@dataclass(frozen=True)
class TrackedWallet:
    """A single tracked smart-money wallet."""

    address: str
    chain: str
    label: str
    tier: Tier
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def poll_interval_seconds(self) -> int:
        return TIER_POLL_INTERVALS.get(self.tier, 3600)

    @property
    def is_evm(self) -> bool:
        return self.chain in ("base", "bsc", "ethereum", "arbitrum", "polygon")


class WalletRegistry:
    """Load and query the wallet registry from YAML."""

    def __init__(self, config_path: Path | None = None):
        if config_path is None:
            config_path = (
                Path(__file__).resolve().parent.parent.parent.parent
                / "config" / "wallet_registry.yaml"
            )
        self._path = config_path
        self._wallets: list[TrackedWallet] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("Wallet registry not found at %s", self._path)
            return
        with open(self._path) as f:
            data = yaml.safe_load(f)
        for w in data.get("wallets", []):
            self._wallets.append(
                TrackedWallet(
                    address=w["address"],
                    chain=w["chain"],
                    label=w.get("label", ""),
                    tier=w.get("tier", "C"),
                    tags=w.get("tags", []),
                    notes=w.get("notes", ""),
                )
            )
        logger.info("Loaded %d wallets from registry", len(self._wallets))

    @property
    def wallets(self) -> list[TrackedWallet]:
        return list(self._wallets)

    def by_chain(self, chain: str) -> list[TrackedWallet]:
        return [w for w in self._wallets if w.chain == chain]

    def by_tier(self, tier: Tier) -> list[TrackedWallet]:
        return [w for w in self._wallets if w.tier == tier]

    def by_tag(self, tag: str) -> list[TrackedWallet]:
        return [w for w in self._wallets if tag in w.tags]

    def get(self, address: str) -> TrackedWallet | None:
        addr_lower = address.lower()
        for w in self._wallets:
            if w.address.lower() == addr_lower:
                return w
        return None
