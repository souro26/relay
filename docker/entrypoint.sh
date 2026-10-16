#!/bin/sh
set -e

# Run database migrations if requested or by default in container
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations via Alembic..."
    alembic upgrade head
fi

exec "$@"
