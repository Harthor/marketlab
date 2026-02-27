"""Connector interfaces."""

from __future__ import annotations

import abc
import pandas as pd


class ConnectorError(RuntimeError):
    """Raised when a source connector cannot fetch required data."""


class PriceConnector(abc.ABC):
    """Base interface for OHLCV connectors."""

    source: str

    @abc.abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """Fetch raw OHLCV for one symbol.

        Returns a DataFrame with a DatetimeIndex and at least
        open/high/low/close/volume columns.
        """
