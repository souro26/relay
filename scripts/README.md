# Database Operations & Maintenance Scripts

This directory contains standalone operational and maintenance scripts for production Relay instances:

- `backup_db.sh`: Automated, timestamped, and gzip-compressed PostgreSQL database backup script with 14-day retention pruning.
- `restore_db.sh`: Safe database restore script for compressed SQL dumps, requiring interactive confirmation before restoring.

## Usage

### Backup
```bash
./scripts/backup_db.sh
```
Environment variables (optional):
- `CONTAINER_NAME`: Docker container running PostgreSQL (default: `relay-postgres-prod`)
- `POSTGRES_USER`: Database user (default: `relay`)
- `POSTGRES_DB`: Target database name (default: `relay_production`)
- `BACKUP_DIR`: Target backup directory (default: `./backups`)
- `RETENTION_DAYS`: Retention period in days (default: `14`)

### Restore
```bash
./scripts/restore_db.sh ./backups/relay_relay_production_YYYYMMDD_HHMMSS.sql.gz
```
Options:
- `--force`: Bypass interactive confirmation prompt.
