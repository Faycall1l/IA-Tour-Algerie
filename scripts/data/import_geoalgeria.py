#!/usr/bin/env python3
"""Download and import @geoalgeria/tourisme data:
- 282 thermal springs from ASAL Geoportail (authoritative gov source)
- 32 parks & reserves
- Cross-reference attractions/historic with existing pois table
"""

import json
import math
import urllib.request
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

CDN = "https://cdn.jsdelivr.net/npm/@geoalgeria/tourisme/data"
USER_AGENT = "ATHAR-Tourism/2.0"


def download(name):
    url = f"{CDN}/{name}.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def wilaya_code_to_id(code):
    """GeoAlgeria uses string codes like '01','02', '67'."""
    return int(code)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def import_thermal_springs(conn):
    print("\n== Thermal Springs ==")
    cur = conn.cursor()

    data = download("thermal-springs")
    print(f"  Downloaded: {len(data)} springs")

    # Ensure thermal_springs table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS thermal_springs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            wilaya_id INTEGER REFERENCES wilayas(id),
            commune_name VARCHAR(200),
            type VARCHAR(50),
            temperature_c DOUBLE PRECISION,
            debit_l_s DOUBLE PRECISION,
            altitude_m DOUBLE PRECISION,
            minerality VARCHAR(200),
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            source VARCHAR(100) DEFAULT 'ASAL geoportail',
            geoalgeria_id INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    conn.commit()

    # Also add to pois table as 'thermal' category
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='pois' AND column_name='thermal_data'
    """)
    if not cur.fetchone():
        cur.execute("ALTER TABLE pois ADD COLUMN thermal_data JSONB")

    conn.commit()

    # Check for existing thermal data to avoid duplicates
    cur.execute("SELECT osm_node_id, name FROM pois WHERE category = 'thermal'")
    existing = {row[1] for row in cur.fetchall()}

    inserted = 0
    for s in data:
        name = s["name"]
        lat = s["lat"]
        lng = s["lng"]
        wid = wilaya_code_to_id(s.get("wilaya_code", "00"))

        # Skip if very similar name exists in pois
        if any(existing_name and name.lower() in existing_name.lower() for existing_name in existing if existing_name):
            continue

        # Insert into thermal_springs table
        cur.execute("""
            INSERT INTO thermal_springs (name, wilaya_id, commune_name, type,
                temperature_c, debit_l_s, altitude_m, minerality,
                latitude, longitude, source, geoalgeria_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            name, wid, s.get("commune_name"), s.get("type"),
            s.get("temperature_c"), s.get("debit_l_s"), s.get("altitude_m"),
            s.get("minerality"), lat, lng,
            s.get("source", "ASAL geoportail"), s.get("id")
        ))
        inserted += 1

        # Also add to pois table as 'thermal' category POI
        thermal_json = json.dumps({
            "temperature_c": s.get("temperature_c"),
            "debit_l_s": s.get("debit_l_s"),
            "altitude_m": s.get("altitude_m"),
            "minerality": s.get("minerality"),
            "source": s.get("source"),
        })

        cur.execute("""
            INSERT INTO pois (id, name, category, wilaya_id, latitude, longitude,
                description, subtype, commune, thermal_data, osm_node_id, osm_type)
            VALUES (gen_random_uuid(), %s, 'other', %s, %s, %s, %s, 'thermal_spring', %s, %s, %s, 'node')
            ON CONFLICT DO NOTHING
        """, (
            name, wid, lat, lng,
            f"Source thermale à {s.get('commune_name', '')} ({s.get('temperature_c', '?')}°C, "
            f"débit: {s.get('debit_l_s', '?')} L/s, minéralité: {s.get('minerality', '?')})"
            if s.get('temperature_c') else f"Source thermale à {s.get('commune_name', '')}",
            s.get("commune_name"), thermal_json,
            -(s.get("id", 0) + 1000000)  # negative OSM ID to avoid collisions
        ))

        conn.commit()

    print(f"  Inserted: {inserted} thermal springs")


def import_parks(conn):
    print("\n== Parks & Reserves ==")
    cur = conn.cursor()

    data = download("parks")
    print(f"  Downloaded: {len(data)} parks")

    inserted = 0
    for p in data:
        name = p.get("name_fr") or p.get("name") or ""
        if not name:
            continue

        lat = p.get("lat")
        lng = p.get("lng")
        if not lat or not lng:
            continue

        wid = wilaya_code_to_id(p.get("wilaya_code", "00"))

        description = ""
        if p.get("category"):
            type_map = {
                "national_park": "Parc national",
                "nature_reserve": "Réserve naturelle",
                "protected_area": "Aire protégée",
            }
            label = type_map.get(p.get("category"), p.get("category"))
            description = f"{label} en Algérie"

        # Check if POI exists nearby
        cur.execute("""
            SELECT id FROM pois
            WHERE wilaya_id = %s AND category = 'park'
              AND ABS(latitude - %s) < 0.01 AND ABS(longitude - %s) < 0.01
        """, (wid, lat, lng))
        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO pois (id, name, category, wilaya_id, latitude, longitude,
                description, subtype)
            VALUES (gen_random_uuid(), %s, 'park', %s, %s, %s, %s, 'national_park')
            ON CONFLICT DO NOTHING
        """, (name, wid, lat, lng, description))
        inserted += 1
        conn.commit()

    print(f"  Inserted: {inserted} parks")


def cross_reference_historic(conn):
    """Cross-reference geoalgeria historic data with our pois to enrich descriptions."""
    print("\n== Historic Cross-Reference ==")
    cur = conn.cursor()

    data = download("historic")
    print(f"  Downloaded: {len(data)} historic sites")

    # Check which ones have Wikidata
    with_wikidata = [h for h in data if h.get("wikidata")]
    print(f"  With Wikidata IDs: {len(with_wikidata)}")

    enriched = 0
    for h in with_wikidata:
        lat = h.get("lat")
        lng = h.get("lng")
        if not lat or not lng:
            continue

        wikidata_id = h["wikidata"]
        name = h.get("name_fr") or h.get("name") or ""

        # Find matching POI by proximity
        cur.execute("""
            SELECT id, name, description FROM pois
            WHERE ABS(latitude - %s) < 0.02 AND ABS(longitude - %s) < 0.02
              AND category IN ('historical', 'cultural', 'museum')
              AND (description IS NULL OR description = '')
        """, (lat, lng))
        match = cur.fetchone()
        if not match:
            continue

        pid, pname, pdesc = match
        if pdesc and len(pdesc) > 20:
            continue

        # Build description
        parts = [name]
        heritage = h.get("heritage_status")
        if heritage:
            parts.append(heritage)
        if h.get("type"):
            parts.append(f"Type: {h['type']}")
        if wikidata_id:
            parts.append(f"Wikidata: {wikidata_id}")

        desc = " — ".join(parts)
        if len(desc) > 10:
            cur.execute("UPDATE pois SET description = %s WHERE id = %s", (desc[:2000], str(pid)))
            enriched += 1
            conn.commit()

    print(f"  Enriched: {enriched} POIs")


def main():
    print("=" * 60)
    print("  GeoAlgeria Tourism Import")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)

    import_thermal_springs(conn)
    import_parks(conn)
    cross_reference_historic(conn)

    conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
