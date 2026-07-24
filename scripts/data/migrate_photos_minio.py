#!/usr/bin/env python3
"""Migrate Wikimedia Commons photo URLs to local MinIO storage.

Downloads unique images from commons.wikimedia.org/upload.wikimedia.org,
uploads to MinIO bucket 'athar-uploads/pois/', and batch-updates DB.
Deduplicates: downloads each unique URL once, updates all POIs referencing it.

Usage:
    python -m scripts.data.migrate_photos_minio [--limit N] [--batch N] [--dry-run]
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
import time
import random
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MINIO_ENDPOINT = settings.minio.endpoint
MINIO_ACCESS_KEY = settings.minio.access_key
MINIO_SECRET_KEY = settings.minio.secret_key
MINIO_BUCKET = settings.minio.bucket
MINIO_SECURE = settings.minio.secure

EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

HEADERS = {"User-Agent": "ATHAR-Tourism/1.0 (https://athar-os.com; photo migration)"}


def get_minio_client() -> Minio:
    client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"],
            }],
        }
        client.set_bucket_policy(MINIO_BUCKET, json.dumps(policy))
        log.info("Created bucket %s with public read policy", MINIO_BUCKET)
    return client


def public_url(object_name: str) -> str:
    scheme = "https" if MINIO_SECURE else "http"
    return f"{scheme}://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{object_name}"


def object_name_from_url(url: str, ext: str) -> str:
    """Generate a deterministic object name from URL hash."""
    import hashlib
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"photos/{h}{ext}"


def download_and_upload(
    client: Minio,
    http: httpx.Client,
    url: str,
) -> tuple[str | None, str]:
    """Download image from URL, upload to MinIO. Returns (minio_url, ext) or (None, ext)."""
    for attempt in range(3):
        try:
            obj_name = object_name_from_url(url, ".jpg")

            # Check if already uploaded
            try:
                client.stat_object(MINIO_BUCKET, obj_name)
                return public_url(obj_name), ".jpg"
            except Exception:
                pass

            # Single request with follow_redirects — no double download
            resp = http.get(url, headers=HEADERS, follow_redirects=True, timeout=20)

            if resp.status_code == 429:
                wait = min(30, 5 * (attempt + 1) + random.uniform(0, 2))
                log.debug("Rate limited, waiting %.1fs", wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            ct_main = content_type.split(";")[0].strip()
            ext = EXTENSION_MAP.get(ct_main, ".jpg")

            content = resp.content
            if len(content) < 500:
                return None, ext

            obj_name = object_name_from_url(url, ext)

            client.put_object(
                bucket_name=MINIO_BUCKET,
                object_name=obj_name,
                data=io.BytesIO(content),
                length=len(content),
                content_type=ct_main,
            )
            return public_url(obj_name), ext

        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            log.debug("Failed %s: %s", url[:80], e)
            return None, ".jpg"


async def fetch_unique_urls(db: AsyncSession, limit: int, offset: int) -> list[tuple[str, list[str]]]:
    """Fetch unique Wikimedia URLs and the POI IDs that reference each."""
    rows = await db.execute(
        text("""
            SELECT photo_urls[1] as url, array_agg(id) as poi_ids, COUNT(*) as cnt
            FROM pois
            WHERE array_length(photo_urls, 1) > 0
              AND (photo_urls[1] LIKE '%commons.wikimedia%'
                   OR photo_urls[1] LIKE '%upload.wikimedia%')
            GROUP BY photo_urls[1]
            ORDER BY cnt DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )
    return [(r[0], list(r[1]), r[2]) for r in rows.all()]


async def update_photo_urls(db: AsyncSession, new_url: str, poi_ids: list[str]):
    """Batch update POIs from old Wikimedia URL to new MinIO URL."""
    if not poi_ids:
        return
    await db.execute(
        text("UPDATE pois SET photo_urls = ARRAY[:url]::text[] WHERE id = ANY(:ids)"),
        {"url": new_url, "ids": poi_ids},
    )


async def migrate(batch_size: int = 100, dry_run: bool = False, max_total: int = 0):
    url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://athar:athar@localhost:5432/athar_db")
    engine = create_async_engine(url)

    async with AsyncSession(engine) as db:
        count_q = await db.execute(text("""
            SELECT COUNT(DISTINCT photo_urls[1]) FROM pois
            WHERE array_length(photo_urls, 1) > 0
              AND (photo_urls[1] LIKE '%commons.wikimedia%'
                   OR photo_urls[1] LIKE '%upload.wikimedia%')
        """))
        total = count_q.scalar() or 0
        log.info("Unique Wikimedia URLs to migrate: %d", total)

        if max_total > 0:
            total = min(total, max_total)

        minio_client = get_minio_client()
        migrated = 0
        errors = 0
        offset = 0

        def _download_group(group: tuple) -> list[tuple[str, str, list[str]]]:
            """Download a group of URLs in a thread. Returns list of (minio_url, poi_ids_str, error)."""
            wiki_url, poi_ids, cnt = group
            with httpx.Client(follow_redirects=True, timeout=20) as http:
                minio_url, ext = download_and_upload(minio_client, http, wiki_url)
            return (minio_url, wiki_url, poi_ids)

        while offset < total:
            url_groups = await fetch_unique_urls(db, batch_size, offset)
            if not url_groups:
                break

            if dry_run:
                log.info("[DRY RUN] Would migrate %d unique URLs (%d total POIs)",
                         len(url_groups), sum(g[2] for g in url_groups))
                for wiki_url, poi_ids, cnt in url_groups[:5]:
                    log.info("  %d POIs: %s", cnt, wiki_url[:80])
                break

            # Download up to 3 URLs in parallel (Wikimedia rate limits ~1 req/s)
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(_download_group, g): g for g in url_groups}
                for future in as_completed(futures):
                    try:
                        minio_url, wiki_url, poi_ids = future.result()
                        if minio_url:
                            await update_photo_urls(db, minio_url, poi_ids)
                            migrated += 1
                        else:
                            errors += 1
                    except Exception as e:
                        errors += 1
                        log.debug("Thread error: %s", e)

            await db.commit()
            offset += batch_size
            # Brief pause between batches to respect rate limits
            time.sleep(2)

            if migrated % 50 == 0 or offset >= total:
                log.info("Progress: %d/%d unique URLs migrated, %d errors",
                         migrated, total, errors)

        log.info("DONE: %d unique URLs migrated, %d errors out of %d total",
                 migrated, errors, total)

    await engine.dispose()


def main():
    parser = ArgumentParser(description="Migrate Wikimedia photos to MinIO (deduplicated)")
    parser.add_argument("--batch", type=int, default=100, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    parser.add_argument("--limit", type=int, default=0, help="Max unique URLs to migrate (0=all)")
    args = parser.parse_args()
    asyncio.run(migrate(batch_size=args.batch, dry_run=args.dry_run, max_total=args.limit))


if __name__ == "__main__":
    main()
