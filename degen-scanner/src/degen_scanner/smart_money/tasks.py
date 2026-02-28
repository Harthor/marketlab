"""Celery task stubs for smart money wallet tracking.

These define the task signatures. The actual Celery app and beat schedule
live in the Django backend (market-research-dashboard). These can be imported
and registered there, or run standalone with a Celery worker pointed at this module.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def poll_tier_a_wallets() -> dict:
    """Poll tier-A wallets (every 5 min).

    1. Load registry, filter tier A
    2. For each wallet: fetch recent txs (Solana RPC or Etherscan)
    3. Parse into ParsedTransactions
    4. Save to storage
    5. Return summary
    """
    from .features import compute_smart_money_features
    from .parser import (
        parse_evm_token_transfers,
        parse_solana_signatures,
    )
    from .registry import WalletRegistry
    from .storage import SmartMoneyStorage
    from .tracker_evm import EVMTracker
    from .tracker_solana import SolanaTracker

    registry = WalletRegistry()
    storage = SmartMoneyStorage()
    sol_tracker = SolanaTracker()
    evm_tracker = EVMTracker()

    tier_a = registry.by_tier("A")
    all_txs = []

    try:
        for wallet in tier_a:
            if wallet.chain == "solana":
                sigs = await sol_tracker.get_recent_signatures(wallet.address, limit=10)
                txs = parse_solana_signatures(sigs, wallet.address, wallet.label)
            elif wallet.is_evm:
                transfers = await evm_tracker.get_token_transfers(
                    wallet.address, wallet.chain, offset=10
                )
                txs = parse_evm_token_transfers(
                    transfers, wallet.address, wallet.label, wallet.chain
                )
            else:
                continue

            all_txs.extend(txs)
            storage.save_transactions(
                wallet.address, wallet.chain,
                [tx.model_dump(mode="json") for tx in txs],
            )
    finally:
        await sol_tracker.close()
        await evm_tracker.close()

    # Compute features
    if all_txs:
        features = compute_smart_money_features(all_txs, tier_a)
        storage.save_features(features)

    return {"wallets_polled": len(tier_a), "transactions": len(all_txs)}


async def poll_tier_b_wallets() -> dict:
    """Poll tier-B wallets (every 15 min). Same logic as tier A but for B wallets."""
    from .features import compute_smart_money_features
    from .parser import (
        parse_evm_token_transfers,
        parse_solana_signatures,
    )
    from .registry import WalletRegistry
    from .storage import SmartMoneyStorage
    from .tracker_evm import EVMTracker
    from .tracker_solana import SolanaTracker

    registry = WalletRegistry()
    storage = SmartMoneyStorage()
    sol_tracker = SolanaTracker()
    evm_tracker = EVMTracker()

    tier_b = registry.by_tier("B")
    all_txs = []

    try:
        for wallet in tier_b:
            if wallet.chain == "solana":
                sigs = await sol_tracker.get_recent_signatures(wallet.address, limit=10)
                txs = parse_solana_signatures(sigs, wallet.address, wallet.label)
            elif wallet.is_evm:
                transfers = await evm_tracker.get_token_transfers(
                    wallet.address, wallet.chain, offset=10
                )
                txs = parse_evm_token_transfers(
                    transfers, wallet.address, wallet.label, wallet.chain
                )
            else:
                continue

            all_txs.extend(txs)
            storage.save_transactions(
                wallet.address, wallet.chain,
                [tx.model_dump(mode="json") for tx in txs],
            )
    finally:
        await sol_tracker.close()
        await evm_tracker.close()

    if all_txs:
        features = compute_smart_money_features(all_txs, tier_b)
        storage.save_features(features)

    return {"wallets_polled": len(tier_b), "transactions": len(all_txs)}


async def poll_tier_c_wallets() -> dict:
    """Poll tier-C wallets (every 1 hour)."""
    from .features import compute_smart_money_features
    from .parser import (
        parse_evm_token_transfers,
        parse_solana_signatures,
    )
    from .registry import WalletRegistry
    from .storage import SmartMoneyStorage
    from .tracker_evm import EVMTracker
    from .tracker_solana import SolanaTracker

    registry = WalletRegistry()
    storage = SmartMoneyStorage()
    sol_tracker = SolanaTracker()
    evm_tracker = EVMTracker()

    tier_c = registry.by_tier("C")
    all_txs = []

    try:
        for wallet in tier_c:
            if wallet.chain == "solana":
                sigs = await sol_tracker.get_recent_signatures(wallet.address, limit=10)
                txs = parse_solana_signatures(sigs, wallet.address, wallet.label)
            elif wallet.is_evm:
                transfers = await evm_tracker.get_token_transfers(
                    wallet.address, wallet.chain, offset=10
                )
                txs = parse_evm_token_transfers(
                    transfers, wallet.address, wallet.label, wallet.chain
                )
            else:
                continue

            all_txs.extend(txs)
            storage.save_transactions(
                wallet.address, wallet.chain,
                [tx.model_dump(mode="json") for tx in txs],
            )
    finally:
        await sol_tracker.close()
        await evm_tracker.close()

    if all_txs:
        features = compute_smart_money_features(all_txs, tier_c)
        storage.save_features(features)

    return {"wallets_polled": len(tier_c), "transactions": len(all_txs)}
