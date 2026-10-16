#!/bin/bash
# ==============================================================================
# Relay PostgreSQL Database Backup Script
# Performs a reliable, timestamped, compressed backup of the Relay database.
# ==============================================================================
set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
CONTAINER_NAME="${CONTAINER_NAME:-relay-postgres-prod}"
DB_USER="${POSTGRES_USER:-relay}"
DB_NAME="${POSTGRES_DB:-${DB_NAME:-relay_production}}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/relay_${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[INFO] Starting database backup for '${DB_NAME}' from container '${CONTAINER_NAME}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    exit 1
fi

docker exec -t "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists | gzip > "${BACKUP_FILE}"

BACKUP_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "[SUCCESS] Backup completed successfully: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Prune old backups older than RETENTION_DAYS
echo "[INFO] Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "relay_${DB_NAME}_*.sql.gz" -mtime +"${RETENTION_DAYS}" -exec rm -f {} \;
echo "[INFO] Maintenance complete."
