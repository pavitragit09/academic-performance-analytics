"""Application settings, read from environment variables."""

import os

API_PREFIX = "/api/v1"
DEFAULT_DATABASE_URL = "sqlite:///./apas.db"


def get_database_url() -> str:
    """Return the database URL. SQLite is used for development and CI."""
    return os.getenv("APAS_DATABASE_URL", DEFAULT_DATABASE_URL)
