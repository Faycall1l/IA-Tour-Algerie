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

REMOTE_HOSTS = ("media-cdn.tripadvisor.com", "dynamic-media-cdn.tripadvisor.com")
SIZE_TOKENS = ("photo-l", "photo-t", "photo-o", "photo-s", "photo-f")


def is_remote_url(url: str | None) -> bool:
    """True when the URL points off-box at a TripAdvisor CDN."""
    return bool(url and any(host in url for host in REMOTE_HOSTS))


def original_size_url(url: str) -> str:
    """Return the `photo-o` (original) variant of a TripAdvisor CDN URL.

    Falls back to the given URL when no recognized size token is present.
    """
    for token in SIZE_TOKENS:
        if token in url:
            return url.replace(token, "photo-o")
    return url


# ── DB ──────────────────────────────────────────────────────────────────────

TARGET_SQL = """
    SELECT id, name, photo_url
    FROM pois
    WHERE photo_url LIKE '%tripadvisor.com%'
    ORDER BY name
"""


def fetch_targets(conn, limit: int = 0) -> list[tuple[str, str, str]]:
    """Return (poi_id, name, remote_photo_url) rows needing migration."""
    cur = conn.cursor()
    if limit > 0:
        cur.execute(f"SELECT * FROM ({TARGET_SQL.rstrip(';')}) t LIMIT %s", (limit,))
    else:
        cur.execute(TARGET_SQL)
    rows = cur.fetchall()
    cur.close()
    return [(str(r[0]), r[1], r[2]) for r in rows]


# ── MinIO ────────────────────────────────────────────────────────────────────

def get_minio_client():
    """Reuse the migrate script's MinIO client (bucket + public-read policy)."""
    from scripts.data.migrate_photos_minio import get_minio_client as _get

    return _get()


def download_and_upload_to_minio(minio_client, http: httpx.Client, url: str):
    """Download an image and upload to MinIO. Returns minio_url or None."""
    from scripts.data.migrate_photos_minio import download_and_upload

    minio_url, _ext = download_and_upload(minio_client, http, url)
    return minio_url


def update_poi_photo(conn, poi_id: str, minio_url: str) -> None:
    """Replace the remote photo with a MinIO URL in photo_url + photo_urls."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE pois SET photo_url = %s, photo_urls = ARRAY[%s]::text[] WHERE id = %s",
        (minio_url, minio_url, poi_id),
    )
    cur.close()


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

    conn = psycopg2.connect(**DB_CONFIG)
    targets = fetch_targets(conn, args.limit)
    log.info("Targets: %d POIs with a remote TripAdvisor photo", len(targets))
    if not targets:
        conn.close()
        return

    if args.dry_run:
        log.info("[DRY RUN] %d/%d targets would be migrated", len(targets), len(targets))
        for _poi_id, name, url in targets[:10]:
            log.info("  %s -> %s", name, original_size_url(url)[:80])
        conn.close()
        return

    minio_client = get_minio_client()
    timeout = httpx.Timeout(30.0, connect=15.0, read=30.0)
    updated = 0
    failed = 0

    with httpx.Client(follow_redirects=True, timeout=timeout) as http:
        for poi_id, name, url in targets:
            if not is_remote_url(url):
                continue
            minio_url = download_and_upload_to_minio(minio_client, http, original_size_url(url))
            if not minio_url:
                failed += 1
                log.warning("Download/upload failed: %s [%s]", name, url[:70])
                continue
            update_poi_photo(conn, poi_id, minio_url)
            updated += 1
            if updated % args.batch == 0:
                conn.commit()
                log.info("Progress: %d migrated, %d failed", updated, failed)

    conn.commit()
    conn.close()
    log.info("DONE: %d POIs migrated, %d failures (of %d targets)", updated, failed, len(targets))


if __name__ == "__main__":
    main()
