"""create editable presentation schema

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260720_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRESENTATION_STATUSES = (
    "DRAFT",
    "PARSING",
    "GENERATING_CONTENT",
    "RENDERING",
    "PREVIEW_READY",
    "COMPLETED",
    "FAILED",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    status_enum = postgresql.ENUM(
        *PRESENTATION_STATUSES, name="presentation_status"
    )
    status_enum.create(bind, checkfirst=True)

    if "ai_provider_configs" not in existing_tables:
        op.create_table(
            "ai_provider_configs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("base_url", sa.String(length=500), nullable=False),
            sa.Column("model", sa.String(length=180), nullable=False),
            sa.Column("image_model", sa.String(length=180), nullable=True),
            sa.Column("encrypted_api_key", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_ai_provider_configs_provider",
            "ai_provider_configs",
            ["provider"],
            unique=False,
        )
    else:
        provider_columns = {
            column["name"] for column in inspector.get_columns("ai_provider_configs")
        }
        if "image_model" not in provider_columns:
            op.add_column(
                "ai_provider_configs",
                sa.Column("image_model", sa.String(length=180), nullable=True),
            )

    if "presentations" not in existing_tables:
        op.create_table(
            "presentations",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column(
                "language",
                sa.String(length=16),
                server_default="zh-TW",
                nullable=False,
            ),
            sa.Column(
                "template",
                sa.String(length=40),
                server_default="editorial",
                nullable=False,
            ),
            sa.Column(
                "status",
                postgresql.ENUM(
                    *PRESENTATION_STATUSES,
                    name="presentation_status",
                    create_type=False,
                ),
                server_default="DRAFT",
                nullable=False,
            ),
            sa.Column("source_text", sa.Text(), nullable=True),
            sa.Column("outline", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column("last_rendered_revision", sa.Integer(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_presentations_status", "presentations", ["status"], unique=False
        )
    else:
        presentation_columns = {
            column["name"] for column in inspector.get_columns("presentations")
        }
        if "template" not in presentation_columns:
            op.add_column(
                "presentations",
                sa.Column(
                    "template",
                    sa.String(length=40),
                    server_default="editorial",
                    nullable=False,
                ),
            )
        if "revision" not in presentation_columns:
            op.add_column(
                "presentations",
                sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            )
        if "last_rendered_revision" not in presentation_columns:
            op.add_column(
                "presentations",
                sa.Column("last_rendered_revision", sa.Integer(), nullable=True),
            )

    if "presentation_versions" not in existing_tables:
        op.create_table(
            "presentation_versions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "presentation_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("language", sa.String(length=16), nullable=False),
            sa.Column("template", sa.String(length=40), nullable=False),
            sa.Column(
                "content", postgresql.JSONB(astext_type=sa.Text()), nullable=False
            ),
            sa.Column(
                "change_reason",
                sa.String(length=80),
                server_default="content_saved",
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["presentation_id"], ["presentations.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "presentation_id",
                "revision",
                name="uq_presentation_versions_presentation_revision",
            ),
        )
        op.create_index(
            "ix_presentation_versions_presentation_id",
            "presentation_versions",
            ["presentation_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_presentation_versions_presentation_id",
        table_name="presentation_versions",
    )
    op.drop_table("presentation_versions")
    op.drop_index("ix_presentations_status", table_name="presentations")
    op.drop_table("presentations")
    op.drop_index(
        "ix_ai_provider_configs_provider", table_name="ai_provider_configs"
    )
    op.drop_table("ai_provider_configs")
    postgresql.ENUM(
        *PRESENTATION_STATUSES, name="presentation_status"
    ).drop(op.get_bind(), checkfirst=True)
