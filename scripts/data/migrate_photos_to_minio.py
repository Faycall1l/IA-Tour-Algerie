#!/usr/bin/env python3
"""Migrate POI photos from Wikimedia Commons URLs to local MinIO storage.

Checkpointed — saves progress to minio_migration_state.json so it can be
interrupted and resumed. Uses conservative rate limiting (5s between requests)
to avoid hitting Wikimedia's 429 rate limit.

Usage:
    python3 scripts/data/migrate_photos_to_minio.py
"""

import asyncio
import hashlib
import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from minio import Minio
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = ROOT / "minio_migration_state.json"

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://athar:athar_pass@localhost:5432/athar_db"
)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "athar-uploads")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DELAY_BETWEEN_REQUESTS = 5  # seconds
MAX_RETRIES = 5


def _public_url(object_name: str) -> str:
    scheme = "https" if MINIO_SECURE else "http"
    return f"{scheme}://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{object_name}"


def get_object_name(url: str) -> str:
    norm_url = url.replace("http://commons.wikimedia.org", "https://commons.wikimedia.org")
    name_hash = hashlib.md5(norm_url.encode()).hexdigest()[:12]
    parsed = urlparse(norm_url)
    fn = parsed.path.rsplit("/", 1)[-1] if parsed.path else "unknown"
    ext = Path(fn.split("?")[0]).suffix or ".jpg"
    return f"pois/{name_hash}{ext}"


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed_urls": [], "failed_urls": [], "migrated_count": 0}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


async def download_one(client: httpx.AsyncClient, url: str) -> bytes | None:
    for attempt in range(MAX_RETRIES):
        try:
            norm_url = url.replace("http://commons.wikimedia.org", "https://commons.wikimedia.org")
            resp = await client.get(norm_url)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                logger.warning("429 on %s, waiting %ds (attempt %d)", url[:50], wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if not ct.startswith("image/"):
                logger.warning("Not an image: %s (%s)", url[:50], ct)
                return None
            return resp.content
        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(10)
            else:
                logger.error("Failed %s: %s", url[:50], exc)
                return None
    return None


async def main():
    engine = create_engine(DATABASE_URL)
    mc = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )

    # Ensure bucket exists
    if not mc.bucket_exists(MINIO_BUCKET):
        mc.make_bucket(MINIO_BUCKET)

    # Get all MinIO object names
    minio_names = {o.object_name for o in mc.list_objects(MINIO_BUCKET, prefix="pois/", recursive=True)}
    logger.info("Existing MinIO objects: %d", len(minio_names))

    # Get remaining external URLs from DB
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT unnest(photo_urls || ARRAY[photo_url]) as url
            FROM pois
            WHERE photo_url NOT LIKE '%localhost:9000%'
              AND (photo_url IS NOT NULL OR (photo_urls IS NOT NULL AND array_length(photo_urls, 1) > 0))
        """)).fetchall()

    all_urls = [r[0] for r in rows]
    logger.info("Remaining unique URLs: %d", len(all_urls))

    # Filter out already-completed URLs and already-uploaded objects
    state = load_state()
    completed = set(state.get("completed_urls", []))
    failed = set(state.get("failed_urls", []))

    url_map = {}

    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True, timeout=60) as client:
        for i, url in enumerate(all_urls):
            if url in completed:
                obj_name = get_object_name(url)
                url_map[url] = _public_url(obj_name)
                continue
            if url in failed:
                continue

            obj_name = get_object_name(url)

            # Check if already in MinIO
            if obj_name in minio_names:
                url_map[url] = _public_url(obj_name)
                completed.add(url)
                state["completed_urls"] = list(completed)
                save_state(state)
                continue

            logger.info("[%d/%d] Downloading %s", i + 1, len(all_urls), url[:60])
            data = await download_one(client, url)
            if data is None:
                failed.add(url)
                state["failed_urls"] = list(failed)
                save_state(state)
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
                continue

            try:
                mc.put_object(MINIO_BUCKET, obj_name, io.BytesIO(data), len(data), content_type="image/jpeg")
                url_map[url] = _public_url(obj_name)
                minio_names.add(obj_name)
                completed.add(url)
                state["completed_urls"] = list(completed)
                state["migrated_count"] = len(completed)
                save_state(state)
                logger.info("  -> %s (%d KB)", obj_name, len(data) // 1024)
            except Exception as exc:
                logger.error("MinIO upload failed for %s: %s", obj_name, exc)
                failed.add(url)
                state["failed_urls"] = list(failed)
                save_state(state)

            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

    logger.info("Download phase complete. %d succeeded, %d failed", len(completed), len(failed))

    # Update DB
    with engine.connect() as conn:
        pois = conn.execute(text("""
            SELECT id, photo_url, photo_urls FROM pois
            WHERE photo_url NOT LIKE '%localhost:9000%'
              AND (photo_url IS NOT NULL OR (photo_urls IS NOT NULL AND array_length(photo_urls, 1) > 0))
        """)).fetchall()

    updated = 0
    with engine.begin() as conn:
        for pid, pu, pua in pois:
            npu = pu
            npua = list(pua or [])
            ch = False
            if pu and pu in url_map:
                npu = url_map[pu]
                ch = True
            if pua:
                new_u = [url_map.get(u, u) for u in pua]
                if new_u != list(pua):
                    npua = new_u
                    ch = True
            if ch:
                conn.execute(
                    text("UPDATE pois SET photo_url = :u, photo_urls = :urls WHERE id = :id"),
                    {"id": pid, "u": npu, "urls": npua},
                )
                updated += 1

    logger.info("DB updated: %d POIs", updated)

    with engine.connect() as conn:
        m = conn.execute(text("SELECT COUNT(*) FROM pois WHERE photo_url LIKE '%localhost:9000%'")).scalar()
        r = conn.execute(
            text("SELECT COUNT(*) FROM pois WHERE photo_url IS NOT NULL AND photo_url NOT LIKE '%localhost:9000%'")
        ).scalar()
    logger.info("Final: %d MinIO, %d external", m, r)

    if failed:
        logger.warning("Failed URLs (%d):", len(failed))
        for u in failed:
            logger.warning("  %s", u)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(main())
