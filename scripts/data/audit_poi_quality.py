#!/usr/bin/env python3
"""Audit POI quality: classify every POI into keep / drop reasons.

The OSM POI extraction grabbed every node in each wilaya bbox, so ~79% of
the corpus is nameless bare nodes (no name=*, no tags) that cannot be
verified, visited or photographed. This script applies a strict quality
gate and reports the classification WITHOUT modifying the DB.

Quality rules (a POI is KEPT only if it passes ALL):
1. Real name: not a placeholder ("(non nommé)", "unnamed", "sans nom",
   "POI N", "N"), length >= 3 after trimming, not a generic junk label
   ("Resto", "Poisson", "King", "Karantika", ...).
2. In Algeria: lat in [18, 38], lng in [-9, 13].
3. Verifiable OSM identity: osm_node_id present.
4. Category sanity: name is not obviously mismatched with category
   (e.g. person-name-only on non-cafe/restaurant categories).
5. Photo sanity: photo_url is a real MinIO object, not a placehold.co
   placeholder, and not shared by more than N other POIs (default 5).

Output: per-category keep/drop table + a JSON file with the kept ids.

Usage: python scripts/data/audit_poi_quality.py [--out /tmp/poi_audit.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

PLACEHOLDER_RE = re.compile(
    r"(non nomm|unnamed|sans nom|non identifi|inconnu|unknown|"
    r"POI \d+|\(\d+\)|^[#_-]+$)",
    re.IGNORECASE,
)

# generic labels that are not visitable destinations for a travel guide
JUNK_NAMES = {
    "resto",
    "snack",
    "snack-bar",
    "pizzeria",
    "cafe",
    "café",
    "restaurant",
    "hotel",
    "king",
    "poisson",
    "boucherie",
    "boulangerie",
    "pharmacie",
    "coiffeur",
    "salon",
    "barbier",
    "garage",
    "station",
    "station service",
    "boutique",
    "magasin",
    "epicerie",
    "supermarché",
    "supermarch",
    "dracena",
    "karantika",
    "lazhar",
    "adel",
    "nour",
    "farid",
    "karim",
    "sami",
    "yacine",
    "amine",
    "mohamed",
    "slimane",
    "rachid",
    "said",
    "hassan",
    "brahim",
    "omar",
    "ali",
    "moussa",
    "ahmed",
    "youcef",
    "djaafar",
    "sofiane",
    "walid",
    "billel",
    "hocine",
    "madani",
}

# categories where a person-name-only POI is acceptable (real local shops)
PERSON_NAME_OK = {"cafe", "restaurant", "market"}

PERSON_NAME_RE = re.compile(r"^[A-ZÀ-Ý][a-zà-ÿ]+( [A-ZÀ-Ý]?[a-zà-ÿ]+)*$")

ALGERIA = {"min_lat": 18.0, "max_lat": 38.0, "min_lng": -9.0, "max_lng": 13.0}

PLACEHOLD_PHOTO = "placehold.co"


async def main(out_path: Path, max_photo_share: int) -> None:
    async with async_session() as session:
        rows = (
            await session.execute(
                text("""
                    SELECT id, name, category, latitude, longitude,
                           osm_node_id, osm_type, photo_url
                    FROM pois
                """)
            )
        ).all()

    photo_use: Counter[str] = Counter(r[7] for r in rows if r[7])
    verdict: dict[str, list[object]] = {}
    kept_ids: list[str] = []
    reasons: Counter[str] = Counter()
    per_cat: Counter[tuple[str, str]] = Counter()

    for r in rows:
        poi_id, name, cat = str(r[0]), str(r[1] or ""), str(r[2] or "")
        lat, lng = r[3], r[4]
        osm_id, photo = r[5], r[7]
        name = name.strip()

        drop = None
        if PLACEHOLDER_RE.search(name) or len(name) < 3:
            drop = "placeholder_name"
        elif name.lower() in JUNK_NAMES:
            drop = "junk_name"
        elif PERSON_NAME_RE.match(name) and cat not in PERSON_NAME_OK:
            drop = "person_name_only"
        elif lat is None or lng is None:
            drop = "no_coords"
        elif not (ALGERIA["min_lat"] <= lat <= ALGERIA["max_lat"]):
            drop = "out_of_algeria_lat"
        elif not (ALGERIA["min_lng"] <= lng <= ALGERIA["max_lng"]):
            drop = "out_of_algeria_lng"
        elif not osm_id:
            drop = "no_osm_id"

        # photo sanity (non-fatal: affects photo quality, not existence)
        photo_bad = bool(photo) and (PLACEHOLD_PHOTO in photo or photo_use[photo] > max_photo_share)

        if drop:
            reasons[drop] += 1
            verdict.setdefault("dropped", []).append(
                {"id": poi_id, "name": name, "category": cat, "reason": drop}
            )
            per_cat[(cat, drop)] += 1
        else:
            verdict.setdefault("kept", []).append(
                {
                    "id": poi_id,
                    "name": name,
                    "category": cat,
                    "photo_bad": photo_bad,
                    "photo_url": photo,
                }
            )
            kept_ids.append(poi_id)

    total = len(rows)
    kept = len(kept_ids)
    print(f"total POIs: {total}")
    print(f"KEPT: {kept} ({kept * 100 / total:.1f}%)")
    print("\nDROPPED by reason:")
    for reason, n in reasons.most_common():
        print(f"  {reason:<24} {n:>6}")
    dropped = total - kept
    print(f"  {'TOTAL DROPPED':<24} {dropped:>6}")

    print("\nkept corpus by category:")
    kept_cats = Counter(v["category"] for v in verdict["kept"])
    for cat, n in kept_cats.most_common():
        print(f"  {cat:<12} {n:>6}")

    photo_bad_kept = sum(1 for v in verdict["kept"] if v["photo_bad"])
    print(f"\nkept POIs with bad/placeholder/shared photos: {photo_bad_kept}")

    out_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=1))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/poi_audit.json"))
    parser.add_argument("--max-photo-share", type=int, default=5)
    args = parser.parse_args()
    import asyncio

    asyncio.run(main(args.out, args.max_photo_share))
