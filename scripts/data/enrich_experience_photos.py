#!/usr/bin/env python3
"""Attach real MinIO POI photos to experiences.

Every photo comes from a real, curated POI in the same wilaya:
  1. Preferred: photos of POIs linked via `poi_experiences` (sort_order = match strength)
  2. Fallback: photos of same-category POIs in the same wilaya (featured first)

No synthetic images. Runs on the curated corpus. Idempotent (only fills
experiences whose photos array is empty). Dry-run with --dry-run.
"""

import argparse
import sys

import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

MAX_PHOTOS = 4

# experience category -> ordered list of acceptable POI categories
CATEGORY_MAP = {
    "tour":     ["cultural", "historical", "museum", "natural"],
    "cultural": ["cultural", "historical", "museum", "religious"],
    "food":     ["restaurant", "market", "cafe"],
    "adventure": ["natural", "mountain", "beach"],
    "hiking":   ["natural", "mountain", "park"],
    "wellness": ["park", "natural"],
    "workshop": ["market"],
    "other":    ["cultural", "historical", "natural"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, wilaya_id, category FROM experiences")
    exps = cur.fetchall()
    print(f"{len(exps)} experiences to consider.")

    # ── 1. Linked POI photos (strongest signal, ordered by sort_order) ──
    cur.execute("""
        SELECT pe.experience_id, p.photo_url
        FROM poi_experiences pe
        JOIN pois p ON p.id = pe.poi_id
        WHERE p.photo_url IS NOT NULL
        ORDER BY pe.experience_id, pe.sort_order ASC, p.is_featured DESC
    """)
    linked: dict[str, list[str]] = {}
    for exp_id, url in cur.fetchall():
        linked.setdefault(str(exp_id), []).append(url)

    # ── 2. Fallback: same-wilaya, same-category POI photos ──
    fallback_cache: dict[tuple[int, str], list[str]] = {}

    def fallback_photos(wilaya_id: int, category: str) -> list[str]:
        key = (wilaya_id, category)
        if key in fallback_cache:
            return fallback_cache[key]
        poi_cats = CATEGORY_MAP.get(category, CATEGORY_MAP["other"])
        cur.execute("""
            SELECT photo_url FROM pois
            WHERE wilaya_id = %s
              AND category = ANY(%s)
              AND photo_url IS NOT NULL
            ORDER BY is_featured DESC, COALESCE(featured_order, 9999) ASC, name ASC
            LIMIT %s
        """, (wilaya_id, poi_cats, MAX_PHOTOS))
        urls = [r[0] for r in cur.fetchall()]
        fallback_cache[key] = urls
        return urls

    updates = []
    linked_used = 0
    fallback_used = 0
    unchanged = 0

    for exp_id, wilaya_id, category in exps:
        exp_id = str(exp_id)
        cur.execute("SELECT photos FROM experiences WHERE id = %s", (exp_id,))
        existing = cur.fetchone()[0]
        if existing:
            unchanged += 1
            continue

        photos = linked.get(exp_id, [])[:MAX_PHOTOS]
        if photos:
            linked_used += 1
        else:
            photos = fallback_photos(wilaya_id, category)
            if photos:
                fallback_used += 1

        if photos:
            updates.append((photos, exp_id))

    if args.dry_run:
        print(f"[dry-run] linked: {linked_used}, fallback: {fallback_used}, already-filled: {unchanged}, total updates: {len(updates)}")
        cur.close()
        conn.close()
        return

    if updates:
        execute_values(
            cur,
            "UPDATE experiences SET photos = v.arr, updated_at = now() FROM (VALUES %s) AS v(arr, id) WHERE experiences.id = v.id::uuid",
            updates,
        )
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM experiences WHERE photos IS NOT NULL AND array_length(photos,1) > 0")
    filled = cur.fetchone()[0]
    print(f"linked-source: {linked_used}")
    print(f"fallback-source: {fallback_used}")
    print(f"already-filled: {unchanged}")
    print(f"experiences now with photos: {filled}/{len(exps)}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
