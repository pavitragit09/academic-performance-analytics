"""Tests for the database connection pool settings (APAS-NF-003)."""

from sqlalchemy.pool import StaticPool

from src.app.config import get_db_max_overflow, get_db_pool_size
from src.app.database import build_engine


def test_pool_settings_default_to_enough_connections(monkeypatch):
    monkeypatch.delenv("APAS_DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("APAS_DB_MAX_OVERFLOW", raising=False)
    assert (get_db_pool_size(), get_db_max_overflow()) == (20, 60)


def test_pool_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("APAS_DB_POOL_SIZE", "30")
    monkeypatch.setenv("APAS_DB_MAX_OVERFLOW", "90")
    assert (get_db_pool_size(), get_db_max_overflow()) == (30, 90)


def test_file_database_gets_the_larger_pool(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'pool.db'}")
    assert engine.pool.size() == 20
    assert engine.pool._max_overflow == 60
    engine.dispose()


def test_in_memory_database_keeps_its_own_pool():
    engine = build_engine("sqlite://", poolclass=StaticPool)
    assert isinstance(engine.pool, StaticPool)
    engine.dispose()


def test_file_database_uses_wal_and_a_lock_timeout(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
    engine.dispose()


def test_in_memory_database_is_not_switched_to_wal():
    engine = build_engine("sqlite://", poolclass=StaticPool)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "memory"
    engine.dispose()


def test_file_database_uses_wal_and_a_lock_timeout(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
    engine.dispose()


def test_in_memory_database_is_not_switched_to_wal():
    engine = build_engine("sqlite://", poolclass=StaticPool)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "memory"
    engine.dispose()