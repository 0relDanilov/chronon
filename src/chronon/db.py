"""Postgres schema (tasks, datasets) and the migration runner.

Datasets keep their payload in JSONB with a GIN ``jsonb_path_ops`` index, so
the time-series endpoint can evaluate jsonpath in the database.
"""

import time
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    BigInteger,
    DateTime,
    Engine,
    ForeignKey,
    Index,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from chronon.settings import get_settings

# Any constant works; every chronon process uses the same one.
_MIGRATION_LOCK = 0x6368726F  # "chro"


class Base(DeclarativeBase):
    """Declarative base for chronon tables."""


class DatasetRow(Base):
    """A dataset: versioned backend state, linked to its parent."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    backend: Mapped[str] = mapped_column(String(60))
    type: Mapped[str] = mapped_column(String(60))
    comment: Mapped[str] = mapped_column(String(300), default="")
    producer: Mapped[str] = mapped_column(String(60))
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("datasets.id"), nullable=True
    )
    data: Mapped[Any] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_datasets_backend_type_ts", "backend", "type", "timestamp"),
        Index("ix_datasets_parent", "parent_id"),
        Index(
            "ix_datasets_data",
            "data",
            postgresql_using="gin",
            postgresql_ops={"data": "jsonb_path_ops"},
        ),
    )


class TaskRow(Base):
    """The durable record of a task. Valkey holds the hot copy."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    backend: Mapped[str] = mapped_column(String(60))
    workflow: Mapped[str] = mapped_column(String(60))
    user_id: Mapped[str] = mapped_column(String(120))
    payload: Mapped[Any] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    result: Mapped[str] = mapped_column(Text, default="{}")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_tasks_backend_status", "backend", "status"),)


@cache
def get_engine() -> Engine:
    """Return the process-wide engine.

    Returns:
        A pooled SQLAlchemy engine.
    """
    return create_engine(
        get_settings().database_url, pool_pre_ping=True, pool_size=5
    )


def migrate(retries: int = 60, delay: float = 2.0) -> None:
    """Bring the schema to the latest revision, safely from many processes.

    Waits for the database to accept connections, takes a Postgres advisory
    lock so concurrent callers apply migrations one at a time, then runs
    Alembic. A caller that finds the schema current does nothing.

    Args:
        retries: Connection attempts before giving up.
        delay: Seconds between attempts.

    Raises:
        OperationalError: If the database stays unreachable.
    """
    engine = get_engine()
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK}
                )
                try:
                    cfg = Config()
                    cfg.set_main_option(
                        "script_location",
                        str(Path(__file__).parent / "alembic"),
                    )
                    cfg.attributes["connection"] = conn
                    command.upgrade(cfg, "head")
                    conn.commit()
                finally:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"),
                        {"k": _MIGRATION_LOCK},
                    )
            return
        except OperationalError:
            if attempt == retries:
                raise
            print(f"database not ready (attempt {attempt}/{retries})")
            time.sleep(delay)
