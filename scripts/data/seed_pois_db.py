#!/usr/bin/env python3
"""Seed the pois table from poi_nodes_enriched.json.

Maps OSM subtypes → POI DB categories. Skips accommodation types
(hotel, guest_house, hostel, camp_site) which go to the stays table.
"""

import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent
POI_SRC = ROOT / "app" / "data" / "poi_nodes_enriched.json"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

OSM_TO_DB_CATEGORY = {
    "hotel": None,
    "guest_house": None,
    "hostel": None,
    "camp_site": None,
    "museum": "museum",
    "archaeological_site": "historical",
    "monument": "historical",
    "memorial": "historical",
    "ruins": "historical",
    "castle": "historical",
    "fort": "historical",
    "battlefield": "historical",
    "artwork": "cultural",
    "attraction": "cultural",
    "theatre": "cultural",
    "cinema": "cultural",
    "library": "cultural",
    "place_of_worship": "religious",
    "beach": "beach",
    "peak": "mountain",
    "cave": "natural",
    "waterfall": "natural",
    "volcano": "natural",
    "bay": "natural",
    "viewpoint": "natural",
    "park": "park",
    "garden": "park",
    "nature_reserve": "natural",
    "restaurant": "restaurant",
    "cafe": "cafe",
    "fast_food": "restaurant",
    "pub": "cafe",
    "bar": "cafe",
    "supermarket": "market",
    "mall": "market",
    "souvenir_shop": "market",
    "gift_shop": "market",
    "marketplace": "market",
    "sports_centre": "other",
    "stadium": "other",
    "marina": "other",
    "lighthouse": "other",
    "tower": "other",
    "observatory": "other",
    "information": "other",
    "yes": "other",
}

ACCOMMODATION_TYPES = {"hotel", "guest_house", "hostel", "camp_site"}


def map_category(subtype, tags):
    db_cat = OSM_TO_DB_CATEGORY.get(subtype)
    if db_cat is not None:
        return db_cat
    if subtype.startswith("tourism_"):
        return "cultural"
    if subtype.startswith("historic_"):
        return "historical"
    if subtype.startswith("amenity_"):
        return "other"
    return "other"


def build_description(poi):
    parts = []
    if poi.get("opening_hours"):
        parts.append(f"Horaires: {poi['opening_hours']}")
    tags = poi.get("tags", {})
    if tags.get("historic:civilization"):
        parts.append(f"Civilisation: {tags['historic:civilization']}")
    if tags.get("historic:period"):
        parts.append(f"Période: {tags['historic:period']}")
    if tags.get("ele"):
        parts.append(f"Altitude: {tags['ele']}m")
    if tags.get("description"):
        parts.append(tags["description"])
    if tags.get("wikidata"):
        parts.append(f"Wikidata: {tags['wikidata']}")
    return " | ".join(parts) if parts else None


def main():
    print("=== Seed POIs into database ===\n")

    if not POI_SRC.exists():
        print(f"ERROR: {POI_SRC} not found")
        sys.exit(1)

    pois = json.loads(POI_SRC.read_text())
    print(f"Loaded {len(pois)} POI nodes")

    engine = create_engine(DATABASE_URL)

    # Check which wilayas exist
    with engine.connect() as conn:
        existing = set(
            row[0]
            for row in conn.execute(text("SELECT id FROM wilayas")).fetchall()
        )
    print(f"Wilayas in DB: {len(existing)}")

    skipped_hotels = 0
    inserted = 0
    errors = 0
    skipped_no_wilaya = 0

    # Remove accommodations that go to stays table
    to_insert = []
    for p in pois:
        subtype = p.get("subtype", "other")
        if subtype in ACCOMMODATION_TYPES:
            skipped_hotels += 1
            continue
        if p["wilaya_id"] not in existing:
            skipped_no_wilaya += 1
            continue
        db_cat = map_category(subtype, p.get("tags", {}))
        to_insert.append((p, db_cat))

    print(f"To insert in pois: {len(to_insert)}")
    print(f"Skipped (accommodation → stays table): {skipped_hotels}")
    print(f"Skipped (missing wilaya): {skipped_no_wilaya}")

    BATCH = 1000
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE pois RESTART IDENTITY CASCADE"))
        for i in range(0, len(to_insert), BATCH):
            batch = to_insert[i : i + BATCH]
            rows = []
            for p, db_cat in batch:
                rows.append({
                    "name": p.get("name", "Sans nom")[:200],
                    "category": db_cat,
                    "wilaya_id": p["wilaya_id"],
                    "latitude": p.get("latitude"),
                    "longitude": p.get("longitude"),
                    "description": build_description(p),
                    "entry_fee_dzd": None,
                    "photo_url": None,
                })
            conn.execute(
                text("""
                    INSERT INTO pois
                        (id, name, category, wilaya_id, latitude, longitude,
                         description, entry_fee_dzd, photo_url)
                    VALUES
                        (gen_random_uuid(), :name, :category, :wilaya_id, :latitude, :longitude,
                         :description, :entry_fee_dzd, :photo_url)
                """),
                rows,
            )
            inserted += len(rows)
            print(f"  Inserted {inserted}/{len(to_insert)}", end="\r")
            sys.stdout.flush()

    print(f"\n\nDone! Inserted {inserted} POIs into database.")


if __name__ == "__main__":
    main()
