"""Database engine, session handling and table creation (SQLAlchemy 2)."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.app.config import get_database_url


class Base(DeclarativeBase):
    """Base class for every database table."""


def build_engine(url: str, **kwargs) -> Engine:
    """Create an engine. SQLite needs foreign keys switched on per connection."""
    if url.startswith("sqlite"):
        connect_args = kwargs.pop("connect_args", {})
        connect_args.setdefault("check_same_thread", False)
        kwargs["connect_args"] = connect_args

    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
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
