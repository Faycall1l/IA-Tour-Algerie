#!/usr/bin/env python3
"""Reassign POIs from parent wilayas to the 11 new wilayas (59-69).

For each new wilaya, find existing POIs that are within 40km of the center
but currently assigned to a different wilaya, and reassign them.
"""

import asyncio
import math
from sqlalchemy import text
from app.db.session import async_session

NEW_WILAYAS = {
    59: (34.11279, 2.1019, "Aflou"),
    60: (35.3972, 5.3658, "Barika"),
    61: (35.192365, 5.6668306, "El Kantara"),
    62: (34.748, 8.0594, "Bir El Ater"),
    63: (34.22259, -1.257, "El Aricha"),
    64: (35.21222, 2.3189, "Ksar Chellala"),
    65: (35.4542653, 2.904444, "Ain Ouessara"),
    66: (34.15429, 3.50309, "Messaad"),
    67: (35.88889, 2.74905, "Ksar El Boukhari"),
    68: (35.2091, 4.1744, "Bou Saada"),
    69: (32.898611, 0.544444, "El Abiodh Sidi Cheikh"),
}

RADIUS_KM = 40


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def reassign():
    async with async_session() as db:
        total_reassigned = 0

        for wilaya_id, (clat, clon, name) in NEW_WILAYAS.items():
            # Find POIs within radius that are assigned to a different wilaya
            rows = await db.execute(text("""
                SELECT id, wilaya_id, latitude, longitude, name
                FROM pois
                WHERE latitude BETWEEN :min_lat AND :max_lat
                  AND longitude BETWEEN :min_lon AND :max_lon
                  AND wilaya_id != :wilaya_id
            """), {
                "min_lat": clat - 0.4, "max_lat": clat + 0.4,
                "min_lon": clon - 0.4, "max_lon": clon + 0.4,
                "wilaya_id": wilaya_id,
            })

            to_reassign = []
            for poi in rows:
                d = haversine(clat, clon, poi.latitude, poi.longitude)
                if d <= RADIUS_KM:
                    to_reassign.append((poi.id, poi.wilaya_id, poi.name))

            if to_reassign:
                for poi_id, old_wilaya, pname in to_reassign:
                    await db.execute(text("""
                        UPDATE pois SET wilaya_id = :new_wilaya WHERE id = :poi_id
                    """), {"new_wilaya": wilaya_id, "poi_id": poi_id})
                await db.commit()
                total_reassigned += len(to_reassign)
                print(f"w{wilaya_id:2d} {name:30s}  +{len(to_reassign):4d} reassigned (from {set(w for _, w, _ in to_reassign)})")
            else:
                print(f"w{wilaya_id:2d} {name:30s}    +0 (no POIs within {RADIUS_KM}km)")

        print(f"\nTotal: {total_reassigned} POIs reassigned")


if __name__ == "__main__":
    asyncio.run(reassign())
