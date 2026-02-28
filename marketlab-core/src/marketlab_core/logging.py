import logging
from typing import Any

_configured = False


def configure_logging(level: str = "INFO", **kwargs: Any) -> None:
    """Configure root logging once."""

    global _configured
    if _configured:
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return module logger with idempotent setup."""

    if not _configured:
        configure_logging()
    return logging.getLogger(name)
