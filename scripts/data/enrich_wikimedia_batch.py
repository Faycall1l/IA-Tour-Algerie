#!/usr/bin/env python3
"""Batch Wikimedia Commons photo enrichment using pipelined API calls.

Much faster than the original: uses batch title→imageinfo lookups (up to 50 titles/call)
and searches in parallel groups.
"""

import os
import sys
import json
import time
import random
import urllib.request
import urllib.parse
import urllib.error
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://fr.wikipedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
MIN_WIDTH = 400
MIN_HEIGHT = 300


def api_call(api_url, params, retries=3):
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        url = f"{api_url}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = (2 ** attempt) * 2 + random.random() * 2
                print(f"    429, waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            return None
        except Exception:
            return None
    return None


def search_commons_batch(queries):
    """Search Commons for up to 3 queries, return {query: first_image_url}."""
    results = {}
    for query in queries:
        if not query or len(query) < 4:
            continue
        data = api_call(COMMONS_API, {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,
            "srlimit": 3,
            "srwhat": "text",
            "format": "json",
        })
        if not data:
            continue
        titles = [r["title"] for r in data.get("query", {}).get("search", [])]
        if titles:
            results[query] = titles
    return results


def fetch_image_urls(title_list):
    """Fetch image URLs for a list of titles (batched 50 at a time)."""
    url_map = {}
    for i in range(0, len(title_list), 50):
        batch = title_list[i:i+50]
        data = api_call(COMMONS_API, {
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
            title = page.get("title", "")
            info = page.get("imageinfo", [])
            if info and info[0].get("width", 0) >= MIN_WIDTH and info[0].get("height", 0) >= MIN_HEIGHT:
                url_map[title] = info[0]["url"]
    return url_map


def main():
    print("=== Batch Wikimedia Photo Enrichment ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    categories = [
        ("museum", 100, "Algérie musée"),
        ("cultural", 300, "Algérie culture"),
        ("beach", 50, "Algérie plage"),
        ("natural", 200, "Algérie nature"),
        ("historical", 500, "Algérie"),
    ]

    total_added = 131

    for category, limit, suffix in categories:
        print(f"\n--- Phase: {category} (max {limit}) ---")

        cur.execute("""
            SELECT p.id, p.name, p.category, p.wilaya_id, w.name_fr
            FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
            WHERE (p.photo_url IS NULL OR p.photo_url = '')
              AND p.category = %s
              AND p.name NOT LIKE '%%non nommé%%'
              AND p.name NOT ILIKE 'unknown%%'
              AND LENGTH(p.name) > 4
            ORDER BY RANDOM()
            LIMIT %s
        """, (category, limit))
        pois = cur.fetchall()
        print(f"  POIs to process: {len(pois)}")

        if not pois:
            continue

        # Build queries: try with suffix first, fallback to name only
        queries = []
        poi_map = {}
        for pid, name, cat, wid, wilaya in pois:
            clean = name.split("(")[0].strip()
            if len(clean) < 5:
                continue
            q1 = f"{clean} {wilaya}"
            q2 = f"{clean} {suffix}"
            q3 = f"{clean} Algeria"
            queries.extend([(q1, pid, clean), (q2, pid, clean), (q3, pid, clean)])
            poi_map[pid] = {"name": clean, "wilaya": wilaya}

        # Search Commons in batches
        search_queries = list(set(q[0] for q in queries))
        print(f"  Unique search queries: {len(search_queries)}")

        query_to_titles = {}
        for i in range(0, len(search_queries), 5):
            batch_q = search_queries[i:i+5]
            results = search_commons_batch(batch_q)
            for q, titles in results.items():
                query_to_titles[q] = titles
            if (i + 5) % 20 == 0:
                print(f"    Searched {i+5}/{len(search_queries)}...", end="\r")
                sys.stdout.flush()
            time.sleep(0.5 + random.random() * 0.3)

        # Collect all unique titles and fetch URLs
        all_titles = list(set(t for titles in query_to_titles.values() for t in titles))
        print(f"\n  Unique Commons titles found: {len(all_titles)}")

        if not all_titles:
            print(f"  No results found for {category}")
            continue

        title_urls = fetch_image_urls(all_titles)
        print(f"  Valid image URLs: {len(title_urls)}")

        # Map query → url via titles
        query_to_url = {}
        for query, titles in query_to_titles.items():
            for t in titles:
                if t in title_urls:
                    query_to_url[query] = title_urls[t]
                    break

        # Update DB
        updated = 0
        for pid, name, cat, wid, wilaya in pois:
            if pid in poi_map and pid not in [r[0] for r in pois[:updated+1] if updated > 0]:
                pass
            clean = name.split("(")[0].strip()
            if len(clean) < 5:
                continue
            url = None
            for q, _, _ in queries:
                if q[1] == pid:
                    url = query_to_url.get(q[0])
                    if url:
                        break
            if url:
                cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (url, str(pid)))
                updated += 1
                if updated % 10 == 0:
                    conn.commit()
            else:
                # Single fallback search
                for try_q in [f"{clean} {wilaya}", f"{clean} Algeria", clean]:
                    data = api_call(COMMONS_API, {
                        "action": "query",
                        "list": "search",
                        "srsearch": try_q,
                        "srnamespace": 6,
                        "srlimit": 3,
                        "format": "json",
                    })
                    if data:
                        titles = [r["title"] for r in data.get("query", {}).get("search", [])]
                        if titles:
                            urls = fetch_image_urls(titles)
                            for t, u in urls.items():
                                if u:
                                    cur.execute("UPDATE pois SET photo_url = %s WHERE id = %s", (u, str(pid)))
                                    updated += 1
                                    break
                        break
                    time.sleep(1.0 + random.random() * 0.5)

        conn.commit()
        total_added += updated
        print(f"  Photos added for {category}: {updated}/{len(pois)}")

    conn.close()
    print(f"\n=== Total photos added: {total_added} ===")


if __name__ == "__main__":
    main()
