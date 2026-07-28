#!/usr/bin/env python3
"""Migrate Wikimedia Commons photo URLs to local MinIO storage.

Downloads unique images from commons.wikimedia.org/upload.wikimedia.org,
uploads to MinIO bucket 'athar-uploads/photos/', and batch-updates DB.
Deduplicates: downloads each unique URL once, updates all POIs referencing it.

Handles both the single primary `photo_url` column and the `photo_urls` array,
so no Wikimedia references remain in either field.

Usage:
    python -m scripts.data.migrate_photos_minio [--limit N] [--batch N] [--dry-run]
"""

import asyncio
import hashlib
import io
import json
import logging
import os
import random
import time
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
            resp = http.get(url, headers=HEADERS, follow_redirects=True)

            if resp.status_code == 429:
                wait = min(60, 10 * (attempt + 1) + random.uniform(0, 5))
                log.warning("Rate limited on %s, waiting %.1fs", url[:60], wait)
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

        except httpx.TimeoutException as e:
            wait = min(60, 5 * (attempt + 1) + random.uniform(0, 3))
            log.warning("Timeout downloading %s (attempt %d), retrying after %.1fs: %s",
                        url[:60], attempt + 1, wait, e)
            time.sleep(wait)
            continue
        except Exception as e:
            if attempt < 2:
                wait = min(30, 3 * (attempt + 1) + random.uniform(0, 2))
                log.warning("Retryable error for %s (attempt %d), waiting %.1fs: %s",
                            url[:60], attempt + 1, wait, e)
                time.sleep(wait)
                continue
            log.warning("Failed %s after 3 attempts: %s", url[:80], e)
            return None, ".jpg"


def _is_wikimedia(url: str | None) -> bool:
    return bool(url and ("commons.wikimedia" in url or "upload.wikimedia" in url))


async def fetch_url_groups(db: AsyncSession, limit: int, offset: int) -> list[tuple[str, set[str], set[str], int]]:
    """Fetch unique Wikimedia URLs and the POI IDs referencing them.

    Returns list of (url, photo_url_ids, photo_urls_ids, total_poi_count).
    """
    photo_url_rows = await db.execute(
        text("""
            SELECT photo_url as url, array_agg(id) as poi_ids
            FROM pois
            WHERE photo_url LIKE '%commons.wikimedia%'
               OR photo_url LIKE '%upload.wikimedia%'
            GROUP BY photo_url
        """),
    )
    photo_urls_rows = await db.execute(
        text("""
            SELECT photo_urls[1] as url, array_agg(id) as poi_ids, COUNT(*) as cnt
            FROM pois
            WHERE array_length(photo_urls, 1) > 0
              AND (photo_urls[1] LIKE '%commons.wikimedia%'
                   OR photo_urls[1] LIKE '%upload.wikimedia%')
            GROUP BY photo_urls[1]
        """),
    )

    groups: dict[str, tuple[set[str], set[str], int]] = {}
    for r in photo_url_rows.all():
        url = r[0]
        ids = set(r[1])
        groups.setdefault(url, (set(), set(), 0))
        photo_url_ids, photo_urls_ids, cnt = groups[url]
        photo_url_ids |= ids
        groups[url] = (photo_url_ids, photo_urls_ids, cnt + len(ids))

    for r in photo_urls_rows.all():
        url = r[0]
        ids = set(r[1])
        cnt = r[2]
        groups.setdefault(url, (set(), set(), 0))
        photo_url_ids, photo_urls_ids, _ = groups[url]
        photo_urls_ids |= ids
        groups[url] = (photo_url_ids, photo_urls_ids, cnt + len(photo_url_ids))

    # Recompute total counts because photo_urls may overlap with photo_url
    sorted_groups = sorted(
        [(url, purl_ids, purls_ids, len(purl_ids | purls_ids)) for url, (purl_ids, purls_ids, _) in groups.items()],
        key=lambda x: x[3],
        reverse=True,
    )
    return sorted_groups[offset:offset + limit]


async def update_photo_url_single(db: AsyncSession, new_url: str, poi_ids: list[str]):
    """Update photo_url column for POIs whose single photo_url matched the Wikimedia URL."""
    if not poi_ids:
        return
    await db.execute(
        text("UPDATE pois SET photo_url = :url WHERE id = ANY(:ids)"),
        {"url": new_url, "ids": poi_ids},
    )


async def update_photo_urls_array(db: AsyncSession, new_url: str, poi_ids: list[str]):
    """Batch update POIs from old Wikimedia URL to new MinIO URL in the photo_urls array."""
    if not poi_ids:
        return
    await db.execute(
        text("UPDATE pois SET photo_urls = ARRAY[:url]::text[] WHERE id = ANY(:ids)"),
        {"url": new_url, "ids": poi_ids},
    )


async def count_wikimedia_references(db: AsyncSession) -> tuple[int, int, int]:
    """Return (unique photo_url wikimedia, unique photo_urls wikimedia, unique combined)."""
    purl = await db.execute(text("""
        SELECT COUNT(DISTINCT photo_url) FROM pois
        WHERE photo_url LIKE '%commons.wikimedia%' OR photo_url LIKE '%upload.wikimedia%'
    """))
    purls = await db.execute(text("""
        SELECT COUNT(DISTINCT photo_urls[1]) FROM pois
        WHERE array_length(photo_urls, 1) > 0
          AND (photo_urls[1] LIKE '%commons.wikimedia%' OR photo_urls[1] LIKE '%upload.wikimedia%')
    """))
    combined = await db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT photo_url as url FROM pois
            WHERE photo_url LIKE '%commons.wikimedia%' OR photo_url LIKE '%upload.wikimedia%'
            UNION
            SELECT DISTINCT photo_urls[1] as url FROM pois
            WHERE array_length(photo_urls, 1) > 0
              AND (photo_urls[1] LIKE '%commons.wikimedia%' OR photo_urls[1] LIKE '%upload.wikimedia%')
        ) t
    """))
    return purl.scalar() or 0, purls.scalar() or 0, combined.scalar() or 0


async def migrate(batch_size: int = 100, dry_run: bool = False, max_total: int = 0):
    url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://athar:athar@localhost:5432/athar_db")
    engine = create_async_engine(url)

    async with AsyncSession(engine) as db:
        purl_total, purls_total, total = await count_wikimedia_references(db)
        log.info("Wikimedia references to migrate: %d unique photo_url URLs, %d unique photo_urls[1] URLs, %d combined unique URLs",
                 purl_total, purls_total, total)

        if max_total > 0:
            total = min(total, max_total)

        minio_client = get_minio_client()
        migrated = 0
        errors = 0
        offset = 0

        def _download_group(group: tuple) -> tuple[str | None, str, set[str], set[str]]:
            """Download a group of URLs in a thread. Returns (minio_url, wiki_url, photo_url_ids, photo_urls_ids)."""
            wiki_url, photo_url_ids, photo_urls_ids, _ = group
            timeout = httpx.Timeout(30.0, connect=15.0, read=30.0)
            with httpx.Client(follow_redirects=True, timeout=timeout) as http:
                minio_url, ext = download_and_upload(minio_client, http, wiki_url)
            return minio_url, wiki_url, photo_url_ids, photo_urls_ids

        while offset < total:
            url_groups = await fetch_url_groups(db, batch_size, offset)
            if not url_groups:
                break

            if dry_run:
                total_pois = sum(len(purl_ids | purls_ids) for _, purl_ids, purls_ids, _ in url_groups)
                log.info("[DRY RUN] Would migrate %d unique URLs (%d total POIs)",
                         len(url_groups), total_pois)
                for wiki_url, purl_ids, purls_ids, _ in url_groups[:5]:
                    log.info("  %d photo_url + %d photo_urls POIs: %s",
                             len(purl_ids), len(purls_ids), wiki_url[:80])
                break

            # Download 1 URL at a time to respect Wikimedia rate limits and avoid hangs
            with ThreadPoolExecutor(max_workers=1) as pool:
                futures = {pool.submit(_download_group, g): g for g in url_groups}
                for future in as_completed(futures):
                    try:
                        minio_url, wiki_url, photo_url_ids, photo_urls_ids = future.result()
                        if minio_url:
                            await update_photo_url_single(db, minio_url, list(photo_url_ids))
                            await update_photo_urls_array(db, minio_url, list(photo_urls_ids))
                            migrated += 1
                            log.info("Migrated %d photo_url + %d photo_urls POIs: %s",
                                     len(photo_url_ids), len(photo_urls_ids), wiki_url[:80])
                        else:
                            errors += 1
                            log.warning("Failed to migrate: %s", wiki_url[:80])
                    except Exception as e:
                        errors += 1
                        log.warning("Thread error: %s", e)

            await db.commit()
            offset += batch_size
            # Pause between batches to respect Wikimedia rate limits
            log.info("Batch done; sleeping 5s before next batch")
            time.sleep(5)

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
