"""On-chain signal builder: Mempool.space (BTC) + DeFiLlama (ETH).

Signals:
    btc_mempool_vbytes      — mempool size in vbytes
    btc_median_fee_rate     — median fee rate from projected blocks
    eth_defi_tvl_total      — total Ethereum DeFi TVL
    eth_l2_tvl_total        — combined L2 TVL (Arbitrum + Optimism + Base)
    eth_stablecoin_supply   — USDT + USDC supply on Ethereum

All transforms follow the project convention: delta, pct_change, zscore, log1p.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from ..http import ApiClient
from ..storage import write_signal_frame
from ..transforms import (
    add_asof_utc,
    add_delta_and_pct,
    add_delta_log1p,
    add_zscore_rolling,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEMPOOL_API = "https://mempool.space/api"
DEFILLAMA_API = "https://api.llama.fi"
STABLECOINS_API = "https://stablecoins.llama.fi"

L2_CHAINS = ["Arbitrum", "Optimism", "Base"]

# Stablecoin IDs for DeFiLlama (USDT=1, USDC=2)
STABLECOIN_IDS = {"USDT": 1, "USDC": 2}

PREFIX = "signal_onchain"


# ---------------------------------------------------------------------------
# Quality checks (OC001-OC004, OC009)
# ---------------------------------------------------------------------------

@dataclass
class QualityNote:
    check_id: str
    level: str  # "pass" | "warn" | "fail"
    message: str


@dataclass
class OnchainQualityReport:
    signal_id: str
    notes: list[QualityNote] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(n.level == "fail" for n in self.notes):
            return "fail"
        if any(n.level == "warn" for n in self.notes):
            return "warn"
        return "pass"


def run_quality_checks(
    df: pl.DataFrame, col: str, signal_id: str
) -> OnchainQualityReport:
    """Run OC001-OC004 + OC009 quality checks on a signal column."""
    report = OnchainQualityReport(signal_id=signal_id)

    if df.is_empty():
        report.notes.append(QualityNote("OC004", "fail", "Empty dataframe"))
        return report

    series = df[col]

    # OC001: Duplicate timestamps
    ts = df["ts_utc"]
    dup_count = ts.len() - ts.n_unique()
    if dup_count > 0:
        report.notes.append(
            QualityNote("OC001", "fail", f"{dup_count} duplicate timestamps")
        )
    else:
        report.notes.append(QualityNote("OC001", "pass", "No duplicate timestamps"))

    # OC002: Gaps > 1 day
    if ts.len() >= 2:
        ts_sorted = ts.sort()
        diffs = ts_sorted.diff().dt.total_days().drop_nulls()
        gap_count = diffs.filter(diffs > 1).len()
        if gap_count > 0:
            report.notes.append(
                QualityNote("OC002", "warn", f"{gap_count} gaps > 1 day")
            )
        else:
            report.notes.append(QualityNote("OC002", "pass", "No gaps > 1 day"))

    # OC003: Flatline > 7 days
    if series.len() >= 8:
        vals = series.to_list()
        max_run = 1
        current_run = 1
        for i in range(1, len(vals)):
            if vals[i] is not None and vals[i - 1] is not None and vals[i] == vals[i - 1]:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
        if max_run > 7:
            report.notes.append(
                QualityNote("OC003", "warn", f"Flatline run of {max_run} days")
            )
        else:
            report.notes.append(QualityNote("OC003", "pass", "No flatline > 7 days"))

    # OC004: Impossible values (negatives where not expected, massive NaN)
    null_ratio = series.null_count() / series.len() if series.len() > 0 else 0
    if null_ratio > 0.5:
        report.notes.append(
            QualityNote("OC004", "fail", f"NaN ratio {null_ratio:.1%}")
        )
    else:
        neg_count = series.filter(series < 0).len()
        if neg_count > 0:
            report.notes.append(
                QualityNote("OC004", "warn", f"{neg_count} negative values")
            )
        else:
            report.notes.append(QualityNote("OC004", "pass", "No impossible values"))

    # OC009: Outlier MAD (|x - median| / MAD > 8)
    non_null = series.drop_nulls().cast(pl.Float64)
    if non_null.len() >= 30:
        median = non_null.median()
        mad = (non_null - median).abs().median()
        if mad and mad > 0:
            z_mad = ((non_null - median).abs() / mad)
            outlier_count = z_mad.filter(z_mad > 8).len()
            if outlier_count > 0:
                report.notes.append(
                    QualityNote("OC009", "warn", f"{outlier_count} MAD outliers (>8)")
                )
            else:
                report.notes.append(QualityNote("OC009", "pass", "No MAD outliers"))
        else:
            report.notes.append(QualityNote("OC009", "pass", "MAD=0 (constant)"))
    else:
        report.notes.append(QualityNote("OC009", "pass", "Insufficient data for MAD"))

    return report


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def _fetch_defillama_chain_tvl(
    client: ApiClient, chain: str, start_dt: datetime, end_dt: datetime
) -> pl.DataFrame:
    """Fetch historical TVL for a chain from DeFiLlama."""
    url = f"{DEFILLAMA_API}/v2/historicalChainTvl/{chain}"
    data = client.get_json(url)

    if not isinstance(data, list):
        logger.warning("Unexpected DeFiLlama response for %s: not a list", chain)
        return pl.DataFrame({"ts_utc": [], "tvl": []}).cast(
            {"ts_utc": pl.Datetime("us", "UTC"), "tvl": pl.Float64}
        )

    rows = []
    for item in data:
        ts = datetime.fromtimestamp(int(item["date"]), tz=UTC)
        ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if ts < start_dt or ts > end_dt:
            continue
        rows.append({"ts_utc": ts, "tvl": float(item.get("tvl", 0))})

    if not rows:
        return pl.DataFrame({"ts_utc": [], "tvl": []}).cast(
            {"ts_utc": pl.Datetime("us", "UTC"), "tvl": pl.Float64}
        )

    return pl.DataFrame(rows).sort("ts_utc").unique("ts_utc", keep="last")


def _fetch_stablecoin_supply(
    client: ApiClient, stablecoin_id: int, start_dt: datetime, end_dt: datetime
) -> pl.DataFrame:
    """Fetch historical supply for a stablecoin on Ethereum from DeFiLlama."""
    url = f"{STABLECOINS_API}/stablecoin/{stablecoin_id}"
    data = client.get_json(url)

    chain_balances = data.get("chainBalances", {}).get("Ethereum", {}).get("tokens", [])
    rows = []
    for item in chain_balances:
        ts = datetime.fromtimestamp(int(item["date"]), tz=UTC)
        ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if ts < start_dt or ts > end_dt:
            continue
        # circulating supply on Ethereum
        circulating = item.get("circulating", {})
        supply = float(circulating.get("peggedUSD", 0))
        rows.append({"ts_utc": ts, "supply": supply})

    if not rows:
        return pl.DataFrame({"ts_utc": [], "supply": []}).cast(
            {"ts_utc": pl.Datetime("us", "UTC"), "supply": pl.Float64}
        )

    return pl.DataFrame(rows).sort("ts_utc").unique("ts_utc", keep="last")


def _fetch_mempool_current(client: ApiClient) -> dict[str, Any]:
    """Fetch current mempool state from Mempool.space."""
    url = f"{MEMPOOL_API}/mempool"
    return client.get_json(url)


def _fetch_mempool_fee_blocks(client: ApiClient) -> list[dict[str, Any]]:
    """Fetch projected mempool blocks with fee rates."""
    url = f"{MEMPOOL_API}/v1/fees/mempool-blocks"
    data = client.get_json(url)
    if isinstance(data, list):
        return data
    return []


# ---------------------------------------------------------------------------
# Signal builders
# ---------------------------------------------------------------------------

def build_eth_defi_tvl(
    client: ApiClient, start_dt: datetime, end_dt: datetime
) -> pl.DataFrame:
    """Build eth_defi_tvl_total signal from DeFiLlama Ethereum TVL."""
    col = f"{PREFIX}_eth_defi_tvl_total"
    df = _fetch_defillama_chain_tvl(client, "Ethereum", start_dt, end_dt)
    if df.is_empty():
        return df
    df = df.rename({"tvl": col})

    # Transforms: pct_change_7d, zscore_90d
    df = df.with_columns(
        (pl.col(col) / pl.col(col).shift(7) - 1.0)
        .clip(-1.0, 1.0)
        .alias(f"{col}_pct_change_7d")
    )
    df = add_zscore_rolling(df, col, window=90)
    df = add_asof_utc(df)
    return df


def build_eth_l2_tvl(
    client: ApiClient, start_dt: datetime, end_dt: datetime
) -> pl.DataFrame:
    """Build eth_l2_tvl_total signal: sum of Arbitrum + Optimism + Base TVL."""
    col = f"{PREFIX}_eth_l2_tvl_total"

    frames = []
    for chain in L2_CHAINS:
        try:
            chain_df = _fetch_defillama_chain_tvl(client, chain, start_dt, end_dt)
            if not chain_df.is_empty():
                chain_df = chain_df.rename({"tvl": chain.lower()})
                frames.append(chain_df)
        except Exception as exc:
            logger.warning("Failed to fetch L2 chain %s: %s", chain, exc)

    if not frames:
        return pl.DataFrame()

    # Join all chains on ts_utc
    combined = frames[0]
    for other in frames[1:]:
        combined = combined.join(other, on="ts_utc", how="full", coalesce=True)
    combined = combined.sort("ts_utc")

    # Sum TVLs (fill nulls with 0)
    chain_cols = [c for c in combined.columns if c != "ts_utc"]
    combined = combined.with_columns(
        pl.sum_horizontal([pl.col(c).fill_null(0.0) for c in chain_cols]).alias(col)
    ).select(["ts_utc", col])

    # Transforms
    combined = combined.with_columns(
        (pl.col(col) / pl.col(col).shift(7) - 1.0)
        .clip(-1.0, 1.0)
        .alias(f"{col}_pct_change_7d")
    )
    combined = add_zscore_rolling(combined, col, window=90)
    combined = add_asof_utc(combined)
    return combined


def build_eth_stablecoin_supply(
    client: ApiClient, start_dt: datetime, end_dt: datetime
) -> pl.DataFrame:
    """Build eth_stablecoin_supply signal: USDT + USDC on Ethereum."""
    col = f"{PREFIX}_eth_stablecoin_supply"

    frames = []
    for name, sid in STABLECOIN_IDS.items():
        try:
            sdf = _fetch_stablecoin_supply(client, sid, start_dt, end_dt)
            if not sdf.is_empty():
                sdf = sdf.rename({"supply": name.lower()})
                frames.append(sdf)
        except Exception as exc:
            logger.warning("Failed to fetch %s supply: %s", name, exc)

    if not frames:
        return pl.DataFrame()

    combined = frames[0]
    for other in frames[1:]:
        combined = combined.join(other, on="ts_utc", how="full", coalesce=True)
    combined = combined.sort("ts_utc")

    supply_cols = [c for c in combined.columns if c != "ts_utc"]
    combined = combined.with_columns(
        pl.sum_horizontal([pl.col(c).fill_null(0.0) for c in supply_cols]).alias(col)
    ).select(["ts_utc", col])

    # Transforms: pct_change_7d, zscore_30d
    combined = combined.with_columns(
        (pl.col(col) / pl.col(col).shift(7) - 1.0)
        .clip(-1.0, 1.0)
        .alias(f"{col}_pct_change_7d")
    )
    combined = add_zscore_rolling(combined, col, window=30)
    combined = add_asof_utc(combined)
    return combined


def build_btc_mempool(client: ApiClient) -> pl.DataFrame:
    """Build btc_mempool_vbytes signal.

    NOTE: Mempool.space /mempool only returns the current state.
    There is no public historical endpoint for mempool size.
    We record today's snapshot — historical data accumulates over time.
    """
    col = f"{PREFIX}_btc_mempool_vbytes"
    try:
        data = _fetch_mempool_current(client)
    except Exception as exc:
        logger.warning("Failed to fetch mempool state: %s", exc)
        return pl.DataFrame()

    vsize = data.get("vsize", 0)
    now = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    df = pl.DataFrame({
        "ts_utc": [now],
        col: [float(vsize)],
    })
    df = add_asof_utc(df)
    return df


def build_btc_fee_rate(client: ApiClient) -> pl.DataFrame:
    """Build btc_median_fee_rate signal.

    NOTE: Like mempool, this only provides the current snapshot.
    """
    col = f"{PREFIX}_btc_median_fee_rate"
    try:
        blocks = _fetch_mempool_fee_blocks(client)
    except Exception as exc:
        logger.warning("Failed to fetch mempool fee blocks: %s", exc)
        return pl.DataFrame()

    if not blocks:
        return pl.DataFrame()

    # Extract median fee from first projected block
    median_fee = blocks[0].get("medianFee", 0)
    now = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    df = pl.DataFrame({
        "ts_utc": [now],
        col: [float(median_fee)],
    })
    df = add_asof_utc(df)
    return df


# ---------------------------------------------------------------------------
# Transforms for wide dataset columns
# ---------------------------------------------------------------------------

def add_onchain_transforms(df: pl.DataFrame) -> pl.DataFrame:
    """Add stationarity transforms to all on-chain signal columns."""
    for col in list(df.columns):
        if not col.startswith(PREFIX) or col == "ts_utc" or col == "asof_utc":
            continue
        # Skip columns that are already transforms
        if any(col.endswith(s) for s in (
            "_delta", "_pct_change", "_zscore_30d", "_zscore_90d",
            "_pct_change_7d", "_log1p", "_delta_log1p", "_burst",
        )):
            continue

        # log1p + pct_change + zscore
        df = add_delta_log1p(df, col)
        df = add_delta_and_pct(df, col)
        df = add_zscore_rolling(df, col, window=30)

        # Burst flag for fee rate
        if "fee_rate" in col:
            zscore_col = f"{col}_zscore_30d"
            if zscore_col in df.columns:
                df = df.with_columns(
                    pl.when(
                        pl.col(zscore_col).is_not_null() & (pl.col(zscore_col) > 2.0)
                    )
                    .then(pl.lit(1))
                    .otherwise(pl.lit(0))
                    .cast(pl.Int8)
                    .alias(f"{col}_burst")
                )

    # Ensure asof_utc
    if "asof_utc" not in df.columns and "ts_utc" in df.columns:
        df = add_asof_utc(df)

    return df


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def fetch_onchain_signals(
    *,
    start: str | None = None,
    end: str | None = None,
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    """Fetch all on-chain signals and write parquets.

    DeFiLlama signals have full history; Mempool.space only has current snapshot.
    """
    client = ApiClient(cache_dir=cache_dir)

    start_dt = (
        datetime.fromisoformat(start).replace(tzinfo=UTC) if start
        else datetime(2020, 1, 1, tzinfo=UTC)
    )
    end_dt = (
        datetime.fromisoformat(end).replace(tzinfo=UTC) if end
        else datetime.now(tz=UTC)
    )

    outputs: list[Path] = []
    quality_reports: list[OnchainQualityReport] = []
    errors: list[str] = []
    warnings: list[str] = []

    # --- DeFiLlama signals (historical) ---
    signal_builders = [
        ("eth_defi_tvl_total", lambda: build_eth_defi_tvl(client, start_dt, end_dt)),
        ("eth_l2_tvl_total", lambda: build_eth_l2_tvl(client, start_dt, end_dt)),
        ("eth_stablecoin_supply", lambda: build_eth_stablecoin_supply(client, start_dt, end_dt)),
    ]

    for signal_id, builder_fn in signal_builders:
        try:
            df = builder_fn()
            if df.is_empty():
                warnings.append(f"{signal_id}: empty response")
                continue

            col = f"{PREFIX}_{signal_id}"
            qc = run_quality_checks(df, col, signal_id)
            quality_reports.append(qc)

            # Write each column as separate parquet
            meta_cols = [c for c in ["ts_utc", "asof_utc"] if c in df.columns]
            signal_cols = [c for c in df.columns if c.startswith(PREFIX)]
            for scol in signal_cols:
                topic = scol.removeprefix(f"{PREFIX}_")
                frame = df.select(meta_cols + [scol])
                outputs.append(
                    write_signal_frame(
                        frame=frame,
                        signals_root=signals_root,
                        source="onchain",
                        topic=topic,
                        freq=freq,
                    )
                )
                logger.info("Wrote %s: %d rows", scol, df.height)
        except Exception as exc:
            errors.append(f"{signal_id}: {exc}")
            logger.error("Failed to build %s: %s", signal_id, exc)

    # --- Mempool.space signals (snapshot only) ---
    for signal_id, builder_fn in [
        ("btc_mempool_vbytes", lambda: build_btc_mempool(client)),
        ("btc_median_fee_rate", lambda: build_btc_fee_rate(client)),
    ]:
        try:
            df = builder_fn()
            if df.is_empty():
                warnings.append(f"{signal_id}: empty response")
                continue

            col = f"{PREFIX}_{signal_id}"
            meta_cols = [c for c in ["ts_utc", "asof_utc"] if c in df.columns]
            signal_cols = [c for c in df.columns if c.startswith(PREFIX)]

            # For Mempool signals, merge with existing data
            for scol in signal_cols:
                topic = scol.removeprefix(f"{PREFIX}_")
                from ..storage import read_parquet_safe, signal_path  # noqa: E402
                existing_path = signal_path(signals_root, "onchain", topic, freq)
                if existing_path.exists():
                    existing = read_parquet_safe(existing_path)
                    new_frame = df.select(meta_cols + [scol])
                    merged = pl.concat([existing, new_frame]).unique("ts_utc", keep="last").sort("ts_utc")
                else:
                    merged = df.select(meta_cols + [scol])

                outputs.append(
                    write_signal_frame(
                        frame=merged,
                        signals_root=signals_root,
                        source="onchain",
                        topic=topic,
                        freq=freq,
                    )
                )
                logger.info("Wrote %s: %d rows (snapshot)", scol, merged.height)
        except Exception as exc:
            errors.append(f"{signal_id}: {exc}")
            logger.error("Failed to build %s: %s", signal_id, exc)

    # --- Write manifest ---
    run_id = f"onchain_build_{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%S')}Z"
    manifest = {
        "run_id": run_id,
        "run_type": "onchain_builder",
        "status": "fail" if errors and not outputs else ("partial" if errors else "success"),
        "signals": {},
        "errors": errors,
        "warnings": warnings,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    for qc in quality_reports:
        manifest["signals"][qc.signal_id] = {
            "rows_written": sum(1 for p in outputs if qc.signal_id in str(p)),
            "quality_status": qc.status,
            "quality_summary": {n.check_id: n.level for n in qc.notes},
        }

    manifest_path = Path(signals_root) / "onchain" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    logger.info("Manifest written: %s", manifest_path)

    return outputs
