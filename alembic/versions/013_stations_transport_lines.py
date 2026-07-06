"""create stations, transport_lines, line_stops

Revision ID: 013
Revises: 012
Create Date: 2026-07-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("name_ar", sa.String(200), nullable=True),
        sa.Column("name_en", sa.String(200), nullable=True),
        sa.Column("wilaya_id", sa.Integer(),
                  sa.ForeignKey("wilayas.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("station_type", sa.String(20), nullable=False),
        sa.Column("operator", sa.String(30), nullable=False),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_stations_station_type",
        "stations",
        "station_type IN ('train','metro','tram','bus','airport','ferry','cable_car','taxi')",
    )
    op.create_check_constraint(
        "ck_stations_operator",
        "stations",
        "operator IN ('SNTF','EMA','SETRAM','SNTV','SOGRAL','TRANSTEV','Air Algérie','Algérie Ferries')",
    )

    op.create_table(
        "transport_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("operator", sa.String(30), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_transport_lines_mode",
        "transport_lines",
        "mode IN ('train','metro','tram','bus','airport','ferry','cable_car','taxi')",
    )

    op.create_table(
        "line_stops",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("line_id", UUID(as_uuid=True),
                  sa.ForeignKey("transport_lines.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("station_id", UUID(as_uuid=True),
                  sa.ForeignKey("stations.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("stop_order", sa.Integer(), nullable=False),
        sa.Column("distance_from_start_km", sa.Float(), nullable=True),
        sa.Column("travel_time_from_start_min", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_line_stops_stop_order",
        "line_stops",
        "stop_order >= 0",
    )


def downgrade() -> None:
    op.drop_table("line_stops")
    op.drop_table("transport_lines")
    op.drop_table("stations")
