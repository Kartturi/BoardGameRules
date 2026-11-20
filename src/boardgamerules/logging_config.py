"""Centralized structured logging for local console output and GCP Cloud Logging."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.env_loader import DEFAULT_DOTENV_PATH, load_env_vars, read_optional_env

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_VALID_LOG_FORMATS = frozenset({"console", "json"})
_STANDARD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
}
_RESERVED_GCP_KEYS = frozenset({"timestamp", "severity", "message", "logger", "exception"})
_NOISY_THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "pymongo", "urllib3", "google_genai")


# CONCEPT: [System Design] Twelve-Factor Logging & Standard Streams (stdout -> GCP Cloud Logging)
# Instead of writing log files to disk or calling a remote logging server over the network,
# the app writes logs directly to standard streams (stderr for local console, stdout for
# GCP JSON). Cloud Run automatically reads every JSON line from stdout and turns fields like
# "severity", "message", and "game_id" into searchable entries in GCP Cloud Logging.
@dataclass(frozen=True)
class LoggingSettings:
    level: str = "INFO"
    log_format: str = "console"

    def __post_init__(self) -> None:
        if self.level not in _VALID_LOG_LEVELS:
            raise DomainValidationError(
                f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}, got '{self.level}'."
            )
        if self.log_format not in _VALID_LOG_FORMATS:
            raise DomainValidationError(
                f"LOG_FORMAT must be one of {sorted(_VALID_LOG_FORMATS)}, got '{self.log_format}'."
            )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path = DEFAULT_DOTENV_PATH,
    ) -> LoggingSettings:
        env = load_env_vars(environ, dotenv_path)
        raw_level = read_optional_env(env, "LOG_LEVEL") or "INFO"
        raw_format = read_optional_env(env, "LOG_FORMAT") or "console"
        return cls(level=raw_level.upper(), log_format=raw_format.lower())


# CONCEPT: [Design Pattern] Strategy Pattern (Pluggable Log Formatters)
# ConsoleLogFormatter and GcpJsonLogFormatter share Python's logging.Formatter interface,
# so the app can switch between human-readable local output and GCP Cloud Logging JSON
# using one environment variable without changing a single log statement in the codebase.
class ConsoleLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        message = _single_line(record.getMessage())
        base = f"{timestamp} | {record.levelname:<8} | {record.name} | {message}"
        extras = _extract_extra_fields(record)
        if extras:
            pairs = " ".join(f"{k}={_single_line(str(v))}" for k, v in sorted(extras.items()))
            base = f"{base} | {pairs}"
        if record.exc_info:
            return f"{base}\n{self.formatException(record.exc_info)}"
        return base


class GcpJsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key, value in _extract_extra_fields(record).items():
            if key not in _RESERVED_GCP_KEYS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _ManagedStreamHandler(logging.StreamHandler[TextIO]):
    _boardgamerules_managed = True


def configure_logging(
    settings: LoggingSettings | None = None,
    stream: TextIO | None = None,
) -> None:
    resolved = settings or LoggingSettings.from_env()
    target_stream = stream or (sys.stdout if resolved.log_format == "json" else sys.stderr)
    handler = _ManagedStreamHandler(target_stream)
    handler.setFormatter(
        GcpJsonLogFormatter() if resolved.log_format == "json" else ConsoleLogFormatter()
    )

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        if getattr(existing, "_boardgamerules_managed", False):
            root_logger.removeHandler(existing)
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved.level)

    noisy_level = logging.NOTSET if resolved.level == "DEBUG" else logging.WARNING
    for logger_name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(noisy_level)


def _extract_extra_fields(record: logging.LogRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_KEYS and not key.startswith("_")
    }


def _single_line(text: str) -> str:
    return text.replace("\r", "\\r").replace("\n", "\\n")
