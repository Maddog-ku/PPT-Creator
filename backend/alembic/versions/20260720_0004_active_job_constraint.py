"""prevent duplicate active generation jobs

Revision ID: 20260720_0004
Revises: 20260720_0003
Create Date: 2026-07-20 20:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0004"
down_revision: Union[str, Sequence[str], None] = "20260720_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY presentation_id
                       ORDER BY CASE WHEN status = 'RUNNING' THEN 0 ELSE 1 END,
                                created_at,
                                id
                   ) AS position
            FROM generation_jobs
            WHERE status IN ('QUEUED', 'RUNNING')
        )
        UPDATE generation_jobs AS job
        SET status = 'CANCELED',
            stage = 'canceled_duplicate',
            cancel_requested = true,
            finished_at = now()
        FROM ranked
        WHERE job.id = ranked.id AND ranked.position > 1
        """
    )
    op.create_index(
        "uq_generation_jobs_one_active_per_presentation",
        "generation_jobs",
        ["presentation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_generation_jobs_one_active_per_presentation",
        table_name="generation_jobs",
    )
