#!/bin/sh
set -e

# Run database migrations if requested or by default in container
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations via Alembic..."
    alembic upgrade head
fi

# In free-tier / single-container deployment (like Render free tier),
# start the simulated order_service in the background if enabled
if [ "${START_INTERNAL_ORDER_SERVICE:-false}" = "true" ]; then
    echo "Starting internal order service on 127.0.0.1:8001..."
    uvicorn order_service.main:app --host 127.0.0.1 --port 8001 &
fi

# Handle dynamic $PORT if set (common in cloud environments like Render)
if [ -n "$PORT" ] && [ "$1" = "uvicorn" ] && [ "$2" = "relay.api.main:app" ]; then
    echo "Starting Relay API on port ${PORT}..."
    exec uvicorn relay.api.main:app --host 0.0.0.0 --port "${PORT}"
fi

exec "$@"
