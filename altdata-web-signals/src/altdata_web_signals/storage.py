"""Filesystem layout helpers."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .config import slugify_topic


def signal_path(signals_root: str | Path, source: str, topic: str, freq: str) -> Path:
    root = Path(signals_root)
    topic_slug = slugify_topic(topic)
    return root / source / topic_slug / f"{freq}.parquet"


def write_signal_frame(
    frame: pl.DataFrame,
    signals_root: str | Path,
    source: str,
    topic: str,
    freq: str,
) -> Path:
    out = signal_path(signals_root=signals_root, source=source, topic=topic, freq=freq)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(out)
    return out


def list_signal_frames(signals_root: str | Path, freq: str) -> list[Path]:
    root = Path(signals_root)
    return sorted(root.glob(f"*/**/{freq}.parquet"))


def read_parquet_safe(path: str | Path) -> pl.DataFrame:
    return pl.read_parquet(path)
