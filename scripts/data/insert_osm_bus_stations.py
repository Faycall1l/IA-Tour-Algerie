#!/usr/bin/env python3
"""Insert OSM bus stations into DB with correct schema."""
import json
import math
from pathlib import Path
from sqlalchemy import create_engine, text

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
    
    # Load existing coordinates
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT latitude, longitude FROM stations"))
        existing_coords = {(round(r[0], 4), round(r[1], 4)) for r in existing}
    
    # Load scraped OSM bus stations
    osm_file = Path("app/data/osm_transport/bus_stations.json")
    if not osm_file.exists():
        print("No bus_stations.json found, re-fetching from OSM...")
        import requests, time
        HEADERS = {"User-Agent": "ATHAR-Research/1.0 (tourism-data-collection)"}
        q = '[out:json][timeout:60];node["amenity"="bus_station"](30.0,-2.0,37.5,12.0);out skel body;'
        r = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, headers=HEADERS, timeout=90)
        osm_stations = r.json()["elements"]
        with open(osm_file, "w") as f:
            json.dump(osm_stations, f)
    else:
        with open(osm_file) as f:
            osm_stations = json.load(f)
    
    print(f"OSM bus stations: {len(osm_stations)}")
    print(f"Existing DB coords: {len(existing_coords)}")
    
    added = 0
    skipped = 0
    for s in osm_stations:
        lat, lon = s["lat"], s["lon"]
        name = s.get("tags", {}).get("name", "")
        wilaya = assign_wilaya(lat, lon)
        if not wilaya:
            skipped += 1
            continue
        key = (round(lat, 4), round(lon, 4))
        if key in existing_coords:
            skipped += 1
            continue
        
        # Insert with correct schema
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    INSERT INTO stations (id, name, station_type, wilaya_id, latitude, longitude, operator, is_active)
                    VALUES (gen_random_uuid(), :name, 'bus', :wilaya, :lat, :lon, 'OSM', true)
                """), {"name": name or f"Gare Routiere W{wilaya}", "wilaya": wilaya, "lat": lat, "lon": lon})
                conn.commit()
                existing_coords.add(key)
                added += 1
            except Exception as e:
                conn.rollback()
                skipped += 1
                if added == 0:
                    print(f"  First error: {e}")
    
    print(f"\nAdded: {added}")
    print(f"Skipped: {skipped}")
    
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM stations")).scalar()
        by_type = conn.execute(text("SELECT station_type, COUNT(*) FROM stations GROUP BY station_type ORDER BY COUNT(*) DESC"))
        print(f"\nTotal stations: {total}")
        for row in by_type:
            print(f"  {row[0]:20s}: {row[1]}")
    
    engine.dispose()


if __name__ == "__main__":
    main()
