#!/usr/bin/env python3
"""Photo enrichment pass 3: OSM wikidata lookup + broader SPARQL + Wikipedia pageimages.

Strategies (in order):
1. OSM Overpass: fetch wikidata tags for our POIs by osm_node_id, then get P18
2. SPARQL v2: broader name matching across ar, fr, en, ber, kab labels
3. Wikipedia pageimages: for POIs matched to articles in previous passes
"""

import json, os, re, sys, time, random, unicodedata, urllib.parse, urllib.request, urllib.error
from xml.etree import ElementTree

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

OSM_API = "https://overpass-api.de/api/interpreter"
WIKIDATA_API = "https://www.wikidata.org/wiki/Special:EntityData"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "ATHAR-Tourism/1.1 (faycal@athar.dz)"
MIN_WIDTH, MIN_HEIGHT = 300, 200
BATCH_DELAY = 1.0  # seconds between OSM batches
RATE_LIMIT = 1.0   # seconds between Wikidata API calls


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


def get_photo_url(url):
    """Convert a full Wikimedia file URL to a usable thumbnail URL."""
    if not url:
        return None
    # Already a thumbnail or local URL
    if "/thumb/" in url or url.startswith("http://localhost"):
        return url
    # Full file URL → thumbnail URL
    # https://commons.wikimedia.org/wiki/File:SomeImage.jpg
    m = re.search(r"/wiki/File:(.+)", url)
    if m:
        filename = m.group(1)
        # build thumbnail URL
        from urllib.parse import quote
        import hashlib
        # Determine hash prefix
        # Wikimedia stores files at upload.wikimedia.org/wikipedia/commons/{hash_prefix}/{filename}
        # But the direct Commons API URL also works:
        # https://commons.wikimedia.org/wiki/Special:FilePath/{filename}?width=640
        return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=640"
    # Maybe already a direct upload URL
    if "upload.wikimedia.org" in url:
        # Add /thumb/ variant for a specific width
        parts = url.rsplit("/", 1)
        if len(parts) == 2 and not parts[1].endswith(".svg"):
            return parts[0] + "/thumb/" + parts[1] + "/640px-" + parts[1]
        return url
    # Just use it as-is
    return url


def update_poi(conn, cur, id_, url, source):
    """Update a single POI with photo URL, don't overwrite existing."""
    if not url:
        return False
    cur.execute(
        "SELECT photo_url FROM pois WHERE id = %s AND photo_url IS NULL",
        (id_,)
    )
    if not cur.fetchone():
        return False
    thumb_url = get_photo_url(url)
    cur.execute(
        "UPDATE pois SET photo_url = %s, photo_urls = ARRAY[%s], updated_at = NOW() WHERE id = %s AND photo_url IS NULL",
        (thumb_url, thumb_url, id_)
    )
    if cur.rowcount:
        print(f"  ✓ {source}: updated POI {id_}")
        return True
    return False


# ── Phase 1: OSM Overpass → wikidata ID → P18 ──

def fetch_osm_wikidata(osm_ids):
    """Batch-fetch wikidata tags from OSM Overpass for a list of node IDs."""
    if not osm_ids:
        return {}
    # Split into chunks of 100 (Overpass limit is ~500 per query)
    chunks = [osm_ids[i:i+100] for i in range(0, len(osm_ids), 100)]
    result = {}
    for chunk in chunks:
        ids_str = ",".join(str(x) for x in chunk)
        overpass_query = f"""
        [out:json][timeout:60];
        node(id:{ids_str});
        out body;
        """
        payload = urllib.parse.urlencode({"data": overpass_query}).encode()
        req = urllib.request.Request(OSM_API, data=payload, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
                for elem in data.get("elements", []):
                    tags = elem.get("tags", {})
                    if "wikidata" in tags:
                        result[elem["id"]] = tags["wikidata"]
        except Exception as e:
            print(f"  Overpass error: {e}")
        time.sleep(BATCH_DELAY)
    return result


def get_wikidata_image(wikidata_id):
    """Fetch P18 (image) from Wikidata entity."""
    url = f"{WIKIDATA_API}/{wikidata_id}.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            entity = data.get("entities", {}).get(wikidata_id, {})
            claims = entity.get("claims", {})
            p18 = claims.get("P18", [])
            if p18:
                return p18[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
    except Exception as e:
        print(f"  Wikidata API error for {wikidata_id}: {e}")
    return None


def phase1_osm(conn, cur):
    """Phase 1: OSM Overpass → wikidata → P18."""
    print("\n=== Phase 1: OSM wikidata lookup ===")
    
    cur.execute("""
        SELECT id, osm_node_id, name FROM pois
        WHERE osm_node_id IS NOT NULL AND photo_url IS NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} POIs have osm_node_id but no photo")
    
    # Also screen out POIs already tried (store tried OSM IDs in a set)
    tried_file = "/tmp/athar_photo_osm_tried.json"
    already_tried = set()
    if os.path.exists(tried_file):
        with open(tried_file) as f:
            already_tried = set(json.load(f))
    
    osm_to_poi = {}
    for row in rows:
        oid = row[1]
        if oid not in already_tried:
            osm_to_poi[oid] = (row[0], row[2])
    
    print(f"  {len(osm_to_poi)} OSM nodes to look up (others already tried)")
    
    if not osm_to_poi:
        print("  No new OSM nodes to query")
        return 0
    
    # Batch query OSM
    osm_ids = list(osm_to_poi.keys())
    wikidata_map = fetch_osm_wikidata(osm_ids)
    print(f"  Found {len(wikidata_map)} wikidata IDs via Overpass")
    
    # Track tried OSM IDs
    tried = set()
    found = 0
    for oid, wid in wikidata_map.items():
        tried.add(oid)
        if oid not in osm_to_poi:
            continue
        poi_id, name = osm_to_poi[oid]
        
        # Get image from Wikidata
        img_value = get_wikidata_image(wid)
        if img_value:
            # Value from P18 is a string (filename on Commons)
            if isinstance(img_value, str):
                url = f"https://commons.wikimedia.org/wiki/File:{img_value.replace(' ', '_')}"
                if update_poi(conn, cur, poi_id, url, "OSM→WD"):
                    found += 1
        time.sleep(RATE_LIMIT)
    
    # Save tried OSM IDs
    with open(tried_file, "w") as f:
        json.dump(list(already_tried | tried), f)
    
    print(f"  Phase 1: {found} new photos")
    return found


# ── Phase 2: Improved SPARQL ──

def run_sparql_v2():
    """Broader SPARQL: fetch ALL Algerian Wikidata items with images,
    including all label languages for better matching."""
    query = """
    SELECT ?item ?itemLabel ?itemAltLabel ?itemLabelAr ?itemLabelEn ?itemLabelKab ?image ?article WHERE {
      ?item wdt:P17 wd:Q262 .
      ?item wdt:P18 ?image .
      OPTIONAL { ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "fr") }
      OPTIONAL { ?item rdfs:label ?itemLabelAr . FILTER(LANG(?itemLabelAr) = "ar") }
      OPTIONAL { ?item rdfs:label ?itemLabelEn . FILTER(LANG(?itemLabelEn) = "en") }
      OPTIONAL { ?item rdfs:label ?itemLabelKab . FILTER(LANG(?itemLabelKab) = "kab") }
      OPTIONAL { ?item skos:altLabel ?itemAltLabel . FILTER(LANG(?itemAltLabel) = "fr") }
      OPTIONAL {
        ?article schema:about ?item .
        ?article schema:isPartOf [wikibase:wikiGroup "wikipedia"] .
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en,ar,ber,kab" }
    }
    LIMIT 30000
    """
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL_URL, data=data, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            print(f"  SPARQL HTTP {e.code}: will retry with smaller limit")
            # Retry with smaller limit
            query2 = query.replace("LIMIT 30000", "LIMIT 15000")
            data2 = urllib.parse.urlencode({"query": query2}).encode()
            req2 = urllib.request.Request(SPARQL_URL, data=data2, headers=headers)
            try:
                with urllib.request.urlopen(req2, timeout=300) as r2:
                    return json.loads(r2.read())
            except Exception as e2:
                print(f"  SPARQL retry also failed: {e2}")
                return None
        except Exception as e:
            print(f"  SPARQL error (attempt {attempt + 1}/4): {e}")
            time.sleep(10 * (attempt + 1))
    return None


def phase2_sparql(conn, cur):
    """Phase 2: Broader SPARQL matching with more languages and fuzzy matching."""
    print("\n=== Phase 2: Improved SPARQL ===")
    
    result = run_sparql_v2()
    if not result:
        print("  SPARQL failed, skipping Phase 2")
        return 0
    
    bindings = result["results"]["bindings"]
    print(f"  Got {len(bindings)} Wikidata items with images")
    
    # Build label → image map (all languages, including alt labels)
    label_image = {}
    article_map = {}
    for b in bindings:
        image = b.get("image", {}).get("value", "")
        item = b.get("item", {}).get("value", "")
        article = b.get("article", {}).get("value", "") if "article" in b else None
        
        for key in ["itemLabel", "itemLabelAr", "itemLabelEn", "itemLabelKab", "itemAltLabel"]:
            if key in b:
                label = b[key].get("value", "").strip()
                if label and len(label) > 1:
                    nkey = normalize(label)
                    if nkey not in label_image:
                        label_image[nkey] = (image, item, label)
        
        # Also add the raw item label from rdfs:label
        if "itemLabel" in b:
            raw = b["itemLabel"].get("value", "")
            if raw:
                nkey = normalize(raw)
                if nkey not in label_image:
                    label_image[nkey] = (image, item, raw)
        
        if article and item:
            article_map[item] = article
    
    print(f"  Built {len(label_image)} normalized labels")
    
    # Fetch POIs needing photos
    cur.execute("""
        SELECT id, name, name_ar, name_en, wilaya_id FROM pois
        WHERE photo_url IS NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} POIs still need photos")
    
    found = 0
    for row in rows:
        poi_id, name, name_ar, name_en, wilaya_id = row
        if not name:
            continue
        
        # Try matching on all available names
        names_to_try = [name]
        if name_ar:
            names_to_try.append(name_ar)
        if name_en:
            names_to_try.append(name_en)
        
        matched = False
        for n in names_to_try:
            nkey = normalize(n)
            if nkey in label_image:
                img_url, item, matched_label = label_image[nkey]
                # Build Commons URL
                if "commons.wikimedia.org" not in img_url:
                    filename = img_url.split("/")[-1] if "/" in img_url else img_url
                    if "." in filename:  # has extension
                        img_url = f"https://commons.wikimedia.org/wiki/File:{filename}"
                    else:
                        continue  # not a file URL
                
                if update_poi(conn, cur, poi_id, img_url, "SPARQLv2"):
                    found += 1
                    matched = True
                break
        
        # Progress logging
        if found > 0 and found % 100 == 0:
            print(f"  ... {found} matched so far")
    
    print(f"  Phase 2: {found} new photos")
    return found


# ── Phase 3: Wikipedia pageimages for matched articles ──

def phase3_wikipedia(conn, cur):
    """Phase 3: For POIs that have Wikipedia articles (from earlier passes), get page images."""
    print("\n=== Phase 3: Wikipedia pageimages ===")
    
    # Get POIs that have name matches with Wikipedia articles from previous SPARQL
    # Re-run SPARQL to get article→item mapping for items that have images
    result = run_sparql_v2()
    if not result:
        print("  SPARQL failed, skipping Phase 3")
        return 0
    
    bindings = result["results"]["bindings"]
    
    # Build article URL → item ID mapping for items WITH images
    article_item = {}
    for b in bindings:
        if "article" in b and "item" in b:
            article = b["article"]["value"]
            item = b["item"]["value"]
            if "image" in b:
                article_item[article] = item
    
    # Get unique Wikipedia articles
    articles = list(set(article_item.keys()))
    print(f"  {len(articles)} unique Wikipedia articles with Commons images")
    
    # Fetch POIs needing photos with names
    cur.execute("""
        SELECT id, name FROM pois
        WHERE photo_url IS NULL AND name IS NOT NULL AND name != ''
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} POIs still need photos")
    
    # For each POI, try matching article title to POI name
    # Build article title → POI map using normalized names
    found = 0
    poi_names = {}
    for row in rows:
        nkey = normalize(row[1])
        if nkey not in poi_names:
            poi_names[nkey] = []
        poi_names[nkey].append(row[0])
    
    for article_url in articles:
        # Extract title from URL
        # e.g. https://en.wikipedia.org/wiki/Monts_du_Hoggar
        title = article_url.split("/")[-1].replace("_", " ")
        if not title:
            continue
        nkey = normalize(title)
        
        if nkey in poi_names:
            item_id = article_item[article_url]
            # Get the image from Wikidata for this item
            img_value = get_wikidata_image(item_id.split("/")[-1])
            if img_value:
                url = f"https://commons.wikimedia.org/wiki/File:{img_value.replace(' ', '_')}"
                for poi_id in poi_names[nkey][:1]:  # first match only
                    if update_poi(conn, cur, poi_id, url, "WikiPI"):
                        found += 1
            time.sleep(RATE_LIMIT)
        
        if found > 0 and found % 50 == 0:
            print(f"  ... {found} from Wikipedia pageimages")
    
    print(f"  Phase 3: {found} new photos")
    return found


# ── Main ──

def main():
    print("=" * 60)
    print("ATHAR Photo Enrichment — Phase 3")
    print("=" * 60)
    
    conn = get_conn()
    cur = conn.cursor()
    
    total = 0
    total += phase1_osm(conn, cur)
    total += phase2_sparql(conn, cur)
    total += phase3_wikipedia(conn, cur)
    
    conn.close()
    
    print("\n" + "=" * 60)
    print(f"Total new photos: {total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
