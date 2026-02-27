"""Minimal structured logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class StructuredLogger:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, extra=kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._logger.error(msg, *args, extra=kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, extra=kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, extra=kwargs)


class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(message)s",
    )
    logger = logging.getLogger()
    for handler in logger.handlers:
        handler.setFormatter(StructuredJSONFormatter())


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(logging.getLogger(name))
