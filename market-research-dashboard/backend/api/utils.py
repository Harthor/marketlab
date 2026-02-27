from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None

    try:
        import numpy as np  # type: ignore

        if isinstance(obj, np.floating):
            return None if not np.isfinite(obj) else float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
    except Exception:
        pass

    if isinstance(obj, dict):
        return {key: json_sanitize(value) for key, value in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [json_sanitize(value) for value in obj]

    return obj


def json_sanitize(obj: Any) -> Any:
    return sanitize_for_json(obj)
