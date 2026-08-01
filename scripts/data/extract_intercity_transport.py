#!/usr/bin/env python3
"""
Scrape OSM for intercity transport data:
1. Bus stations (amenity=bus_station) — 560 in Algeria
2. Coach routes (type=route, route=coach) — intercity bus lines

Then add missing bus stations to DB as new stations.

Usage: python scripts/data/extract_intercity_transport.py
"""

import json
import math
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import create_engine, text

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "ATHAR-Research/1.0 (tourism-data-collection)"}
ALGERIA_BOX = "(30.0,-2.0,37.5,12.0)"
DB_URL = "postgresql://athar:athar_pass@localhost:5434/athar_db"

WILAYA_CENTERS = {
    1: (27.8743, 0.2933), 2: (33.0833, -0.6333), 3: (36.3667, 2.8333),
    4: (35.8333, 6.1833), 5: (36.1667, 5.4167), 6: (36.7500, 5.0833),
    7: (36.8333, 8.3333), 8: (34.8333, -1.3167), 9: (36.4667, 2.8167),
    10: (36.8333, 7.7667), 11: (32.9167, 3.2500), 12: (35.6000, 6.1667),
    13: (34.8828, -1.3167), 14: (35.4000, 1.3167), 15: (36.7167, 4.0500),
    16: (36.7536, 3.0588), 17: (34.6703, 3.2503), 18: (36.8333, 5.7500),
    19: (36.1833, 5.4167), 20: (35.3833, 7.1500), 21: (36.1667, 6.5667),
    22: (35.6967, -0.6333), 23: (36.9000, 7.7667), 24: (36.2833, 6.6167),
    25: (36.3650, 6.6147), 26: (35.0333, 1.3167), 27: (34.8828, -0.2833),
    28: (35.7167, 4.5500), 29: (35.7500, -0.8000), 30: (31.9500, 5.3333),
    31: (35.6967, -0.6333), 32: (36.7500, 3.0500), 33: (32.8000, 3.0333),
    34: (35.8333, 5.8000), 35: (36.7167, 3.4667), 36: (35.8333, 8.3167),
    37: (32.0833, -1.7833), 38: (35.6000, 1.8000), 39: (33.3500, 6.8333),
    40: (35.5000, 7.1333), 41: (36.7167, 8.3167), 42: (36.3000, 2.3333),
    43: (36.8333, 6.0667), 44: (36.2333, 1.3333), 45: (33.0833, 1.2833),
    46: (31.6167, -2.2167), 47: (32.4833, 3.6667), 48: (33.3833, -0.6333),
    49: (28.2500, 0.2667), 50: (33.1167, -3.6333), 51: (27.2167, 1.9167),
    52: (34.7500, -1.3167), 53: (33.0667, 6.0833), 54: (24.5500, 9.4833),
    55: (32.4833, -0.1500), 56: (34.6833, -1.1333), 57: (35.3833, 1.2833),
    58: (35.3833, 2.1500), 59: (36.3667, 1.3333), 60: (35.5000, 5.3667),
    61: (34.8833, -1.6333), 62: (34.8333, 5.7333), 63: (35.4333, 7.8000),
    64: (35.7333, 4.5500), 65: (32.1167, 5.3167), 66: (35.7500, 3.2167),
    67: (34.7833, 1.7167), 68: (34.0500, 2.0000), 69: (36.5000, 3.0833),
}


def fetch_overpass(query, retries=3):
    for attempt in range(retries):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=90)
            if r.status_code == 200:
                return r.json()
            print(f"  Overpass status {r.status_code}, retry {attempt+1}...")
        except Exception as e:
            print(f"  Overpass error: {e}, retry {attempt+1}...")
        time.sleep(5 * (attempt + 1))
    return {"elements": []}


def assign_wilaya(lat, lon):
    best_w, best_d = None, float("inf")
    for w, (clat, clon) in WILAYA_CENTERS.items():
        d = math.sqrt((lat - clat)**2 + (lon - clon)**2)
        if d < best_d:
            best_d = d
            best_w = w
    return best_w if best_d < 1.5 else None


def main():
    engine = create_engine(DB_URL)

    # 1. Fetch all bus stations from OSM
    print("=== Fetching bus stations from OSM ===")
    q = f'[out:json][timeout:60];node["amenity"="bus_station"]{ALGERIA_BOX};out skel body;'
    data = fetch_overpass(q)
    osm_stations = data.get("elements", [])
    print(f"Found {len(osm_stations)} bus stations in OSM")

    # Get existing station coordinates from DB
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT latitude, longitude FROM stations"))
        existing_coords = {(round(r[0], 4), round(r[1], 4)) for r in existing}
        existing_count = conn.execute(text("SELECT COUNT(*) FROM stations")).scalar()
        print(f"Existing stations in DB: {existing_count}")

    # Find new stations not already in DB
    new_stations = []
    for s in osm_stations:
        lat, lon = s["lat"], s["lon"]
        name = s.get("tags", {}).get("name", "")
        wilaya = assign_wilaya(lat, lon)
        if not wilaya:
            continue
        key = (round(lat, 4), round(lon, 4))
        if key in existing_coords:
            continue
        new_stations.append({
            "osm_id": s["id"],
            "name": name or f"Gare Routière W{wilaya}",
            "lat": lat,
            "lon": lon,
            "wilaya": wilaya,
        })

    print(f"New bus stations to add: {len(new_stations)}")

    # Insert new stations
    if new_stations:
        added = 0
        with engine.connect() as conn:
            for ns in new_stations:
                try:
                    conn.execute(text("""
                        INSERT INTO stations (id, name, type, wilaya_id, latitude, longitude, mode, lines_at_station)
                        VALUES (gen_random_uuid(), :name, 'bus_station', :wilaya, :lat, :lon, 'bus', '[]'::jsonb)
                    """), {"name": ns["name"], "wilaya": ns["wilaya"], "lat": ns["lat"], "lon": ns["lon"]})
                    added += 1
                except Exception as e:
                    print(f"  Skip {ns['name']}: {e}")
            conn.commit()
        print(f"Inserted {added} new bus stations")

    # 2. Fetch coach (intercity bus) routes
    print("\n=== Fetching coach routes ===")
    q2 = f'[out:json][timeout:60];relation["type"="route"]["route"="coach"]{ALGERIA_BOX};out tags;'
    data2 = fetch_overpass(q2)
    routes = data2.get("elements", [])
    print(f"Found {len(routes)} coach routes")

    # Save raw data
    out_dir = Path("app/data/osm_transport")
    out_dir.mkdir(exist_ok=True)

    route_details = []
    for r in routes:
        tags = r.get("tags", {})
        route_details.append({
            "osm_id": r["id"],
            "name": tags.get("name", ""),
            "from": tags.get("from", ""),
            "to": tags.get("to", ""),
            "operator": tags.get("operator", ""),
            "network": tags.get("network", ""),
            "ref": tags.get("ref", ""),
        })

    # Print summary
    operators = {}
    for route in route_details:
        op = route["operator"] or "unknown"
        operators[op] = operators.get(op, 0) + 1
    print(f"\nOperators: {dict(sorted(operators.items(), key=lambda x: -x[1])[:10])}")

    for route in route_details[:20]:
        name = route["name"] or f"{route['from']} → {route['to']}"
        print(f"  {route['osm_id']}: {name[:70]} | op={route['operator']}")

    with open(out_dir / "coach_routes.json", "w") as f:
        json.dump(route_details, f, indent=2, ensure_ascii=False)

    # 3. Summary
    total_stations = existing_count + (len(new_stations) if new_stations else 0)
    print(f"\n=== SUMMARY ===")
    print(f"OSM bus stations found: {len(osm_stations)}")
    print(f"New stations added: {len(new_stations)}")
    print(f"Total stations in DB: ~{total_stations}")
    print(f"Coach routes found: {len(routes)}")
    print(f"Raw data saved to {out_dir}/")

    engine.dispose()


if __name__ == "__main__":
    main()
