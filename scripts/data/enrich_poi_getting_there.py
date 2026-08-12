"""Enrich pois.getting_there with nearest transit station + walk time.

Reuses the grid-based spatial index from build_artisan_transit_access.py: for
every POI, find the closest transit station (cap MAX_WALK_KM), and persist a
JSONB `getting_there` dict with the station name/type, distance and walking
time (80 m/min, same convention as station transfers edges). Idempotent:
rewrites getting_there for all geolocated POIs on every run.

Usage:
    .venv/bin/python scripts/data/enrich_poi_getting_there.py [--max-walk-km 5]
"""

import argparse
import asyncio
import json
import math
import os
import re

import asyncpg

WALKING_M_PER_MIN = 80.0
MAX_WALK_KM = 5.0
GRID_CELL_KM = 1.0

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

STATION_TYPE_FR = {
    "bus_station": "gare routière",
    "bus": "arrêt de bus",
    "train_station": "gare SNTF",
    "train": "gare SNTF",
    "tram_station": "station de tramway",
    "tram": "station de tramway",
    "taxi_station": "station de taxi",
    "taxi": "station de taxi",
    "airport": "aéroport",
    "ferry_terminal": "terminal ferry",
    "cablecar": "téléphérique",
    "metro_station": "station de métro",
    "metro": "station de métro",
}


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


def build_getting_there(poi: dict, station: dict, distance_m: float) -> dict:
    stype = station.get("station_type") or ""
    label = STATION_TYPE_FR.get(stype, stype.replace("_", " "))
    sname = station.get("name") or "station"
    sname = re.sub(r"^(Arrêt|Gare|Station|Terminal)\s+", "", sname, flags=re.IGNORECASE)
    walk_min = round(distance_m / WALKING_M_PER_MIN, 1)
    if distance_m <= MAX_WALK_KM * 1000:
        note = (
            f"Marchez environ {max(1, round(walk_min))} min ({round(distance_m)} m) "
            f"jusqu'à {label} {sname}."
        )
    else:
        km = round(distance_m / 1000, 1)
        note = (
            f"Aucun arrêt de transport en commun à moins de {MAX_WALK_KM:g} km; "
            f"l'arrêt le plus proche ({label} {sname}) est à environ {km} km — "
            f"prévoyez un taxi ou la voiture."
        )
    return {
        "nearest_station": sname,
        "station_type": stype,
        "distance_m": round(distance_m),
        "walking_time_min": walk_min,
        "getting_there_instructions": note,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-walk-km", type=float, default=MAX_WALK_KM)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = await asyncpg.connect(DATABASE_URL)
    pois = await conn.fetch(
        "SELECT id, name, latitude, longitude FROM pois "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
    )
    stations = await conn.fetch(
        "SELECT id, name, station_type, latitude, longitude FROM stations "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
    )
    print(f"pois: {len(pois)}, stations: {len(stations)}", flush=True)

    index = GridIndex([dict(s) for s in stations], GRID_CELL_KM / 111.0)

    enriched = 0
    rows: list[tuple[str, str]] = []
    for p in pois:
        hits = index.nearest(p["latitude"], p["longitude"], 200.0, 1)
        if not hits:
            continue
        d = _haversine_km(p["latitude"], p["longitude"], hits[0]["latitude"], hits[0]["longitude"])
        gt = build_getting_there(dict(p), dict(hits[0]), d * 1000)
        rows.append((str(p["id"]), gt))
        enriched += 1

    print(f"enriched: {enriched}/{len(pois)}", flush=True)
    if args.dry_run:
        await conn.close()
        return

    for i, (poi_id, gt) in enumerate(rows, 1):
        await conn.execute(
            "UPDATE pois SET getting_there = $2::jsonb WHERE id = $1",
            poi_id,
            json.dumps(gt, ensure_ascii=False),
        )
        if i % 1000 == 0:
            print(f"  {i}/{len(rows)}", flush=True)
    n = await conn.fetchval("SELECT count(*) FROM pois WHERE getting_there IS NOT NULL")
    print(f"pois with getting_there: {n}", flush=True)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
