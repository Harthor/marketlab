"""Wikipedia Pageviews API fetcher with derived signals and quality checks.

Wikimedia REST API:
    GET /metrics/pageviews/per-article/{project}/all-access/all-agents/{article}/daily/{start}/{end}
    Timestamps: YYYYMMDD00

Derived signals per topic:
    signal_wiki_{topic}           – raw daily pageviews (Int64)
    signal_wiki_{topic}_ma7       – 7-day moving average (Float64)
    signal_wiki_{topic}_delta     – day-to-day absolute change
    signal_wiki_{topic}_pct_change – percent change (winsorized [-1,1])
    signal_wiki_{topic}_zscore_30d – rolling 30-day z-score
    signal_wiki_{topic}_burst     – boolean flag when zscore > 2
    signal_wiki_{topic}_log_delta – log1p delta (stable for count data)

Quality checks:
    WIKI001 – no data returned (empty payload)
    WIKI002 – gap ratio > 10 % (missing days after fill)
    WIKI003 – zero-run > 7 consecutive days
    WIKI004 – spike: single day > 5× rolling median
    WIKI005 – stale: last observation > 3 days old
    WIKI006 – short history (< 180 rows after transform)
    WIKI007 – negative values (should never happen)
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ..config import slugify_topic
from ..core import normalize_timezone
from ..http import ApiClient
from ..storage import write_signal_frame
from ..transforms import add_asof_utc, add_delta_and_pct, add_delta_log1p, add_zscore_rolling

logger = logging.getLogger(__name__)

WIKI_ENDPOINT = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    "/{project}/all-access/all-agents/{article}/daily/{start}/{end}"
)

# Wikimedia API returns at most ~1 year of daily data per request
MAX_CHUNK_DAYS = 365


# ---------------------------------------------------------------------------
# Quality check types
# ---------------------------------------------------------------------------

@dataclass
class QualityNote:
    """One quality check result."""
    code: str
    level: str  # "good" | "warning" | "poor"
    message: str
    value: float | int | None = None


@dataclass
class WikiQualityReport:
    """Aggregated quality report for a single topic."""
    topic: str
    notes: list[QualityNote] = field(default_factory=list)
    passed: bool = True

    def add(self, code: str, level: str, message: str, value: float | int | None = None) -> None:
        self.notes.append(QualityNote(code=code, level=level, message=message, value=value))
        if level == "poor":
            self.passed = False


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _to_wiki_timestamp(value: date | str) -> str:
    if isinstance(value, str):
        dt = datetime.fromisoformat(value).replace(tzinfo=UTC)
    else:
        dt = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    return dt.strftime("%Y%m%d00")


def _article_path(topic: str) -> str:
    return urllib.parse.quote(topic.strip().replace(" ", "_"))


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def parse_wikipedia_payload(
    payload: dict[str, Any],
    topic: str,
    start: date,
    end: date,
    *,
    freq: str = "1d",
    signal_prefix: str = "signal_wiki",
) -> pl.DataFrame:
    """Parse Wikimedia pageviews JSON into a polars DataFrame with date grid."""
    if "items" not in payload:
        raise ValueError("Respuesta de Wikipedia sin items")

    values: list[tuple[datetime, int]] = []
    for item in payload["items"]:
        ts_raw = str(item.get("timestamp", "")).strip()
        if len(ts_raw) >= 8:
            dt = datetime.strptime(ts_raw[:8], "%Y%m%d").replace(tzinfo=UTC)
        else:
            continue
        values.append((dt, int(item.get("views", 0))))

    if values:
        raw = pl.DataFrame({"ts_utc": [v[0] for v in values], "value": [v[1] for v in values]})
        raw = raw.with_columns(pl.col("ts_utc").dt.truncate(freq).alias("ts_utc"))
        raw = raw.group_by("ts_utc").agg(pl.col("value").sum().alias("value"))
    else:
        raw = pl.DataFrame({
            "ts_utc": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "value": pl.Series([], dtype=pl.Int64),
        })

    column = f"{signal_prefix}_{slugify_topic(topic)}"

    # Complete date grid for the range
    days = int((end - start).days)
    grid = [
        datetime.combine(start + timedelta(days=offset), datetime.min.time(), tzinfo=UTC)
        for offset in range(days + 1)
    ]
    all_days = pl.DataFrame({"ts_utc": grid})

    out = all_days.join(raw, on="ts_utc", how="left")
    out = out.with_columns(
        pl.col("value").fill_null(0).cast(pl.Int64).alias(column),
    ).select(["ts_utc", column])
    return normalize_timezone(out, ts_col="ts_utc")


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def add_wiki_transforms(
    df: pl.DataFrame,
    col: str,
) -> pl.DataFrame:
    """Add all derived signals for a Wikipedia pageviews column.

    Adds: _ma7, _delta, _pct_change, _zscore_30d, _burst, _log_delta, _log1p.
    Also adds asof_utc.
    """
    # 7-day moving average
    df = df.with_columns(
        pl.col(col).cast(pl.Float64).rolling_mean(window_size=7).alias(f"{col}_ma7"),
    )

    # delta + pct_change (winsorized)
    df = add_delta_and_pct(df, col)

    # rolling z-score 30d
    df = add_zscore_rolling(df, col, window=30)

    # burst flag: zscore > 2
    zscore_col = f"{col}_zscore_30d"
    df = df.with_columns(
        pl.when(pl.col(zscore_col).is_not_null() & (pl.col(zscore_col) > 2.0))
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .cast(pl.Int8)
        .alias(f"{col}_burst"),
    )

    # log1p delta (for count data)
    df = add_delta_log1p(df, col)

    # asof_utc: Wikipedia data for day T is available by T+1 00:00 UTC
    df = add_asof_utc(df)

    return df


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def run_quality_checks(
    df: pl.DataFrame,
    col: str,
    topic: str,
) -> WikiQualityReport:
    """Run WIKI001–WIKI007 quality checks on the pageviews DataFrame."""
    report = WikiQualityReport(topic=topic)

    n_rows = len(df)

    # WIKI001 – empty data
    if n_rows == 0:
        report.add("WIKI001", "poor", f"No data returned for topic '{topic}'")
        return report

    series = df[col]

    # WIKI007 – negative values
    n_negative = int(series.filter(series < 0).len())
    if n_negative > 0:
        report.add("WIKI007", "poor", f"{n_negative} negative pageview values detected", n_negative)

    # WIKI002 – gap ratio (null before fill → we check zeros since we filled nulls with 0)
    # Since we already filled nulls with 0, count zeros as potential gaps
    n_zeros = int(series.filter(series == 0).len())
    gap_ratio = n_zeros / n_rows if n_rows > 0 else 0.0
    if gap_ratio > 0.10:
        report.add(
            "WIKI002",
            "warning",
            f"Gap ratio {gap_ratio:.1%} ({n_zeros}/{n_rows} zero-days) exceeds 10%",
            round(gap_ratio, 4),
        )
    else:
        report.add("WIKI002", "good", f"Gap ratio {gap_ratio:.1%} OK", round(gap_ratio, 4))

    # WIKI003 – consecutive zero runs > 7
    values = series.to_list()
    max_zero_run = 0
    current_run = 0
    for v in values:
        if v == 0:
            current_run += 1
            max_zero_run = max(max_zero_run, current_run)
        else:
            current_run = 0

    if max_zero_run > 7:
        report.add(
            "WIKI003",
            "warning",
            f"Longest consecutive zero-run is {max_zero_run} days (> 7)",
            max_zero_run,
        )
    else:
        report.add("WIKI003", "good", f"Max zero-run {max_zero_run} days OK", max_zero_run)

    # WIKI004 – spike detection (single day > 5× rolling 14d median)
    if n_rows >= 14:
        spike_df = df.with_columns(
            pl.col(col).cast(pl.Float64).rolling_median(window_size=14).alias("_med14"),
        )
        spike_df = spike_df.filter(
            (pl.col("_med14") > 0) & (pl.col(col) > pl.col("_med14") * 5),
        )
        n_spikes = len(spike_df)
        if n_spikes > 0:
            report.add(
                "WIKI004",
                "warning",
                f"{n_spikes} spike(s) detected (> 5× rolling 14d median)",
                n_spikes,
            )
        else:
            report.add("WIKI004", "good", "No spikes detected", 0)
    else:
        report.add("WIKI004", "good", "Too few rows for spike detection", 0)

    # WIKI005 – stale data (last observation > 3 days old)
    last_ts = df["ts_utc"].max()
    if last_ts is not None:
        staleness = (datetime.now(tz=UTC) - last_ts).days
        if staleness > 3:
            report.add(
                "WIKI005",
                "warning",
                f"Data is {staleness} days stale (last: {last_ts.date()})",
                staleness,
            )
        else:
            report.add("WIKI005", "good", f"Data freshness OK ({staleness}d)", staleness)

    # WIKI006 – short history
    if n_rows < 180:
        report.add(
            "WIKI006",
            "warning",
            f"Short history: {n_rows} rows (< 180 recommended)",
            n_rows,
        )
    else:
        report.add("WIKI006", "good", f"History length {n_rows} rows OK", n_rows)

    return report


# ---------------------------------------------------------------------------
# Fetch orchestrator
# ---------------------------------------------------------------------------

def _fetch_chunks(
    client: ApiClient,
    topic: str,
    start_date: date,
    end_date: date,
    *,
    project: str,
    freq: str,
    signal_prefix: str,
) -> pl.DataFrame:
    """Fetch Wikipedia pageviews in chunks of MAX_CHUNK_DAYS and concatenate."""
    frames: list[pl.DataFrame] = []
    chunk_start = start_date

    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=MAX_CHUNK_DAYS - 1), end_date)
        start_key = _to_wiki_timestamp(chunk_start)
        end_key = _to_wiki_timestamp(chunk_end)
        url = WIKI_ENDPOINT.format(
            project=project,
            article=_article_path(topic),
            start=start_key,
            end=end_key,
        )
        try:
            payload = client.get_json(url)
            frame = parse_wikipedia_payload(
                payload=payload,
                topic=topic,
                start=chunk_start,
                end=chunk_end,
                freq=freq,
                signal_prefix=signal_prefix,
            )
            frames.append(frame)
            logger.info("wiki chunk %s → %s: %d rows", chunk_start, chunk_end, len(frame))
        except Exception as exc:
            logger.warning("wiki chunk %s → %s failed: %s", chunk_start, chunk_end, exc)

        chunk_start = chunk_end + timedelta(days=1)

    if not frames:
        col = f"{signal_prefix}_{slugify_topic(topic)}"
        return pl.DataFrame({
            "ts_utc": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            col: pl.Series([], dtype=pl.Int64),
        })

    combined = pl.concat(frames, how="vertical_relaxed")
    # Deduplicate (overlapping chunk boundaries)
    combined = combined.unique(subset=["ts_utc"]).sort("ts_utc")
    return combined


def fetch_wiki_series(
    topics: list[str],
    start: str,
    end: str,
    *,
    project: str = "en.wikipedia",
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    """Fetch Wikipedia pageviews, derive signals, run quality checks, write parquets.

    Returns list of written parquet paths.
    """
    client = ApiClient(cache_dir=cache_dir)
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()
    outputs: list[Path] = []

    for topic in topics:
        logger.info("Fetching Wikipedia pageviews: topic=%s range=%s→%s", topic, start, end)

        # Fetch raw pageviews (chunked for long ranges)
        raw_df = _fetch_chunks(
            client,
            topic,
            start_date,
            end_date,
            project=project,
            freq=freq,
            signal_prefix="signal_wiki",
        )

        col = f"signal_wiki_{slugify_topic(topic)}"

        # Run quality checks on raw data
        qc = run_quality_checks(raw_df, col, topic)
        for note in qc.notes:
            if note.level == "poor":
                logger.error("QC %s [%s]: %s", note.code, note.level, note.message)
            elif note.level == "warning":
                logger.warning("QC %s [%s]: %s", note.code, note.level, note.message)
            else:
                logger.info("QC %s [%s]: %s", note.code, note.level, note.message)

        # Apply transforms
        df = add_wiki_transforms(raw_df, col)

        # Write individual signal parquets (one per derived column)
        meta_cols = [c for c in ["ts_utc", "asof_utc"] if c in df.columns]
        signal_cols = [c for c in df.columns if c.startswith("signal_wiki_")]
        for scol in signal_cols:
            topic_slug = scol.removeprefix("signal_wiki_")
            frame = df.select(meta_cols + [scol])
            out_path = write_signal_frame(
                frame=frame,
                signals_root=signals_root,
                source="wiki",
                topic=topic_slug,
                freq=freq,
            )
            outputs.append(out_path)
            logger.info("wrote %s (%d rows)", out_path, len(frame))

    return outputs
