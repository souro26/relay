# Relay

A Python-first business workflow integration system for processing customer requests to modify orders.

## Architecture Overview

Relay demonstrates production-minded engineering for AI-powered business workflows. The initial use case processes customer messages requesting order modifications (e.g., changing delivery dates), interpreting the request, retrieving the relevant order from an external API, executing the update, and persisting the complete execution history.

### System Components

**Relay (Core)** - The workflow orchestration engine:
- Receives structured order change requests via HTTP
- Validates requests and registers inbound events
- Detects duplicate events using database uniqueness constraints
- Orchestrates communication with external order management service
- Persists execution state and outcomes in PostgreSQL

**Order Management Service (Simulated External System)** - A separate FastAPI service:
- In-memory order store with realistic seed data
- RESTful endpoints for order retrieval and delivery date updates
- Business rule enforcement (no changes to shipped/cancelled/delivered orders)
- Resets on process restart (demonstration only)

### Stack

- **Python 3.11+**
- **FastAPI** - HTTP API framework (both services)
- **Pydantic / Pydantic Settings** - Configuration and request validation
- **SQLAlchemy 2.x** - Database ORM (Relay only)
- **PostgreSQL** - Persistent storage (Relay only)
- **Alembic** - Database migrations (Relay only)
- **HTTPX** - HTTP client for external service communication
- **Pytest** - Testing
- **Ruff** - Linting and formatting

### Project Structure

```
relay/
├── .github/                      # CI/CD workflows (lint, test, build)
├── docker/                       # Container definitions & startup scripts
│   ├── Dockerfile                # Multi-stage production image for Relay
│   ├── Dockerfile.order-service  # Production image for Order Service
│   └── entrypoint.sh             # Container migration & startup script
├── src/
│   ├── relay/                    # Core Relay application
│   │   ├── api/                  # FastAPI routes & middleware
│   │   ├── core/                 # Configuration & logging
│   │   ├── db/                   # Database session and base
│   │   ├── models/               # SQLAlchemy & Pydantic models
│   │   ├── services/             # Workflow orchestration
│   │   ├── static/               # Frontend static assets (CSS, JS)
│   │   └── templates/            # Jinja2 frontend templates
│   └── order_service/            # Simulated external order management
│       ├── main.py               # FastAPI application
│       ├── models.py             # Pydantic models
│       ├── store.py              # Order store
│       └── db.py                 # DB session helper
├── tests/                        # Comprehensive test suite
├── alembic/                      # Database migration scripts
├── scripts/                      # Operational & diagnostic utilities
│   ├── check_data.py             # Database inspection script
│   └── check_tables.py           # Table schema verification script
├── .dockerignore                 # Docker build ignore rules
├── .env.example                  # Environment template
├── .env.staging.template         # Staging environment template
├── alembic.ini                   # Alembic configuration
├── docker-compose.yml            # Multi-service local & staging compose
├── pyproject.toml                # Project metadata & tool config
└── README.md
```

## Prerequisites

- Python 3.11 or newer
- PostgreSQL 14 or newer
- pip (or uv/poetry)

## Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Application environment: `development`, `staging`, `production`, `test` | `development` |
| `DATABASE_URL` | PostgreSQL connection URL (required) | - |
| `LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` |
| `ORDER_SERVICE_URL` | Base URL for order management service | `http://localhost:8001` |
| `ORDER_SERVICE_TIMEOUT` | HTTP timeout for order service calls (seconds) | `10.0` |

Example `DATABASE_URL`:
```
postgresql://user:password@localhost:5432/relay
```

Example `.env` for local development:
```bash
ENVIRONMENT=development
DATABASE_URL=postgresql://relay:relay_dev_password@localhost:5432/relay
LOG_LEVEL=INFO
ORDER_SERVICE_URL=http://localhost:8001
ORDER_SERVICE_TIMEOUT=10.0
```

## Database Setup

### Create the Database

```sql
CREATE DATABASE relay;
CREATE USER relay WITH ENCRYPTED PASSWORD 'relay';
GRANT ALL PRIVILEGES ON DATABASE relay TO relay;
```

### Run Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# View migration history
alembic history
```

## Starting the Services

### Order Management Service (Terminal 1)

```bash
# Install dependencies
pip install -e ".[dev]"

# Start the order service on port 8001
uvicorn order_service.main:app --reload --host 0.0.0.0 --port 8001
```

The order service will be available at `http://localhost:8001`.

### Relay API (Terminal 2)

```bash
# Install dependencies (if not already done)
pip install -e ".[dev]"

# Start Relay API on port 8000
uvicorn relay.api.main:app --reload --host 0.0.0.0 --port 8000
```

The Relay API will be available at `http://localhost:8000`.

## Running Tests

```bash
# Run all tests (34 tests: 22 Stage 1 + 12 Stage 2)
pytest

# Run with coverage
pytest --cov=relay --cov=order_service

# Run specific test file
pytest tests/test_order_change.py -v
```

Tests use isolated configuration and SQLite for database constraint tests. They do not require a running PostgreSQL instance for most tests, but integration tests do require PostgreSQL.

## API Endpoints

### Relay (Port 8000)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Basic health check (no DB required) |
| GET | `/ready` | Readiness check (includes DB connectivity) |
| POST | `/api/v1/order-change-requests` | Submit order change request |
| GET | `/api/v1/workflows` | List workflow executions with pagination |
| GET | `/api/v1/workflows/{execution_id}` | Retrieve a single workflow execution |

### Order Management Service (Port 8001)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/orders` | List all orders (optionally filter by `customer_id`) |
| GET | `/orders/{order_id}` | Retrieve order by ID |
| PATCH | `/orders/{order_id}` | Update order delivery date |

## Example Requests

### Submit Order Change Request

```bash
curl -X POST http://localhost:8000/api/v1/order-change-requests \
  -H "Content-Type: application/json" \
  -d '{
    "source_system": "demo",
    "external_event_id": "evt-1001",
    "customer_id": "customer-101",
    "order_id": "ORD-A0608F16",
    "requested_delivery_date": "2026-11-15T00:00:00+00:00"
  }'
```

### Success Response (201 Created)

```json
{
  "execution_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "workflow_type": "order_change",
  "result": {
    "order_id": "ORD-A0608F16",
    "previous_delivery_date": "2026-11-10T00:00:00+00:00",
    "new_delivery_date": "2026-11-15T00:00:00+00:00",
    "order_status": "confirmed"
  },
  "error_details": null,
  "created_at": "2026-10-13T12:00:00.000000+00:00",
  "updated_at": "2026-10-13T12:00:05.000000+00:00",
  "completed_at": "2026-10-13T12:00:05.000000+00:00"
}
```

### Error Responses

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `CUSTOMER_ORDER_MISMATCH` | Order belongs to different customer |
| 404 | `ORDER_NOT_FOUND` | Order does not exist |
| 409 | `DUPLICATE_EVENT` | Duplicate event detected (includes existing execution ID) |
| 409 | `INVALID_STATE_TRANSITION` | Cannot change shipped/cancelled/delivered order |
| 422 | Validation Error | Invalid request data (e.g., malformed date) |
| 502 | `EXTERNAL_SERVICE_ERROR` | Order service returned 5xx error |
| 503 | `EXTERNAL_SERVICE_UNAVAILABLE` | Order service unreachable |
| 504 | `EXTERNAL_SERVICE_TIMEOUT` | Order service request timed out |

### Retrieve Workflow Execution

```bash
curl http://localhost:8000/api/v1/workflows/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### List Workflows

```bash
curl "http://localhost:8000/api/v1/workflows?page=1&page_size=20"
```

### Order Service Endpoints

```bash
# List all orders
curl http://localhost:8001/orders

# Get specific order
curl http://localhost:8001/orders/ORD-A0608F16

# Update delivery date
curl -X PATCH http://localhost:8001/orders/ORD-A0608F16 \
  -H "Content-Type: application/json" \
  -d '{"delivery_date": "2026-11-15T00:00:00+00:00"}'
```

## Seeded Order Data

The order service starts with these orders:

| Order ID | Customer | Delivery Date | Status |
|----------|----------|---------------|--------|
| ORD-XXXXXX | customer-101 | 2026-11-10 | confirmed |
| ORD-XXXXXX | customer-101 | 2026-11-20 | pending |
| ORD-XXXXXX | customer-102 | 2026-11-15 | shipped |
| ORD-XXXXXX | customer-103 | 2026-11-25 | cancelled |
| ORD-XXXXXX | customer-104 | 2026-12-01 | delivered |

(Order IDs are generated with `ORD-` prefix + 8 random hex chars)

## Current Implementation Status

### Completed (Phase 1 - Foundation)
- [x] Project structure with `src/` layout
- [x] Centralized typed configuration with validation
- [x] SQLAlchemy models: `WorkflowExecution`, `InboundEvent`
- [x] Database constraints and indexes
- [x] Alembic migration setup with initial migration
- [x] FastAPI application with health, readiness, and workflow endpoints
- [x] Structured error responses with appropriate HTTP status codes
- [x] Comprehensive test suite (22 tests passing)
- [x] Linting and formatting with Ruff

### Completed (Phase 2 - Order Change Workflow)
- [x] Simulated order management service with in-memory store
- [x] Order change request endpoint with full validation
- [x] Duplicate event detection using database uniqueness constraint
- [x] Customer/order ownership validation
- [x] Business rule enforcement (no changes to shipped/cancelled/delivered)
- [x] External service communication with proper error handling
- [x] Execution state persistence (success/failure states)
- [x] Duplicate event handling (returns existing execution ID)
- [x] Comprehensive test coverage (12 new tests)
- [x] All 34 tests passing

### Not Yet Implemented (Future Phases)
- [ ] LLM integration for request interpretation
- [ ] Authentication and authorization
- [ ] Request/response logging middleware
- [ ] Metrics and monitoring
- [ ] Background workers for async processing
- [ ] Streamlit inspection interface

## Known Limitations

1. **PostgreSQL Required**: The application requires a running PostgreSQL instance. SQLite is not supported as a production substitute due to differences in JSONB support, enum handling, and concurrent access patterns.

2. **Simulated Order Service**: The order management service uses an in-memory store that resets on process restart. It is not a production order management system.

3. **No Authentication**: All endpoints are currently public. Authentication will be added in a future phase.

4. **No Background Processing**: Workflow execution is synchronous. Async processing with Celery or similar will be added later.

5. **Manual Migration Application**: Migrations must be applied manually with `alembic upgrade head`. No auto-migration on startup.

6. **Limited Pagination**: The workflow list endpoint uses offset-based pagination. Cursor-based pagination may be added for better performance on large datasets.

7. **At-Least-Once Execution**: The system does not guarantee exactly-once execution across PostgreSQL and the external HTTP service. Duplicate detection prevents re-execution, but network partitions between commit and response could theoretically cause issues.

## Development Commands

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Run tests with verbose output
pytest -v

# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback last migration
alembic downgrade -1
```

## License

This is a demonstration project, not intended for production use without further development.