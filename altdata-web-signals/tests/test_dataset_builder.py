from __future__ import annotations

from datetime import datetime, timezone
import json

import polars as pl

from altdata_web_signals.dataset import build_research_dataset
from altdata_web_signals.storage import write_signal_frame

try:
    from marketlab_core import validate_dataset_df
except Exception:  # pragma: no cover
    validate_dataset_df = None


def _build_prices(path):
    rows = [
        {"ts_utc": datetime(2022, 1, day, tzinfo=timezone.utc), "close": float(100 + day)}
        for day in range(1, 8)
    ]
    frame = pl.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def _build_signals(signals_root):
    # RSS: columna no canonical para validar normalización.
    rss_frame = pl.DataFrame(
        {
            "ts_utc": [datetime(2022, 1, day, tzinfo=timezone.utc) for day in range(1, 8)],
            "raw_count": [1, 2, None, 2, 1, 3, 0],
        }
    )
    write_signal_frame(frame=rss_frame, signals_root=signals_root, source="rss", topic="Apple", freq="1d")

    wiki_frame = pl.DataFrame(
        {
            "ts_utc": [datetime(2022, 1, day, tzinfo=timezone.utc) for day in range(1, 8)],
            "signal_wiki_bitcoin": [5, 4, 6, 7, 4, 3, 6],
        }
    )
    write_signal_frame(frame=wiki_frame, signals_root=signals_root, source="wiki", topic="Bitcoin", freq="1d")


def test_build_dataset_stable_schema_and_meta(tmp_path):
    symbol = "BTC-USD"
    freq = "1d"

    signals_root = tmp_path / "signals"
    prices_root = tmp_path / "market-data-ingest" / "data" / "processed"
    datasets_root = tmp_path / "data" / "datasets"

    price_path = prices_root / "yfinance" / symbol / freq / "BTC-USD_1d.parquet"
    _build_prices(price_path)
    _build_signals(signals_root)

    dataset_path = build_research_dataset(
        symbol=symbol,
        freq=freq,
        join="inner",
        fill_method="forward",
        signals_root=signals_root,
        prices_root=prices_root,
        price_source="yfinance",
        datasets_root=datasets_root,
        start="2022-01-01",
        end="2022-01-07",
    )
    expected = datasets_root / symbol / f"{freq}.parquet"
    assert dataset_path == expected

    frame = pl.read_parquet(dataset_path)
    assert frame.columns == [
        "ts_utc",
        "symbol",
        "close",
        "returns_1d",
        "signal_rss_apple",
        "signal_wiki_bitcoin",
        "coverage_signal_rss_apple",
        "coverage_signal_wiki_bitcoin",
    ]
    assert frame["symbol"].n_unique() == 1
    assert frame["symbol"][0] == symbol
    assert frame["coverage_signal_rss_apple"].to_list().count(0) == 1

    for col in ["coverage_signal_rss_apple", "coverage_signal_wiki_bitcoin"]:
        values = set(frame[col].unique().to_list())
        assert values.issubset({0, 1})

    assert frame.select(pl.col("coverage_signal_rss_apple")).min().item(0, 0) >= 0

    meta_path = datasets_root / symbol / f"{freq}.meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert "schema_version" in meta
    assert meta["symbol"] == symbol
    assert meta["freq"] == freq
    assert meta["join_mode"] == "inner"
    assert meta["fill_method"] == "forward"
    assert sorted(meta["sources"]) == ["rss", "wiki"]
    assert meta["topics"]["wiki"] == ["bitcoin"]
    assert meta["topics"]["rss"] == ["apple"]
    assert meta["keywords"]["wiki"] == ["bitcoin"]
    assert meta["keywords"]["rss"] == ["apple"]
    assert meta["ts_range"]["start"].endswith("00:00+00:00")
    assert meta["ts_range"]["end"].endswith("00:00+00:00")
    assert meta["returns_def"]["method"] == "simple"
    assert meta["returns_def"]["definition"] == "returns_1d = close / close.shift(1) - 1"
    assert isinstance(meta["missingness"], dict)
    assert "signal_rss_apple" in meta["missingness"]
    assert "signal_wiki_bitcoin" in meta["missingness"]
    assert meta["missingness"]["signal_rss_apple"]["coverage_ratio"] == 5 / 6
    assert meta["missingness"]["signal_wiki_bitcoin"]["coverage_ratio"] == 1.0
    assert "signals" in meta and isinstance(meta["signals"], list)
    assert all(
        isinstance(item, dict) and {"source", "topic", "keyword"}.issubset(item.keys())
        for item in meta["signals"]
    )
    assert isinstance(meta["dataset_hash"], str)
    assert len(meta["dataset_hash"]) == 64
    assert "code_version" in meta and isinstance(meta["code_version"], str)
    assert meta["coverage_columns"] == [
        "coverage_signal_rss_apple",
        "coverage_signal_wiki_bitcoin",
    ]

    if validate_dataset_df is not None:
        validate_input = frame.rename(
            {
                "ts_utc": "timestamp",
                "returns_1d": "target",
            }
        )
        signal_cols = [col for col in frame.columns if col.startswith("signal_")]
        validate_input = validate_input.rename(
            {col: f"feature_{idx}_{col.removeprefix('signal_')}" for idx, col in enumerate(signal_cols)}
        )
        report = validate_dataset_df(validate_input)
        assert report.ok


def test_build_dataset_graceful_without_signals(tmp_path):
    symbol = "BTC-USD"
    freq = "1d"

    prices_root = tmp_path / "market-data-ingest" / "data" / "processed"
    datasets_root = tmp_path / "data" / "datasets"
    price_path = prices_root / "yfinance" / symbol / freq / "BTC-USD_1d.parquet"

    _build_prices(price_path)

    dataset_path = build_research_dataset(
        symbol=symbol,
        freq=freq,
        join="outer",
        fill_method="none",
        signals_root=tmp_path / "signals",
        prices_root=prices_root,
        price_source="yfinance",
        datasets_root=datasets_root,
        start="2022-01-01",
        end="2022-01-07",
    )

    frame = pl.read_parquet(dataset_path)
    assert frame.columns == ["ts_utc", "symbol", "close", "returns_1d"]
    assert frame.height == 6

    meta = json.loads((datasets_root / symbol / f"{freq}.meta.json").read_text(encoding="utf-8"))
    assert meta["missingness"] == {}
    assert meta["coverage_columns"] == []


def test_build_dataset_falls_back_to_canonical_price_path(tmp_path):
    symbol = "BTC-USD"
    freq = "1d"

    prices_root = tmp_path / "data" / "processed"
    datasets_root = tmp_path / "data" / "datasets"
    # path legacy canónico esperado por algunos scripts/manual
    price_path = prices_root / symbol / f"{freq}.parquet"
    _build_prices(price_path)

    dataset_path = build_research_dataset(
        symbol=symbol,
        freq=freq,
        join="outer",
        fill_method="none",
        signals_root=tmp_path / "signals",
        prices_root=prices_root,
        price_source="yfinance",
        datasets_root=datasets_root,
        start="2022-01-01",
        end="2022-01-07",
    )

    frame = pl.read_parquet(dataset_path)
    assert frame.height == 6
