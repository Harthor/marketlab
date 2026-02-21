#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

from report_utils import ExperimentPaths, utc_now_compact


TEMPLATE_BY_ACTION = {
    "expand_universe": "expand_universe.md.j2",
    "timeframe_compare": "timeframe_compare.md.j2",
    "new_strategy_family": "new_strategy_family.md.j2",
    "walkforward": "walkforward.md.j2",
    "fee_sensitivity": "fee_sensitivity.md.j2",
    "rerun_or_debug": "rerun_or_debug.md.j2",
}


def _safe(value: Any, default: str = "n/a") -> str:
    if value is None:
        return default
    return str(value)


def _pref(preferences: dict[str, Any] | None, key: str, default: Any) -> Any:
    if not preferences:
        return default
    return preferences.get(key, default)


def _build_context(
    last_result: dict[str, Any],
    recommendation: dict[str, Any],
    preferences: dict[str, Any] | None = None,
) -> dict[str, str]:
    m = last_result.get("metrics", {})
    rv = last_result.get("robustness_validation", {}) or {}
    robustness_flags = rv.get("flags", []) or []
    robustness_flags_txt = ", ".join(str(x) for x in robustness_flags) if robustness_flags else "none"
    robustness_score = rv.get("robustness_score")
    pref_default_tf = _safe(_pref(preferences, "default_timeframe", "1h"))
    pref_universe_first = _safe(_pref(preferences, "prioritize_universe_expansion", True))
    pref_avoid_lower = _safe(_pref(preferences, "avoid_lower_timeframes", True))
    pref_scoring_pure = _safe(_pref(preferences, "prefer_scoring_pure", True))

    return {
        "experiment_id": _safe(last_result.get("experiment_id")),
        "strategy_name": _safe(last_result.get("strategy_name")),
        "strategy_family": _safe(last_result.get("strategy_family")),
        "config_path": _safe(last_result.get("config_path")),
        "timeframe": _safe(last_result.get("timeframe")),
        "timerange": _safe(last_result.get("timerange")),
        "universe_label": _safe(last_result.get("universe_label")),
        "market_mode": _safe(last_result.get("market_mode")),
        "pairs_count": _safe(last_result.get("pairs_count")),
        "trades": _safe(m.get("trades", 0)),
        "trades_per_day": f"{float(m.get('trades_per_day', 0.0)):.4f}",
        "profit_total_pct": f"{float(m.get('profit_total_pct', 0.0)):.4f}",
        "winrate_pct": f"{float(m.get('winrate_pct', 0.0)):.4f}",
        "profit_factor": _safe(m.get("profit_factor")),
        "max_drawdown_pct": f"{float(m.get('max_drawdown_pct', 0.0)):.4f}",
        "recommendation_code": _safe(recommendation.get("recommendation_code")),
        "recommendation_text": _safe(recommendation.get("recommendation_text")),
        "next_action_type": _safe(recommendation.get("next_action_type")),
        "robustness_score": _safe(robustness_score),
        "robustness_flags": robustness_flags_txt,
        "robustness_report_json": _safe(rv.get("report_json")),
        "pref_default_timeframe": pref_default_tf,
        "pref_prioritize_universe_expansion": pref_universe_first,
        "pref_avoid_lower_timeframes": pref_avoid_lower,
        "pref_prefer_scoring_pure": pref_scoring_pure,
    }


def _preferences_block(context: dict[str, str]) -> str:
    return (
        "Preferencias del usuario\n"
        f"- Mantener timeframe default en `{context['pref_default_timeframe']}`\n"
        f"- Priorizar expansión de universo antes que bajar timeframe: `{context['pref_prioritize_universe_expansion']}`\n"
        f"- Evitar sugerir timeframes más bajos por defecto: `{context['pref_avoid_lower_timeframes']}`\n"
        f"- Selección de pares por defecto: scoring puro = `{context['pref_prefer_scoring_pure']}`\n"
    )


def _anti_smoke_block(context: dict[str, str]) -> str:
    return (
        "Validación anti-humo\n"
        f"- Robustness score: `{context['robustness_score']}`\n"
        f"- Flags activos: `{context['robustness_flags']}`\n"
        f"- Reporte: `{context['robustness_report_json']}`\n"
    )


def render_prompt(
    paths: ExperimentPaths,
    last_result: dict[str, Any],
    recommendation: dict[str, Any],
    preferences: dict[str, Any] | None = None,
) -> Path:
    action = recommendation.get("next_action_type", "rerun_or_debug")
    template_name = TEMPLATE_BY_ACTION.get(action, "rerun_or_debug.md.j2")
    template_path = paths.templates / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    template = template_path.read_text(encoding="utf-8")
    context = _build_context(last_result, recommendation, preferences=preferences)
    rendered_main = template.format(**context).strip()

    rendered = f"{_preferences_block(context)}\n\n{_anti_smoke_block(context)}\n\n{rendered_main}\n"

    out_name = f"next_prompt_{utc_now_compact()}.md"
    out_path = paths.prompts / out_name
    out_path.write_text(rendered, encoding="utf-8")
    return out_path
