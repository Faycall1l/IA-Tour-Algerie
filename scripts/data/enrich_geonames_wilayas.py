#!/usr/bin/env python3
"""Targeted GeoNames enrichment for under-covered wilayas (data-v2 step 12).

Reads the GeoNames Algeria dump (`raw/geonames/DZ.txt`, real gazetteer data)
and inserts tourism-relevant features (peaks, dunes, springs, ruins, oases,
tombs, forts, parks…) into `pois` for wilayas that still have <50 POIs.

Wilaya assignment is coordinate-based (nearest of the 69 official centers),
the same scheme used by the OSM PBF extractor. Rows are deduplicated against
existing DB POIs by (wilaya, normalized name, ~5km coords) and within the
dump by geoname id. Each inserted POI carries `source='geonames'`,
`source_id=<geonameid>`, and a `geonames.org` website link.

Usage:
    python -m scripts.data.enrich_geonames_wilayas [--dry-run] [--limit N]
"""

import argparse
import logging
import os
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "athar_db",
    "user": "athar",
    "password": "athar_pass",
}

RAW_DIR = Path(__file__).resolve().parent / "raw"
GEONAMES_FILE = RAW_DIR / "geonames" / "DZ.txt"
CENTERS_FILE = RAW_DIR / "wilayas_centers.json"

TARGET_WILAYAS = (50, 52, 54, 57, 59, 62, 63, 64)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Targeted GeoNames POI enrichment for under-covered wilayas"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report candidates per wilaya without inserting",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to insert (0 = all)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log.info("GeoNames wilaya enrichment (dry_run=%s, limit=%d)", args.dry_run, args.limit)


if __name__ == "__main__":
    main()
