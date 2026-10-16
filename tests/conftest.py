"""Test configuration and fixtures for Relay tests.

This module sets up the test environment with mocked dependencies for unit tests.
Integration tests for the order service use a real database separately.
"""

import os
import tempfile
import uuid
from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

import order_service.models  # noqa: F401
from relay.core.config import settings
from relay.db.base import Base

os.environ["DATABASE_URL"] = "sqlite:///./test_relay.db"

# Override settings for test
settings.database_url = "sqlite:///./test_relay.db"


def pytest_addoption(parser):
    """Add --run-integration command line option."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require PostgreSQL",
    )


def pytest_configure(config):
    """Register integration marker."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests requiring PostgreSQL"
    )


def _is_integration_mode(request):
    """Check if integration tests should run."""
    return request.config.getoption("--run-integration")


# Module-level storage for PostgreSQL integration test database (session-scoped)
_pg_integration_db_engine = None


def _validate_integration_test_db(url: str) -> None:
    """Validate that the integration test database strictly targets relay_test."""
    parsed = make_url(url)
    if parsed.database != "relay_test":
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Integration tests must target 'relay_test', "
            f"refusing to run against database '{parsed.database}'"
        )


def _get_pg_integration_db_engine():
    """Get or create the PostgreSQL integration test database engine (session-scoped)."""
    global _pg_integration_db_engine
    if _pg_integration_db_engine is None:
        # Use explicit environment variable if set, with safe local fallback
        db_url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+psycopg://relay:relay@localhost:5433/relay_test",
        )
        _validate_integration_test_db(db_url)

        _pg_integration_db_engine = create_engine(db_url, echo=False, pool_pre_ping=True)

        # Import ALL models to register them with Base metadata before create_all
        import order_service.models  # noqa: F401
        from relay.models import InboundEvent, WorkflowExecution  # noqa: F401

        # Note: We don't call create_all here - migrations handle schema
    return _pg_integration_db_engine


def _cleanup_pg_integration_db():
    """Clean up the PostgreSQL integration test database."""
    global _pg_integration_db_engine
    if _pg_integration_db_engine is not None:
        _pg_integration_db_engine.dispose()
        _pg_integration_db_engine = None


@pytest.fixture(scope="session", autouse=True)
def cleanup_pg_integration_db():
    """Clean up PostgreSQL integration test database at end of session."""
    yield
    _cleanup_pg_integration_db()


@pytest.fixture(scope="session")
def pg_integration_db_engine(request):
    """Return the shared PostgreSQL integration test database engine."""
    if not _is_integration_mode(request):
        pytest.skip("PostgreSQL integration tests require --run-integration flag")
    return _get_pg_integration_db_engine()


@pytest.fixture
def pg_integration_db_session(request, pg_integration_db_engine):
    """Create a test database session for PostgreSQL integration tests."""
    if not _is_integration_mode(request):
        pytest.skip("PostgreSQL integration tests require --run-integration flag")

    # Fail-closed safety validation: strictly forbid running cleanup on non-test databases
    if pg_integration_db_engine.url.database != "relay_test":
        target_db = pg_integration_db_engine.url.database
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Refusing to perform test cleanup against '{target_db}'"
        )

    # Clean only idempotency keys and relay tables, preserve seed orders
    from order_service.models import IdempotencyKey
    from sqlalchemy import delete, text

    with pg_integration_db_engine.connect() as conn:
        conn.execute(delete(IdempotencyKey))
        conn.execute(text("DELETE FROM inbound_events"))
        conn.execute(text("DELETE FROM workflow_executions"))
        conn.commit()

    SessionLocal = sessionmaker(
        bind=pg_integration_db_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def pg_integration_order_client(request, pg_integration_db_engine, pg_integration_db_session):
    """Test client for order service with real PostgreSQL database for integration tests."""
    if not _is_integration_mode(request):
        pytest.skip("PostgreSQL integration tests require --run-integration flag")
    with (
        patch("order_service.db.engine", pg_integration_db_engine),
        patch("order_service.db.SessionLocal", lambda: pg_integration_db_session),
    ):
        from order_service.main import app

        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def pg_integration_relay_client(request, pg_integration_db_engine, pg_integration_db_session):
    """Test client for Relay API with real PostgreSQL database for integration tests."""
    if not _is_integration_mode(request):
        pytest.skip("PostgreSQL integration tests require --run-integration flag")
    from relay.core.ratelimit import reset_rate_limiter

    reset_rate_limiter()
    try:
        with (
            patch(
                "relay.core.ratelimit.InMemoryRateLimiter.check_rate_limit",
                return_value=(True, {"limit": 100, "remaining": 99, "reset_after_seconds": 60}),
            ),
            patch("relay.db.session.engine", pg_integration_db_engine),
            patch("relay.db.session.SessionLocal", lambda: pg_integration_db_session),
            patch("relay.api.main.engine", pg_integration_db_engine),
        ):
            from relay.api.main import app as relay_app

            with TestClient(relay_app) as test_client:
                yield test_client
    finally:
        reset_rate_limiter()


# Module-level storage for SQLite integration test database (session-scoped)
_integration_db_engine = None
_integration_db_path = None


def _get_integration_db_engine():
    """Get or create the integration test database engine (session-scoped)."""
    global _integration_db_engine, _integration_db_path
    if _integration_db_engine is None:
        # Create a unique temporary database file
        temp_dir = tempfile.gettempdir()
        _integration_db_path = os.path.join(temp_dir, f"test_relay_{uuid.uuid4().hex[:8]}.db")
        db_url = f"sqlite:///{_integration_db_path}"

        _integration_db_engine = create_engine(
            db_url, echo=False, connect_args={"check_same_thread": False}
        )

        # Import ALL models to register them with Base metadata before create_all
        import order_service.models  # noqa: F401
        from relay.models import InboundEvent, WorkflowExecution  # noqa: F401

        Base.metadata.create_all(_integration_db_engine)
    return _integration_db_engine


def _cleanup_integration_db():
    """Clean up the integration test database."""
    global _integration_db_engine, _integration_db_path
    if _integration_db_engine is not None:
        try:
            Base.metadata.drop_all(_integration_db_engine)
        except Exception:
            pass
        _integration_db_engine.dispose()
        _integration_db_engine = None
        if _integration_db_path:
            try:
                os.remove(_integration_db_path)
            except Exception:
                pass
            _integration_db_path = None


@pytest.fixture(scope="session", autouse=True)
def cleanup_integration_db():
    """Clean up integration test database at end of session."""
    yield
    _cleanup_integration_db()


@pytest.fixture
def integration_db_engine():
    """Return the shared integration test database engine."""
    return _get_integration_db_engine()


@pytest.fixture
def clean_integration_db(integration_db_engine):
    """Clean all tables between integration tests to ensure isolation.

    This fixture is NOT autouse - integration tests must explicitly request it.
    """
    from sqlalchemy import delete, text

    from order_service.models import IdempotencyKey, Order

    with integration_db_engine.connect() as conn:
        # Delete in order to respect foreign keys
        conn.execute(delete(IdempotencyKey))
        conn.execute(delete(Order))
        # Delete relay tables
        conn.execute(text("DELETE FROM inbound_events"))
        conn.execute(text("DELETE FROM workflow_executions"))
        conn.commit()
    yield
    # Clean up after test as well
    with integration_db_engine.connect() as conn:
        conn.execute(delete(IdempotencyKey))
        conn.execute(delete(Order))
        conn.execute(text("DELETE FROM inbound_events"))
        conn.execute(text("DELETE FROM workflow_executions"))
        conn.commit()


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    # Set high rate limit for tests
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "10000")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the rate limiter between tests to ensure test isolation."""
    from relay.core.ratelimit import reset_rate_limiter

    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def mock_db_session():
    """Mock database session for unit tests."""
    session = MagicMock()
    return session


@pytest.fixture
def client():
    """Test client with mocked database for Relay API unit tests."""
    mock_session = MagicMock()
    mock_engine = MagicMock()

    with (
        patch("relay.db.session.engine", mock_engine),
        patch("relay.db.session.SessionLocal", lambda: mock_session),
        patch("relay.api.main.engine", mock_engine),
    ):
        from relay.api.main import app

        with TestClient(app) as test_client:
            yield test_client, mock_session


@pytest.fixture
def order_client():
    """Test client for order service with mocked database for unit tests."""
    mock_session = MagicMock()
    mock_engine = MagicMock()

    with (
        patch("order_service.db.engine", mock_engine),
        patch("order_service.db.SessionLocal", lambda: mock_session),
    ):
        from order_service.main import app

        with TestClient(app) as test_client:
            yield test_client, mock_session


@pytest.fixture
def sample_workflow():
    import uuid
    from datetime import datetime

    from relay.models import WorkflowExecution, WorkflowStatus

    workflow = MagicMock(spec=WorkflowExecution)
    workflow.id = uuid.uuid4()
    workflow.workflow_type = "order_modification"
    workflow.status = WorkflowStatus.PENDING
    workflow.original_request = {"order_id": "123", "action": "change_date"}
    workflow.interpreted_request = None
    workflow.result = None
    workflow.error_details = None
    workflow.created_at = datetime.now(UTC)
    workflow.updated_at = datetime.now(UTC)
    workflow.completed_at = None
    return workflow


@pytest.fixture
def integration_db_session(integration_db_engine):
    """Create a test database session for integration tests."""
    SessionLocal = sessionmaker(
        bind=integration_db_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def integration_order_client(integration_db_engine, integration_db_session):
    """Test client for order service with real database for integration tests."""
    with (
        patch("order_service.db.engine", integration_db_engine),
        patch("order_service.db.SessionLocal", lambda: integration_db_session),
    ):
        from order_service.main import app

        with TestClient(app) as test_client:
            yield test_client
