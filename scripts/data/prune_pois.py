#!/usr/bin/env python3
"""Prune POIs to a curated tourism set for the demo (quality over quantity).

Keeps:
  - tourism categories: historical, cultural, museum, natural, mountain,
    beach, park, market
  - religious: has a real photo OR a notable-name pattern (grande/kebir/
    basilique/cathedrale/synagogue/abbaye/historique/ancien/sidi/saint/...)
  - restaurant/cafe: has a real photo (someone documented it -> notable)

Drops:
  - placeholder/unnamed names (points that map to nothing)
  - bad coordinates (0,0 or NULL)
  - everything else not matching the above

Dropped rows are backed up to scripts/data/reports/pruned_pois.json before
deletion (reversible). poi_experiences rows pointing at dropped POIs are
removed first (the FK would otherwise block the delete).

Usage:
  python scripts/data/prune_pois.py            # dry-run: report only
  python scripts/data/prune_pois.py --apply    # apply to the DB
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

TOURISM_CATEGORIES = {
    "historical", "cultural", "museum", "natural",
    "mountain", "beach", "park", "market",
}

NOTABLE_RELIGIOUS = re.compile(
    r"grande|kebir|great|basilique|basilica|cath[ée]drale|synagogue|abbaye|"
    r"abbey|historique|historic|ancien|ancienne|sidi|saint|mus[eé]e|mausol"
    r"[ée]e|marabout|zawiya|touriba|koubba|emir|amir",
    re.IGNORECASE,
)

PLACEHOLDER = re.compile(
    r"non nomm[ée]|non name|unnamed|unknown|inconnu|^\d+$|^$",
    re.IGNORECASE,
)

_CATS = ",".join(f"'{c}'" for c in sorted(TOURISM_CATEGORIES))

_NOTABLE_SQL = (
    "name ~* '(grande|kebir|great|basilique|basilica|cath[ée]drale|synagogue|"
    "abbaye|abbey|historique|historic|ancien|ancienne|sidi|saint|mus[ée]e|"
    "mausol[ée]e|marabout|zawiya|touriba|koubba|emir|amir)'"
)

_KEEP = f"""
(category IN ({_CATS}))
OR (category = 'religious' AND (photo_url IS NOT NULL OR {_NOTABLE_SQL}))
OR (category IN ('restaurant', 'cafe') AND photo_url IS NOT NULL)
"""

_CLEAN = """
AND name IS NOT NULL AND name != ''
AND NOT (name ~* 'non nomm[ée]|non nomme|non name|unnamed|unknown|inconnu')
AND latitude IS NOT NULL AND longitude IS NOT NULL
AND NOT (latitude = 0 AND longitude = 0)
"""

KEEP_PRED = f"({_KEEP} {_CLEAN})"
DROP_PRED = f"NOT ({_KEEP} {_CLEAN})"

_PARAMS: dict = {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="execute deletes")
    parser.add_argument(
        "--backup",
        default="scripts/data/reports/pruned_pois.json",
        help="path for the dropped-rows backup",
    )
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    report_dir = Path(args.backup).parent
    report_dir.mkdir(parents=True, exist_ok=True)

    with engine.begin() as conn:
        total = conn.execute(text("SELECT count(*) FROM pois")).scalar()

        keep_rows = conn.execute(
            text(f"SELECT count(*) FROM pois WHERE {KEEP_PRED}"), _PARAMS
        ).scalar()

        per_cat = conn.execute(
            text(
                f"SELECT category, count(*) AS kept FROM pois "
                f"WHERE {KEEP_PRED} GROUP BY category ORDER BY kept DESC"
            ),
            _PARAMS,
        ).mappings().fetchall()

        drop_rows = conn.execute(
            text(
                f"SELECT id, name, category, wilaya_id, source, latitude, longitude "
                f"FROM pois WHERE {DROP_PRED}"
            ),
            _PARAMS,
        ).mappings().fetchall()

        print(f"total POIs            : {total}")
        print(f"keep (curated)        : {keep_rows}")
        print(f"drop                  : {len(drop_rows)}")
        print("\nkept by category:")
        for r in per_cat:
            print(f"  {r['category']:12} {r['kept']}")

        drop_by_cat: dict[str, int] = {}
        for r in drop_rows:
            drop_by_cat[r["category"]] = drop_by_cat.get(r["category"], 0) + 1
        print("\ndropped by category:")
        for cat, c in sorted(drop_by_cat.items(), key=lambda kv: -kv[1]):
            print(f"  {cat:12} {c}")

        wilaya_after = conn.execute(
            text(f"SELECT count(DISTINCT wilaya_id) FROM pois WHERE {KEEP_PRED}"),
            _PARAMS,
        ).scalar()
        print(f"\nwilayas still covered : {wilaya_after}/69")

        # Bottom wilayas after prune (those that drop below ~15 POIs).
        low = conn.execute(
            text(
                f"SELECT w.name_fr, count(x.id) FROM wilayas w "
                f"LEFT JOIN (SELECT id, wilaya_id FROM pois WHERE {KEEP_PRED}) x "
                f"ON x.wilaya_id = w.id "
                f"GROUP BY w.name_fr HAVING count(x.id) < 15 ORDER BY 2 ASC"
            ),
            _PARAMS,
        ).mappings().fetchall()
        if low:
            print("\nwilayas with <15 POIs after prune:")
            for r in low:
                print(f"  {r['name_fr']:28} {r['count']}")

        if not args.apply:
            print("\n[dry-run] nothing changed. Re-run with --apply to delete.")
            return 0

        with open(args.backup, "w", encoding="utf-8") as fh:
            json.dump(
                [
                    {
                        "id": str(r["id"]),
                        "name": r["name"],
                        "category": r["category"],
                        "wilaya_id": r["wilaya_id"],
                        "source": r["source"],
                        "latitude": r["latitude"],
                        "longitude": r["longitude"],
                    }
                    for r in drop_rows
                ],
                fh,
                ensure_ascii=False,
                indent=1,
            )
        print(f"\nbacked up {len(drop_rows)} dropped rows to {args.backup}")

        conn.execute(
            text(
                f"DELETE FROM poi_experiences WHERE poi_id IN "
                f"(SELECT id FROM pois WHERE {DROP_PRED})"
            ),
            _PARAMS,
        )
        result = conn.execute(
            text(f"DELETE FROM pois WHERE {DROP_PRED}"), _PARAMS
        )
        remaining = conn.execute(text("SELECT count(*) FROM pois")).scalar()
        print(f"deleted {result.rowcount} POIs; remaining: {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
