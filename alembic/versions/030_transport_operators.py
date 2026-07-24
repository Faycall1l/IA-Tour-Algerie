"""Add transport_operators table for real operator contacts.

Revision ID: 030
Revises: 029
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "3edf9d601281"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transport_operators",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("name_ar", sa.String(100), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("website", sa.String(300), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("headquarters_wilaya_id", sa.Integer, sa.ForeignKey("wilayas.id"), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("coverage_type", sa.String(30), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("metadata", sa.JSON, nullable=True),
    )

    op.create_index("ix_transport_operators_mode", "transport_operators", ["mode"])
    op.create_index("ix_transport_operators_name", "transport_operators", ["name"])


def downgrade() -> None:
    op.drop_index("ix_transport_operators_name")
    op.drop_index("ix_transport_operators_mode")
    op.drop_table("transport_operators")
