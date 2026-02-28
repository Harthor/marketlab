"""Alert Engine v1 — evaluator.

Evaluates all enabled AlertRules against the latest dashboard data
and creates AlertEvent records when conditions are met.

Supports three alert types:
    signal_state_change  — fires when a card's state transitions
    threshold_breach     — fires when a metric crosses a threshold
    anomaly             — fires when a metric deviates beyond N sigma
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

from django.utils import timezone

from .models import AlertEvent, AlertRule

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _get_card(dashboard: dict[str, Any], card_key: str) -> dict[str, Any] | None:
    for signal in dashboard.get("signals", []):
        if signal.get("cardKey") == card_key:
            return signal
    return None


def _resolve_metric(card: dict[str, Any], metric: str) -> float | None:
    """Resolve a dot-separated metric path from a card payload."""
    stats = card.get("stats", {})
    if metric in stats:
        return _safe_float(stats[metric])
    bd = card.get("confidenceBreakdown") or {}
    if metric in bd:
        return _safe_float(bd[metric])
    detail = card.get("detail") or {}
    granger = detail.get("granger") or {}
    if metric.startswith("granger."):
        key = metric.split(".", 1)[1]
        return _safe_float(granger.get(key))
    bootstrap = detail.get("bootstrap") or {}
    if metric.startswith("bootstrap."):
        key = metric.split(".", 1)[1]
        return _safe_float(bootstrap.get(key))
    return _safe_float(card.get(metric))


def _in_cooldown(rule: AlertRule) -> bool:
    """Check if the rule has fired recently within its cooldown window."""
    if rule.cooldown_minutes <= 0:
        return False
    cutoff = timezone.now() - timedelta(minutes=rule.cooldown_minutes)
    return rule.events.filter(fired_at__gte=cutoff).exists()


def _is_duplicate(rule: AlertRule, title: str) -> bool:
    """Prevent exact duplicate events within the last hour."""
    cutoff = timezone.now() - timedelta(hours=1)
    return rule.events.filter(title=title, fired_at__gte=cutoff).exists()


# ---------------------------------------------------------------------------
# Per-type evaluators
# ---------------------------------------------------------------------------


def _evaluate_signal_state_change(
    rule: AlertRule,
    card: dict[str, Any],
    previous_states: dict[str, str],
) -> AlertEvent | None:
    """Fire when a card's state transitions between specified states."""
    config = rule.config or {}
    current_state = card.get("state", "unknown")
    previous_state = previous_states.get(rule.card_key, "unknown")

    if current_state == previous_state:
        return None

    from_states = config.get("from_states")
    to_states = config.get("to_states")

    if from_states and previous_state not in from_states:
        return None
    if to_states and current_state not in to_states:
        return None

    title = f"{rule.card_key}: {previous_state} → {current_state}"
    if _is_duplicate(rule, title):
        return None

    severity = AlertEvent.Severity.INFO
    if current_state == "blocked":
        severity = AlertEvent.Severity.CRITICAL
    elif current_state in ("orange", "red"):
        severity = AlertEvent.Severity.WARNING

    return AlertEvent(
        rule=rule,
        severity=severity,
        title=title,
        message=f"Signal state for {card.get('displayName', rule.card_key)} "
                f"changed from {previous_state} to {current_state}.",
        context={
            "previous_state": previous_state,
            "current_state": current_state,
            "card_key": rule.card_key,
        },
    )


def _evaluate_threshold_breach(
    rule: AlertRule,
    card: dict[str, Any],
) -> AlertEvent | None:
    """Fire when a metric crosses a configured threshold."""
    config = rule.config or {}
    metric = config.get("metric")
    operator = config.get("operator", "gt")
    threshold = _safe_float(config.get("value"))

    if not metric or threshold is None:
        return None

    actual = _resolve_metric(card, metric)
    if actual is None:
        return None

    _ops = {"gt": actual > threshold, "gte": actual >= threshold,
            "lt": actual < threshold, "lte": actual <= threshold,
            "eq": actual == threshold}
    if not _ops.get(operator, False):
        return None

    title = f"{rule.card_key}: {metric} {operator} {threshold} (actual={actual:.4f})"
    if _is_duplicate(rule, title):
        return None

    return AlertEvent(
        rule=rule,
        severity=AlertEvent.Severity.WARNING,
        title=title,
        message=f"{metric} = {actual:.4f} triggered threshold ({operator} {threshold}).",
        context={
            "metric": metric,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "card_key": rule.card_key,
        },
    )


def _evaluate_anomaly(
    rule: AlertRule,
    card: dict[str, Any],
) -> AlertEvent | None:
    """Fire when a metric exceeds N standard deviations (simplified z-score check)."""
    config = rule.config or {}
    metric = config.get("metric")
    sigma = _safe_float(config.get("sigma", 2.0))

    if not metric or sigma is None:
        return None

    actual = _resolve_metric(card, metric)
    if actual is None:
        return None

    # For v1, we use the stabilityScore z-interpretation:
    # if the metric value itself exceeds sigma threshold in absolute terms,
    # treat it as an anomaly. For z-scored metrics (like zscore_30d), this
    # directly applies. For raw metrics, the user sets appropriate sigma.
    if abs(actual) <= sigma:
        return None

    title = f"{rule.card_key}: {metric} anomaly (|{actual:.4f}| > {sigma}σ)"
    if _is_duplicate(rule, title):
        return None

    return AlertEvent(
        rule=rule,
        severity=AlertEvent.Severity.CRITICAL,
        title=title,
        message=f"{metric} = {actual:.4f} exceeds {sigma}σ anomaly threshold.",
        context={
            "metric": metric,
            "sigma": sigma,
            "actual": actual,
            "card_key": rule.card_key,
        },
    )


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------


def evaluate_all_rules(
    dashboard: dict[str, Any] | None = None,
    previous_states: dict[str, str] | None = None,
) -> list[AlertEvent]:
    """Evaluate all enabled alert rules and return newly created events.

    Args:
        dashboard: The full DashboardRunData payload. If None, fetches live.
        previous_states: Map of card_key → previous state. If None, reads
            from the most recent AlertEvent per card.

    Returns:
        List of newly created AlertEvent instances.
    """
    if dashboard is None:
        from . import dashboard_service
        dashboard = dashboard_service.get_dashboard_data()

    if previous_states is None:
        previous_states = _infer_previous_states()

    rules = AlertRule.objects.filter(enabled=True).select_related()
    created_events: list[AlertEvent] = []

    for rule in rules:
        card = _get_card(dashboard, rule.card_key)
        if card is None:
            continue

        if _in_cooldown(rule):
            logger.debug("Rule %s in cooldown, skipping", rule.id)
            continue

        event: AlertEvent | None = None
        if rule.alert_type == AlertRule.AlertType.SIGNAL_STATE_CHANGE:
            event = _evaluate_signal_state_change(rule, card, previous_states)
        elif rule.alert_type == AlertRule.AlertType.THRESHOLD_BREACH:
            event = _evaluate_threshold_breach(rule, card)
        elif rule.alert_type == AlertRule.AlertType.ANOMALY:
            event = _evaluate_anomaly(rule, card)

        if event is not None:
            event.save()
            created_events.append(event)
            logger.info("Alert fired: %s (rule=%s)", event.title, rule.id)

    # Also evaluate degen rules (separate evaluator, no coupling)
    try:
        from .evaluator_degen import evaluate_degen_rules
        degen_events = evaluate_degen_rules()
        created_events.extend(degen_events)
    except Exception:
        logger.warning("Degen alert evaluation failed", exc_info=True)

    return created_events


def _infer_previous_states() -> dict[str, str]:
    """Infer previous card states from the most recent state_change events."""
    states: dict[str, str] = {}
    recent = (
        AlertEvent.objects
        .filter(rule__alert_type=AlertRule.AlertType.SIGNAL_STATE_CHANGE)
        .order_by("-fired_at")[:50]
    )
    for event in recent:
        card_key = event.context.get("card_key", "")
        if card_key and card_key not in states:
            states[card_key] = event.context.get("current_state", "unknown")
    return states
