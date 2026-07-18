"""020 Add experience tracking fields (source, is_verified, completion_count)

Adds source tracking, verification status, and completion metrics
to the experiences table for better lifecycle management.

Revision ID: 020
Revises: 019
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiences", sa.Column("source", sa.String(100), nullable=True))
    op.add_column("experiences", sa.Column("source_url", sa.String(500), nullable=True))
    op.add_column(
        "experiences",
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "experiences",
        sa.Column("completion_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_experiences_source", "experiences", ["source"])
    op.create_index("ix_experiences_is_verified", "experiences", ["is_verified"])


def downgrade() -> None:
    op.drop_index("ix_experiences_is_verified")
    op.drop_index("ix_experiences_source")
    op.drop_column("experiences", "completion_count")
    op.drop_column("experiences", "is_verified")
    op.drop_column("experiences", "source_url")
    op.drop_column("experiences", "source")
