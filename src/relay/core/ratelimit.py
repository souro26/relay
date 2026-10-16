"""In-memory rate limiter for API endpoints."""

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from relay.api.correlation import get_client_ip
from relay.core.config import get_settings


@dataclass
class RateLimitBucket:
    """Token bucket for a single client."""

    tokens: float
    last_refill: float = field(default_factory=time.monotonic)
    request_count: int = 0


class InMemoryRateLimiter:
    """Simple in-memory token bucket rate limiter.

    Note: This is an in-memory implementation suitable for single-instance
    deployments. It does NOT provide globally consistent limits across
    multiple application instances. For multi-instance deployments, use
    a distributed rate limiter (e.g., Redis-based).
    """

    def __init__(
        self,
        get_limit: Callable[[], int] | None = None,
        requests_per_minute: int = 10,
        burst_allowance: int = 2,
    ):
        """
        Initialize the rate limiter.

        Args:
            get_limit: Callable that returns the current rate limit
                (requests per minute). If provided, this takes precedence over
                requests_per_minute.
            requests_per_minute: Maximum requests per minute per client
                (fallback if get_limit is None).
            burst_allowance: Additional burst tokens allowed.
        """
        self._get_limit = get_limit
        self._fallback_limit = max(1, requests_per_minute)
        self.burst_allowance = max(0, burst_allowance)
        self._max_tokens = self._fallback_limit + self.burst_allowance
        self._refill_rate = self._fallback_limit / 60.0  # tokens per second

        self._buckets: dict[str, RateLimitBucket] = defaultdict(
            lambda: RateLimitBucket(tokens=self._max_tokens)
        )
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.monotonic()

    @property
    def requests_per_minute(self) -> int:
        """Get the current rate limit (uses callable if provided, otherwise fallback)."""
        if self._get_limit is not None:
            return max(1, self._get_limit())
        return self._fallback_limit

    @property
    def max_tokens(self) -> int:
        return self.requests_per_minute + self.burst_allowance

    @property
    def refill_rate(self) -> float:
        return self.requests_per_minute / 60.0

    def _refill_bucket(self, bucket: RateLimitBucket) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        new_tokens = elapsed * self.refill_rate
        bucket.tokens = min(self.max_tokens, bucket.tokens + new_tokens)
        bucket.last_refill = now

    def _get_client_key(self, request: Request) -> str:
        """Extract client identifier from request."""
        return get_client_ip(request)

    def _cleanup_old_buckets(self) -> None:
        """Remove inactive buckets to prevent memory leaks."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        cutoff = now - 3600  # Remove buckets inactive for 1 hour
        expired_keys = [key for key, bucket in self._buckets.items() if bucket.last_refill < cutoff]
        for key in expired_keys:
            del self._buckets[key]

        self._last_cleanup = now

    def check_rate_limit(self, request: Request) -> tuple[bool, dict[str, Any]]:
        """
        Check if request is within rate limit.

        Returns:
            Tuple of (allowed, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset_after_seconds
        """
        self._cleanup_old_buckets()

        client_key = self._get_client_key(request)
        bucket = self._buckets[client_key]

        self._refill_bucket(bucket)

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            bucket.request_count += 1
            allowed = True
        else:
            allowed = False

        remaining = max(0, int(bucket.tokens))
        reset_after = max(0, (1 - bucket.tokens) / self.refill_rate) if not allowed else 0

        rate_limit_info = {
            "limit": self.requests_per_minute,
            "remaining": remaining,
            "reset_after_seconds": round(reset_after, 1),
        }

        return allowed, rate_limit_info

    def get_rate_limit_headers(self, rate_limit_info: dict[str, Any]) -> dict[str, str]:
        """Generate rate limit headers for response."""
        return {
            "X-RateLimit-Limit": str(rate_limit_info["limit"]),
            "X-RateLimit-Remaining": str(rate_limit_info["remaining"]),
            "X-RateLimit-Reset": str(int(time.time() + rate_limit_info["reset_after_seconds"])),
        }


# Global rate limiter instance (initialized on first use)
_rate_limiter: InMemoryRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get or create the global rate limiter instance.

    Reads the current settings at runtime to allow test configuration changes.
    """
    global _rate_limiter
    if _rate_limiter is None:
        # Force reload settings to pick up any test environment changes
        from relay.core.config import reload_settings

        reload_settings()
        _rate_limiter = InMemoryRateLimiter(
            get_limit=lambda: get_settings().rate_limit_per_minute,
            burst_allowance=2,
        )
    else:
        # Update rate limit if settings have changed (e.g., in tests)
        # Force reload settings to pick up test environment changes
        from relay.core.config import reload_settings

        reload_settings()
        s = get_settings()
        if _rate_limiter.requests_per_minute != s.rate_limit_per_minute:
            _rate_limiter.requests_per_minute = s.rate_limit_per_minute
            _rate_limiter.max_tokens = s.rate_limit_per_minute + _rate_limiter.burst_allowance
            _rate_limiter.refill_rate = s.rate_limit_per_minute / 60.0
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter instance (for testing)."""
    global _rate_limiter
    _rate_limiter = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limits on specific endpoints."""

    def __init__(
        self,
        app,
        rate_limiter: InMemoryRateLimiter | None = None,
        excluded_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self._rate_limiter = rate_limiter
        self.excluded_paths = excluded_paths or [
            "/health",
            "/ready",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static",
        ]

    def _get_rate_limiter(self) -> InMemoryRateLimiter:
        """Get the rate limiter, creating it lazily on first use."""
        if self._rate_limiter is None:
            self._rate_limiter = get_rate_limiter()
        return self._rate_limiter

    @property
    def rate_limiter(self) -> InMemoryRateLimiter:
        """Get the rate limiter, creating it lazily if needed."""
        return self._get_rate_limiter()

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for excluded paths
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self.excluded_paths):
            return await call_next(request)

        # Check rate limit
        allowed, rate_limit_info = self.rate_limiter.check_rate_limit(request)

        if not allowed:
            # Log rate limit exceeded
            from relay.api.correlation import get_client_ip
            from relay.core.logging import log_rate_limit_exceeded

            client_ip = get_client_ip(request)
            log_rate_limit_exceeded(client_ip, rate_limit_info["limit"])

            # Return 429 with Retry-After header
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": (
                        f"Rate limit of {rate_limit_info['limit']} requests per minute exceeded"
                    ),
                    "retry_after_seconds": rate_limit_info["reset_after_seconds"],
                },
                headers={
                    "Retry-After": str(int(rate_limit_info["reset_after_seconds"])),
                },
            )

        # Request is allowed - process the request
        response = await call_next(request)

        # Add rate limit headers to response
        for header, value in self.rate_limiter.get_rate_limit_headers(rate_limit_info).items():
            response.headers[header] = value

        return response
