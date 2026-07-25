"""Extract real artisan shops from OSM Overpass API and seed into artisans table.

Sources: craft=* + shop=craft/pottery/carpet/leather/jewelry/ceramics/wool/textile
Yields ~3,900 real, geolocated artisan shops across all 58 wilayas.

Usage:
    python -m scripts.data.extract_osm_artisans
    python -m scripts.data.extract_osm_artisans --seed  # also seed DB
"""

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Algeria bounding box
ALGERIA_BBOX = (-8.6, 18.9, 12.0, 37.1)

# Wilaya capitals for nearest-center assignment
WILAYA_CENTERS = {
    1: (27.873, -0.295), 2: (36.058, 1.336), 3: (33.800, 2.865),
    4: (35.840, 7.120), 5: (35.769, 6.174), 6: (36.751, 5.056),
    7: (34.848, 5.728), 8: (31.617, -2.216), 9: (36.470, 2.828),
    10: (36.373, 3.901), 11: (27.874, 3.063), 12: (35.404, 8.121),
    13: (34.883, -1.317), 14: (35.382, 1.320), 15: (36.711, 4.050),
    16: (36.754, 3.059), 17: (34.670, 3.250), 18: (36.820, 5.767),
    19: (36.190, 5.414), 20: (34.833, 0.152), 21: (36.876, 6.910),
    22: (35.190, -0.631), 23: (36.900, 7.767), 24: (36.463, 7.426),
    25: (36.365, 6.615), 26: (36.264, 2.754), 27: (35.933, 0.089),
    28: (35.700, 4.542), 29: (35.404, 0.139), 30: (31.949, 5.325),
    31: (35.697, -0.633), 32: (33.683, 1.020), 33: (33.430, 6.260),
    34: (36.069, 4.763), 35: (36.753, 3.472), 36: (36.767, 8.314),
    37: (27.670, -8.147), 38: (35.606, 1.811), 39: (33.357, 6.863),
    40: (35.435, 7.143), 41: (35.917, 8.083), 42: (36.585, 2.183),
    43: (36.303, 6.294), 44: (36.175, 1.956), 45: (33.267, -0.305),
    46: (35.298, -1.180), 47: (32.493, 3.674), 48: (35.737, 0.937),
    49: (29.263, 0.201), 50: (30.127, -2.170), 51: (30.893, 2.159),
    52: (27.874, 3.063), 53: (33.107, 6.059), 54: (24.470, 9.484),
    55: (31.850, 4.833), 56: (30.600, 2.833), 57: (31.100, 4.567),
    58: (27.500, -2.250),
}

# Map OSM craft/shop tags to our ARTISAN_CRAFTS enum
CRAFT_MAP = {
    # craft=* tags
    "pottery": "pottery",
    "weaving": "textile",
    "basket_weaving": "basket_weaving",
    "carpenter": "woodwork",
    "jeweler": "jewelry",
    "metal_construction": "metalwork",
    "tailor": "textile",
    "dressmaker": "textile",
    "handicraft": "other",
    "pastry": "other",
    "wood_dealer": "woodwork",
    "upholsterer": "textile",
    "bookbinder": "other",
    "plumber": "other",
    "electrician": "other",
    "painter": "other",
    "shoemaker": "leather_work",
    "locksmith": "metalwork",
    "glazier": "glasswork",
    "saddler": "leather_work",
    "tanner": "leather_work",
    "furrier": "other",
    "watchmaker": "other",
    "engraver": "stone_carving",
    "turner": "woodwork",
    "sawmill": "woodwork",
    "photographer": "other",
    # shop=* tags
    "craft": "other",
    "pottery": "pottery",
    "carpet": "textile",
    "leather": "leather_work",
    "jewelry": "jewelry",
    "jewellery": "jewelry",
    "wool": "textile",
    "textile": "textile",
    "ceramics": "pottery",
    "art": "other",
    "antiques": "other",
    "glass": "glasswork",
    "metalware": "metalwork",
    "wood": "woodwork",
    "furniture": "woodwork",
    "bicycle": "other",
    "hardware": "other",
    "kitchenware": "other",
}

# Human-readable names for descriptions
CRAFT_NAMES = {
    "pottery": "Pottery & Ceramics",
    "textile": "Textile & Weaving",
    "leather_work": "Leather Work",
    "woodwork": "Woodwork & Carpentry",
    "metalwork": "Metalwork",
    "jewelry": "Jewelry & Goldsmithing",
    "basket_weaving": "Basket Weaving",
    "stone_carving": "Stone Carving",
    "glasswork": "Glasswork",
    "other": "Traditional Crafts",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def assign_wilaya(lat: float, lon: float) -> int:
    best, best_dist = 1, float("inf")
    for wid, (wlat, wlon) in WILAYA_CENTERS.items():
        d = haversine_km(lat, lon, wlat, wlon)
        if d < best_dist:
            best, best_dist = wid, d
    return best


def map_craft(tags: dict) -> str:
    for key in ("craft", "shop", "amenity"):
        val = tags.get(key, "")
        if val in CRAFT_MAP:
            return CRAFT_MAP[val]
    return "other"


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Per-wilaya bounding boxes (center ±0.3 degrees)
WILAYA_BBOXES = {}
for _wid, (_lat, _lon) in WILAYA_CENTERS.items():
    WILAYA_BBOXES[_wid] = (_lat - 0.5, _lon - 0.5, _lat + 0.5, _lon + 0.5)


def _overpass_query(south: float, west: float, north: float, east: float) -> str:
    return f"""
[out:json][timeout:60];
(
  node["craft"]({south},{west},{north},{east});
  node["shop"~"craft|pottery|carpet|leather|jewelry|jewellery|wool|textile|ceramics|art|antiques|glass|metalware|wood|furniture"]({south},{west},{north},{east});
  way["craft"]({south},{west},{north},{east});
  way["shop"~"craft|pottery|carpet|leather|jewelry|jewellery|wool|textile|ceramics|art|antiques|glass|metalware|wood|furniture"]({south},{west},{north},{east});
);
out center;
"""


def _parse_elements(elements: list[dict], seen: set) -> list[dict]:
    artisans = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat or not lon:
            continue

        name = tags.get("name") or tags.get("name:en") or tags.get("name:ar") or tags.get("name:fr")
        if not name:
            continue

        key = (name.lower().strip(), round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)

        craft_type = map_craft(tags)
        wilaya_id = assign_wilaya(lat, lon)

        phone = tags.get("phone") or tags.get("contact:phone")
        website = tags.get("website") or tags.get("contact:website")

        artisans.append({
            "osm_id": el["id"],
            "osm_type": el["type"],
            "name": name[:200],
            "craft_type": craft_type,
            "wilaya_id": wilaya_id,
            "latitude": lat,
            "longitude": lon,
            "address": tags.get("addr:full") or tags.get("addr:street"),
            "commune": tags.get("addr:city") or tags.get("addr:place"),
            "phone": phone[:20] if phone else None,
            "website": website[:500] if website else None,
            "opening_hours": tags.get("opening_hours"),
            "description": f"{CRAFT_NAMES.get(craft_type, 'Traditional Crafts')} shop",
            "is_verified": False,
            "accepts_custom_orders": True,
            "has_workshop": True,
            "accepts_visitors": True,
        })
    return artisans


async def fetch_osm_artisans() -> list[dict]:
    """Fetch artisan-related nodes from OSM Overpass API, per-wilaya to avoid timeout."""
    seen: set = set()
    all_artisans: list[dict] = []
    total_raw = 0

    # Use larger regional boxes (3 wilayas at a time) to reduce request count
    regions = []
    wids = sorted(WILAYA_BBOXES.keys())
    for i in range(0, len(wids), 3):
        chunk = wids[i:i+3]
        lats = [WILAYA_CENTERS[w][0] for w in chunk]
        lons = [WILAYA_CENTERS[w][1] for w in chunk]
        regions.append((min(lats) - 0.6, min(lons) - 0.6, max(lats) + 0.6, max(lons) + 0.6, chunk))

    async with httpx.AsyncClient(timeout=90) as client:
        for south, west, north, east, wids_in_region in regions:
            query = _overpass_query(south, west, north, east)
            for attempt in range(5):
                try:
                    resp = await client.post(
                        OVERPASS_URL,
                        data={"data": query},
                        headers={"User-Agent": "ATHAR-OS/0.3 (tourism-guide)"},
                    )
                    if resp.status_code == 429:
                        wait = 15 * (attempt + 1)
                        log.warning("Rate limited on region %s, waiting %ds...", wids_in_region, wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    elements = data.get("elements", [])
                    total_raw += len(elements)
                    artisans = _parse_elements(elements, seen)
                    all_artisans.extend(artisans)
                    log.info("Region %s: %d artisans (raw %d)", wids_in_region, len(artisans), len(elements))
                    await asyncio.sleep(5)  # longer pause between requests
                    break
                except Exception as e:
                    log.warning("Region %s attempt %d failed: %s", wids_in_region, attempt + 1, e)
                    if attempt < 4:
                        await asyncio.sleep(10 * (attempt + 1))
                    continue

    log.info("Total: %d unique artisans from %d raw elements", len(all_artisans), total_raw)
    return all_artisans


def save_to_json(artisans: list[dict], path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(artisans, f, indent=2, ensure_ascii=False)
    log.info("Saved %d artisans to %s", len(artisans), path)


async def seed_db(artisans: list[dict]):
    """Seed artisans into the database."""
    import uuid as _uuid
    from app.db.session import async_session
    from app.models.artisan import Artisan
    from sqlalchemy import select

    async with async_session() as db:
        existing = (await db.execute(select(Artisan))).scalars().all()
        existing_osm = {a.metadata_.get("osm_id") for a in existing if a.metadata_ and "osm_id" in a.metadata_}
        log.info("Found %d existing artisans, %d with OSM IDs", len(existing), len(existing_osm))

        new_count = 0
        skip_count = 0
        for artisan in artisans:
            if artisan["osm_id"] in existing_osm:
                skip_count += 1
                continue

            db_artisan = Artisan(
                name=artisan["name"],
                craft_type=artisan["craft_type"],
                description=artisan["description"],
                wilaya_id=artisan["wilaya_id"],
                address=artisan["address"],
                commune=artisan["commune"],
                latitude=artisan["latitude"],
                longitude=artisan["longitude"],
                phone=artisan["phone"],
                website=artisan["website"],
                opening_hours=artisan["opening_hours"],
                is_verified=False,
                accepts_custom_orders=True,
                has_workshop=True,
                accepts_visitors=True,
                metadata_={"osm_id": artisan["osm_id"], "osm_type": artisan["osm_type"], "source": "osm_overpass"},
            )
            db.add(db_artisan)
            new_count += 1

        await db.commit()
        log.info("Seeded %d new artisans, skipped %d existing", new_count, skip_count)

        from sqlalchemy import func
        total = (await db.execute(select(func.count(Artisan.id)))).scalar()
        log.info("Total artisans in DB: %d", total)


async def main():
    parser = argparse.ArgumentParser(description="Extract OSM artisans")
    parser.add_argument("--seed", action="store_true", help="Seed DB after extraction")
    parser.add_argument("--json", default="app/data/osm_artisans.json", help="JSON output path")
    parser.add_argument("--from-json", action="store_true", help="Skip Overpass, load from existing JSON")
    args = parser.parse_args()

    if args.from_json:
        with open(args.json) as f:
            artisans = json.load(f)
        log.info("Loaded %d artisans from %s", len(artisans), args.json)
    else:
        artisans = await fetch_osm_artisans()
        save_to_json(artisans, args.json)

    if args.seed:
        await seed_db(artisans)


if __name__ == "__main__":
    asyncio.run(main())
