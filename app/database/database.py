"""Database engine and session management.

Phase 1 uses SQLite by default (see app/core/config.py). Because all
queries go through SQLAlchemy's ORM, switching to PostgreSQL later only
requires changing DATABASE_URL.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.database.models import Base

settings = get_settings()

# check_same_thread=False is required for SQLite when the same connection
# may be touched from multiple threads (e.g. Streamlit's execution model).
# It is a no-op for other database backends.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
# expire_on_commit=False: without this, every attribute on an ORM object
# becomes unusable the instant get_session()'s commit() runs, because
# SQLAlchemy's default behavior is to expire all loaded attributes on
# commit (forcing a re-fetch on next access) -- but by then the session
# is closed, so that re-fetch raises DetachedInstanceError. Callers
# throughout this codebase (and the dashboard) routinely fetch an object
# inside `with get_session()` and read its attributes after the block
# exits, which is exactly the pattern this setting is required to support.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables that don't already exist."""
    settings.ensure_data_dirs()
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, committing on success and rolling back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
