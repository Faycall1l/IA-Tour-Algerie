#!/usr/bin/env python3
"""Bulk photo enrichment via Wikidata SPARQL — get all Algerian Wikipedia articles with images.

This makes one SPARQL call to get all ~10K Algerian Wikidata items with Commons images,
then matches them to our POIs by name similarity.
"""

import json
import os
import sys
import urllib.request
import urllib.parse

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"

SPARQL = """
SELECT ?item ?itemLabel ?itemAltLabel ?image ?article WHERE {
  ?item wdt:P17 wd:Q262 .           # country: Algeria
  ?item wdt:P18 ?image .            # has Commons image
  OPTIONAL { ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en") }
  OPTIONAL { ?item skos:altLabel ?itemAltLabel . FILTER(LANG(?itemAltLabel) = "en") }
  OPTIONAL {
    ?article schema:about ?item .
    ?article schema:isPartOf [wikibase:wikiGroup "wikipedia"] .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en,ar" }
}
LIMIT 15000
"""


def run_sparql():
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    data = urllib.parse.urlencode({"query": SPARQL}).encode()
    req = urllib.request.Request(SPARQL_URL, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"SPARQL error: {e}")
        return None


def normalize(s):
    return s.lower().strip().replace("-", " ").replace("'", " ")


def main():
    print("Querying Wikidata for all Algerian items with Commons images...")
    result = run_sparql()
    if not result:
        print("No results.")
        sys.exit(1)

    bindings = result["results"]["bindings"]
    print(f"Got {len(bindings)} Wikidata items with images")

    # Build label→image map
    label_image = {}
    for b in bindings:
        image = b["image"]["value"]
        for key in ["itemLabel", "itemAltLabel"]:
            if key in b:
                labels = b[key]["value"]
                for lbl in labels.split(","):
                    lbl = lbl.strip()
                    if len(lbl) > 3:
                        label_image[normalize(lbl)] = image

    print(f"Unique labels: {len(label_image)}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name FROM pois
        WHERE (photo_urls IS NULL OR photo_urls = '{}')
          AND name NOT LIKE '%non nommé%'
          AND name NOT ILIKE 'unknown%'
          AND LENGTH(name) > 4
    """)
    pois = cur.fetchall()
    print(f"POIs needing photos: {len(pois)}")

    matched = 0
    for pid, name in pois:
        key = normalize(name)
        # Exact match
        url = label_image.get(key)
        if not url:
            # Try partial: check if POI name is a substring of any label
            for lbl, img in label_image.items():
                if key in lbl or lbl in key:
                    url = img
                    break
        if url:
            cur.execute(
                "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) WHERE id = %s",
                (url, url, str(pid))
            )
            matched += 1
            if matched % 50 == 0:
                conn.commit()
                print(f"  Matched {matched}...", end="\r")
                sys.stdout.flush()

    conn.commit()
    print(f"\nMatched: {matched}/{len(pois)}")
    conn.close()


if __name__ == "__main__":
    main()
