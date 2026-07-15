#!/usr/bin/env python3
"""Spatial photo enrichment: match POIs to Wikidata items by proximity.

Fetches ALL Algerian Wikidata items that have BOTH a Commons image (P18)
AND coordinates (P625), then for each photo-less POI finds the nearest
Wikidata item within a radius. This catches photos for unnamed POIs
and where OSM/Wikidata names differ.
"""

import json
import math
import sys
import time
import urllib.parse
import urllib.request

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
MAX_DISTANCE_M = 500  # max meters for a match


def haversine(lat1, lon1, lat2, lon2):
    """Haversine distance in meters between two lat/lon points."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def run_sparql():
    """Fetch all Algerian Wikidata items with P18 (image) AND P625 (coordinates)."""
    query = """
    SELECT ?item ?itemLabel ?image ?lat ?lon ?article WHERE {
      ?item wdt:P17 wd:Q262 .
      ?item wdt:P18 ?image .
      ?item wdt:P625 ?coords .
      ?item p:P625 ?coordsNode .
      ?coordsNode psv:P625 ?coordsValue .
      ?coordsValue wikibase:geoLatitude ?lat .
      ?coordsValue wikibase:geoLongitude ?lon .
      OPTIONAL { ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "fr") }
      OPTIONAL {
        ?article schema:about ?item .
        ?article schema:isPartOf [wikibase:wikiGroup "wikipedia"] .
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en,ar" }
    }
    LIMIT 100000
    """
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL_URL, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"SPARQL error: {e}")
        return None


def main():
    print("=== Spatial Photo Enrichment ===\n")

    # ── Step 1: Fetch all POIs without photos ──
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, latitude, longitude, name
        FROM pois
        WHERE (photo_urls IS NULL OR photo_urls = '{}')
          AND latitude IS NOT NULL AND longitude IS NOT NULL
    """)
    pois = cur.fetchall()
    print(f"POIs needing photos: {len(pois)}")

    if not pois:
        print("No POIs need photos!")
        conn.close()
        return

    # ── Step 2: Fetch Wikidata items with images + coordinates ──
    print("\nQuerying Wikidata for Algerian items with images + coordinates...")
    result = run_sparql()
    if not result or "results" not in result:
        print("SPARQL failed, aborting")
        conn.close()
        return

    bindings = result["results"]["bindings"]
    print(f"Got {len(bindings)} Wikidata items with images + coordinates")

    # Build spatial index (grid-based, ~0.1° cells)
    wd_items = []
    for b in bindings:
        try:
            lat = float(b["lat"]["value"])
            lon = float(b["lon"]["value"])
            image = b["image"]["value"]
            label = b.get("itemLabel", {}).get("value", "")
            wd_items.append((lat, lon, image, label))
        except (KeyError, ValueError):
            continue

    print(f"Parsed {len(wd_items)} Wikidata items")

    # Build grid index: grid_cell -> list of (lat, lon, image, label)
    GRID_SIZE = 0.1  # degrees (~11km)
    grid = {}
    for lat, lon, img, label in wd_items:
        cell = (round(lat / GRID_SIZE), round(lon / GRID_SIZE))
        grid.setdefault(cell, []).append((lat, lon, img, label))

    print(f"Grid cells: {len(grid)}")

    def find_nearest(poi_lat, poi_lon):
        """Find nearest Wikidata image within MAX_DISTANCE_M."""
        cell = (round(poi_lat / GRID_SIZE), round(poi_lon / GRID_SIZE))
        candidates = []
        # Check neighboring cells
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                nc = (cell[0] + di, cell[1] + dj)
                candidates.extend(grid.get(nc, []))

        best_dist = float("inf")
        best_img = None
        for lat, lon, img, _ in candidates:
            d = haversine(poi_lat, poi_lon, lat, lon)
            if d < best_dist:
                best_dist = d
                best_img = img

        if best_dist <= MAX_DISTANCE_M:
            return best_img, best_dist
        return None, None

    # ── Step 3: Match ──
    matched = 0
    updates = []

    for i, (pid, lat, lon, name) in enumerate(pois):
        img, dist = find_nearest(lat, lon)
        if img:
            updates.append((img, str(pid)))
            matched += 1
        if (i + 1) % 5000 == 0:
            print(f"  Processed {i+1}/{len(pois)}, matched {matched}...")

    print(f"\nTotal matches: {matched}")

    # ── Step 4: Batch update DB ──
    print("Updating database...")
    batch_size = 500
    for i in range(0, len(updates), batch_size):
        batch = updates[i : i + batch_size]
        for img, pid in batch:
            cur.execute(
                "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s AND (photo_urls IS NULL OR photo_urls = '{}')",
                (img, img, pid)
            )
        conn.commit()
        print(f"  Updated {min(i + batch_size, len(updates))}/{len(updates)}")

    # ── Final count ──
    cur.execute("SELECT COUNT(*) FROM pois WHERE photo_urls IS NOT NULL AND photo_urls != '{}'")
    with_photos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pois WHERE photo_urls IS NULL OR photo_urls = '{}'")
    without_photos = cur.fetchone()[0]
    total = with_photos + without_photos

    print(f"\n=== Results ===")
    print(f"POIs with photos:    {with_photos:>6,} ({with_photos/total*100:.1f}%)")
    print(f"POIs without photos: {without_photos:>6,} ({without_photos/total*100:.1f}%)")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
