#!/usr/bin/env python3
"""Assign wilaya to transit nodes missing wilaya_name via nearest-center + name matching."""

import json
import math
import re
import sys
from pathlib import Path

import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "athar_db",
    "user": "athar",
    "password": "athar_pass",
}

DATA_DIR = Path("app/data")

# Name → wilaya name_fr mapping (from OSM tags / common names)
CITY_TO_WILAYA = {
    "adrar": "Adrar",
    "chlef": "Chlef",
    "laghouat": "Laghouat",
    "oum el bouaghi": "Oum El Bouaghi",
    "batna": "Batna",
    "bejaia": "Béjaïa",
    "biskra": "Biskra",
    "bechar": "Béchar",
    "blida": "Blida",
    "bouira": "Bouira",
    "tamanrasset": "Tamanrasset",
    "tebessa": "Tébessa",
    "tlemcen": "Tlemcen",
    "tiaret": "Tiaret",
    "tizi ouzou": "Tizi Ouzou",
    "alger": "Alger",
    "djelfa": "Djelfa",
    "jijel": "Jijel",
    "setif": "Sétif",
    "saida": "Saïda",
    "skikda": "Skikda",
    "sidi bel abbes": "Sidi Bel Abbès",
    "annaba": "Annaba",
    "guelma": "Guelma",
    "constantine": "Constantine",
    "medea": "Médéa",
    "mostaganem": "Mostaganem",
    "msila": "M'Sila",
    "mascara": "Mascara",
    "ouargla": "Ouargla",
    "oran": "Oran",
    "el bayadh": "El Bayadh",
    "illizi": "Illizi",
    "bordj bou arreridj": "Bordj Bou Arreridj",
    "boumerdes": "Boumerdès",
    "el tarf": "El Tarf",
    "tindouf": "Tindouf",
    "tissemsilt": "Tissemsilt",
    "el oued": "El Oued",
    "khenchela": "Khenchela",
    "souk ahras": "Souk Ahras",
    "tipaza": "Tipaza",
    "mila": "Mila",
    "ain defla": "Aïn Defla",
    "naama": "Naâma",
    "ain temouchent": "Aïn Témouchent",
    "ghardaia": "Ghardaïa",
    "relizane": "Relizane",
    "timimoun": "Timimoun",
    "bordj badji mokhtar": "Bordj Badji Mokhtar",
    "ouled djellal": "Ouled Djellal",
    "beni abbes": "Béni Abbès",
    "ain salah": "Aïn Salah",
    "ain guezzam": "Aïn Guezzam",
    "touggourt": "Touggourt",
    "djanet": "Djanet",
    "el meghaier": "El Meghaier",
    "el meniaa": "El Meniaa",
    "inzize": "In Salah",
    "ouled slimane": "Ouled Slimane",
    "sidi bennour": "Sidi Bennour",
}

# Extra city name hints (lowercase)
CITY_HINTS = {k: v for k, v in CITY_TO_WILAYA.items()}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def extract_city(name):
    """Try to match city name from node name."""
    if not name:
        return None
    name_lower = name.lower()
    # Direct match
    for city, wilaya in CITY_HINTS.items():
        if city in name_lower:
            return wilaya
    # Try extracting last word(s)
    words = name_lower.split()
    for w in words:
        if w in CITY_HINTS:
            return CITY_HINTS[w]
    return None

def main():
    print("=== Fix Missing Wilaya for Transit Nodes ===\n")

    # Load nodes
    with open(DATA_DIR / "transit_nodes_enriched.json") as f:
        nodes = json.load(f)

    # Find missing
    missing = []
    for n in nodes:
        wn = n.get("wilaya_name")
        if not wn or wn == "unknown":
            lat = n.get("latitude")
            lon = n.get("longitude")
            if lat and lon and 18 <= lat <= 38 and -9 <= lon <= 12:
                missing.append(n)

    print(f"Nodes missing wilaya (inside Algeria): {len(missing)}")

    if not missing:
        print("Nothing to fix!")
        return

    # Load wilayas from DB
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT id, name_fr, latitude, longitude FROM wilayas ORDER BY id")
    wilayas = [{"id": r[0], "name_fr": r[1], "lat": r[2], "lon": r[3]} for r in cur.fetchall()]
    conn.close()
    print(f"Wilaya reference centers: {len(wilayas)}")

    fixed = 0
    city_fixed = 0
    nearest_fixed = 0
    for n in missing:
        name = n.get("name", "")
        lat = n["latitude"]
        lon = n["longitude"]

        # 1. Try city name matching
        city_name = extract_city(name)
        matched = None
        if city_name:
            for w in wilayas:
                if w["name_fr"].lower() == city_name.lower():
                    matched = w
                    break

        # 2. Fall back to nearest center
        if not matched:
            nearest = min(wilayas, key=lambda w: haversine(lat, lon, w["lat"], w["lon"]))
            dist = haversine(lat, lon, nearest["lat"], nearest["lon"])
            # Only assign if within reasonable distance (200km from center)
            if dist <= 200:
                matched = nearest
                nearest_fixed += 1
            else:
                # Too far from any wilaya center — skip (probably not in Algeria)
                continue
        else:
            city_fixed += 1

        n["wilaya_id"] = matched["id"]
        n["wilaya_name"] = matched["name_fr"]
        fixed += 1

    print(f"\nFixed by city name : {city_fixed}")
    print(f"Fixed by nearest   : {nearest_fixed}")
    print(f"Total fixed        : {fixed}")

    # Also check if any still missing
    still_missing = [n for n in nodes if not n.get("wilaya_name") or n["wilaya_name"] == "unknown"]
    print(f"Still missing      : {len(still_missing)}")

    # Save updated nodes
    with open(DATA_DIR / "transit_nodes_enriched.json", "w") as f:
        json.dump(nodes, f, ensure_ascii=False)
    print(f"\nSaved {len(nodes)} nodes to transit_nodes_enriched.json")

    # Also update POI nodes file
    poi_path = DATA_DIR / "poi_nodes_enriched.json"
    if poi_path.exists():
        with open(poi_path) as f:
            pois = json.load(f)
        poi_fixed = 0
        for p in pois:
            if not p.get("wilaya_name") or p["wilaya_name"] == "unknown":
                lat = p.get("latitude")
                lon = p.get("longitude")
                if lat and lon and 18 <= lat <= 38 and -9 <= lon <= 12:
                    name = p.get("name", "")
                    city_name = extract_city(name)
                    matched = None
                    if city_name:
                        for w in wilayas:
                            if w["name_fr"].lower() == city_name.lower():
                                matched = w
                                break
                    if not matched:
                        nearest = min(wilayas, key=lambda w: haversine(lat, lon, w["lat"], w["lon"]))
                        dist = haversine(lat, lon, nearest["lat"], nearest["lon"])
                        if dist <= 200:
                            matched = nearest
                    if matched:
                        p["wilaya_id"] = matched["id"]
                        p["wilaya_name"] = matched["name_fr"]
                        poi_fixed += 1
        with open(poi_path, "w") as f:
            json.dump(pois, f, ensure_ascii=False)
        print(f"POI nodes: {poi_fixed} fixed")

    # Update DB stations table
    print("\nUpdating DB stations table...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    db_fixed = 0
    for n in missing:
        if n.get("wilaya_id"):
            cur.execute(
                "UPDATE stations SET wilaya_id = %s WHERE name = %s AND wilaya_id IS DISTINCT FROM %s",
                (n["wilaya_id"], n.get("name", ""), n["wilaya_id"]),
            )
            if cur.rowcount > 0:
                db_fixed += cur.rowcount
    conn.commit()
    conn.close()
    print(f"DB stations updated: {db_fixed}")

    print("\nDone!")

if __name__ == "__main__":
    main()
