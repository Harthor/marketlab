from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Lasso, LassoCV, Ridge, RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODEL_ALIASES = {
    "ridge": "ridge",
    "ridgecv": "ridgecv",
    "lasso": "lasso",
    "lassocv": "lassocv",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "histgb": "histgb",
    "gradient_boost": "histgb",
    "gb": "histgb",
}


def is_baseline(model_name: str) -> bool:
    return model_name in {"naive0", "naive_last", "naive", "naive_mean"}


def _normalize_model_name(model_name: str) -> str:
    value = model_name.lower().strip()
    return MODEL_ALIASES.get(value, value)


def predict_baseline(kind: str, y_train: np.ndarray, size: int) -> np.ndarray:
    if kind == "naive0":
        return np.zeros(size, dtype=float)
    if kind in {"naive", "naive_last"}:
        if size <= 0:
            return np.array([], dtype=float)
        preds = np.empty(size, dtype=float)
        preds[0] = float(y_train[-1])
        if size > 1:
            preds[1:] = y_train[: size - 1]
        return preds
    if kind == "naive_mean":
        mean_val = float(np.nanmean(y_train)) if len(y_train) > 0 else 0.0
        return np.full(size, mean_val, dtype=float)
    raise ValueError(f"unknown baseline kind: {kind}")


def make_model(model_name: str, params: dict[str, Any], random_state: int = 42) -> Any:
    normalized = _normalize_model_name(model_name)
    if normalized == "ridge":
        alpha = float(params.get("alpha", 1.0))
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=alpha, random_state=random_state)),
            ]
        )
    if normalized == "ridgecv":
        alphas = params.get("alphas", [0.01, 0.1, 1.0, 10.0, 100.0])
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", RidgeCV(alphas=alphas)),
            ]
        )
    if normalized == "lasso":
        alpha = float(params.get("alpha", 1.0))
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", Lasso(alpha=alpha, random_state=random_state, max_iter=int(params.get("max_iter", 2000)))),
            ]
        )
    if normalized == "lassocv":
        alphas = params.get("alphas", [0.01, 0.1, 1.0, 10.0, 100.0])
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", LassoCV(
                    alphas=alphas,
                    random_state=random_state,
                    max_iter=int(params.get("max_iter", 5000)),
                )),
            ]
        )
    if normalized == "histgb":
        return HistGradientBoostingRegressor(
            learning_rate=float(params.get("learning_rate", 0.05)),
            max_depth=int(params.get("max_depth", 6)),
            max_iter=int(params.get("n_estimators", 300)),
            random_state=random_state,
        )

    if normalized in {"xgboost", "lightgbm"}:
        # Optional dependency with graceful fallback.
        try:
            if normalized == "xgboost":
                from xgboost import XGBRegressor

                return XGBRegressor(
                    n_estimators=int(params.get("n_estimators", 500)),
                    learning_rate=float(params.get("learning_rate", 0.05)),
                    max_depth=int(params.get("max_depth", 6)),
                    objective="reg:squarederror",
                    random_state=random_state,
                    subsample=float(params.get("subsample", 0.8)),
                    colsample_bytree=float(params.get("colsample_bytree", 0.8)),
                    n_jobs=int(params.get("n_jobs", 4)),
                )

            from lightgbm import LGBMRegressor

            return LGBMRegressor(
                n_estimators=int(params.get("n_estimators", 400)),
                learning_rate=float(params.get("learning_rate", 0.05)),
                max_depth=int(params.get("max_depth", 6)),
                random_state=random_state,
                n_jobs=int(params.get("n_jobs", 4)),
            )
        except Exception:
            return HistGradientBoostingRegressor(random_state=random_state)

    raise ValueError(f"unknown model: {model_name}")


def feature_importance(model: Any, feature_names: list[str]) -> tuple[list[str], list[float]]:
    estimator = model
    if isinstance(estimator, Pipeline):
        estimator = estimator[-1]

    if hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype=float)
    elif hasattr(estimator, "coef_"):
        coef = estimator.coef_
        values = np.abs(np.asarray(coef, dtype=float))
    else:
        return [], []

    if len(values) != len(feature_names):
        return feature_names, values.tolist()
    pairs = sorted(zip(feature_names, values, strict=False), key=lambda item: float(abs(item[1])), reverse=True)
    names, scores = zip(*pairs, strict=False) if pairs else ([], [])
    return list(names), list(map(float, scores))
