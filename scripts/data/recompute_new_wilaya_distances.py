#!/usr/bin/env python3
"""Recompute wilaya_distances rows involving the 11 new wilayas (59-69).

The rows that referenced the old transport-hub placeholders were deleted by
fix_wilaya_numbering.py. This script re-fetches real OSRM road distances
between the official wilaya capitals and re-inserts them.

Usage: python scripts/data/recompute_new_wilaya_distances.py
"""

import asyncio
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

OSRM = "https://router.project-osrm.org/route/v1/driving/{p1};{p2}?overview=false"


def haversine(lat1, lng1, lat2, lng2) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def fetch_osrm(lat1, lng1, lat2, lng2) -> tuple[float, float] | None:
    url = OSRM.format(p1=f"{lng1},{lat1}", p2=f"{lng2},{lat2}")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "athar-data/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            route = data.get("routes", [])
            if data.get("code") == "Ok" and route:
                return route[0]["distance"] / 1000.0, route[0]["duration"] / 60.0
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


async def main() -> None:
    async with async_session() as session:
        async with session.begin():
            rows = (
                await session.execute(text("SELECT id, latitude, longitude FROM wilayas"))
            ).all()
            centers = {r[0]: (r[1], r[2]) for r in rows}
            assert len(centers) == 69, f"expected 69 wilayas, got {len(centers)}"

            pairs = []
            for a in centers:
                for b in centers:
                    if a < b and (a >= 59 or b >= 59):
                        pairs.append((a, b))
            print(f"fetching {len(pairs)} OSRM distances")

            inserted = fallback = 0
            for i, (a, b) in enumerate(pairs):
                lat1, lng1 = centers[a]
                lat2, lng2 = centers[b]
                res = fetch_osrm(lat1, lng1, lat2, lng2)
                if res is None:
                    km = haversine(lat1, lng1, lat2, lng2) * 1.3
                    mins = km / 80 * 60
                    road = "national"
                    fallback += 1
                else:
                    km, mins = res
                    straight = haversine(lat1, lng1, lat2, lng2)
                    road = "autoroute" if km / max(straight, 1e-6) < 1.25 else "national"
                await session.execute(
                    text("""
                        INSERT INTO wilaya_distances
                            (origin_wilaya_id, dest_wilaya_id, driving_distance_km,
                             driving_time_minutes, road_classification,
                             has_train_route, has_direct_flight)
                        VALUES (:a, :b, :km, :mins, :road, false, false)
                        ON CONFLICT (origin_wilaya_id, dest_wilaya_id) DO UPDATE SET
                            driving_distance_km = EXCLUDED.driving_distance_km,
                            driving_time_minutes = EXCLUDED.driving_time_minutes,
                            road_classification = EXCLUDED.road_classification
                    """),
                    {"a": a, "b": b, "km": round(km, 1), "mins": round(mins, 1), "road": road},
                )
                inserted += 1
                if i % 50 == 0:
                    print(f"  {i}/{len(pairs)}...")
                time.sleep(0.15)
            print(f"DONE: {inserted} rows, {fallback} haversine fallbacks")


if __name__ == "__main__":
    asyncio.run(main())
