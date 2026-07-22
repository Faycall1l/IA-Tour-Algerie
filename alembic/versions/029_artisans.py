"""Add artisans table for craftspeople on the marketplace.

Revision ID: 029
Revises: 028
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artisans",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("craft_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("wilaya_id", sa.Integer, sa.ForeignKey("wilayas.id"), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("commune", sa.String(200), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("whatsapp", sa.String(20), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("photos", sa.ARRAY(sa.String(500)), nullable=True),
        sa.Column("opening_hours", sa.String(200), nullable=True),
        sa.Column("years_experience", sa.Integer, nullable=True),
        sa.Column("specializations", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("price_range_min", sa.Float, nullable=True),
        sa.Column("price_range_max", sa.Float, nullable=True),
        sa.Column("accepts_custom_orders", sa.Boolean, server_default="true"),
        sa.Column("has_workshop", sa.Boolean, server_default="true"),
        sa.Column("accepts_visitors", sa.Boolean, server_default="true"),
        sa.Column("is_verified", sa.Boolean, server_default="false"),
        sa.Column("metadata", sa.JSON, nullable=True),
    )

    op.execute(sa.text("""
        ALTER TABLE artisans ADD CONSTRAINT ck_artisan_craft_type
        CHECK (craft_type IN (
            'pottery', 'carpet_weaving', 'leather_work', 'woodwork',
            'metalwork', 'jewelry', 'textile', 'basket_weaving',
            'tilework', 'calligraphy', 'embroidery', 'stone_carving',
            'glasswork', 'copper_work', 'other'
        ))
    """))

    op.create_index("ix_artisans_wilaya", "artisans", ["wilaya_id"])
    op.create_index("ix_artisans_location", "artisans", ["latitude", "longitude"])
    op.create_index("ix_artisans_user", "artisans", ["user_id"])
    op.create_index("ix_artisans_craft", "artisans", ["craft_type"])

    op.execute(sa.text("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'traveler'
    """))
    op.execute(sa.text("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_user_role
    """))
    op.execute(sa.text("""
        ALTER TABLE users ADD CONSTRAINT ck_user_role
        CHECK (role IN ('traveler', 'guide', 'agency', 'hotel', 'admin', 'artisan'))
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_user_role"))
    op.execute(sa.text("""
        ALTER TABLE users ADD CONSTRAINT ck_user_role
        CHECK (role IN ('traveler', 'guide', 'agency', 'hotel', 'admin'))
    """))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS role"))

    op.drop_index("ix_artisans_craft")
    op.drop_index("ix_artisans_user")
    op.drop_index("ix_artisans_location")
    op.drop_index("ix_artisans_wilaya")
    op.drop_table("artisans")
