"""Add fun_fact to pois table.

Revision ID: 031
Revises: 030
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pois", sa.Column("fun_fact", sa.Text(), nullable=True))
    op.add_column("pois", sa.Column("fun_fact_source", sa.String(200), nullable=True))
    op.create_index("ix_pois_fun_fact", "pois", ["fun_fact"], postgresql_where="fun_fact IS NOT NULL")


def downgrade() -> None:
    op.drop_index("ix_pois_fun_fact", postgresql_where="fun_fact IS NOT NULL")
    op.drop_column("pois", "fun_fact_source")
    op.drop_column("pois", "fun_fact")
