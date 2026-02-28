"""Reddit crypto subreddit fetcher with FinBERT sentiment analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ..http import ApiClient
from ..storage import write_signal_frame
from ..transforms import add_asof_utc, add_delta, add_delta_log1p, add_zscore_rolling

DEFAULT_SUBREDDITS: list[str] = ["bitcoin", "cryptocurrency"]

REDDIT_TOP_URL = "https://www.reddit.com/r/{subreddit}/top.json"


def parse_reddit_payload(
    payload: dict[str, Any],
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Parse Reddit JSON listing into a list of post dicts.

    Each dict has keys: ``date``, ``title``, ``score``,
    ``num_comments``, ``has_btc``.
    """
    entries: list[dict[str, Any]] = []
    children = payload.get("data", {}).get("children", [])

    for child in children:
        data = child.get("data", {})
        created = data.get("created_utc")
        if created is None:
            continue

        ts = datetime.fromtimestamp(float(created), tz=UTC)
        if ts < start or ts > end:
            continue

        title = str(data.get("title", "") or "")
        day = ts.replace(hour=0, minute=0, second=0, microsecond=0)

        entries.append({
            "date": day,
            "title": title,
            "score": int(data.get("score", 0)),
            "num_comments": int(data.get("num_comments", 0)),
            "has_btc": "bitcoin" in title.lower() or "btc" in title.lower(),
        })

    return entries


def aggregate_reddit_entries(
    all_entries: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
) -> pl.DataFrame:
    """Aggregate parsed Reddit entries into a daily DataFrame.

    Signals:
    - signal_reddit_post_count, comment_count, score_mean, score_sum
    - signal_reddit_title_sentiment (FinBERT mean)
    - signal_reddit_btc_mention_count
    - signal_reddit_sentiment_finbert_{mean,std}
    - signal_reddit_{positive,negative}_ratio, neg_minus_pos
    - signal_reddit_sentiment_defined
    """
    from ..sentiment import finbert_batch_stats

    total_days = int((end.date() - start.date()).days) + 1
    day_range = [
        start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=i)
        for i in range(total_days)
    ]

    day_entries: dict[datetime, list[dict[str, Any]]] = {d: [] for d in day_range}
    for entry in all_entries:
        day = entry["date"]
        if day in day_entries:
            day_entries[day].append(entry)

    rows: list[dict[str, Any]] = []
    for day in sorted(day_range):
        entries = day_entries[day]
        post_count = len(entries)
        comment_count = sum(e["num_comments"] for e in entries)
        scores = [e["score"] for e in entries]
        score_sum = sum(scores)
        score_mean: float | None = score_sum / post_count if post_count > 0 else None
        btc_count = sum(1 for e in entries if e["has_btc"])

        titles = [e["title"] for e in entries if e["title"].strip()]
        stats = finbert_batch_stats(titles)

        rows.append({
            "ts_utc": day,
            "signal_reddit_post_count": post_count,
            "signal_reddit_comment_count": comment_count,
            "signal_reddit_score_mean": score_mean,
            "signal_reddit_score_sum": score_sum,
            "signal_reddit_title_sentiment": stats["mean"],
            "signal_reddit_btc_mention_count": btc_count,
            "signal_reddit_sentiment_finbert_mean": stats["mean"],
            "signal_reddit_sentiment_finbert_std": stats["std"],
            "signal_reddit_positive_ratio": stats["positive_ratio"],
            "signal_reddit_negative_ratio": stats["negative_ratio"],
            "signal_reddit_neg_minus_pos": stats["neg_minus_pos"],
        })

    schema = {
        "ts_utc": pl.Datetime("us", "UTC"),
        "signal_reddit_post_count": pl.Int64,
        "signal_reddit_comment_count": pl.Int64,
        "signal_reddit_score_mean": pl.Float64,
        "signal_reddit_score_sum": pl.Int64,
        "signal_reddit_title_sentiment": pl.Float64,
        "signal_reddit_btc_mention_count": pl.Int64,
        "signal_reddit_sentiment_finbert_mean": pl.Float64,
        "signal_reddit_sentiment_finbert_std": pl.Float64,
        "signal_reddit_positive_ratio": pl.Float64,
        "signal_reddit_negative_ratio": pl.Float64,
        "signal_reddit_neg_minus_pos": pl.Float64,
    }
    df = pl.DataFrame(rows, schema=schema)

    df = df.with_columns(
        (pl.col("signal_reddit_post_count") > 0)
        .cast(pl.Int8)
        .alias("signal_reddit_sentiment_defined"),
    )

    return df


def add_reddit_transforms(df: pl.DataFrame) -> pl.DataFrame:
    """Add stationarity transforms to Reddit DataFrame.

    New columns:
    - signal_reddit_post_count_{delta, zscore_7d, delta_log1p}
    - signal_reddit_comment_count_delta_log1p
    - signal_reddit_score_sum_delta_log1p
    - signal_reddit_sentiment_delta
    - signal_reddit_btc_mention_delta
    - signal_reddit_neg_sentiment_flag
    - asof_utc (T+1 00:00 UTC)
    """
    df = add_delta(df, "signal_reddit_post_count")
    df = add_zscore_rolling(df, "signal_reddit_post_count", window=7)
    df = add_delta_log1p(df, "signal_reddit_post_count")

    df = add_delta_log1p(df, "signal_reddit_comment_count")
    df = add_delta_log1p(df, "signal_reddit_score_sum")

    df = add_delta(df, "signal_reddit_title_sentiment")
    if "signal_reddit_title_sentiment_delta" in df.columns:
        df = df.rename({
            "signal_reddit_title_sentiment_delta": "signal_reddit_sentiment_delta",
        })

    df = add_delta(df, "signal_reddit_btc_mention_count")
    if "signal_reddit_btc_mention_count_delta" in df.columns:
        df = df.rename({
            "signal_reddit_btc_mention_count_delta": "signal_reddit_btc_mention_delta",
        })

    df = df.with_columns(
        pl.when(
            pl.col("signal_reddit_title_sentiment").is_not_null()
            & (pl.col("signal_reddit_title_sentiment") < -0.2)
        )
        .then(1)
        .otherwise(0)
        .alias("signal_reddit_neg_sentiment_flag")
    )

    df = add_asof_utc(df)

    return df


def fetch_reddit_signals(
    *,
    subreddits: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    """Fetch Reddit top posts from crypto subreddits and write signal parquets."""
    subs = subreddits or DEFAULT_SUBREDDITS
    end_dt = (
        datetime.fromisoformat(end).replace(tzinfo=UTC)
        if end
        else datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    start_dt = (
        datetime.fromisoformat(start).replace(tzinfo=UTC)
        if start
        else end_dt - timedelta(days=60)
    )
    end_dt = end_dt + timedelta(days=1) - timedelta(microseconds=1)

    client = ApiClient(cache_dir=cache_dir)
    all_entries: list[dict[str, Any]] = []

    for sub in subs:
        url = REDDIT_TOP_URL.format(subreddit=sub)
        try:
            payload = client.get_json(url, params={"t": "day", "limit": "100"})
        except Exception:
            continue
        entries = parse_reddit_payload(payload, start=start_dt, end=end_dt)
        all_entries.extend(entries)

    df = aggregate_reddit_entries(all_entries, start=start_dt, end=end_dt)
    df = add_reddit_transforms(df)

    meta_cols = [c for c in ["ts_utc", "asof_utc"] if c in df.columns]
    outputs: list[Path] = []
    for col in [c for c in df.columns if c.startswith("signal_reddit_")]:
        topic = col.removeprefix("signal_reddit_")
        frame = df.select(meta_cols + [col])
        outputs.append(
            write_signal_frame(
                frame=frame,
                signals_root=signals_root,
                source="reddit",
                topic=topic,
                freq=freq,
            )
        )

    return outputs
