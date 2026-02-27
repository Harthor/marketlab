#!/usr/bin/env python3
"""Fetch BTC-USD 1d OHLCV and persist an append-only research-ready parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

import pandas as pd

SCHEMA_VERSION = "1.0"
REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
DEFAULT_PROVIDER = "cryptocompare"
YFINANCE_PROVIDER = "yfinance"
STOOQ_PROVIDER = "stooq"
CRYPTOCOMPARE_PROVIDER = "cryptocompare"
COINGECKO_PROVIDER = "coingecko"

STOOQ_URL_TEMPLATE = "https://stooq.com/q/d/l/?s={symbol}&i=d"
CRYPTOCOMPARE_BASE_URL = "https://min-api.cryptocompare.com/data/v2/histoday"
CRYPTOCOMPARE_LIMIT = 2000
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range"
COINGECKO_USER_AGENT = "MarketLab/0.1 (contact: research@marketlab)"
COINGECKO_RATE_LIMIT_BACKOFF_SECONDS = 2
COINGECKO_RATE_LIMIT_RETRIES = 2

if sys.version_info < (3, 11):
    raise SystemExit("Requires Python >= 3.11 to run this script.")


def _is_rate_limited(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code == 429
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request = Request(url)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urlopen(request, timeout=60) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _fetch_json_with_retry(
    *,
    url: str,
    headers: dict[str, str] | None = None,
    max_retries: int,
    backoff_seconds: int,
    provider: str,
) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return _fetch_json(url, headers=headers)
        except Exception as exc:  # pragma: no cover
            if isinstance(exc, HTTPError) and exc.code == 429 and attempt < max_retries:
                wait = backoff_seconds * (2**attempt)
                print(f"WARN: {provider} devolvió 429. Reintentando en {wait}s (attempt {attempt + 1}/{max_retries}).")
                sleep(wait)
                continue
            raise


def _normalize_datetime(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, utc=True, errors="raise")
    return parsed.floor("D")


def _normalize_frame(frame: pd.DataFrame, source: str, index_as_date: bool = False) -> pd.DataFrame:
    normalized = frame.copy()
    if index_as_date:
        normalized["ts_utc"] = _normalize_datetime(normalized.index)
    if "ts_utc" not in normalized.columns:
        if "date" not in normalized.columns:
            raise ValueError(f"{source}: faltan columnas de fecha.")
        normalized["ts_utc"] = _normalize_datetime(normalized["date"])

    for col in REQUIRED_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    normalized["open"] = pd.to_numeric(normalized["open"], errors="raise")
    normalized["high"] = pd.to_numeric(normalized["high"], errors="raise")
    normalized["low"] = pd.to_numeric(normalized["low"], errors="raise")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="raise")
    normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(0)

    normalized = normalized.loc[:, ["ts_utc", "open", "high", "low", "close", "volume"]].copy()
    normalized = normalized.dropna(subset=["ts_utc"] + list(REQUIRED_COLUMNS[:-1]))
    if normalized["close"].isna().any():
        raise ValueError(f"{source}: descarga contiene NaN en OHLC.")
    if (normalized["close"] <= 0).any():
        raise ValueError(f"{source}: se detectó close <= 0.")

    return normalized.sort_values("ts_utc").reset_index(drop=True)


def _normalize_stooq(raw: pd.DataFrame, start: str, source_url: str) -> pd.DataFrame:
    normalized = raw.copy()
    normalized.columns = [str(col).lstrip("\ufeff").strip().lower() for col in normalized.columns]
    if "date" not in normalized.columns:
        raise ValueError(f"Respuesta CSV de stooq no trae columna date: {source_url}")

    start_ts = pd.Timestamp(start, tz="UTC")
    normalized["ts_utc"] = _normalize_datetime(normalized["date"])
    for col in REQUIRED_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    return _normalize_frame(normalized.loc[normalized["ts_utc"] >= start_ts], "stooq")


def _flatten_columns(columns: Any) -> list[str]:
    if not isinstance(columns, pd.MultiIndex):
        return [str(col).strip() for col in columns]

    flat: list[str] = []
    for col in columns.tolist():
        if isinstance(col, tuple) and col:
            if str(col[0]).strip():
                flat.append(str(col[0]).strip())
            elif str(col[-1]).strip():
                flat.append(str(col[-1]).strip())
            else:
                flat.append(str(col).strip())
        else:
            flat.append(str(col).strip())
    return flat


def _normalize_yfinance(raw: pd.DataFrame) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = _flatten_columns(raw.columns)
    raw = raw.copy()
    raw.columns = [str(col).strip().lower() for col in raw.columns]
    return _normalize_frame(raw, "yfinance", index_as_date=True)


def _normalize_cryptocompare(raw: pd.DataFrame, start: str, source_url: str) -> pd.DataFrame:
    if "time" not in raw.columns:
        raise ValueError(f"Respuesta de cryptocompare no trae columna time: {source_url}")

    normalized = raw.copy()
    normalized["ts_utc"] = _normalize_datetime(pd.to_datetime(normalized["time"], unit="s", utc=True, errors="raise"))
    if "volumefrom" not in normalized.columns:
        normalized["volumefrom"] = pd.NA
    normalized["volume"] = normalized["volumefrom"]

    for col in REQUIRED_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    start_ts = pd.Timestamp(start, tz="UTC")
    normalized = normalized.loc[normalized["ts_utc"] >= start_ts]
    if normalized.empty:
        return normalized.loc[:, ["ts_utc", *REQUIRED_COLUMNS]].copy().reset_index(drop=True)

    return _normalize_frame(normalized, "cryptocompare")


def _normalize_coingecko(raw: dict[str, Any], start: str, source_url: str) -> pd.DataFrame:
    if not isinstance(raw, dict):
        raise ValueError(f"Respuesta inválida de coingecko: {source_url}")
    if raw.get("error"):
        raise ValueError(f"coingecko devolvió error: {raw.get('error')}")

    prices = pd.DataFrame(raw.get("prices", []), columns=["ts", "close"])
    volumes = pd.DataFrame(raw.get("total_volumes", []), columns=["ts", "volume"])
    if prices.empty:
        return pd.DataFrame(columns=["ts_utc", *REQUIRED_COLUMNS])

    start_ts = pd.Timestamp(start, tz="UTC")
    prices["ts_utc"] = _normalize_datetime(pd.to_datetime(prices["ts"], unit="ms", utc=True, errors="raise"))
    prices = prices.dropna(subset=["ts_utc", "close"])
    prices["ts_day"] = prices["ts_utc"]
    if not volumes.empty:
        volumes["ts_utc"] = _normalize_datetime(pd.to_datetime(volumes["ts"], unit="ms", utc=True, errors="raise"))
        volumes = volumes.dropna(subset=["ts_utc", "volume"])
        volumes["ts_day"] = volumes["ts_utc"]

    prices = prices.loc[prices["ts_utc"] >= start_ts]
    if prices.empty:
        return pd.DataFrame(columns=["ts_utc", *REQUIRED_COLUMNS])

    daily_close = (
        prices[["ts_day", "ts_utc", "close"]]
        .sort_values("ts_utc")
        .groupby("ts_day", as_index=False)
        .agg(ts_utc=("ts_utc", "last"), close=("close", "last"))
    )

    if volumes.empty:
        daily_volume = pd.DataFrame({"ts_day": daily_close["ts_day"] + pd.Timedelta(0), "volume": [0.0] * len(daily_close)})
    else:
        daily_volume = (
            volumes[["ts_day", "volume"]]
            .sort_values("ts_day")
            .groupby("ts_day", as_index=False)
            .agg(volume=("volume", "last"))
        )

    merged = daily_close.merge(daily_volume, on="ts_day", how="left")
    merged["volume"] = pd.to_numeric(merged["volume"], errors="coerce").fillna(0)

    merged["open"] = merged["high"] = merged["low"] = merged["close"]
    merged = merged[["ts_utc", "open", "high", "low", "close", "volume"]]
    return _normalize_frame(merged, COINGECKO_PROVIDER)


def _load_existing(path: Path) -> pd.DataFrame | None:
    frame = pd.read_parquet(path)
    available = set(frame.columns)
    if not {"ts_utc", *REQUIRED_COLUMNS}.issubset(available):
        missing = sorted([col for col in ("ts_utc", *REQUIRED_COLUMNS) if col not in available])
        print(f"WARN: parquet existente ignorado para rebuild completo (faltan columnas: {missing}).")
        return None

    frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], utc=True, errors="raise").dt.floor("D")
    return frame.loc[:, ["ts_utc", *REQUIRED_COLUMNS]].sort_values("ts_utc").reset_index(drop=True)


def _backup_path(path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.stem}_backup_{timestamp}{path.suffix}")


def _rotate_existing_backup(path: Path) -> Path | None:
    if not path.exists():
        return None

    backup = _backup_path(path)
    try:
        path.rename(backup)
        print(f"INFO: parquet previo movido a backup: {backup}")
        return backup
    except OSError as exc:
        print(f"WARN: no se pudo hacer backup de {path} ({exc}); se sobrescribirá sin backup.")
        return None


def _stooq_symbol(symbol: str) -> str:
    # Stooq usa tickers sin separador; para BTC-USD debe usarse "btcusd".
    cleaned = (
        str(symbol)
        .strip()
        .lower()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
    )
    if cleaned in {"btcusd", "xbtusd"}:
        return "btcusd"
    return cleaned


def _split_symbol(symbol: str) -> tuple[str, str]:
    normalized = str(symbol).strip().replace("_", "-").upper()
    if "-" in normalized:
        base, quote = normalized.split("-", 1)
        base = base.strip()
        quote = quote.strip()
        if base and quote and quote.isalpha() and len(quote) == 3:
            return base, quote
    return "BTC", "USD"


def _fetch_yfinance(symbol: str, start: str) -> tuple[pd.DataFrame | None, str | None]:
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover (dependency availability)
        return None, str(exc)

    try:
        raw = yf.download(
            symbol,
            start=start,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
    except Exception as exc:
        return None, str(exc)

    if raw is None or raw.empty:
        return None, f"yfinance no devolvió filas para {symbol} desde {start}."

    try:
        return _normalize_yfinance(raw), None
    except Exception as exc:
        return None, str(exc)


def _fetch_stooq(symbol: str, start: str) -> tuple[pd.DataFrame | None, str | None, str]:
    stooq_symbol = _stooq_symbol(symbol)
    source_url = STOOQ_URL_TEMPLATE.format(symbol=stooq_symbol)
    try:
        raw = pd.read_csv(source_url)
    except Exception as exc:
        return None, str(exc), source_url

    if raw is None or raw.empty:
        return None, "DataFrame vacío", source_url

    try:
        normalized = _normalize_stooq(raw, start=start, source_url=source_url)
    except Exception as exc:
        return None, str(exc), source_url

    return normalized, None, source_url


def _fetch_cryptocompare(start: str, symbol: str = "BTC", quote: str = "USD") -> tuple[pd.DataFrame, str | None]:
    start_ts = pd.Timestamp(start, tz="UTC")
    to_ts = int(datetime.now(timezone.utc).timestamp())
    frames: list[pd.DataFrame] = []
    headers: dict[str, str] = {}
    api_key = os.getenv("CRYPTOCOMPARE_API_KEY")
    if api_key:
        headers["authorization"] = f"Apikey {api_key}"

    source_url = None

    while True:
        query = urlencode({"fsym": symbol, "tsym": quote, "limit": CRYPTOCOMPARE_LIMIT, "toTs": to_ts})
        request_url = f"{CRYPTOCOMPARE_BASE_URL}?{query}"
        try:
            payload = _fetch_json(request_url, headers=headers)
        except Exception as exc:
            raise ValueError(f"No se pudo consultar cryptocompare ({request_url}): {exc}")

        if not isinstance(payload, dict):
            raise ValueError(f"Respuesta no válida de cryptocompare: {request_url}")

        if str(payload.get("Response", "")).lower() != "success":
            message = payload.get("Message") or payload.get("Response")
            raise ValueError(f"cryptocompare respondió con error ({request_url}): {message}")

        rows = payload.get("Data", {}).get("Data")
        if not isinstance(rows, list) or not rows:
            break

        page = pd.DataFrame(rows)
        frames.append(_normalize_cryptocompare(page, start=start, source_url=request_url))

        earliest_ts = pd.to_datetime(page["time"], unit="s", utc=True, errors="coerce").min()
        if pd.isna(earliest_ts):
            break

        if earliest_ts < start_ts:
            break

        next_to_ts = int((earliest_ts - timedelta(days=1)).timestamp())
        if next_to_ts < 0 or next_to_ts >= to_ts:
            break
        to_ts = next_to_ts
        source_url = request_url

    if not frames:
        _fetch_cryptocompare.last_url = source_url
        return pd.DataFrame(columns=["ts_utc", *REQUIRED_COLUMNS]), source_url

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["ts_utc"]).sort_values("ts_utc").reset_index(drop=True)
    if start_ts is not None:
        merged = merged.loc[merged["ts_utc"] >= start_ts]
    _fetch_cryptocompare.last_url = source_url or request_url
    return merged, _fetch_cryptocompare.last_url


_fetch_cryptocompare.last_url = None


def _fetch_coingecko(
    *,
    start: str,
    symbol: str,
    quote: str,
) -> tuple[pd.DataFrame, str | None]:
    start_ts = int(pd.Timestamp(start, tz="UTC").timestamp())
    to_ts = int(datetime.now(timezone.utc).timestamp())
    if symbol.upper() != "BTC":
        print(f"WARN: CoinGecko endpoint usa BTC; se ignorará symbol={symbol} y se asume BTC.")
    params = {"vs_currency": quote.lower(), "from": start_ts, "to": to_ts}
    source_url = f"{COINGECKO_BASE_URL}?{urlencode(params)}"
    payload = _fetch_json_with_retry(
        url=source_url,
        headers={"User-Agent": COINGECKO_USER_AGENT},
        max_retries=COINGECKO_RATE_LIMIT_RETRIES,
        backoff_seconds=COINGECKO_RATE_LIMIT_BACKOFF_SECONDS,
        provider="coingecko",
    )
    return _normalize_coingecko(payload, start=start, source_url=source_url), source_url


def _fetch_prices(symbol: str, start: str) -> tuple[pd.DataFrame, str, str | None, list[str]]:
    warnings: list[str] = []
    base, quote = _split_symbol(symbol)

    # 1) cryptocompare primero
    try:
        cframe, cryptocompare_url = _fetch_cryptocompare(start, symbol=base, quote=quote)
    except Exception as exc:
        cframe = None
        if _is_rate_limited(exc):
            print(f"WARN: cryptocompare devolvió 429 ({symbol}): {exc}; probando CoinGecko.")
        else:
            print(f"WARN: cryptocompare sin datos/errores para {symbol} desde {start}: {exc}; probando CoinGecko.")
    else:
        if cframe is not None and not cframe.empty:
            return cframe, CRYPTOCOMPARE_PROVIDER, cryptocompare_url, warnings

    # 2) coingecko como fallback
    try:
        cgframe, cg_url = _fetch_coingecko(start=start, symbol=base, quote=quote)
    except Exception as exc:
        if _is_rate_limited(exc):
            print(f"WARN: CoinGecko devolvió 429 ({symbol}): {exc}; probando otros providers.")
        else:
            print(f"WARN: CoinGecko sin datos/errores para {symbol} desde {start}: {exc}; probando otros providers.")
    else:
        if cgframe is not None and not cgframe.empty:
            warnings.append("coingecko_no_ohlc_filled_from_close")
            return cgframe, COINGECKO_PROVIDER, cg_url, warnings

    # fallbacks legacy
    print("INFO: intentando fallback con yfinance.")
    yframe, yerror = _fetch_yfinance(symbol, start)
    if yframe is not None and not yframe.empty:
        return yframe, YFINANCE_PROVIDER, None, warnings
    if yerror:
        if _is_rate_limited(Exception(yerror)):
            print(f"WARN: yfinance devolvió 429 ({symbol}): {yerror}; probando Stooq.")
        else:
            print(f"WARN: yfinance sin datos/errores para {symbol} desde {start}: {yerror}; probando Stooq.")

    print("INFO: intentando fallback con Stooq.")
    sframe, serror, stooq_url = _fetch_stooq(symbol, start)
    if sframe is not None and not sframe.empty:
        return sframe, STOOQ_PROVIDER, stooq_url, warnings
    if serror:
        if _is_rate_limited(Exception(serror)):
            print(f"WARN: Stooq devolvió 429 ({symbol}): {serror}; no quedaron providers más.")
        else:
            print(f"WARN: Stooq sin datos/errores para {symbol} desde {start}: {serror}; no quedaron providers más.")

    raise ValueError(f"No se pudo obtener datos para {symbol} desde {start} ni con cryptocompare, coingecko, yfinance o stooq.")


def _merge_append(existing: pd.DataFrame | None, incoming: pd.DataFrame) -> pd.DataFrame:
    if existing is None:
        merged = incoming.copy()
    else:
        merged = pd.concat([existing, incoming], ignore_index=True)

    merged = merged.drop_duplicates(subset=["ts_utc"], keep="last").sort_values("ts_utc").reset_index(drop=True)
    merged["ts_utc"] = pd.to_datetime(merged["ts_utc"], utc=True, errors="raise").dt.floor("D")

    ts = merged["ts_utc"].sort_values().to_list()
    if len(ts) > 1:
        for left, right in zip(ts, ts[1:]):
            if right <= left:
                raise ValueError("ts_utc debe ser estrictamente creciente luego del merge.")

    return merged


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    with temp_path.open("wb") as handle:
        handle.write(content)
    os.replace(temp_path, path)


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    frame.to_parquet(temp_path, index=False, engine="pyarrow")
    os.replace(temp_path, path)
    return _sha256_file(path)


def _atomic_write_meta(payload: dict[str, Any], path: Path) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(path, serialized)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Actualiza BTC-USD daily OHLCV con append-only. "
            "Orden de providers: cryptocompare -> coingecko -> yfinance -> stooq (fallback legacy)."
        )
    )
    parser.add_argument("--symbol", default="BTC-USD", help="Ticker a descargar (default BTC-USD).")
    parser.add_argument("--start", default="2018-01-01", help="Fecha inicial YYYY-MM-DD (default 2018-01-01).")
    parser.add_argument(
        "--min-rows",
        type=int,
        default=365,
        help="Mínimo de filas para escribir el dataset final (default 365).",
    )
    parser.add_argument(
        "--out",
        default="data/datasets/BTC-USD/1d.parquet",
        help="Salida final parquet (default data/datasets/BTC-USD/1d.parquet).",
    )
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=3,
        help="No escribir si max(ts_utc) es anterior a hoy - N días (default 3).",
    )
    return parser.parse_args()


def _build_meta_payload(
    *,
    symbol: str,
    interval: str,
    rows: int,
    min_ts: pd.Timestamp | None,
    max_ts: pd.Timestamp | None,
    sha256: str,
    max_staleness_days: int,
    min_rows: int,
    provider: str,
    source_url: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "interval": interval,
        "provider": provider,
        "rows": rows,
        "min_ts_utc": str(min_ts) if min_ts is not None else None,
        "max_ts_utc": str(max_ts) if max_ts is not None else None,
        "sha256": sha256,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_staleness_days": max_staleness_days,
        "min_rows": min_rows,
    }
    if source_url:
        payload["source_url"] = source_url
    if warnings:
        payload["warnings"] = warnings
    return payload


def main() -> int:
    args = _parse_args()
    output = Path(args.out)
    interval = "1d"
    start = args.start

    existing: pd.DataFrame | None = None
    fetch_start = start
    if output.exists():
        existing = _load_existing(output)
        if existing is not None and len(existing) > 0:
            last_ts = pd.to_datetime(existing["ts_utc"], utc=True).max()
            fetch_start = (last_ts - timedelta(days=3)).strftime("%Y-%m-%d")

    downloaded, provider, source_url, warnings = _fetch_prices(args.symbol, start=fetch_start)

    merged = _merge_append(existing, downloaded)
    if len(merged) < args.min_rows:
        raise SystemExit(
            f"Gating bloqueó la salida: rows={len(merged)} < min_rows={args.min_rows}. "
            f"Reintentá con un rango/start más amplio."
        )

    max_ts = pd.to_datetime(merged["ts_utc"], utc=True).max()
    staleness_limit = datetime.now(timezone.utc).date() - timedelta(days=args.max_staleness_days)
    if pd.to_datetime(max_ts).date() < staleness_limit:
        raise SystemExit(
            f"Gating bloqueó la salida: max_date={max_ts.date()} < {staleness_limit} "
            f"(hoy - {args.max_staleness_days} días)."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    _rotate_existing_backup(output)
    temp_sha = _atomic_write_parquet(merged, output)
    meta_path = output.with_suffix(".meta.json")

    min_ts = pd.to_datetime(merged["ts_utc"], utc=True).min()
    meta_payload = _build_meta_payload(
        symbol=args.symbol,
        interval=interval,
        rows=len(merged),
        min_ts=min_ts,
        max_ts=max_ts,
        sha256=temp_sha,
        max_staleness_days=args.max_staleness_days,
        min_rows=args.min_rows,
        provider=provider,
        source_url=source_url,
        warnings=warnings,
    )
    _atomic_write_meta(meta_payload, meta_path)

    print(f"OK: {len(merged)} rows -> {output}")
    print(f"ts_range: {min_ts} -> {max_ts}")
    print(f"meta: {meta_path}")
    print(f"provider: {provider}")
    if source_url:
        print(f"source_url: {source_url}")
    print(f"sha256: {temp_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
