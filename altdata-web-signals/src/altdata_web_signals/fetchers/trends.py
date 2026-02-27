"""Optional Google Trends integration (best effort)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ..config import slugify_topic


def fetch_trend_series(keywords: list[str], start: str, end: str, *, country: str = "US") -> dict[str, pl.DataFrame]:
    """Best-effort fetch for Google Trends using pytrends.

    Nota: pytrends es frágil frente a cambios de HTML/ratelimits. Si falla,
    no rompe el flujo; se debe intentar en otro horario o con VPN/proxy.
    """

    try:
        from pytrends.request import TrendReq
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "pytrends no está instalado. Ejecutar con `pip install .[trends]` para esta fuente."
        ) from exc

    pytrends = TrendReq(hl="en-US", tz=0)
    payload: dict[str, Any] = {}

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
            ts_col = ser.columns[0]
            value_col = kw_norm
            frame = pl.from_pandas(ser[[ts_col, value_col]].rename(columns={ts_col: "ts_utc"}))
            frame = frame.rename({value_col: f"signal_trends_{slugify_topic(kw_norm)}"})
            frames[kw] = frame
            payload[kw] = frame.height
        except Exception:
            payload[kw] = 0

    if not frames:
        raise RuntimeError(f"No se pudo descargar tendencias para keywords={keywords}. payload={payload}")

    return frames
