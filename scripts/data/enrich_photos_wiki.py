#!/usr/bin/env python3
"""Fast photo enrichment: Wikipedia API search for POI names + page images.

Uses en/fr Wikipedia search + pageimages API — no SPARQL, no Overpass.
Targets featured + highest-ranked POIs first for maximum impact.
"""

import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

WIKIPEDIA_APIS = {
    "en": "https://en.wikipedia.org/w/api.php",
    "fr": "https://fr.wikipedia.org/w/api.php",
    "ar": "https://ar.wikipedia.org/w/api.php",
}
USER_AGENT = "ATHAR-Tourism/1.2 (faycal@athar.dz)"


def normalize(s):
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn


def search_wikipedia(api_url, query, lang):
    """Search Wikipedia for a page matching the query."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 5,
        "format": "json",
        "srprop": "titlesnippet",
    }
    url = f"{api_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            pages = data.get("query", {}).get("search", [])
            if pages:
                return pages[0]["title"]
    except Exception:
        pass
    return None


def get_page_image(api_url, title):
    """Get the main image from a Wikipedia page."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "pithumbsize": 640,
        "format": "json",
    }
    url = f"{api_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if "thumbnail" in page_data:
                    return page_data["thumbnail"]["source"]
                if "pageimage" in page_data:
                    # Build thumbnail URL from pageimage
                    return f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=pageimages&pithumbsize=640&format=json"
    except Exception:
        pass
    return None


def update_poi(cur, poi_id, url, source):
    """Update a single POI with photo URL."""
    if not url:
        return False
    cur.execute(
        "SELECT photo_url FROM pois WHERE id = %s AND photo_url IS NULL",
        (poi_id,)
    )
    if not cur.fetchone():
        return False
    cur.execute(
        "UPDATE pois SET photo_url = %s, photo_urls = ARRAY[%s], updated_at = NOW() WHERE id = %s AND photo_url IS NULL",
        (url, url, poi_id)
    )
    if cur.rowcount:
        return True
    return False


def enrich_batch(start_id=0, limit=500):
    """Process POIs in priority order (featured + historical/cultural first)."""
    conn = get_conn()
    cur = conn.cursor()
    
    # Get prioritized list of POIs needing photos
    cur.execute("""
        SELECT id, name, name_en, name_ar, wilaya_id, category, is_featured, featured_order
        FROM pois
        WHERE photo_url IS NULL 
          AND name IS NOT NULL AND name != ''
          AND LENGTH(name) > 2
          AND category IN ('historical', 'cultural', 'museum', 'natural', 'mountain', 'beach', 'park', 'religious')
        ORDER BY is_featured DESC NULLS LAST, featured_order ASC NULLS LAST, id ASC
        OFFSET %s LIMIT %s
    """, (start_id, limit))
    rows = cur.fetchall()
    
    if not rows:
        print("No more POIs to process")
        return 0
    
    print(f"Processing {len(rows)} POIs (offset {start_id})...")
    
    found = 0
    for row in rows:
        poi_id, name, name_en, name_ar, wilaya_id, category, featured, f_order = row
        
        # Try search on multiple Wikipedia languages
        search_queries = []
        if name_en:
            search_queries.append((name_en, "en"))
        if name_ar:
            search_queries.append((name_ar, "ar"))
        # French is usually best for Algerian topics
        search_queries.insert(0, (name, "fr"))
        if name != name_en and name != name_ar:
            search_queries.append((name, "en"))
        
        matched = False
        for query, lang in search_queries:
            if len(query) < 3:
                continue
            
            api_url = WIKIPEDIA_APIS.get(lang)
            if not api_url:
                continue
            
            # Try exact page match first
            title = search_wikipedia(api_url, query, lang)
            if not title:
                continue
            
            # Get image from the page
            img_url = get_page_image(api_url, title)
            if not img_url:
                # Try French Wikipedia as fallback
                if lang != "fr":
                    title2 = search_wikipedia(WIKIPEDIA_APIS["fr"], query, "fr")
                    if title2:
                        img_url = get_page_image(WIKIPEDIA_APIS["fr"], title2)
            
            if img_url:
                if update_poi(cur, poi_id, img_url, f"Wiki({lang})"):
                    found += 1
                    matched = True
                    tag = "★" if featured else " "
                    print(f"  [{tag}] {name[:40]:40s} → {title[:50]:50s} ({lang})")
                break
            
            time.sleep(0.1)  # rate limit between wikis
        
        if matched:
            time.sleep(0.2)  # rate limit between POIs
    
    conn.close()
    print(f"\nFound {found} photos in this batch")
    return found


def main():
    print("=" * 60)
    print("ATHAR Photo Enrichment — Wikipedia Fast Track")
    print("=" * 60)
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    
    enrich_batch(args.offset, args.limit)


if __name__ == "__main__":
    main()
