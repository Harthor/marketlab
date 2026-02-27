"""Google Trends BTC fetcher — wraps pytrends with parquet persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from ..config import slugify_topic
from ..storage import write_signal_frame

DEFAULT_BTC_KEYWORDS: list[str] = ["bitcoin", "buy bitcoin", "bitcoin crash", "crypto"]


def _fetch_raw_trends(
    keywords: list[str],
    start: str,
    end: str,
    *,
    country: str = "US",
) -> dict[str, pl.DataFrame]:
    """Call pytrends and return {keyword: DataFrame} with ts_utc + signal column."""
    try:
        from pytrends.request import TrendReq
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "pytrends no instalado. Ejecutar: pip install .[trends]"
        ) from exc

    pytrends = TrendReq(hl="en-US", tz=0)
    frames: dict[str, pl.DataFrame] = {}

    for kw in keywords:
        kw_norm = kw.strip()
        if not kw_norm:
            continue
        try:
            pytrends.build_payload([kw_norm], timeframe=f"{start} {end}", geo=country)
            raw = pytrends.interest_over_time()
            if raw is None or raw.empty:
                continue
            ser = raw.reset_index()
            ts_col_name = ser.columns[0]
            frame = pl.from_pandas(ser[[ts_col_name, kw_norm]].rename(columns={ts_col_name: "ts_utc"}))
            signal_col = f"signal_trends_{slugify_topic(kw_norm)}"
            frame = frame.rename({kw_norm: signal_col})
            frames[kw_norm] = frame
        except Exception:
            continue

    return frames


def parse_trends_payload(
    raw_data: dict[str, list[dict[str, Any]]],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, pl.DataFrame]:
    """Parse pre-fetched trends data (for testing without pytrends).

    Expects ``{keyword: [{date: ISO, value: int}, ...]}``.
    Returns ``{keyword: DataFrame}`` with ``ts_utc`` and ``signal_trends_{slug}`` columns.
    """
    frames: dict[str, pl.DataFrame] = {}
    for kw, items in raw_data.items():
        if not items:
            continue
        dates = [datetime.fromisoformat(r["date"]).replace(tzinfo=UTC) for r in items]
        values = [int(r["value"]) for r in items]
        signal_col = f"signal_trends_{slugify_topic(kw)}"
        df = pl.DataFrame({"ts_utc": dates, signal_col: values}).sort("ts_utc")

        if start is not None:
            df = df.filter(pl.col("ts_utc") >= start)
        if end is not None:
            df = df.filter(pl.col("ts_utc") <= end)

        frames[kw] = df
    return frames


def fetch_trends_btc_signals(
    *,
    keywords: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    country: str = "US",
    signals_root: str | Path = "data/signals",
    freq: str = "1w",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    """Fetch Google Trends for BTC keywords and write signal parquets.

    Writes one parquet per keyword at:
    - trends_btc/{keyword_slug}/{freq}.parquet

    Default keywords: bitcoin, buy bitcoin, bitcoin crash, crypto.
    Default freq is ``1w`` (weekly) because Trends data is weekly.
    """
    kws = keywords or DEFAULT_BTC_KEYWORDS
    end_str = end or datetime.now(tz=UTC).strftime("%Y-%m-%d")
    start_str = start or (datetime.now(tz=UTC).replace(year=datetime.now(tz=UTC).year - 5)).strftime("%Y-%m-%d")

    frames = _fetch_raw_trends(kws, start_str, end_str, country=country)

    if not frames:
        raise RuntimeError(f"No trends data returned for keywords={kws}")

    outputs: list[Path] = []
    for kw, frame in frames.items():
        slug = slugify_topic(kw)
        outputs.append(
            write_signal_frame(
                frame=frame,
                signals_root=signals_root,
                source="trends_btc",
                topic=slug,
                freq=freq,
            )
        )

    return outputs
