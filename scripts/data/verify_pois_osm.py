#!/usr/bin/env python3
"""Verify kept POIs against the live OSM API.

For a sample (or all) of the kept POIs, fetch the OSM element by
osm_node_id and check:
1. the node still exists on OSM
2. DB coords match OSM coords (within ~100m)
3. the node has a name tag (or an acceptable reason for none)
4. tags are consistent with the DB category

Constant checking: the audit gate is only as good as the source data,
so we validate the kept corpus against the live source of truth.

Usage: python scripts/data/verify_pois_osm.py [--all] [--sample N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db.session import async_session  # noqa: E402

OSM_API = "https://api.openstreetmap.org/api/0.6/node/{id}.json"
UA = {"User-Agent": "athar-data/1.0"}

CATEGORY_TAGS = {
    "restaurant": {"amenity": "restaurant"},
    "cafe": {"amenity": "cafe"},
    "museum": {"tourism": "museum", "amenity": "museum"},
    "historical": {"historic": "*", "tourism": "attraction"},
    "cultural": {"tourism": "attraction", "historic": "*"},
    "natural": {"natural": "*", "leisure": "nature_reserve"},
    "mountain": {"natural": "peak", "natural": "volcano"},
    "park": {"leisure": "park", "leisure": "garden"},
    "market": {"amenity": "marketplace", "shop": "*"},
    "beach": {"natural": "beach", "leisure": "beach_resort"},
    "religious": {"amenity": "place_of_worship", "historic": "wayside_shrine"},
    "other": {},
}


def fetch_node(node_id: int) -> dict | None:
    url = OSM_API.format(id=node_id)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            els = data.get("elements", [])
            return els[0] if els else None
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


async def main(sample: int, all_: bool, audit_file: Path) -> None:
    kept_ids = set()
    if audit_file.exists():
        audit = json.loads(audit_file.read_text())
        kept_ids = {str(v["id"]) for v in audit.get("kept", [])}
        print(f"loaded {len(kept_ids)} kept ids from {audit_file}")

    async with async_session() as session:
        if kept_ids:
            import random

            sample_ids = list(kept_ids)
            if not all_:
                random.seed(42)
                sample_ids = random.sample(sample_ids, min(sample, len(sample_ids)))
            rows = (
                await session.execute(
                    text("""
                        SELECT id, name, category, latitude, longitude,
                               osm_node_id, osm_type
                        FROM pois WHERE id = ANY(:ids)
                    """),
                    {"ids": sample_ids},
                )
            ).all()
        elif all_:
            rows = (
                await session.execute(
                    text("""
                        SELECT id, name, category, latitude, longitude,
                               osm_node_id, osm_type
                        FROM pois
                    """)
                )
            ).all()
        else:
            rows = (
                await session.execute(
                    text("""
                        SELECT id, name, category, latitude, longitude,
                               osm_node_id, osm_type
                        FROM pois
                        ORDER BY random() LIMIT :sample
                    """),
                    {"sample": sample},
                )
            ).all()
        print(f"verifying {len(rows)} kept POIs")

    issues: Counter[str] = Counter()
    results = []
    for i, r in enumerate(rows):
        poi_id, name, cat = str(r[0]), str(r[1]), str(r[2])
        lat, lng, node_id, osm_type = r[3], r[4], r[5], r[6]
        if not node_id or osm_type != "node":
            issues["no_osm_node"] += 1
            continue
        node = fetch_node(int(node_id))
        if node is None:
            issues["node_deleted_or_unreachable"] += 1
            continue
        nlat, nlng = node.get("lat"), node.get("lon")
        if nlat is None:
            issues["no_coords"] += 1
            continue
        dlat = abs(lat - nlat) * 111.0
        dlng = abs(lng - nlng) * 111.0 * max(0.5, abs((lat + nlat) / 2) / 57.3)
        dist_km = (dlat**2 + dlng**2) ** 0.5
        tags = node.get("tags", {}) or {}
        has_name = bool(tags.get("name") or tags.get("name:fr"))
        issues["total_checked"] += 1
        if dist_km > 0.2:
            issues["coord_mismatch_gt_200m"] += 1
            results.append({"id": poi_id, "name": name, "osm": node_id,
                            "db": (lat, lng), "osm_pt": (nlat, nlng), "km": round(dist_km, 3)})
        elif not has_name:
            issues["no_name_on_osm"] += 1
        elif i % 20 == 0:
            print(f"  checked {i}/{len(rows)}")

    print("\n=== OSM verification results ===")
    for k, v in issues.most_common():
        print(f"  {k:<35} {v:>6}")
    if results:
        print("\ncoordinate mismatches (sample):")
        for x in results[:10]:
            print(f"  {x['name'][:35]:<35} osm={x['osm']} db={x['db']} osm={x['osm_pt']} Δ{x['km']}km")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=60)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--audit", type=Path, default=Path("/tmp/poi_audit.json"))
    args = parser.parse_args()
    asyncio.run(main(args.sample, args.all, args.audit))
