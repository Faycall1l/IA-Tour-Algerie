#!/usr/bin/env python3
"""Compute accessibility score for every POI: nearest station, distance, modes nearby.

Stores results in the `getting_there` JSONB column on `pois`.
"""

import json
import math
from collections import defaultdict

import psycopg2
import psycopg2.extras

DB_CONFIG = {'host': 'localhost', 'port': 5434, 'dbname': 'athar_db', 'user': 'athar', 'password': 'athar_pass'}

# Category importance weights (for ranking)
CATEGORY_WEIGHT = {
    "museum": 100, "cultural": 90, "historical": 85, "natural": 80,
    "beach": 75, "park": 70, "mountain": 65, "market": 60,
    "religious": 55, "restaurant": 50, "cafe": 40, "other": 30,
}

WALK_SPEED_KMH = 5.0


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * 6371 * math.asin(min(1, math.sqrt(a)))


def accessibility_score(dist_km: float, modes_nearby: int) -> int:
    if dist_km < 0.1:
        base = 100
    elif dist_km < 0.3:
        base = 80
    elif dist_km < 0.5:
        base = 60
    elif dist_km < 1.0:
        base = 40
    elif dist_km < 2.0:
        base = 20
    else:
        base = 5
    # Mode bonus
    if modes_nearby >= 3:
        base = min(100, base + 20)
    elif modes_nearby == 2:
        base = min(100, base + 10)
    return base


def combined_score(is_featured: bool, category: str, accessibility: int) -> float:
    cat_w = CATEGORY_WEIGHT.get(category, 30)
    featured_bonus = 100 if is_featured else 0
    return accessibility * 0.4 + cat_w * 0.3 + featured_bonus * 0.3


def build_grid(stations: list[dict], cell_size: float = 0.08):
    """Assign stations to a spatial grid."""
    grid = defaultdict(list)
    for s in stations:
        cx = int(s['longitude'] / cell_size)
        cy = int(s['latitude'] / cell_size)
        grid[(cx, cy)].append(s)
    return grid, cell_size


def expanding_cells(cx, cy, max_radius: int = 6):
    """Yield (cx, cy) starting from center and expanding outward up to max_radius."""
    yield (cx, cy)
    for r in range(1, max_radius + 1):
        for dx in range(-r, r + 1):
            yield (cx + dx, cy + r)
            yield (cx + dx, cy - r)
        for dy in range(-r + 1, r):
            yield (cx + r, cy + dy)
            yield (cx - r, cy + dy)


def compute_accessibility(pois: list[dict], stations: list[dict]) -> dict[int, dict]:
    """For each POI, find nearest station(s) and compute accessibility."""
    grid, cell_size = build_grid(stations)

    results = {}
    for poi in pois:
        pid = poi['id']
        plat, plon = poi['latitude'], poi['longitude']
        cx = int(plon / cell_size)
        cy = int(plat / cell_size)

        best_dist = float('inf')
        best_station = None
        modes_nearby = set()
        lines_nearby = set()
        found = False

        for ncx, ncy in expanding_cells(cx, cy, max_radius=6):
            cell_stations = grid.get((ncx, ncy), [])
            if not cell_stations:
                if found:
                    continue
                continue
            for s in cell_stations:
                d = haversine_km(plat, plon, s['latitude'], s['longitude'])
                if d < best_dist:
                    best_dist = d
                    best_station = s
                    found = True
                if d < 0.5:
                    modes_nearby.add(s['station_type'])
                    for line in s.get('lines', []):
                        lines_nearby.add(line.get('line_id'))

        walk_min = round((best_dist / WALK_SPEED_KMH) * 60) if best_dist < float('inf') else None
        access_score = accessibility_score(best_dist, len(modes_nearby))

        results[pid] = {
            "nearest_station_id": str(best_station['id']) if best_station else None,
            "nearest_station_name": best_station['name'] if best_station else None,
            "nearest_station_type": best_station['station_type'] if best_station else None,
            "distance_km": round(best_dist, 3) if best_dist < float('inf') else None,
            "walking_time_min": walk_min,
            "accessibility_score": access_score,
            "modes_nearby": sorted(modes_nearby) if modes_nearby else None,
            "lines_nearby_count": len(lines_nearby),
        }

    return results


def main():
    # Load stations from DB (with line info)
    print("Loading stations...", flush=True)
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT s.id, s.name, s.latitude, s.longitude, s.station_type,
               COALESCE(jsonb_agg(
                   jsonb_build_object('line_id', tl.id, 'line_name', tl.name, 'mode', tl.mode)
               ) FILTER (WHERE tl.id IS NOT NULL), '[]') as lines
        FROM stations s
        LEFT JOIN line_stops ls ON ls.station_id = s.id
        LEFT JOIN transport_lines tl ON tl.id = ls.line_id
        GROUP BY s.id
    """)
    stations_raw = cur.fetchall()

    stations = [
        {
            'id': r[0],
            'name': r[1],
            'latitude': r[2],
            'longitude': r[3],
            'station_type': r[4],
            'lines': r[5],
        }
        for r in stations_raw
    ]
    print(f"  {len(stations)} stations loaded", flush=True)

    # Load POIs
    print("Loading POIs...", flush=True)
    cur.execute("""
        SELECT id, latitude, longitude, category, is_featured, wilaya_id
        FROM pois
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)
    pois_raw = cur.fetchall()
    pois_by_id = {}
    for r in pois_raw:
        pois_by_id[r[0]] = {
            'id': r[0],
            'latitude': r[1],
            'longitude': r[2],
            'category': r[3],
            'is_featured': r[4],
            'wilaya_id': r[5],
        }
    pois = list(pois_by_id.values())
    print(f"  {len(pois)} POIs loaded", flush=True)

    # Compute accessibility
    print("Computing accessibility...", flush=True)
    results = compute_accessibility(pois, stations)
    print(f"  Computed for {len(results)} POIs", flush=True)

    # Update DB in batches
    print("Updating DB...", flush=True)
    cur2 = conn.cursor()
    count = 0
    rows = []
    for pid, data in results.items():
        poi_data = pois_by_id[pid]
        combined = combined_score(
            poi_data['is_featured'],
            poi_data['category'],
            data['accessibility_score'],
        )
        getting_there = {
            **data,
            "combined_score": round(combined, 1),
        }
        rows.append((str(pid), json.dumps(getting_there)))
        count += 1

    # Use a single large batch update via temp table
    cur2.execute("CREATE TEMP TABLE tmp_poi_access (id UUID, getting_there JSONB) ON COMMIT DROP")
    psycopg2.extras.execute_values(cur2, "INSERT INTO tmp_poi_access (id, getting_there) VALUES %s", rows, template="(%s, %s::jsonb)")
    cur2.execute("""
        UPDATE pois p
        SET getting_there = t.getting_there
        FROM tmp_poi_access t
        WHERE p.id = t.id
    """)
    conn.commit()
    print(f"  Updated {count} POIs total", flush=True)
    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
