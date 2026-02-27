"""Runtime configuration for the altdata-web-signals project."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class PathConfig:
    """Resolved filesystem locations used by commands."""

    root: Path
    signals_root: Path
    datasets_root: Path
    cache_root: Path
    market_data_root: Path

    @classmethod
    def default(cls, root: str | Path = ".") -> "PathConfig":
        root_path = Path(root).expanduser().resolve()
        # Soporte de workspace central:
        # - MARKETLAB_WORKSPACE: raíz del monorepo de proyecto
        # - MARKETDATA_PROCESSED_DIR: raíz absoluta/relativa de data/processed
        workspace_root = Path(os.getenv("MARKETLAB_WORKSPACE", root_path.parent)).expanduser().resolve()
        env_processed = os.getenv("MARKETDATA_PROCESSED_DIR")
        market_data_processed = (
            Path(env_processed).expanduser().resolve()
            if env_processed is not None
            else workspace_root / "market-data-ingest" / "data" / "processed"
        )
        return cls(
            root=root_path,
            signals_root=root_path / "data" / "signals",
            datasets_root=root_path / "data" / "datasets",
            cache_root=root_path / ".cache" / "altdata-web-signals",
            market_data_root=market_data_processed,
        )


def slugify_topic(topic: str) -> str:
    """Normalize topic/source labels into filesystem-safe slugs."""

    value = topic.strip().lower()
    value = value.replace(" ", "_")
    keep = [ch for ch in value if ch.isalnum() or ch in ("_", "-")]
    return "".join(keep).strip("_") or "topic"
