#!/usr/bin/env python3
"""Seed wilaya_distances table from OSRM road distance data.

Usage: python scripts/seed_wilaya_distances.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import async_session
from sqlalchemy import text


async def main() -> None:
    src = Path(__file__).resolve().parent.parent / "app" / "data" / "wilaya_distances.json"
    if not src.exists():
        print(f"❌ {src} not found")
        sys.exit(1)

    data = json.loads(src.read_text())
    print(f"📂 Loaded {len(data)} entries from {src}")

    upsert_sql = text("""
        INSERT INTO wilaya_distances
            (created_at, updated_at, origin_wilaya_id, dest_wilaya_id,
             driving_distance_km, driving_time_minutes, road_classification,
             has_train_route, has_direct_flight)
        VALUES
            (NOW(), NOW(), :origin_id, :dest_id,
             :distance_km, :time_min, :road,
             :train, :flight)
        ON CONFLICT (origin_wilaya_id, dest_wilaya_id)
        DO UPDATE SET
            driving_distance_km = EXCLUDED.driving_distance_km,
            driving_time_minutes = EXCLUDED.driving_time_minutes,
            road_classification = EXCLUDED.road_classification,
            has_train_route = EXCLUDED.has_train_route,
            has_direct_flight = EXCLUDED.has_direct_flight,
            updated_at = NOW()
    """)

    async with async_session() as session:
        async with session.begin():
            for entry in data:
                await session.execute(
                    upsert_sql,
                    {
                        "origin_id": entry["origin_id"],
                        "dest_id": entry["dest_id"],
                        "distance_km": entry["driving_distance_km"],
                        "time_min": entry["driving_time_minutes"],
                        "road": entry["road_classification"],
                        "train": entry["has_train_route"],
                        "flight": entry["has_direct_flight"],
                    },
                )
        print(f"✅ Seeded {len(data)} rows into wilaya_distances")


if __name__ == "__main__":
    asyncio.run(main())
