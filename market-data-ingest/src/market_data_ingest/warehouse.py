"""DuckDB persistence and idempotent merge into prices table."""

from __future__ import annotations

from pathlib import Path

from .config import Paths
from .logging_utils import get_logger

logger = get_logger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS prices (
    ts_utc TIMESTAMP,
    symbol VARCHAR,
    venue VARCHAR,
    timeframe VARCHAR,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    source VARCHAR,
    ingestion_ts TIMESTAMP,
    checksum VARCHAR,
    PRIMARY KEY (ts_utc, symbol, timeframe)
)
"""


def _collect_parquet_files(processed_dir: Path) -> list[Path]:
    return [p for p in processed_dir.glob("**/*.parquet") if p.is_file()]


def _require_duckdb() -> object:
    try:
        import duckdb

        return duckdb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "duckdb no está instalado. Instalalo para construir el warehouse: `pip install duckdb` "
            "(o `pip install -e .[dev]` según tu entorno)."
        ) from exc


def build_warehouse(paths: Paths) -> dict[str, int]:
    paths.create()
    parquet_files = _collect_parquet_files(paths.processed_dir)

    if not parquet_files:
        logger.info("warehouse_no_files", path=str(paths.processed_dir))
        return {"before_rows": 0, "incoming_rows": 0, "inserted_rows": 0}

    duckdb = _require_duckdb()
    conn = None
    try:
        conn = duckdb.connect(str(paths.warehouse_path))
        conn.execute(CREATE_TABLE_SQL)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prices_symbol_timeframe ON prices(symbol, timeframe)")

        before = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]

        path_expr = str(paths.processed_dir / "**" / "*.parquet")
        safe_path = path_expr.replace("'", "''")
        conn.execute(
            f"CREATE OR REPLACE TEMP TABLE incoming AS "
            f"SELECT DISTINCT * FROM read_parquet('{safe_path}', union_by_name=True)"
        )
        incoming_rows = conn.execute("SELECT COUNT(*) FROM incoming").fetchone()[0]

        conn.execute(
            """
            INSERT INTO prices
            SELECT
                i.ts_utc, i.symbol, i.venue, i.timeframe,
                i.open, i.high, i.low, i.close, i.volume,
                i.source, i.ingestion_ts, i.checksum
            FROM incoming i
            WHERE NOT EXISTS (
                SELECT 1
                FROM prices p
                WHERE
                    p.ts_utc = i.ts_utc
                    AND p.symbol = i.symbol
                    AND p.timeframe = i.timeframe
            )
            """
        )

        after = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    finally:
        if conn is not None:
            conn.close()

    inserted = int(after - before)
    logger.info("warehouse_build_complete", before=int(before), incoming=int(incoming_rows), inserted=inserted)
    return {"before_rows": int(before), "incoming_rows": int(incoming_rows), "inserted_rows": inserted}


def read_prices(paths: Paths) -> list[tuple]:
    duckdb = _require_duckdb()
    conn = duckdb.connect(str(paths.warehouse_path))
    try:
        rows = conn.execute(
            "SELECT symbol, venue, timeframe, ts_utc, open, high, low, close, volume, source, ingestion_ts, checksum FROM prices"
        ).fetchall()
        return rows
    finally:
        conn.close()
