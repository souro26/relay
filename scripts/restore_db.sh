#!/bin/bash
# ==============================================================================
# Relay PostgreSQL Database Restore Script
# Restores a compressed SQL dump into the Relay database container.
# ==============================================================================
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <path_to_backup_file.sql.gz> [--force]"
    exit 1
fi

BACKUP_FILE="$1"
FORCE_FLAG="${2:-}"
CONTAINER_NAME="${CONTAINER_NAME:-relay-postgres-prod}"
DB_USER="${POSTGRES_USER:-relay}"
DB_NAME="${POSTGRES_DB:-${DB_NAME:-relay_production}}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "[ERROR] Backup file does not exist: ${BACKUP_FILE}"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Target container '${CONTAINER_NAME}' is not running."
    exit 1
fi

if [ "${FORCE_FLAG}" != "--force" ]; then
    echo "WARNING: This will overwrite current data in database '${DB_NAME}' inside container '${CONTAINER_NAME}'."
    read -rp "Are you sure you want to proceed? [y/N] " confirmation
    if [[ ! "${confirmation}" =~ ^[Yy]$ ]]; then
        echo "Restore aborted by user."
        exit 0
    fi
fi

echo "[INFO] Restoring database '${DB_NAME}' from '${BACKUP_FILE}'..."

gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}"

echo "[SUCCESS] Database restore completed successfully."
