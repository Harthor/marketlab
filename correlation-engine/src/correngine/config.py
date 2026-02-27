from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from marketlab_core.contracts import TIMESTAMP_COL
except Exception:
    TIMESTAMP_COL = "ts_utc"


def parse_windows(raw: str) -> tuple[int, ...]:
    if isinstance(raw, (list, tuple)):
        return tuple(int(v) for v in raw)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("windows no puede estar vacío")
    values = []
    for item in parts:
        value = int(item)
        if value <= 0:
            raise ValueError("Las ventanas deben ser > 0")
        values.append(value)
    return tuple(sorted(set(values)))


@dataclass(frozen=True)
class RunConfig:
    """Configuración del experimento de correlación."""

    dataset: str
    target: str = "returns_1d"
    timestamp: str = TIMESTAMP_COL
    max_lag: int = 30
    windows: tuple[int, ...] = (30, 90, 180)
    seed: int = 42
    bootstrap: int = 0
    top: int = 50
    min_effective_obs: int = 10
    distance_corr: bool = False
    output_root: str = "reports"
    cache_root: str = "~/.cache/correlation-engine"

    def as_dict(self) -> dict:
        data = asdict(self)
        data["windows"] = list(self.windows)
        data["dataset"] = str(Path(self.dataset).expanduser())
        data["output_root"] = str(Path(self.output_root).expanduser())
        data["cache_root"] = str(Path(self.cache_root).expanduser())
        return data
