"""Lazy SQLAlchemy engine construction."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Build the PostgreSQL engine on demand; app import does not connect."""
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured before database access")
    return create_engine(database_url, pool_pre_ping=True)
