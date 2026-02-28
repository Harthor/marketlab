"""Service layer for the Degen Scanner endpoint.

Reads the latest watchlist snapshot from degen-scanner storage.
Falls back to a minimal demo snapshot when the file is not available.
"""
from __future__ import annotations

import json
from pathlib import Path

# Path to the degen-scanner watchlist directory (relative to repo root)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_WATCHLIST_DIR = _REPO_ROOT / "degen-scanner" / "src" / "degen_scanner" / "storage" / "watchlists"
_CURRENT_FILE = _WATCHLIST_DIR / "watchlist_current.json"


def get_watchlist() -> dict:
    """Return the current degen watchlist snapshot as a dict.

    If the real file exists, return it.  Otherwise return a demo payload
    so the frontend can render immediately.
    """
    if _CURRENT_FILE.exists():
        return json.loads(_CURRENT_FILE.read_text())

    return _build_demo_watchlist()


def _build_demo_watchlist() -> dict:
    """Minimal demo data for dev/preview purposes."""
    return {
        "snapshot_id": "demo-001",
        "generated_at": "2026-02-28T12:00:00+00:00",
        "total_tokens": 8,
        "category_counts": {
            "meme_bluechip": 2,
            "meme_emerging": 2,
            "narrative_high_beta": 2,
            "dex_new_launch": 1,
            "pre_cex_watch": 1,
        },
        "tokens": [
            {
                "asset_uid": "solana:WIF",
                "symbol": "WIF",
                "name": "dogwifhat",
                "chain": "solana",
                "token_address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
                "category": "meme_bluechip",
                "market_cap_usd": 920_000_000,
                "liquidity_usd": 14_200_000,
                "volume_24h_usd": 185_000_000,
                "price_usd": 0.92,
                "holder_count": 185000,
                "age_hours": 8760,
                "universe_score": 88.5,
                "risk_score": 18,
                "attention_flags": ["dexscreener_boosted", "birdeye_trending"],
                "security_flags": [],
            },
            {
                "asset_uid": "solana:BONK",
                "symbol": "BONK",
                "name": "Bonk",
                "chain": "solana",
                "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                "category": "meme_bluechip",
                "market_cap_usd": 1_400_000_000,
                "liquidity_usd": 22_500_000,
                "volume_24h_usd": 210_000_000,
                "price_usd": 0.000021,
                "holder_count": 520000,
                "age_hours": 17520,
                "universe_score": 91.2,
                "risk_score": 12,
                "attention_flags": ["birdeye_trending"],
                "security_flags": [],
            },
            {
                "asset_uid": "solana:POPCAT",
                "symbol": "POPCAT",
                "name": "Popcat",
                "chain": "solana",
                "token_address": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
                "category": "meme_emerging",
                "market_cap_usd": 280_000_000,
                "liquidity_usd": 5_100_000,
                "volume_24h_usd": 42_000_000,
                "price_usd": 0.28,
                "holder_count": 67000,
                "age_hours": 4320,
                "universe_score": 72.3,
                "risk_score": 35,
                "attention_flags": ["dexscreener_boosted"],
                "security_flags": [],
            },
            {
                "asset_uid": "base:BRETT",
                "symbol": "BRETT",
                "name": "Brett",
                "chain": "base",
                "token_address": "0x532f27101965dd16442e59d40670faf5ebb142e4",
                "category": "meme_emerging",
                "market_cap_usd": 350_000_000,
                "liquidity_usd": 8_200_000,
                "volume_24h_usd": 55_000_000,
                "price_usd": 0.035,
                "holder_count": 92000,
                "age_hours": 6480,
                "universe_score": 76.1,
                "risk_score": 28,
                "attention_flags": ["geckoterminal_trending"],
                "security_flags": [],
            },
            {
                "asset_uid": "solana:JUP",
                "symbol": "JUP",
                "name": "Jupiter",
                "chain": "solana",
                "token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
                "category": "narrative_high_beta",
                "market_cap_usd": 1_600_000_000,
                "liquidity_usd": 35_000_000,
                "volume_24h_usd": 120_000_000,
                "price_usd": 1.18,
                "holder_count": 310000,
                "age_hours": 8760,
                "universe_score": 82.4,
                "risk_score": 15,
                "attention_flags": [],
                "security_flags": [],
            },
            {
                "asset_uid": "solana:RENDER",
                "symbol": "RENDER",
                "name": "Render Token",
                "chain": "solana",
                "token_address": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
                "category": "narrative_high_beta",
                "market_cap_usd": 3_200_000_000,
                "liquidity_usd": 18_000_000,
                "volume_24h_usd": 95_000_000,
                "price_usd": 6.20,
                "holder_count": 145000,
                "age_hours": 17520,
                "universe_score": 79.8,
                "risk_score": 10,
                "attention_flags": [],
                "security_flags": [],
            },
            {
                "asset_uid": "solana:NEWTOKEN1",
                "symbol": "CATGOLD",
                "name": "Cat Gold",
                "chain": "solana",
                "token_address": "CATgo1dXyz1234567890abcdefghijk",
                "category": "dex_new_launch",
                "market_cap_usd": 2_800_000,
                "liquidity_usd": 420_000,
                "volume_24h_usd": 1_200_000,
                "price_usd": 0.0028,
                "holder_count": 1200,
                "age_hours": 18,
                "universe_score": 45.6,
                "risk_score": 72,
                "attention_flags": ["dexscreener_boosted"],
                "security_flags": ["mint_authority_enabled"],
            },
            {
                "asset_uid": "bsc:PRECEX1",
                "symbol": "AIDOG",
                "name": "AI Dog",
                "chain": "bsc",
                "token_address": "0xAIDOG1234567890abcdefghijk",
                "category": "pre_cex_watch",
                "market_cap_usd": 45_000_000,
                "liquidity_usd": 3_100_000,
                "volume_24h_usd": 18_000_000,
                "price_usd": 0.045,
                "holder_count": 28000,
                "age_hours": 720,
                "universe_score": 64.2,
                "risk_score": 42,
                "attention_flags": ["reddit_mention"],
                "security_flags": [],
            },
        ],
    }
