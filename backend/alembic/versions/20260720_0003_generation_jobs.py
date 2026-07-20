"""add durable generation jobs

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260720_0003"
down_revision: Union[str, Sequence[str], None] = "20260720_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "presentation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="QUEUED", nullable=False
        ),
        sa.Column(
            "stage", sa.String(length=40), server_default="queued", nullable=False
        ),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"], ["presentations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generation_jobs_presentation_id",
        "generation_jobs",
        ["presentation_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_job_type",
        "generation_jobs",
        ["job_type"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_status",
        "generation_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_status", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_job_type", table_name="generation_jobs")
    op.drop_index(
        "ix_generation_jobs_presentation_id", table_name="generation_jobs"
    )
    op.drop_table("generation_jobs")
