"""Filesystem + DuckDB-backed cache."""

from __future__ import annotations

import hashlib
import os
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from .config import get_settings
from .io import read_parquet, write_parquet


@dataclass
class CacheInfo:
    entries: int
    size_bytes: int
    root: str


class Cache:
    """Local cache where DataFrames are stored as parquet and objects as pickle."""

    def __init__(self, root: str | Path | None = None):
        settings = get_settings()
        self.root = Path(root or os.fspath(settings.cache_root)).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.data_root = self.root / "data"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "index.duckdb"

        self.db = duckdb.connect(str(self.db_path))
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                key VARCHAR PRIMARY KEY,
                artifact_type VARCHAR,
                created_at TIMESTAMP,
                expires_at TIMESTAMP,
                file_path VARCHAR,
                payload_type VARCHAR,
                file_size BIGINT
            )
            """
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _path_for_key(self, key: str, artifact: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        sub = self.data_root / digest[:2] / digest[2:4]
        sub.mkdir(parents=True, exist_ok=True)
        suffix = ".parquet" if artifact == "parquet" else ".pkl"
        return sub / f"{digest}{suffix}"

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return None

    def get(self, key: str) -> Any | None:
        key = str(key)
        row = self.db.execute(
            """
            SELECT artifact_type, file_path, expires_at, payload_type
            FROM cache_entries
            WHERE key = ?
            """,
            [key],
        ).fetchone()

        if row is None:
            return None

        artifact_type, file_path, expires_at, _payload_type = row
        expires_at_dt = self._parse_datetime(expires_at)
        if expires_at_dt and expires_at_dt <= self._now():
            self.delete(key)
            return None

        path = Path(file_path)
        if not path.exists():
            self.delete(key)
            return None

        if artifact_type == "parquet":
            return read_parquet(path)
        if artifact_type == "pickle":
            with path.open("rb") as handle:
                return pickle.load(handle)

        raise ValueError(f"Unknown artifact type '{artifact_type}' for key {key}")

    def set(self, key: str, obj: Any, ttl: int | float | timedelta | None = None) -> str:
        key = str(key)
        self.delete(key)

        expires_at = None
        now = self._now()
        if ttl is not None:
            if isinstance(ttl, (int, float)):
                expires_at = now + timedelta(seconds=float(ttl))
            else:
                expires_at = now + ttl

        if isinstance(obj, pl.DataFrame):
            artifact = "parquet"
            path = self._path_for_key(key, artifact)
            write_parquet(obj, path)
            payload_type = "polars.DataFrame"
        else:
            artifact = "pickle"
            path = self._path_for_key(key, artifact)
            with path.open("wb") as handle:
                pickle.dump(obj, handle)
            payload_type = type(obj).__name__

        self.db.execute(
            """
            INSERT INTO cache_entries (
                key, artifact_type, created_at, expires_at, file_path, payload_type, file_size
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [key, artifact, now, expires_at, os.fspath(path), payload_type, path.stat().st_size],
        )
        return key

    def delete(self, key: str) -> None:
        row = self.db.execute(
            "SELECT file_path FROM cache_entries WHERE key = ?",
            [key],
        ).fetchone()

        if row:
            path = Path(row[0])
            if path.exists():
                path.unlink()

        self.db.execute("DELETE FROM cache_entries WHERE key = ?", [key])

    def cache_info(self) -> CacheInfo:
        """Return cache summary."""

        row = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM cache_entries"
        ).fetchone()
        if row is None:
            return CacheInfo(entries=0, size_bytes=0, root=os.fspath(self.root))

        entries, size_bytes = row
        return CacheInfo(entries=int(entries), size_bytes=int(size_bytes), root=os.fspath(self.root))

    def cleanup(self) -> int:
        """Remove expired entries and return removed count."""

        removed = 0
        rows = self.db.execute(
            "SELECT key FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
            [self._now()],
        ).fetchall()

        for (key,) in rows:
            self.delete(key)
            removed += 1

        return removed
