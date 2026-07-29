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

            # 4xx client errors (e.g., 400 bad thumbnail URL) will not succeed on retry
            if 400 <= resp.status_code < 500:
                log.warning("Client error %d for %s: skipping", resp.status_code, url[:80])
                return None, ".jpg"

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
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else 0
            if 400 <= status < 500:
                log.warning("Client error %d for %s: skipping", status, url[:80])
                return None, ".jpg"
            if attempt < 2:
                wait = min(30, 3 * (attempt + 1) + random.uniform(0, 2))
                log.warning("HTTP error %d for %s (attempt %d), retrying after %.1fs: %s",
                            status, url[:60], attempt + 1, wait, e)
                time.sleep(wait)
                continue
            log.warning("Failed %s after 3 attempts: %s", url[:80], e)
            return None, ".jpg"
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


_URL_ENCODED_BYTES = {
    # ASCII chars that are commonly percent-encoded in URLs
    *range(0x20, 0x30),  # space, ! " # $ % & ' ( )
    *range(0x3A, 0x41),  # : ; < = > ? @
    *range(0x5B, 0x5F),  # [ \ ] ^
    0x60,                 # `
    *range(0x7B, 0x7F),  # { | } ~
}


def _decode_underscore_encoded(name: str) -> str:
    """Decode Wikimedia filenames where % was replaced by _.

    Examples:
        Mus_C3_A9e_de_Tlemcen_12.jpg -> Musée_de_Tlemcen_12.jpg
        Map_of_Tassili_n_27Ajjer_and_surroundings-en.jpg -> Map_of_Tassili_n'Ajjer_and_surroundings-en.jpg
    """
    import re

    def _is_hex(s: str) -> bool:
        return len(s) == 2 and all(c in "0123456789abcdefABCDEF" for c in s)

    def _byte(s: str) -> int:
        return int(s, 16)

    result = []
    i = 0
    n = len(name)
    while i < n:
        if name[i] == "_" and i + 2 < n and _is_hex(name[i + 1 : i + 3]):
            b = _byte(name[i + 1 : i + 3])
            # Common single-byte encoded ASCII chars
            if b in _URL_ENCODED_BYTES:
                result.append(chr(b))
                i += 3
                continue
            # UTF-8 multi-byte sequences
            seq = bytes([b])
            i2 = i + 3
            if 0xC2 <= b <= 0xDF:
                expected_len = 2
            elif 0xE0 <= b <= 0xEF:
                expected_len = 3
            elif 0xF0 <= b <= 0xF4:
                expected_len = 4
            else:
                expected_len = 1

            while (
                len(seq) < expected_len
                and i2 + 2 < n
                and name[i2] == "_"
                and _is_hex(name[i2 + 1 : i2 + 3])
                and 0x80 <= _byte(name[i2 + 1 : i2 + 3]) <= 0xBF
            ):
                seq += bytes([_byte(name[i2 + 1 : i2 + 3])])
                i2 += 3

            if len(seq) == expected_len and expected_len > 1:
                try:
                    result.append(seq.decode("utf-8"))
                    i = i2
                    continue
                except Exception:
                    pass
            # Not a valid encoded sequence; keep the literal underscore
            result.append(name[i])
            i += 1
        else:
            result.append(name[i])
            i += 1
    return "".join(result)


def _normalize_wikimedia_url(url: str) -> str:
    """Normalize Wikimedia URLs to avoid slow redirects.

    - http://commons.wikimedia.org -> https://commons.wikimedia.org
    - Special:FilePath spaces (%20) -> underscores
    - Special:FilePath -> direct upload.wikimedia.org URL using MD5 hash dirs
      (avoids the slow commons.wikimedia.org redirect server)
    - Malformed thumbnail URLs (with _960px-... suffix) -> full-size upload.wikimedia.org URL
    - Underscore-encoded (% -> _) filenames are decoded back to proper characters
    """
    import urllib.parse

    if url.startswith("http://commons.wikimedia.org/"):
        url = "https" + url[4:]

    # Fix malformed thumbnail URLs and decode any underscore-encoded filenames
    thumb_fix = _fix_thumbnail_url(url)
    if thumb_fix:
        return thumb_fix

    direct = _direct_upload_url(url)
    if direct:
        return direct

    if "commons.wikimedia.org/wiki/Special:FilePath/" in url:
        prefix = "commons.wikimedia.org/wiki/Special:FilePath/"
        idx = url.index(prefix) + len(prefix)
        filename = urllib.parse.unquote(url[idx:])
        filename = _decode_underscore_encoded(filename)
        filename = filename.replace(" ", "_")
        url = url[:idx] + filename
        return url

    # Decode underscore-encoded upload.wikimedia.org URLs
    if "upload.wikimedia.org" in url:
        decoded = _decode_upload_wikimedia_url(url)
        if decoded:
            return decoded
    return url


def _fix_thumbnail_url(url: str) -> str | None:
    """Convert malformed Wikimedia thumbnail URLs to full-size upload.wikimedia.org URLs.

    Some stored URLs are broken thumbnails like:
        /wikipedia/commons/thumb/e/e3/Foo.jpg_960px-Foo/bar.jpg
        /wikipedia/commons/thumb/e/e3/Foo.jpg/960px-thumbnail.jpg
    The correct full-size URL is:
        /wikipedia/commons/e/e3/Foo.jpg
    """
    import re
    import urllib.parse

    # _<width>px-.../... suffix
    m = re.match(
        r"^(https?://upload\.wikimedia\.org/wikipedia/commons)/thumb/([0-9a-f]/[0-9a-f]{2}/.+?)_\d+px-[^/]+(?:/[^/]+)?$",
        url,
    )
    if m:
        filename = _decode_underscore_encoded(m.group(2))
        encoded = urllib.parse.quote(filename.replace(" ", "_"), safe="_/()")
        return f"{m.group(1)}/{encoded}"

    # /<width>px-.../... suffix
    m = re.match(
        r"^(https?://upload\.wikimedia\.org/wikipedia/commons)/thumb/([0-9a-f]/[0-9a-f]{2}/.+?)/\d+px-[^/]+(?:/[^/]+)?$",
        url,
    )
    if m:
        filename = _decode_underscore_encoded(m.group(2))
        encoded = urllib.parse.quote(filename.replace(" ", "_"), safe="_/()")
        return f"{m.group(1)}/{encoded}"

    return None


def _decode_upload_wikimedia_url(url: str) -> str | None:
    """Decode underscore-encoded full-size upload.wikimedia.org URLs.

    Example:
        https://upload.wikimedia.org/wikipedia/commons/e/eb/Mus_C3_A9e_public_...
      -> https://upload.wikimedia.org/wikipedia/commons/e/eb/Mus%C3%A9e_public_...
    """
    import re
    import urllib.parse

    m = re.match(
        r"^(https?://upload\.wikimedia\.org/wikipedia/commons/[0-9a-f]/[0-9a-f]{2}/)(.+)$",
        url,
    )
    if not m:
        return None
    prefix, filename = m.group(1), m.group(2)
    decoded = _decode_underscore_encoded(filename)
    encoded = urllib.parse.quote(decoded.replace(" ", "_"), safe="_/()")
    return f"{prefix}{encoded}"


def _direct_upload_url(url: str) -> str | None:
    """Convert a Wikimedia Commons Special:FilePath URL to a direct upload.wikimedia.org URL.

    Wikimedia file URL scheme: /wikipedia/commons/{md5[0]}/{md5[0:2]}/{filename}
    Filename must use underscores for spaces.
    """
    import urllib.parse

    if "Special:FilePath/" not in url:
        return None
    idx = url.index("Special:FilePath/") + len("Special:FilePath/")
    filename = urllib.parse.unquote(url[idx:])
    filename = _decode_underscore_encoded(filename)
    filename = filename.replace(" ", "_")
    if not filename:
        return None
    h = hashlib.md5(filename.encode("utf-8")).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[0:2]}/{filename}"


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
        url = _normalize_wikimedia_url(r[0])
        ids = set(r[1])
        groups.setdefault(url, (set(), set(), 0))
        photo_url_ids, photo_urls_ids, cnt = groups[url]
        photo_url_ids |= ids
        groups[url] = (photo_url_ids, photo_urls_ids, cnt + len(ids))

    for r in photo_urls_rows.all():
        url = _normalize_wikimedia_url(r[0])
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
        purl_total, purls_total, raw_total = await count_wikimedia_references(db)
        # Fetch the full normalized/deduplicated list once so total matches what we iterate.
        all_groups = await fetch_url_groups(db, 1000000, 0)
        total = len(all_groups)
        log.info("Wikimedia references to migrate: %d unique photo_url URLs, %d unique photo_urls[1] URLs, %d raw unique URLs, %d normalized unique URLs",
                 purl_total, purls_total, raw_total, total)

        if max_total > 0:
            total = min(total, max_total)
            all_groups = all_groups[:total]

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
            url_groups = all_groups[offset:offset + batch_size]
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
