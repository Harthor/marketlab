"""Candidate generator — the main loop that ties everything together.

Pipeline:
    1. Load playbooks + global config
    2. Detect regime from watchlist
    3. For each token × each playbook: evaluate → score confidence → build candidate
    4. Resolve conflicts (best candidate per token)
    5. Apply portfolio overlay (risk limits)
    6. Emit accepted candidates to PaperTradeEngine
    7. Log audit trail
"""
from __future__ import annotations

import logging
from typing import Any

from paper_trading.playbooks.confidence import ConfidenceCalculator
from paper_trading.playbooks.evaluator import PlaybookEvaluator
from paper_trading.playbooks.loader import PlaybookConfig, PlaybookLoader
from paper_trading.regime.detector import RegimeDetector

from .audit_log import log_generation_run
from .conflict_resolver import resolve_conflicts
from .derived_features import compute_priority_score
from .portfolio_overlay import apply_overlay

logger = logging.getLogger(__name__)


class CandidateGenerator:
    """Evaluates all playbooks against all watchlist tokens and generates
    trade candidates for the PaperTradeEngine."""

    def __init__(self) -> None:
        self.loader = PlaybookLoader()
        self.evaluator: PlaybookEvaluator | None = None
        self.confidence = ConfidenceCalculator()
        self.regime_detector = RegimeDetector()

    def run(
        self,
        tokens: list[dict[str, Any]],
        portfolio: Any,
        *,
        min_confidence: float = 0.35,
        min_priority: float = 0.01,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """Run the full candidate generation pipeline.

        Args:
            tokens: Degen watchlist tokens with full state.
            portfolio: PaperPortfolio instance.
            min_confidence: Minimum confidence to consider a candidate.
            min_priority: Minimum priority score to emit.
            dry_run: If True, generate candidates but don't execute trades.

        Returns:
            List of candidate dicts that were emitted (or would be, if dry_run).
        """
        # 1. Load playbooks
        self.loader.load()
        global_config = self.loader.get_global()
        playbooks = self.loader.get_playbooks()
        self.evaluator = PlaybookEvaluator(global_config=global_config)

        if not playbooks:
            logger.warning("No playbooks loaded, skipping candidate generation")
            return []

        # 2. Detect regime
        regime_result = self.regime_detector.detect(tokens)
        current_regime = regime_result.current_regime
        regime_conf = regime_result.confidence

        logger.info(
            "Regime: %s (%.2f) — %d tokens, %d playbooks",
            current_regime, regime_conf, len(tokens), len(playbooks),
        )

        # 3. Evaluate all tokens × all playbooks
        raw_candidates = []
        for token in tokens:
            # Global veto check
            veto = self.evaluator.check_global_veto(token)
            if veto:
                continue

            # Global filter check
            if not self.evaluator.check_global_filters(token):
                continue

            for pb in playbooks:
                candidate = self._evaluate_token_playbook(
                    token, pb, current_regime, min_confidence,
                )
                if candidate:
                    raw_candidates.append(candidate)

        # 4. Resolve conflicts
        resolved = resolve_conflicts(raw_candidates)

        # 5. Filter by min priority
        resolved = [c for c in resolved if c["priority_score"] >= min_priority]

        # 6. Portfolio overlay
        risk_config = global_config.portfolio_risk
        accepted = apply_overlay(resolved, portfolio, risk_config)

        # 7. Emit or dry run
        emitted = (
            self._emit_candidates(accepted, portfolio) if not dry_run else accepted
        )

        # 8. Audit log
        log_generation_run(
            regime=current_regime,
            regime_confidence=regime_conf,
            evaluated_count=len(tokens),
            candidates_raw=len(raw_candidates),
            candidates_after_conflict=len(resolved),
            candidates_after_overlay=len(accepted),
            emitted_count=len(emitted),
        )

        return emitted

    def _evaluate_token_playbook(
        self,
        token: dict[str, Any],
        pb: PlaybookConfig,
        current_regime: str,
        min_confidence: float,
    ) -> dict[str, Any] | None:
        """Evaluate a single token against a single playbook."""
        result = self.evaluator.evaluate(pb, token)
        if not result.passed or result.vetoed:
            return None

        conf = self.confidence.compute(pb, token, result)
        if conf < min_confidence:
            return None

        regime_fit = pb.regime_fit.get(current_regime, 0.5)
        priority = compute_priority_score(
            confidence=conf,
            edge_prior=pb.edge_prior,
            regime_fit=regime_fit,
            token=token,
        )

        return {
            "asset_uid": token.get("asset_uid", ""),
            "symbol": token.get("symbol", "?"),
            "chain": token.get("chain", ""),
            "category": token.get("category", ""),
            "token_address": token.get("token_address", ""),
            "token_bucket": token.get("token_bucket", "microcap_listed"),
            "arrival_price_usd": token.get("price_usd", 0),
            "exit_liquidity_usd": token.get("liquidity_usd", 0),
            "volume_24h_usd": token.get("volume_24h_usd", 0),
            "pool_fee_bps": token.get("pool_fee_bps", 30),
            "buy_tax_bps": token.get("buy_tax_bps", 0),
            "sell_tax_bps": token.get("sell_tax_bps", 0),
            "chain_fee_usd": token.get("chain_fee_usd", 0.0),
            "priority_fee_usd": token.get("priority_fee_usd", 0.0),
            "reserve_quote_usd": token.get("reserve_quote_usd"),
            "reserve_token_units": token.get("reserve_token_units"),
            "route_hops": token.get("route_hops", 1),
            "security_flags": token.get("security_flags", []),
            "confidence_multiplier": conf,
            "trigger_type": f"playbook:{pb.slug}",
            "signal_context": {
                "playbook": pb.slug,
                "confidence": round(conf, 4),
                "priority_score": round(priority, 4),
                "regime": current_regime,
                "regime_fit": regime_fit,
                "required_passed": result.required_passed,
                "confirmations_passed": result.confirmations_passed,
            },
            "playbook_slug": pb.slug,
            "priority_score": priority,
        }

    def _emit_candidates(
        self,
        candidates: list[dict[str, Any]],
        portfolio: Any,
    ) -> list[dict[str, Any]]:
        """Send candidates to PaperTradeEngine."""
        from paper_trading.trade_engine import PaperTradeEngine

        engine = PaperTradeEngine()
        emitted = []

        for c in candidates:
            try:
                trade = engine.process_candidate(portfolio, c)
                c["trade_id"] = str(trade.id)
                c["trade_status"] = trade.status
                emitted.append(c)
                logger.info(
                    "Emitted candidate: %s (%s) → %s",
                    c["symbol"], c["playbook_slug"], trade.status,
                )
            except Exception:
                logger.exception("Failed to emit candidate: %s", c.get("symbol"))

        return emitted
