"""Quickstart example for manual smoke execution."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl

from marketlab_core.io import read_parquet, write_parquet
from marketlab_core.storage import Cache
from marketlab_core.timeseries import align, compute_returns


def main() -> None:
    t_a = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(120)]
    t_b = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=2 * i) for i in range(60)]

    a = pl.DataFrame(
        {
            "timestamp": t_a,
            "value": np.sin(np.linspace(0, 6, len(t_a))) + 5.0,
        }
    )
    b = pl.DataFrame(
        {
            "timestamp": t_b,
            "value": np.linspace(100.0, 110.0, len(t_b)),
        }
    )

    a_returns = compute_returns(a, value_col="value", method="simple", horizon=1)
    print("last return in a:", a_returns[-1, "value_simple_ret_1"])

    aligned = align([a, b], how="outer", freq="1m", method="ffill")
    print("aligned shape:", aligned.shape)

    cache = Cache(root=Path("/tmp/marketlab-core-example"))
    cache.set("aligned", aligned)
    cached = cache.get("aligned")
    assert cached is not None

    out = Path("examples/out/aligned_example.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_parquet(cached, out)
    reread = read_parquet(out)
    print("written + read:", reread.shape)


if __name__ == "__main__":
    main()
