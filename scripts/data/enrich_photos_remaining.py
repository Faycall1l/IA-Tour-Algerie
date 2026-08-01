#!/usr/bin/env python3
"""Targeted photo enrichment for the last ~650 named high-value POIs.

Strategy: for each remaining named POI in historical/cultural/museum/etc
categories, try:
  1. Direct Wikipedia page search (title match → page image)
  2. Commons category search with POI name + wilaya
  3. Commons file search with exact name
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
MIN_DIM = 300

# Names that we know won't have Commons images
SKIP_PATTERNS = (
    "ancienne piste", "pk ", "pont", "ruin", "monument aux",
    "entrée", "carrefour", "marché", "centre commercial",
    "sidi ", "mosquée ", "stèle", "borne", "fontaine",
)


def api_request(api_url, params, retries=3):
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        url = f"{api_url}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
            else:
                return None


def clean_name(name):
    name = name.split("(")[0].strip()
    name = re.sub(r"[_,]", " ", name)
    return name.strip()


def search_commons_direct(query):
    """Search Commons files directly by title."""
    params = {
        "action": "query",
        "list": "allimages",
        "aiprefix": query[:80],
        "ailimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|size",
        "format": "json",
    }
    data = api_request(COMMONS_API, params)
    if not data:
        return None
    images = data.get("query", {}).get("allimages", [])
    for img in images:
        url = img.get("url", "")
        w, h = img.get("width", 0), img.get("height", 0)
        if url and (w >= MIN_DIM or h >= MIN_DIM):
            return url
    return None


def search_commons_category(query):
    """Search Commons by category for the query."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": 5,
        "format": "json",
    }
    data = api_request(COMMONS_API, params)
    if not data:
        return None
    titles = [r["title"] for r in data.get("query", {}).get("search", []) if "title" in r]
    for title in titles:
        params2 = {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|size",
            "format": "json",
        }
        data2 = api_request(COMMONS_API, params2)
        if not data2:
            continue
        pages = data2.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1":
                continue
            info = page.get("imageinfo", [])
            if info:
                i = info[0]
                url = i.get("url", "")
                w, h = i.get("width", 0), i.get("height", 0)
                if url and (w >= MIN_DIM or h >= MIN_DIM):
                    return url
    return None


def search_wikipedia_page(name, wilaya):
    """Search Wikipedia for a page matching the POI name, get its main image."""
    # Try English Wikipedia first
    for lang, api in [("en", WIKIPEDIA_API), ("fr", "https://fr.wikipedia.org/w/api.php"), ("ar", "https://ar.wikipedia.org/w/api.php")]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f"{name} {wilaya} Algeria",
            "srlimit": 3,
            "format": "json",
        }
        data = api_request(api, params)
        if not data:
            continue
        pages = data.get("query", {}).get("search", [])
        if not pages:
            continue
        # Get page image
        title = pages[0]["title"]
        params2 = {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "pithumbsize": 800,
            "format": "json",
        }
        data2 = api_request(api, params2)
        if not data2:
            continue
        pages2 = data2.get("query", {}).get("pages", {})
        for pid, page in pages2.items():
            if pid == "-1":
                continue
            thumb = page.get("thumbnail", {})
            source = page.get("pageimage", "")
            if thumb:
                return thumb.get("source") or thumb.get("url")
            if source:
                # Get direct Commons URL
                return search_commons_direct(f"File:{source}")
    return None


def main():
    print("=== Targeted Photo Enrichment (Remaining Named POIs) ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.name, p.category, w.name_fr
        FROM pois p
        JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_urls IS NULL OR p.photo_urls = '{}')
          AND LENGTH(TRIM(p.name)) > 5
          AND p.name NOT ILIKE '%non nommé%'
          AND p.name NOT ILIKE 'unknown%'
          AND p.category IN ('historical', 'cultural', 'natural', 'museum', 'beach', 'park')
        ORDER BY p.is_featured DESC, RANDOM()
    """)
    pois = cur.fetchall()
    print(f"Targeted POIs: {len(pois)}")

    found = 0
    skipped = 0
    for i, (pid, name, category, wilaya) in enumerate(pois):
        clean = clean_name(name)
        if len(clean) < 5:
            continue
        if any(p in clean.lower() for p in SKIP_PATTERNS):
            skipped += 1
            continue

        progress = f"[{i+1}/{len(pois)}]"
        print(f"  {progress} {clean[:45]:45s}...", end=" ")
        sys.stdout.flush()

        url = None

        # Strategy 1: Wikipedia page → page image
        url = search_wikipedia_page(clean, wilaya)

        # Strategy 2: Commons category search
        if not url:
            url = search_commons_category(f"{clean} {wilaya} Algeria")

        # Strategy 3: Direct Commons file search
        if not url:
            url = search_commons_direct(clean)

        if url:
            cur.execute(
                "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s AND (photo_urls IS NULL OR photo_urls = '{}')",
                (url, url, str(pid))
            )
            conn.commit()
            found += 1
            print("✓")
        else:
            print("✗")

        # Rate limit
        time.sleep(0.8)

    print(f"\n=== Results ===")
    print(f"Found: {found}, Skipped: {skipped}")

    cur.execute("SELECT COUNT(*) FROM pois WHERE photo_urls IS NOT NULL AND photo_urls != '{}'")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pois")
    all_p = cur.fetchone()[0]
    print(f"Total with photos: {total:,} ({total/all_p*100:.1f}%)")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
