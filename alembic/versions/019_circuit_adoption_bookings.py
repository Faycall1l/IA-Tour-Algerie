"""019 Polymorphic bookings (entity_type + entity_id) + indexes

Migrates bookings from single experience_id FK to polymorphic
entity_type + entity_id pattern supporting experiences AND circuits.

Revision ID: 019
Revises: 018
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add polymorphic columns
    op.add_column(
        "bookings",
        sa.Column("entity_type", sa.String(20), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
    )

    # Backfill: copy existing experience_id -> entity_id, set entity_type='experience'
    op.execute(
        "UPDATE bookings SET entity_type = 'experience', entity_id = experience_id"
    )

    # Make new columns non-nullable
    op.alter_column("bookings", "entity_type", nullable=False)
    op.alter_column("bookings", "entity_id", nullable=False)

    # Add check constraint
    op.create_check_constraint(
        "ck_booking_entity_type",
        "bookings",
        sa.text("entity_type IN ('experience', 'circuit')"),
    )

    # Index
    op.create_index("ix_bookings_entity", "bookings", ["entity_type", "entity_id"])

    # Drop old FK + column
    op.drop_constraint("bookings_experience_id_fkey", "bookings", type_="foreignkey")
    op.drop_index("ix_bookings_experience_id", table_name="bookings")
    op.drop_column("bookings", "experience_id")

    # Drop old booking status constraint (will be recreated by model)
    op.drop_constraint("ck_booking_status", "bookings", type_="check")


def downgrade() -> None:
    # Add back experience_id
    op.add_column(
        "bookings",
        sa.Column(
            "experience_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # Backfill from entity_id where entity_type = 'experience'
    op.execute(
        "UPDATE bookings SET experience_id = entity_id WHERE entity_type = 'experience'"
    )

    # Delete circuit bookings (no experience_id)
    op.execute("DELETE FROM bookings WHERE entity_type = 'circuit'")

    # Make experience_id non-nullable + FK
    op.alter_column("bookings", "experience_id", nullable=False)
    op.create_foreign_key(
        "bookings_experience_id_fkey",
        "bookings",
        "experiences",
        ["experience_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_bookings_experience_id", "bookings", ["experience_id"])

    # Drop polymorphic columns
    op.drop_index("ix_bookings_entity", table_name="bookings")
    op.drop_constraint("ck_booking_entity_type", "bookings", type_="check")
    op.drop_column("bookings", "entity_id")
    op.drop_column("bookings", "entity_type")
