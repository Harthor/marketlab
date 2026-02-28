"""Dashboard v2 data service.

Reads correlation-engine and forecasting-backtest parquets/manifests
and assembles a DashboardRunData-compatible JSON payload for the frontend.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from django.conf import settings

from .utils import json_sanitize

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORRELATION_REPORTS = "correlation-engine/reports"
FORECAST_RUNS = "forecasting-backtest/runs"

# Feature prefix → card key mapping
CARD_PREFIXES: dict[str, str] = {
    "signal_trends_": "trends",
    "signal_fng_": "fng",
    "signal_rss_crypto_": "rss",
    "signal_reddit_": "reddit",
    "signal_wiki_": "wikipedia",
    "signal_onchain_": "onchain",
}

# Window integer → RollingPoint.window string
WINDOW_LABELS: dict[int, str] = {
    30: "30d",
    60: "60d",
    90: "90d",
    180: "26w",
}

# Card display metadata
CARD_META: dict[str, dict[str, Any]] = {
    "trends": {
        "displayName": "Google Trends (BTC)",
        "simpleName": "Tendencias de búsqueda",
        "icon": "search",
        "signalId": "signal_trends",
        "dataFrequency": "weekly",
    },
    "fng": {
        "displayName": "Fear & Greed Index",
        "simpleName": "Miedo y codicia",
        "icon": "thermometer",
        "signalId": "signal_fng",
        "dataFrequency": "daily",
    },
    "rss": {
        "displayName": "RSS + FinBERT Sentiment",
        "simpleName": "Noticias crypto",
        "icon": "newspaper",
        "signalId": "signal_rss_crypto",
        "dataFrequency": "daily",
    },
    "reddit": {
        "displayName": "Reddit Sentiment",
        "simpleName": "Comunidad Reddit",
        "icon": "messages-off",
        "signalId": "signal_reddit",
        "dataFrequency": "insufficient",
    },
    "wikipedia": {
        "displayName": "Wikipedia Pageviews",
        "simpleName": "Atención pública",
        "icon": "book-open",
        "signalId": "signal_wiki",
        "dataFrequency": "daily",
    },
    "onchain": {
        "displayName": "On-Chain Metrics",
        "simpleName": "Datos on-chain",
        "icon": "link",
        "signalId": "signal_onchain",
        "dataFrequency": "daily",
    },
}


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------

def _workspace_root() -> Path:
    return getattr(settings, "MARKETLAB_WORKSPACE", Path(__file__).resolve().parents[2]).resolve()


def _find_latest_complete_run(reports_dir: Path) -> Path | None:
    """Find the most recent correlation run with status=complete."""
    if not reports_dir.is_dir():
        return None
    candidates = []
    for d in reports_dir.iterdir():
        if not d.is_dir():
            continue
        summary = d / "summary.json"
        if summary.exists():
            try:
                data = json.loads(summary.read_text())
                if data.get("status") == "complete":
                    candidates.append((d, d.stat().st_mtime))
            except Exception:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _read_parquet_safe(path: Path) -> pd.DataFrame | None:
    """Read a parquet file, returning None on failure."""
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None on failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Feature → card mapping
# ---------------------------------------------------------------------------

def _feature_to_card(feature: str) -> str | None:
    """Map a feature column name to its card key."""
    for prefix, card_key in CARD_PREFIXES.items():
        if feature.startswith(prefix):
            return card_key
    return None


def _safe_float(value: Any) -> float | None:
    """Convert to float, returning None for NaN/inf."""
    if value is None:
        return None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# State determination
# ---------------------------------------------------------------------------

def _determine_state(
    abs_corr: float | None,
    p_value: float | None,
    n_obs: int | None,
    stability: float | None = None,
) -> str:
    """Determine signal state: green/yellow/orange/blocked."""
    if n_obs is not None and n_obs < 60:
        return "blocked"
    if n_obs is not None and n_obs < 180:
        return "orange"
    if abs_corr is not None and p_value is not None:
        if abs_corr >= 0.20 and p_value <= 0.05:
            return "green"
        if abs_corr >= 0.12 or p_value <= 0.10:
            return "yellow"
    return "orange"


def _relationship_kind(lead_lag: str | None, best_lag: int | None) -> str:
    if best_lag is not None and best_lag == 0:
        return "synchronous"
    if lead_lag == "feature_leads":
        return "predictive"
    if lead_lag == "target_leads":
        return "reactive"
    return "unknown"


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------

def _build_rolling_points(
    rolling_df: pd.DataFrame | None,
    card_features: list[str],
) -> list[dict[str, Any]]:
    """Build RollingPoint[] for a card from rolling_corr data."""
    if rolling_df is None or rolling_df.empty:
        return []
    filtered = rolling_df[rolling_df["feature"].isin(card_features)]
    if filtered.empty:
        return []
    # Pick the feature with the highest mean absolute correlation
    best_feature = (
        filtered.groupby("feature")["correlation"]
        .apply(lambda s: s.abs().mean())
        .idxmax()
    )
    subset = filtered[filtered["feature"] == best_feature]
    points = []
    for _, row in subset.iterrows():
        ts_val = row.get("timestamp")
        if ts_val is not None and hasattr(ts_val, "isoformat"):
            ts_str = ts_val.isoformat()
        else:
            ts_str = str(ts_val)
        window_int = int(row.get("window", 0))
        window_label = WINDOW_LABELS.get(window_int, f"{window_int}d")
        corr_val = _safe_float(row.get("correlation"))
        if corr_val is not None:
            points.append({"ts": ts_str, "window": window_label, "value": corr_val})
    return points


def _build_lag_profile(
    lag_df: pd.DataFrame | None,
    card_features: list[str],
    freq: str,
) -> list[dict[str, Any]]:
    """Build LagPoint[] for a card."""
    if lag_df is None or lag_df.empty:
        return []
    filtered = lag_df[lag_df["feature"].isin(card_features)]
    if filtered.empty:
        return []
    # Pick the feature with the highest best abs_correlation
    best_feature = (
        filtered.groupby("feature")["abs_correlation"]
        .max()
        .idxmax()
    )
    subset = filtered[filtered["feature"] == best_feature].sort_values("lag")
    unit = "week" if freq == "weekly" else "day"
    points = []
    for _, row in subset.iterrows():
        lag_val = int(row.get("lag", 0))
        corr_val = _safe_float(row.get("correlation"))
        p_val = _safe_float(row.get("p_value"))
        if corr_val is not None:
            points.append({"lag": lag_val, "unit": unit, "correlation": corr_val, "pValue": p_val})
    return points


def _build_normalized_overlay(
    rolling_df: pd.DataFrame | None,
    card_features: list[str],
) -> list[dict[str, Any]]:
    """Build normalizedOverlaySeries from rolling correlation data.

    We approximate this from the rolling_corr table:
    use the 30d/90d rolling correlation as a proxy signal overlay.
    For a full implementation, this would join price and signal time series.
    """
    # This is a simplified implementation - we return the rolling correlation
    # as the 'signal' line and a constant for 'price' (normalized)
    if rolling_df is None or rolling_df.empty:
        return []
    filtered = rolling_df[rolling_df["feature"].isin(card_features)]
    if filtered.empty:
        return []
    best_feature = (
        filtered.groupby("feature")["correlation"]
        .apply(lambda s: s.abs().mean())
        .idxmax()
    )
    # Pick the smallest window for higher resolution
    subset = filtered[filtered["feature"] == best_feature]
    windows = sorted(subset["window"].unique())
    if not windows:
        return []
    smallest_window = windows[0]
    window_data = subset[subset["window"] == smallest_window].sort_values("timestamp")
    if window_data.empty:
        return []
    points = []
    for _, row in window_data.iterrows():
        ts_val = row.get("timestamp")
        if ts_val is not None and hasattr(ts_val, "isoformat"):
            ts_str = ts_val.isoformat()
        else:
            ts_str = str(ts_val)
        corr_val = _safe_float(row.get("correlation"))
        if corr_val is not None:
            # Normalize: price = corr value, signal = abs(corr) * 100
            points.append({"ts": ts_str, "price": corr_val, "signal": abs(corr_val)})
    return points


def _build_regime_breakdown(
    advanced: dict[str, Any],
    card_features: list[str],
) -> list[dict[str, Any]]:
    """Build RegimeMetric[] from advanced_metrics.regime."""
    regime_data = advanced.get("regime", {})
    for feature in card_features:
        if feature in regime_data:
            regimes = regime_data[feature]
            return [
                {
                    "name": r.get("regime", "unknown"),
                    "correlation": _safe_float(r.get("correlation")),
                    "pValue": _safe_float(r.get("p_value")),
                    "n": _safe_int(r.get("n")),
                }
                for r in regimes
            ]
    return []


def _build_granger(
    advanced: dict[str, Any],
    card_features: list[str],
) -> dict[str, Any]:
    """Build GrangerMetric from advanced_metrics.granger."""
    granger_data = advanced.get("granger", {})
    for feature in card_features:
        if feature in granger_data:
            g = granger_data[feature]
            direction = g.get("direction", "pending")
            return {
                "available": direction != "pending",
                "direction": direction,
                "pValueForward": _safe_float(g.get("p_value_forward")),
                "pValueReverse": _safe_float(g.get("p_value_reverse")),
            }
    return {"available": False, "direction": "pending", "pValueForward": None, "pValueReverse": None}


def _build_bootstrap(
    advanced: dict[str, Any],
    card_features: list[str],
) -> dict[str, Any]:
    """Build BootstrapMetric from advanced_metrics.bootstrap."""
    boot_data = advanced.get("bootstrap", {})
    for feature in card_features:
        if feature in boot_data:
            b = boot_data[feature]
            return {
                "available": True,
                "pValueMaxStat": _safe_float(b.get("p_value_max_stat")),
                "ciLow": _safe_float(b.get("lower")),
                "ciHigh": _safe_float(b.get("upper")),
            }
    return {"available": False, "pValueMaxStat": None, "ciLow": None, "ciHigh": None}


def _build_asymmetry(
    advanced: dict[str, Any],
    card_features: list[str],
) -> dict[str, Any] | None:
    """Build AsymmetryMetric from advanced_metrics.asymmetry."""
    asym_data = advanced.get("asymmetry", {})
    for feature in card_features:
        if feature in asym_data:
            a = asym_data[feature]
            return {
                "negative": _safe_float(a.get("negative_corr")),
                "positive": _safe_float(a.get("positive_corr")),
                "delta": _safe_float(a.get("delta")),
                "dominantSide": a.get("dominant_side", "none"),
            }
    return None


def _build_confidence_breakdown(
    advanced: dict[str, Any],
    card_features: list[str],
) -> dict[str, Any] | None:
    """Build ConfidenceBreakdown from advanced_metrics.stability."""
    stab_data = advanced.get("stability", {})
    for feature in card_features:
        if feature in stab_data:
            s = stab_data[feature]
            total = _safe_float(s.get("total")) or 0
            return {
                "total": round(total),
                "strength": _safe_float(s.get("strength")),
                "consistency": _safe_float(s.get("consistency")),
                "regimeRobustness": _safe_float(s.get("regimeRobustness")),
                "significance": _safe_float(s.get("significance")),
                "sampleSufficiency": _safe_float(s.get("sampleSufficiency")),
                "directionality": _safe_float(s.get("directionality")),
            }
    return None


def _build_narrative(card_key: str, state: str) -> dict[str, Any]:
    """Build narrative copy for a signal card."""
    narratives: dict[str, dict[str, dict[str, str]]] = {
        "trends": {
            "simple": {
                "title": "Google Trends",
                "subtitle": "Tendencias de búsqueda",
                "summary": "Las búsquedas de Bitcoin en Google muestran patrones que preceden movimientos de precio.",
                "cta": "Ver análisis completo",
            },
            "pro": {
                "title": "Google Trends — Señales BTC",
                "subtitle": "Cross-correlación con precio BTC",
                "summary": "Análisis de lag, correlación rolling y causalidad de Granger entre search trends y returns.",
                "cta": "Explorar métricas avanzadas",
            },
        },
        "fng": {
            "simple": {
                "title": "Fear & Greed Index",
                "subtitle": "Miedo y codicia",
                "summary": "El índice de miedo y codicia captura el sentimiento general del mercado crypto.",
                "cta": "Ver análisis completo",
            },
            "pro": {
                "title": "Fear & Greed — Señal diaria",
                "subtitle": "Correlación con BTC returns",
                "summary": "Análisis de la relación entre FNG y retornos diarios de BTC con métricas de robustez.",
                "cta": "Explorar métricas avanzadas",
            },
        },
        "rss": {
            "simple": {
                "title": "Noticias Crypto",
                "subtitle": "RSS + Sentiment",
                "summary": "Volumen de noticias y sentimiento de titulares como señales del mercado.",
                "cta": "Ver análisis completo",
            },
            "pro": {
                "title": "RSS + FinBERT Sentiment",
                "subtitle": "NLP sobre feeds crypto",
                "summary": "Conteo de artículos, menciones BTC y sentimiento VADER sobre titulares de 5 fuentes.",
                "cta": "Explorar métricas avanzadas",
            },
        },
        "reddit": {
            "simple": {
                "title": "Reddit",
                "subtitle": "Comunidad crypto",
                "summary": "Aún no hay datos suficientes para analizar señales de Reddit.",
                "cta": "Datos insuficientes",
            },
            "pro": {
                "title": "Reddit Sentiment",
                "subtitle": "Pendiente de recolección",
                "summary": "Se necesitan al menos 60 días de datos para iniciar el análisis.",
                "cta": "Ver requisitos",
            },
        },
        "wikipedia": {
            "simple": {
                "title": "Wikipedia Pageviews",
                "subtitle": "Atención pública",
                "summary": "Las visitas a páginas de Wikipedia sobre Bitcoin reflejan el interés público general.",
                "cta": "Ver análisis completo",
            },
            "pro": {
                "title": "Wikipedia Pageviews — Señales BTC",
                "subtitle": "Pageviews diarios + señales derivadas",
                "summary": (
                    "Correlación entre pageviews de Bitcoin/Ethereum/Cryptocurrency y retornos BTC."
                ),
                "cta": "Explorar métricas avanzadas",
            },
        },
        "onchain": {
            "simple": {
                "title": "On-Chain Metrics",
                "subtitle": "Datos on-chain",
                "summary": "Métricas directas de la blockchain: TVL DeFi, stablecoins, mempool y fees.",
                "cta": "Ver análisis completo",
            },
            "pro": {
                "title": "On-Chain Metrics — BTC + ETH",
                "subtitle": "Mempool.space + DeFiLlama",
                "summary": (
                    "TVL Ethereum, supply stablecoins, mempool BTC y median fee rate como señales de mercado."
                ),
                "cta": "Explorar métricas avanzadas",
            },
        },
    }
    return narratives.get(card_key, narratives["reddit"])


def _build_card(
    card_key: str,
    card_features: list[str],
    corr_df: pd.DataFrame | None,
    lag_df: pd.DataFrame | None,
    lag_summary_df: pd.DataFrame | None,
    rolling_df: pd.DataFrame | None,
    advanced: dict[str, Any],
    freq: str,
) -> dict[str, Any]:
    """Build a complete SignalCardData dict for one card."""
    meta = CARD_META.get(card_key, CARD_META["reddit"])

    # Find the representative feature (highest abs correlation)
    best_feature = None
    best_corr = 0.0
    best_p = 1.0
    best_n = 0
    best_lag_val = 0
    best_lead_lag = "unknown"

    if corr_df is not None and not corr_df.empty:
        card_corr = corr_df[corr_df["feature"].isin(card_features)]
        if not card_corr.empty:
            idx = card_corr["pearson"].abs().idxmax()
            row = card_corr.loc[idx]
            best_feature = row["feature"]
            best_corr = _safe_float(row.get("pearson")) or 0.0
            best_p = _safe_float(row.get("pearson_p")) or 1.0
            best_n = _safe_int(row.get("n_obs")) or 0

    # Prioritize best_feature first so advanced metrics pick the most relevant one
    if best_feature and best_feature in card_features:
        card_features = [best_feature] + [f for f in card_features if f != best_feature]

    if lag_summary_df is not None and not lag_summary_df.empty and best_feature:
        lag_row = lag_summary_df[lag_summary_df["feature"] == best_feature]
        if not lag_row.empty:
            best_lag_val = _safe_int(lag_row.iloc[0].get("best_lag")) or 0
            best_lead_lag = lag_row.iloc[0].get("lead_lag", "unknown")

    state = _determine_state(abs(best_corr) if best_corr else None, best_p, best_n)

    # Force blocked for reddit (no data)
    if card_key == "reddit" and not card_features:
        state = "blocked"

    confidence_bd = _build_confidence_breakdown(advanced, card_features)
    confidence_total = confidence_bd["total"] if confidence_bd else 0

    unit = "week" if freq == "weekly" else "day"
    best_lead = {
        "value": abs(best_lag_val) if best_lag_val else 0,
        "unit": unit,
        "correlation": best_corr,
        "pValue": best_p,
        "kind": _relationship_kind(best_lead_lag, best_lag_val),
        "label": f"+{abs(best_lag_val)}{unit[0]} | r={best_corr:.2f}" if best_corr else "N/A",
    }

    # Build stats
    asym = _build_asymmetry(advanced, card_features)
    stab = confidence_bd

    stats_dict = {
        "primaryCorrelation": _safe_float(best_corr),
        "primaryPValue": _safe_float(best_p),
        "stabilityScore": stab["total"] if stab else None,
        "regimeBull": None,
        "regimeBear": None,
        "asymmetryNegative": asym["negative"] if asym else None,
        "asymmetryPositive": asym["positive"] if asym else None,
    }

    # Get regime bull/bear from advanced metrics
    regime_bd = _build_regime_breakdown(advanced, card_features)
    for r in regime_bd:
        if r["name"] == "bull":
            stats_dict["regimeBull"] = r["correlation"]
        elif r["name"] == "bear":
            stats_dict["regimeBear"] = r["correlation"]

    detail = {
        "cardKey": card_key,
        "selectedLead": best_lead,
        "normalizedOverlaySeries": _build_normalized_overlay(rolling_df, card_features),
        "rollingCorrelation": _build_rolling_points(rolling_df, card_features),
        "lagProfile": _build_lag_profile(lag_df, card_features, freq),
        "regimeBreakdown": regime_bd,
        "asymmetry": asym,
        "granger": _build_granger(advanced, card_features),
        "bootstrap": _build_bootstrap(advanced, card_features),
        "confidenceBreakdown": confidence_bd,
        "timelineNarrative": [],
        "dataQualityNotes": [],
    }

    card = {
        "cardKey": card_key,
        "signalId": meta["signalId"],
        "displayName": meta["displayName"],
        "simpleName": meta["simpleName"],
        "state": state,
        "icon": meta["icon"],
        "confidence": confidence_total,
        "confidenceBreakdown": confidence_bd,
        "bestLead": best_lead if state != "blocked" else None,
        "sampleSize": best_n if best_n > 0 else None,
        "minSampleRequired": 180,
        "relationshipKind": _relationship_kind(best_lead_lag, best_lag_val),
        "dataFrequency": meta["dataFrequency"],
        "narrative": _build_narrative(card_key, state),
        "stats": stats_dict,
        "detail": detail,
        "dataQualityNotes": [],
        "blockedReason": "Datos insuficientes" if state == "blocked" else None,
        "progress": {"current": best_n, "required": 60, "unit": "observations"} if state == "blocked" else None,
    }

    return card


# ---------------------------------------------------------------------------
# Forecast helpers
# ---------------------------------------------------------------------------

MODEL_DIR_MAP: dict[str, str] = {
    "btc-trends-naive-mean": "Naive Mean",
    "btc-trends-ridgecv-basic": "RidgeCV Basic",
    "btc-trends-lassocv-basic": "LassoCV Basic",
    "btc-trends-ridgecv-lagged": "RidgeCV Lagged",
}


def _build_forecast(workspace: Path) -> dict[str, Any] | None:
    """Build ForecastPanelData from forecast model runs.

    Each sub-directory in forecasting-backtest/runs/ represents one model.
    """
    forecast_dir = workspace / FORECAST_RUNS
    if not forecast_dir.is_dir():
        return None

    models: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    best_equity_dir: Path | None = None
    best_sharpe = -999.0

    for d in sorted(forecast_dir.iterdir()):
        if not d.is_dir():
            continue
        summary_path = d / "run_summary.json"
        if not summary_path.exists():
            continue

        summary = _read_json_safe(summary_path)
        if summary is None:
            continue

        trading = summary.get("metrics", {}).get("trading", {})
        if not trading:
            continue

        model_id = d.name.replace("btc-trends-", "").replace("-", "_")
        label = MODEL_DIR_MAP.get(d.name, d.name)
        sharpe = _safe_float(trading.get("sharpe"))
        cagr = _safe_float(trading.get("cagr"))
        max_dd = _safe_float(trading.get("max_drawdown"))
        hit_rate = _safe_float(trading.get("hit_rate"))

        # Convert cagr and max_drawdown to percentage
        if cagr is not None:
            cagr = round(cagr * 100, 2)
        if max_dd is not None:
            max_dd = round(max_dd * 100, 2)

        models.append({
            "modelId": model_id,
            "label": label,
            "sharpe": round(sharpe, 4) if sharpe is not None else None,
            "cagr": cagr,
            "maxDrawdown": max_dd,
            "hitRate": round(hit_rate, 4) if hit_rate is not None else None,
        })

        # Track best model for equity curve
        if sharpe is not None and sharpe > best_sharpe:
            best_sharpe = sharpe
            best_equity_dir = d

    # Load equity curve from the best model
    if best_equity_dir is not None:
        equity_tables = best_equity_dir / "tables"
        equity_df = _read_parquet_safe(equity_tables / "equity.parquet")
        if equity_df is not None and not equity_df.empty:
            for _, row in equity_df.iterrows():
                ts_val = row.get("ts_utc")
                if ts_val is not None and hasattr(ts_val, "isoformat"):
                    ts_str = ts_val.isoformat()
                else:
                    ts_str = str(ts_val)
                equity_curve.append({
                    "ts": ts_str,
                    "strategy": _safe_float(row.get("equity")) or 1.0,
                    "benchmark": 1.0,
                })

    if not models and not equity_curve:
        return None

    return {
        "available": True,
        "equityCurve": equity_curve,
        "models": models,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_dashboard_data() -> dict[str, Any]:
    """Assemble the complete DashboardRunData from all data sources."""
    workspace = _workspace_root()

    # Find latest correlation runs (one weekly, one daily)
    corr_reports = workspace / CORRELATION_REPORTS
    weekly_run = None
    daily_run = None

    if corr_reports.is_dir():
        runs = []
        for d in corr_reports.iterdir():
            if not d.is_dir():
                continue
            summary_path = d / "summary.json"
            if summary_path.exists():
                try:
                    s = json.loads(summary_path.read_text())
                    if s.get("status") == "complete":
                        runs.append((d, s, d.stat().st_mtime))
                except Exception:
                    continue
        runs.sort(key=lambda x: x[2], reverse=True)

        for run_dir, summary, _mtime in runs:
            dataset_path = summary.get("dataset_path", "")
            if "weekly" in dataset_path and weekly_run is None:
                weekly_run = (run_dir, summary)
            elif "daily" in dataset_path and daily_run is None:
                daily_run = (run_dir, summary)
            if weekly_run and daily_run:
                break

    # Build feature → card mapping from available runs
    card_features: dict[str, dict[str, list[str]]] = {
        "trends": {"features": [], "freq": "weekly"},
        "fng": {"features": [], "freq": "daily"},
        "rss": {"features": [], "freq": "daily"},
        "reddit": {"features": [], "freq": "daily"},
        "wikipedia": {"features": [], "freq": "daily"},
        "onchain": {"features": [], "freq": "daily"},
    }

    # Read parquets from runs
    weekly_corr_df = None
    weekly_lag_df = None
    weekly_lag_summary_df = None
    weekly_rolling_df = None
    weekly_advanced: dict[str, Any] = {}

    daily_corr_df = None
    daily_lag_df = None
    daily_lag_summary_df = None
    daily_rolling_df = None
    daily_advanced: dict[str, Any] = {}

    if weekly_run:
        run_dir, summary = weekly_run
        tables_dir = run_dir / "tables"
        weekly_corr_df = _read_parquet_safe(tables_dir / "correlations.parquet")
        weekly_lag_df = _read_parquet_safe(tables_dir / "lag.parquet")
        weekly_lag_summary_df = _read_parquet_safe(tables_dir / "lag_summary.parquet")
        weekly_rolling_df = _read_parquet_safe(tables_dir / "rolling_corr.parquet")
        weekly_advanced = summary.get("advanced_metrics", {})

        # Map features to cards
        if weekly_corr_df is not None:
            for f in weekly_corr_df["feature"].tolist():
                card = _feature_to_card(f)
                if card:
                    card_features[card]["features"].append(f)

    if daily_run:
        run_dir, summary = daily_run
        tables_dir = run_dir / "tables"
        daily_corr_df = _read_parquet_safe(tables_dir / "correlations.parquet")
        daily_lag_df = _read_parquet_safe(tables_dir / "lag.parquet")
        daily_lag_summary_df = _read_parquet_safe(tables_dir / "lag_summary.parquet")
        daily_rolling_df = _read_parquet_safe(tables_dir / "rolling_corr.parquet")
        daily_advanced = summary.get("advanced_metrics", {})

        if daily_corr_df is not None:
            for f in daily_corr_df["feature"].tolist():
                card = _feature_to_card(f)
                if card and f not in card_features[card]["features"]:
                    card_features[card]["features"].append(f)

    # Build signal cards
    signals = []
    for card_key in ["trends", "fng", "rss", "reddit", "wikipedia", "onchain"]:
        info = card_features[card_key]
        features = info["features"]
        freq = info["freq"]

        # Choose which run's data to use
        if freq == "weekly":
            corr_df = weekly_corr_df
            lag_df = weekly_lag_df
            lag_summary_df = weekly_lag_summary_df
            rolling_df = weekly_rolling_df
            advanced = weekly_advanced
        else:
            corr_df = daily_corr_df
            lag_df = daily_lag_df
            lag_summary_df = daily_lag_summary_df
            rolling_df = daily_rolling_df
            advanced = daily_advanced

        card = _build_card(
            card_key=card_key,
            card_features=features,
            corr_df=corr_df,
            lag_df=lag_df,
            lag_summary_df=lag_summary_df,
            rolling_df=rolling_df,
            advanced=advanced,
            freq=freq,
        )
        signals.append(card)

    # Build forecast
    forecast = _build_forecast(workspace)

    # Determine run_id from the newest run
    run_id = "dashboard-live"
    generated_at = datetime.now(timezone.utc).isoformat()
    if weekly_run:
        run_id = weekly_run[1].get("run_id", run_id)

    payload: dict[str, Any] = {
        "runId": run_id,
        "generatedAt": generated_at,
        "asset": "BTC-USD",
        "modeDefault": "simple",
        "signals": signals,
        "forecast": forecast,
    }

    return json_sanitize(payload)
