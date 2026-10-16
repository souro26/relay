"""Structured JSON logging configuration."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from relay.api.correlation import get_correlation_id, get_workflow_id


class JSONFormatter(logging.Formatter):
    """JSON log formatter with correlation ID and workflow ID support."""

    def __init__(self, include_timestamp: bool = True):
        super().__init__()
        self.include_timestamp = include_timestamp

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add timestamp
        if self.include_timestamp:
            record_time = datetime.fromtimestamp(record.created, tz=UTC)
            log_data["timestamp"] = record_time.isoformat()

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add workflow ID if available
        workflow_id = get_workflow_id()
        if workflow_id:
            log_data["workflow_id"] = workflow_id

        # Add extra fields from record
        extra_fields = {
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        log_data.update(extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra attributes from record (custom fields)
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            }:
                # Only include JSON-serializable values
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    pass

        return json.dumps(log_data, ensure_ascii=False)


class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        # Add correlation ID and workflow ID to the message if available
        correlation_id = get_correlation_id()
        workflow_id = get_workflow_id()

        prefix_parts = []
        if correlation_id:
            prefix_parts.append(f"cid={correlation_id[:8]}")
        if workflow_id:
            prefix_parts.append(f"wid={workflow_id[:8]}")

        prefix = f"[{' '.join(prefix_parts)}] " if prefix_parts else ""

        # Format the message
        message = super().format(record)
        return f"{prefix}{message}"


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    include_timestamp: bool = True,
) -> None:
    """Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: Use JSON output (True for production, False for dev).
        include_timestamp: Include timestamp in log output.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        formatter = JSONFormatter(include_timestamp=include_timestamp)
    else:
        formatter = DevelopmentFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Set specific loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info("Logging configured", extra={"log_level": level, "json_format": json_format})


def log_workflow_event(
    logger: logging.Logger,
    event: str,
    workflow_id: str,
    status: str,
    duration_ms: float | None = None,
    **extra: Any,
) -> None:
    """Log a workflow lifecycle event with structured data."""
    extra_data = {
        "workflow_id": workflow_id,
        "event": event,
        "status": status,
    }
    if duration_ms is not None:
        extra_data["duration_ms"] = duration_ms
    extra_data.update(extra)

    logger.info(f"Workflow {event}: {status}", extra=extra_data)


def log_order_service_call(
    logger: logging.Logger,
    method: str,
    url: str,
    status_code: int | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    """Log an order service HTTP call with structured data."""
    extra_data = {
        "event": "order_service_call",
        "method": method,
        "url": url,
    }
    if status_code is not None:
        extra_data["status_code"] = status_code
    if duration_ms is not None:
        extra_data["duration_ms"] = duration_ms
    if error is not None:
        extra_data["error"] = error
    extra_data.update(extra)

    level = logging.ERROR if error else logging.INFO
    logger.log(level, f"Order service {method} {url}", extra=extra_data)


def log_llm_call(
    logger: logging.Logger,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    """Log an LLM API call with structured data."""
    extra_data = {
        "event": "llm_call",
        "model": model,
    }
    if prompt_tokens is not None:
        extra_data["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        extra_data["completion_tokens"] = completion_tokens
    if duration_ms is not None:
        extra_data["duration_ms"] = duration_ms
    if error is not None:
        extra_data["error"] = error
    extra_data.update(extra)

    level = logging.ERROR if error else logging.INFO
    logger.log(level, f"LLM call to {model}", extra=extra_data)


def log_rate_limit_exceeded(
    logger: logging.Logger,
    client_ip: str,
    endpoint: str,
    limit: int,
    **extra: Any,
) -> None:
    """Log a rate limit exceeded event."""
    extra_data = {
        "event": "rate_limit_exceeded",
        "client_ip": client_ip,
        "endpoint": endpoint,
        "limit_per_minute": limit,
    }
    extra_data.update(extra)

    logger.warning(f"Rate limit exceeded for {client_ip} on {endpoint}", extra=extra_data)
