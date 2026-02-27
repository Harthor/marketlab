from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "dataset": {"path": None},
    "target": "returns_1d",
    "features": None,
    "model": {
        "name": "ridge",
        "params": {},
    },
    "walk_forward": {
        "train_window_days": 730,
        "test_window_days": 92,
        "step_days": 92,
        "min_train_rows": 260,
        "min_test_rows": 30,
    },
    "imputation": {
        "strategy": "zero+coverage",
        "coverage_floor": 0.0,
        "max_fill_gap": 1,
    },
    "backtest": {
        "threshold": 0.0,
        "transaction_cost": 0.0004,
        "slippage": 0.0002,
        "initial_capital": 1.0,
    },
    "random_state": 42,
}


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_update(copy.deepcopy(base[key]), value)
        else:
            base[key] = value
    return base


def load_config(path: str | None) -> dict[str, Any]:
    base = copy.deepcopy(DEFAULT_CONFIG)
    if not path:
        return base
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if payload is None:
        return base
    if not isinstance(payload, dict):
        raise TypeError("config file must contain a YAML mapping")
    return _deep_update(base, payload)


def merge_cli_overrides(
    config: dict[str, Any],
    *,
    dataset: str | None = None,
    target: str | None = None,
    timestamp: str | None = None,
    model: str | None = None,
    output_root: str | None = None,
    features: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    output = copy.deepcopy(config)
    if dataset is not None:
        output.setdefault("dataset", {})
        output["dataset"]["path"] = str(dataset)
    if target is not None:
        output["target"] = target
    if timestamp is not None:
        output.setdefault("dataset", {})
        output["dataset"]["timestamp_col"] = timestamp
    if model is not None:
        output.setdefault("model", {})
        output["model"]["name"] = model
    if features is not None:
        output["features"] = features
    if output_root is not None:
        output["output_root"] = str(output_root)
    if run_id is not None:
        output["run_id"] = run_id
    return output


def config_fingerprint(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
