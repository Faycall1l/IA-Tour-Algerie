#!/usr/bin/env python3
"""Phase A: TripAdvisor-style enrichment from existing data.

Runs all zero-cost internal enrichments:
  A3 — Rankings per (wilaya, category)
  A4 — Suggested duration per category
  A5 — Price level from entry_fee_dzd
  A8 — POI↔Experience linking
  A9 — name_ar / name_en from osm_tags
"""

import os
import sys

import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

DURATION_BY_CATEGORY = {
    "museum": 45,
    "historical": 30,
    "cultural": 90,
    "religious": 45,
    "natural": 45,
    "beach": 120,
    "mountain": 90,
    "park": 90,
    "market": 60,
    "restaurant": 90,
    "cafe": 45,
    "other": 60,
}

PRICE_LEVEL_MAP = {
    "0": "Gratuit",
    "1": "$",
    "2": "$$",
    "3": "$$$",
}

CATEGORY_IMPORTANCE = {
    "museum": 0,
    "historical": 1,
    "natural": 2,
    "cultural": 3,
    "beach": 4,
    "mountain": 5,
    "religious": 6,
    "park": 7,
    "market": 8,
    "restaurant": 9,
    "cafe": 10,
    "other": 11,
}


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ── Schema changes ──
    print("=== Schema: Adding new columns ===")
    schema_sql = [
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS photo_urls TEXT[] DEFAULT '{}'",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS ranking_position INTEGER",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS ranking_total INTEGER",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS suggested_duration_min INTEGER",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS price_level VARCHAR(10)",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS neighborhood VARCHAR(200)",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS award VARCHAR(200)",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS getting_there JSONB",
        "ALTER TABLE pois ADD COLUMN IF NOT EXISTS trip_type_counts JSONB",
    ]
    for sql in schema_sql:
        cur.execute(sql)
    conn.commit()
    print("  Columns added.\n")

    # ── A5: Price level ──
    print("=== A5: Price level ===")
    cur.execute("""
        UPDATE pois SET price_level = CASE
            WHEN entry_fee_dzd IS NULL THEN 'Free'
            WHEN entry_fee_dzd = 0 THEN 'Free'
            WHEN entry_fee_dzd <= 200 THEN '$'
            WHEN entry_fee_dzd <= 1000 THEN '$$'
            ELSE '$$$'
        END
        WHERE price_level IS NULL
    """)
    conn.commit()
    print(f"  Price levels set: {cur.rowcount}\n")

    # ── A4: Suggested duration ──
    print("=== A4: Suggested duration ===")
    for cat, mins in DURATION_BY_CATEGORY.items():
        cur.execute(
            "UPDATE pois SET suggested_duration_min = %s WHERE category = %s AND suggested_duration_min IS NULL",
            (mins, cat)
        )
    conn.commit()
    print(f"  Duration set for all categories.\n")

    # ── A3: Rankings per (wilaya, category) ──
    print("=== A3: Rankings ===")
    # Clear old ranks
    cur.execute("UPDATE pois SET ranking_position = NULL, ranking_total = NULL")
    conn.commit()

    cur.execute("""
        SELECT DISTINCT wilaya_id, category FROM pois
    """)
    groups = cur.fetchall()
    ranked_total = 0
    for wilaya_id, category in groups:
        cur.execute("""
            SELECT id FROM pois
            WHERE wilaya_id = %s AND category = %s
            ORDER BY
                is_featured DESC,
                COALESCE(featured_order, 9999) ASC,
                name ASC
        """, (wilaya_id, category))
        ids = [r[0] for r in cur.fetchall()]
        total = len(ids)
        for pos, pid in enumerate(ids, 1):
            cur.execute(
                "UPDATE pois SET ranking_position = %s, ranking_total = %s WHERE id = %s",
                (pos, total, pid)
            )
        ranked_total += total

    conn.commit()
    print(f"  Ranked {ranked_total} POIs across {len(groups)} wilaya×category groups.\n")

    # ── A9: name_ar / name_en from osm_tags ──
    print("=== A9: Arabic/English names ===")
    cur.execute("""
        UPDATE pois SET
            name_ar = COALESCE(name_ar, osm_tags->>'name:ar'),
            name_en = COALESCE(name_en, osm_tags->>'name:en')
        WHERE osm_tags IS NOT NULL
          AND osm_tags != '{}'
          AND (name_ar IS NULL OR name_en IS NULL)
    """)
    conn.commit()
    print(f"  name_ar/name_en updated: {cur.rowcount}\n")

    # ── A8: POI↔Experience linking ──
    print("=== A8: POI↔Experience links ===")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS poi_experiences (
            poi_id UUID NOT NULL REFERENCES pois(id) ON DELETE CASCADE,
            experience_id UUID NOT NULL REFERENCES experiences(id) ON DELETE CASCADE,
            sort_order INTEGER DEFAULT 0,
            PRIMARY KEY (poi_id, experience_id)
        )
    """)
    conn.commit()
    print("  poi_experiences table created.")

    # Build links by matching title/description keywords
    cur.execute("""
        SELECT e.id, e.title, e.description, e.wilaya_id
        FROM experiences e
        WHERE e.status = 'active'
    """)
    exps = cur.fetchall()

    links = []
    for eid, title, desc, wilaya_id in exps:
        # Extract keywords from title and description
        keywords = set()
        for text in [title, desc or ""]:
            for w in text.lower().split():
                w = w.strip(",.!?;:()[]{}\"'")
                if len(w) > 3:
                    keywords.add(w)

        if not keywords:
            continue

        # Find POIs in same wilaya matching any keyword in name
        for kw in keywords:
            cur.execute(
                "SELECT id FROM pois WHERE wilaya_id = %s AND LOWER(name) LIKE %s LIMIT 1",
                (wilaya_id, f"%{kw}%")
            )
            row = cur.fetchone()
            if row:
                links.append((row[0], eid, len(links)))
                break

    if links:
        execute_values(
            cur,
            "INSERT INTO poi_experiences (poi_id, experience_id, sort_order) VALUES %s ON CONFLICT DO NOTHING",
            links,
        )
        conn.commit()
    print(f"  Created {len(links)} POI↔Experience links.\n")

    # ── Stats ──
    cur.execute("SELECT COUNT(*) FROM pois WHERE ranking_position IS NOT NULL")
    ranked = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pois WHERE price_level IS NOT NULL")
    priced = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pois WHERE suggested_duration_min IS NOT NULL")
    duration = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pois WHERE name_ar IS NOT NULL OR name_en IS NOT NULL")
    names_ext = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM poi_experiences")
    links_count = cur.fetchone()[0]

    print("=== Summary ===")
    print(f"  Ranked:       {ranked}/{ranked_total}")
    print(f"  Price level:  {priced}")
    print(f"  Duration:     {duration}")
    print(f"  Ext. names:   {names_ext}")
    print(f"  Poi↔Exp links: {links_count}")

    conn.close()
    print("\nPhase A done!")


if __name__ == "__main__":
    main()
