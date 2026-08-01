#!/usr/bin/env python3
"""Category-walk photo enrichment: recursively walk Wikimedia Commons categories.

For each root category (top-level Algeria themes + all 58 wilayas/provinces),
recursively collect subcategories (max depth 3) and all geotagged files,
then spatially match remaining photo-less POIs (300m radius).

Strategy: Commons file pages expose GPS coordinates via the `coordinates`
prop; most category files are geotagged only in leaf/place-specific
categories (e.g. "Mosques in Algiers"), which top-level fetches miss.
"""

import json
import math
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
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
MAX_DISTANCE_M = 300
GRID_SIZE = 0.2
MAX_DEPTH = 3
MAX_CATEGORIES = 700
SLEEP = 1.0

ROOTS = [
    "Algeria", "History of Algeria", "Archaeological sites in Algeria",
    "Roman sites in Algeria", "Mosques in Algeria", "Museums in Algeria",
    "National parks of Algeria", "Beaches of Algeria", "Mountains of Algeria",
    "Mountain ranges of Algeria", "Lakes of Algeria", "Rivers of Algeria",
    "Waterfalls in Algeria", "Caves of Algeria", "Oases of Algeria",
    "Forests of Algeria", "Gardens in Algeria", "Bridges in Algeria",
    "Lighthouses in Algeria", "Forts in Algeria", "Palaces in Algeria",
    "Kasbahs in Algeria", "Medinas in Algeria", "World Heritage Sites in Algeria",
    "Cultural heritage of Algeria", "Natural heritage of Algeria",
    "Landscapes of Algeria", "Coastal views in Algeria", "Deserts of Algeria",
    "Saharan views in Algeria", "Hotels in Algeria", "Markets in Algeria",
    "Monuments and memorials in Algeria", "Cemeteries in Algeria",
    "Churches in Algeria", "Synagogues in Algeria", "Water towers in Algeria",
    "Fountains in Algeria", "Hammams in Algeria", "Tunnels in Algeria",
    "Dams in Algeria", "Archaeological artifacts in Algeria", "Rock art in Algeria",
    "Tassili n'Ajjer", "Hoggar Mountains", "Atlas Mountains in Algeria",
    "Tell Atlas", "Saharan Atlas", "Aures Mountains", "Djurdjura Mountains",
    "Kabylie", "Oran", "Algiers", "Constantine", "Annaba", "Tlemcen",
    "Setif", "Biskra", "Tamanrasset", "Ghardaia",
    # Historical / architectural depth roots
    "Ruins in Algeria", "Ancient history of Algeria", "Numidia",
    "Roman architecture in Algeria", "Ottoman architecture in Algeria",
    "Colonial architecture in Algeria", "French colonial architecture in Algeria",
    "Mausoleums in Algeria", "Ksour in Algeria", "Berber architecture",
    "Castles in Algeria", "Ancient Roman buildings in Algeria",
    "Punic settlements in Algeria", "Byzantine architecture in Algeria",
    "Streets in Algeria", "Squares in Algeria", "Arches in Algeria",
    "Baths in Algeria", "Amphitheaters in Algeria", "Theatres in Algeria",
    "Basilicas in Algeria", "Cathedrals in Algeria", "Monasteries in Algeria",
    "Zawiyas in Algeria", "Cisterns in Algeria", "Aqueducts in Algeria",
    "Necropoleis in Algeria", "Megalithic monuments in Algeria",
    "Dolmens in Algeria", "Tumuli in Algeria", "Rock carvings in Algeria",
    "Petroglyphs in Algeria", "Capsian culture", "Phoenician colonies in Algeria",
    "Vandal Kingdom", "Ottoman Algeria", "French Algeria",
    "Algerian War", "Battle of Algiers", "People's National Army",
    "Agriculture in Algeria", "Oases of the Sahara",
] + [f"{w} Province" for w in [
    "Adrar", "Chlef", "Laghouat", "Oum El Bouaghi", "Batna", "Béjaïa",
    "Biskra", "Béchar", "Blida", "Bouira", "Tamanrasset", "Tébessa",
    "Tlemcen", "Tiaret", "Tizi Ouzou", "Algiers", "Djelfa", "Jijel",
    "Sétif", "Saïda", "Skikda", "Sidi Bel Abbès", "Annaba", "Guelma",
    "Constantine", "Médéa", "Mostaganem", "M'Sila", "Mascara", "Ouargla",
    "Oran", "El Bayadh", "Illizi", "Bordj Bou Arréridj", "Boumerdès",
    "El Tarf", "Tindouf", "Tissemsilt", "El Oued", "Khenchela",
    "Souk Ahras", "Tipaza", "Mila", "Aïn Defla", "Naâma", "Aïn Témouchent",
    "Ghardaïa", "Relizane", "Timimoun", "Bordj Badji Mokhtar", "Ouled Djellal",
    "Béni Abbès", "In Salah", "In Guezzam", "Touggourt", "Djanet",
    "El M'Ghair", "El Meniaa",
]]

SKIP_SUBCAT_PATTERNS = ("people", "history of", "maps", "drawings", "stamps",
                        "coins", "logos", "flags", "documents", "manuscripts",
                        "postcards", "panoramics", "aerial", "satellite", "maps ")


def api(params, retries=4):
    params = dict(params)
    params["format"] = "json"
    url = COMMONS_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"  API error (attempt {attempt + 1}/{retries}): {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None


def get_subcats(cat):
    subs = []
    cont = ""
    while True:
        params = {
            "action": "query", "list": "categorymembers",
            "cmtitle": f"Category:{cat}", "cmtype": "subcat",
            "cmlimit": "500",
        }
        if cont:
            params["cmcontinue"] = cont
        data = api(params)
        if not data or "query" not in data:
            break
        for m in data["query"]["categorymembers"]:
            name = m["title"].replace("Category:", "")
            subs.append(name)
        if "continue" in data and "cmcontinue" in data["continue"]:
            cont = data["continue"]["cmcontinue"]
        else:
            break
        time.sleep(SLEEP)
    return subs


def get_files_with_coords(cat):
    """Return list of (lat, lon, url) for files in category with GPS coords."""
    found = []
    cont = ""
    while True:
        params = {
            "action": "query", "generator": "categorymembers",
            "gcmtitle": f"Category:{cat}", "gcmtype": "file",
            "gcmlimit": "500", "prop": "coordinates|imageinfo",
            "iiprop": "url", "colimit": "50",
        }
        if cont:
            params["gcmcontinue"] = cont
        data = api(params)
        if not data or "query" not in data:
            break
        pages = data["query"].get("pages", {})
        for p in pages.values():
            coords = p.get("coordinates") or []
            if not coords:
                continue
            ii = (p.get("imageinfo") or [{}])[0]
            url = ii.get("url")
            if not url:
                continue
            lat = coords[0]["lat"]
            lon = coords[0]["lon"]
            found.append((lat, lon, url))
        if "continue" in data and "gcmcontinue" in data["continue"]:
            cont = data["continue"]["gcmcontinue"]
        else:
            break
        time.sleep(SLEEP)
    return found


def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    print("=== Category-Walk Photo Enrichment ===\n")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, latitude, longitude FROM pois
        WHERE (photo_urls IS NULL OR photo_urls = '{}')
          AND latitude IS NOT NULL AND longitude IS NOT NULL
    """)
    pois = cur.fetchall()
    print(f"Photo-less matchable POIs: {len(pois):,}")

    poi_grid = {}
    for pid, lat, lon in pois:
        cell = (round(lat / GRID_SIZE), round(lon / GRID_SIZE))
        poi_grid.setdefault(cell, []).append((pid, lat, lon))

    matched_urls = {}
    all_images = set()
    seen_cats = set()
    queue = [(r, 0) for r in ROOTS]
    cat_count = 0
    img_count = 0

    while queue and cat_count < MAX_CATEGORIES:
        cat, depth = queue.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        cat_count += 1
        print(f"[{cat_count}/{MAX_CATEGORIES}] {cat} (depth {depth})", flush=True)

        items = get_files_with_coords(cat)
        img_count += len(items)
        matched_this = 0
        for lat, lon, url in items:
            if url in all_images:
                continue
            all_images.add(url)
            cell = (round(lat / GRID_SIZE), round(lon / GRID_SIZE))
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    nc = (cell[0] + di, cell[1] + dj)
                    for pid, plon, plat in poi_grid.get(nc, []):
                        if pid in matched_urls:
                            continue
                        if haversine(lat, lon, plon, plat) <= MAX_DISTANCE_M:
                            matched_urls[pid] = url
                            matched_this += 1
                            break
                    if matched_this and pid in matched_urls:
                        break
        print(f"  images {len(items)}, matched {matched_this} (total {len(matched_urls)})", flush=True)

        if depth < MAX_DEPTH:
            subs = get_subcats(cat)
            filtered = [s for s in subs
                        if not any(p in s.lower() for p in SKIP_SUBCAT_PATTERNS)]
            for s in filtered[:60]:
                if s not in seen_cats:
                    queue.append((s, depth + 1))
        time.sleep(SLEEP)

    print(f"\nWalked {cat_count} categories, {img_count} unique images, {len(matched_urls)} matches")

    if matched_urls:
        ids_list = list(matched_urls.items())
        for i in range(0, len(ids_list), 500):
            batch = ids_list[i:i + 500]
            for pid, url in batch:
                if len(url) > 450:
                    base = url.rsplit("/", 1)[-1].split("?")[0]
                    url = "https://commons.wikimedia.org/wiki/Special:FilePath/" \
                          + urllib.parse.quote(base) + "?width=800"
                cur.execute(
                    "UPDATE pois SET photo_urls = ARRAY[%s], photo_url = COALESCE(photo_url, %s) "
                    "WHERE id = %s AND (photo_urls IS NULL OR photo_urls = '{}')",
                    (url, url, str(pid)),
                )
            conn.commit()
            print(f"  Updated {min(i + 500, len(ids_list))}/{len(ids_list)}")
        print("Done")

    cur.execute("SELECT COUNT(*) FROM pois WHERE photo_urls IS NOT NULL AND photo_urls != '{}'")
    total = cur.fetchone()[0]
    print(f"Total POIs with photos: {total:,}")
    conn.close()


if __name__ == "__main__":
    main()
