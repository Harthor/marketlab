"""Playbook evaluator — checks conditions against token state."""
from __future__ import annotations

import logging
from typing import Any

from .loader import ConditionConfig, GlobalConfig, PlaybookConfig

logger = logging.getLogger(__name__)


def _resolve_field(state: dict[str, Any], field: str) -> Any:
    """Resolve a dot-separated field path from token state.

    Supports nested dicts: ``"smart_money.consensus_score"`` resolves to
    ``state["smart_money"]["consensus_score"]``.
    """
    parts = field.split(".")
    obj: Any = state
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
        if obj is None:
            return None
    return obj


def _eval_condition(state: dict[str, Any], cond: ConditionConfig) -> bool:
    """Evaluate a single condition against the token state."""
    actual = _resolve_field(state, cond.field)
    if actual is None:
        return False

    op = cond.operator
    val = cond.value

    try:
        if op == "gt":
            return float(actual) > float(val)
        if op == "gte":
            return float(actual) >= float(val)
        if op == "lt":
            return float(actual) < float(val)
        if op == "lte":
            return float(actual) <= float(val)
        if op == "eq":
            return actual == val
        if op == "neq":
            return actual != val
        if op == "in":
            return actual in (val if isinstance(val, list) else [val])
        if op == "not_in":
            return actual not in (val if isinstance(val, list) else [val])
        if op == "between":
            lo, hi = val[0], val[1]
            return float(lo) <= float(actual) <= float(hi)
    except (ValueError, TypeError, IndexError):
        return False

    return False


class EvalResult:
    """Result of evaluating a playbook against a token."""

    __slots__ = (
        "playbook_slug",
        "passed",
        "vetoed",
        "veto_reason",
        "required_passed",
        "required_total",
        "confirmations_passed",
        "confirmations_total",
    )

    def __init__(self, playbook_slug: str) -> None:
        self.playbook_slug = playbook_slug
        self.passed = False
        self.vetoed = False
        self.veto_reason = ""
        self.required_passed = 0
        self.required_total = 0
        self.confirmations_passed = 0
        self.confirmations_total = 0


class PlaybookEvaluator:
    """Evaluate playbook conditions against token state."""

    def __init__(self, global_config: GlobalConfig | None = None) -> None:
        self.global_config = global_config or GlobalConfig()

    def evaluate(
        self,
        playbook: PlaybookConfig,
        token_state: dict[str, Any],
    ) -> EvalResult:
        """Evaluate a single playbook against a token.

        Steps:
            1. Check playbook filters (chains, categories, age, liquidity)
            2. Check global vetos — if any fires, vetoed=True
            3. Check playbook vetos — if any fires, vetoed=True
            4. Check required conditions — ALL must pass
            5. Count confirmation signals
        """
        result = EvalResult(playbook.slug)

        # 1. Filters
        if not self._passes_filters(playbook, token_state):
            return result

        # 2. Global vetos
        for veto in self.global_config.vetos:
            if _eval_condition(token_state, veto):
                result.vetoed = True
                result.veto_reason = f"global_veto:{veto.field}"
                return result

        # 3. Playbook vetos
        for veto in playbook.vetos:
            if _eval_condition(token_state, veto):
                result.vetoed = True
                result.veto_reason = f"playbook_veto:{veto.field}"
                return result

        # 4. Required conditions — ALL must pass
        result.required_total = len(playbook.required)
        for cond in playbook.required:
            if _eval_condition(token_state, cond):
                result.required_passed += 1

        if result.required_total > 0 and result.required_passed < result.required_total:
            return result

        # 5. Confirmations — count how many pass
        result.confirmations_total = len(playbook.confirmations)
        for cond in playbook.confirmations:
            if _eval_condition(token_state, cond):
                result.confirmations_passed += 1

        result.passed = True
        return result

    def check_global_veto(self, token_state: dict[str, Any]) -> str:
        """Check only global vetos. Returns veto reason or empty string."""
        for veto in self.global_config.vetos:
            if _eval_condition(token_state, veto):
                return f"global_veto:{veto.field}"
        return ""

    def check_global_filters(self, token_state: dict[str, Any]) -> bool:
        """Check global filters. Returns True if token passes all."""
        return all(
            _eval_condition(token_state, filt)
            for filt in self.global_config.filters
        )

    def _passes_filters(
        self,
        playbook: PlaybookConfig,
        state: dict[str, Any],
    ) -> bool:
        """Check playbook-level filters."""
        # Chain filter
        if playbook.chains:
            chain = state.get("chain", "")
            if chain not in playbook.chains:
                return False

        # Category filter
        if playbook.categories:
            cat = state.get("category", "")
            if cat not in playbook.categories:
                return False

        # Age filter
        age = state.get("age_hours", 0) or 0
        if playbook.min_age_hours > 0 and age < playbook.min_age_hours:
            return False
        if playbook.max_age_hours > 0 and age > playbook.max_age_hours:
            return False

        # Liquidity filter
        liq = state.get("liquidity_usd", 0) or 0
        if playbook.min_liquidity_usd > 0 and liq < playbook.min_liquidity_usd:
            return False

        # Volume filter
        vol = state.get("volume_24h_usd", 0) or 0
        if playbook.min_volume_24h_usd > 0 and vol < playbook.min_volume_24h_usd:
            return False

        # Market cap filter
        mcap = state.get("market_cap_usd", 0) or 0
        return not (playbook.min_market_cap_usd > 0 and mcap < playbook.min_market_cap_usd)
