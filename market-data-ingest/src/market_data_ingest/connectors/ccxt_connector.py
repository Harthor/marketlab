"""Optional CCXT connector for crypto symbols."""

from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd

from .base import ConnectorError, PriceConnector


class CCXTConnector(PriceConnector):
    source = "ccxt"

    def __init__(self, exchange: str = "binance", venue: str = "crypto") -> None:
        self.exchange = exchange
        self.venue = venue

    def fetch_ohlcv(self, symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
        try:
            import ccxt
        except ImportError as exc:
            raise ConnectorError(
                "ccxt no está instalado. Si querés usar este conector, instalalo con `pip install ccxt` (origen opcional)."
            ) from exc

        exchange_module = getattr(ccxt, self.exchange, None)
        if exchange_module is None:
            raise ConnectorError(
                f"No existe el exchange '{self.exchange}' en ccxt. Ajustá --exchange con un valor válido."
            )

        exchange = exchange_module({"enableRateLimit": True})

        since = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
        until = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() * 1000)

        try:
            raw = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                params={"until": until},
            )
        except Exception as exc:
            msg = str(exc)
            if "API key" in msg.lower() or "permission" in msg.lower():
                raise ConnectorError(
                    "Este exchange requiere credenciales para ese endpoint. Dejalo como TODO hasta agregar API keys en el connector."
                ) from exc
            raise ConnectorError(f"Error en CCXT para {symbol}: {msg}") from exc

        if not raw:
            raise ConnectorError(f"No se recibió data desde ccxt para {symbol}")

        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume", "trades"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.set_index("ts")[["open", "high", "low", "close", "volume"]]
