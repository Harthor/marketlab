"""Celery tasks for MarketLab data pipeline.

Queues:
    ingest  — fetch external data (FNG, Wikipedia, RSS)
    compute — dataset assembly + correlation engine
    alerts  — (placeholder) notification tasks

All tasks use `track_task` context manager for automatic
TaskRun logging and DataFreshness updates.
"""
from __future__ import annotations

import logging
import subprocess
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workspace() -> Path:
    return getattr(settings, "MARKETLAB_WORKSPACE", Path(".")).resolve()


def _venv_python() -> str:
    """Resolve the virtualenv python for subprocess calls."""
    workspace = _workspace()
    venv_python = workspace / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return "python"


@contextmanager
def track_task(
    task_name: str,
    celery_task_id: str = "",
    source: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Context manager that creates a TaskRun record and updates DataFreshness.

    Usage:
        with track_task("ingest_fng", self.request.id, source="fng") as ctx:
            # ... do work ...
            ctx["row_count"] = 2248
    """
    # Lazy import to avoid circular imports at module level
    from .models import DataFreshness, TaskRun

    run = TaskRun.objects.create(
        task_name=task_name,
        celery_task_id=celery_task_id,
        status=TaskRun.Status.RUNNING,
    )
    ctx: dict[str, Any] = {"row_count": None}

    try:
        yield ctx
        run.mark_success(summary={"row_count": ctx.get("row_count")})
        if source:
            freshness, _ = DataFreshness.objects.get_or_create(source=source)
            freshness.update_success(row_count=ctx.get("row_count"))
        logger.info("Task %s completed successfully", task_name)

    except Exception as exc:
        error_msg = f"{exc}\n{traceback.format_exc()}"
        run.mark_failure(error_msg)
        if source:
            freshness, _ = DataFreshness.objects.get_or_create(source=source)
            freshness.update_failure(str(exc))
        logger.error("Task %s failed: %s", task_name, exc)
        raise


def _run_cli(args: list[str], cwd: str | Path | None = None) -> str:
    """Run a CLI command and return stdout. Raises on non-zero exit."""
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=600,  # 10 min max
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(args)}\n"
            f"  stderr: {result.stderr[:2000]}"
        )
    return result.stdout


# ---------------------------------------------------------------------------
# Ingest tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="api.tasks.ingest_fng")
def ingest_fng(self):  # type: ignore[no-untyped-def]
    """Fetch latest Fear & Greed Index data."""
    with track_task("ingest_fng", self.request.id, source="fng") as ctx:
        python = _venv_python()
        workspace = _workspace()
        signals_dir = workspace / "altdata-web-signals"

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        output = _run_cli(
            [python, "-m", "altdata_web_signals.cli", "fng",
             "--start", "2020-01-01", "--end", today],
            cwd=signals_dir,
        )
        ctx["row_count"] = output.count("saved=")
        logger.info("FNG ingest: %s files written", ctx["row_count"])


@shared_task(bind=True, name="api.tasks.ingest_wikipedia")
def ingest_wikipedia(self):  # type: ignore[no-untyped-def]
    """Fetch latest Wikipedia pageviews for BTC-related topics."""
    with track_task("ingest_wikipedia", self.request.id, source="wikipedia") as ctx:
        python = _venv_python()
        workspace = _workspace()
        signals_dir = workspace / "altdata-web-signals"

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        output = _run_cli(
            [python, "-m", "altdata_web_signals.cli", "wiki",
             "--topics", "Bitcoin,Ethereum,Cryptocurrency",
             "--start", "2020-01-01", "--end", today],
            cwd=signals_dir,
        )
        ctx["row_count"] = output.count("saved=")
        logger.info("Wikipedia ingest: %s files written", ctx["row_count"])


@shared_task(bind=True, name="api.tasks.ingest_rss_crypto")
def ingest_rss_crypto(self):  # type: ignore[no-untyped-def]
    """Fetch latest RSS crypto feeds with FinBERT sentiment."""
    with track_task("ingest_rss_crypto", self.request.id, source="rss_crypto") as ctx:
        python = _venv_python()
        workspace = _workspace()
        signals_dir = workspace / "altdata-web-signals"

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        output = _run_cli(
            [python, "-m", "altdata_web_signals.cli", "rss-crypto",
             "--end", today],
            cwd=signals_dir,
        )
        ctx["row_count"] = output.count("saved=")
        logger.info("RSS crypto ingest: %s files written", ctx["row_count"])


@shared_task(bind=True, name="api.tasks.ingest_onchain")
def ingest_onchain(self):  # type: ignore[no-untyped-def]
    """Fetch on-chain signals from Mempool.space + DeFiLlama."""
    with track_task("ingest_onchain", self.request.id, source="onchain") as ctx:
        python = _venv_python()
        workspace = _workspace()
        signals_dir = workspace / "altdata-web-signals"

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        output = _run_cli(
            [python, "-m", "altdata_web_signals.cli", "onchain",
             "--start", "2020-01-01", "--end", today],
            cwd=signals_dir,
        )
        ctx["row_count"] = output.count("saved=")
        logger.info("On-chain ingest: %s files written", ctx["row_count"])


# ---------------------------------------------------------------------------
# Compute tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="api.tasks.compute_build_dataset")
def compute_build_dataset(self):  # type: ignore[no-untyped-def]
    """Rebuild the research-ready BTC dataset with all signals."""
    with track_task("compute_build_dataset", self.request.id, source="dataset") as ctx:
        python = _venv_python()
        workspace = _workspace()
        signals_dir = workspace / "altdata-web-signals"

        output = _run_cli(
            [python, "-m", "altdata_web_signals.cli", "build-dataset",
             "--symbol", "BTC-USD", "--freq", "1d", "--join", "how=outer"],
            cwd=signals_dir,
        )
        ctx["row_count"] = 1  # one dataset produced
        logger.info("Dataset build: %s", output.strip())


@shared_task(bind=True, name="api.tasks.compute_correlation")
def compute_correlation(self):  # type: ignore[no-untyped-def]
    """Run the correlation engine on the latest dataset."""
    with track_task("compute_correlation", self.request.id, source="correlation") as ctx:
        python = _venv_python()
        workspace = _workspace()
        engine_dir = workspace / "correlation-engine"
        dataset = workspace / "altdata-web-signals" / "data" / "datasets" / "BTC-USD" / "btc_daily_signals.parquet"

        if not dataset.exists():
            logger.warning("Daily dataset not found at %s, skipping correlation", dataset)
            ctx["row_count"] = 0
            return

        output = _run_cli(
            [python, "-m", "correngine", "run",
             "--dataset", str(dataset), "--bootstrap", "500"],
            cwd=engine_dir,
        )
        ctx["row_count"] = 1
        logger.info("Correlation engine: %s", output.strip())


@shared_task(bind=True, name="api.tasks.compute_catchup_check")
def compute_catchup_check(self):  # type: ignore[no-untyped-def]
    """Check if any data sources missed their scheduled ingest and re-run."""
    from .models import DataFreshness

    with track_task("compute_catchup_check", self.request.id) as ctx:
        catchup_count = 0
        for freshness in DataFreshness.objects.all():
            old_status = freshness.status
            new_status = freshness.check_staleness()
            if old_status != "stale" and new_status == "stale":
                logger.warning(
                    "Source %s became stale (last success: %s)",
                    freshness.source,
                    freshness.last_success_at,
                )
                catchup_count += 1

        ctx["row_count"] = catchup_count
        logger.info("Catchup check: %d sources need attention", catchup_count)


@shared_task(bind=True, name="api.tasks.compute_data_freshness")
def compute_data_freshness(self):  # type: ignore[no-untyped-def]
    """Update staleness status for all tracked data sources."""
    from .models import DataFreshness

    with track_task("compute_data_freshness", self.request.id) as ctx:
        sources = DataFreshness.objects.all()
        for source in sources:
            source.check_staleness()

        ctx["row_count"] = sources.count()
        logger.info("Data freshness: updated %d sources", ctx["row_count"])


# ---------------------------------------------------------------------------
# Alert tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="api.tasks.evaluate_alerts")
def evaluate_alerts(self):  # type: ignore[no-untyped-def]
    """Evaluate all enabled alert rules and fire events."""
    from .evaluator import evaluate_all_rules

    with track_task("evaluate_alerts", self.request.id) as ctx:
        events = evaluate_all_rules()
        ctx["row_count"] = len(events)
        logger.info("Alert evaluation: %d events fired", len(events))
