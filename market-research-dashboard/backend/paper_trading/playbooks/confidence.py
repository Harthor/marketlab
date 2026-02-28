"""Confidence calculator — weighted scoring using ramp/inv_ramp helpers."""
from __future__ import annotations

import logging
from typing import Any

from .evaluator import EvalResult, _resolve_field
from .helpers import boolf, clip01, inv_ramp, ramp
from .loader import ConfidenceComponent, PlaybookConfig

logger = logging.getLogger(__name__)

# Map func names to callables
_FUNC_MAP = {
    "ramp": ramp,
    "inv_ramp": inv_ramp,
    "clip01": lambda x, _lo, _hi: clip01(x),
    "boolf": lambda x, _lo, _hi: boolf(x),
    "raw": lambda x, _lo, _hi: clip01(x),
}


def _score_component(
    comp: ConfidenceComponent,
    state: dict[str, Any],
) -> float:
    """Score a single confidence component. Returns value in [0, 1]."""
    val = _resolve_field(state, comp.field)
    if val is None:
        return 0.0

    try:
        val_f = float(val)
    except (ValueError, TypeError):
        return boolf(val)

    func = _FUNC_MAP.get(comp.func)
    if func is None:
        return 0.0

    return func(val_f, comp.lo, comp.hi)


class ConfidenceCalculator:
    """Compute confidence score for a playbook match."""

    def compute(
        self,
        playbook: PlaybookConfig,
        token_state: dict[str, Any],
        eval_result: EvalResult,
    ) -> float:
        """Compute final confidence score in [0, 1].

        Formula:
            1. Start with base_confidence
            2. Add weighted component scores
            3. Apply confirmation bonus
            4. Clamp to [0, 1]
        """
        if not eval_result.passed:
            return 0.0

        # Base
        score = playbook.base_confidence

        # Weighted components
        if playbook.confidence_components:
            total_weight = sum(c.weight for c in playbook.confidence_components)
            if total_weight > 0:
                weighted_sum = 0.0
                for comp in playbook.confidence_components:
                    comp_score = _score_component(comp, token_state)
                    weighted_sum += comp.weight * comp_score
                # Normalize: weighted average adds up to (1 - base_confidence)
                headroom = 1.0 - playbook.base_confidence
                score += headroom * (weighted_sum / total_weight)

        # Confirmation bonus: each confirmation adds a small boost
        if eval_result.confirmations_total > 0:
            conf_ratio = (
                eval_result.confirmations_passed
                / eval_result.confirmations_total
            )
            # Confirmations can boost up to 10% of remaining headroom
            remaining = 1.0 - score
            score += remaining * 0.10 * conf_ratio

        return clip01(score)
