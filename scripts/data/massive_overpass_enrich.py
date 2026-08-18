#!/usr/bin/env python3
"""Fast enrichment via Overpass API — population-sorted, checkpointed.

Queries in order of population density (highest first) so we get the most
new POIs early. Desert wilayas use tiny bboxes around the city only.
Checkpointed to resume on failure.
"""

import asyncio
import hashlib
import json
import math
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
CP_FILE = ROOT / "scripts/data/reports/overpass_fast_cp.json"

OVERPASS = "https://overpass-api.de/api/interpreter"

# Population-sorted: dense cities first, desert last
# (lat, lon, name, bbox_radius_deg)
WILAYAS = [
    (16, 36.75, 3.06, "Algiers", 0.2),
    (31, 35.7, -0.63, "Oran", 0.2),
    (25, 36.36, 6.61, "Constantine", 0.2),
    (6, 36.75, 5.07, "Bejaia", 0.2),
    (15, 36.71, 4.05, "Tizi Ouzou", 0.2),
    (5, 35.56, 6.17, "Batna", 0.2),
    (19, 36.19, 5.41, "Setif", 0.2),
    (9, 36.47, 2.83, "Blida", 0.2),
    (23, 36.9, 7.76, "Annaba", 0.2),
    (35, 36.76, 3.48, "Boumerdes", 0.15),
    (18, 36.82, 5.77, "Jijel", 0.15),
    (21, 36.88, 6.91, "Skikda", 0.15),
    (36, 36.77, 8.31, "El Tarf", 0.15),
    (24, 36.46, 7.43, "Guelma", 0.15),
    (43, 36.45, 6.26, "Mila", 0.15),
    (40, 35.44, 7.14, "Khenchela", 0.15),
    (12, 35.4, 8.12, "Tebessa", 0.15),
    (41, 36.29, 7.95, "Souk Ahras", 0.15),
    (4, 35.87, 7.11, "Oum El Bouaghi", 0.15),
    (10, 36.37, 3.9, "Bouira", 0.15),
    (34, 36.07, 4.77, "BBA", 0.15),
    (2, 36.16, 1.33, "Chlef", 0.15),
    (42, 36.59, 2.45, "Tipaza", 0.15),
    (26, 36.26, 2.75, "Medea", 0.15),
    (14, 35.37, 1.32, "Tiaret", 0.15),
    (44, 36.26, 1.97, "Ain Defla", 0.15),
    (28, 35.7, 4.54, "MSila", 0.15),
    (13, 34.88, -1.32, "Tlemcen", 0.15),
    (22, 35.19, -0.63, "SBA", 0.15),
    (48, 35.74, 0.56, "Relizane", 0.15),
    (27, 35.93, 0.09, "Mostaganem", 0.15),
    (29, 35.4, 0.14, "Mascara", 0.15),
    (20, 34.83, 0.15, "Saida", 0.15),
    (46, 35.3, -1.14, "Ain Temouchent", 0.15),
    (38, 35.61, 1.81, "Tissemsilt", 0.15),
    (7, 34.85, 5.73, "Biskra", 0.2),
    (39, 33.37, 6.86, "El Oued", 0.15),
    (17, 34.67, 3.25, "Djelfa", 0.2),
    (3, 33.8, 2.87, "Laghouat", 0.2),
    (32, 33.68, 1.02, "El Bayadh", 0.15),
    (30, 31.96, 5.33, "Ouargla", 0.2),
    (47, 32.49, 3.67, "Ghardaia", 0.2),
    (8, 31.62, -2.22, "Bechar", 0.2),
    (45, 33.27, -0.31, "Naama", 0.15),
    (51, 34.43, 5.06, "Ouled Djellal", 0.15),
    (59, 34.11, 2.1, "Aflou", 0.15),
    (60, 35.4, 5.37, "Barika", 0.15),
    (61, 35.19, 5.67, "El Kantara", 0.15),
    (64, 35.21, 2.32, "Ksar Chellala", 0.15),
    (67, 35.89, 2.75, "Ksar El Boukhari", 0.15),
    (68, 35.21, 4.17, "Bou Saada", 0.15),
    (62, 34.75, 8.06, "Bir El Ater", 0.15),
    (63, 34.22, -1.26, "El Aricha", 0.15),
    (65, 35.45, 2.9, "Ain Ouessara", 0.15),
    (66, 34.15, 3.5, "Messaad", 0.15),
    (69, 32.9, 0.54, "El Abiodh Sidi Cheikh", 0.15),
    (11, 22.79, 5.52, "Tamanrasset", 0.15),
    (55, 33.1, 6.07, "Touggourt", 0.15),
    (57, 33.95, 5.92, "El MGhair", 0.15),
    (58, 30.58, 2.88, "El Meniaa", 0.1),
    (49, 29.26, 0.23, "Timimoun", 0.1),
    (52, 30.08, -2.17, "Beni Abbes", 0.1),
    (53, 27.19, 2.48, "In Salah", 0.1),
    (37, 27.67, -8.15, "Tindouf", 0.1),
    (33, 26.51, 8.48, "Illizi", 0.1),
    (56, 24.55, 9.48, "Djanet", 0.1),
    (50, 21.33, 0.92, "BBM", 0.1),
    (54, 19.57, 5.77, "In Guezzam", 0.1),
]

OVERPASS_QUERIES = [
    ("tourism", (
        '[out:json][timeout:60];'
        '(node["tourism"](bbox:{b});way["tourism"](bbox:{b}););'
        'out center body;'
    )),
    ("historic", (
        '[out:json][timeout:60];'
        '(node["historic"](bbox:{b});way["historic"](bbox:{b}););'
        'out center body;'
    )),
    ("named_natural", (
        '[out:json][timeout:60];'
        '(node["natural"]["name"](bbox:{b});way["natural"]["name"](bbox:{b}););'
        'out center body;'
    )),
    ("named_amenity", (
        '[out:json][timeout:60];'
        '(node["amenity"~"^(restaurant|cafe|fast_food|bar|pub|cinema|theatre|'
        'library|community_centre|place_of_worship)$"]["name"](bbox:{b});'
        'way["amenity"~"^(restaurant|cafe|fast_food|bar|pub|cinema|theatre|'
        'library|community_centre|place_of_worship)$"]["name"](bbox:{b}););'
        'out center body;'
    )),
    ("named_leisure", (
        '[out:json][timeout:60];'
        '(node["leisure"~"^(park|garden|nature_reserve|stadium|sports_centre)$"]'
        '["name"](bbox:{b});'
        'way["leisure"~"^(park|garden|nature_reserve|stadium|sports_centre)$"]'
        '["name"](bbox:{b}););'
        'out center body;'
    )),
    ("craft_shop", (
        '[out:json][timeout:60];'
        '(node["shop"~"^(craft|pottery|carpet|jewelry|leather|souvenir)$"]'
        '(bbox:{b});node["craft"](bbox:{b}););'
        'out center body;'
    )),
]

CAT_MAP = {
    "museum": ("museum","museum"), "attraction": ("historical","attraction"),
    "artwork": ("cultural","artwork"), "viewpoint": ("natural","viewpoint"),
    "gallery": ("cultural","gallery"), "camp_site": ("natural","camp_site"),
    "picnic_site": ("natural","picnic_site"), "information": ("natural","info"),
    "theme_park": ("natural","theme_park"), "zoo": ("natural","zoo"),
    "hotel": ("restaurant","hotel"), "motel": ("restaurant","hotel"),
    "guest_house": ("restaurant","guest_house"), "hostel": ("restaurant","hostel"),
    "chalet": ("restaurant","chalet"), "resort": ("restaurant","resort"),
    "apartment": ("restaurant","apartment"),
}
HIST_MAP = {
    "castle": ("historical","castle"), "ruins": ("historical","ruins"),
    "archaeological_site": ("historical","archaeological"),
    "memorial": ("historical","memorial"), "monument": ("historical","monument"),
    "fort": ("historical","fort"), "mosque": ("religious","historic_mosque"),
    "mausoleum": ("historical","mausoleum"), "tomb": ("historical","tomb"),
    "church": ("religious","historic_church"), "palace": ("historical","palace"),
    "citywalls": ("historical","city_walls"), "yes": ("historical","historic"),
    "house": ("historical","historic_house"), "manor": ("historical","manor"),
}
NAT_MAP = {
    "peak": ("mountain","peak"), "hill": ("mountain","hill"),
    "volcano": ("mountain","volcano"), "cliff": ("mountain","cliff"),
    "dune": ("mountain","dune"), "ridge": ("mountain","ridge"),
    "waterfall": ("natural","waterfall"), "spring": ("natural","spring"),
    "hot_spring": ("natural","hot_spring"), "cave": ("natural","cave"),
    "oasis": ("natural","oasis"), "lake": ("natural","lake"),
    "water": ("natural","water"), "wood": ("natural","wood"),
    "beach": ("beach","beach"), "cape": ("beach","cape"),
    "bay": ("beach","bay"), "yes": ("natural","natural"),
}


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


def classify(tags):
    a = tags.get("amenity")
    if a in ("restaurant", "fast_food"):
        return "restaurant", "restaurant"
    if a == "cafe":
        return "cafe", "cafe"
    if a in ("bar", "pub"):
        return "cafe", "bar"
    if a in ("cinema", "theatre", "library", "community_centre"):
        return "cultural", a
    if a == "place_of_worship":
        return "religious", "place_of_worship"
    h = tags.get("historic")
    if h:
        return HIST_MAP.get(h, ("historical", f"historic/{h}"))
    t = tags.get("tourism")
    if t:
        return CAT_MAP.get(t, ("natural", t))
    n = tags.get("natural")
    if n:
        return NAT_MAP.get(n, ("natural", n))
    lev = tags.get("leisure")
    if lev:
        return ("natural", lev)
    s = tags.get("shop") or tags.get("craft")
    if s:
        return ("cultural", f"shop/{s}")
    return None, None


def make_source_id(lat, lon, name):
    return hashlib.md5(f"{lat:.6f},{lon:.6f},{name}".encode()).hexdigest()[:16]


def bbox_str(lat, lon, r):
    return f"{lat-r:.4f},{lon-r:.4f},{lat+r:.4f},{lon+r:.4f}"


def load_cp():
    if CP_FILE.exists():
        return json.loads(CP_FILE.read_text())
    return {"done": [], "inserted": {}}


def save_cp(cp):
    CP_FILE.parent.mkdir(parents=True, exist_ok=True)
    CP_FILE.write_text(json.dumps(cp))


async def query_osm(client, query):
    for attempt in range(4):
        try:
            r = await client.post(OVERPASS, data={"data": query}, timeout=90)
            if r.status_code == 429:
                await asyncio.sleep(30 + attempt*15)
                continue
            if r.status_code == 504:
                await asyncio.sleep(20 + attempt*10)
                continue
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError):
            await asyncio.sleep(10 + attempt*5)
    return None


async def main():
    from app.db.session import async_session as sess
    from sqlalchemy import text

    cp = load_cp()
    total_new = 0

    async with httpx.AsyncClient(headers={"User-Agent": "ATHAR/1.0"}) as client:
        async with sess() as db:
            for wid, lat, lon, name, radius in WILAYAS:
                if str(wid) in cp.get("inserted", {}) and cp["inserted"][str(wid)] >= 0:
                    prev = cp["inserted"][str(wid)]
                    print(f"\nw{wid:2d} {name:30s} SKIP (+{prev})")
                    total_new += prev
                    continue

                print(f"\nw{wid:2d} {name:30s} ({lat:.2f},{lon:.2f}) r={radius}")

                existing = await db.execute(
                    text("SELECT latitude,longitude,name FROM pois WHERE wilaya_id=:w"),
                    {"w": wid},
                )
                existing_set = {
                    (round(r[0],4),round(r[1],4),r[2].lower().strip())
                    for r in existing
                }
                ecount = len(existing_set)
                seen = set()
                all_pois = []

                for qname, qtmpl in OVERPASS_QUERIES:
                    q = qtmpl.format(b=bbox_str(lat, lon, radius))
                    data = await query_osm(client, q)
                    if not data:
                        print(f"  {qname}: FAILED")
                        await asyncio.sleep(5)
                        continue
                    elems = data.get("elements", [])
                    print(f"  {qname}: {len(elems)}")

                    for el in elems:
                        raw = el.get("tags", {})
                        if not isinstance(raw, dict):
                            continue
                        name_val = raw.get("name")
                        if not name_val:
                            continue
                        elat = el.get("lat") or (el.get("center") or {}).get("lat")
                        elon = el.get("lon") or (el.get("center") or {}).get("lon")
                        if not elat or not elon:
                            continue
                        dk = (round(elat,4), round(elon,4), name_val.lower().strip())
                        if dk in seen or dk in existing_set:
                            continue
                        seen.add(dk)
                        cat, sub = classify(raw)
                        if cat is None:
                            continue
                        all_pois.append({
                            "name": name_val,
                            "name_en": raw.get("name:en"),
                            "name_ar": raw.get("name:ar"),
                            "category": cat,
                            "subtype": sub,
                            "latitude": elat,
                            "longitude": elon,
                            "wilaya_id": wid,
                            "description": raw.get("description",""),
                            "source": "osm",
                            "source_id": make_source_id(elat, elon, name_val),
                            "osm_node_id": el.get("id"),
                            "osm_tags": json.dumps({k:v for k,v in raw.items() if k in (
                                "name","name:ar","name:en","name:fr","wikidata",
                                "wikipedia","phone","website","opening_hours","fee",
                                "cuisine","stars","wheelchair","description",
                            )}),
                        })
                    await asyncio.sleep(3)

                inserted = 0
                for poi in all_pois:
                    try:
                        await db.execute(text("""
                            INSERT INTO pois (id,name,name_en,name_ar,category,subtype,
                                latitude,longitude,wilaya_id,description,source,source_id,
                                osm_node_id,osm_tags,is_featured,entry_fee_dzd,
                                suggested_duration_min,price_level,ranking_position,ranking_total)
                            VALUES (gen_random_uuid(),:name,:name_en,:name_ar,:category,:subtype,
                                :latitude,:longitude,:wilaya_id,:description,:source,:source_id,
                                :osm_node_id,CAST(:osm_tags AS jsonb),false,0,30,'free',0,0)
                        """), poi)
                        inserted += 1
                    except Exception:
                        pass
                await db.commit()

                total_new += inserted
                cp.setdefault("inserted", {})[str(wid)] = inserted
                save_cp(cp)
                print(f"  => +{inserted} (total {ecount} -> {ecount+inserted})")
                await asyncio.sleep(5)

    print(f"\n{'='*60}")
    print(f"TOTAL NEW: {total_new} POIs")
    save_cp(cp)


if __name__ == "__main__":
    asyncio.run(main())
