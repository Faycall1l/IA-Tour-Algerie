#!/usr/bin/env python3
"""Seed DB from the unified v2 corpus (deduped).

Reads:
    scripts/data/pois_v2_deduped.json
    scripts/data/stays_v2_deduped.json

Behavior:
  - Wipes poi_experiences, pois, stays (CASCADE / RESTART IDENTITY).
  - Maps categories and property types to DB-allowed values.
  - Assigns source/source_id/verified_at from the corpus.
  - Sets default price_per_night_dzd for stays (type-based).
  - Batches inserts.
"""

import asyncio
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import asyncpg


def to_jsonb(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None

DATA = Path(__file__).resolve().parent
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

CATEGORY_MAP: dict[str, str] = {
    "historic": "historical",
    "historical": "historical",
    "museum": "museum",
    "natural": "natural",
    "nature": "natural",
    "park": "park",
    "religious": "religious",
    "religion": "religious",
    "beach": "beach",
    "mountain": "mountain",
    "market": "market",
    "restaurant": "restaurant",
    "cafe": "cafe",
    "food": "restaurant",
    "cultural": "cultural",
    "culture": "cultural",
}

STAY_TYPE_DEFAULT_PRICE: dict[str, float] = {
    "hotel": 6000.0,
    "hostel": 2500.0,
    "guesthouse": 4000.0,
    "apartment": 5000.0,
    "riad": 7000.0,
    "eco_lodge": 8000.0,
}


async def wipe_tourism(conn: asyncpg.Connection) -> None:
    await conn.execute("TRUNCATE TABLE poi_experiences RESTART IDENTITY CASCADE")
    await conn.execute("TRUNCATE TABLE pois RESTART IDENTITY CASCADE")
    await conn.execute("TRUNCATE TABLE stays RESTART IDENTITY CASCADE")


def as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def clean_category(value: str | None) -> str:
    return CATEGORY_MAP.get((value or "").lower().strip(), value or "other")


def clean_stay_type(value: str | None) -> str:
    t = (value or "hotel").lower().strip()
    if t in ("guest_house", "guesthouse"):
        return "guesthouse"
    if t in ("eco_lodge", "ecolodge"):
        return "eco_lodge"
    if t in STAY_TYPE_DEFAULT_PRICE:
        return t
    return "hotel"


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def insert_pois(conn: asyncpg.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = [
        "id",
        "name",
        "name_ar",
        "name_en",
        "category",
        "subtype",
        "wilaya_id",
        "latitude",
        "longitude",
        "description",
        "photo_url",
        "photo_urls",
        "website",
        "phone",
        "opening_hours",
        "operator",
        "cuisine",
        "osm_node_id",
        "osm_type",
        "osm_tags",
        "source",
        "source_id",
        "verified_at",
    ]
    placeholders = ",".join(f"${i + 1}" for i in range(len(cols)))
    stmt = f"INSERT INTO pois ({','.join(cols)}) VALUES ({placeholders})"
    count = 0
    batch = 500
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        await conn.executemany(stmt, [[r[c] for c in cols] for r in chunk])
        count += len(chunk)
        print(f"  POIs inserted: {count}/{len(rows)}", end="\r")
    print()
    return count


async def insert_stays(conn: asyncpg.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = [
        "id",
        "provider_id",
        "name",
        "property_type",
        "description",
        "wilaya_id",
        "address",
        "latitude",
        "longitude",
        "price_per_night_dzd",
        "amenities",
        "photos",
        "check_in_time",
        "check_out_time",
        "max_guests",
        "total_rooms",
        "source",
        "source_id",
        "verified_at",
        "is_active",
    ]
    placeholders = ",".join(f"${i + 1}" for i in range(len(cols)))
    stmt = f"INSERT INTO stays ({','.join(cols)}) VALUES ({placeholders})"
    count = 0
    batch = 500
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        await conn.executemany(stmt, [[r[c] for c in cols] for r in chunk])
        count += len(chunk)
        print(f"  Stays inserted: {count}/{len(rows)}", end="\r")
    print()
    return count


async def seed() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        provider_id = await conn.fetchval(
            "SELECT id FROM users WHERE phone = '+213500000001'"
        )
        if not provider_id:
            provider_id = await conn.fetchval("SELECT id FROM users LIMIT 1")
        print(f"Provider id: {provider_id}")

        await wipe_tourism(conn)
        print("Wiped existing pois/stays/poi_experiences")

        pois_raw = json.loads((DATA / "pois_v2_deduped.json").read_text(encoding="utf-8"))
        stays_raw = json.loads((DATA / "stays_v2_deduped.json").read_text(encoding="utf-8"))
        print(f"Loaded {len(pois_raw)} POIs and {len(stays_raw)} stays")

        poi_rows = []
        for p in pois_raw:
            lat = parse_float(p.get("lat"))
            lng = parse_float(p.get("lng"))
            if lat is None or lng is None:
                continue
            tags = p.get("tags") or {}
            refs = p.get("refs") or {}
            source = p.get("source", "unknown")
            url = p.get("url")
            if source == "tripadvisor" and refs.get("tripadvisor"):
                url = f"https://www.tripadvisor.com/Attraction_Review-g{p.get('geo_id')}-d{refs['tripadvisor']}"
            elif source == "geoalgeria-culture" and p.get("url"):
                url = p["url"]

            name = p.get("name_fr") or p.get("name_en") or ""
            name_en = p.get("name_en") or p.get("name_fr") or ""
            photo_urls = p.get("photo_urls") or []
            poi_rows.append(
                {
                    "id": str(__import__("uuid").uuid4()),
                    "name": name[:200],
                    "name_ar": p.get("name_ar"),
                    "name_en": name_en[:200] if name_en else None,
                    "category": clean_category(p.get("category")),
                    "subtype": (p.get("subtype") or "")[:100],
                    "wilaya_id": p["wilaya_id"],
                    "latitude": lat,
                    "longitude": lng,
                    "description": p.get("description"),
                    "photo_url": photo_urls[0] if photo_urls else None,
                    "photo_urls": photo_urls,
                    "website": url[:300] if url else None,
                    "phone": (tags.get("phone") or None)[:50]
                    if tags.get("phone")
                    else None,
                    "opening_hours": (tags.get("opening_hours") or None)[:200]
                    if tags.get("opening_hours")
                    else None,
                    "operator": (tags.get("operator") or None)[:200]
                    if tags.get("operator")
                    else None,
                    "cuisine": (tags.get("cuisine") or None)[:200]
                    if tags.get("cuisine")
                    else None,
                    "osm_node_id": parse_int(
                        refs.get("osm").split("/")[-1]
                        if refs.get("osm") and str(refs["osm"]).startswith("node/")
                        else None
                    ),
                    "osm_type": str(refs["osm"]).split("/")[0]
                    if refs.get("osm")
                    else None,
                    "osm_tags": to_jsonb(tags) if tags else None,
                    "source": source[:50] if source else None,
                    "source_id": str(p.get("source_id") or "")[:255] or None,
                    "verified_at": as_date(p.get("verified_at")),
                }
            )

        stay_rows = []
        for s in stays_raw:
            lat = parse_float(s.get("lat"))
            lng = parse_float(s.get("lng"))
            if lat is None or lng is None:
                continue
            tags = s.get("tags") or {}
            prop_type = clean_stay_type(s.get("type"))
            amenities = {k: v for k, v in tags.items() if k in ("wifi", "internet_access", "stars", "rooms", "beds", "smoking")}
            stay_rows.append(
                {
                    "id": str(__import__("uuid").uuid4()),
                    "provider_id": provider_id,
                    "name": (s.get("name_fr") or s.get("name_en") or "")[:200],
                    "property_type": prop_type,
                    "description": s.get("description"),
                    "wilaya_id": s["wilaya_id"],
                    "address": (tags.get("address") or tags.get("addr:street") or tags.get("addr:city") or None)[:500]
                    if (tags.get("address") or tags.get("addr:street") or tags.get("addr:city"))
                    else None,
                    "latitude": lat,
                    "longitude": lng,
                    "price_per_night_dzd": STAY_TYPE_DEFAULT_PRICE.get(prop_type, 6000.0),
                    "amenities": list(amenities.keys()) if amenities else None,
                    "photos": s.get("photo_urls") or None,
                    "check_in_time": None,
                    "check_out_time": None,
                    "max_guests": parse_int(tags.get("capacity")),
                    "total_rooms": parse_int(tags.get("rooms")),
                    "source": (s.get("source") or "unknown")[:50],
                    "source_id": str(s.get("source_id") or "")[:255] or None,
                    "verified_at": as_date(s.get("verified_at")),
                    "is_active": True,
                }
            )

        print(f"Prepared {len(poi_rows)} POIs and {len(stay_rows)} stays for insert")
        poi_count = await insert_pois(conn, poi_rows)
        stay_count = await insert_stays(conn, stay_rows)
        print(f"Seeded {poi_count} POIs and {stay_count} stays")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
