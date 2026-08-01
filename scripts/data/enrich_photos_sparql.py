#!/usr/bin/env python3
"""Find Commons photos via French Wikipedia — match POI names to Wikipedia articles."""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

WIKIPEDIA_API = "https://fr.wikipedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"


def api_call(url, params, retries=3):
    headers = {"User-Agent": USER_AGENT}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(full_url, headers=headers), timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((2 ** attempt) * 2)
                continue
            return None
        except Exception:
            return None
    return None


def find_wikipedia_page(title):
    """Search French Wikipedia for a page matching the title, return (page_title, image_url)."""
    data = api_call(WIKIPEDIA_API, {
        "action": "query",
        "list": "search",
        "srsearch": title,
        "srlimit": 5,
        "format": "json",
    })
    if not data:
        return None

    pages = data.get("query", {}).get("search", [])
    for p in pages:
        page_title = p["title"]
        # Get page props including page image
        data2 = api_call(WIKIPEDIA_API, {
            "action": "query",
            "titles": page_title,
            "prop": "pageprops|pageimages",
            "ppprop": "wikibase_item",
            "piprop": "thumbnail",
            "pithumbsize": 800,
            "format": "json",
        })
        if not data2:
            continue
        for pid, page in data2.get("query", {}).get("pages", {}).items():
            if pid == "-1":
                continue
            thumbnail = page.get("thumbnail")
            if thumbnail and thumbnail.get("source"):
                return page_title, thumbnail["source"]

    return None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get promising POIs — named, not yet with photos
    cur.execute("""
        SELECT p.id, p.name, p.wilaya_id, w.name_fr
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_urls IS NULL OR p.photo_urls = '{}')
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT ILIKE 'unknown%'
          AND LENGTH(p.name) > 5
          AND p.category IN ('museum', 'beach', 'natural', 'cultural', 'historical')
        ORDER BY p.is_featured DESC, RANDOM()
        LIMIT 300
    """)
    pois = cur.fetchall()
    print(f"POIs to query: {len(pois)}")

    found = 0
    for pid, name, wid, wilaya in pois:
        clean = name.split("(")[0].strip()
        if len(clean) < 5:
            continue

        # Try with wilaya suffix first, then name alone
        result = find_wikipedia_page(f"{clean} {wilaya}")
        if not result:
            result = find_wikipedia_page(f"{clean} Algérie")
        if not result:
            result = find_wikipedia_page(clean)

        if result:
            page_title, img_url = result
            cur.execute(
                "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s",
                (img_url, img_url, str(pid))
            )
            conn.commit()
            found += 1
            print(f"  ✓ {clean[:40]:40s} → {page_title[:35]}")
        else:
            print(f"  ✗ {clean[:40]}")

        time.sleep(0.5)

    conn.close()
    print(f"\nPhotos found: {found}/{len(pois)}")


if __name__ == "__main__":
    main()
