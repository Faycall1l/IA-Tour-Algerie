#!/usr/bin/env python3
"""Fetch Wikimedia Commons photos for top POIs and store URLs in DB."""

import json
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


def commons_api(params, retries=3):
    """Call Commons API with retry on 429."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = (2 ** attempt) + random.random() * 3
                print(f"    429, waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            return None
        except Exception:
            return None
    return None


def find_photo(query):
    """Find best photo for a query on Commons."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": 3,
        "srwhat": "text",
        "format": "json",
    }
    data = commons_api(params)
    if not data:
        return None
    titles = [r["title"] for r in data.get("query", {}).get("search", [])]
    for title in titles:
        # Get URL
        params2 = {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|size",
            "format": "json",
        }
        data2 = commons_api(params2)
        if not data2:
            continue
        pages = data2.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid != "-1":
                info = page.get("imageinfo", [])
                if info:
                    i = info[0]
                    if i.get("width", 0) >= MIN_WIDTH and i.get("height", 0) >= MIN_HEIGHT:
                        return i["url"]
    return None


def main():
    print("=== Wikimedia Commons Photo Enrichment ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Phase 1: Museums (highest priority - they have real names)
    print("--- Phase 1: Museums ---")
    cur.execute("""
        SELECT p.id, p.name, p.category, p.wilaya_id, w.name_fr
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_url IS NULL OR p.photo_url = '')
          AND p.category = 'museum'
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT LIKE '%unknown%'
        ORDER BY RANDOM()
    """)
    pois = cur.fetchall()
    print(f"Museums to enrich: {len(pois)}")

    success = 0
    total = len(pois)
    for i, (pid, name, category, wid, wilaya) in enumerate(pois, 1):
        clean = name.split("(")[0].strip()
        if len(clean) < 5:
            continue
        print(f"  [{i}/{total}] {clean[:50]}...", end=" ")
        url = find_photo(clean)
        if url:
            cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
            conn.commit()
            success += 1
            print(f"✓")
        else:
            # Try with wilaya name
            url = find_photo(f"{clean} {wilaya}")
            if url:
                cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
                conn.commit()
                success += 1
                print(f"✓ (w/ wilaya)")
            else:
                print(f"✗")
        time.sleep(2.0 + random.random() * 1.0)

    print(f"  Museums with photos: {success}/{total}\n")

    # Phase 2: Natural landmarks and beaches (visually striking)
    print("--- Phase 2: Natural & Beaches ---")
    cur.execute("""
        SELECT p.id, p.name, p.category, p.wilaya_id, w.name_fr
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_url IS NULL OR p.photo_url = '')
          AND p.category IN ('natural', 'beach')
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT LIKE '%unknown%'
          AND LENGTH(p.name) > 3
        ORDER BY RANDOM()
        LIMIT 200
    """)
    pois = cur.fetchall()
    print(f"Natural/beach to enrich: {len(pois)}")
    s2 = 0
    for i, (pid, name, category, wid, wilaya) in enumerate(pois, 1):
        clean = name.split("(")[0].strip()
        if len(clean) < 5:
            continue
        print(f"  [{i}/{len(pois)}] {clean[:50]}...", end=" ")
        url = find_photo(f"{clean} Algeria")
        if not url:
            url = find_photo(clean)
        if url:
            cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
            conn.commit()
            s2 += 1
            print(f"✓")
        else:
            print(f"✗")
        time.sleep(2.0 + random.random())

    success += s2
    print(f"  Natural/beach with photos: {s2}/{len(pois)}\n")

    # Phase 3: Cultural POIs with real names
    print("--- Phase 3: Cultural Sites ---")
    cur.execute("""
        SELECT p.id, p.name, p.category, p.wilaya_id, w.name_fr
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_url IS NULL OR p.photo_url = '')
          AND p.category = 'cultural'
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT LIKE '%unknown%'
          AND p.description IS NOT NULL
          AND LENGTH(p.name) > 5
        ORDER BY RANDOM()
        LIMIT 200
    """)
    pois = cur.fetchall()
    print(f"Cultural to enrich: {len(pois)}")
    s3 = 0
    for i, (pid, name, category, wid, wilaya) in enumerate(pois, 1):
        clean = name.split("(")[0].strip()
        if len(clean) < 5:
            continue
        print(f"  [{i}/{len(pois)}] {clean[:50]}...", end=" ")
        url = find_photo(f"{clean} Algeria")
        if not url:
            url = find_photo(clean)
        if url:
            cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
            conn.commit()
            s3 += 1
            print(f"✓")
        else:
            print(f"✗")
        time.sleep(2.0 + random.random())

    success += s3
    print(f"  Cultural with photos: {s3}/{len(pois)}\n")

    # Phase 4: Historical POIs (top ones with real names)
    print("--- Phase 4: Historical Sites (sample) ---")
    cur.execute("""
        SELECT p.id, p.name, p.category, p.wilaya_id, w.name_fr
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_url IS NULL OR p.photo_url = '')
          AND p.category = 'historical'
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT LIKE '%unknown%'
          AND LENGTH(p.name) > 8
        ORDER BY RANDOM()
        LIMIT 200
    """)
    pois = cur.fetchall()
    print(f"Historical to enrich: {len(pois)}")
    s4 = 0
    for i, (pid, name, category, wid, wilaya) in enumerate(pois, 1):
        clean = name.split("(")[0].strip()
        if len(clean) < 5:
            continue
        print(f"  [{i}/{len(pois)}] {clean[:50]}...", end=" ")
        url = find_photo(f"{clean} Algeria")
        if not url:
            url = find_photo(clean)
        if url:
            cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
            conn.commit()
            s4 += 1
            print(f"✓")
        else:
            print(f"✗")
        time.sleep(2.0 + random.random())

    success += s4
    print(f"  Historical with photos: {s4}/{len(pois)}\n")

    conn.close()
    print(f"Total photos added: {success}")


if __name__ == "__main__":
    main()
