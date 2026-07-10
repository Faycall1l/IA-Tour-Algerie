#!/usr/bin/env python3
"""Fetch Commons photos for POIs by matching against Wikidata's Algerian items.

Uses a single SPARQL query to get all Algerian items with Commons images and
OSM node IDs, then matches to our POIs by osm_node_id.
"""

import os
import sys
import json
import time
import urllib.request
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

SPARQL_URL = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"

SPARQL_QUERY = """
SELECT ?osmNodeId ?image WHERE {
  ?item wdt:P17 wd:Q262 .
  ?item wdt:P18 ?image .
  ?item wdt:P11693 ?osmNodeId .
}
LIMIT 10000
"""


def run_sparql(query):
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    req = urllib.request.Request(SPARQL_URL, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  SPARQL error: {e}")
        return None


def main():
    print("=== Wikidata Photo Enrichment via SPARQL ===\n")

    print("  Querying Wikidata for Algerian items with OSM node IDs and Commons images...")
    result = run_sparql(SPARQL_QUERY)

    if not result or "results" not in result:
        print("  No results from SPARQL query")
        sys.exit(1)

    bindings = result["results"]["bindings"]
    print(f"  Found {len(bindings)} items")

    # Build map: osm_node_id → image_url
    osm_image_map = {}
    for b in bindings:
        try:
            osm_id = int(b["osmNodeId"]["value"])
        except (ValueError, KeyError):
            continue
        image = b["image"]["value"]
        if osm_id not in osm_image_map:
            osm_image_map[osm_id] = image

    print(f"  Unique OSM node IDs with images: {len(osm_image_map)}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Find matching POIs
    cur.execute("""
        SELECT id, osm_node_id, name
        FROM pois
        WHERE (photo_url IS NULL OR photo_url = '')
          AND osm_node_id IS NOT NULL
          AND name NOT LIKE '%non nommé%'
          AND name NOT ILIKE 'unknown%'
    """)
    pois = cur.fetchall()
    print(f"  POIs needing photos: {len(pois)}")

    matched = 0
    for pid, osm_node_id, name in pois:
        if osm_node_id and int(osm_node_id) in osm_image_map:
            url = osm_image_map[int(osm_node_id)]
            cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
            matched += 1
            if matched % 50 == 0:
                conn.commit()
                print(f"    Matched {matched}...", end="\r")
                sys.stdout.flush()

    conn.commit()
    print(f"\n  Photos matched via OSM node ID: {matched}")

    # Retry the remaining via SPARQL for items without OSM node ID but with matching labels
    cur.execute("""
        SELECT COUNT(*) FROM pois
        WHERE (photo_url IS NULL OR photo_url = '')
          AND name NOT LIKE '%non nommé%'
          AND name NOT ILIKE 'unknown%'
    """)
    remaining = cur.scalar()
    print(f"  Remaining without photos: {remaining}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
