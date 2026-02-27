"""Connector factory."""

from __future__ import annotations

from .base import ConnectorError, PriceConnector


def get_connector(source: str, exchange: str | None = None) -> PriceConnector:
    source_clean = source.strip().lower()

    if source_clean == "yfinance":
        from .yfinance import YFinanceConnector

        return YFinanceConnector()

    if source_clean == "ccxt":
        from .ccxt_connector import CCXTConnector

        return CCXTConnector(exchange=exchange or "binance")

    raise ConnectorError(f"Source '{source}' no soportado. Usá 'yfinance' o 'ccxt'.")
