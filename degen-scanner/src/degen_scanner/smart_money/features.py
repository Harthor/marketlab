"""Smart money feature computation — consensus, accumulation, first-buy signals."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .parser import ParsedTransaction
from .registry import TrackedWallet

logger = logging.getLogger(__name__)


def compute_smart_money_features(
    transactions: list[ParsedTransaction],
    wallets: list[TrackedWallet],
    lookback_hours: int = 72,
) -> dict[str, dict[str, Any]]:
    """Compute per-asset smart money features from recent transactions.

    Returns dict keyed by asset_uid with feature dict:
        - consensus_score: 0-100, how many tracked wallets agree on direction
        - consensus_direction: "accumulate" | "distribute" | "neutral"
        - accumulation_net_usd: net USD flow (positive = buying)
        - unique_wallets_buying: count of distinct wallets buying
        - unique_wallets_selling: count of distinct wallets selling
        - first_buy_detected: True if any wallet's first-ever buy of this token
        - tier_a_active: True if any tier-A wallet is involved
        - whale_buy_count: count of buys from wallets tagged "whale"
        - total_buy_volume: total tokens bought
        - total_sell_volume: total tokens sold
        - latest_activity: ISO timestamp of most recent tx
    """
    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)

    # Build wallet lookup
    wallet_map: dict[str, TrackedWallet] = {}
    for w in wallets:
        wallet_map[w.address.lower()] = w

    # Group recent transactions by asset
    asset_txs: dict[str, list[ParsedTransaction]] = defaultdict(list)
    for tx in transactions:
        if tx.block_time < cutoff:
            continue
        uid = tx.asset_uid
        if uid:
            asset_txs[uid].append(tx)

    features: dict[str, dict[str, Any]] = {}

    for asset_uid, txs in asset_txs.items():
        buyers: set[str] = set()
        sellers: set[str] = set()
        tier_a = False
        whale_buys = 0
        total_buy = 0.0
        total_sell = 0.0
        buy_usd = 0.0
        sell_usd = 0.0
        latest = txs[0].block_time

        for tx in txs:
            wallet = wallet_map.get(tx.wallet_address.lower())
            if tx.block_time > latest:
                latest = tx.block_time

            if tx.direction in ("buy", "transfer_in"):
                buyers.add(tx.wallet_address.lower())
                total_buy += tx.amount_tokens
                buy_usd += tx.amount_usd or 0.0
                if wallet and wallet.tier == "A":
                    tier_a = True
                if wallet and "whale" in wallet.tags:
                    whale_buys += 1
            elif tx.direction in ("sell", "transfer_out"):
                sellers.add(tx.wallet_address.lower())
                total_sell += tx.amount_tokens
                sell_usd += tx.amount_usd or 0.0

        n_buying = len(buyers)
        n_selling = len(sellers)
        n_total = len(buyers | sellers)

        # Consensus score: agreement among tracked wallets
        if n_total == 0:
            consensus_score = 0.0
            consensus_dir = "neutral"
        else:
            buy_ratio = n_buying / n_total
            if buy_ratio >= 0.7:
                consensus_dir = "accumulate"
                wr = n_buying / max(len(wallets), 1)
                consensus_score = min(100.0, buy_ratio * 100 * wr * 10)
            elif buy_ratio <= 0.3:
                consensus_dir = "distribute"
                wr = n_selling / max(len(wallets), 1)
                consensus_score = min(100.0, (1 - buy_ratio) * 100 * wr * 10)
            else:
                consensus_dir = "neutral"
                consensus_score = 0.0

        consensus_score = min(100.0, max(0.0, consensus_score))

        features[asset_uid] = {
            "consensus_score": round(consensus_score, 1),
            "consensus_direction": consensus_dir,
            "accumulation_net_usd": round(buy_usd - sell_usd, 2),
            "unique_wallets_buying": n_buying,
            "unique_wallets_selling": n_selling,
            "first_buy_detected": False,  # requires historical context
            "tier_a_active": tier_a,
            "whale_buy_count": whale_buys,
            "total_buy_volume": round(total_buy, 6),
            "total_sell_volume": round(total_sell, 6),
            "latest_activity": latest.isoformat(),
        }

    return features


def detect_first_buys(
    current_transactions: list[ParsedTransaction],
    historical_assets_by_wallet: dict[str, set[str]],
) -> set[str]:
    """Detect asset_uids where a tracked wallet is buying for the first time.

    Args:
        current_transactions: recent transactions to check
        historical_assets_by_wallet: wallet_address -> set of asset_uids previously traded

    Returns:
        Set of asset_uids with first-buy detections
    """
    first_buys: set[str] = set()
    for tx in current_transactions:
        if tx.direction not in ("buy", "transfer_in"):
            continue
        uid = tx.asset_uid
        if not uid:
            continue
        wallet_addr = tx.wallet_address.lower()
        history = historical_assets_by_wallet.get(wallet_addr, set())
        if uid not in history:
            first_buys.add(uid)
            logger.info(
                "First buy detected: wallet=%s asset=%s",
                tx.wallet_label or wallet_addr[:8],
                uid,
            )
    return first_buys


def compute_accumulation_signal(
    features: dict[str, dict[str, Any]],
    min_wallets: int = 2,
    min_consensus: float = 50.0,
) -> list[dict[str, Any]]:
    """Filter features to find strong accumulation signals.

    Returns list of assets with strong buy consensus from multiple wallets.
    """
    signals = []
    for asset_uid, feat in features.items():
        if (
            feat["consensus_direction"] == "accumulate"
            and feat["unique_wallets_buying"] >= min_wallets
            and feat["consensus_score"] >= min_consensus
        ):
            signals.append({
                "asset_uid": asset_uid,
                "signal_type": "whale_accumulation",
                "strength": feat["consensus_score"],
                "wallets_buying": feat["unique_wallets_buying"],
                "tier_a_active": feat["tier_a_active"],
                "net_usd": feat["accumulation_net_usd"],
            })
    return sorted(signals, key=lambda s: s["strength"], reverse=True)
