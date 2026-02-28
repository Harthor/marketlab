"""Degen Scanner settings."""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
STORAGE_DIR = PROJECT_ROOT / "src" / "degen_scanner" / "storage"

RAW_DIR = STORAGE_DIR / "raw"
CURATED_DIR = STORAGE_DIR / "curated"
WATCHLIST_DIR = STORAGE_DIR / "watchlists"
MANIFEST_DIR = STORAGE_DIR / "manifests"

# ---------------------------------------------------------------------------
# API keys (from env — all optional for free tiers)
# ---------------------------------------------------------------------------
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")  # demo key if available
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")

# ---------------------------------------------------------------------------
# Rate limits & cache TTLs (seconds)
# ---------------------------------------------------------------------------
DEXSCREENER_CACHE_TTL = 30
GECKOTERMINAL_CACHE_TTL = 60
BIRDEYE_CACHE_TTL = 300  # 5 min — conserve free CUs
COINGECKO_CACHE_TTL = 600  # 10 min
REDDIT_CACHE_TTL = 120
JUPITER_CACHE_TTL = 120

# ---------------------------------------------------------------------------
# Universe defaults
# ---------------------------------------------------------------------------
MAX_WATCHLIST_SIZE = 60
CANONICAL_POOL_HYSTERESIS_HOURS = 6
