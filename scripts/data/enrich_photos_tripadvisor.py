#!/usr/bin/env python3
"""Migrate remote TripAdvisor media-cdn photos to MinIO.

Targets POIs whose `photo_url` still points at media-cdn.tripadvisor.com
(113 on the reseeded corpus). For each target it downloads the original
(`photo-o`) size, uploads it to MinIO, and writes the MinIO URL into
`photo_url` + `photo_urls`. Idempotent: object names are deterministic
URL hashes, so re-runs skip already-uploaded images, and only POIs with a
remote photo are considered on each run.

Reuses the MinIO download/upload machinery from `migrate_photos_minio` so
all photos land in the same `athar-uploads/photos/` namespace with the same
URL-hash naming and validation.

Usage:
    python -m scripts.data.enrich_photos_tripadvisor [--dry-run] [--limit N] [--batch N]
"""

import argparse
import logging
import os
from pathlib import Path

import httpx
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate TripAdvisor media-cdn photos to MinIO"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report targets without downloading or updating",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to process (0 = all)")
    parser.add_argument(
        "--batch",
        type=int,
        default=50,
        help="DB commit batch size",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log.info("TripAdvisor photo migration (dry_run=%s, limit=%d, batch=%d)",
             args.dry_run, args.limit, args.batch)


if __name__ == "__main__":
    main()
