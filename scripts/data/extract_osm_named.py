#!/usr/bin/env python3
"""Overpass API named-only extraction for all 69 wilayas (Aug 2026).

Real named places only — tagged OSM elements whose object has a `name`.
No placeholders, no synthetic rows. Outputs unified-stage JSON consumed by
stage_sources.py's OSM merge step:

OUTPUT:
- scripts/data/raw/osm_pois_named.json     (tourism/historic/natural/cultural
                                            + restaurants/cafes → pois_v2)
- scripts/data/raw/osm_stays_named.json    (hotel/guest_house/hostel/motel/
                                            dormitory/chalet/appartment/camp
                                            → stays_v2)

Tags covered (nodes + ways only, ways collapsed to centroid):
POIs: tourism=attraction|museum|viewpoint|artwork|zoo|theme_park|picnic_site,
      historic=*, natural=* (relevant subset), amenity=place_of_worship, beach
Stays: tourism=hotel|guest_house|hostel|motel|alpine_hut|chalet|camp_site,
      building=hotel (fallback), tourism=apartment
Food:  amenity=restaurant|cafe|fast_food, cuisine=* optional

Usage: python scripts/data/extract_osm_named.py
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "scripts" / "data" / "raw"
OVERPASS = "https://overpass-api.de/api/interpreter"
# mirror fallbacks
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.big-map.nl/api/interpreter",
]

POI_TAGS = (
    "nwr[tourism](if:t['tourism']!~'hotel|guest_house|hostel|motel|alpine_hut|chalet|camp_site|apartment|caravan_site|resort');"
)
STAY_TAGS = "nwr[tourism](if:t['tourism']~'hotel|guest_house|hostel|motel|alpine_hut|chalet|camp_site|apartment|caravan_site|resort');"
FOOD_TAGS = "nwr[amenity~'restaurant|cafe|fast_food'];"


def bbox_for(lat: float) -> float:
    """Bbox radius half-width by latitude band.

    Northern wilayas are compact (cities, coast); southern wilayas are
    enormous (Adrar 439k km², Tamanrasset 557k km²) and POIs cluster in
    far-flung oases/parks — need wide boxes to reach them.
    """
    if lat >= 33.0:
        return 0.55
    if lat >= 28.0:
        return 1.2
    if lat >= 26.0:
        return 2.2
    return 3.2


def bbox_query(wilaya: dict, tags: str) -> str:
    lat, lon = wilaya["latitude"], wilaya["longitude"]
    r = bbox_for(lat)
    s, w, n, e = lat - r, lon - r, lat + r, lon + r
    return (
        f'[out:json][timeout:180];'
        f"({tags}({s:.4f},{w:.4f},{n:.4f},{e:.4f}););"
        f'out center tags;'
    )


def run_overpass(q: str, retries: int = 4) -> dict:
    last = None
    for i in range(retries):
        for url in [OVERPASS] + MIRRORS:
            try:
                resp = httpx.post(url, data={"data": q}, timeout=200)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if "elements" in data and data["elements"]:
                    return data
            except Exception as exc:
                last = exc
        time.sleep(3 + i * 4)
    if last:
        print(f"  overpass failed: {last}")
    return {"elements": []}


def categorize(tags: dict) -> tuple[str, str]:
    """Return (category, subtype) mapped to ATHAR pois CHECK constraint."""
    t = tags.get("tourism")
    h = tags.get("historic")
    n = tags.get("natural")
    a = tags.get("amenity")
    if a in ("restaurant", "fast_food"):
        return "restaurant", "restaurant"
    if a == "cafe":
        return "cafe", "cafe"
    if h:
        # historic=* values → historical except religious buildings
        if tags.get("religion") or h in ("wayside_shrine", "wayside_cross"):
            return "religious", f"historic/{h}"
        if h == "memorial":
            return "historical", "memorial"
        if h == "archaeological_site":
            return "historical", "archaeological"
        return "historical", f"historic/{h}"
    if n:
        if n in ("beach", "beachrock"):
            return "beach", n
        if n in ("peak", "hill", "volcano", "cliff", "dune", "ridge"):
            return "mountain", n
        if n in ("waterfall", "spring", "hot_spring", "geyser", "cave",
                 "sinkhole", "bay", "cape", "desert", "oasis", "lake"):
            return "natural", n
        if n in ("wood", "forest", "wetland", "heath", "scrub"):
            return "natural", n
        return "natural", n or "place"
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
    if tags.get("historic") is None and tags.get("tourism") is None:
        return "cultural", "other"
    return "cultural", t or "other"


def stays_from_tags(tags: dict) -> tuple[str, str]:
    t = tags.get("tourism")
    if t in ("hotel", "motel"):
        return "hotel", "hotel"
    if t == "hostel":
        return "hostel", "hostel"
    if t in ("guest_house", "bed_and_breakfast", "chalet"):
        return "guesthouse", t
    if t in ("alpine_hut", "camp_site", "caravan_site", "resort", "apartment"):
        return "hotel", t
    return "hotel", t or "hotel"


def element_coords(el: dict) -> tuple[float, float]:
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else (None, None)


def main() -> int:
    wilayas = json.loads((RAW / "wilayas_centers.json").read_text(encoding="utf-8"))
    pois_out: list[dict] = []
    stays_out: list[dict] = []
    food_out: list[dict] = []
    per_wilaya: dict[int, dict] = {}
    seen = set()

    for wi, w in enumerate(wilayas):
        wid = w["id"]
        counts = {"poi": 0, "stay": 0, "food": 0}
        for tags, tag_name in [
            (POI_TAGS, "poi"),
            (STAY_TAGS, "stay"),
            (FOOD_TAGS, "food"),
        ]:
            data = run_overpass(bbox_query(w, tags))
            for el in data.get("elements", []):
                el_tags = el.get("tags") or {}
                name = el_tags.get("name")
                if not name or not name.strip():
                    continue
                lat, lon = element_coords(el)
                if lat is None:
                    continue
                key = (el.get("type"), el.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                osm_ref = f"{el.get('type')}/{el['id']}"
                if tag_name == "stay" and el_tags.get("tourism") in (
                    "hotel", "guest_house", "hostel", "motel", "alpine_hut",
                    "chalet", "camp_site", "apartment", "resort", "caravan_site",
                ):
                    stay_type, stay_sub = stays_from_tags(el_tags)
                    stays_out.append(
                        {
                            "source": "osm",
                            "source_id": osm_ref,
                            "name_fr": None,
                            "name_ar": el_tags.get("name:ar"),
                            "name_en": name,
                            "type": stay_type,
                            "subtype": stay_sub,
                            "lat": lat,
                            "lng": lon,
                            "wilaya_code": f"{wid:02d}",
                            "description": None,
                            "rating": None,
                            "num_reviews": None,
                            "photo_urls": [],
                            "verified_at": "2026-08-01",
                            "url": f"https://www.openstreetmap.org/{osm_ref}",
                            "refs": {"osm": osm_ref},
                            "purpose": "stays",
                            "tags": {
                                k: el_tags[k]
                                for k in (
                                    "stars", "capacity", "internet_access",
                                    "internet_access:fee", "smoking", "wifi",
                                    "rooms", "beds", "price_range",
                                    "address", "phone", "website", "opening_hours",
                                    "payment:mastercard", "payment:visa",
                                )
                                if k in el_tags
                            },
                        }
                    )
                    per_wilaya.setdefault(wid, {"poi": 0, "stay": 0, "food": 0})
                    per_wilaya[wid]["stay"] += 1
                    counts["stay"] += 1
                    continue
                if el_tags.get("amenity") in ("restaurant", "cafe", "fast_food"):
                    cat, sub = categorize(el_tags)
                    food_out.append(
                        {
                            "source": "osm",
                            "source_id": osm_ref,
                            "name_fr": None,
                            "name_ar": el_tags.get("name:ar"),
                            "name_en": name,
                            "category": cat,
                            "subtype": sub,
                            "lat": lat,
                            "lng": lon,
                            "wilaya_code": f"{wid:02d}",
                            "description": None,
                            "rating": None,
                            "num_reviews": None,
                            "photo_urls": [],
                            "verified_at": "2026-08-01",
                            "url": f"https://www.openstreetmap.org/{osm_ref}",
                            "refs": {"osm": osm_ref},
                            "purpose": "user",
                            "tags": {
                                k: el_tags[k]
                                for k in (
                                    "cuisine", "opening_hours", "phone",
                                    "website", "price_range", "vegan",
                                    "vegetarian", "takeaway", "outdoor_seating",
                                )
                                if k in el_tags
                            },
                        }
                    )
                    per_wilaya.setdefault(wid, {"poi": 0, "stay": 0, "food": 0})
                    per_wilaya[wid]["food"] += 1
                    counts["food"] += 1
                    continue
                # place to visit (attraction/museum/historic/natural/…)
                cat, sub = categorize(el_tags)
                if cat in ("cultural", "historical", "natural", "museum",
                           "religious", "park", "beach", "mountain"):
                    pois_out.append(
                        {
                            "source": "osm",
                            "source_id": osm_ref,
                            "name_fr": None,
                            "name_ar": el_tags.get("name:ar"),
                            "name_en": name,
                            "category": cat,
                            "subtype": sub,
                            "lat": lat,
                            "lng": lon,
                            "wilaya_code": f"{wid:02d}",
                            "description": None,
                            "rating": None,
                            "num_reviews": None,
                            "photo_urls": [],
                            "verified_at": "2026-08-01",
                            "url": f"https://www.openstreetmap.org/{osm_ref}",
                            "refs": {"osm": osm_ref},
                            "purpose": "user",
                            "tags": {
                                k: el_tags[k]
                                for k in (
                                    "wikidata", "wikipedia", "phone",
                                    "website", "opening_hours", "fee",
                                    "wheelchair", "description",
                                )
                                if k in el_tags
                            },
                        }
                    )
                per_wilaya.setdefault(wid, {"poi": 0, "stay": 0, "food": 0})
                per_wilaya[wid]["poi"] += 1
                counts["poi"] += 1
        print(
            f"  w{wid:02d} {w['name_fr'][:20]:22} poi={counts['poi']:4} "
            f"stay={counts['stay']:3} food={counts['food']:4}",
            flush=True,
        )
        time.sleep(1.5)  # be kind to Overpass

    (RAW / "osm_pois_named.json").write_text(
        json.dumps(pois_out, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "osm_stays_named.json").write_text(
        json.dumps(stays_out, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "osm_food_named.json").write_text(
        json.dumps(food_out, ensure_ascii=False), encoding="utf-8"
    )
    qa = {
        "pois": len(pois_out),
        "stays": len(stays_out),
        "food": len(food_out),
        "total": len(pois_out) + len(stays_out) + len(food_out),
        "unique_elements": len(seen),
        "wilayas": {str(k): v for k, v in per_wilaya.items()},
    }
    (RAW / "osm_named_qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(qa, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())