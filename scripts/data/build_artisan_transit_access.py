"""Build artisan <-> nearest transit station walking edges (artisan_transit_access).

For every artisan in the `artisans` table, find the closest transit stations
(up to MAX_STATIONS, within MAX_WALK_KM) using a grid-based spatial index over
the `stations` table, and persist the walking edges with rank 0 = closest.
Walking time estimated at 80 m/min (4.8 km/h), same convention as the station
`transfers` edges. Idempotent: the table is rebuilt (DELETE + INSERT) on every
run, so re-running after artisan/station changes is safe.

Usage:
    .venv/bin/python scripts/data/build_artisan_transit_access.py [--max-walk-km 5] [--max-stations 3]
"""

import argparse
import asyncio
import math
import os

import asyncpg

WALKING_M_PER_MIN = 80.0
MAX_WALK_KM = 5.0
GRID_CELL_KM = 1.0

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _cell(lat: float, lng: float, cell_deg: float) -> tuple[int, int]:
    return (int(lat / cell_deg), int(lng / cell_deg))


def _ring_cells(r: int):
    if r <= 0:
        yield (0, 0)
        return
    for x in range(-r, r + 1):
        yield (x, -r)
        yield (x, r)
    for y in range(-r + 1, r):
        yield (-r, y)
        yield (r, y)


class GridIndex:
    """Grid-based spatial index over transit stations."""

    def __init__(self, stations: list[dict], cell_deg: float) -> None:
        self.cell_deg = cell_deg
        self.grid: dict[tuple[int, int], list[dict]] = {}
        for s in stations:
            self.grid.setdefault(_cell(s["latitude"], s["longitude"], cell_deg), []).append(s)

    def nearest(self, lat: float, lng: float, max_km: float, limit: int) -> list[dict]:
        c = _cell(lat, lng, self.cell_deg)
        hits: list[tuple[float, dict]] = []
        km_per_cell = self.cell_deg * 111.0
        max_r = int(max_km / km_per_cell) + 1
        for r in range(max_r + 1):
            if r * km_per_cell > (hits[0][0] if hits else max_km):
                break
            for dx, dy in _ring_cells(r):
                for s in self.grid.get((c[0] + dx, c[1] + dy), []):
                    d = _haversine_km(lat, lng, s["latitude"], s["longitude"])
                    if d <= max_km:
                        hits.append((d, s))
            hits.sort(key=lambda h: h[0])
            hits = hits[:limit]
        return [s for _, s in hits]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-walk-km", type=float, default=MAX_WALK_KM)
    parser.add_argument("--max-stations", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = await asyncpg.connect(DATABASE_URL)
    artisans = await conn.fetch(
        "SELECT id, name, latitude, longitude FROM artisans WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
    )
    stations = await conn.fetch("SELECT id, latitude, longitude FROM stations")
    print(f"artisans: {len(artisans)}, stations: {len(stations)}", flush=True)

    index = GridIndex([dict(s) for s in stations], GRID_CELL_KM / 111.0)

    pairs: list[tuple[dict, dict, float]] = []
    for a in artisans:
        nearest = index.nearest(a["latitude"], a["longitude"], args.max_walk_km, args.max_stations)
        for s in nearest:
            d = _haversine_km(a["latitude"], a["longitude"], s["latitude"], s["longitude"])
            pairs.append((a, s, d))

    connected = {id(a) for a, _s, _d in pairs}
    print(
        f"connected: {len(connected)}/{len(artisans)} artisans, "
        f"{len(pairs)} edges (max {args.max_stations} per artisan)",
        flush=True,
    )
    if args.dry_run:
        await conn.close()
        return

    async with conn.transaction():
        await conn.execute("DELETE FROM artisan_transit_access")
        if pairs:
            per_artisan: dict[str, int] = {}
            for a, s, d in pairs:
                aid = str(a["id"])
                rank = per_artisan.get(aid, 0)
                per_artisan[aid] = rank + 1
                await conn.execute(
                    "INSERT INTO artisan_transit_access "
                    "(artisan_id, station_id, distance_m, walking_time_min, rank, source) "
                    "VALUES ($1, $2, $3, $4, $5, 'spatial')",
                    aid,
                    str(s["id"]),
                    round(d * 1000, 1),
                    round(d * 1000 / WALKING_M_PER_MIN, 1),
                    rank,
                )
    n = await conn.fetchval("SELECT count(*) FROM artisan_transit_access")
    print(f"inserted {n} edges", flush=True)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
