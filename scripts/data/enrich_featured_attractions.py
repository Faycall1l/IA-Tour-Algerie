#!/usr/bin/env python3
"""Select top POIs per wilaya based on OSM tags + name quality."""

import psycopg2
import re

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

# Keywords in OSM tags that indicate important sites
IMPORTANT_TAGS = [
    "archaeological_site", "museum", "monument", "castle", "ruins",
    "fort", "tower", "cathedral", "mosque", "church", "temple",
    "palace", "theatre", "amphitheatre", "fountain", "waterfall",
    "cave", "peak", "volcano", "bay", "cape", "lighthouse",
    "garden", "viewpoint", "nature_reserve", "national_park",
    "zoo", "aquarium", "planetarium", "observatory",
    "memorial", "statue", "artwork", "gallery",
    "library", "stadium", "historic",
]

STOP_WORDS = {"non nommé", "unknown", "parking", "toilets", "bench",
              "waste", "recycling", "post box", "telephone"}


def has_proper_name(name):
    """Check if name is a proper place name (not generic/trash)."""
    if not name:
        return False
    name_lower = name.lower()
    for sw in STOP_WORDS:
        if sw in name_lower:
            return False
    # Must have at least 4 chars and contain letters
    if len(name) < 4:
        return False
    if not re.search(r'[a-zA-Z\u0600-\u06FF\u0400-\u04FF]', name):
        return False
    return True


def calc_importance(category, has_description):
    """Score a POI's importance (higher = more important)."""
    cat_scores = {"museum": 100, "natural": 80, "cultural": 70,
                  "historical": 50, "beach": 60, "park": 50, "mountain": 30}
    score = cat_scores.get(category, 10)
    if has_description:
        score += 30
    return score


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Ensure columns exist
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='pois' AND column_name='featured_order'""")
    if not cur.fetchone():
        cur.execute("ALTER TABLE pois ADD COLUMN featured_order INTEGER")
        cur.execute("ALTER TABLE pois ADD COLUMN is_featured BOOLEAN DEFAULT FALSE")
        conn.commit()
        print("Added featured columns\n")

    # Reset existing
    cur.execute("UPDATE pois SET is_featured = FALSE, featured_order = NULL")
    conn.commit()

    # Get all wilayas
    cur.execute("SELECT id, name_fr FROM wilayas ORDER BY id")
    wilayas = cur.fetchall()

    total = 0
    for wid, name_fr in wilayas:
        # Get POIs for this wilaya with proper names
        sql = """SELECT p.id, p.name, p.category,
                   (p.description IS NOT NULL AND p.description != '') as has_desc
            FROM pois p
            WHERE p.wilaya_id = %s
              AND p.name NOT LIKE '%%non nommé%%'
              AND p.name NOT LIKE '%%unknown%%'
              AND LENGTH(p.name) > 4
              AND p.category IN ('museum', 'natural', 'cultural', 'historical', 'beach', 'park')
            ORDER BY
              CASE p.category
                WHEN 'museum' THEN 1 WHEN 'natural' THEN 2 WHEN 'beach' THEN 3
                WHEN 'cultural' THEN 4 WHEN 'park' THEN 5 WHEN 'historical' THEN 6
              END,
              LENGTH(p.name) DESC"""
        cur.execute(sql, (wid,))
        pois = cur.fetchall()

        # Score and rank
        scored = []
        for pid, name, cat, has_desc in pois:
            # Skip if name doesn't look like a real place
            if not has_proper_name(name):
                continue
            score = calc_importance(cat, has_desc)
            scored.append((score, pid, name))

        # Take top 5 per wilaya
        scored.sort(key=lambda x: -x[0])
        for rank, (score, pid, name) in enumerate(scored[:5], 1):
            cur.execute(
                "UPDATE pois SET featured_order = %s, is_featured = TRUE WHERE id = %s",
                (rank, str(pid))
            )
            total += 1

        conn.commit()

        top_names = [s[2][:30] for s in scored[:3]]
        print(f"  [{wid:2d}] {name_fr:25s} {len(scored):3d} candidates → {min(5, len(scored))} featured: {', '.join(top_names)}")

    print(f"\nTotal featured POIs: {total}")

    cur.execute("SELECT COUNT(*) FROM pois WHERE is_featured = TRUE")
    print(f"Verified: {cur.fetchone()[0]}")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
