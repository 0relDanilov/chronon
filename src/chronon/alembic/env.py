"""Alembic environment: runs on the connection that chronon.db.migrate holds."""

from alembic import context
from sqlalchemy.engine import Connection

from chronon.db import Base

connection: Connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
