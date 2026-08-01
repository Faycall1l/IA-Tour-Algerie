#!/usr/bin/env python3
"""Wikipedia photo enrichment — direct, fast, targeted.
Runs in small batches, logs everything, 1 request at a time.
"""

import json, re, sys, time, unicodedata, urllib.parse, urllib.request, os

import psycopg2

DB = {"host": "localhost", "port": 5434, "dbname": "athar_db", "user": "athar", "password": "athar_pass"}
UA = "ATHAR-Tourism/1.3"
API_FR = "https://fr.wikipedia.org/w/api.php"
API_EN = "https://en.wikipedia.org/w/api.php"
DELAY = 0.3  # seconds between requests


def norm(s):
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]", "", re.sub(r"\s+", " ", s)).strip()


def search(api, query):
    params = urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": 3, "format": "json", "srprop": "titlesnippet"
    })
    req = urllib.request.Request(f"{api}?{params}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            pages = json.loads(r.read()).get("query", {}).get("search", [])
            return pages[0]["title"] if pages else None
    except Exception as e:
        return None


def page_image(api, title):
    params = urllib.parse.urlencode({
        "action": "query", "titles": title, "prop": "pageimages",
        "pithumbsize": 640, "format": "json"
    })
    req = urllib.request.Request(f"{api}?{params}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            for pid, pd in json.loads(r.read()).get("query", {}).get("pages", {}).items():
                return pd.get("thumbnail", {}).get("source", None)
    except Exception:
        return None


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, name, name_en, name_ar, category
        FROM pois
        WHERE photo_url IS NULL AND name IS NOT NULL AND name != ''
          AND LENGTH(name) > 3
          AND is_featured = true
        ORDER BY featured_order ASC, id ASC
    """)
    rows = cur.fetchall()
    print(f"Featured POIs needing photos: {len(rows)}")
    
    found = 0
    for i, (pid, name, name_en, name_ar, cat) in enumerate(rows):
        sys.stdout.flush()
        queries = [(name, "fr")]
        if name_en and name_en != name:
            queries.append((name_en, "en"))
        if name_ar and name_ar != name and name_ar != name_en:
            queries.append((name_ar, "ar"))
        
        matched = False
        for q, lang in queries:
            api = API_FR if lang == "fr" else API_EN
            title = search(api, q)
            if not title:
                continue
            img = page_image(api, title)
            if img:
                cur.execute(
                    "UPDATE pois SET photo_url = %s, photo_urls = ARRAY[%s], updated_at = NOW() WHERE id = %s AND photo_url IS NULL",
                    (img, img, pid)
                )
                if cur.rowcount:
                    found += 1
                    print(f"  [{i+1}/{len(rows)}] ✓ {name[:40]:40s} → {title[:40]:40s} [{lang}]")
                    matched = True
                break
            time.sleep(DELAY)
        
        if matched:
            conn.commit()
        
        if (i+1) % 10 == 0:
            conn.commit()
            print(f"  ... {i+1}/{len(rows)} processed, {found} found")
    
    conn.commit()
    conn.close()
    print(f"\nDone. Found {found} new photos")


if __name__ == "__main__":
    main()
