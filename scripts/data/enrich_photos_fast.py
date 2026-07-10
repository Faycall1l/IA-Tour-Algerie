#!/usr/bin/env python3
"""Fast batch photo enrichment — searches Commons for top POIs and adds URLs.

Matches by (name, wilaya, category) using the Commons search API in small batches.
"""

import json
import os
import sys
import time
import random
import urllib.request
import urllib.parse
import urllib.error

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
MIN_WIDTH = 400
MIN_HEIGHT = 300


def api_call(params):
    headers = {"User-Agent": USER_AGENT}
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((2 ** attempt) * 2 + random.random() * 2)
                continue
            return None
        except Exception:
            return None
    return None


def fetch_image_urls(titles):
    """Given list of Commons file titles, return {title: url} for valid images."""
    url_map = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        data = api_call({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|size",
            "format": "json",
        })
        if not data:
            continue
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1":
                continue
            info = page.get("imageinfo", [])
            if info and info[0].get("width", 0) >= MIN_WIDTH and info[0].get("height", 0) >= MIN_HEIGHT:
                url_map[page["title"]] = info[0]["url"]
    return url_map


def search_commons(query, limit=3):
    """Search Commons for a query, return list of file titles."""
    data = api_call({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": limit,
        "srwhat": "text",
        "format": "json",
    })
    if not data:
        return []
    return [r["title"] for r in data.get("query", {}).get("search", [])]


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    total_added = 0

    # Priority 1: featured POIs (most visible)
    for label, where, limit in [
        ("Featured POIs", "AND p.is_featured = TRUE", None),
        ("Museums", "AND p.category = 'museum' AND LENGTH(p.name) > 5", 80),
        ("Beaches", "AND p.category = 'beach' AND LENGTH(p.name) > 4", 50),
        ("Natural sites", "AND p.category = 'natural' AND LENGTH(p.name) > 5", 150),
        ("Cultural sites", "AND p.category = 'cultural' AND LENGTH(p.name) > 5", 200),
        ("Historical (short)", "AND p.category = 'historical' AND LENGTH(p.name) BETWEEN 8 AND 30", 300),
    ]:
        print(f"\n--- {label} ---")
        limit_sql = f"LIMIT {limit}" if limit else ""
        cur.execute(f"""
            SELECT p.id, p.name, p.wilaya_id, w.name_fr
            FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
            WHERE (p.photo_urls IS NULL OR p.photo_urls = '{{}}')
              AND p.name NOT LIKE '%%non nommé%%'
              {where}
            ORDER BY p.is_featured DESC, p.featured_order ASC, RANDOM()
            {limit_sql}
        """)
        pois = cur.fetchall()
        if not pois:
            print("  None needing photos.")
            continue
        print(f"  Processing {len(pois)} POIs...")

        updated = 0
        for pid, name, wid, wilaya in pois:
            clean = name.split("(")[0].strip()
            if len(clean) < 5:
                continue

            # Try queries in order of specificity
            found_url = None
            for query in [
                f"{clean} {wilaya}",
                f"{clean} Algeria",
                clean,
            ]:
                titles = search_commons(query)
                if titles:
                    urls = fetch_image_urls(titles)
                    for t, u in urls.items():
                        found_url = u
                        break
                if found_url:
                    break

            if found_url:
                cur.execute(
                    "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s",
                    (found_url, found_url, str(pid))
                )
                updated += 1
                if updated % 10 == 0:
                    conn.commit()

            time.sleep(0.6 + random.random() * 0.4)

        conn.commit()
        total_added += updated
        print(f"  Added: {updated}/{len(pois)}")

    conn.close()
    print(f"\n=== Total photos added: {total_added} ===")


if __name__ == "__main__":
    main()
