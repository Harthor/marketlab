"""Configuration helpers for data paths and pipeline defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    """Resolved file locations for one repository run."""

    root: Path
    raw_dir: Path
    processed_dir: Path
    warehouse_path: Path

    @classmethod
    def default(cls, root: Path | str = ".") -> "Paths":
        root_path = Path(root).expanduser().resolve()
        data_dir = root_path / "data"
        return cls(
            root=root_path,
            raw_dir=data_dir / "raw",
            processed_dir=data_dir / "processed",
            warehouse_path=data_dir / "warehouse.duckdb",
        )

    def create(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
