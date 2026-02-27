"""Yahoo Finance connector (MVP)."""

from __future__ import annotations

import pandas as pd

from .base import ConnectorError, PriceConnector


class YFinanceConnector(PriceConnector):
    source = "yfinance"

    def __init__(self, venue: str = "NYSE") -> None:
        self.venue = venue

    def fetch_ohlcv(self, symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - exercised via integration
            raise ConnectorError(
                "No se encontró yfinance. Instalalo con `pip install yfinance`."
            ) from exc

        raw = yf.download(
            tickers=symbol,
            start=start,
            end=end,
            interval=timeframe,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if raw is None or raw.empty:
            raise ConnectorError(f"No se recibió data desde yfinance para {symbol}")

        # Compatibilidad defensiva si yfinance devuelve MultiIndex de columnas
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.droplevel(1, axis=1)

        rename = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
        raw = raw.rename(columns=rename)

        required = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required if col not in raw.columns]
        if missing:
            raise ConnectorError(
                f"Faltan columnas necesarias en yfinance para {symbol}: {missing}"
            )

        return raw[required].copy()
