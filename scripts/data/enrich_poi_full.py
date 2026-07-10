#!/usr/bin/env python3
"""Extract ALL available OSM fields from poi_nodes_enriched.json into pois table."""

import json
import math
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

DATA_DIR = "app/data"


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def load_poi_index():
    """Build a spatial index of POI nodes from JSON."""
    with open(f"{DATA_DIR}/poi_nodes_enriched.json") as f:
        nodes = json.load(f)
    index = {}
    for n in nodes:
        lat, lon = n.get("latitude"), n.get("longitude")
        if lat is not None and lon is not None:
            index[(round(lat, 4), round(lon, 4))] = n
    return nodes, index


def match_node(lat, lon, index):
    """Find closest POI node within 500m radius."""
    key = (round(lat, 4), round(lon, 4))
    node = index.get(key)
    if node:
        return node, 0

    best_dist = 0.5
    best_node = None
    for nk, nv in index.items():
        d = haversine(lat, lon, nk[0], nk[1])
        if d < best_dist:
            best_dist = d
            best_node = nv
    return best_node, best_dist


def add_columns(cur):
    new_cols = [
        ("subtype", "VARCHAR(100)"),
        ("operator", "VARCHAR(200)"),
        ("has_parking", "BOOLEAN"),
        ("has_accessibility", "BOOLEAN"),
        ("name_ar", "VARCHAR(200)"),
        ("name_en", "VARCHAR(200)"),
        ("osm_node_id", "BIGINT"),
        ("osm_type", "VARCHAR(20)"),
    ]

    cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                   WHERE table_name='pois'""")
    existing = {row[0] for row in cur.fetchall()}

    for col_name, col_type in new_cols:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE pois ADD COLUMN {col_name} {col_type}")

    # Check if cuisine exists
    if "cuisine" not in existing:
        cur.execute("ALTER TABLE pois ADD COLUMN cuisine VARCHAR(200)")


def enrich_pois(conn):
    cur = conn.cursor()

    print("== Adding new columns ==")
    add_columns(cur)
    conn.commit()

    print("\n== Loading POI index ==")
    all_nodes, index = load_poi_index()
    print(f"  JSON nodes: {len(all_nodes)}")

    # Get all DB POIs
    cur.execute("SELECT id, name, latitude, longitude FROM pois")
    db_pois = cur.fetchall()
    print(f"  DB POIs: {len(db_pois)}")

    # Counters
    stats = {
        "subtype": 0, "operator": 0, "parking": 0, "access": 0,
        "name_ar": 0, "name_en": 0, "osm_id": 0, "osm_type": 0,
        "cuisine": 0,
    }

    for pid, name, lat, lon in db_pois:
        if lat is None or lon is None:
            continue

        node, dist = match_node(lat, lon, index)
        if not node:
            continue

        updates, vals = [], []

        # subtype
        if node.get("subtype"):
            updates.append("subtype = %s")
            vals.append(node["subtype"][:100])
            stats["subtype"] += 1

        # operator
        if node.get("operator"):
            updates.append("operator = %s")
            vals.append(str(node["operator"])[:200])
            stats["operator"] += 1

        # has_parking / has_accessibility
        if node.get("has_parking") is not None:
            updates.append("has_parking = %s")
            vals.append(bool(node["has_parking"]))
            stats["parking"] += 1

        if node.get("has_accessibility") is not None:
            updates.append("has_accessibility = %s")
            vals.append(bool(node["has_accessibility"]))
            stats["access"] += 1

        # name_ar / name_en
        if node.get("name_ar"):
            updates.append("name_ar = %s")
            vals.append(node["name_ar"][:200])
            stats["name_ar"] += 1

        if node.get("name_en"):
            updates.append("name_en = %s")
            vals.append(node["name_en"][:200])
            stats["name_en"] += 1

        # osm_node_id / osm_type
        osm = node.get("osm_data", {}) or {}
        if osm.get("osm_id"):
            updates.append("osm_node_id = %s")
            vals.append(osm["osm_id"])
            stats["osm_id"] += 1

        if osm.get("osm_type"):
            updates.append("osm_type = %s")
            vals.append(osm["osm_type"][:20])
            stats["osm_type"] += 1

        # Cuisine from tags
        tags = node.get("tags", {}) or {}
        cuisine = tags.get("cuisine")
        if cuisine and isinstance(cuisine, str):
            updates.append("cuisine = %s")
            vals.append(cuisine[:200])
            stats["cuisine"] += 1

        if updates:
            sql = f"UPDATE pois SET {', '.join(updates)} WHERE id = %s"
            vals.append(str(pid))
            cur.execute(sql, vals)

        if len(db_pois) > 1000 and int(stats["subtype"]) % 5000 == 0 and int(stats["subtype"]) > 0:
            conn.commit()
            print(f"  Progress: {stats['subtype']} subtype updates...")

    conn.commit()

    print("\n== Enrichment Results ==")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def main():
    print("=" * 60)
    print("  POI Full Field Enrichment")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    enrich_pois(conn)
    conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
