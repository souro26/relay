"""Database session management for the order service.

This module provides database session management that reuses the existing
PostgreSQL infrastructure from the Relay application.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from relay.core.config import settings

# Module-level engine and session factory (can be patched in tests)
engine = None
SessionLocal = None


def get_engine():
    """Get or create the database engine (lazy initialization)."""
    global engine
    if engine is None:
        engine = create_engine(
            str(settings.database_url),
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.environment == "development",
        )
    return engine


def get_session_local():
    """Get or create the session factory (lazy initialization)."""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False, expire_on_commit=False
        )
    return SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session with automatic commit/rollback/close."""
    session = get_session_local()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency for getting a database session."""
    session = get_session_local()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
