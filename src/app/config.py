"""Application settings, read from environment variables."""

import os

API_PREFIX = "/api/v1"
DEFAULT_DATABASE_URL = "sqlite:///./apas.db"


def get_database_url() -> str:
    """Return the database URL. SQLite is used for development and CI."""
    return os.getenv("APAS_DATABASE_URL", DEFAULT_DATABASE_URL)


def get_smtp_host() -> str:
    """Mail server for alert e-mails. MailHog (localhost) is used in testing."""
    return os.getenv("APAS_SMTP_HOST", "localhost")


def get_smtp_port() -> int:
    """Mail server port. MailHog listens on 1025."""
    return int(os.getenv("APAS_SMTP_PORT", "1025"))


def get_mail_from() -> str:
    """Sender address used on alert e-mails."""
    return os.getenv("APAS_MAIL_FROM", "apas@localhost")


def get_db_pool_size() -> int:
    """Database connections kept open per process (APAS-NF-003: 200 concurrent users)."""
    return int(os.getenv("APAS_DB_POOL_SIZE", "20"))


def get_db_max_overflow() -> int:
    """Extra connections allowed when the pool is busy."""
    return int(os.getenv("APAS_DB_MAX_OVERFLOW", "60"))