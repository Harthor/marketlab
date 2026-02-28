"""Tests for Universe Manager: models, filters, scoring, manager pipeline."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from degen_scanner.universe.filters import (
    apply_exclusion_rules,
    passes_anti_rug,
    passes_hard_filters,
)
from degen_scanner.universe.manager import UniverseManager
from degen_scanner.universe.models import AssetCandidate, WatchlistSnapshot
from degen_scanner.universe.scoring import (
    compute_risk_score,
    compute_universe_score,
    normalize_age,
    normalize_attention,
    normalize_liquidity,
    normalize_volume,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(**kwargs) -> AssetCandidate:
    defaults = {
        "asset_uid": "solana:FakeToken123",
        "symbol": "FAKE",
        "name": "Fake Token",
        "chain": "solana",
        "token_address": "FakeToken123",
        "source": "test",
        "liquidity_usd": 500_000,
        "volume_24h_usd": 1_000_000,
        "age_hours": 720,  # 30 days
    }
    defaults.update(kwargs)
    return AssetCandidate(**defaults)


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


class TestNormalizeFunctions:
    def test_liquidity_zero(self):
        assert normalize_liquidity(0) == 0.0
        assert normalize_liquidity(None) == 0.0

    def test_liquidity_scales(self):
        low = normalize_liquidity(50_000)
        mid = normalize_liquidity(500_000)
        high = normalize_liquidity(5_000_000)
        assert low < mid < high

    def test_volume_scales(self):
        low = normalize_volume(10_000)
        high = normalize_volume(10_000_000)
        assert low < high

    def test_attention_empty(self):
        assert normalize_attention([]) == 0.0

    def test_attention_with_flags(self):
        score = normalize_attention(["dexscreener_boosted", "birdeye_trending"])
        assert score > 0

    def test_age_very_new(self):
        assert normalize_age(1) < normalize_age(48)

    def test_age_optimal(self):
        assert normalize_age(720) > normalize_age(6)

    def test_universe_score_range(self):
        asset = _make_candidate()
        score = compute_universe_score(asset)
        assert 0 <= score <= 100

    def test_risk_score_young_token(self):
        young = _make_candidate(age_hours=6, liquidity_usd=50_000)
        old = _make_candidate(age_hours=720, liquidity_usd=2_000_000)
        assert compute_risk_score(young) > compute_risk_score(old)


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


class TestFilters:
    @pytest.fixture()
    def policy(self):
        import yaml
        with open(CONFIG_DIR / "universe_policy.yaml") as f:
            return yaml.safe_load(f)

    def test_meme_bluechip_passes(self, policy):
        asset = _make_candidate(
            liquidity_usd=2_000_000,
            volume_24h_usd=10_000_000,
            age_hours=180 * 24,
            top10_holders_pct_ex_lp=30,
        )
        passes, reasons = passes_hard_filters(asset, "meme_bluechip", policy)
        assert passes, f"Failed: {reasons}"

    def test_meme_bluechip_fails_low_volume(self, policy):
        asset = _make_candidate(
            liquidity_usd=2_000_000,
            volume_24h_usd=100_000,  # below 5M
            age_hours=180 * 24,
        )
        passes, reasons = passes_hard_filters(asset, "meme_bluechip", policy)
        assert not passes

    def test_meme_emerging_passes(self, policy):
        asset = _make_candidate(
            liquidity_usd=200_000,
            volume_24h_usd=500_000,
            age_hours=30 * 24,
            top10_holders_pct_ex_lp=25,
        )
        passes, _ = passes_hard_filters(asset, "meme_emerging", policy)
        assert passes

    def test_dex_new_launch_fails_too_young(self, policy):
        asset = _make_candidate(age_hours=2, liquidity_usd=200_000, volume_1h_usd=100_000)
        passes, reasons = passes_hard_filters(asset, "dex_new_launch", policy)
        assert not passes
        assert any("age_below_6h" in r for r in reasons)

    def test_dex_new_launch_fails_too_old(self, policy):
        asset = _make_candidate(age_hours=30 * 24, liquidity_usd=200_000, volume_1h_usd=100_000)
        passes, reasons = passes_hard_filters(asset, "dex_new_launch", policy)
        assert not passes

    def test_anti_rug_solana_mint_authority(self, policy):
        asset = _make_candidate(mint_authority_disabled=False)
        passes, reasons = passes_anti_rug(asset, policy)
        assert not passes
        assert "mint_authority_enabled" in reasons

    def test_anti_rug_passes_clean(self, policy):
        asset = _make_candidate(
            mint_authority_disabled=True,
            freeze_authority_disabled=True,
            creator_wallet_pct=5,
            liquidity_usd=200_000,
        )
        passes, _ = passes_anti_rug(asset, policy)
        assert passes

    def test_exclusion_honeypot(self):
        asset = _make_candidate(security_flags=["honeypot"])
        passes, _ = apply_exclusion_rules(asset)
        assert not passes

    def test_exclusion_zero_liquidity(self):
        asset = _make_candidate(liquidity_usd=0)
        passes, _ = apply_exclusion_rules(asset)
        assert not passes


# ---------------------------------------------------------------------------
# Manager tests
# ---------------------------------------------------------------------------


class TestUniverseManager:
    def test_full_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            watchlist_dir = Path(tmp) / "watchlists"
            manager = UniverseManager(
                policy_path=CONFIG_DIR / "universe_policy.yaml",
                chains_path=CONFIG_DIR / "chains.yaml",
                watchlist_dir=watchlist_dir,
            )

            candidates = [
                _make_candidate(
                    asset_uid="solana:Token1",
                    symbol="DOGE",
                    token_address="Token1",
                    liquidity_usd=5_000_000,
                    volume_24h_usd=20_000_000,
                    age_hours=365 * 24,
                    top10_holders_pct_ex_lp=20,
                    mint_authority_disabled=True,
                    freeze_authority_disabled=True,
                ),
                _make_candidate(
                    asset_uid="solana:Token2",
                    symbol="BRETT",
                    token_address="Token2",
                    liquidity_usd=300_000,
                    volume_24h_usd=600_000,
                    age_hours=30 * 24,
                    top10_holders_pct_ex_lp=25,
                    mint_authority_disabled=True,
                    freeze_authority_disabled=True,
                ),
                # Should be filtered out (honeypot)
                _make_candidate(
                    asset_uid="solana:Token3",
                    symbol="SCAM",
                    token_address="Token3",
                    security_flags=["honeypot"],
                    liquidity_usd=1_000_000,
                    volume_24h_usd=5_000_000,
                ),
            ]

            snapshot = manager.refresh(candidates)
            assert isinstance(snapshot, WatchlistSnapshot)
            # SCAM should be filtered out
            symbols = [t.symbol for t in snapshot.tokens]
            assert "SCAM" not in symbols
            assert len(snapshot.tokens) >= 1

            # Check watchlist file was written
            wl_path = watchlist_dir / "watchlist_current.json"
            assert wl_path.exists()
            data = json.loads(wl_path.read_text())
            assert "tokens" in data
            assert data["total_tokens"] >= 1

    def test_enabled_chains(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = UniverseManager(
                policy_path=CONFIG_DIR / "universe_policy.yaml",
                chains_path=CONFIG_DIR / "chains.yaml",
                watchlist_dir=Path(tmp),
            )
            chains = manager.enabled_chains()
            assert "solana" in chains
            assert "base" in chains
            assert "bsc" in chains

    def test_canonical_pool_hysteresis(self):
        """Merged candidates should keep the highest liquidity pool."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = UniverseManager(
                policy_path=CONFIG_DIR / "universe_policy.yaml",
                chains_path=CONFIG_DIR / "chains.yaml",
                watchlist_dir=Path(tmp),
            )
            candidates = [
                _make_candidate(
                    asset_uid="solana:SameToken",
                    token_address="SameToken",
                    source="dexscreener",
                    liquidity_usd=100_000,
                    pool_address="pool_low",
                ),
                _make_candidate(
                    asset_uid="solana:SameToken",
                    token_address="SameToken",
                    source="geckoterminal",
                    liquidity_usd=500_000,
                    pool_address="pool_high",
                ),
            ]
            merged = manager._merge_candidates(manager._normalize(candidates))
            assert len(merged) == 1
            # Should keep higher liquidity
            assert merged[0].liquidity_usd == 500_000
