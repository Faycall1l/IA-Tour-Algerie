#!/usr/bin/env python3
"""Enrich stays with amenities, photos, descriptions, and room data.

Based on property type and wilaya, assigns realistic amenities,
placeholder photos, check-in/out times, and enriched descriptions.

Usage:
    python -m scripts.data.enrich_stays
    python -m scripts.data.enrich_stays --dry-run
"""

import random
from argparse import ArgumentParser

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://athar:athar_pass@localhost:5432/athar_db"

# Amenities by property type
AMENITIES_BY_TYPE = {
    "hotel": [
        ["wifi", "air_conditioning", "tv", "parking", "restaurant", "room_service", "24h_reception"],
        ["wifi", "air_conditioning", "tv", "pool", "spa", "gym", "parking"],
        ["wifi", "air_conditioning", "minibar", "safe", "laundry", "parking", "restaurant"],
    ],
    "hostel": [
        ["wifi", "kitchen", "laundry", "common_area", "lockers"],
        ["wifi", "kitchen", "garden", "common_area", "bicycle_rental"],
        ["wifi", "shared_kitchen", "terrace", "laundry", "tv_room"],
    ],
    "guesthouse": [
        ["wifi", "garden", "breakfast", "terrace", "parking"],
        ["wifi", "breakfast", "garden", "kitchen", "laundry"],
        ["wifi", "terrace", "breakfast", "parking", "air_conditioning"],
    ],
}

# Check-in/out by type
CHECK_IN_OUT = {
    "hotel": ("14:00", "12:00"),
    "hostel": ("12:00", "10:00"),
    "guesthouse": ("13:00", "11:00"),
}

# Room ranges by type
ROOM_RANGES = {
    "hotel": (20, 200),
    "hostel": (8, 60),
    "guesthouse": (3, 15),
}

# Color codes for placeholder photos by property type
PHOTO_COLORS = {
    "hotel": ["2563EB", "1E40AF", "DC2626", "B91C1C", "7C3AED"],
    "hostel": ["059669", "047857", "D97706", "D97706", "2563EB"],
    "guesthouse": ["B45309", "92400E", "059669", "047857", "DC2626"],
}

WILAYA_NAMES = {}


def generate_description(name: str, prop_type: str, wilaya_id: int, amenities: list[str]) -> str:
    wilaya = WILAYA_NAMES.get(wilaya_id, f"wilaya {wilaya_id}")

    type_desc = {
        "hotel": "cet hôtel",
        "hostel": "cet hostel",
        "guesthouse": "cette maison d'hôtes",
    }
    td = type_desc.get(prop_type, "cet établissement")

    parts = [f"{td.capitalize()} situé à {wilaya}."]

    if "pool" in amenities:
        parts.append("Profitez de la piscine pour vous détendre après une journée de visites.")
    if "restaurant" in amenities:
        parts.append("Un restaurant sur place vous propose une cuisine locale raffinée.")
    if "spa" in amenities:
        parts.append("Le spa et le centre de bien-être offrent des soins relaxants.")
    if "garden" in amenities or "terrace" in amenities:
        parts.append("Un jardin ou une terrasse vous invite à la détente en plein air.")
    if "wifi" in amenities:
        parts.append("WiFi gratuit dans tout l'établissement.")
    if "breakfast" in amenities:
        parts.append("Un petit-déjeuner copieux est inclus chaque matin.")
    if "kitchen" in amenities or "shared_kitchen" in amenities:
        parts.append("Une cuisine équipée est à votre disposition.")

    parts.append("Idéalement situé pour explorer les merveilles de l'Algérie.")

    return " ".join(parts)


def enrich_stays(dry_run: bool = False):
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Load wilaya names
        global WILAYA_NAMES
        for r in conn.execute(text("SELECT id, name_en FROM wilayas")).fetchall():
            WILAYA_NAMES[r[0]] = r[1]

        stays = conn.execute(text("""
            SELECT id, name, property_type, wilaya_id, amenities, photos,
                   description, total_rooms, check_in_time, check_out_time
            FROM stays
            ORDER BY id
        """)).fetchall()

        print(f"Processing {len(stays)} stays...")

        updated = 0
        for row in stays:
            sid = row[0]
            name = row[1]
            ptype = row[2]
            wid = row[3]
            existing_amenities = row[4]
            existing_photos = row[5]
            existing_desc = row[6]
            existing_rooms = row[7]

            # Generate amenities if missing
            if not existing_amenities:
                amenity_pool = AMENITIES_BY_TYPE.get(ptype, AMENITIES_BY_TYPE["guesthouse"])
                amenities = random.choice(amenity_pool)
            else:
                amenities = existing_amenities

            # Generate placeholder photos if missing
            if not existing_photos:
                color = random.choice(PHOTO_COLORS.get(ptype, ["2563EB"]))
                safe_name = name.replace(" ", "+")[:30]
                photos = [
                    f"https://placehold.co/600x400/{color}/FFFFFF?text={safe_name}"
                ]
            else:
                photos = existing_photos

            # Generate description if missing/short
            if not existing_desc or len(existing_desc) < 30:
                description = generate_description(name, ptype, wid, amenities)
            else:
                description = existing_desc

            # Generate total_rooms if missing
            if not existing_rooms:
                lo, hi = ROOM_RANGES.get(ptype, (5, 30))
                total_rooms = random.randint(lo, hi)
            else:
                total_rooms = existing_rooms

            # Check-in/out
            ci, co = CHECK_IN_OUT.get(ptype, ("14:00", "11:00"))

            if dry_run:
                print(f"  [dry-run] {name} ({ptype}): {len(amenities)} amenities, {len(photos)} photos, {total_rooms} rooms")
                continue

            conn.execute(
                text("""
                    UPDATE stays SET
                        amenities = :amenities,
                        photos = :photos,
                        description = :description,
                        total_rooms = :total_rooms,
                        check_in_time = :check_in,
                        check_out_time = :check_out
                    WHERE id = :id
                """),
                {
                    "id": sid,
                    "amenities": amenities,
                    "photos": photos,
                    "description": description,
                    "total_rooms": total_rooms,
                    "check_in": ci,
                    "check_out": co,
                },
            )
            updated += 1

        print(f"\nUpdated {updated} stays")


def main():
    parser = ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    enrich_stays(dry_run=args.dry_run)
    engine = create_engine(DATABASE_URL)
    engine.dispose()


if __name__ == "__main__":
    main()
