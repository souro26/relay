# ==============================================================================
# Multi-stage production Dockerfile for Relay API
# ==============================================================================

# --- Stage 1: Build Dependencies ---
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools if needed
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging configuration and source for wheel build
COPY pyproject.toml README.md ./
COPY src ./src

# Create wheels directory and build wheel for dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir build && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels .

# --- Stage 2: Runtime Image ---
FROM python:3.11-slim AS runtime

# Install curl for docker healthchecks
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/false -m appuser

WORKDIR /app

# Copy and install pre-built wheels from builder
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application source and configuration
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh && \
    chown -R appuser:appgroup /app

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8000

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "relay.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
