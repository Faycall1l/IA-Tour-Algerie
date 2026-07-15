"""017 Full-text search (tsvector) + GeoJSON support

Revision ID: 017
Revises: 016
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── POIs full-text search ──
    op.add_column(
        "pois",
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('french', "
                "coalesce(name, '') || ' ' || "
                "coalesce(name_en, '') || ' ' || "
                "coalesce(name_ar, '') || ' ' || "
                "coalesce(description, '') || ' ' || "
                "coalesce(category, '') || ' ' || "
                "coalesce(subtype, '') || ' ' || "
                "coalesce(commune, '') || ' ' || "
                "coalesce(operator, '') || ' ' || "
                "coalesce(cuisine, '') || ' ' || "
                "coalesce(neighborhood, '')"
                ")",
                persisted=False,
            ),
        ),
    )
    op.create_index("ix_pois_search_vector", "pois", ["search_vector"], postgresql_using="gin")

    # ── Stays full-text search ──
    op.add_column(
        "stays",
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('french', "
                "coalesce(name, '') || ' ' || "
                "coalesce(description, '') || ' ' || "
                "coalesce(property_type, '') || ' ' || "
                "coalesce(address, '')"
                ")",
                persisted=False,
            ),
        ),
    )
    op.create_index("ix_stays_search_vector", "stays", ["search_vector"], postgresql_using="gin")

    # ── Experiences full-text search ──
    op.add_column(
        "experiences",
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('french', "
                "coalesce(title, '') || ' ' || "
                "coalesce(description, '') || ' ' || "
                "coalesce(category, '')"
                ")",
                persisted=False,
            ),
        ),
    )
    op.create_index("ix_experiences_search_vector", "experiences", ["search_vector"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_pois_search_vector", table_name="pois")
    op.drop_column("pois", "search_vector")

    op.drop_index("ix_stays_search_vector", table_name="stays")
    op.drop_column("stays", "search_vector")

    op.drop_index("ix_experiences_search_vector", table_name="experiences")
    op.drop_column("experiences", "search_vector")
