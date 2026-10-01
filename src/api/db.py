"""SQLAlchemy engine/session setup. Supabase Postgres in production, SQLite in tests via dependency override."""
from __future__ import annotations

from typing import Optional

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    # Every ORM model in models.py inherits from this — it's what lets
    # Base.metadata.create_all()/Alembic see all the tables in one place.
    pass


def make_engine(database_url: Optional[str] = None):
    # Falls back to Settings().database_url (Supabase, from .env) unless a URL is
    # passed explicitly — tests pass their own throwaway SQLite URL instead.
    url = database_url or get_settings().database_url
    # pool_pre_ping checks a pooled connection is still alive before using it —
    # matters for Supabase, which can silently drop idle connections.
    return create_engine(url, pool_pre_ping=True)


# Module-level, set once by init_engine() — this is what get_db() below reads from.
engine = None
SessionLocal: Optional[sessionmaker] = None


def init_engine(database_url: Optional[str] = None) -> None:
    """Called once by create_app(); tests call this against a SQLite URL instead."""
    global engine, SessionLocal
    engine = make_engine(database_url)
    # autoflush=False/autocommit=False: nothing hits the DB until code explicitly
    # calls db.flush()/db.commit() — keeps writes predictable inside a request.
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    # FastAPI dependency: `db: Session = Depends(get_db)` in a route gets one Session
    # per request, and this generator's `finally` guarantees it's closed afterwards
    # even if the route raises.
    if SessionLocal is None:
        raise RuntimeError("init_engine() must be called before get_db()")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
