"""add generation retry metadata

Revision ID: 20260720_0002
Revises: 20260720_0001
Create Date: 2026-07-20 17:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260720_0002"
down_revision: Union[str, Sequence[str], None] = "20260720_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE presentations "
        "ADD COLUMN IF NOT EXISTS generation_settings JSONB"
    )
    op.execute(
        "ALTER TABLE presentations "
        "ADD COLUMN IF NOT EXISTS failed_stage VARCHAR(40)"
    )
    op.execute(
        "ALTER TABLE presentations "
        "ADD COLUMN IF NOT EXISTS last_error TEXT"
    )


def downgrade() -> None:
    op.drop_column("presentations", "last_error")
    op.drop_column("presentations", "failed_stage")
    op.drop_column("presentations", "generation_settings")
