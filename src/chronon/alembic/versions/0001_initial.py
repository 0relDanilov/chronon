"""Initial schema: datasets and tasks.

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the datasets and tasks tables."""
    op.create_table(
        "datasets",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("backend", sa.String(60), nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("comment", sa.String(300), nullable=False),
        sa.Column("producer", sa.String(60), nullable=False),
        sa.Column(
            "parent_id",
            sa.BigInteger,
            sa.ForeignKey("datasets.id"),
            nullable=True,
        ),
        sa.Column("data", JSONB, nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_datasets_backend_type_ts",
        "datasets",
        ["backend", "type", "timestamp"],
    )
    op.create_index("ix_datasets_parent", "datasets", ["parent_id"])
    op.create_index(
        "ix_datasets_data",
        "datasets",
        ["data"],
        postgresql_using="gin",
        postgresql_ops={"data": "jsonb_path_ops"},
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("backend", sa.String(60), nullable=False),
        sa.Column("workflow", sa.String(60), nullable=False),
        sa.Column("user_id", sa.String(120), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.Text, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tasks_backend_status", "tasks", ["backend", "status"])


def downgrade() -> None:
    """Drop both tables."""
    op.drop_table("tasks")
    op.drop_table("datasets")
