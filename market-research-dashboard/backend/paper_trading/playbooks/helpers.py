"""Scoring helper functions for playbook confidence calculation."""
from __future__ import annotations


def clip01(x: float) -> float:
    """Clamp *x* to [0, 1]."""
    return max(0.0, min(1.0, float(x)))


def ramp(x: float, lo: float, hi: float) -> float:
    """Linear ramp: 0 at *lo*, 1 at *hi*, clamped to [0, 1].

    Used for "more is better" signals (e.g. liquidity, score).
    """
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return clip01((x - lo) / (hi - lo))


def inv_ramp(x: float, lo: float, hi: float) -> float:
    """Inverse ramp: 1 at *lo*, 0 at *hi*, clamped to [0, 1].

    Used for "less is better" signals (e.g. risk_score, age).
    """
    if hi == lo:
        return 0.0 if x >= hi else 1.0
    return clip01(1.0 - (x - lo) / (hi - lo))


def boolf(x: object) -> float:
    """Boolean-to-float: 1.0 if truthy, 0.0 otherwise."""
    return 1.0 if x else 0.0
