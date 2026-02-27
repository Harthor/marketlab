#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _pref(preferences: dict[str, Any] | None, key: str, default: Any) -> Any:
    if not preferences:
        return default
    return preferences.get(key, default)


def _universe_size(label: str | None) -> int | None:
    if not label:
        return None
    s = label.strip().lower()
    if s.startswith("top") and s[3:].isdigit():
        return int(s[3:])
    if "manual" in s and any(ch.isdigit() for ch in s):
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else None
    return None


def _same_context(row: dict[str, str], last_result: dict[str, Any]) -> bool:
    return (
        row.get("strategy_name") == last_result.get("strategy_name")
        and row.get("timeframe") == last_result.get("timeframe")
        and row.get("timerange") == last_result.get("timerange")
    )


def _detect_universe_expansion_degradation(last_result: dict[str, Any], ledger_rows: list[dict[str, str]]) -> bool:
    points: list[tuple[int, float]] = []

    for row in ledger_rows:
        if not _same_context(row, last_result):
            continue
        size = _universe_size(row.get("universe_label"))
        pf = _as_float(row.get("profit_factor"))
        if size is None or pf is None:
            continue
        points.append((size, pf))

    current_size = _universe_size(str(last_result.get("universe_label", "")))
    current_pf = _as_float(last_result.get("metrics", {}).get("profit_factor"))
    if current_size is not None and current_pf is not None:
        points.append((current_size, current_pf))

    if len(points) < 2:
        return False

    best_by_size: dict[int, float] = {}
    for size, pf in points:
        prev = best_by_size.get(size)
        if prev is None or pf > prev:
            best_by_size[size] = pf

    sizes = sorted(best_by_size)
    if len(sizes) < 2:
        return False

    for i in range(len(sizes) - 1):
        s0, s1 = sizes[i], sizes[i + 1]
        if best_by_size[s0] > 1 and best_by_size[s1] < 1:
            return True

    if len(sizes) >= 3:
        for i in range(len(sizes) - 2):
            a, b, c = sizes[i], sizes[i + 1], sizes[i + 2]
            if best_by_size[a] > best_by_size[b] > best_by_size[c]:
                return True

    return False


def _detect_train_overfit(last_result: dict[str, Any], ledger_rows: list[dict[str, str]]) -> bool:
    split = last_result.get("split_label")
    if not split:
        return False

    strategy = last_result.get("strategy_name")
    timeframe = last_result.get("timeframe")

    by_universe: dict[str, float] = {}
    for row in ledger_rows:
        if row.get("split_label") != split:
            continue
        if row.get("strategy_name") != strategy:
            continue
        if row.get("timeframe") != timeframe:
            continue
        pf = _as_float(row.get("profit_factor"))
        if pf is None:
            continue
        by_universe[row.get("universe_label", "")] = pf

    scoring = [v for k, v in by_universe.items() if "top" in k and "train" not in k]
    train_sel = [v for k, v in by_universe.items() if "train" in k]
    if not scoring or not train_sel:
        return False
    return max(train_sel) < max(scoring)


def _baseline_note(last_result: dict[str, Any], baseline_result: dict[str, Any] | None) -> str:
    if not baseline_result:
        return ""

    last_pf = _as_float(last_result.get("metrics", {}).get("profit_factor"))
    base_pf = _as_float(baseline_result.get("metrics", {}).get("profit_factor"))
    last_dd = _as_float(last_result.get("metrics", {}).get("max_drawdown_pct"))
    base_dd = _as_float(baseline_result.get("metrics", {}).get("max_drawdown_pct"))

    if last_pf is None or base_pf is None or last_dd is None or base_dd is None:
        return ""

    d_pf = last_pf - base_pf
    d_dd = last_dd - base_dd
    rel_pf = "mejor" if d_pf > 0 else "peor" if d_pf < 0 else "igual"
    return (
        f" Comparado con baseline ({baseline_result.get('experiment_id')}), "
        f"este experimento es {rel_pf} en PF por {d_pf:+.3f} y en DD por {d_dd:+.3f}pp."
    )


def decide_next_step(
    last_result: dict[str, Any],
    ledger_rows: list[dict[str, str]],
    baseline_result: dict[str, Any] | None = None,
    preferences: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    min_trades_for_conf = int(thresholds.get("min_trades_for_confidence", 80))
    low_sample_trades = int(thresholds.get("low_sample_trades", 30))
    discard_pf_threshold = float(thresholds.get("discard_pf_threshold", 0.8))
    high_dd_pct_for_discard = float(thresholds.get("high_dd_pct_for_discard", 4.0))

    metrics = last_result.get("metrics", {})
    pf = _as_float(metrics.get("profit_factor"))
    trades = int(metrics.get("trades", 0) or 0)
    max_dd = _as_float(metrics.get("max_drawdown_pct")) or 0.0
    timeframe = str(last_result.get("timeframe", ""))
    strategy_family = str(last_result.get("strategy_family", "unknown"))
    status = str(last_result.get("status", ""))
    is_oos = last_result.get("robustness", {}).get("oos")

    preferred_timeframe = str(_pref(preferences, "default_timeframe", "1h"))
    avoid_lower_tf = bool(_pref(preferences, "avoid_lower_timeframes", True))
    prioritize_universe = bool(_pref(preferences, "prioritize_universe_expansion", True))
    prefer_scoring_pure = bool(_pref(preferences, "prefer_scoring_pure", True))

    baseline_note = _baseline_note(last_result, baseline_result)
    expansion_degraded = _detect_universe_expansion_degradation(last_result, ledger_rows)
    robustness_validation = last_result.get("robustness_validation", {}) or {}
    robustness_flags = [str(x) for x in robustness_validation.get("flags", [])]
    robustness_score = _as_float(robustness_validation.get("robustness_score"))
    infra_retryable = bool(robustness_validation.get("retryable", False))
    infra_fail_flags = {"INFRA_FAIL_LOOKAHEAD", "INFRA_FAIL_RECURSIVE"}
    logical_fail_flags = {"FAIL_LOOKAHEAD", "FAIL_RECURSIVE"}

    if any(flag in logical_fail_flags for flag in robustness_flags):
        return {
            "recommendation_code": "DISCARD_OR_REDESIGN",
            "recommendation_text": (
                "Validación anti-humo falló en lookahead/recursive. No continuar expansión; corregir sesgo o descartar idea."
                + baseline_note
            ),
            "next_action_type": "rerun_or_debug",
            "next_prompt_payload": {"focus": "rerun_or_debug", "reason": "anti_smoke_fail"},
        }

    if any(flag in infra_fail_flags for flag in robustness_flags):
        return {
            "recommendation_code": "RERUN_OR_DEBUG",
            "recommendation_text": (
                "Validación anti-humo con fallo de infraestructura (DNS/red/exchange). "
                "No penalizar la estrategia por este resultado; reintentar validación técnica."
                + (" Marcado como retryable." if infra_retryable else "")
                + baseline_note
            ),
            "next_action_type": "rerun_or_debug",
            "next_prompt_payload": {"focus": "rerun_or_debug", "reason": "anti_smoke_infra_fail"},
        }

    if "COST_FRAGILE" in robustness_flags and pf is not None and pf > 1:
        return {
            "recommendation_code": "MORE_WALKFORWARD",
            "recommendation_text": (
                "La estrategia muestra fragilidad a costos. Mantener setup, reforzar walk-forward y revisar implementación/ejecución antes de escalar."
                + baseline_note
            ),
            "next_action_type": "walkforward",
            "next_prompt_payload": {"focus": "walkforward", "reason": "cost_fragile"},
        }

    if status != "success" or pf is None:
        return {
            "recommendation_code": "RERUN_OR_DEBUG",
            "recommendation_text": (
                "Resultado incompleto o PF no disponible. Re-ejecutar/depurar parseo antes de decidir."
                + baseline_note
            ),
            "next_action_type": "rerun_or_debug",
            "next_prompt_payload": {"focus": "rerun_or_debug", "reason": "status!=success or profit_factor missing"},
        }

    if _detect_train_overfit(last_result, ledger_rows) and prefer_scoring_pure:
        return {
            "recommendation_code": "MORE_WALKFORWARD",
            "recommendation_text": (
                "Se detecta sobreajuste train->test. Mantener scoring puro por defecto y ejecutar más splits walk-forward."
                + baseline_note
            ),
            "next_action_type": "walkforward",
            "next_prompt_payload": {"focus": "walkforward", "mode": "scoring_only", "splits": "more"},
        }

    # Sanity fail: enough sample size with clearly poor edge should not trigger sample expansion.
    if (pf < discard_pf_threshold and trades >= min_trades_for_conf) or (
        pf < 1 and trades >= min_trades_for_conf and max_dd >= high_dd_pct_for_discard
    ):
        return {
            "recommendation_code": "DISCARD_OR_REDESIGN",
            "recommendation_text": (
                "PF muy bajo con muestra suficiente; no ampliar universo/splits en esta version. "
                "Descartar o redisenar estrategia y mantener baseline para produccion."
                + baseline_note
            ),
            "next_action_type": "new_strategy_family",
            "next_prompt_payload": {
                "focus": "new_strategy_family",
                "reason": "sanity_fail_enough_sample",
                "default_timeframe": preferred_timeframe,
            },
        }

    if "LOW_SAMPLE" in robustness_flags and pf is not None and pf > 1:
        return {
            "recommendation_code": "INCREASE_SAMPLE_SIZE",
            "recommendation_text": (
                "Validación anti-humo detecta muestra baja. Aumentar muestra con universo/splits sin cambiar lógica."
                + baseline_note
            ),
            "next_action_type": "expand_universe",
            "next_prompt_payload": {"focus": "expand_universe", "reason": "low_sample"},
        }

    # Respect user preference: avoid automatically proposing lower timeframes.
    if avoid_lower_tf and timeframe != preferred_timeframe:
        return {
            "recommendation_code": "INCREASE_SAMPLE_SIZE",
            "recommendation_text": (
                f"Normalizar al timeframe preferido ({preferred_timeframe}) y aumentar muestra por universo/splits. "
                "No bajar timeframe por defecto."
                + baseline_note
            ),
            "next_action_type": "expand_universe",
            "next_prompt_payload": {"focus": "expand_universe", "target_timeframe": preferred_timeframe},
        }

    if pf < 1 and strategy_family == "trend":
        return {
            "recommendation_code": "HOLD_BASELINE_TRY_NEW_FAMILY",
            "recommendation_text": (
                "PF<1 en familia trend. Mantener baseline actual y probar nueva familia de estrategia en setup homogéneo."
                + baseline_note
            ),
            "next_action_type": "new_strategy_family",
            "next_prompt_payload": {"focus": "new_strategy_family", "family": "trend", "style": "new_family"},
        }

    if is_oos is True and pf > 1:
        return {
            "recommendation_code": "BASELINE_CANDIDATE",
            "recommendation_text": "Resultado OOS con PF>1. Marcar como baseline candidato y correr sensibilidad a fees." + baseline_note,
            "next_action_type": "fee_sensitivity",
            "next_prompt_payload": {"focus": "fee_sensitivity"},
        }

    if pf > 1 and trades < low_sample_trades:
        if expansion_degraded:
            return {
                "recommendation_code": "MORE_WALKFORWARD",
                "recommendation_text": (
                    "Hay evidencia de degradación al expandir universo. No expandir más por ahora; aumentar evidencia con más historia/splits walk-forward."
                    + baseline_note
                ),
                "next_action_type": "walkforward",
                "next_prompt_payload": {"focus": "walkforward", "splits": "more", "mode": "scoring_only"},
            }
        if prioritize_universe:
            return {
                "recommendation_code": "INCREASE_SAMPLE_SIZE",
                "recommendation_text": (
                    "PF>1 con pocos trades. Priorizar aumento de muestra expandiendo universo de pares en 1h "
                    "antes de cualquier ajuste de timeframe."
                    + baseline_note
                ),
                "next_action_type": "expand_universe",
                "next_prompt_payload": {"focus": "expand_universe", "from_universe": last_result.get("universe_label", "top10")},
            }

    if pf > 1 and trades >= low_sample_trades:
        return {
            "recommendation_code": "MORE_WALKFORWARD",
            "recommendation_text": (
                "PF>1 con muestra razonable. Ejecutar más splits walk-forward y/o sensibilidad a fees."
                + (f" Robustness score={robustness_score:.1f}." if robustness_score is not None else "")
                + baseline_note
            ),
            "next_action_type": "walkforward",
            "next_prompt_payload": {"focus": "walkforward"},
        }

    if expansion_degraded:
        return {
            "recommendation_code": "HOLD_BASELINE_TRY_NEW_FAMILY",
            "recommendation_text": (
                "La expansión de universo degradó PF históricamente. Mantener universo robusto, aumentar evidencia con splits y probar nueva familia."
                + baseline_note
            ),
            "next_action_type": "new_strategy_family",
            "next_prompt_payload": {"focus": "new_strategy_family", "mode": "scoring_only"},
        }

    if prioritize_universe:
        return {
            "recommendation_code": "INCREASE_SAMPLE_SIZE",
            "recommendation_text": (
                "Priorizar aumento de muestra en 1h mediante universo/splits antes de variar timeframe."
                + baseline_note
            ),
            "next_action_type": "expand_universe",
            "next_prompt_payload": {"focus": "expand_universe"},
        }

    return {
        "recommendation_code": "RERUN_OR_DEBUG",
        "recommendation_text": "Sin regla concluyente. Repetir sanity run homogéneo y verificar datos/parseo." + baseline_note,
        "next_action_type": "rerun_or_debug",
        "next_prompt_payload": {"focus": "rerun_or_debug", "reason": "fallback"},
    }
