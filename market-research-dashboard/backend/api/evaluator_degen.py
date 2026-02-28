"""Alert Engine — Degen evaluator.

Evaluates degen-specific alert types against the current degen watchlist
and smart money features. Separate from the BTC evaluator to avoid any
coupling with the existing signal evaluation logic.

Supports four degen alert types:
    whale_accumulation    — fires when smart money consensus score crosses threshold
    liquidity_event       — fires when a token's liquidity changes dramatically
    rug_risk_detected     — fires when risk_score crosses critical threshold
    explosion_score_jump  — fires when universe_score jumps significantly
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import AlertEvent, AlertRule

logger = logging.getLogger(__name__)

# Template loader
_TEMPLATES_CACHE: dict[str, dict] = {}


def _load_templates(lang: str = "en") -> dict[str, dict[str, str]]:
    """Load alert templates for the given language."""
    if lang in _TEMPLATES_CACHE:
        return _TEMPLATES_CACHE[lang]

    templates_dir = Path(__file__).parent / "alert_templates"
    path = templates_dir / f"degen_{lang}.json"
    if not path.exists():
        path = templates_dir / "degen_en.json"
    if not path.exists():
        return {}

    data = json.loads(path.read_text())
    _TEMPLATES_CACHE[lang] = data
    return data


def _render_template(
    alert_type: str, lang: str, context: dict[str, Any]
) -> tuple[str, str]:
    """Render title and message from templates."""
    templates = _load_templates(lang)
    tmpl = templates.get(alert_type, {})
    title_fmt = tmpl.get("title", "{alert_type}: {symbol}")
    message_fmt = tmpl.get("message", "Alert triggered for {symbol}")
    try:
        title = title_fmt.format(**context)
        message = message_fmt.format(**context)
    except KeyError:
        title = f"{alert_type}: {context.get('symbol', 'unknown')}"
        message = "Degen alert triggered"
    return title, message


def _get_watchlist_data() -> dict[str, Any]:
    """Load the current degen watchlist."""
    from . import degen_service
    return degen_service.get_watchlist()


def _get_smart_money_features() -> dict[str, dict[str, Any]]:
    """Load latest smart money features from storage."""
    workspace = getattr(
        settings, "MARKETLAB_WORKSPACE", Path("."),
    )
    sm_dir = (
        Path(workspace) / "degen-scanner" / "src"
        / "degen_scanner" / "storage" / "smart_money" / "features"
    )
    if not sm_dir.exists():
        return {}

    files = sorted(sm_dir.glob("sm_features_*.json"), reverse=True)
    if not files:
        return {}

    return json.loads(files[0].read_text())


def _in_cooldown(rule: AlertRule) -> bool:
    if rule.cooldown_minutes <= 0:
        return False
    cutoff = timezone.now() - timedelta(minutes=rule.cooldown_minutes)
    return rule.events.filter(fired_at__gte=cutoff).exists()


def _is_duplicate(rule: AlertRule, title: str) -> bool:
    cutoff = timezone.now() - timedelta(hours=1)
    return rule.events.filter(title=title, fired_at__gte=cutoff).exists()


# ---------------------------------------------------------------------------
# Per-type degen evaluators
# ---------------------------------------------------------------------------

def _evaluate_whale_accumulation(
    rule: AlertRule,
    watchlist: dict[str, Any],
    sm_features: dict[str, dict[str, Any]],
    lang: str,
) -> list[AlertEvent]:
    """Fire when smart money consensus score exceeds threshold for tracked tokens."""
    config = rule.config or {}
    min_consensus = config.get("min_consensus", 60.0)
    min_wallets = config.get("min_wallets", 2)
    events = []

    for asset_uid, feat in sm_features.items():
        if feat.get("consensus_direction") != "accumulate":
            continue
        if feat.get("consensus_score", 0) < min_consensus:
            continue
        if feat.get("unique_wallets_buying", 0) < min_wallets:
            continue

        # Find the symbol in watchlist
        symbol = _find_symbol(watchlist, asset_uid)
        ctx = {
            "asset_uid": asset_uid,
            "symbol": symbol,
            "consensus_score": feat.get("consensus_score", 0),
            "wallets_buying": feat.get("unique_wallets_buying", 0),
            "tier_a_active": feat.get("tier_a_active", False),
            "net_usd": feat.get("accumulation_net_usd", 0),
        }

        title, message = _render_template("whale_accumulation", lang, ctx)
        if _is_duplicate(rule, title):
            continue

        severity = AlertEvent.Severity.WARNING
        if feat.get("tier_a_active"):
            severity = AlertEvent.Severity.CRITICAL

        events.append(AlertEvent(
            rule=rule,
            severity=severity,
            title=title,
            message=message,
            context=ctx,
        ))

    return events


def _evaluate_liquidity_event(
    rule: AlertRule,
    watchlist: dict[str, Any],
    lang: str,
) -> list[AlertEvent]:
    """Fire when a token's liquidity drops below threshold or changes dramatically."""
    config = rule.config or {}
    min_liquidity = config.get("min_liquidity_usd", 50_000)
    events = []

    for token in watchlist.get("tokens", []):
        liq = token.get("liquidity_usd") or 0
        if liq >= min_liquidity:
            continue

        symbol = token.get("symbol", "?")
        asset_uid = token.get("asset_uid", "")
        ctx = {
            "asset_uid": asset_uid,
            "symbol": symbol,
            "liquidity_usd": liq,
            "min_liquidity_usd": min_liquidity,
            "chain": token.get("chain", ""),
        }

        title, message = _render_template("liquidity_event", lang, ctx)
        if _is_duplicate(rule, title):
            continue

        severity = AlertEvent.Severity.WARNING
        if liq < min_liquidity * 0.5:
            severity = AlertEvent.Severity.CRITICAL

        events.append(AlertEvent(
            rule=rule,
            severity=severity,
            title=title,
            message=message,
            context=ctx,
        ))

    return events


def _evaluate_rug_risk(
    rule: AlertRule,
    watchlist: dict[str, Any],
    lang: str,
) -> list[AlertEvent]:
    """Fire when a token's risk_score crosses the critical threshold."""
    config = rule.config or {}
    risk_threshold = config.get("risk_threshold", 75)
    events = []

    for token in watchlist.get("tokens", []):
        risk = token.get("risk_score", 0)
        if risk < risk_threshold:
            continue

        symbol = token.get("symbol", "?")
        asset_uid = token.get("asset_uid", "")
        flags = token.get("security_flags", [])
        ctx = {
            "asset_uid": asset_uid,
            "symbol": symbol,
            "risk_score": risk,
            "risk_threshold": risk_threshold,
            "security_flags": ", ".join(flags) if flags else "none",
            "chain": token.get("chain", ""),
        }

        title, message = _render_template("rug_risk_detected", lang, ctx)
        if _is_duplicate(rule, title):
            continue

        events.append(AlertEvent(
            rule=rule,
            severity=AlertEvent.Severity.CRITICAL,
            title=title,
            message=message,
            context=ctx,
        ))

    return events


def _evaluate_explosion_score_jump(
    rule: AlertRule,
    watchlist: dict[str, Any],
    lang: str,
) -> list[AlertEvent]:
    """Fire when a token's universe_score exceeds a high threshold (sudden jump)."""
    config = rule.config or {}
    score_threshold = config.get("score_threshold", 80)
    events = []

    for token in watchlist.get("tokens", []):
        score = token.get("universe_score", 0)
        if score < score_threshold:
            continue

        symbol = token.get("symbol", "?")
        asset_uid = token.get("asset_uid", "")
        ctx = {
            "asset_uid": asset_uid,
            "symbol": symbol,
            "universe_score": score,
            "score_threshold": score_threshold,
            "category": token.get("category", ""),
            "chain": token.get("chain", ""),
        }

        title, message = _render_template("explosion_score_jump", lang, ctx)
        if _is_duplicate(rule, title):
            continue

        severity = AlertEvent.Severity.WARNING
        if score >= 90:
            severity = AlertEvent.Severity.CRITICAL

        events.append(AlertEvent(
            rule=rule,
            severity=severity,
            title=title,
            message=message,
            context=ctx,
        ))

    return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_symbol(watchlist: dict[str, Any], asset_uid: str) -> str:
    """Find a token symbol by asset_uid in the watchlist."""
    for token in watchlist.get("tokens", []):
        if token.get("asset_uid") == asset_uid:
            return token.get("symbol", "?")
    # Fallback: extract from uid
    parts = asset_uid.split(":")
    return parts[-1][:8] if parts else "?"


# ---------------------------------------------------------------------------
# Main degen evaluator
# ---------------------------------------------------------------------------

DEGEN_ALERT_TYPES = {
    AlertRule.AlertType.WHALE_ACCUMULATION,
    AlertRule.AlertType.LIQUIDITY_EVENT,
    AlertRule.AlertType.RUG_RISK_DETECTED,
    AlertRule.AlertType.EXPLOSION_SCORE_JUMP,
}


def evaluate_degen_rules(
    watchlist: dict[str, Any] | None = None,
    sm_features: dict[str, dict[str, Any]] | None = None,
    lang: str = "en",
) -> list[AlertEvent]:
    """Evaluate all enabled degen alert rules.

    Args:
        watchlist: Degen watchlist data. If None, loads from degen_service.
        sm_features: Smart money features. If None, loads from storage.
        lang: Language for alert templates ("en" or "es").

    Returns:
        List of newly created AlertEvent instances.
    """
    if watchlist is None:
        try:
            watchlist = _get_watchlist_data()
        except Exception:
            logger.warning("Could not load degen watchlist for alerts")
            watchlist = {"tokens": []}

    if sm_features is None:
        sm_features = _get_smart_money_features()

    rules = AlertRule.objects.filter(
        enabled=True,
        alert_type__in=[t.value for t in DEGEN_ALERT_TYPES],
    )

    created_events: list[AlertEvent] = []

    for rule in rules:
        if _in_cooldown(rule):
            logger.debug("Degen rule %s in cooldown, skipping", rule.id)
            continue

        events: list[AlertEvent] = []
        if rule.alert_type == AlertRule.AlertType.WHALE_ACCUMULATION:
            events = _evaluate_whale_accumulation(
                rule, watchlist, sm_features, lang,
            )
        elif rule.alert_type == AlertRule.AlertType.LIQUIDITY_EVENT:
            events = _evaluate_liquidity_event(rule, watchlist, lang)
        elif rule.alert_type == AlertRule.AlertType.RUG_RISK_DETECTED:
            events = _evaluate_rug_risk(rule, watchlist, lang)
        elif rule.alert_type == AlertRule.AlertType.EXPLOSION_SCORE_JUMP:
            events = _evaluate_explosion_score_jump(
                rule, watchlist, lang,
            )

        for event in events:
            event.save()
            created_events.append(event)
            logger.info(
                "Degen alert fired: %s (rule=%s)", event.title, rule.id,
            )

    return created_events
