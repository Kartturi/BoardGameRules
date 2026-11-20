"""Unit tests for centralized logging configuration and formatters."""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.logging_config import (
    _NOISY_THIRD_PARTY_LOGGERS,
    ConsoleLogFormatter,
    GcpJsonLogFormatter,
    LoggingSettings,
    configure_logging,
)


@pytest.fixture(autouse=True)
def restore_logging_state() -> Iterator[None]:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_noisy_levels = {
        name: logging.getLogger(name).level for name in _NOISY_THIRD_PARTY_LOGGERS
    }
    try:
        yield
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        for name, level in original_noisy_levels.items():
            logging.getLogger(name).setLevel(level)


def test_should_load_logging_settings_with_defaults_and_env_overrides(tmp_path: Path) -> None:
    # Arrange
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text('LOG_LEVEL="debug"\nLOG_FORMAT="JSON"\n', encoding="utf-8")

    # Act
    defaults = LoggingSettings.from_env(environ={})
    from_dotenv = LoggingSettings.from_env(environ={}, dotenv_path=dotenv_file)
    overridden = LoggingSettings.from_env(
        environ={"LOG_LEVEL": "warning", "LOG_FORMAT": "console"},
        dotenv_path=dotenv_file,
    )

    # Assert
    assert defaults == LoggingSettings(level="INFO", log_format="console")
    assert from_dotenv == LoggingSettings(level="DEBUG", log_format="json")
    assert overridden == LoggingSettings(level="WARNING", log_format="console")


@pytest.mark.parametrize(
    ("level", "log_format"),
    [
        ("TRACE", "console"),
        ("", "console"),
        ("INFO", "xml"),
        ("INFO", ""),
    ],
)
def test_should_raise_domain_validation_error_when_log_level_or_format_is_invalid(
    level: str,
    log_format: str,
) -> None:
    # Arrange / Act / Assert
    with pytest.raises(DomainValidationError):
        LoggingSettings(level=level, log_format=log_format)


def test_should_format_human_readable_console_log_and_escape_newlines() -> None:
    # Arrange
    formatter = ConsoleLogFormatter()
    record = logging.LogRecord(
        name="boardgamerules.batch.ingestor",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="Indexed manual\nforged line",
        args=(),
        exc_info=None,
    )
    record.game_id = "catan"
    record.file_key = "incoming/catan\r\n.pdf"

    # Act
    output = formatter.format(record)

    # Assert
    assert "\n" not in output
    assert "\r" not in output
    assert "INFO" in output
    assert "boardgamerules.batch.ingestor" in output
    assert "Indexed manual\\nforged line" in output
    assert "game_id=catan" in output
    assert "file_key=incoming/catan\\r\\n.pdf" in output
    assert "taskName" not in output


def test_should_format_gcp_json_log_with_utc_timestamp_severity_and_extra_fields() -> None:
    # Arrange
    formatter = GcpJsonLogFormatter()
    record = logging.LogRecord(
        name="boardgamerules.rag.qa",
        level=logging.WARNING,
        pathname=__file__,
        lineno=77,
        msg="Retrieved %d chunks",
        args=(4,),
        exc_info=None,
    )
    record.game_id = "scythe"
    record.chunk_count = 4

    # Act
    raw = formatter.format(record)
    payload = json.loads(raw)

    # Assert
    assert "\n" not in raw
    assert payload["severity"] == "WARNING"
    assert payload["message"] == "Retrieved 4 chunks"
    assert payload["logger"] == "boardgamerules.rag.qa"
    assert payload["timestamp"].endswith("+00:00") or payload["timestamp"].endswith("Z")
    assert payload["game_id"] == "scythe"
    assert payload["chunk_count"] == 4
    assert "taskName" not in payload


def test_should_block_extra_fields_from_overwriting_reserved_gcp_json_keys() -> None:
    # Arrange
    formatter = GcpJsonLogFormatter()
    record = logging.LogRecord(
        name="boardgamerules.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Safe message",
        args=(),
        exc_info=None,
    )
    record.severity = "SPOOFED"
    record.timestamp = "1999-01-01"
    record.game_id = "catan"

    # Act
    payload = json.loads(formatter.format(record))

    # Assert
    assert payload["severity"] == "INFO"
    assert payload["timestamp"] != "1999-01-01"
    assert payload["game_id"] == "catan"


def test_should_include_formatted_traceback_in_gcp_json_log_on_exception() -> None:
    # Arrange
    formatter = GcpJsonLogFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="boardgamerules.batch.ingestor",
        level=logging.ERROR,
        pathname=__file__,
        lineno=12,
        msg="PDF ingestion failed",
        args=(),
        exc_info=exc_info,
    )

    # Act
    payload = json.loads(formatter.format(record))

    # Assert
    assert payload["severity"] == "ERROR"
    assert "RuntimeError: boom" in payload["exception"]


def test_should_replace_managed_handler_without_removing_pytest_caplog_handler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    buffer = io.StringIO()
    logger = logging.getLogger("boardgamerules.test.idempotent")

    # Act
    configure_logging(LoggingSettings(level="INFO", log_format="json"), stream=buffer)
    configure_logging(LoggingSettings(level="INFO", log_format="json"), stream=buffer)
    with caplog.at_level(logging.INFO):
        logger.info("hello", extra={"game_id": "catan"})

    # Assert
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["game_id"] == "catan"
    assert any(rec.message == "hello" for rec in caplog.records)


def test_should_route_console_logs_to_stderr_and_json_logs_to_stdout_by_default() -> None:
    # Arrange / Act
    configure_logging(LoggingSettings(level="INFO", log_format="console"))
    console_handlers = [
        h for h in logging.getLogger().handlers if getattr(h, "_boardgamerules_managed", False)
    ]
    configure_logging(LoggingSettings(level="INFO", log_format="json"))
    json_handlers = [
        h for h in logging.getLogger().handlers if getattr(h, "_boardgamerules_managed", False)
    ]

    # Assert
    assert len(console_handlers) == 1
    assert console_handlers[0].stream is sys.stderr
    assert len(json_handlers) == 1
    assert json_handlers[0].stream is sys.stdout


def test_should_filter_out_debug_logs_when_configured_level_is_info() -> None:
    # Arrange
    buffer = io.StringIO()
    logger = logging.getLogger("boardgamerules.test.level_filter")

    # Act
    configure_logging(LoggingSettings(level="INFO", log_format="json"), stream=buffer)
    logger.debug("hidden debug event")
    logger.info("visible info event")

    # Assert
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "visible info event"
