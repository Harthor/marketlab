"""Correlation Engine for quantitative signal/target analysis."""

from .config import RunConfig
from .runner import RunResult, run_correlation

__all__ = ["RunConfig", "RunResult", "run_correlation"]

__version__ = "0.1.0"
