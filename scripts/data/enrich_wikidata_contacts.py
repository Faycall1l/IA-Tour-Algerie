#!/usr/bin/env python3
"""
Wikidata contact enrichment for POIs.

Strategy: Query Wikidata in bulk for all entities of specific types
(museums, national parks, historical sites, etc.) in Algeria, then
match to our POIs by name/category. Much faster than per-POI SPARQL.

Queries:
  1. All museums in Algeria with phone/website/email/opening_hours
  2. All national parks and protected areas
  3. All cultural/historical monuments with contact data
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import psycopg2

DB_DSN = os.getenv("DATABASE_URL", "postgresql://athar:athar_pass@localhost:5432/athar_db")
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

CATEGORY_WD_CLASSES = {
    "museum": "wd:Q33506",        # museum
    "cultural": "wd:Q570116",     # cultural property
    "historical": "wd:Q358",      # historical site
    "park": "wd:Q46169",          # national park
    "natural": "wd:Q46169",       # also national parks
    "religious": "wd:Q179049",    # religious building -> not ideal, too broad
}

TOP_WD_CLASSES = [
    "wd:Q33506",      # museum
    "wd:Q570116",     # cultural property
    "wd:Q358",        # historical site
    "wd:Q46169",      # national park
    "wd:Q41176",      # building
    "wd:Q23413",      # castle/palace
    "wd:Q16560",      # palace
    "wd:Q16970",      # church -> only 4 religious POIs, skip
    "wd:Q34622",      # mosque
]


def sparql_query(query, retries=3):
    params = {"format": "json", "query": query}
    url = f"{SPARQL_ENDPOINT}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"  SPARQL error (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
    return None


def fetch_all_wikidata_entities():
    """Fetch all relevant entities from Wikidata in Algeria."""
    wd_classes = " ".join(TOP_WD_CLASSES)
    query = f"""
    SELECT ?item ?itemLabel ?phone ?website ?email ?openingHours ?facebook ?instagram ?twitter ?instance ?instanceLabel WHERE {{
      VALUES ?type {{ {wd_classes} }}
      ?item wdt:P31/wdt:P279* ?type .
      ?item wdt:P17 wd:Q262 .
      OPTIONAL {{ ?item wdt:P1329 ?phone . }}
      OPTIONAL {{ ?item wdt:P856 ?website . }}
      OPTIONAL {{ ?item wdt:P968 ?email . }}
      OPTIONAL {{ ?item wdt:P6375 ?openingHours . }}
      OPTIONAL {{ ?item wdt:P2013 ?facebook . }}
      OPTIONAL {{ ?item wdt:P2003 ?instagram . }}
      OPTIONAL {{ ?item wdt:P2002 ?twitter . }}
      OPTIONAL {{ ?item wdt:P31 ?instance . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en,ar" . }}
    }}
    LIMIT 10000
    """
    print("Fetching all Wikidata entities in Algeria (museums, sites, parks, etc.)...")
    result = sparql_query(query)
    if not result:
        print("  No results!")
        return []

    bindings = result.get("results", {}).get("bindings", [])
    print(f"  Got {len(bindings)} entities from Wikidata")

    # Deduplicate by item URI, keeping entry with most fields
    seen = {}
    for b in bindings:
        uri = b["item"]["value"]
        if uri not in seen:
            seen[uri] = b
        else:
            existing = seen[uri]
            existing_fields = sum(1 for k in ("phone", "website", "email", "openingHours") if k in existing)
            new_fields = sum(1 for k in ("phone", "website", "email", "openingHours") if k in b)
            if new_fields > existing_fields:
                seen[uri] = b

    return list(seen.values())


def normalize_phone(phone):
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    return cleaned[:20] if len(cleaned) >= 8 else None


def normalize_url(url):
    url = url.strip()
    if url.startswith(("http://", "https://")):
        return url[:300]
    if "." in url:
        return f"https://{url}"[:300]
    return None


def build_label_index(entities):
    """Build search index: lowercase label -> list of entities."""
    index = {}
    for e in entities:
        label = e.get("itemLabel", {}).get("value", "").lower().strip()
        if not label:
            continue
        index.setdefault(label, []).append(e)

        # Also index by alternate names
        alt_label = e.get("itemAltLabel", {}).get("value", "")
        if alt_label:
            for alt in alt_label.split(","):
                alt = alt.strip().lower()
                if alt and len(alt) > 2:
                    index.setdefault(alt, []).append(e)
    return index


def match_pois_to_wikidata(pois, entities, cur):
    """Match POIs to Wikidata entities by name and update contacts."""
    index = build_label_index(entities)
    enriched = 0

    for pid, name, category, lat, lon in pois:
        if not name or len(name) < 3:
            continue

        name_lower = name.lower().strip()
        matches = index.get(name_lower, [])

        if not matches:
            continue

        # Use first match
        m = matches[0]
        enriched += 1
        updates = []
        vals = []

        phone = m.get("phone", {}).get("value")
        if phone:
            p = normalize_phone(phone)
            if p:
                updates.append("phone = COALESCE(NULLIF(phone, ''), %s)")
                vals.append(p)

        website = m.get("website", {}).get("value")
        if website:
            w = normalize_url(website)
            if w:
                updates.append("website = COALESCE(NULLIF(website, ''), %s)")
                vals.append(w)

        email = m.get("email", {}).get("value")
        if email:
            updates.append("email = COALESCE(NULLIF(email, ''), %s)")
            vals.append(str(email)[:200])

        opening_hours = m.get("openingHours", {}).get("value")
        if opening_hours:
            updates.append("opening_hours = COALESCE(NULLIF(opening_hours, ''), %s)")
            vals.append(str(opening_hours)[:200])

        social = {}
        fb = m.get("facebook", {}).get("value")
        if fb:
            social["facebook"] = str(fb)[:300]
        ig = m.get("instagram", {}).get("value")
        if ig:
            social["instagram"] = str(ig)[:300]
        tw = m.get("twitter", {}).get("value")
        if tw:
            social["twitter"] = str(tw)[:300]
        if social:
            updates.append("social_media = social_media || %s::jsonb")
            vals.append(json.dumps(social))

        if updates:
            updates.append("updated_at = NOW()")
            vals.append(str(pid))
            cur.execute(
                f"UPDATE pois SET {', '.join(updates)} WHERE id = %s",
                vals
            )

    return enriched


def main():
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Step 1: Fetch all relevant Wikidata entities in Algeria
    entities = fetch_all_wikidata_entities()
    if not entities:
        print("No Wikidata entities fetched, aborting.")
        conn.close()
        return

    # Step 2: Fetch POIs that are likely to match (named, relevant categories)
    cur.execute("""
        SELECT id, COALESCE(NULLIF(name_en, ''), name) as search_name,
               category, latitude, longitude
        FROM pois
        WHERE name IS NOT NULL AND name != ''
          AND category IN ('museum', 'cultural', 'historical', 'park', 'natural', 'religious')
        ORDER BY id
    """)
    pois = cur.fetchall()
    print(f"Matching {len(pois)} POIs against {len(entities)} Wikidata entities...")

    # Step 3: Match and update
    batch_size = 500
    total_enriched = 0
    for i in range(0, len(pois), batch_size):
        batch = pois[i:i + batch_size]
        enriched = match_pois_to_wikidata(batch, entities, cur)
        conn.commit()
        total_enriched += enriched
        pct = (i + len(batch)) / len(pois) * 100
        print(f"  Batch {i//batch_size + 1}: +{enriched} (processed {(i + len(batch))}, {pct:.0f}%)")

    # Summary
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone != '') AS with_phone,
            COUNT(*) FILTER (WHERE website IS NOT NULL AND website != '') AS with_website,
            COUNT(*) FILTER (WHERE opening_hours IS NOT NULL AND opening_hours != '') AS with_hours,
            COUNT(*) FILTER (WHERE email IS NOT NULL AND email != '') AS with_email
        FROM pois
    """)
    stats = cur.fetchone()
    print(f"\n=== Final Coverage ===")
    print(f"  phone:          {stats[0]}")
    print(f"  website:        {stats[1]}")
    print(f"  opening_hours:  {stats[2]}")
    print(f"  email:          {stats[3]}")
    print(f"  Newly enriched: {total_enriched}")
    print("Done!")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
