"""Correlation ID middleware and context management."""

import contextvars
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Context variable to store correlation ID for the current request
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Context variable to store workflow ID for the current request
workflow_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "workflow_id", default=None
)

# Context variable to store current step name
step_name_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "step_name", default=None
)

# Header name for correlation ID
CORRELATION_ID_HEADER = "X-Correlation-ID"

# Maximum length for correlation ID to prevent abuse
MAX_CORRELATION_ID_LENGTH = 64


def get_correlation_id() -> str | None:
    """Get the correlation ID for the current request context."""
    return correlation_id_var.get()


def get_workflow_id() -> str | None:
    """Get the workflow ID for the current request context."""
    return workflow_id_var.get()


def get_step_name() -> str | None:
    """Get the step name for the current request context."""
    return step_name_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current request context."""
    correlation_id_var.set(correlation_id)


def set_workflow_id(workflow_id: str) -> None:
    """Set the workflow ID for the current request context."""
    workflow_id_var.set(workflow_id)


def set_step_name(step_name: str | None) -> None:
    """Set the step name for the current request context."""
    step_name_var.set(step_name)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return uuid.uuid4().hex


def validate_correlation_id(value: str) -> str:
    """Validate and sanitize a correlation ID from an incoming header.

    Args:
        value: The raw correlation ID from the header.

    Returns:
        A sanitized correlation ID or a newly generated one if invalid.
    """
    if not value:
        return generate_correlation_id()

    # Strip whitespace
    value = value.strip()

    # Check length
    if len(value) > MAX_CORRELATION_ID_LENGTH:
        return generate_correlation_id()

    # Allow alphanumeric, hyphens, and underscores
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        return generate_correlation_id()

    return value


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to handle correlation ID propagation."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate correlation ID
        incoming_cid = request.headers.get(CORRELATION_ID_HEADER)
        if incoming_cid:
            correlation_id = validate_correlation_id(incoming_cid)
        else:
            correlation_id = generate_correlation_id()

        # Set correlation ID in context
        token = correlation_id_var.set(correlation_id)

        try:
            # Process the request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[CORRELATION_ID_HEADER] = correlation_id

            return response
        finally:
            # Reset context variable
            correlation_id_var.reset(token)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, accounting for proxy headers.

    Only trusts X-Forwarded-For when behind a trusted proxy.
    For production behind a proxy, configure trusted_proxies in the app.
    """
    # Check X-Forwarded-For header (only first IP in chain)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        ips = [ip.strip() for ip in forwarded_for.split(",")]
        if ips:
            return ips[0]

    # Check X-Real-IP header (set by some proxies)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return "unknown"
