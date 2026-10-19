"""Runtime configuration, read from the environment once per process."""

import os
from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True)
class Settings:
    """Settings shared by every chronon process.

    Attributes:
        database_url: SQLAlchemy URL for Postgres (psycopg 3 driver).
        valkey_url: redis-py URL for Valkey.
        provider_keys_dir: Directory of provider public keys, one PEM per file,
            named ``<backend>.<key-name>.pem``.
        task_ttl_seconds: Lifetime of a task's hot status in Valkey.
    """

    database_url: str
    valkey_url: str
    provider_keys_dir: str
    task_ttl_seconds: int


def _database_url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://chronon:chronon@localhost:5432/chronon"
    )
    # CNPG's app secret holds a plain postgresql:// URI; we use psycopg 3.
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@cache
def get_settings() -> Settings:
    """Return the process settings, read from the environment on first use.

    Returns:
        The settings.
    """
    return Settings(
        database_url=_database_url(),
        valkey_url=os.environ.get("VALKEY_URL", "redis://localhost:6379/0"),
        provider_keys_dir=os.environ.get(
            "PROVIDER_KEYS_DIR", "/etc/chronon/provider-keys"
        ),
        task_ttl_seconds=int(os.environ.get("TASK_TTL_SECONDS", "86400")),
    )
