"""I/O helpers for parquet/csv and minimal local catalog metadata."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


def read_parquet(path: str | Path, **kwargs: Any) -> pl.DataFrame:
    return pl.read_parquet(str(path), **kwargs)


def write_parquet(df: pl.DataFrame, path: str | Path, **kwargs: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(str(target), **kwargs)
    return target


def read_csv(path: str | Path, **kwargs: Any) -> pl.DataFrame:
    return pl.read_csv(str(path), **kwargs)


def write_csv(df: pl.DataFrame, path: str | Path, **kwargs: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(str(target), **kwargs)
    return target


@dataclass
class CatalogAsset:
    path: str
    format: str
    rows: int | None = None
    columns: list[str] | None = None
    size_bytes: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class DataCatalog:
    """Minimal catalog that stores dataset locations + metadata in jsonl."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "catalog.jsonl"

    def register(
        self,
        dataset_path: str | Path,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> CatalogAsset:
        source = Path(dataset_path)
        if not source.is_absolute():
            source = self.root / source
        if not source.exists():
            raise FileNotFoundError(source)

        fmt = source.suffix.lower().lstrip(".") or "unknown"
        size_bytes = source.stat().st_size
        rows = None
        columns = None
        if fmt in {"parquet", "csv"}:
            frame = pl.read_parquet(source) if fmt == "parquet" else pl.read_csv(source)
            rows = frame.height
            columns = frame.columns

        asset = CatalogAsset(
            path=str(source.relative_to(self.root) if source.is_relative_to(self.root) else source),
            format=fmt,
            rows=rows,
            columns=list(columns) if columns is not None else None,
            size_bytes=size_bytes,
            metadata=dict(metadata or {}),
        )
        with self.manifest.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(asset), ensure_ascii=False) + "\n")
        return asset


    def list_assets(self) -> list[CatalogAsset]:
        if not self.manifest.exists():
            return []
        assets: list[CatalogAsset] = []
        with self.manifest.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line.strip())
                assets.append(
                    CatalogAsset(
                        path=raw["path"],
                        format=raw["format"],
                        rows=raw["rows"],
                        columns=raw["columns"],
                        size_bytes=raw["size_bytes"],
                        metadata=raw["metadata"],
                        created_at=raw["created_at"],
                    )
                )
        return assets


    def get(self, path: str) -> CatalogAsset | None:
        for asset in self.list_assets():
            if asset.path == path:
                return asset
        return None
