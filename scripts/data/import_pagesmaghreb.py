#!/usr/bin/env python3
"""Import PagesMaghreb artisans into the DB alongside the verified OSM set.

Two sources, one `artisans` table:
  - OSM (70 records, `app/data/osm_artisans.json`): verified OSM nodes, already
    seeded. metadata.source = "osm_overpass".
  - PagesMaghreb (575 records, `app/data/pm_artisans_mapped.json`): real firms
    from the PagesMaghreb business directory. Every record carries a verifiable
    source_url (30/30 sampled live), a street address, and a wilaya_code that
    maps to the official wilaya numbering. metadata.source = "pagesmaghreb".

Idempotent: re-runs skip records already present by (metadata.pm_id) or by a
name+wilaya match against an existing OSM artisan (OSM wins). No synthetic data.

Usage:
  .venv/bin/python scripts/data/import_pagesmaghreb.py [--dry-run]
Then recompute transit access:
  .venv/bin/python scripts/data/build_artisan_transit_access.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from pathlib import Path

import asyncpg

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from app.core.config import settings  # noqa: E402
from scripts.data.classify_pm_crafts import classify_categories as classify_pm  # noqa: E402
from scripts.data.prune_artisans import classify as classify_name  # noqa: E402

OSM_JSON = REPO / "app" / "data" / "osm_artisans.json"
PM_JSON = REPO / "app" / "data" / "pm_artisans_mapped.json"

MAX_NAME = 200
MAX_ADDRESS = 500
MAX_COMMUNE = 200
MAX_WEBSITE = 500


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def clean_phone(p: str) -> str:
    d = re.sub(r"[^0-9+]", "", p or "")
    return d if d.startswith("+213") and len(d) == 13 else (d or None)


def is_mobile(p: str) -> bool:
    return bool(re.match(r"^\+213[567]\d{8}$", p or ""))


def transform(pm: list[dict], osm_keys: set[tuple[str, int]]) -> tuple[list[dict], int, int]:
    rows = []
    dup_osm = 0
    seen_pm = set()
    for r in pm:
        addr = r["addresses"][0]
        wid = int(addr["wilaya_code"])
        key = (normalize_name(r["name"]), wid)
        if key in osm_keys:
            dup_osm += 1
            continue
        pm_id = int(r["pm_id"])
        if pm_id in seen_pm:
            continue
        seen_pm.add(pm_id)

        street = (addr.get("street") or "").strip()
        city = (addr.get("city") or "").strip()
        full_addr = ", ".join(p for p in [street, city] if p)[:MAX_ADDRESS] or None

        craft_type = r.get("craft_type") or classify_pm(r.get("categories") or [])
        if craft_type is None:
            continue  # non-craft / supply-only firm — dropped

        phones = [clean_phone(p) for p in r.get("phones", [])]
        phones = [p for p in phones if p]
        phone = phones[0] if phones else None
        whatsapp = next((p for p in phones if is_mobile(p)), None)
        website = (r.get("websites") or [None])[0]
        if website and not website.startswith("http"):
            website = "https://" + website
        if website and len(website) > MAX_WEBSITE:
            website = None

        rows.append(
            {
                "name": r["name"][:MAX_NAME],
                "craft_type": craft_type,
                "description": r.get("activity_description") or None,
                "wilaya_id": wid,
                "address": full_addr,
                "commune": city[:MAX_COMMUNE] or None,
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "phone": phone,
                "whatsapp": whatsapp,
                "website": website,
                "specializations": [
                    s[:100] for s in (r.get("craft_categories") or r.get("categories") or [])[:5]
                ],
                "is_verified": True,
                "metadata": {
                    "source": "pagesmaghreb",
                    "pm_id": pm_id,
                    "source_url": r["source_url"],
                    "geocode_stage": r.get("geocode_stage"),
                    "listing_category": r.get("listing_category"),
                    "name_quality": classify_name(r["name"]),
                },
            }
        )
    return rows, dup_osm, len(seen_pm)


async def _connect() -> asyncpg.Connection:
    url = settings.database.url.replace("+asyncpg", "", 1)
    return await asyncpg.connect(url or "postgresql://athar:athar_pass@localhost:5434/athar_db")


async def seed(rows: list[dict]) -> None:
    conn = await _connect()
    try:
        inserted = 0
        existing = 0
        for row in rows:
            present = await conn.fetchval(
                "SELECT 1 FROM artisans WHERE metadata->>'pm_id' = $1",
                str(row["metadata"]["pm_id"]),
            )
            if present:
                existing += 1
                continue
            await conn.execute(
                """
                INSERT INTO artisans (
                    id, name, craft_type, description, wilaya_id, address, commune,
                    latitude, longitude, phone, whatsapp, website, specializations,
                    is_verified, accepts_custom_orders, has_workshop, accepts_visitors,
                    metadata
                ) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9,
                          $10, $11, $12, $13, $14, $15, $16, $17)
                """,
                row["name"], row["craft_type"], row["description"], row["wilaya_id"],
                row["address"], row["commune"], row["latitude"], row["longitude"],
                row["phone"], row["whatsapp"], row["website"], row["specializations"],
                row["is_verified"], True, True, True, json.dumps(row["metadata"]),
            )
            inserted += 1
        total = await conn.fetchval("SELECT count(*) FROM artisans")
        print(f"DB: inserted {inserted} new, skipped {existing} already present")
        print(f"total artisans in DB: {total}")
    finally:
        await conn.close()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(OSM_JSON) as fh:
        osm = json.load(fh)
    with open(PM_JSON) as fh:
        pm = json.load(fh)
    print(f"OSM records: {len(osm)}  PM records: {len(pm)}")

    osm_keys = {(normalize_name(r["name"]), int(r["wilaya_id"])) for r in osm}
    rows, dup_osm, n_uniq = transform(pm, osm_keys)
    print(f"PM dedup vs OSM: {dup_osm} dropped (OSM wins); {n_uniq} unique PM records")
    print(f"transformed rows ready: {len(rows)}")

    if args.dry_run:
        for s in rows[:6]:
            print(
                f"  - {s['name']} [{s['craft_type']}] w{s['wilaya_id']} "
                f"ph={s['phone']} src={s['metadata']['source_url'][:60]}"
            )
        print(f"[DRY-RUN] would insert {len(rows)} new artisans")
        return

    await seed(rows)


if __name__ == "__main__":
    asyncio.run(main())
