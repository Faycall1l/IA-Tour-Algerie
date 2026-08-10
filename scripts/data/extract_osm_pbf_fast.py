#!/usr/bin/env python3
"""Fast local OSM PBF extraction using osmium C++ filters (no Python iteration of every object)."""

import json
import math
import sys
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "scripts" / "data" / "raw"
PBF = RAW / "osm" / "algeria-latest.osm.pbf"

TAGS_OF_INTEREST = {
    "tourism": ("attraction", "museum", "artwork", "viewpoint", "theme_park",
                "zoo", "picnic_site", "gallery", "information", "hotel",
                "guest_house", "hostel", "motel", "alpine_hut", "chalet",
                "camp_site", "apartment", "caravan_site", "resort"),
    "historic": ("*",),
    "amenity": ("restaurant", "cafe", "fast_food", "place_of_worship"),
}

STAY_TOURISM = {
    "hotel", "guest_house", "hostel", "motel", "alpine_hut", "chalet",
    "camp_site", "apartment", "caravan_site", "resort",
}

PICK_KEYS = (
    "name:ar", "wikidata", "wikipedia", "phone", "website", "opening_hours",
    "fee", "wheelchair", "description", "stars", "capacity", "internet_access",
    "internet_access:fee", "smoking", "wifi", "rooms", "beds", "price_range",
    "address", "cuisine", "vegan", "vegetarian", "takeaway", "outdoor_seating",
)


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_wilaya(lat, lon, centers):
    best, best_d = None, None
    for wid, (clat, clon) in centers.items():
        d = haversine(lat, lon, clat, clon)
        if best_d is None or d < best_d:
            best, best_d = wid, d
    return best


def categorize(tags):
    a = tags.get("amenity")
    if a in ("restaurant", "fast_food"):
        return "restaurant", "restaurant"
    if a == "cafe":
        return "cafe", "cafe"
    h = tags.get("historic")
    if h:
        if tags.get("religion") or h in ("wayside_shrine", "wayside_cross"):
            return "religious", f"historic/{h}"
        if h == "memorial":
            return "historical", "memorial"
        if h == "archaeological_site":
            return "historical", "archaeological"
        return "historical", f"historic/{h}"
    n = tags.get("natural")
    if n:
        if n == "beach":
            return "beach", n
        if n in ("peak", "hill", "volcano", "cliff", "dune", "ridge"):
            return "mountain", n
        if n in ("waterfall", "spring", "hot_spring", "geyser", "cave",
                 "sinkhole", "bay", "cape", "oasis", "desert", "lake",
                 "wood", "forest", "wetland", "heath", "scrub", "rock"):
            return "natural", n
        return "natural", n
    t = tags.get("tourism")
    if t == "museum":
        return "museum", "museum"
    if t == "attraction":
        return "cultural", "attraction"
    if t == "viewpoint":
        return "natural", "viewpoint"
    if t == "artwork":
        return "cultural", "artwork"
    if t == "theme_park":
        return "park", "theme_park"
    if t == "zoo":
        return "park", "zoo"
    if t == "picnic_site":
        return "park", "picnic_site"
    if a == "place_of_worship":
        return "religious", a
    return None, None


def process(pbf_path):
    centers = {
        int(w["id"]): (w["latitude"], w["longitude"])
        for w in json.loads((RAW / "wilayas_centers.json").read_text(encoding="utf-8"))
    }

    ACCEPT = {
        "tourism": TAGS_OF_INTEREST["tourism"],
        "historic": ("*",),
        "amenity": TAGS_OF_INTEREST["amenity"],
        "natural": ("*",),
    }

    pois, food, stays = [], [], []
    seen = set()
    total = 0

    for key in ACCEPT:
        fp = (
            osmium.FileProcessor(str(pbf_path))
            .with_locations()
            .with_filter(osmium.filter.KeyFilter(key))
        )
        for obj in fp:
            total += 1
            tags = {tag.k: tag.v for tag in obj.tags}
            val = tags.get(key)
            if not val or (ACCEPT[key] != ("*",) and val not in ACCEPT[key]):
                continue
            name = tags.get("name")
            if not name:
                continue
            loc = getattr(obj, "location", None)
            if loc is None and hasattr(obj, "nodes"):
                for nd in obj.nodes:
                    nl = getattr(nd, "location", None)
                    if nl is not None:
                        loc = nl
                        break
            if loc is None:
                continue
            key_id = (obj.type_str(), obj.id)
            if key_id in seen:
                continue
            seen.add(key_id)
            lat, lon = loc.lat, loc.lon
            wid = nearest_wilaya(lat, lon, centers)
            ref = f"{obj.type_str()}/{obj.id}"
            base = {
                "source": "osm",
                "source_id": ref,
                "name_fr": None,
                "name_ar": tags.get("name:ar"),
                "name_en": name,
                "lat": lat,
                "lng": lon,
                "wilaya_code": f"{wid:02d}",
                "description": None,
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2026-08-01",
                "url": f"https://www.openstreetmap.org/{ref}",
                "refs": {"osm": ref},
                "tags": {k: v for k, v in tags.items() if k in PICK_KEYS},
            }
            t = tags.get("tourism")
            if t in STAY_TOURISM:
                stype = {"hotel": "hotel", "motel": "hotel", "hostel": "hostel",
                         "guest_house": "guesthouse", "chalet": "guesthouse"}.get(t, "hotel")
                rec = {**base, "type": stype, "subtype": t, "purpose": "stays"}
                stays.append(rec)
                continue
            if tags.get("amenity") in ("restaurant", "fast_food", "cafe"):
                cat = "restaurant" if tags["amenity"] != "cafe" else "cafe"
                rec = {**base, "category": cat, "subtype": tags["amenity"], "purpose": "user"}
                food.append(rec)
                continue
            cat, sub = categorize(tags)
            if cat is None:
                continue
            rec = {**base, "category": cat, "subtype": sub, "purpose": "user"}
            pois.append(rec)

    return pois, food, stays, total


def main() -> int:
    if not PBF.exists():
        print(f"missing {PBF}")
        return 1
    print(f"extracting from {PBF} ...", flush=True)
    pois, food, stays, total = process(PBF)
    (RAW / "osm_pois_named.json").write_text(
        json.dumps(pois, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "osm_food_named.json").write_text(
        json.dumps(food, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "osm_stays_named.json").write_text(
        json.dumps(stays, ensure_ascii=False), encoding="utf-8"
    )
    qa = {
        "pois": len(pois),
        "food": len(food),
        "stays": len(stays),
        "total": len(pois) + len(food) + len(stays),
        "matched_objects": total,
    }
    (RAW / "osm_named_qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(qa, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())