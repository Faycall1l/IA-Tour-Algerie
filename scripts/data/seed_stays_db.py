#!/usr/bin/env python3
"""Seed stays table from accommodation POIs in poi_nodes_enriched.json.

Extracts hotels, guest_houses, hostels, camp_sites and maps them to the stays table.
Uses the hotel provider user as the provider_id FK.
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
    "postgresql://athar:athar_pass@localhost:5432/athar_db",
)

OSM_TO_PROPERTY_TYPE = {
    "hotel": "hotel",
    "guest_house": "guesthouse",
    "hostel": "hostel",
    "camp_site": "hostel",
    "riad": "riad",
    "eco_lodge": "eco_lodge",
}


def main():
    print("=== Seed stays from accommodation POIs ===\n")

    if not POI_SRC.exists():
        print(f"ERROR: {POI_SRC} not found")
        sys.exit(1)

    pois = json.loads(POI_SRC.read_text())

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Get the hotel provider user
        provider = conn.execute(
            text("SELECT id FROM users WHERE phone = '+213500000001'")
        ).fetchone()
        if not provider:
            print("ERROR: Hotel provider user not found. Run seed_providers.py first.")
            sys.exit(1)
        provider_id = provider[0]
        print(f"Using provider: {provider_id}")

        # Get valid wilayas
        valid_wilayas = {
            row[0]
            for row in conn.execute(text("SELECT id FROM wilayas")).fetchall()
        }

        # Clear existing
        conn.execute(text("TRUNCATE TABLE stays RESTART IDENTITY CASCADE"))

        ACCOMMODATION_TYPES = {"hotel", "guest_house", "hostel", "camp_site"}
        to_insert = []
        for p in pois:
            st = p.get("subtype", "")
            if st not in ACCOMMODATION_TYPES:
                continue
            wid = p.get("wilaya_id")
            if wid not in valid_wilayas:
                continue
            name = p.get("name", "")
            if not name or "(non nommé)" in name:
                continue
            tags = p.get("tags", {})
            prop_type = OSM_TO_PROPERTY_TYPE.get(st, "hotel")
            desc = None
            if tags.get("description"):
                desc = tags["description"]
            elif tags.get("website"):
                desc = f"Site web: {tags['website']}"
            to_insert.append({
                "provider_id": provider_id,
                "name": name[:200],
                "property_type": prop_type,
                "description": desc,
                "wilaya_id": wid,
                "address": tags.get("addr:street") or tags.get("addr:city"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "price_per_night_dzd": 0,
                "amenities": None,
                "photos": None,
                "check_in_time": "14:00",
                "check_out_time": "11:00",
                "max_guests": None,
                "total_rooms": None,
                "is_active": True,
            })

        print(f"Accommodations to seed: {len(to_insert)}")

        BATCH = 500
        inserted = 0
        for i in range(0, len(to_insert), BATCH):
            batch = to_insert[i : i + BATCH]
            conn.execute(
                text("""
                    INSERT INTO stays
                        (id, provider_id, name, property_type, description,
                         wilaya_id, address, latitude, longitude,
                         price_per_night_dzd, amenities, photos,
                         check_in_time, check_out_time,
                         max_guests, total_rooms, is_active)
                    VALUES
                        (gen_random_uuid(), :provider_id, :name, :property_type, :description,
                         :wilaya_id, :address, :latitude, :longitude,
                         :price_per_night_dzd, :amenities, :photos,
                         :check_in_time, :check_out_time,
                         :max_guests, :total_rooms, :is_active)
                """),
                batch,
            )
            inserted += len(batch)
            print(f"  Inserted {inserted}/{len(to_insert)}", end="\r")
            sys.stdout.flush()

    print(f"\n\nDone! Inserted {inserted} stays into database.")


if __name__ == "__main__":
    main()
