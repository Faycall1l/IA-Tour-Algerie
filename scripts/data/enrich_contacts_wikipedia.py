#!/usr/bin/env python3
"""Phase B: Extract contact data + Wikipedia descriptions from source JSON.

Extracts phone, website, opening_hours, email from tags dict in
poi_nodes_enriched.json, then fetches Wikipedia descriptions for POIs
that have a wikipedia tag.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

DATA_DIR = "app/data"
WIKIPEDIA_API = "https://fr.wikipedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"

SRC_FIELDS = {
    "phone": None,
    "website": None,
    "opening_hours": None,
    "email": None,
    "contact:phone": "phone",
    "contact:website": "website",
    "contact:email": "email",
    "addr:phone": "phone",
}


def normalize_phone(phone):
    """Normalize phone number: keep digits and + prefix."""
    if not phone:
        return None
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    if len(cleaned) >= 8:
        return cleaned[:20]
    return None


def normalize_website(url):
    """Basic website normalization."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url[:300]
    if "." in url:
        return f"https://{url}"[:300]
    return None


def parse_wikipedia_tag(tag):
    """Parse wikipedia tag like 'fr:Nom de page' into (lang, page)."""
    if not tag:
        return None, None
    tag = tag.strip()
    if ":" in tag:
        parts = tag.split(":", 1)
        return parts[0], parts[1]
    return "fr", tag


def fetch_wikipedia_extract(page_title, lang="fr", retries=3):
    """Fetch Wikipedia page extract/summary."""
    for attempt in range(retries):
        params = {
            "action": "query",
            "titles": page_title,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "exchars": 500,
            "format": "json",
        }
        api_url = f"https://{lang}.wikipedia.org/w/api.php"
        full_url = f"{api_url}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid != "-1" and page.get("extract"):
                    return page["extract"][:500]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((2**attempt) + 0.5)
                continue
            return None
        except Exception:
            return None
    return None


def main():
    print("=== Phase B: Contact Data + Wikipedia Descriptions ===\n")

    # Load source JSON
    src_path = f"{DATA_DIR}/poi_nodes_enriched.json"
    if not os.path.exists(src_path):
        print(f"ERROR: {src_path} not found")
        sys.exit(1)

    with open(src_path) as f:
        source_pois = json.load(f)
    print(f"Loaded {len(source_pois)} POIs from source")

    # Build spatial index for matching (lat, lon) -> node
    index = {}
    for p in source_pois:
        lat, lon = p.get("latitude"), p.get("longitude")
        if lat is not None and lon is not None:
            index[(round(lat, 4), round(lon, 4))] = p

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ── Phase B1: Contact Data Extraction ──
    print("\n--- Phase B1: Contact Data ---")

    cur.execute("SELECT id, latitude, longitude FROM pois")
    db_pois = cur.fetchall()
    print(f"DB POIs: {len(db_pois)}")

    # Ensure social_media column exists
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='pois' AND column_name='social_media'
    """)
    if not cur.fetchone():
        cur.execute("ALTER TABLE pois ADD COLUMN social_media JSONB DEFAULT '{}'::jsonb")
        conn.commit()
        print("  Added social_media column")

    contact_stats = {"phone": 0, "website": 0, "opening_hours": 0, "email": 0, "facebook": 0, "instagram": 0}

    for pid, lat, lon in db_pois:
        if lat is None or lon is None:
            continue

        key = (round(lat, 4), round(lon, 4))
        node = index.get(key)
        if not node:
            continue

        tags = node.get("tags", {}) or {}
        updates = []
        vals = []

        # Extract phone from any phone field
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or tags.get("mobile")
        if phone:
            phone = normalize_phone(phone)
            if phone:
                updates.append("phone = %s")
                vals.append(phone)
                contact_stats["phone"] += 1

        website = tags.get("website") or tags.get("contact:website")
        if website:
            website = normalize_website(website)
            if website:
                updates.append("website = %s")
                vals.append(website)
                contact_stats["website"] += 1

        opening_hours = tags.get("opening_hours")
        if opening_hours:
            updates.append("opening_hours = %s")
            vals.append(str(opening_hours)[:200])
            contact_stats["opening_hours"] += 1

        email = tags.get("email") or tags.get("contact:email")
        if email:
            updates.append("email = %s")
            vals.append(str(email)[:200])
            contact_stats["email"] += 1

        # Social media
        social = {}
        fb = tags.get("contact:facebook")
        if fb:
            social["facebook"] = str(fb)[:300]
            contact_stats["facebook"] += 1
        ig = tags.get("contact:instagram")
        if ig:
            social["instagram"] = str(ig)[:300]
            contact_stats["instagram"] += 1
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

    conn.commit()
    print(f"  phone: {contact_stats['phone']}")
    print(f"  website: {contact_stats['website']}")
    print(f"  opening_hours: {contact_stats['opening_hours']}")
    print(f"  email: {contact_stats['email']}")
    print(f"  facebook: {contact_stats['facebook']}")
    print(f"  instagram: {contact_stats['instagram']}")

    # ── Phase B2: Wikipedia Descriptions ──
    print("\n--- Phase B2: Wikipedia Descriptions ---")

    # First check if description column already has Wikipedia-sourced content
    cur.execute("""
        SELECT COUNT(*) FROM pois
        WHERE description IS NOT NULL AND description != ''
          AND (description LIKE '%[Source:%' OR description LIKE '%Wikipedia%')
    """)
    existing_wiki = cur.fetchone()[0]
    print(f"POIs already with Wikipedia-sourced descriptions: {existing_wiki}")

    # Find POIs with wikipedia tags in source
    wiki_pois = []
    for p in source_pois:
        tags = p.get("tags", {}) or {}
        if tags.get("wikipedia"):
            lat, lon = p.get("latitude"), p.get("longitude")
            if lat is not None and lon is not None:
                wiki_pois.append((p, tags["wikipedia"]))

    print(f"POIs with wikipedia tag: {len(wiki_pois)}")

    wiki_updated = 0
    for p, wiki_tag in wiki_pois:
        lang, page = parse_wikipedia_tag(wiki_tag)
        if not page:
            continue

        # Match to DB by lat/lon
        lat, lon = p.get("latitude"), p.get("longitude")
        key = (round(lat, 4), round(lon, 4))
        node = index.get(key)
        if not node:
            continue

        # Get DB id
        cur.execute(
            "SELECT id, description FROM pois WHERE latitude = %s AND longitude = %s",
            (node["latitude"], node["longitude"])
        )
        db_row = cur.fetchone()
        if not db_row:
            continue

        pid, existing_desc = db_row

        # Skip if already has a non-generic description
        if existing_desc and len(existing_desc) > 30 and "Source:" in existing_desc:
            continue

        print(f"  Fetching Wikipedia: {page} ({lang})...", end=" ", flush=True)
        extract = fetch_wikipedia_extract(page, lang)
        if extract:
            new_desc = f"{extract} [Source: Wikipedia ({lang})]"
            cur.execute(
                "UPDATE pois SET description = %s, updated_at = NOW() WHERE id = %s",
                (new_desc[:500], str(pid))
            )
            conn.commit()
            wiki_updated += 1
            print("✓")
        else:
            print("✗ (no extract)")

        time.sleep(0.5)

    print(f"  Wikipedia descriptions fetched: {wiki_updated}")

    # ── Summary ──
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone != '') AS with_phone,
            COUNT(*) FILTER (WHERE website IS NOT NULL AND website != '') AS with_website,
            COUNT(*) FILTER (WHERE opening_hours IS NOT NULL AND opening_hours != '') AS with_hours,
            COUNT(*) FILTER (WHERE email IS NOT NULL AND email != '') AS with_email
        FROM pois
    """)
    stats = cur.fetchone()

    print(f"\n=== Final Contact Coverage ===")
    print(f"  phone: {stats[0]}")
    print(f"  website: {stats[1]}")
    print(f"  opening_hours: {stats[2]}")
    print(f"  email: {stats[3]}")
    print("\nDone!")

    conn.close()


if __name__ == "__main__":
    main()
