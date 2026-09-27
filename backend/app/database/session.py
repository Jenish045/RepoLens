"""Lazy SQLAlchemy engine construction."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Build the PostgreSQL engine on demand; app import does not connect."""
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured before database access")
    return create_engine(database_url, pool_pre_ping=True)


def get_session():
    """Yield a short-lived unit-of-work session for a request or background job."""
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
