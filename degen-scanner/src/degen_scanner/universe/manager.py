"""Universe Manager: orchestrates discovery, filtering, scoring, and watchlist emission."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import yaml

from .filters import apply_exclusion_rules, passes_anti_rug, passes_hard_filters
from .models import (
    AssetCandidate,
    AssetEntry,
    AssetStatus,
    Category,
    VenueProfile,
    WatchlistSnapshot,
)
from .scoring import compute_risk_score, compute_universe_score

logger = logging.getLogger(__name__)


class UniverseManager:
    """Maintains a live, scored, categorized watchlist of degen tokens."""

    def __init__(
        self,
        policy_path: str | Path,
        chains_path: str | Path,
        watchlist_dir: str | Path,
    ):
        self.policy = self._load_yaml(policy_path)
        self.chains_config = self._load_yaml(chains_path)
        self.watchlist_dir = Path(watchlist_dir)
        self.watchlist_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_yaml(path: str | Path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def enabled_chains(self) -> list[str]:
        """Return list of enabled chain names."""
        chains = self.chains_config.get("chains", {})
        return [name for name, cfg in chains.items() if cfg.get("enabled", False)]

    def refresh(self, candidates: list[AssetCandidate]) -> WatchlistSnapshot:
        """Run the full pipeline: normalize → merge → filter → score → categorize → emit."""
        # 1. Normalize identifiers
        normalized = self._normalize(candidates)

        # 2. Merge duplicates by asset_uid
        merged = self._merge_candidates(normalized)
        total_candidates = len(merged)

        # 3. Apply exclusion rules
        after_exclusion = []
        for asset in merged:
            passes, _ = apply_exclusion_rules(asset)
            if passes:
                after_exclusion.append(asset)

        # 4. Apply anti-rug
        after_rug = []
        for asset in after_exclusion:
            passes, _ = passes_anti_rug(asset, self.policy)
            if passes:
                after_rug.append(asset)

        # 5. Categorize + filter per category
        categorized = self._categorize_and_filter(after_rug)

        # 6. Score
        entries = self._score_and_convert(categorized)

        # 7. Select final watchlist (respect max_tokens per category)
        selected = self._select_final(entries)

        # 8. Emit
        snapshot = WatchlistSnapshot(
            snapshot_id=uuid.uuid4().hex[:12],
            chains=self.enabled_chains(),
            total_candidates_scanned=total_candidates,
            total_after_filters=len(selected),
            tokens=selected,
            category_counts={
                cat.value: sum(1 for t in selected if t.category == cat)
                for cat in Category
                if any(t.category == cat for t in selected)
            },
        )
        self._emit(snapshot)
        return snapshot

    def _normalize(self, candidates: list[AssetCandidate]) -> list[AssetCandidate]:
        """Ensure asset_uid = '{chain}:{token_address}' and lowercase addresses."""
        for c in candidates:
            c.token_address = c.token_address.strip()
            # Solana addresses are case-sensitive, EVM are not
            if c.chain != "solana":
                c.token_address = c.token_address.lower()
            c.asset_uid = f"{c.chain}:{c.token_address}"
        return candidates

    def _merge_candidates(self, candidates: list[AssetCandidate]) -> list[AssetCandidate]:
        """Deduplicate by asset_uid, keeping best data from each source."""
        by_uid: dict[str, AssetCandidate] = {}

        for c in candidates:
            uid = c.asset_uid
            if uid not in by_uid:
                by_uid[uid] = c
                continue

            existing = by_uid[uid]
            # Merge: prefer non-None values, combine attention flags
            if c.liquidity_usd and (
                not existing.liquidity_usd
                or c.liquidity_usd > existing.liquidity_usd
            ):
                existing.liquidity_usd = c.liquidity_usd
            if c.volume_24h_usd and not existing.volume_24h_usd:
                existing.volume_24h_usd = c.volume_24h_usd
            if c.volume_1h_usd and not existing.volume_1h_usd:
                existing.volume_1h_usd = c.volume_1h_usd
            if c.market_cap_usd and not existing.market_cap_usd:
                existing.market_cap_usd = c.market_cap_usd
            if c.holder_count and not existing.holder_count:
                existing.holder_count = c.holder_count
            if c.pool_address and not existing.pool_address:
                existing.pool_address = c.pool_address
                existing.dex_id = c.dex_id
                existing.quote_token = c.quote_token
            if c.price_usd and not existing.price_usd:
                existing.price_usd = c.price_usd
            if c.age_hours is not None and existing.age_hours is None:
                existing.age_hours = c.age_hours
            # Merge attention flags (deduplicated)
            for flag in c.attention_flags:
                if flag not in existing.attention_flags:
                    existing.attention_flags.append(flag)

        return list(by_uid.values())

    def _categorize_and_filter(
        self, assets: list[AssetCandidate]
    ) -> list[tuple[AssetCandidate, str]]:
        """Assign best-fit category and check hard filters."""
        categories = list(self.policy.get("categories", {}).keys())
        result: list[tuple[AssetCandidate, str]] = []

        for asset in assets:
            best_cat = None
            for cat in categories:
                passes, _ = passes_hard_filters(asset, cat, self.policy)
                if passes:
                    best_cat = cat
                    break  # first matching category wins (ordered by priority in YAML)

            if best_cat:
                result.append((asset, best_cat))

        return result

    def _score_and_convert(
        self, categorized: list[tuple[AssetCandidate, str]]
    ) -> list[AssetEntry]:
        """Convert candidates to scored AssetEntry objects."""
        entries: list[AssetEntry] = []

        for candidate, cat_name in categorized:
            try:
                cat = Category(cat_name)
            except ValueError:
                cat = Category.UNCLASSIFIED

            venue = VenueProfile.DEX_NEW
            if candidate.listed_on_cex:
                venue = VenueProfile.CEX_MATURE
            elif candidate.age_hours and candidate.age_hours > 30 * 24:
                venue = VenueProfile.DEX_MATURE

            reasons: list[str] = []
            if candidate.liquidity_usd and candidate.liquidity_usd >= 100_000:
                reasons.append("liquid")
            if candidate.attention_flags:
                reasons.extend(candidate.attention_flags[:3])

            entry = AssetEntry(
                asset_uid=candidate.asset_uid,
                symbol=candidate.symbol,
                name=candidate.name,
                chain=candidate.chain,
                token_address=candidate.token_address,
                category=cat,
                venue_profile=venue,
                status=AssetStatus.ACTIVE,
                primary_pool_address=candidate.pool_address,
                primary_dex_id=candidate.dex_id,
                quote_token=candidate.quote_token,
                market_cap_usd=candidate.market_cap_usd,
                fdv_usd=candidate.fdv_usd,
                liquidity_usd=candidate.liquidity_usd,
                volume_24h_usd=candidate.volume_24h_usd,
                volume_1h_usd=candidate.volume_1h_usd,
                price_usd=candidate.price_usd,
                age_hours=candidate.age_hours,
                holder_count=candidate.holder_count,
                top10_holders_pct_ex_lp=candidate.top10_holders_pct_ex_lp,
                creator_wallet_pct=candidate.creator_wallet_pct,
                security_flags=candidate.security_flags,
                attention_flags=candidate.attention_flags,
                universe_score=compute_universe_score(candidate),
                risk_score=compute_risk_score(candidate),
                include_reason=reasons,
                listed_on_coingecko=candidate.listed_on_coingecko,
                coingecko_id=candidate.coingecko_id,
            )
            entries.append(entry)

        return entries

    def _select_final(self, entries: list[AssetEntry]) -> list[AssetEntry]:
        """Rank within each category, respect max_tokens, return final list."""
        categories = self.policy.get("categories", {})

        by_cat: dict[str, list[AssetEntry]] = {}
        for entry in entries:
            by_cat.setdefault(entry.category.value, []).append(entry)

        selected: list[AssetEntry] = []
        for cat_name, tokens in by_cat.items():
            max_tokens = categories.get(cat_name, {}).get("max_tokens", 10)
            sorted_tokens = sorted(tokens, key=lambda t: t.universe_score, reverse=True)
            selected.extend(sorted_tokens[:max_tokens])

        # Sort final list by universe_score descending
        selected.sort(key=lambda t: t.universe_score, reverse=True)
        return selected

    def _emit(self, snapshot: WatchlistSnapshot) -> None:
        """Write watchlist_current.json."""
        current_path = self.watchlist_dir / "watchlist_current.json"
        data = snapshot.to_api_dict()
        current_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info(
            "Watchlist emitted: %d tokens, snapshot=%s",
            len(snapshot.tokens),
            snapshot.snapshot_id,
        )
