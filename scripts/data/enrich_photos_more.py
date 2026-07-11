#!/usr/bin/env python3
"""Bulk photo enrichment: Wikidata SPARQL + Commons API fallback.

Phase 1: SPARQL — get ALL Algerian Wikidata items with Commons images, match
to POIs by FR/EN/AR names (exact + fuzzy). This is ~90% of the work in one call.

Phase 2: Commons API — for remaining featured/prominent named POIs, search
Commons directly with wilaya context.

Phase 3: Wikivoyage — partial name match for remaining.
"""

import json
import os
import re
import sys
import time
import random
import unicodedata
import urllib.parse
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

SPARQL_URL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
MIN_WIDTH = 400
MIN_HEIGHT = 300


def normalize(s):
    """Normalize string for matching: lowercase, strip, remove diacritics."""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_name(name):
    """Remove parenthetical suffixes like '(non nommé)'."""
    return name.split("(")[0].strip()


# ── Phase 1: SPARQL ──

def run_sparql():
    """Fetch all Algerian Wikidata items that have a Commons image."""
    query = """
    SELECT ?item ?itemLabel ?itemAltLabel ?image ?article WHERE {
      ?item wdt:P17 wd:Q262 .
      ?item wdt:P18 ?image .
      OPTIONAL { ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "fr") }
      OPTIONAL { ?item skos:altLabel ?itemAltLabel . FILTER(LANG(?itemAltLabel) = "fr") }
      OPTIONAL {
        ?article schema:about ?item .
        ?article schema:isPartOf [wikibase:wikiGroup "wikipedia"] .
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en,ar" }
    }
    LIMIT 20000
    """
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL_URL, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"SPARQL error: {e}")
        return None


def phase1_sparql(conn, cur):
    """Phase 1: Match POIs to Wikidata images via SPARQL by name."""
    print("\n=== Phase 1: Wikidata SPARQL ===")

    result = run_sparql()
    if not result:
        print("SPARQL failed, skipping Phase 1")
        return

    bindings = result["results"]["bindings"]
    print(f"Got {len(bindings)} Wikidata items with images")

    # Build normalized label → image map (all languages)
    label_image = {}
    for b in bindings:
        image = b["image"]["value"]
        # Also try to get direct Commons URL
        # Convert File:xxx to Special:FilePath
        labels = set()
        for key in ("itemLabel", "itemAltLabel"):
            if key in b:
                for lbl in b[key]["value"].split(","):
                    lbl = lbl.strip()
                    if len(lbl) > 3:
                        labels.add(lbl)

        for lbl in labels:
            norm = normalize(lbl)
            if len(norm) > 3:
                label_image[norm] = image

    print(f"Unique normalized labels: {len(label_image)}")

    # Get all named POIs without photos
    cur.execute("""
        SELECT p.id, p.name, p.name_en, p.name_ar, p.category, p.is_featured
        FROM pois p
        WHERE (p.photo_urls IS NULL OR p.photo_urls = '{}')
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT ILIKE 'unknown%'
          AND LENGTH(TRIM(p.name)) > 3
    """)
    pois = cur.fetchall()
    print(f"POIs to match: {len(pois)}")

    # Phase 1a: exact match
    matched = 0
    updates = []

    for pid, name, name_en, name_ar, category, is_featured in pois:
        names = [n for n in [name, name_en, name_ar] if n and len(n) > 3]
        found = False
        for n in names:
            key = normalize(n)
            url = label_image.get(key)
            if url:
                updates.append((url, str(pid), name))
                matched += 1
                found = True
                break
            # Fuzzy: check if this label is a substring of any Wikidata label
            for wd_label, img in label_image.items():
                if key in wd_label or wd_label in key:
                    updates.append((img, str(pid), name))
                    matched += 1
                    found = True
                    break
            if found:
                break

        if matched % 200 == 0:
            print(f"  Matched {matched}...", end="\r")
            sys.stdout.flush()

    # Batch update
    print(f"\n  Total matched: {matched}")
    for i, (url, pid, name) in enumerate(updates):
        cur.execute(
            "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s AND (photo_urls IS NULL OR photo_urls = '{}')",
            (url, url, pid)
        )
        if i % 500 == 0:
            conn.commit()

    conn.commit()
    print(f"  Updated DB: {len(updates)} POIs")


# ── Phase 2: Commons API ──

def commons_search(query, retries=3):
    """Search Commons for best image matching query."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,
            "srlimit": 3,
            "format": "json",
        }
        url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((2 ** attempt) + random.random() * 2)
                continue
            return None
        except Exception:
            return None

        titles = [r["title"] for r in data.get("query", {}).get("search", [])]
        for title in titles:
            params2 = {
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "format": "json",
            }
            url2 = f"{COMMONS_API}?{urllib.parse.urlencode(params2)}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url2, headers=headers), timeout=20) as resp2:
                    data2 = json.loads(resp2.read())
            except Exception:
                continue

            pages = data2.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid == "-1":
                    continue
                info = page.get("imageinfo", [])
                if info:
                    i = info[0]
                    w, h = i.get("width", 0), i.get("height", 0)
                    if w >= MIN_WIDTH and h >= MIN_HEIGHT:
                        return i["url"]
        return None


def phase2_commons(conn, cur):
    """Phase 2: Commons API for remaining featured/prominent POIs."""
    print("\n=== Phase 2: Commons API ===")

    # Target: museums, beaches, historical, cultural, natural with real names
    cur.execute("""
        SELECT p.id, p.name, p.category, w.name_fr
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE (p.photo_urls IS NULL OR p.photo_urls = '{}')
          AND p.name NOT LIKE '%non nommé%'
          AND p.name NOT ILIKE 'unknown%'
          AND LENGTH(p.name) > 5
          AND p.category IN ('museum', 'beach', 'natural', 'cultural', 'historical')
        ORDER BY p.is_featured DESC, RANDOM()
    """)
    pois = cur.fetchall()
    print(f"Top POIs to photo-find: {len(pois)}")

    found = 0
    total = min(len(pois), 1000)
    for pid, name, category, wilaya in pois[:total]:
        clean = clean_name(name)
        if len(clean) < 5:
            continue
        print(f"  [{found+1}/{total}] {clean[:40]:40s}...", end=" ")
        sys.stdout.flush()

        url = commons_search(f"{clean} {wilaya} Algeria")
        if not url:
            url = commons_search(f"{clean} Algeria")
        if not url:
            url = commons_search(clean)

        if url:
            cur.execute(
                "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s",
                (url, url, str(pid))
            )
            conn.commit()
            found += 1
            print("✓")
        else:
            print("✗")

        time.sleep(1.5 + random.random() * 1.0)

    print(f"\n  Phase 2: {found}/{total} photos found")


def main():
    print("=== Comprehensive Photo Enrichment ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    # Count current state
    cur.execute("""
        SELECT COUNT(*) FROM pois
        WHERE (photo_urls IS NULL OR photo_urls = '{}')
    """)
    before = cur.fetchone()[0]
    print(f"POIs without photos: {before}")

    # Phase 1: SPARQL bulk match
    phase1_sparql(conn, cur)

    # Count after Phase 1
    cur.execute("""
        SELECT COUNT(*) FROM pois
        WHERE (photo_urls IS NULL OR photo_urls = '{}')
    """)
    after_p1 = cur.fetchone()[0]
    print(f"\nAfter Phase 1 — still missing photos: {after_p1}")

    # Phase 2: Commons API for remaining
    phase2_commons(conn, cur)

    # Final count
    cur.execute("""
        SELECT COUNT(*) FROM pois
        WHERE photo_urls IS NOT NULL AND photo_urls != '{}'
    """)
    final_with = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM pois
        WHERE (photo_urls IS NULL OR photo_urls = '{}')
    """)
    final_without = cur.fetchone()[0]

    print(f"\n=== Results ===")
    print(f"With photos: {final_with}")
    print(f"Without photos: {final_without}")
    print(f"Coverage: {final_with / (final_with + final_without) * 100:.1f}%")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
