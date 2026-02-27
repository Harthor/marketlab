"""Unit test for idempotent upsert behavior with a duckdb shim."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from market_data_ingest.config import Paths

SCHEMA = [
    "ts_utc",
    "symbol",
    "venue",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "ingestion_ts",
    "checksum",
]


class _FakeDuckResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class _FakeDuckConnection:
    def __init__(self, state: dict[str, pd.DataFrame], path: str, registry: dict[str, list[pd.DataFrame]]):
        self._state = state
        self._path = path
        self._registry = registry

    def execute(self, query: str) -> _FakeDuckResult:
        query_lower = query.lower().strip()

        if query_lower.startswith("create table if not exists prices"):
            return _FakeDuckResult(None)

        if query_lower.startswith("create index if not exists"):
            return _FakeDuckResult(None)

        if query_lower.startswith("select count(*) from prices"):
            return _FakeDuckResult((len(self._state["prices"]),))

        if query_lower.startswith("create or replace temp table incoming"):
            frames = self._registry.get(self._path, [])
            if frames:
                self._state["incoming"] = pd.concat(frames, ignore_index=True)
            else:
                self._state["incoming"] = pd.DataFrame(columns=SCHEMA)
            return _FakeDuckResult(None)

        if query_lower.startswith("select count(*) from incoming"):
            return _FakeDuckResult((len(self._state["incoming"]),))

        if query_lower.startswith("insert into prices"):
            incoming = self._state.get("incoming", pd.DataFrame(columns=SCHEMA))
            if not incoming.empty:
                merged = pd.concat([self._state["prices"], incoming], ignore_index=True)
                self._state["prices"] = merged.drop_duplicates(
                    subset=["ts_utc", "symbol", "timeframe"],
                    keep="first",
                ).reset_index(drop=True)
            return _FakeDuckResult(None)

        if query_lower.startswith("select symbol, venue, timeframe"):
            return _FakeDuckResult([])

        raise RuntimeError(f"Query no soportada en fake duckdb: {query}")

    def close(self) -> None:
        return None


def _build_fake_duckdb() -> types.ModuleType:
    state_by_path: dict[str, dict[str, pd.DataFrame]] = {}
    incoming_by_path: dict[str, list[pd.DataFrame]] = {}

    def connect(db_path: str) -> _FakeDuckConnection:
        path = str(db_path)
        if path not in state_by_path:
            state_by_path[path] = {
                "prices": pd.DataFrame(columns=SCHEMA),
                "incoming": pd.DataFrame(columns=SCHEMA),
            }
        return _FakeDuckConnection(state=state_by_path[path], path=path, registry=incoming_by_path)

    def set_incoming(path: str, frames: list[pd.DataFrame]) -> None:
        incoming_by_path[str(path)] = frames

    module = types.ModuleType("duckdb")
    module.connect = connect
    module._set_incoming = set_incoming
    return module


def _sample_frame(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"], utc=True),
            "symbol": [symbol, symbol],
            "venue": ["NYSE", "NYSE"],
            "timeframe": ["1d", "1d"],
            "open": [1.0, 2.0],
            "high": [1.2, 2.2],
            "low": [0.8, 1.6],
            "close": [1.1, 2.1],
            "volume": [100.0, 120.0],
            "source": ["yfinance", "yfinance"],
            "ingestion_ts": [pd.Timestamp("2025-01-01T00:00:00Z"), pd.Timestamp("2025-01-01T00:00:00Z")],
            "checksum": ["a", "b"],
        }
    )


class TestWarehouseUpsert(unittest.TestCase):
    def test_build_warehouse_without_duckdb_fails_with_clear_message(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = Paths.default(tmp)
            paths.create()

            original_duck = sys.modules.pop("duckdb", None)
            original_warehouse = sys.modules.pop("market_data_ingest.warehouse", None)
            original_collect = None
            try:
                import importlib
                warehouse = importlib.import_module("market_data_ingest.warehouse")
                original_collect = warehouse._collect_parquet_files
                warehouse._collect_parquet_files = lambda _path: [Path("dummy.parquet")]
                with self.assertRaises(RuntimeError) as err:
                    warehouse.build_warehouse(paths)
                self.assertIn("duckdb no está instalado", str(err.exception))
            finally:
                if original_collect is not None and "warehouse" in locals():
                    warehouse._collect_parquet_files = original_collect
                if original_duck is None:
                    sys.modules.pop("duckdb", None)
                else:
                    sys.modules["duckdb"] = original_duck
                if original_warehouse is None:
                    sys.modules.pop("market_data_ingest.warehouse", None)
                else:
                    sys.modules["market_data_ingest.warehouse"] = original_warehouse

    def _run_two_builds_with_fake_dk(self, frames: list[pd.DataFrame]) -> tuple[dict[str, int], dict[str, int]]:
        with TemporaryDirectory() as tmp:
            fake_dk = _build_fake_duckdb()
            paths = Paths.default(tmp)
            paths.create()

            original_warehouse = sys.modules.get("market_data_ingest.warehouse")
            original_duck = sys.modules.get("duckdb")
            sys.modules["duckdb"] = fake_dk

            try:
                sys.modules.pop("market_data_ingest.warehouse", None)
                import importlib

                warehouse = importlib.import_module("market_data_ingest.warehouse")

                fake_dk._set_incoming(str(paths.warehouse_path), frames)
                original_collect = warehouse._collect_parquet_files
                warehouse._collect_parquet_files = lambda _path: [Path("dummy")]

                try:
                    first = warehouse.build_warehouse(paths)
                    second = warehouse.build_warehouse(paths)
                finally:
                    warehouse._collect_parquet_files = original_collect
                return first, second
            finally:
                if original_warehouse is None:
                    sys.modules.pop("market_data_ingest.warehouse", None)
                else:
                    sys.modules["market_data_ingest.warehouse"] = original_warehouse
                if original_duck is None:
                    sys.modules.pop("duckdb", None)
                else:
                    sys.modules["duckdb"] = original_duck

    def test_build_warehouse_is_idempotent_for_duplicates(self) -> None:
        first, second = self._run_two_builds_with_fake_dk([_sample_frame("AAPL")])

        self.assertEqual(first["inserted_rows"], 2)
        self.assertEqual(second["inserted_rows"], 0)

    def test_build_warehouse_handles_multiple_symbols(self) -> None:
        summary, _ = self._run_two_builds_with_fake_dk([_sample_frame("AAPL"), _sample_frame("MSFT")])
        self.assertEqual(summary["inserted_rows"], 4)


if __name__ == "__main__":
    unittest.main()
