"""Typer CLI for market-data-ingest."""

from __future__ import annotations

import typer

from .config import Paths
from .ingestion import run_download
from .logging_utils import configure_logging, get_logger
from .quality import quality_report
from .warehouse import build_warehouse

app = typer.Typer(help="MVP de ingestión de precios (acciones/ETFs/crypto) a parquet + DuckDB.")

logger = get_logger(__name__)


def _format_symbol_report(report: dict[str, object]) -> str:
    return (
        f"{report['symbol']} | rows={report['rows']} | "
        f"rango={report.get('from', 'n/a')} -> {report.get('to', 'n/a')} | "
        f"raw={report['raw_path']} | processed={report['processed_path']}"
    )


@app.command("download")
def download(
    symbols: str = typer.Option(..., "--symbols", help="Lista de símbolos separada por coma. Ej: AAPL,MSFT"),
    start: str = typer.Option(..., "--start", help="Fecha inicio YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="Fecha fin YYYY-MM-DD"),
    timeframe: str = typer.Option("1d", "--timeframe", help="1m, 5m, 1h, 1d, 1wk, 1mo"),
    source: str = typer.Option("yfinance", "--source", help="yfinance | ccxt"),
    exchange: str = typer.Option("binance", "--exchange", help="Exchange cuando usás ccxt"),
    venue: str = typer.Option("", "--venue", help="Venue opcional. Ej: NYSE"),
    root: str = typer.Option(".", "--root", help="Directorio raíz del repo (contiene data/)."),
    log_level: str = typer.Option("INFO", "--log-level", help="DEBUG, INFO, WARN, ERROR"),
) -> None:
    """Descargar OHLCV, guardar raw y parquet normalizado."""
    configure_logging(log_level)
    paths = Paths.default(root)
    report = run_download(
        paths=paths,
        symbols=symbols,
        start=start,
        end=end,
        timeframe=timeframe,
        source=source,
        exchange=exchange,
        venue=venue or None,
    )

    for row in report:
        typer.echo(_format_symbol_report(row))


@app.command("build-warehouse")
def build_warehouse_cmd(
    root: str = typer.Option(".", "--root", help="Directorio raíz del repo (contiene data/)."),
    log_level: str = typer.Option("INFO", "--log-level", help="DEBUG, INFO, WARN, ERROR"),
) -> None:
    """Crear/actualizar la tabla DuckDB `prices` sin duplicar filas."""
    configure_logging(log_level)
    try:
        summary = build_warehouse(Paths.default(root))
    except RuntimeError as exc:
        typer.echo(f"ERROR: {exc}")
        raise typer.Exit(code=1)
    typer.echo(
        "Resumen build-warehouse | "
        f"antes={summary['before_rows']} | incoming={summary['incoming_rows']} | insertadas={summary['inserted_rows']}"
    )


@app.command("quality-report")
def quality_report_cmd(
    root: str = typer.Option(".", "--root", help="Directorio raíz del repo (contiene data/)."),
    log_level: str = typer.Option("INFO", "--log-level", help="DEBUG, INFO, WARN, ERROR"),
) -> None:
    """Reporta estado por símbolo (filas, rango y gaps/sospechoso/outliers)."""
    configure_logging(log_level)
    reports = quality_report(Paths.default(root))

    if not reports:
        typer.echo("No hay filas en warehouse para reportar.")
        return

    for rep in reports:
        log_payload = rep.__dict__
        logger.info("quality_symbol_report", **log_payload)
        typer.echo(
            "{symbol} {timeframe} | rows={rows} | rango={date_min}->{date_max} "
            "| duplicados={duplicates} | null_rows={null_rows} | missing={missing_timestamps} | "
            "gaps={suspicious_gaps} | outliers={outliers}".format(
                **rep.__dict__
            )
        )


if __name__ == "__main__":
    app()
