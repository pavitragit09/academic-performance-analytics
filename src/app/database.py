"""Database engine, session handling and table creation (SQLAlchemy 2)."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.app.config import get_database_url, get_db_max_overflow, get_db_pool_size


class Base(DeclarativeBase):
    """Base class for every database table."""


def build_engine(url: str, **kwargs) -> Engine:
    """Create an engine. SQLite needs foreign keys switched on per connection."""
    if url.startswith("sqlite"):
        connect_args = kwargs.pop("connect_args", {})
        connect_args.setdefault("check_same_thread", False)
        connect_args.setdefault("timeout", 30)  # wait for a locked database instead of failing
        kwargs["connect_args"] = connect_args

    # The default pool (5 + 10 connections) runs dry with 200 concurrent users (APAS-NF-003).
    # In-memory databases and callers that choose their own pool keep what they asked for.
    if "poolclass" not in kwargs and url not in ("sqlite://", "sqlite:///:memory:"):
        kwargs.setdefault("pool_size", get_db_pool_size())
        kwargs.setdefault("max_overflow", get_db_max_overflow())

    in_memory = url in ("sqlite://", "sqlite:///:memory:")
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if not in_memory:
                # WAL lets readers and the one writer work at the same time, so session
                # updates no longer fail with "database is locked" under load (APAS-NF-003).
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


engine = build_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: open one session per request and always close it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(target: Engine = engine) -> None:
    """Create any missing tables."""
    from src.app import models  # noqa: F401  (registers the tables on Base)

    Base.metadata.create_all(bind=target)