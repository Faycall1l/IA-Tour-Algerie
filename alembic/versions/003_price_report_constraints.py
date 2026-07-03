"""add constraints and indexes to price_reports

Revision ID: 003
Revises: 002
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_price_reports_route",
        "price_reports",
        ["origin_wilaya_id", "dest_wilaya_id", "transport_mode"],
    )
    op.create_check_constraint(
        "ck_price_positive",
        "price_reports",
        "price_dzd > 0",
    )
    op.create_check_constraint(
        "ck_valid_transport_mode",
        "price_reports",
        "transport_mode IN ('taxi', 'bus', 'train', 'plane', 'ferry')",
    )
    op.create_check_constraint(
        "ck_valid_confidence",
        "price_reports",
        "confidence IN ('user', 'verified', 'official')",
    )


def downgrade() -> None:
    op.drop_index("ix_price_reports_route", table_name="price_reports")
    op.drop_constraint("ck_price_positive", "price_reports", type_="check")
    op.drop_constraint("ck_valid_transport_mode", "price_reports", type_="check")
    op.drop_constraint("ck_valid_confidence", "price_reports", type_="check")
