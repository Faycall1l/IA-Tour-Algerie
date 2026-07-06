#!/usr/bin/env python3
"""Import scraped SNTF stations + old non-SNTF stations into the DB.

Usage:
  python scripts/import_sntf_seed.py [--dry-run]
"""

import json
import uuid
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.models.station import Station, TransportLine, LineStop
from app.database import SessionLocal
from app.data.transport_stations import STATIONS_SEED as OLD_STATIONS


LINE_COLORS = {
    "train": "#E53935",
    "metro": "#1E88E5",
    "tram": "#43A047",
    "bus": "#FB8C00",
    "airport": "#8E24AA",
    "ferry": "#00ACC1",
    "flight": "#1565C0",
    "cablecar": "#FF6F00",
    "taxi": "#757575",
}

TYPE_MAP = {
    "train": "train",
    "metro": "metro",
    "tram": "tram",
    "bus": "bus",
    "airport": "airport",
    "ferry": "ferry",
    "flight": "airport",
    "cablecar": "cablecar",
    "taxi": "taxi",
}


def main(dry_run=False):
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Importing transport seed data...")

    # ── Read new SNTF stations ──
    with open(ROOT / "app" / "data" / "sntf_seed_complete.json") as f:
        sntf_data = json.load(f)
    sntf_stations = sntf_data["stations"]
    sntf_lines = sntf_data["lines"]

    print(f"  New SNTF stations: {len(sntf_stations)}")
    print(f"  New SNTF lines: {len(sntf_lines)}")

    # ── Read old non-SNTF stations ──
    old_non_sntf = []
    for s in OLD_STATIONS:
        typ = s.get("type", "")
        if typ == "train" and s.get("operator") == "SNTF":
            continue  # replaced by new scraper data
        old_non_sntf.append(s)

    print(f"  Old non-SNTF stations kept: {len(old_non_sntf)}")

    # ── Build station list ──
    all_stations = []
    seen_names = set()

    skipped_no_coords = 0
    for s in sntf_stations:
        name = s.get("name_clean", s.get("name", "")).strip()
        if not name:
            continue
        lat, lng = s.get("lat"), s.get("lng")
        if lat is None or lng is None:
            skipped_no_coords += 1
            continue  # skip stations without coordinates
        key = name.lower().replace("(", "").replace(")", "").replace("'", "").replace("-", " ").strip()
        if key in seen_names:
            skipped_no_coords += 1
            continue
        seen_names.add(key)
        all_stations.append({
            "name": name,
            "station_type": "train",
            "operator": "SNTF",
            "lat": lat,
            "lng": lng,
            "wilaya_id": s.get("wilaya_id"),
        })
    if skipped_no_coords:
        print(f"  Skipped {skipped_no_coords} SNTF stations without coordinates")

    # Track how many old names we skip as dupes
    old_skipped = 0
    old_no_coords = 0
    for s in old_non_sntf:
        name = s.get("name", "").strip()
        if not name:
            continue
        lat, lng = s.get("lat"), s.get("lng")
        if lat is None or lng is None:
            old_no_coords += 1
            continue  # skip without coords
        key = name.lower().replace("(", "").replace(")", "").replace("'", "").replace("-", " ").strip()
        if key in seen_names:
            old_skipped += 1
            continue
        seen_names.add(key)

        # Map old "type" -> "station_type"
        typ = TYPE_MAP.get(s.get("type", ""), s.get("type", ""))
        all_stations.append({
            "name": name,
            "station_type": typ,
            "operator": s.get("operator", typ.upper() if typ != "tram" else "EMAC") or "",
            "lat": lat,
            "lng": lng,
            "wilaya_id": s.get("wilaya_id"),
        })
    if old_no_coords:
        print(f"  Skipped {old_no_coords} old stations without coordinates")

    print(f"  Old non-SNTF skipped (name clash): {old_skipped}")
    print(f"  Total stations: {len(all_stations)}")

    types = Counter(s["station_type"] for s in all_stations)
    print(f"  By type: {dict(types)}")

    if dry_run:
        return

    # ── DB import ──
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM line_stops"))
        db.execute(text("DELETE FROM transport_lines"))
        db.execute(text("DELETE FROM stations"))
        db.commit()
        print("  Cleared existing transport data")

        # Insert stations
        station_name_to_id = {}
        for s in all_stations:
            st = Station(
                id=str(uuid.uuid4()),
                name=s["name"],
                station_type=s["station_type"],
                operator=s["operator"],
                latitude=s["lat"],
                longitude=s["lng"],
                wilaya_id=s["wilaya_id"],
                is_active=True,
            )
            db.add(st)
            db.flush()
            key = s["name"].lower().replace("(", "").replace(")", "").replace("'", "").replace("-", " ").strip()
            station_name_to_id[key] = st.id

        print(f"  Inserted {len(all_stations)} stations")

        # Insert lines
        for ld in sntf_lines:
            tl = TransportLine(
                id=str(uuid.uuid4()),
                name=ld["name"],
                operator=ld.get("operator", "SNTF"),
                mode=ld.get("mode", "train"),
                color=ld.get("color", LINE_COLORS.get(ld.get("mode", "train"), "#666")),
                description=ld.get("description", ""),
                is_active=True,
            )
            db.add(tl)
            db.flush()
            line_id = tl.id

            for order, stop_name in enumerate(ld["stops"]):
                key = stop_name.lower().replace("(", "").replace(")", "").replace("'", "").replace("-", " ").strip()
                sid = station_name_to_id.get(key)
                if not sid:
                    print(f"  WARNING: stop '{stop_name}' not found for line '{ld['name']}'")
                    continue
                ls = LineStop(
                    id=str(uuid.uuid4()),
                    line_id=line_id,
                    station_id=sid,
                    stop_order=order + 1,
                )
                db.add(ls)

        db.commit()
        print(f"  Inserted {len(sntf_lines)} lines with stops")

        # Summary
        print(f"\n{'='*50}")
        print(f"IMPORT COMPLETE")
        print(f"{'='*50}")
        print(f"  Stations: {len(all_stations)}")
        print(f"  Lines: {len(sntf_lines)}")
        print(f"  Types: {dict(types)}")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
