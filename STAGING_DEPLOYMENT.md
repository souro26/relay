# Relay Staging Deployment Guide

## Overview

This guide documents how to set up and deploy Relay to a staging environment.

## Prerequisites

- Docker and Docker Compose v2+
- Python 3.11+
- NVIDIA API Key (for LLM interpretation)
- PostgreSQL 16 (via Docker Compose)

## Quick Start

### 1. Start PostgreSQL

```bash
docker-compose up -d
```

This starts PostgreSQL 16 with:
- Database: `relay_staging`
- User: `relay`
- Password: from `POSTGRES_PASSWORD` env var (default: `relay_staging_password`)
- Port: `5432`
- Persistent volume: `postgres_data`
- Health check: `pg_isready` every 5s

### 2. Configure Environment

```bash
# Copy the staging template
cp .env.staging.template .env.staging

# Edit with your actual values
# At minimum, set:
# - DATABASE_URL (with correct password)
# - LLM_API_KEY (NVIDIA NIM API key)
# - DEMO_API_KEY (for NL endpoint access)
```

### 3. Apply Migrations

```bash
# Set the staging DATABASE_URL
export DATABASE_URL="postgresql+psycopg://relay:YOUR_PASSWORD@localhost:5432/relay_staging"

# Run migrations
alembic upgrade head
```

### 4. Run Tests

```bash
# Unit tests (no database required)
python -m pytest tests/ -v --asyncio-mode=auto

# Integration tests (requires PostgreSQL)
python -m pytest tests/ -v --run-integration --asyncio-mode=auto
```

### 5. Run Application Services

#### Terminal 1: Order Service (port 8001)
```bash
export DATABASE_URL="postgresql+psycopg://relay:YOUR_PASSWORD@localhost:5432/relay_staging"
export ORDER_SERVICE_URL=http://localhost:8001
python -m order_service.main
```

#### Terminal 2: Relay API (port 8000)
```bash
export DATABASE_URL="postgresql+psycopg://relay:YOUR_PASSWORD@localhost:5432/relay_staging"
export ORDER_SERVICE_URL=http://localhost:8001
export LLM_API_KEY=your_nvidia_api_key
python -m relay.api.main
```

## Service Endpoints

| Service | Port | Endpoints |
|---------|------|-----------|
| Relay API | 8000 | `/health`, `/ready`, `/api/v1/order-change-requests`, `/api/v1/order-change-requests/nl` |
| Order Service | 8001 | `/health`, `/orders/{id}`, `/orders/{id}/idempotency/{key}` |

## Configuration

### Required Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `ORDER_SERVICE_URL` | Order service base URL | Yes |
| `LLM_API_KEY` | NVIDIA NIM API key | Yes (for NL endpoint) |
| `DEMO_API_KEY` | Demo access key for NL endpoint | Optional* |
| `LLM_API_KEY` | NVIDIA NIM API key | Yes |

*Required if `DEMO_API_KEY` is set in environment

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development`, `staging`, `production`, `test` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `ORDER_SERVICE_TIMEOUT` | `10.0` | HTTP timeout for order service calls |
| `RATE_LIMIT_PER_MINUTE` | `10` | Rate limit for NL endpoint |
| `LLM_TIMEOUT` | `30.0` | LLM request timeout (seconds) |
| `RATE_LIMIT_PER_MINUTE` | `10` | NL endpoint rate limit |

## Database

### Migrations

```bash
# Check current revision
alembic current

# Show migration history
alembic history

# Create new migration
alembic revision -m "description" --autogenerate

# Upgrade to head
alembic upgrade head

# Downgrade one revision
alembic downgrade -1
```

### Seed Data

The migration `f3bde427f2bc` includes seed data for 5 orders:
- ORD-136D6350 (customer-101, confirmed)
- ORD-61964039 (customer-101, pending)
- ORD-C176AE39 (customer-102, shipped)
- ORD-761CDE8F (customer-103, cancelled)
- ORD-04CAB142 (customer-104, delivered)

## Testing

### Unit Tests (No Database)
```bash
python -m pytest tests/test_api.py tests/test_config.py tests/test_models.py tests/test_nl_interpreter.py::TestNLInterpreterService -v --asyncio-mode=auto
```

### Integration Tests (Requires PostgreSQL)
```bash
# Requires PostgreSQL running on port 5432 with relay_staging database
python -m pytest tests/test_nl_interpreter.py::TestNLInterpreterEndpoint tests/test_nl_interpreter.py::TestAccessControl tests/test_order_change.py -v --run-integration --asyncio-mode=auto
```

### All Tests
```bash
python -m pytest tests/ -v --run-integration --asyncio-mode=auto
```

## Quality Checks

```bash
# Linting
python -m ruff check .

# Formatting
python -m ruff format --check .

# Auto-fix
python -m ruff check . --fix
python -m ruff format .
```

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Client    │────▶│  Relay API   │────▶│  Order Service   │
│             │     │  (port 8000) │     │   (port 8001)    │
└─────────────┘     └──────┬───────┘     └────────┬─────────┘
                           │                      │
                    ┌──────▼───────┐     ┌────────▼─────────┐
                    │  PostgreSQL  │     │  PostgreSQL      │
                    │  (relay_     │     │  (relay_staging) │
                    │  _staging)   │     │                  │
                    └──────────────┘     └──────────────────┘
```

## Health Checks

- **Relay API**: `GET /health` → `{"status": "healthy", "service": "relay"}`
- **Relay API Readiness**: `GET /ready` → checks database connectivity
- **Order Service**: `GET /health` → `{"status": "healthy", "service": "order-management"}`

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
docker-compose ps

# Check logs
docker-compose logs postgres

# Test connection
psql "postgresql+psycopg://relay:password@localhost:5432/relay_staging" -c "SELECT 1"
```

### Migration Issues
```bash
# Check current revision
alembic current

# Check pending migrations
alembic heads

# Force set revision (if needed)
alembic stamp head
```

### Application Issues
```bash
# Check logs
docker-compose logs -f relay-api
docker-compose logs -f order-service

# Check ports
netstat -tlnp | grep -E '8000|8001|5432'
```

## Security Notes

- Never commit `.env` or `.env.staging` files
- Use strong passwords for staging
- Rotate `LLM_API_KEY` and `DEMO_API_KEY` regularly
- Use `hmac.compare_digest()` for API key comparison (already implemented)
- Rate limiting is in-memory (not distributed) - suitable for staging only

## Rollback Procedure

```bash
# Rollback migration
alembic downgrade -1

# Or to specific revision
alembic downgrade <revision_id>
```

## Support

For issues, check:
1. Application logs: `docker-compose logs -f`
2. Database logs: `docker-compose logs postgres`
4. Application health: `curl http://localhost:8000/health`
5. Database connectivity: `curl http://localhost:8000/ready`