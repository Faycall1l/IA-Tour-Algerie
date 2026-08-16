#!/usr/bin/env python3
"""Targeted OSM Overpass extraction for under-covered new wilayas (65, 66, 69).

Extracts tourism POIs within ~40km of each wilaya center via Overpass API,
deduplicates against existing DB POIs, and inserts new ones.
"""

import asyncio
import hashlib
import math

import httpx
from app.db.session import async_session
from sqlalchemy import text

TARGETS = {
    65: (35.4542653, 2.904444, "Ain Ouessara", 0.4),
    66: (34.15429, 3.50309, "Messaad", 0.4),
    69: (32.898611, 0.544444, "El Abiodh Sidi Cheikh", 0.5),
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

QUERY_TEMPLATE = """
[out:json][timeout:60];
(
  node["tourism"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  way["tourism"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["historic"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["amenity"="place_of_worship"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["amenity"="restaurant"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["amenity"="cafe"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["natural"="peak"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["natural"="spring"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
  node["natural"="waterfall"](bbox:{min_lat},{min_lon},{max_lat},{max_lon});
);
out center body;
"""

CATEGORY_MAP = {
    "museum": ("museum", "museum"),
    "attraction": ("historical", "attraction"),
    "artwork": ("cultural", "artwork"),
    "viewpoint": ("natural", "viewpoint"),
    "gallery": ("cultural", "gallery"),
    "hotel": ("restaurant", "hotel"),
    "guest_house": ("restaurant", "guest_house"),
    "hostel": ("restaurant", "hostel"),
    "camp_site": ("natural", "camp_site"),
    "theme_park": ("natural", "theme_park"),
    "zoo": ("natural", "zoo"),
    "information": ("natural", "information"),
    "chalet": ("restaurant", "chalet"),
    "motel": ("restaurant", "motel"),
    "apartment": ("restaurant", "apartment"),
    "caravan_site": ("natural", "caravan_site"),
    "resort": ("restaurant", "resort"),
    "alpine_hut": ("restaurant", "alpine_hut"),
}

HISTORIC_MAP = {
    "castle": ("historical", "castle"),
    "ruins": ("historical", "ruins"),
    "archaeological_site": ("historical", "archaeological"),
    "memorial": ("historical", "memorial"),
    "monument": ("historical", "monument"),
    "fort": ("historical", "fort"),
    "tower": ("historical", "tower"),
    "mosque": ("religious", "historic_mosque"),
    "mausoleum": ("historical", "mausoleum"),
    "tomb": ("historical", "tomb"),
    "wayside_shrine": ("religious", "wayside_shrine"),
    "wayside_cross": ("religious", "wayside_cross"),
    "ship": ("historical", "ship"),
    "yes": ("historical", "historic"),
}


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def classify(tags):
    a = tags.get("amenity")
    if a in ("restaurant", "fast_food"):
        return "restaurant", "restaurant"
    if a == "cafe":
        return "cafe", "cafe"
    if a == "place_of_worship":
        return "religious", f"religion/{tags.get('religion', 'unknown')}"
    h = tags.get("historic")
    if h:
        return HISTORIC_MAP.get(h, ("historical", f"historic/{h}"))
    t = tags.get("tourism")
    if t:
        return CATEGORY_MAP.get(t, ("natural", t))
    n = tags.get("natural")
    if n:
        if n in ("peak", "hill", "volcano", "cliff", "dune", "ridge"):
            return "mountain", n
        return "natural", n
    return "other", "other"


def make_source_id(lat, lon, tags):
    key = f"{lat:.6f},{lon:.6f},{tags.get('name', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


async def extract_wilaya(client, wilaya_id, lat, lon, _name, radius):
    bbox = {
        "min_lat": lat - radius,
        "max_lat": lat + radius,
        "min_lon": lon - radius,
        "max_lon": lon + radius,
    }
    query = QUERY_TEMPLATE.format(**bbox)

    resp = await client.post(OVERPASS_URL, data={"data": query}, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    new_pois = []
    for elem in data.get("elements", []):
        tags = elem.get("tags", {})
        if not tags.get("name"):
            continue
        elat = elem.get("lat") or elem.get("center", {}).get("lat")
        elon = elem.get("lon") or elem.get("center", {}).get("lon")
        if not elat or not elon:
            continue
        d = haversine(lat, lon, elat, elon)
        if d > 40:
            continue
        category, subtype = classify(tags)
        source_id = make_source_id(elat, elon, tags)
        new_pois.append(
            {
                "name": tags.get("name", "Unknown"),
                "name_en": tags.get("name:en"),
                "name_ar": tags.get("name:ar"),
                "category": category,
                "subtype": subtype,
                "latitude": elat,
                "longitude": elon,
                "wilaya_id": wilaya_id,
                "description": tags.get("description", ""),
                "source": "osm",
                "source_id": source_id,
                "osm_node_id": elem.get("id"),
            }
        )

    return new_pois


async def main():
    async with async_session() as db:
        async with httpx.AsyncClient(headers={"User-Agent": "ATHAR/1.0 (travel-guide)"}) as client:
            total_inserted = 0
            for wilaya_id, (lat, lon, name, radius) in TARGETS.items():
                # Get existing POIs in this wilaya within 5km
                existing = await db.execute(
                    text("""
                    SELECT latitude, longitude, name FROM pois
                    WHERE wilaya_id = :wid
                """),
                    {"wid": wilaya_id},
                )
                existing_set = {
                    (round(r[0], 4), round(r[1], 4), r[2].lower().strip()) for r in existing
                }

                print(f"\nQuerying Overpass for w{wilaya_id} {name}...")
                new_pois = await extract_wilaya(client, wilaya_id, lat, lon, name, radius)
                print(f"  Found {len(new_pois)} POIs with names")

                # Dedup against existing
                to_insert = []
                for poi in new_pois:
                    key = (
                        round(poi["latitude"], 4),
                        round(poi["longitude"], 4),
                        poi["name"].lower().strip(),
                    )
                    if key not in existing_set:
                        to_insert.append(poi)
                        existing_set.add(key)

                if to_insert:
                    for poi in to_insert:
                        await db.execute(
                            text("""
                            INSERT INTO pois
                            (id, name, name_en, name_ar, category, subtype,
                             latitude, longitude, wilaya_id, description,
                             source, source_id, osm_node_id,
                             is_featured, entry_fee_dzd,
                             suggested_duration_min, price_level,
                             ranking_position, ranking_total)
                            VALUES (gen_random_uuid(),
                                    :name, :name_en, :name_ar,
                                    :category, :subtype,
                                    :latitude, :longitude,
                                    :wilaya_id, :description,
                                    :source, :source_id, :osm_node_id,
                                    false, 0, 30, 'free', 0, 0)
                        """),
                            poi,
                        )
                    await db.commit()
                    total_inserted += len(to_insert)
                    cats = {}
                    for p in to_insert:
                        cats[p["category"]] = cats.get(p["category"], 0) + 1
                    print(f"  Inserted {len(to_insert)} new POIs: {cats}")
                else:
                    print("  0 new POIs (all duplicates or no data)")

                await asyncio.sleep(2)  # Rate limit

            # Verify final counts
            for wilaya_id, (_, _, name, _) in TARGETS.items():
                result = await db.execute(
                    text("""
                    SELECT COUNT(*) FROM pois WHERE wilaya_id = :wid
                """),
                    {"wid": wilaya_id},
                )
                cnt = result.scalar()
                print(f"w{wilaya_id:2d} {name:30s}  {cnt:5d} POIs")

            print(f"\nTotal inserted: {total_inserted}")


if __name__ == "__main__":
    asyncio.run(main())
