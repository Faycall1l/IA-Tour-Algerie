#!/usr/bin/env python3
"""Enrich named POIs with real Wikidata P18 (image) photos.

Targets POIs that carry a `wikidata` reference in `osm_tags` but have no
photo. For each target it fetches the item's P18 claim via a batched SPARQL
VALUES query, converts the Commons filename to a direct upload.wikimedia.org
URL, downloads it, uploads it to MinIO, and writes the MinIO URL into
`photo_url` + `photo_urls`. Idempotent and checkpointed: only POIs without a
photo are considered on each run.

Reuses the MinIO download/upload machinery from `migrate_photos_minio` so all
photos land in the same `athar-uploads/photos/` namespace with the same
URL-hash naming and validation.

Usage:
    python -m scripts.data.enrich_photos_wikidata_p18 [--dry-run] [--limit N] [--batch N]
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich POIs with Wikidata P18 photos via MinIO")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report targets and expected SPARQL hits without downloading or updating",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to process (0 = all)")
    parser.add_argument(
        "--batch",
        type=int,
        default=50,
        help="DB update batch size (SPARQL chunks are derived from this)",
    )
    parser.add_argument(
        "--sparql-batch",
        type=int,
        default=100,
        help="Max QIDs per SPARQL VALUES query",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log.info("Wikidata P18 photo enrichment (dry_run=%s, limit=%d, batch=%d)",
             args.dry_run, args.limit, args.batch)


if __name__ == "__main__":
    main()
