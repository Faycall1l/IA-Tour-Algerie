"""seed wilaya_distances with real OSRM road distances

Revision ID: 012
Revises: 011
Create Date: 2026-07-05
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _load_data() -> list[dict[str, Any]]:
    src = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "wilaya_distances.json"
    if not src.exists():
        raise RuntimeError(f"Seed data not found: {src}")
    return json.loads(src.read_text())


def upgrade() -> None:
    data = _load_data()
    op.execute("TRUNCATE TABLE wilaya_distances")
    for entry in data:
        op.execute(
            """
            INSERT INTO wilaya_distances
                (created_at, updated_at, origin_wilaya_id, dest_wilaya_id,
                 driving_distance_km, driving_time_minutes, road_classification,
                 has_train_route, has_direct_flight)
            VALUES
                (NOW(), NOW(), %(origin_id)s, %(dest_id)s,
                 %(distance)s, %(time)s, %(road)s,
                 %(train)s, %(flight)s)
            """,
            {
                "origin_id": entry["origin_id"],
                "dest_id": entry["dest_id"],
                "distance": entry["driving_distance_km"],
                "time": entry["driving_time_minutes"],
                "road": entry["road_classification"],
                "train": entry["has_train_route"],
                "flight": entry["has_direct_flight"],
            },
        )
    print(f"✅ Seeded {len(data)} wilaya_distance rows")


def downgrade() -> None:
    op.execute("TRUNCATE TABLE wilaya_distances")
