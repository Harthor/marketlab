#!/usr/bin/env python3
"""Demo end-to-end sin llamadas de red (usa fixtures + precios sintéticos)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import polars as pl  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for item in (str(ROOT), str(SRC_ROOT)):
    if item not in sys.path:
        sys.path.insert(0, item)

from altdata_web_signals.config import PathConfig  # noqa: E402
from altdata_web_signals.fetchers.wikipedia import parse_wikipedia_payload  # noqa: E402
from altdata_web_signals.fetchers.rss import parse_rss_counts  # noqa: E402
from altdata_web_signals.dataset import build_research_dataset  # noqa: E402
from altdata_web_signals.storage import write_signal_frame  # noqa: E402
from reports.quick_signal_analysis import run_analysis  # noqa: E402
from reports.visualize_dataset import plot_dataset  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures"


def _write_synthetic_prices(
    root: Path,
    symbol: str,
    freq: str = "1d",
    source: str = "yfinance",
) -> Path:
    # Prices en formato simple (ts_utc + close), compatible con el builder.
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    close = 45000.0

    for day in range(365):
        ts = start + timedelta(days=day)
        close = close * (1.0 + 0.002 if day % 5 else 1.0 - 0.0015)
        rows.append({"ts_utc": ts, "close": float(round(close, 8))})

    frame = pl.DataFrame(rows)
    destination = root / source / symbol / freq
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / "BTC-USD_1d_demo.parquet"
    frame.write_parquet(out)
    return out


def _build_fixture_signals(signals_root: Path) -> None:
    wiki_payload = json.loads((FIXTURES / "wikipedia_sample.json").read_text(encoding="utf-8"))
    wiki_frame = parse_wikipedia_payload(
        payload=wiki_payload,
        topic="Bitcoin",
        start=datetime(2022, 1, 1, tzinfo=timezone.utc).date(),
        end=datetime(2022, 1, 3, tzinfo=timezone.utc).date(),
    )
    write_signal_frame(wiki_frame, signals_root=signals_root, source="wiki", topic="Bitcoin", freq="1d")

    rss_payload = (FIXTURES / "rss_sample.xml").read_text(encoding="utf-8")
    rss_frames = parse_rss_counts(
        feed_payload=rss_payload,
        keywords=["bitcoin", "apple", "nvidia"],
        start=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end=datetime(2022, 1, 3, tzinfo=timezone.utc),
    )
    for keyword, frame in rss_frames.items():
        write_signal_frame(frame, signals_root=signals_root, source="rss", topic=keyword, freq="1d")


def main() -> int:
    cfg = PathConfig.default(ROOT)
    signals_root = ROOT / "data" / "signals"
    signals_root.mkdir(parents=True, exist_ok=True)

    _build_fixture_signals(signals_root)
    _write_synthetic_prices(cfg.market_data_root, symbol="BTC-USD", freq="1d", source="yfinance")

    dataset = build_research_dataset(
        symbol="BTC-USD",
        freq="1d",
        signals_root=signals_root,
        prices_root=cfg.market_data_root,
        price_source="yfinance",
        datasets_root=cfg.datasets_root,
        start="2022-01-01",
        end="2022-12-31",
        fill_method="none",
        join="inner",
        returns_method="simple",
    )

    run_analysis(str(dataset), output_dir=str(ROOT / "reports"))
    plot_dataset(str(dataset), output_dir=str(ROOT / "reports"))

    print(f"dataset={dataset}")
    print(f"meta={dataset.with_suffix('.meta.json')}")
    print("analysis outputs -> reports/rolling_signal_correlations.csv, reports/cross_correlation_lags.csv")
    print("plot outputs -> reports/prices_and_returns.png, reports/corr_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
